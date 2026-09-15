"""Replayable work facts and untrusted ownership proposals, never authority."""
from copy import deepcopy
import hashlib

from jsonschema import Draft202012Validator

from ..agent_schema import WORK_REQUEST, REFLECTION_REQUEST, obj, array, schema, validate_output
from ..errors import LedgerError

EVENT_ACTORS = {
    "WorkSessionOpened": "work_gateway",
    "WorkTurnRecorded": "work_model",
    "WorkToolRecorded": "work_gateway",
    "WorkResultRecorded": "work_gateway",
    "WorkOwnerReplyRecorded": "local_cli",
    "ReflectionRecorded": "reflection_gateway",
}
HASH = {"type": "string", "pattern": "^[a-f0-9]{64}$"}
STRING = {"type": "string", "maxLength": 65536}
MODEL = obj({"provider": {"type": "string", "maxLength": 160},
             "model": {"type": "string", "maxLength": 240},
             "adapter_sha256": {"anyOf": [HASH, {"type": "null"}]}})
ARTIFACT = obj({"path": STRING, "storage_path": STRING, "sha256": HASH,
                "size": {"type": "integer", "minimum": 0}})
TOOL = obj({"id": STRING, "tool": STRING, "path": STRING, "text": STRING})
RESULT = obj({
    "status": {"enum": ["SUCCEEDED", "PARTIAL", "WAITING_OWNER", "FAILED"]},
    "answer": STRING, "question": STRING, "reason": STRING,
    "artifacts": array(ARTIFACT, 32), "artifact_directory": STRING,
    "evidence_status": {"const": "NOT_VERIFIED"},
    "model": MODEL,
    "tool_counts": obj({"succeeded": {"type": "integer", "minimum": 0},
                       "refused": {"type": "integer", "minimum": 0}}),
})
REFLECTION = obj({
    "id": {"type": "string", "minLength": 1, "maxLength": 120},
    "status": {"enum": ["PROPOSED", "FAILED", "OFF"]},
    "model": MODEL,
    "trace_sha256": HASH,
    "source_event_ids": array({"type": "string", "maxLength": 160}, 1000),
    "source_first_revision": {"type": "integer", "minimum": 1},
    "source_last_revision": {"type": "integer", "minimum": 1},
    "schema_version": {"const": 1},
    "authority": {"const": "PROPOSAL_ONLY"},
    "failure_code": {"type": "string", "maxLength": 160},
    "proposal": {"anyOf": [schema({"format": REFLECTION_REQUEST}), {"type": "null"}]},
})


def require(condition, code="WORK_EVENT_INVALID"):
    if not condition:
        raise LedgerError(code)


def validate_payload(kind, payload):
    shapes = {
        "WorkSessionOpened": obj({
            "read_scope": array(STRING, 32), "work_model": MODEL,
            "previous_run": {"anyOf": [STRING, {"type": "null"}]},
            "context": {"type": "object"},
            "max_turns": {"type": "integer", "minimum": 1, "maximum": 64},
        }),
        "WorkTurnRecorded": obj({
            "index": {"type": "integer", "minimum": 0, "maximum": 63},
            "request_sha256": HASH, "model": MODEL,
            "proposal": schema({"format": WORK_REQUEST}),
        }),
        "WorkToolRecorded": obj({
            "turn_index": {"type": "integer", "minimum": 0, "maximum": 63},
            "request": TOOL,
            "status": {"enum": ["SUCCEEDED", "REFUSED"]},
            "reason": STRING, "text": STRING,
            "sha256": {"anyOf": [HASH, {"type": "null"}]},
            "artifact": {"anyOf": [ARTIFACT, {"type": "null"}]},
        }),
        "WorkResultRecorded": RESULT,
        "WorkOwnerReplyRecorded": obj({"question_source_ref": STRING, "text": STRING}),
        "ReflectionRecorded": REFLECTION,
    }
    require(kind in shapes and Draft202012Validator(shapes[kind]).is_valid(payload))


def apply_event(state, event):
    kind = event["type"]
    if kind not in EVENT_ACTORS:
        return
    from .events import citation
    from ..agent_schema import trace_from_events
    payload = event["payload"]
    validate_payload(kind, payload)
    ref = citation(event)
    stamp = {"source_ref": ref, "recorded_at": event["recorded_at"],
             "revision": event["revision"]}
    if kind == "WorkSessionOpened":
        require(not state.get("work_session"), "WORK_ALREADY_OPEN")
        require(set(payload["read_scope"]) <= set(state["read_scope"]), "PATH_SCOPE")
        state["work_session"] = {**deepcopy(payload), **stamp}
        state["work_turns"], state["work_tools"], state["work_artifacts"] = [], [], {}
    elif kind == "WorkTurnRecorded":
        require(state.get("work_session") and not state.get("work_result"), "WORK_CONTEXT")
        require(payload["index"] == len(state["work_turns"])
                and payload["index"] < state["work_session"]["max_turns"], "WORK_CONTEXT")
        validate_output({"format": WORK_REQUEST}, payload["proposal"])
        state["work_turns"].append({**deepcopy(payload), **stamp})
    elif kind == "WorkToolRecorded":
        require(state.get("work_turns") and not state.get("work_result"), "WORK_CONTEXT")
        turn = state["work_turns"][-1]
        require(payload["turn_index"] == turn["index"]
                and payload["request"] in turn["proposal"]["tool_requests"], "WORK_TOOL_BINDING")
        require(not any(row["turn_index"] == turn["index"]
                        and row["request"]["id"] == payload["request"]["id"]
                        for row in state["work_tools"]), "WORK_TOOL_DUPLICATE")
        tool = payload["request"]["tool"]
        if payload["status"] == "SUCCEEDED":
            require(tool in ("read_file", "write_candidate", "list_files"), "WORK_TOOL_PERMISSION")
            if tool == "read_file":
                require(payload["request"]["path"] in state["read_scope"], "PATH_SCOPE")
                require(payload["sha256"] == hashlib.sha256(payload["text"].encode()).hexdigest())
            if tool == "write_candidate":
                item = payload["artifact"]
                require(item and item["path"] == payload["request"]["path"]
                        and item["sha256"] == hashlib.sha256(payload["request"]["text"].encode()).hexdigest())
                require(item["size"] == len(payload["request"]["text"].encode()))
                state["work_artifacts"][item["path"]] = deepcopy(item)
            else:
                require(payload["artifact"] is None)
        else:
            require(payload["artifact"] is None and payload["sha256"] is None)
        state["work_tools"].append({**deepcopy(payload), **stamp})
    elif kind == "WorkResultRecorded":
        require(state.get("work_session") and not state.get("work_result"), "WORK_CONTEXT")
        require(payload["artifacts"] == sorted(state["work_artifacts"].values(), key=lambda x: x["path"]),
                "WORK_ARTIFACT_BINDING")
        succeeded = sum(row["status"] == "SUCCEEDED" for row in state["work_tools"])
        refused = sum(row["status"] == "REFUSED" for row in state["work_tools"])
        require(payload["tool_counts"] == {"succeeded": succeeded, "refused": refused})
        if payload["status"] == "SUCCEEDED":
            require(state["work_turns"] and not refused
                    and state["work_turns"][-1]["proposal"]["status"] == "COMPLETE")
        if payload["status"] == "WAITING_OWNER":
            require(state["work_turns"] and state["work_turns"][-1]["proposal"]["status"] == "NEEDS_OWNER")
        if state["work_turns"]:
            last = state["work_turns"][-1]["proposal"]
            require(payload["answer"] == last["answer"] and payload["question"] == last["owner_question"])
        state["work_result"] = {**deepcopy(payload), **stamp}
    elif kind == "WorkOwnerReplyRecorded":
        require(state.get("work_result", {}).get("status") == "WAITING_OWNER", "WORK_QUESTION_UNKNOWN")
        require(payload["question_source_ref"] == state["work_result"]["source_ref"]
                and not state.get("work_owner_reply"), "WORK_QUESTION_UNKNOWN")
        # A reply is recorded speech, NOT a file permission or rule approval.
        state["work_owner_reply"] = {**deepcopy(payload), **stamp}
    elif kind == "ReflectionRecorded":
        result = state.get("work_result")
        require(result is not None, "WORK_RESULT_REQUIRED")
        reflections = state.setdefault("work_reflections", [])
        require(not any(row["id"] == payload["id"] for row in reflections), "REFLECTION_DUPLICATE")
        # Work events have been accumulated by the reducer, not supplied by AI.
        events = [row for row in state.get("work_trace_events", [])
                  if row["revision"] <= result["revision"]]
        trace = trace_from_events(events)
        require(payload["trace_sha256"] == trace["sha256"]
                and payload["source_event_ids"] == [row["source_ref"] for row in trace["events"]]
                and payload["source_first_revision"] == trace["first_revision"]
                and payload["source_last_revision"] == trace["last_revision"], "REFLECTION_TRACE_CHANGED")
        if payload["status"] == "PROPOSED":
            require(payload["proposal"] is not None and not payload["failure_code"])
            validate_output({"format": REFLECTION_REQUEST, "trace": trace}, payload["proposal"])
        else:
            require(payload["proposal"] is None)
        reflections.append({**deepcopy(payload), **stamp})
