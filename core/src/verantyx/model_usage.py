"""Provider-reported counters only; never prompt bodies, credentials or estimates."""
from datetime import datetime, timezone
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys

from .domain.codec import digest
from .errors import LedgerError
from .native_session import STATE_ENV, private_directory

FIELDS = ("input_tokens", "uncached_input_tokens", "cached_input_tokens", "cache_write_input_tokens",
          "output_tokens", "reasoning_output_tokens")


def normalize(provider, result):
    usage = result.get("usage") or {}
    if not isinstance(usage, dict):
        return {}
    tokens = {}
    def put(key, value):
        if type(value) is int and 0 <= value <= 2**40:
            tokens[key] = value
    if provider == "ollama":
        put("input_tokens", result.get("prompt_eval_count"))
        put("output_tokens", result.get("eval_count"))
        return tokens
    if provider in ("anthropic", "claude_code"):
        put("uncached_input_tokens", usage.get("input_tokens"))
        put("cached_input_tokens", usage.get("cache_read_input_tokens"))
        put("cache_write_input_tokens", usage.get("cache_creation_input_tokens"))
        if all(key in tokens for key in ("uncached_input_tokens", "cached_input_tokens", "cache_write_input_tokens")):
            tokens["input_tokens"] = sum(tokens.values())
    else:
        put("input_tokens", usage.get("input_tokens", usage.get("prompt_tokens")))
        detail = usage.get("input_tokens_details", usage.get("prompt_tokens_details")) or {}
        detail = detail if isinstance(detail, dict) else {}
        put("cached_input_tokens", usage.get("cached_input_tokens", detail.get("cached_tokens")))
        output_detail = usage.get("output_tokens_details", usage.get("completion_tokens_details")) or {}
        output_detail = output_detail if isinstance(output_detail, dict) else {}
        put("reasoning_output_tokens", usage.get("reasoning_output_tokens", output_detail.get("reasoning_tokens")))
    put("output_tokens", usage.get("output_tokens", usage.get("completion_tokens")))
    return tokens


def publish(config, request, result=None, *, tokens=None, source="provider", observer=None):
    tokens = normalize(config["provider"], result or {}) if tokens is None else tokens
    tokens = {key: value for key, value in tokens.items()
              if key in FIELDS and type(value) is int and 0 <= value <= 2**40}
    event = {"kind": "usage", "tokens": tokens, "source": source}
    directory = os.environ.get(STATE_ENV)
    if directory:
        try:
            root = private_directory(Path(directory))
            path = root / "usage.sqlite3"
            if path.is_symlink() or (path.exists() and path.stat().st_nlink != 1):
                raise OSError("Unsafe usage path")
            fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            with closing(sqlite3.connect(path, timeout=2)) as db, db:
                db.execute("CREATE TABLE IF NOT EXISTS usage (observed_at TEXT, provider TEXT, model TEXT, purpose TEXT, request_hash TEXT, source TEXT, tokens TEXT)")
                db.execute("INSERT INTO usage VALUES (?,?,?,?,?,?,?)", (
                    datetime.now(timezone.utc).isoformat(), config["provider"], config["model"],
                    request.get("format", "unknown"), digest(request), source, json.dumps(tokens)))
        except (OSError, sqlite3.Error, ValueError, LedgerError):
            # A telemetry failure must never repeat a billed request.
            event["recording_failed"] = True
    if observer:
        observer(event)
    else:
        from .model_observation import emit
        emit(sys.stderr, event)
    return event


def summary(root):
    base = Path(root).resolve() / ".verantyx" / "model-adapters"
    totals, purposes, calls, missing, reused = {}, {}, 0, 0, 0
    measured_input = measured_cached = measured_calls = 0
    for path in sorted(base.glob("**/.transport/usage.sqlite3")):
        if any(p.is_symlink() for p in (path, *path.parents)):
            continue
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
            for purpose, source, raw in db.execute("SELECT purpose, source, tokens FROM usage"):
                if source == "local_cache":
                    reused += 1
                    continue
                calls += 1
                purposes[purpose] = purposes.get(purpose, 0) + 1
                tokens = json.loads(raw)
                missing += not bool(tokens)
                for key, count in tokens.items():
                    totals[key] = totals.get(key, 0) + count
                if "input_tokens" in tokens and "cached_input_tokens" in tokens:
                    measured_calls += 1
                    measured_input += tokens["input_tokens"]
                    measured_cached += tokens["cached_input_tokens"]
    return {"ok": True, "calls": calls, "local_reuses": reused, "calls_without_usage": missing,
            "tokens": totals, "calls_by_purpose": purposes, "cache_measured_calls": measured_calls,
            "cached_input_ratio": measured_cached / measured_input if measured_input else None,
            "scope": "Reported usage since transport optimization; excludes older Codex budget records."}
