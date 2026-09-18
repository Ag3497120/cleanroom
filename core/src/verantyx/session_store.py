"""Private console state. Separate from model prose and exportable skill records.

Names, workspace consent, candidate-edit grants and memo history are host-owned
SQLite rows. Imported notebooks and model responses cannot create these grants.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import unicodedata
import uuid

from .errors import LedgerError
from .personal_profile import connection
from .domain.codec import canonical

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS cr_workspace (root TEXT PRIMARY KEY, identity TEXT NOT NULL, trusted INTEGER NOT NULL DEFAULT 0, agent TEXT, room TEXT)",
    "CREATE TABLE IF NOT EXISTS cr_session (id TEXT PRIMARY KEY, root TEXT NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS cr_room (id TEXT PRIMARY KEY, root TEXT NOT NULL, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS cr_run (run_id TEXT NOT NULL, root TEXT NOT NULL, agent TEXT NOT NULL, room TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(root,run_id))",
    "CREATE TABLE IF NOT EXISTS cr_memo (id TEXT PRIMARY KEY, root TEXT NOT NULL, room TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL, run_id TEXT)",
    "CREATE INDEX IF NOT EXISTS cr_memo_room ON cr_memo(root,room,created_at)",
    "CREATE INDEX IF NOT EXISTS cr_memo_paging ON cr_memo(root,room,created_at DESC,id DESC)",
    "CREATE INDEX IF NOT EXISTS cr_run_agent ON cr_run(root,agent,created_at)",
    "CREATE INDEX IF NOT EXISTS cr_run_room ON cr_run(root,room,created_at)",
    "CREATE TABLE IF NOT EXISTS cr_preference (root TEXT PRIMARY KEY, document TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS cr_grant (id TEXT PRIMARY KEY, root TEXT NOT NULL, scope TEXT NOT NULL, kind TEXT NOT NULL, created_at TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS cr_summary (id TEXT PRIMARY KEY, root TEXT NOT NULL, agent TEXT NOT NULL, document TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS cr_summary_session ON cr_summary(root,agent,created_at DESC)",
    "CREATE TABLE IF NOT EXISTS cr_legacy_import (root TEXT PRIMARY KEY)",
    "CREATE TABLE IF NOT EXISTS cr_summary_source (root TEXT NOT NULL, agent TEXT NOT NULL, source_ref TEXT NOT NULL, event_hash TEXT NOT NULL, run_id TEXT NOT NULL, summary_id TEXT NOT NULL, PRIMARY KEY(root,agent,source_ref))",
)
DEFAULT_PREFERENCES = {"auto_compact": False, "context_window": None, "compact_threshold": 0.75,
                       "model_windows": {}}
RESERVED = {"verantyx", "vernatyx", "new", "compact", "cleanroom", "help", "commands", "model",
            "models", "settings", "setup", "attach", "detach", "queue", "approvals", "tutorial",
            "done", "close", "history", "scope", "review", "learn", "notebook", "details", "quit", "insights"}


def now():
    return datetime.now(timezone.utc).isoformat()


def root_key(root):
    return str(Path(root).expanduser().resolve())


def directory_identity(root):
    stat = Path(root).stat()
    return hashlib.sha256((root_key(root) + ":" + str(stat.st_dev) + ":" + str(stat.st_ino)).encode()).hexdigest()


@contextmanager
def db():
    with connection(True) as store:
        for statement in SCHEMA:
            store.execute(statement)
        yield store


def _name(name):
    if not isinstance(name, str):
        raise LedgerError("ARGUMENTS", {"reason": "CLEANROOM_NAME"})
    name = unicodedata.normalize("NFKC", name).strip()
    if not 1 <= len(name) <= 80 or any(unicodedata.category(c).startswith("C") or c in "/\\" for c in name):
        raise LedgerError("ARGUMENTS", {"reason": "CLEANROOM_NAME"})
    if name.casefold() in RESERVED:
        raise LedgerError("ARGUMENTS", {"reason": "RESERVED_CLEANROOM_NAME"})
    return name


def _initial(store, root):
    key, identity = root_key(root), directory_identity(root)
    store.execute("INSERT OR IGNORE INTO cr_workspace(root,identity) VALUES(?,?)", (key, identity))
    row = store.execute("SELECT identity,agent,room FROM cr_workspace WHERE root=?", (key,)).fetchone()
    if row[0] != identity:
        store.execute("UPDATE cr_workspace SET identity=?,trusted=0 WHERE root=?", (identity, key))
    agent, room = row[1], row[2]
    if not agent:
        agent = uuid.uuid4().hex
        store.execute("INSERT INTO cr_session VALUES(?,?,?,?)", (agent, key, "Session " + now()[:19], now()))
        store.execute("UPDATE cr_workspace SET agent=? WHERE root=?", (agent, key))
    if not room:
        room = uuid.uuid4().hex
        base = (Path(key).name or "Cleanroom")[:60]
        try:
            base = _name(base)
        except LedgerError:
            base = "My Cleanroom"
        name = base
        suffix = 1
        while store.execute("SELECT 1 FROM cr_room WHERE name_key=?", (name.casefold(),)).fetchone():
            suffix += 1
            name = base + " " + str(suffix)
        store.execute("INSERT INTO cr_room VALUES(?,?,?,?,?)", (room, key, name, name.casefold(), now()))
        store.execute("UPDATE cr_workspace SET room=? WHERE root=?", (room, key))
    return key, agent, room


def current(root):
    with db() as store:
        key, agent, room = _initial(store, root)
        agent_row = store.execute("SELECT name,created_at FROM cr_session WHERE id=?", (agent,)).fetchone()
        room_row = store.execute("SELECT name,created_at FROM cr_room WHERE id=?", (room,)).fetchone()
    return {"agent": {"id": agent, "name": agent_row[0], "created_at": agent_row[1]},
            "room": {"id": room, "name": room_row[0], "created_at": room_row[1]}}


def trusted(root):
    key, identity = root_key(root), directory_identity(root)
    with db() as store:
        row = store.execute("SELECT identity,trusted FROM cr_workspace WHERE root=?", (key,)).fetchone()
    return bool(row and row[0] == identity and row[1])


def trust(root):
    with db() as store:
        key, _, _ = _initial(store, root)
        store.execute("UPDATE cr_workspace SET trusted=1 WHERE root=?", (key,))


def new_agent(root, name=None):
    identity = uuid.uuid4().hex
    name = _name(name) if name else "Session " + now()[:19]
    with db() as store:
        key, _, _ = _initial(store, root)
        store.execute("INSERT INTO cr_session VALUES(?,?,?,?)", (identity, key, name, now()))
        store.execute("UPDATE cr_workspace SET agent=? WHERE root=?", (identity, key))
    return current(root)


def new_room(root, name):
    name, identity = _name(name), uuid.uuid4().hex
    with db() as store:
        key, _, _ = _initial(store, root)
        if store.execute("SELECT 1 FROM cr_room WHERE name_key=?", (name.casefold(),)).fetchone():
            raise LedgerError("ARGUMENTS", {"reason": "CLEANROOM_NAME_EXISTS"})
        store.execute("INSERT INTO cr_room VALUES(?,?,?,?,?)", (identity, key, name, name.casefold(), now()))
        store.execute("UPDATE cr_workspace SET room=? WHERE root=?", (identity, key))
    return current(root)


def rooms(root):
    with db() as store:
        key, _, active = _initial(store, root)
        rows = store.execute("SELECT id,name,created_at FROM cr_room WHERE root=? ORDER BY created_at", (key,)).fetchall()
    return [{"id": row[0], "name": row[1], "created_at": row[2], "active": row[0] == active} for row in rows]


def rename_room(root, room_id, name):
    name = _name(name)
    with db() as store:
        key, _, _ = _initial(store, root)
        conflict = store.execute("SELECT id FROM cr_room WHERE name_key=?", (name.casefold(),)).fetchone()
        if conflict and conflict[0] != room_id:
            raise LedgerError("ARGUMENTS", {"reason": "CLEANROOM_NAME_EXISTS"})
        if not store.execute("SELECT 1 FROM cr_room WHERE root=? AND id=?", (key, room_id)).fetchone():
            raise LedgerError("ARGUMENTS")
        store.execute("UPDATE cr_room SET name=?,name_key=? WHERE root=? AND id=?", (name, name.casefold(), key, room_id))
    return current(root)


def switch_room(root, room_id):
    with db() as store:
        key, _, _ = _initial(store, root)
        if not store.execute("SELECT 1 FROM cr_room WHERE root=? AND id=?", (key, room_id)).fetchone():
            raise LedgerError("ARGUMENTS")
        store.execute("UPDATE cr_workspace SET room=? WHERE root=?", (room_id, key))
    return current(root)


def bind_run(root, run_id, *, agent=None, room=None):
    with db() as store:
        key, current_agent, current_room = _initial(store, root)
        agent, room = agent or current_agent, room or current_room
        if not store.execute("SELECT 1 FROM cr_session WHERE root=? AND id=?", (key, agent)).fetchone():
            raise LedgerError("ARGUMENTS")
        if not store.execute("SELECT 1 FROM cr_room WHERE root=? AND id=?", (key, room)).fetchone():
            raise LedgerError("ARGUMENTS")
        store.execute("INSERT OR IGNORE INTO cr_run VALUES(?,?,?,?,?)", (run_id, key, agent, room, now()))


def runs(root, *, agent=None, room=None):
    with db() as store:
        key, current_agent, current_room = _initial(store, root)
        column, identity = ("room", room) if room else ("agent", agent or current_agent)
        rows = store.execute("SELECT run_id FROM cr_run WHERE root=? AND " + column + "=? ORDER BY created_at",
                             (key, identity)).fetchall()
    return [row[0] for row in rows]


def import_legacy(root, notes, run_ids=()):
    """One-time, lossless import; never deletes or rewrites project JSONL."""
    with db() as store:
        key, agent, room = _initial(store, root)
        if store.execute("SELECT 1 FROM cr_legacy_import WHERE root=?", (key,)).fetchone():
            return
        for row in notes:
            identity = hashlib.sha256((key + ":" + row["id"]).encode()).hexdigest()
            store.execute("INSERT OR IGNORE INTO cr_memo VALUES(?,?,?,?,?,?)",
                          (identity, key, room, row["body"], row["created_at"], row.get("run_id")))
        for run_id in run_ids:
            store.execute("INSERT OR IGNORE INTO cr_run VALUES(?,?,?,?,?)", (run_id, key, agent, room, now()))
        store.execute("INSERT INTO cr_legacy_import VALUES(?)", (key,))


def save_memo(root, body, *, key, run_id=None, room=None):
    if not isinstance(body, str) or not body.strip() or len(body) > 4000:
        raise LedgerError("ARGUMENTS")
    with db() as store:
        path, _, current_room = _initial(store, root)
        room = room or current_room
        if not store.execute("SELECT 1 FROM cr_room WHERE root=? AND id=?", (path, room)).fetchone():
            raise LedgerError("ARGUMENTS")
        prior = store.execute("SELECT root,room,body,created_at,run_id FROM cr_memo WHERE id=?", (key,)).fetchone()
        if prior and (prior[0], prior[1], prior[2], prior[4]) != (path, room, body, run_id):
            raise LedgerError("IDEMPOTENCY_CONFLICT")
        stamp = prior[3] if prior else now()
        store.execute("INSERT OR IGNORE INTO cr_memo VALUES(?,?,?,?,?,?)", (key, path, room, body, stamp, run_id))
    return {"id": key, "body": body, "created_at": stamp, "run_id": run_id,
            "body_sha256": hashlib.sha256(body.encode()).hexdigest(), "authority": "REFERENCE_ONLY",
            "attribution": "LOCAL_INPUT_NOT_AUTHENTICATED", "format": "cleanroom.owner-note.v1"}


def memo_page(root, room=None, *, limit=200, offset=0, query=""):
    """Read-only, bounded windows; the archive is never truncated or deleted."""
    limit, offset = min(200, max(1, int(limit))), max(0, int(offset))
    with connection() as store:
        if store is None or not store.execute("SELECT 1 FROM sqlite_master WHERE name='cr_memo'").fetchone():
            return {"rows": [], "total": 0, "offset": offset, "limit": limit, "query": query}
        path = root_key(root)
        if room is None:
            current_row = store.execute("SELECT room FROM cr_workspace WHERE root=?", (path,)).fetchone()
            room = current_row[0] if current_row else None
        clause, args = "root=? AND room=?", [path, room]
        if query.strip():
            # ESCAPE prevents % and _ in the user's text becoming SQL patterns.
            value = query.strip()[:4000].replace("!", "!!").replace("%", "!%").replace("_", "!_")
            clause += " AND body LIKE ? ESCAPE '!'"
            args.append("%" + value + "%")
        total = store.execute("SELECT COUNT(*) FROM cr_memo WHERE " + clause, args).fetchone()[0]
        rows = store.execute("SELECT id,body,created_at,run_id FROM cr_memo WHERE " + clause
                             + " ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?", [*args, limit, offset]).fetchall()
    # The existing catalogue reverses chronological notes for its newest-first view.
    notes = [{"id": row[0], "body": row[1], "created_at": row[2], "run_id": row[3],
              "authority": "REFERENCE_ONLY", "attribution": "LOCAL_INPUT_NOT_AUTHENTICATED",
              "body_sha256": hashlib.sha256(row[1].encode()).hexdigest(),
              "format": "cleanroom.owner-note.v1"} for row in reversed(rows)]
    return {"rows": notes, "total": total, "offset": offset, "limit": limit, "query": query}


def memo_rows(root, room=None, *, limit=200, offset=0, query=""):
    return memo_page(root, room, limit=limit, offset=offset, query=query)["rows"]


def memo_index(root, room, *, query=""):
    """Search the complete room without loading every memo into the UI."""
    from .cleanroom_owner import normal
    terms = normal(query).split()
    with connection() as store:
        if store is None or not store.execute("SELECT 1 FROM sqlite_master WHERE name='cr_memo'").fetchone():
            return []
        store.create_function("owner_matches", 1, lambda body: int(all(term in normal(body) for term in terms)))
        rows = store.execute("SELECT id,created_at FROM cr_memo WHERE root=? AND room=? AND owner_matches(body)",
                             (root_key(root), room)).fetchall()
    return [{"id": row[0], "created_at": row[1]} for row in rows]


def memos_by_id(root, room, identities):
    if not identities:
        return []
    if len(identities) > 200:
        raise LedgerError("ARGUMENTS")
    with connection() as store:
        if store is None:
            return []
        rows = store.execute("SELECT id,body,created_at,run_id FROM cr_memo WHERE root=? AND room=? AND id IN ("
                             + ",".join("?" for _ in identities) + ")", [root_key(root), room, *identities]).fetchall()
    return [dict(zip(("id", "body", "created_at", "run_id"), row)) for row in rows]


def preferences(root):
    with db() as store:
        row = store.execute("SELECT document FROM cr_preference WHERE root=?", (root_key(root),)).fetchone()
    return {**deepcopy(DEFAULT_PREFERENCES), **(json.loads(row[0]) if row else {})}


def set_preferences(root, **changes):
    if not set(changes) <= set(DEFAULT_PREFERENCES):
        raise LedgerError("ARGUMENTS")
    with db() as store:
        key = root_key(root)
        row = store.execute("SELECT document FROM cr_preference WHERE root=?", (key,)).fetchone()
        value = {**deepcopy(DEFAULT_PREFERENCES), **(json.loads(row[0]) if row else {}), **changes}
        if type(value["auto_compact"]) is not bool:
            raise LedgerError("ARGUMENTS")
        window = value["context_window"]
        if window is not None and (type(window) is not int or not 4096 <= window <= 2000000):
            raise LedgerError("ARGUMENTS")
        if not 0.25 <= value["compact_threshold"] <= 0.9 or type(value["model_windows"]) is not dict:
            raise LedgerError("ARGUMENTS")
        store.execute("INSERT OR REPLACE INTO cr_preference VALUES(?,?)", (key, canonical(value)))
    return value


def grant(root, scope):
    if scope not in ("workspace", "permanent"):
        raise LedgerError("ARGUMENTS")
    identity, key = uuid.uuid4().hex, root_key(root) if scope == "workspace" else "*"
    with db() as store:
        store.execute("INSERT INTO cr_grant VALUES(?,?,?,?,?,0)", (identity, key, scope, "candidate_edit", now()))
    return identity


def edit_grant(root):
    with db() as store:
        row = store.execute("SELECT id,scope FROM cr_grant WHERE kind='candidate_edit' AND revoked=0 AND root IN (?, '*') "
                            "ORDER BY CASE scope WHEN 'workspace' THEN 0 ELSE 1 END, created_at DESC LIMIT 1",
                            (root_key(root),)).fetchone()
    return {"id": row[0], "scope": row[1]} if row else None


def revoke(root, *, permanent=False):
    with db() as store:
        store.execute("UPDATE cr_grant SET revoked=1 WHERE root=? AND kind='candidate_edit'",
                      ("*" if permanent else root_key(root),))


def save_summary(root, agent, document):
    value = deepcopy(document)
    value["id"], value["created_at"] = uuid.uuid4().hex, now()
    with db() as store:
        for row in value.get("coverage", []):
            store.execute("INSERT OR REPLACE INTO cr_summary_source VALUES(?,?,?,?,?,?)",
                          (root_key(root), agent, row["source_ref"], row["event_hash"], row["run_id"], value["id"]))
        store.execute("INSERT INTO cr_summary VALUES(?,?,?,?,?)",
                      (value["id"], root_key(root), agent, canonical(value), value["created_at"]))
    return value


def summary(root, agent):
    with db() as store:
        row = store.execute("SELECT document FROM cr_summary WHERE root=? AND agent=? ORDER BY created_at DESC LIMIT 1",
                            (root_key(root), agent)).fetchone()
    return json.loads(row[0]) if row else None

def covered_sources(root, agent, refs):
    result = {}
    refs = list(dict.fromkeys(refs))
    with connection() as store:
        if store is None or not store.execute("SELECT 1 FROM sqlite_master WHERE name='cr_summary_source'").fetchone():
            return result
        for index in range(0, len(refs), 200):
            part = refs[index:index + 200]
            rows = store.execute("SELECT source_ref,event_hash FROM cr_summary_source WHERE root=? AND agent=? AND source_ref IN ("
                                 + ",".join("?" for _ in part) + ")", (root_key(root), agent, *part))
            result.update((row[0], row[1]) for row in rows)
    return result


def legacy_imported(root):
    with connection() as store:
        if store is None or not store.execute("SELECT 1 FROM sqlite_master WHERE name='cr_legacy_import'").fetchone():
            return False
        return bool(store.execute("SELECT 1 FROM cr_legacy_import WHERE root=?", (root_key(root),)).fetchone())
