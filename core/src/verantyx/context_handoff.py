"""Loss-aware bounded context views over immutable work records.

Compaction affects model input, never the event archive. No summary is promoted
to evidence; omitted events remain addressable with read_work_history.
"""
from copy import deepcopy
from .agent_schema import trace_from_events, reflection_events
from .domain.codec import canonical, digest
from .errors import LedgerError


def source_events(state):
    raw = state.get("work_trace_events", [])
    revision = (state.get("work_result") or {}).get("revision", state["revision"])
    return trace_from_events(reflection_events(raw, revision, state["revision"]))["events"]


def build(root, configuration, run_id, *, budget=60000):
    if type(budget) is not int or not 4000 <= budget <= 200000:
        raise LedgerError("ARGUMENTS")
    from .agent_runtime import _state
    state = _state(root, configuration, run_id)
    events = source_events(state)
    selected, omitted, size = [], [], 0
    for event in reversed(events):
        length = len(canonical(event).encode())
        if size + length <= budget:
            selected.append(event)
            size += length
        else:
            omitted.append({"source_ref": event["source_ref"], "event_hash": event["event_hash"],
                            "type": event["type"], "revision": event["revision"]})
    return {"format": "verantyx.handoff.v1", "run_id": run_id,
            "purpose": configuration["project"]["purpose"], "request": state["request"],
            "work_status": (state.get("work_result") or {}).get("status", "IN_PROGRESS"),
            "candidate_manifest": deepcopy(list(state.get("work_artifacts", {}).values())),
            "previous_model": state.get("work_session", {}).get("work_model"),
            "events": list(reversed(selected)), "omitted": list(reversed(omitted)),
            "source_sha256": digest(events), "archive_available": True,
            "authority": "REFERENCE_NOT_PERMISSION_OR_MASTERY", "semantic_summary": False,
            "read_more": {"tool": "read_work_history", "path": run_id, "text": "SOURCE_REF"},
            "budget_bytes": budget}


def compact(request, *, budget=180000):
    value = deepcopy(request)
    if len(canonical(value).encode()) <= budget:
        return value, {"compacted": False, "omitted": [], "archive_unchanged": True}
    omitted = []
    for name, keep in (("turns", 2), ("tool_receipts", 4)):
        rows = value.get(name, [])
        while len(rows) > keep and len(canonical(value).encode()) > budget:
            row = rows.pop(0)
            omitted.append({"collection": name, "source_ref": row.get("source_ref"),
                            "sha256": digest(row), "index": row.get("index", row.get("turn_index"))})
    handoff = value.get("project_context", {}).get("model_handoff")
    if handoff:
        while handoff["events"] and len(canonical(value).encode()) > budget:
            event = handoff["events"].pop(0)
            handoff["omitted"].append({key: event[key] for key in ("source_ref", "event_hash", "type", "revision")})
    value["context_compaction"] = {"compacted": True, "omitted": omitted,
                                   "archive_unchanged": True, "semantic_summary": False}
    # Leave indispensable recent state intact. A remaining overflow fails
    # at the normal request limit, rather than silently deleting constraints.
    return value, value["context_compaction"]


def read(root, configuration, run_id, source_ref, *, allowed_runs):
    if run_id not in allowed_runs:
        raise LedgerError("PATH_SCOPE")
    from .agent_runtime import _state
    rows = source_events(_state(root, configuration, run_id))
    event = next((row for row in rows if row["source_ref"] == source_ref), None)
    if event is None:
        raise LedgerError("REFLECTION_SOURCE_UNKNOWN")
    body = canonical(event)
    if len(body.encode()) > 65536:
        raise LedgerError("DOCUMENT_LIMIT")
    return body
