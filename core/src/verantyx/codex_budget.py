"""Persistent usage and idempotency receipts. No application-level call cap."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3
import uuid

from .domain.codec import canonical, decode, digest
from .errors import LedgerError

DB_NAME = "calls.sqlite3"
BOUNDARY = ("Application-level generation limits are disabled. Historical reservations, "
            "provider-reported usage and duplicate-request protection are retained. "
            "No automatic retry of failed or uncertain requests. Provider limits still apply.")
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")


def _require(condition, reason, code="BRIDGE_CONFIG"):
    if not condition:
        raise LedgerError(code, {"reason": reason})


def _now():
    return datetime.now(timezone.utc).isoformat()


def validate_cap(max_calls):
    _require(type(max_calls) is int and 1 <= max_calls <= 10000, "CODEX_CALL_CAP")


def initialize(directory, max_calls=4):
    """Create a new budget only. An existing or missing session is never reset."""
    validate_cap(max_calls)
    directory = Path(directory)
    _require(not directory.exists() and not directory.is_symlink(), "CODEX_BUDGET_EXISTS", "OUTPUT_EXISTS")
    directory.mkdir(mode=0o700, parents=True)
    path = directory / DB_NAME
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    connection = sqlite3.connect(path)
    try:
        connection.executescript("""
            CREATE TABLE session (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                session_id TEXT NOT NULL, max_calls INTEGER NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE calls (
                id INTEGER PRIMARY KEY, cache_key TEXT UNIQUE NOT NULL,
                request_sha256 TEXT NOT NULL, config_sha256 TEXT NOT NULL,
                role TEXT NOT NULL, model TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('IN_FLIGHT','SUCCEEDED','FAILED','UNKNOWN')),
                reserved_at TEXT NOT NULL, finished_at TEXT,
                output_json TEXT, output_sha256 TEXT, token_usage_json TEXT, error_code TEXT
            );
            PRAGMA user_version=1;
        """)
        connection.execute("INSERT INTO session VALUES (1, ?, ?, ?)", (uuid.uuid4().hex, max_calls, _now()))
        connection.commit()
    finally:
        connection.close()
    return str(path)


@contextmanager
def _database(directory, *, write=False):
    directory = Path(directory)
    path = directory / DB_NAME
    _require(directory.is_dir() and not directory.is_symlink() and path.is_file()
             and not path.is_symlink() and path.stat().st_nlink == 1, "CODEX_BUDGET_MISSING_OR_UNSAFE")
    connection = sqlite3.connect(path.resolve().as_uri() + ("?mode=rw" if write else "?mode=ro"),
                                 uri=True, timeout=5, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        _require(connection.execute("PRAGMA user_version").fetchone()[0] == 1, "CODEX_BUDGET_VERSION")
        connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def reserve(configuration, value):
    """Atomically reuse a successful receipt or reserve one call before launch."""
    request_hash, config_hash = digest(value), digest(configuration)
    key = digest({"request": request_hash, "config": config_hash, "adapter_contract": 1})
    with _database(configuration["budget_directory"], write=True) as connection:
        session = connection.execute("SELECT * FROM session WHERE singleton=1").fetchone()
        _require(session is not None, "CODEX_BUDGET_SESSION")
        found = connection.execute("SELECT * FROM calls WHERE cache_key=?", (key,)).fetchone()
        if found is not None:
            _require(found["status"] == "SUCCEEDED", "CODEX_REQUEST_ALREADY_RESERVED", "BRIDGE_OUTCOME_UNKNOWN")
            return dict(found)
        cursor = connection.execute(
            "INSERT INTO calls (cache_key,request_sha256,config_sha256,role,model,status,reserved_at) "
            "VALUES (?,?,?,?,?,'IN_FLIGHT',?)",
            (key, request_hash, config_hash, configuration["role"], configuration["model"], _now()))
        return dict(connection.execute("SELECT * FROM calls WHERE id=?", (cursor.lastrowid,)).fetchone())


def record_usage(directory, reservation_id, value):
    """Keep only provider-reported token counts, without inventing missing zeroes."""
    if type(value) is not dict:
        return
    tokens = {key: value[key] for key in TOKEN_FIELDS if type(value.get(key)) is int and value[key] >= 0}
    if not tokens:
        return
    with _database(directory, write=True) as connection:
        cursor = connection.execute("UPDATE calls SET token_usage_json=? WHERE id=? AND status='IN_FLIGHT'",
                                    (canonical(tokens), reservation_id))
        _require(cursor.rowcount == 1, "CODEX_RESERVATION_STATE")


def finish(directory, reservation_id, *, status, output=None, error_code=None):
    _require(status in ("SUCCEEDED", "FAILED", "UNKNOWN"), "CODEX_RESERVATION_STATE")
    _require((status == "SUCCEEDED") == (output is not None), "CODEX_RESERVATION_OUTPUT")
    with _database(directory, write=True) as connection:
        cursor = connection.execute(
            "UPDATE calls SET status=?,finished_at=?,output_json=?,output_sha256=?,error_code=? "
            "WHERE id=? AND status='IN_FLIGHT'",
            (status, _now(), canonical(output) if output is not None else None,
             digest(output) if output is not None else None, error_code, reservation_id))
        _require(cursor.rowcount == 1, "CODEX_RESERVATION_STATE")


def usage(directory):
    """Read receipts without creating a database, starting a process or resetting."""
    with _database(directory) as connection:
        session = connection.execute("SELECT * FROM session WHERE singleton=1").fetchone()
        _require(session is not None, "CODEX_BUDGET_SESSION")
        rows = connection.execute(
            "SELECT id,request_sha256,config_sha256,role,model,status,reserved_at,finished_at,"
            "output_sha256,token_usage_json,error_code FROM calls ORDER BY id").fetchall()
    calls, totals, roles = [], {}, {"implementation": 0, "verification": 0}
    missing = 0
    for row in rows:
        item = dict(row)
        raw = item.pop("token_usage_json")
        item["provider_reported_tokens"] = decode(raw) if raw is not None else None
        missing += raw is None
        roles[item["role"]] = roles.get(item["role"], 0) + 1
        for key, count in (item["provider_reported_tokens"] or {}).items():
            totals[key] = totals.get(key, 0) + count
        calls.append(item)
    return {"schema_version": 1, "format": "verantyx.codex-usage.v1", "session_id": session["session_id"],
            "max_calls": None, "calls_reserved": len(calls), "call_limit_enforced": False,
            "legacy_max_calls": session["max_calls"], "calls_remaining": None, "calls_by_role": roles,
            "provider_reported_tokens": totals, "calls_without_token_usage": missing,
            "token_or_cost_hard_limit": False, "boundary": BOUNDARY, "calls": calls}
