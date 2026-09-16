"""In-progress, source-linked insights and optional AI remaining-time ranges.

This is a private presentation index, never a permission or mastery authority.
Original work events remain in the project event store.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import re
import time
import uuid

from jsonschema import Draft202012Validator

from . import session_store, personal_profile
from .domain.codec import canonical, digest
from .errors import LedgerError

CONTRACT = """Report work_pulse in each work turn when an estimate is possible.
It estimates REMAINING implementation and testing minutes, separately, as ranges.
Use null when there is insufficient information. State the stage, basis and unknowns.
It is not a promise, measured progress, evidence of testing, or a reason to stop work.
Update it after real progress, failures or interruptions. Interruption timings supplied
by the host are observed waiting time; do not silently reuse an old estimate.
Leave useful source-linked learning_notes during work, not only at the end. Respect
the shared person's pace. No homework, inferred mastery, or hidden reasoning."""

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS cr_insight (seq INTEGER PRIMARY KEY AUTOINCREMENT, root TEXT NOT NULL, room TEXT NOT NULL, run_id TEXT NOT NULL, source_ref TEXT NOT NULL, event_hash TEXT NOT NULL, ordinal INTEGER NOT NULL, document TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(root,source_ref,ordinal))",
    "CREATE INDEX IF NOT EXISTS cr_insight_room ON cr_insight(root,room,seq DESC)",
    "CREATE INDEX IF NOT EXISTS cr_insight_run ON cr_insight(root,run_id,seq DESC)",
    "CREATE TABLE IF NOT EXISTS cr_work_pulse (root TEXT NOT NULL, run_id TEXT NOT NULL, source_ref TEXT NOT NULL, document TEXT NOT NULL, estimated_at REAL NOT NULL, PRIMARY KEY(root,run_id))",
    "CREATE TABLE IF NOT EXISTS cr_insight_question (id TEXT PRIMARY KEY, root TEXT NOT NULL, run_id TEXT NOT NULL, note_seq INTEGER NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL, started REAL NOT NULL, finished REAL NOT NULL, duration REAL NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS cr_question_run ON cr_insight_question(root,run_id,started)",
    "CREATE INDEX IF NOT EXISTS cr_exposure_day ON exposures(day,channel)",
    "CREATE INDEX IF NOT EXISTS cr_exposure_work ON exposures(work_key,channel)",
)


def output_schema():
    from .agent_schema import obj, array
    span = obj({"minimum": {"type": "number", "minimum": 0, "maximum": 10080},
                "maximum": {"type": "number", "minimum": 0, "maximum": 10080}})
    return {"anyOf": [{"type": "null"}, obj({
        "implementation_minutes": deepcopy(span), "testing_minutes": deepcopy(span),
        "stage": {"type": "string", "maxLength": 160},
        "basis": {"type": "string", "maxLength": 1200},
        "unknowns": array({"type": "string", "maxLength": 500}, 8),
    })]}


def initialize(store):
    for sql in SCHEMA:
        store.execute(sql)


def _read(root, sql, values=(), many=False):
    with personal_profile.connection() as store:
        if store is None or not store.execute("SELECT 1 FROM sqlite_master WHERE name='cr_insight'").fetchone():
            return [] if many else None
        rows = store.execute(sql, (session_store.root_key(root), *values))
        return rows.fetchall() if many else rows.fetchone()


def _decode(row):
    return {"id": "L-" + str(row[0]).zfill(6), "number": row[0], "run_id": row[1],
            "note": json.loads(row[2]), "source_ref": row[3], "created_at": row[4]}


def capture(root, configuration, state):
    """Idempotently index the just-recorded turn; never fail the work plane."""
    try:
        events = state.get("work_trace_events", [])
        if not events or events[-1]["type"] != "WorkTurnRecorded":
            return
        from .agent_schema import trace_from_events
        from .learning_capture import notes_from_event
        event = trace_from_events(events[-1:])["events"][0]
        refs = {item["project_id"] + ":" + item["event_id"] for item in events}
        notes, _ = notes_from_event(event, refs)
        proposal = event["payload"]["proposal"]
        pulse = proposal.get("work_pulse")
        valid = pulse is not None and Draft202012Validator(output_schema()).is_valid(pulse)
        if valid:
            valid = all(math.isfinite(part[k]) for part in (pulse["implementation_minutes"], pulse["testing_minutes"])
                        for k in ("minimum", "maximum"))
            valid = valid and all(pulse[k]["minimum"] <= pulse[k]["maximum"]
                                  for k in ("implementation_minutes", "testing_minutes"))
        with session_store.db() as store:
            initialize(store)
            key, _, current_room = session_store._initial(store, root)
            bound = store.execute("SELECT room FROM cr_run WHERE root=? AND run_id=?", (key, state["run_id"])).fetchone()
            room = bound[0] if bound else current_room
            for index, note in enumerate(notes):
                store.execute("INSERT OR IGNORE INTO cr_insight(root,room,run_id,source_ref,event_hash,ordinal,document,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (key, room, state["run_id"], event["source_ref"], event["event_hash"], index,
                     canonical({**note, "work_key": configuration["project"]["id"] + "/" + state["run_id"],
                                "source_event_hash": event["event_hash"]}), event["recorded_at"]))
            # Missing/invalid fresh estimates become unavailable, not stale certainty.
            document = {"proposal": pulse if valid else None, "model": event["payload"]["model"],
                        "reason": "" if valid else "NOT_ESTIMATED",
                        "authority": "AI_ESTIMATE_NOT_PROMISE", "source_ref": event["source_ref"]}
            stamp = datetime.fromisoformat(event["recorded_at"].replace("Z", "+00:00")).timestamp()
            store.execute("INSERT OR REPLACE INTO cr_work_pulse VALUES(?,?,?,?,?)",
                          (key, state["run_id"], event["source_ref"], canonical(document), stamp))
    except Exception:
        # Notes remain in the exact WorkTurnRecorded event and can be indexed later.
        return


def notes(root, room, limit=20, offset=0, run_id=None):
    limit, offset = max(1, min(int(limit), 100)), max(0, int(offset))
    clause, args = ("run_id=?", (run_id,)) if run_id else ("room=?", (room,))
    rows = _read(root, "SELECT seq,run_id,document,source_ref,created_at FROM cr_insight WHERE root=? AND "
                 + clause + " ORDER BY seq DESC LIMIT ? OFFSET ?", (*args, limit, offset), True)
    return [_decode(row) for row in rows]


def resolve(root, identity):
    match = re.fullmatch(r"L-([0-9]{1,12})", identity.strip(), re.IGNORECASE)
    if not match:
        return None
    row = _read(root, "SELECT seq,run_id,document,source_ref,created_at FROM cr_insight WHERE root=? AND seq=?",
                (int(match.group(1)),))
    return _decode(row) if row else None


def parse_reference(text):
    """A registered host ID, not a semantic classifier of natural-language work."""
    match = re.fullmatch(r"(L-[0-9]{1,12})(?:\s+([\s\S]{1,4000}))?", text.strip(), re.IGNORECASE)
    return (match.group(1).upper(), (match.group(2) or "").strip()) if match else None


def reserve(root, item):
    pref = personal_profile.preferences()
    if (not pref["enabled"] or pref["mode"] == "on_demand" or pref["timing"] != "at_breaks"):
        return False
    work_key = item["note"].get("work_key", session_store.root_key(root) + "/" + item["run_id"])
    # Use the same exposure pool as end-of-work lessons: no second notification budget.
    identity = "live:" + item["id"]
    token = digest({"lesson": identity, "work": work_key, "channel": "learning"})
    with session_store.db() as store:
        if store.execute("SELECT 1 FROM exposures WHERE id=?", (token,)).fetchone():
            return False
        total = store.execute("SELECT COUNT(*) FROM exposures WHERE day=? AND channel='learning'",
                             (personal_profile.day(),)).fetchone()[0]
        current = store.execute("SELECT COUNT(*) FROM exposures WHERE work_key=? AND channel='learning'",
                               (work_key,)).fetchone()[0]
        if total >= pref["daily_limit"] or current >= min(2, pref["per_work"]):
            return False
        store.execute("INSERT INTO exposures VALUES(?,?,?,?,?)",
                      (token, personal_profile.day(), work_key, identity, "learning"))
        personal_profile._touch(store)
    return True


def pulse(root, run_id):
    row = _read(root, "SELECT document,estimated_at FROM cr_work_pulse WHERE root=? AND run_id=?", (run_id,))
    if not row:
        return {"available": False}
    value, stamp = json.loads(row[0]), row[1]
    if value["proposal"] is None:
        return {"available": False, **value}
    interruptions = _read(root, "SELECT started,finished,duration,status FROM cr_insight_question WHERE root=? AND run_id=? AND started>=?",
                          (run_id, stamp), True)
    now = time.time()
    extra = sum(item[2] if item[3] != "RUNNING" else max(0, now - item[0]) for item in interruptions)
    elapsed = max(0, now - stamp - extra)
    proposal = value["proposal"]
    minimum = sum(proposal[k]["minimum"] for k in ("implementation_minutes", "testing_minutes")) * 60
    maximum = sum(proposal[k]["maximum"] for k in ("implementation_minutes", "testing_minutes")) * 60
    return {**value, "available": True, "estimated_at": stamp,
            "remaining_min": max(0, math.ceil((minimum - elapsed) / 60)),
            "remaining_max": max(0, math.ceil((maximum - elapsed) / 60)),
            "overdue": elapsed > maximum, "interruption_seconds": round(extra, 1),
            "needs_update": bool(interruptions),
            "question_running": any(item[3] == "RUNNING" for item in interruptions)}


def interrupt_context(root, run_id):
    rows = _read(root, "SELECT duration,status FROM cr_insight_question WHERE root=? AND run_id=? ORDER BY started DESC LIMIT 32",
                 (run_id,), True)
    return {"answered_or_attempted_questions": len(rows),
            "observed_seconds": round(sum(row[0] for row in rows), 1),
            "instruction": "Re-estimate remaining work after these measured interruptions. They are not new implementation instructions."}


def answer(root, configuration, *, identity, question="", run_id=None, key=None, adapter=None, timeout=None):
    """One read-only answer, separate from WorkResult; never execute a proposed tool."""
    from .agent_models import selected_work, invoke
    from .agent_schema import WORK_REQUEST, schema
    note = resolve(root, identity)
    if note is None:
        raise LedgerError("ARGUMENTS", {"reason": "UNKNOWN_LEARNING_REFERENCE"})
    key = key or uuid.uuid4().hex
    active_run = run_id or note["run_id"]
    started = time.time()
    with session_store.db() as store:
        initialize(store)
        prior = store.execute("SELECT question,status,answer,model,reason FROM cr_insight_question WHERE id=?", (key,)).fetchone()
        if prior:
            if prior[0] != question:
                raise LedgerError("IDEMPOTENCY_CONFLICT")
            return {"id": key, "learning_id": note["id"], "question": question, "status": prior[1],
                    "answer": prior[2], "model": json.loads(prior[3]), "reason": prior[4]}
        store.execute("INSERT INTO cr_insight_question VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (key, session_store.root_key(root), active_run, note["number"], question, "", "{}",
                       "RUNNING", started, 0, 0, "", session_store.now()))
    monotonic = time.monotonic()
    result = {"id": key, "learning_id": note["id"], "question": question, "status": "FAILED", "answer": "", "model": {}}
    from .personal_growth import context as personal_context
    try:
        # The original public explanation is retained in full. Private memos are not included.
        request = {"format": WORK_REQUEST, "generation_id": "insight-" + key,
                   "request": question or "Explain this recorded insight in small, optional steps in the response language.",
                   "response_locale": configuration["ui"]["locale"], "selected_insight": note,
                   "tool_capabilities": {}, "capture_learning": False, "personal_context": personal_context(),
                   "learning_sources": [], "approved_files": [],
                   "output_contract": (
                       "This is a side question about the quoted selected_insight, not a new implementation task. "
                       "Explain its concrete context, prerequisites, tradeoffs and a small optional next step. "
                       "Use its full explanation and source links. Distinguish plans from completed checks. "
                       "Do not infer ability, mastery, permission or new work. No tools or hidden reasoning. "
                       "Return COMPLETE, a useful answer, empty tool_requests, owner_question and learning_notes. "
                       "If details are absent, say so without inventing them. The main implementation resumes unchanged.")}
        request["output_schema"] = schema(request)
        from .session_context import input_budget
        if len(canonical(request).encode()) > input_budget(root, configuration):
            raise LedgerError("WORK_CONTEXT_LIMIT", {"reason": "INSIGHT_TOO_LARGE_FOR_MODEL"})
        call = invoke(root, adapter or selected_work(root, configuration), request, key="insight-" + key, timeout=timeout)
        document = call["document"]
        if document["status"] != "COMPLETE" or document["tool_requests"]:
            raise LedgerError("BRIDGE_PROTOCOL", {"reason": "INSIGHT_READ_ONLY"})
        result.update(status="ANSWERED", answer=document["answer"], model=call["model"],
                      request_sha256=digest(request), reason="")
    except Exception as error:
        result["reason"] = getattr(error, "code", type(error).__name__)
    result["elapsed_seconds"] = max(0, time.monotonic() - monotonic)
    with session_store.db() as store:
        store.execute("UPDATE cr_insight_question SET answer=?,model=?,status=?,finished=?,duration=?,reason=? WHERE id=?",
                      (result["answer"], canonical({"identity": result["model"], "request_sha256": result.get("request_sha256"),
                                  "insight_source_ref": note["source_ref"], "authority": "AI_EXPLANATION_NOT_MASTERY"}),
                       result["status"], time.time(),
                       result["elapsed_seconds"], result.get("reason", ""), key))
    return result


def service(root, configuration, state, inbox, *, adapter=None, timeout=None):
    if inbox is None:
        return
    while (row := inbox.next_question()) is not None:
        try:
            result = answer(root, configuration, identity=row["learning_id"], question=row["question"],
                            run_id=state["run_id"], key=row["id"], adapter=adapter, timeout=timeout)
        except Exception as error:
            result = {**row, "status": "FAILED", "answer": "", "reason": getattr(error, "code", type(error).__name__)}
        inbox.question_answered(result)

def question_history(root, run_ids, limit=80):
    if not run_ids:
        return []
    chosen = list(run_ids)[-80:]
    rows = _read(root, "SELECT id,note_seq,question,answer,status,reason,created_at,model FROM cr_insight_question WHERE root=? AND run_id IN ("
                 + ",".join("?" for _ in chosen) + ") ORDER BY started DESC LIMIT ?",
                 (*chosen, min(80, max(1, limit))), True)
    return [{"id": row[0], "learning_id": "L-" + str(row[1]).zfill(6), "question": row[2],
             "answer": row[3], "status": row[4], "reason": row[5], "created_at": row[6],
             "model": json.loads(row[7])} for row in reversed(rows)]
