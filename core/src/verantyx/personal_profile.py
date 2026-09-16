"""Private, cross-project owner experience. No inferred ability or execution rights."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3
import stat
import sys
import uuid

from .domain.codec import digest
from .errors import LedgerError

FORMAT = "verantyx.personal-notebook.v1"
SESSION_ID = uuid.uuid4().hex
KINDS = ("experience", "understanding", "confidence", "support", "goal", "delegation", "memo")
DEFAULTS = {
    "onboarded": False, "enabled": False, "share_with_ai": False,
    "mode": "on_demand", "weight": "brief", "timing": "after_work",
    "daily_limit": 1, "per_work": 1, "stack_questions": True,
}
ENUMS = {"mode": ("on_demand", "light", "guided"), "weight": ("brief", "snippet", "practice"),
         "timing": ("after_work", "at_breaks", "on_demand")}
RECORD_KINDS = {"statement", "proposal", "stack", "journal", "report", "lesson", "note", "preference",
                "skill_asset", "skill_progress", "learning_trace", "learning_guide", "integration"}
CHOICES = {"NEXT_TIME", "REFERENCE", "DELEGATE", "DISMISS", "REOPEN",
           "SELF_REPORTED_UNDERSTOOD", "SELF_REPORTED_APPLIED", "SELF_REPORTED_TRANSFERRED"}


def require(condition, reason):
    if not condition:
        raise LedgerError("ARGUMENTS", {"reason": reason})


def now():
    return datetime.now(timezone.utc).isoformat()


def day():
    return datetime.now().astimezone().date().isoformat()


def home():
    explicit = os.environ.get("VERANTYX_PERSONAL_HOME")
    if explicit:
        value = Path(explicit).expanduser()
        require(value.is_absolute(), "PERSONAL_HOME_ABSOLUTE")
    elif sys.platform == "darwin":
        value = Path.home() / "Library/Application Support/Verantyx/Personal"
    else:
        value = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "verantyx/personal"
    require(value.is_absolute(), "PERSONAL_HOME_ABSOLUTE")
    return value


def settings_valid(changes):
    require(type(changes) is dict and set(changes) <= set(DEFAULTS), "PERSONAL_SETTINGS_FIELDS")
    for key, value in changes.items():
        if key in ENUMS:
            require(type(value) is str and value in ENUMS[key], "PERSONAL_SETTINGS_VALUE")
        elif key in ("daily_limit", "per_work"):
            require(type(value) is int and 0 <= value <= (12 if key == "daily_limit" else 3),
                    "PERSONAL_SETTINGS_LIMIT")
        else:
            require(type(value) is bool, "PERSONAL_SETTINGS_BOOLEAN")
    return deepcopy(changes)


def _safe_home(create=False):
    path = home()
    for part in [*reversed(path.parents), path]:
        require(not part.is_symlink(), "PERSONAL_HOME_SYMLINK")
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    return path


@contextmanager
def connection(write=False):
    directory = _safe_home(write)
    path = directory / "profile.sqlite3"
    if not path.exists() and not write:
        yield None
        return
    require(not path.is_symlink(), "PERSONAL_STORE_SYMLINK")
    if write and not path.exists():
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "PERSONAL_STORE_FILE")
    db = sqlite3.connect(path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                         uri=True, timeout=5, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        if write:
            os.chmod(path, 0o600)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA secure_delete=ON")
            db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT NOT NULL, "
                       "work_key TEXT NOT NULL, document TEXT NOT NULL, updated TEXT NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS records_kind ON records(kind, updated)")
            db.execute("CREATE INDEX IF NOT EXISTS records_work ON records(work_key)")
            db.execute("CREATE TABLE IF NOT EXISTS history (seq INTEGER PRIMARY KEY AUTOINCREMENT, "
                       "record_id TEXT NOT NULL, document TEXT NOT NULL, changed TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS exposures (id TEXT PRIMARY KEY, day TEXT NOT NULL, "
                       "work_key TEXT NOT NULL, record_id TEXT NOT NULL, channel TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, intent TEXT NOT NULL, "
                       "status TEXT NOT NULL, result TEXT)")
            db.execute("BEGIN IMMEDIATE")
        yield db
        if write:
            db.execute("COMMIT")
    except BaseException:
        if write and db.in_transaction:
            db.execute("ROLLBACK")
        raise
    finally:
        db.close()


def _meta(db, name, fallback):
    row = db.execute("SELECT value FROM meta WHERE key=?", (name,)).fetchone() if db else None
    return json.loads(row[0]) if row else deepcopy(fallback)


def _touch(db):
    value = _meta(db, "revision", 0) + 1
    db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", ("revision", json.dumps(value)))
    return value


def _get(db, identity):
    row = db.execute("SELECT document FROM records WHERE id=?", (identity,)).fetchone() if db else None
    return json.loads(row[0]) if row else None


def _rows(db, kind=None, limit=300):
    if db is None:
        return []
    if kind:
        values = db.execute("SELECT document FROM records WHERE kind=? ORDER BY updated DESC, id LIMIT ?",
                            (kind, limit)).fetchall()
    else:
        values = db.execute("SELECT document FROM records ORDER BY updated DESC, id LIMIT ?", (limit,)).fetchall()
    return [json.loads(row[0]) for row in values]


def _put(db, record, history=False):
    require(record.get("kind") in RECORD_KINDS, "PERSONAL_RECORD_KIND")
    value = deepcopy(record)
    value["updated_at"] = now()
    old = _get(db, value["id"])
    if history and old:
        db.execute("INSERT INTO history(record_id,document,changed) VALUES(?,?,?)",
                   (value["id"], json.dumps(old, ensure_ascii=False), now()))
    db.execute("INSERT OR REPLACE INTO records VALUES (?,?,?,?,?)",
               (value["id"], value["kind"], value.get("work_key", ""),
                json.dumps(value, ensure_ascii=False), value["updated_at"]))
    _touch(db)
    return value


def active(record):
    scope = record.get("scope", "GLOBAL")
    return (scope == "GLOBAL" or scope == "SESSION" and record.get("session_id") == SESSION_ID
            or scope == "TODAY" and record.get("day") == day())


def _settings(db):
    result = {**DEFAULTS, **_meta(db, "settings", {})}
    for row in reversed(_rows(db, "preference", 100)):
        if active(row):
            result.update(row.get("changes", {}))
    return result


def preferences():
    with connection() as db:
        return _settings(db)


def configure(changes, *, scope="GLOBAL"):
    changes = settings_valid(changes)
    require(scope in ("GLOBAL", "SESSION", "TODAY"), "PERSONAL_SCOPE")
    with connection(True) as db:
        if scope == "GLOBAL":
            value = {**DEFAULTS, **_meta(db, "settings", {}), **changes}
            db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
                       ("settings", json.dumps(value, ensure_ascii=False)))
            _touch(db)
        else:
            _put(db, {"id": uuid.uuid4().hex, "kind": "preference", "changes": changes,
                      "scope": scope, "session_id": SESSION_ID, "day": day(),
                      "authority": "OWNER_SELECTED"})
        return _settings(db)


def put_record(record):
    with connection(True) as db:
        return _put(db, record)


def get_record(identity):
    with connection() as db:
        return _get(db, identity)


def records(kind=None, limit=300):
    require(kind is None or kind in RECORD_KINDS, "PERSONAL_RECORD_KIND")
    require(type(limit) is int and 1 <= limit <= 5000, "PERSONAL_RECORD_LIMIT")
    with connection() as db:
        return _rows(db, kind, limit)


def statement(text, *, technology="", kind="experience", share=False, scope="GLOBAL",
              record_id=None, source=None):
    require(type(text) is str and 0 < len(text.strip()) <= 8000, "PERSONAL_STATEMENT")
    require(type(technology) is str and len(technology) <= 160, "PERSONAL_TECHNOLOGY")
    require(kind in KINDS and scope in ("GLOBAL", "SESSION", "TODAY") and type(share) is bool,
            "PERSONAL_STATEMENT_KIND")
    with connection(True) as db:
        old = _get(db, record_id) if record_id else None
        require(not record_id or old is not None and old["kind"] == "statement", "PERSONAL_RECORD_REQUIRED")
        row = {"id": record_id or uuid.uuid4().hex, "kind": "statement", "category": kind,
               "text": text.strip(), "technology": technology.strip(), "share_with_ai": share,
               "scope": scope, "session_id": SESSION_ID, "day": day(),
               "authority": "OWNER_SELF_REPORT", "source": source or {"kind": "DIRECT_OWNER_ENTRY"},
               "created_at": old.get("created_at", now()) if old else now()}
        return _put(db, row, history=bool(old))


def snapshot():
    with connection() as db:
        kinds = {kind: _rows(db, kind, 120 if kind in ("lesson", "statement", "skill_progress") else 40)
                 for kind in ("statement", "proposal", "stack", "journal", "report", "lesson", "note", "skill_progress")}
        counts = dict(db.execute("SELECT kind,COUNT(*) FROM records GROUP BY kind").fetchall()) if db else {}
        return {"format": FORMAT, "revision": _meta(db, "revision", 0), "home": str(home()),
                "settings": _settings(db), "records": kinds, "counts": counts,
                "omitted": {key: max(0, counts.get(key, 0) - len(rows)) for key, rows in kinds.items()},
                "ability_inference": False, "mastery_assessed": False}


def shared_context():
    with connection() as db:
        pref = _settings(db)
        result = {"settings": pref, "records": [], "learning": [], "notes": [], "omitted": 0,
                  "authority": "SELF_REPORTS_AND_AI_PROPOSALS_NOT_ABILITY_SCORES",
                  "skills": {"items": [], "omitted": 0}}
        if not pref["enabled"] or not pref["share_with_ai"]:
            result["sharing"] = "PRIVATE"
            return result
        result["sharing"] = "OWNER_OPTED_IN"
        used = 0
        for row in _rows(db, "statement", 200):
            if not row.get("share_with_ai") or not active(row):
                continue
            entry = {key: row[key] for key in ("id", "category", "technology", "text", "scope", "authority")}
            size = len(json.dumps(entry, ensure_ascii=False).encode())
            if len(result["records"]) >= 32 or used + size > 16000:
                result["omitted"] += 1
                continue
            result["records"].append(entry)
            used += size
        for row in _rows(db, "lesson", 120):
            if not row.get("share_with_ai") or row.get("choice") == "DISMISS":
                continue
            entry = {key: row.get(key) for key in
                     ("id", "topic", "title", "minimum_step", "choice", "feedback", "authority")}
            size = len(json.dumps(entry, ensure_ascii=False).encode())
            if len(result["learning"]) >= 20 or used + size > 24000:
                result["omitted"] += 1
                continue
            result["learning"].append(entry)
            used += size
        for row in _rows(db, "note", 100):
            if not row.get("share_with_ai"):
                continue
            entry = {key: row.get(key) for key in ("id", "text", "journal_id", "authority")}
            size = len(json.dumps(entry, ensure_ascii=False).encode())
            if len(result["notes"]) >= 10 or used + size > 28000:
                result["omitted"] += 1
                continue
            result["notes"].append(entry)
            used += size
        from .skill_assets import shared_records
        result["skills"] = shared_records(db)
        return result


def claim_prompt(technology, work_key, *, can_ask=True):
    """A once-only invitation, never a skill test or an ability observation."""
    identity = "stack-" + digest(technology.strip().casefold())[:24]
    with connection(True) as db:
        pref = _settings(db)
        if not pref["enabled"] or not pref["stack_questions"]:
            return False
        previous = _get(db, identity)
        if previous and previous.get("status") == "INVITED":
            return False
        for row in _rows(db, "statement", 1000):
            if row.get("technology", "").strip().casefold() == technology.strip().casefold():
                return False
        already = db.execute("SELECT COUNT(*) FROM exposures WHERE day=? AND channel='stack'",
                             (day(),)).fetchone()[0]
        this_work = db.execute("SELECT COUNT(*) FROM exposures WHERE work_key=? AND channel='stack'",
                               (work_key,)).fetchone()[0]
        invited = (can_ask and pref["mode"] != "on_demand" and pref["timing"] != "on_demand"
                   and already < pref["daily_limit"] and not this_work)
        _put(db, {"id": identity, "kind": "stack", "technology": technology, "work_key": work_key,
                  "status": "INVITED" if invited else "NEXT_OPPORTUNITY",
                  "authority": "EXPERIENCE_NOT_RECORDED_NOT_INEXPERIENCE"})
        if invited:
            db.execute("INSERT OR IGNORE INTO exposures VALUES(?,?,?,?,?)",
                       (identity, day(), work_key, identity, "stack"))
        return invited


def reserve_lesson(identity, work_key, *, explicit=False):
    with connection(True) as db:
        row = _get(db, identity)
        if not row or row["kind"] != "lesson":
            return False
        if explicit:
            return True
        pref = _settings(db)
        if (not pref["enabled"] or pref["mode"] == "on_demand" or pref["timing"] == "on_demand"
                or row.get("choice") != "OPEN"):
            return False
        token = digest({"lesson": identity, "work": work_key, "channel": "learning"})
        if db.execute("SELECT 1 FROM exposures WHERE id=?", (token,)).fetchone():
            return False
        total = db.execute("SELECT COUNT(*) FROM exposures WHERE day=? AND channel='learning'",
                           (day(),)).fetchone()[0]
        current = db.execute("SELECT COUNT(*) FROM exposures WHERE work_key=? AND channel='learning'",
                             (work_key,)).fetchone()[0]
        if total >= pref["daily_limit"] or current >= pref["per_work"]:
            return False
        db.execute("INSERT INTO exposures VALUES (?,?,?,?,?)", (token, day(), work_key, identity, "learning"))
        _touch(db)
        return True


def choose_lesson(identity, choice, *, text="", share=None):
    require(choice in CHOICES and type(text) is str and len(text) <= 8000, "PERSONAL_LESSON_CHOICE")
    require(share is None or type(share) is bool, "PERSONAL_SHARING")
    with connection(True) as db:
        row = _get(db, identity)
        require(row and row["kind"] == "lesson", "PERSONAL_LESSON_REQUIRED")
        row["choice"] = "OPEN" if choice == "REOPEN" else choice
        row.setdefault("feedback", []).append({"choice": choice, "text": text, "recorded_at": now(),
                                              "authority": "OWNER_SELF_REPORT", "scope": "THIS_TOPIC_ONLY"})
        if share is not None:
            row["share_with_ai"] = share
        return _put(db, row, history=True)


def add_note(text, *, journal_id="", share=False):
    require(type(text) is str and 0 < len(text.strip()) <= 8000, "PERSONAL_NOTE")
    require(type(share) is bool, "PERSONAL_SHARING")
    with connection(True) as db:
        parent = _get(db, journal_id) if journal_id else None
        require(not journal_id or parent and parent["kind"] == "journal", "PERSONAL_JOURNAL_REQUIRED")
        return _put(db, {"id": uuid.uuid4().hex, "kind": "note", "text": text.strip(),
                         "journal_id": journal_id, "work_key": parent["work_key"] if parent else "",
                         "share_with_ai": share, "authority": "OWNER_SELF_REPORT", "created_at": now()})


def forget(identity):
    """Delete selected local data and dependent AI drafts, not provider/project logs."""
    with connection(True) as db:
        row = _get(db, identity)
        require(row is not None, "PERSONAL_RECORD_REQUIRED")
        remove = {identity}
        rows = [json.loads(item[0]) for item in db.execute("SELECT document FROM records")]
        changed = True
        while changed:
            changed = False
            for item in rows:
                dependencies = set(item.get("profile_refs", []))
                dependencies.update(item.get("source_record_ids", []))
                dependencies.update(item.get(key) for key in ("target_id", "journal_id", "previous_id", "report_id", "asset_id")
                                    if item.get(key))
                if item["id"] not in remove and dependencies & remove:
                    remove.add(item["id"])
                    changed = True
        for item in remove:
            db.execute("DELETE FROM records WHERE id=?", (item,))
            db.execute("DELETE FROM history WHERE record_id=?", (item,))
            db.execute("DELETE FROM exposures WHERE record_id=?", (item,))
        # Old model responses can quote the deleted profile. Keep outcome
        # tombstones so a replay cannot silently turn into another model call.
        db.execute("UPDATE calls SET result=NULL,status='FORGOTTEN' WHERE status='COMPLETE'")
        _touch(db)
        return {"deleted": sorted(remove), "scope": "LOCAL_PERSONAL_DATA_ONLY",
                "project_and_provider_history_erased": False}


def begin_call(identity, intent):
    with connection(True) as db:
        row = db.execute("SELECT * FROM calls WHERE id=?", (identity,)).fetchone()
        if row:
            require(row["intent"] == intent, "PERSONAL_CALL_CONFLICT")
            if row["status"] == "COMPLETE":
                return json.loads(row["result"])
            raise LedgerError("ARGUMENTS", {"reason": "PERSONAL_CALL_" + row["status"],
                                           "automatic_retry": False})
        db.execute("INSERT INTO calls VALUES (?,?,?,NULL)", (identity, intent, "OUTCOME_UNKNOWN"))
        return None


def complete_call(identity, result):
    with connection(True) as db:
        db.execute("UPDATE calls SET result=?,status='COMPLETE' WHERE id=?",
                   (json.dumps(result, ensure_ascii=False), identity))


def export_bundle():
    with connection() as db:
        total = db.execute("SELECT COUNT(*) FROM records").fetchone()[0] if db else 0
        require(total <= 5000, "PERSONAL_EXPORT_PARTITION_REQUIRED")
        return {"format": FORMAT, "exported_at": now(), "settings": _settings(db),
                "records": _rows(db, limit=5000), "contains_private_data": True,
                "boundary": "No credentials, execution permissions or mastery certification."}


def import_bundle(value):
    require(type(value) is dict and value.get("format") == FORMAT
            and type(value.get("records")) is list and len(value["records"]) <= 5000, "PERSONAL_IMPORT_FORMAT")
    require(len(json.dumps(value, ensure_ascii=False).encode()) <= 8 * 1024 * 1024, "PERSONAL_IMPORT_LIMIT")
    accepted = []
    # Imported data never enables sharing, grants rights or replaces local settings.
    for row in value["records"]:
        require(type(row) is dict and row.get("kind") in RECORD_KINDS, "PERSONAL_IMPORT_RECORD")
        require(type(row.get("id")) is str and 0 < len(row["id"]) <= 200, "PERSONAL_IMPORT_ID")
        if row["kind"] != "statement":
            continue
        require(row.get("category") in KINDS and type(row.get("text")) is str
                and 0 < len(row["text"]) <= 8000 and type(row.get("technology", "")) is str
                and len(row.get("technology", "")) <= 160, "PERSONAL_IMPORT_STATEMENT")
        accepted.append(row)
    with connection(True) as db:
        count = 0
        for row in accepted:
            identity = "import-" + digest({"id": row["id"], "text": row["text"], "category": row["category"]})[:32]
            if _get(db, identity):
                continue
            _put(db, {"id": identity, "kind": "statement", "category": row["category"],
                      "text": row["text"], "technology": row.get("technology", ""),
                      "scope": "GLOBAL", "share_with_ai": False, "authority": "IMPORTED_SELF_REPORT",
                      "source": {"kind": "EXPLICIT_IMPORT", "original_id": row["id"]}, "created_at": now()})
            count += 1
    return {"imported_statements": count, "other_records_not_imported": len(value["records"]) - len(accepted),
            "sharing_enabled": False}


def revision():
    with connection() as db:
        return _meta(db, "revision", 0)


def fail_call(identity, code):
    with connection(True) as db:
        db.execute("UPDATE calls SET status='FAILED',result=? WHERE id=? AND status='OUTCOME_UNKNOWN'",
                   (json.dumps({"code": code}), identity))
