"""Preserve public implementation explanations and receipts while work proceeds.

These are explanatory notes, not hidden model reasoning, mastery assessments,
or execution evidence. Original project events remain the authoritative source.
"""
from copy import deepcopy
import json

from jsonschema import Draft202012Validator

from . import personal_profile as profile
from .domain.codec import digest

CONTRACT = """While implementing, optionally leave learning_notes for useful skills and
technology choices at the moment the details are available. Do not wait for a final
summary. Preserve concrete prerequisites, omitted intermediate steps, alternatives,
failure conditions, and how to check the result. Write user-facing explanations of
observable decisions, NOT hidden chain-of-thought or private internal reasoning.
Use the shared personal_context only. Do not infer ability from delegation or silence.
Do not quote private profile details in project notes. profile_refs can identify
explicit shared statements; unknown experience is not inexperience.
Each note has title, target_kind (SKILL, TECHNOLOGY, BOTH), technology_tags,
explanation, prerequisites, expanded_steps, alternatives, pitfalls, verification,
next_small_step, source_event_ids and profile_refs. source_event_ids may use ONLY
learning_sources, never profile IDs. Put shared profile IDs in profile_refs instead.
Empty notes are valid; usually zero to two useful notes suffice, with at most four.
The host binds the note to this actual turn and separately records tool results.
A planned write/check is not a completed operation. These notes never block work,
ask extra homework, mark learning complete, or create new permissions."""
CAPTURE_TYPES = {"WorkSessionOpened", "WorkTurnRecorded", "WorkToolRecorded", "WorkResultRecorded", "WorkOwnerReplyRecorded"}


def note_schema():
    from .agent_schema import obj, array, SOURCE
    text = {"type": "string", "maxLength": 6000}
    entry = {"type": "string", "maxLength": 3000}
    return obj({
        "title": {"type": "string", "minLength": 1, "maxLength": 240},
        "target_kind": {"type": "string", "enum": ["SKILL", "TECHNOLOGY", "BOTH"]},
        "technology_tags": array({"type": "string", "minLength": 1, "maxLength": 160}, 8),
        "explanation": text, "prerequisites": array(entry, 10),
        "expanded_steps": array(entry, 16), "alternatives": array(entry, 8),
        "pitfalls": array(entry, 10), "verification": array(entry, 10),
        "next_small_step": entry,
        "source_event_ids": array(SOURCE, 16),
        "profile_refs": array(SOURCE, 16),
    })


def profile_refs(context):
    refs = []
    for name in ("records", "learning", "notes"):
        refs += [row["id"] for row in context.get(name, []) if row.get("id")]
    refs += [row["id"] for row in context.get("skills", {}).get("items", []) if row.get("id")]
    return sorted(set(refs))


def notes_from_event(event, known_refs):
    raw = event.get("payload", {}).get("proposal", {}).get("learning_notes", [])
    if type(raw) is not list:
        return [], [{"reason": "NOT_A_LIST", "source_ref": event["source_ref"]}]
    accepted, rejected = [], []
    validator = Draft202012Validator(note_schema())
    for index, value in enumerate(raw):
        if index >= 4 or not validator.is_valid(value):
            rejected.append({"reason": "NOTE_SCHEMA", "index": index, "source_ref": event["source_ref"]})
        elif not set(value["source_event_ids"]) <= known_refs:
            rejected.append({"reason": "UNKNOWN_SOURCE", "index": index, "source_ref": event["source_ref"]})
        else:
            accepted.append({**deepcopy(value), "recorded_in": event["source_ref"],
                             "authority": "AI_EXPLANATION_NOT_EXECUTION_OR_MASTERY"})
    return accepted, rejected


def pending_notes_from_event(event, known_refs):
    """Expose incomplete notes without treating their claims as cited evidence.

    The original event is unchanged. A pending ID uses the raw index, separate
    from the historical accepted-note indexes used by learning_moments.
    """
    _, errors = notes_from_event(event, known_refs)
    raw = event.get("payload", {}).get("proposal", {}).get("learning_notes", [])
    pending = []
    for error in errors:
        index = error.get("index", 0)
        value = raw[index] if isinstance(raw, list) and index < len(raw) else raw
        if error["reason"] == "UNKNOWN_SOURCE":
            note = deepcopy(value)
        else:
            note = {
                "title": "Explanation awaiting source review",
                "target_kind": "BOTH", "technology_tags": [], "explanation": "",
                "prerequisites": [], "expanded_steps": [], "alternatives": [],
                "pitfalls": [], "verification": [], "next_small_step": "",
                "source_event_ids": [], "profile_refs": [],
            }
            if isinstance(value, dict) and isinstance(value.get("title"), str):
                note["title"] = value["title"][:240] or note["title"]
        note.update(recorded_in=event["source_ref"], provenance_status="PENDING_SOURCE_REVIEW",
                    authority="AI_EXPLANATION_PENDING_PROVENANCE_NOT_EVIDENCE_OR_MASTERY",
                    diagnostics=[deepcopy(error)])
        pending.append({"index": index, "note": note, "diagnostic": deepcopy(error)})
    return pending


def note_status(events):
    refs = {event["source_ref"] for event in events}
    accepted, pending = 0, []
    for event in events:
        notes, errors = notes_from_event(event, refs)
        accepted += len(notes)
        pending.extend(errors)
    return {"accepted": accepted, "pending": len(pending), "diagnostics": pending}


def capture_safe(configuration, state, *, personal_context=None):
    """A failed personal index never cancels a committed work event."""
    try:
        if not profile.preferences()["enabled"]:
            return {"status": "PROJECT_ONLY", "work_result_unchanged": True}
        from .agent_schema import trace_from_events, reflection_events
        raw_events = state.get("work_trace_events", [])
        if not any(event["type"] in CAPTURE_TYPES for event in raw_events):
            return {"status": "NOT_APPLICABLE"}
        revision = (state.get("work_result") or {}).get("revision", state["revision"])
        events = trace_from_events(reflection_events(raw_events, revision, state["revision"]))["events"]
        last_ref = next((event["source_ref"] for event in reversed(events)
                         if event["type"] == "WorkTurnRecorded"), None)
        added = 0
        with profile.connection(True) as db:
            for event in events:
                identity = "learning-trace-" + digest(event["source_ref"])[:40]
                old = profile._get(db, identity)
                if old:
                    profile.require(old["event"]["event_hash"] == event["event_hash"], "LEARNING_TRACE_CHANGED")
                    continue
                context = deepcopy(personal_context or {}) if event["source_ref"] == last_ref else {}
                row = {
                    "id": identity, "kind": "learning_trace",
                    "work_key": configuration["project"]["id"] + "/" + state["run_id"],
                    "project_id": configuration["project"]["id"], "project_name": configuration["project"]["name"],
                    "run_id": state["run_id"], "request": state["request"], "event": event,
                    "profile_snapshot": context,
                    "profile_snapshot_sha256": event["payload"].get("learning_profile_sha256", digest(context)),
                    "profile_refs": profile_refs(context), "share_with_ai": False,
                    "authority": "EXACT_WORK_EVENT_WITH_SEPARATE_AI_NOTES",
                    "created_at": event["recorded_at"],
                }
                profile._put(db, row)
                added += 1
        from .notebook_bridge import auto_sync
        vault = auto_sync() if added and state.get("work_result") else {"status": "DEFERRED_UNTIL_WORK_BOUNDARY"}
        return {"status": "RECORDED", "added": added, "vault": vault,
                "learning_notes": note_status(events), "work_result_unchanged": True}
    except Exception as error:
        return {"status": "PERSONAL_INDEX_DEFERRED", "reason": getattr(error, "code", type(error).__name__),
                "project_events_retained": True, "work_result_unchanged": True}


def iter_traces(run_id=None, *, newest=False, limit=None):
    """Stream archive rows, optionally bounded; never build an all-history list for the UI."""
    with profile.connection() as db:
        if db is None:
            return
        args, clause = [], "kind='learning_trace'"
        if run_id is not None:
            clause += " AND json_extract(document,'$.run_id')=?"
            args.append(run_id)
        order = "DESC" if newest else "ASC"
        sql = "SELECT document FROM records WHERE " + clause + " ORDER BY updated " + order + ",id " + order
        if limit is not None:
            sql += " LIMIT ?"
            args.append(max(1, int(limit)))
        for row in db.execute(sql, args):
            yield json.loads(row[0])


def traces(run_id=None, limit=None):
    # Full export callers remain lossless. Interactive callers request a bounded page.
    return list(iter_traces(run_id, limit=limit))


def known_sources(refs):
    """Resolve only cited IDs using the records primary key, not every past event."""
    refs = set(refs)
    result = set()
    with profile.connection() as db:
        if db is None:
            return result
        for ref in refs:
            identity = "learning-trace-" + digest(ref)[:40]
            row = db.execute("SELECT document FROM records WHERE id=? AND kind='learning_trace'", (identity,)).fetchone()
            if row and json.loads(row[0]).get("event", {}).get("source_ref") == ref:
                result.add(ref)
    return result


def event_sources(event):
    raw = event.get("payload", {}).get("proposal", {}).get("learning_notes", [])
    refs = {event["source_ref"]}
    if isinstance(raw, list):
        for note in raw[:4]:
            if isinstance(note, dict) and isinstance(note.get("source_event_ids"), list):
                refs.update(ref for ref in note["source_event_ids"][:16] if isinstance(ref, str))
    return known_sources(refs)


def topics():
    by_name = {}
    for row in iter_traces():
        refs = event_sources(row["event"])
        notes, _ = notes_from_event(row["event"], refs)
        pending = pending_notes_from_event(row["event"], refs)
        for note, status in [(note, "notes") for note in notes] + [(item["note"], "pending") for item in pending]:
            for name in note["technology_tags"]:
                item = by_name.setdefault(name, {"technology": name, "work_keys": set(), "notes": 0, "pending": 0})
                item["work_keys"].add(row["work_key"])
                item[status] += 1
    return [{"technology": name, "works": len(value["work_keys"]),
             "notes": value["notes"], "pending": value["pending"]}
            for name, value in sorted(by_name.items())]


def index_project(root, configuration, run_id):
    """Explicitly recover an index, never reconstruct a missing past profile."""
    from .agent_runtime import _state
    from .agent_schema import trace_from_events, reflection_events
    state = _state(root, configuration, run_id)
    revision = (state.get("work_result") or {}).get("revision", state["revision"])
    entries = trace_from_events(reflection_events(state.get("work_trace_events", []), revision, state["revision"]))["events"]
    added = 0
    with profile.connection(True) as db:
        for event in entries:
            identity = "learning-trace-" + digest(event["source_ref"])[:40]
            if profile._get(db, identity):
                continue
            profile._put(db, {
                "id": identity, "kind": "learning_trace",
                "work_key": configuration["project"]["id"] + "/" + run_id,
                "project_id": configuration["project"]["id"], "project_name": configuration["project"]["name"],
                "run_id": run_id, "request": state["request"], "event": event,
                "profile_snapshot": {}, "profile_snapshot_sha256": event["payload"].get("learning_profile_sha256"), "profile_refs": [],
                "share_with_ai": False, "authority": "EXACT_WORK_EVENT_REINDEXED_PROFILE_UNAVAILABLE",
                "created_at": event["recorded_at"],
            })
            added += 1
    return {"added": added, "past_profile_reconstructed": False, "work_result_unchanged": True}
