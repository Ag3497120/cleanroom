"""Replayable work facts and untrusted ownership proposals, never authority."""
from copy import deepcopy
import hashlib

from jsonschema import Draft202012Validator

from ..agent_schema import WORK_REQUEST, REFLECTION_REQUEST, REFLECTION_SKILLS_REQUEST, obj, array, schema, validate_output
from ..errors import LedgerError

EVENT_ACTORS = {
    "WorkSessionOpened": "work_gateway",
    "WorkTurnRecorded": "work_model",
    "WorkToolRecorded": "work_gateway",
    "WorkResultRecorded": "work_gateway",
    "WorkOwnerReplyRecorded": "local_cli",
    "WorkInstructionRecorded": "local_cli",
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
CHANGE_REVIEW = obj({
    "review_id": HASH, "path": STRING, "request_id": STRING,
    "before_sha256": {"anyOf": [HASH, {"type": "null"}]},
    "after_sha256": HASH, "diff_sha256": HASH,
    "baseline": {"enum": ["CANDIDATE", "APPROVED_SOURCE", "NOT_READ"]},
    "scope": {"const": "ISOLATED_CANDIDATE_ONLY"},
    "mode": {"enum": ["ALLOW_ONCE", "BYPASS_GRANTED", "BYPASS_RUN", "WORKSPACE", "PERMANENT", "DENIED", "PREAUTHORIZED"]},
    "grant_id": {"type": "string", "maxLength": 64},
})
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
    "schema_version": {"enum": [1, 2]},
    "authority": {"const": "PROPOSAL_ONLY"},
    "failure_code": {"type": "string", "maxLength": 160},
    "proposal": {"anyOf": [schema({"format": REFLECTION_REQUEST}),
                             schema({"format": REFLECTION_SKILLS_REQUEST}), {"type": "null"}]},
})


# Optional additive provenance fields keep historical v1 ledgers readable.
REFLECTION["properties"].update({
    "trace_version": {"const": 2},
    "generation_id": {"type": "string", "minLength": 1, "maxLength": 120},
    "perspective": {"type": "string", "maxLength": 4000},
    "owner_context": {"type": "object"},
    "owner_context_sha256": HASH,
    "skill_context": {"type": "object"},
    "skill_context_sha256": HASH,
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
        "WorkInstructionRecorded": obj({
            "id": {"type": "string", "minLength": 1, "maxLength": 64},
            "text": {"type": "string", "minLength": 1, "maxLength": 16000},
            "user_text": {"type": "string", "minLength": 1, "maxLength": 16000},
            "before_turn": {"type": "integer", "minimum": 0, "maximum": 63},
            "authority": {"const": "HUMAN_INSTRUCTION_NOT_PERMISSION"},
        }),
        "ReflectionRecorded": REFLECTION,
    }
    shapes["WorkToolRecorded"]["properties"]["change_review"] = CHANGE_REVIEW
    shapes["WorkTurnRecorded"]["properties"]["learning_profile_sha256"] = HASH
    shapes["WorkTurnRecorded"]["properties"]["context_snapshot"] = {"type": "object"}
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
        continued = payload["context"].get("continued_candidate")
        if continued:
            require(continued["run_id"] == payload["previous_run"], "WORK_ARTIFACT_BINDING")
            require(Draft202012Validator(array(ARTIFACT, 32)).is_valid(continued["artifacts"]),
                    "WORK_ARTIFACT_BINDING")
            require(len({row["path"] for row in continued["artifacts"]}) == len(continued["artifacts"]),
                    "WORK_ARTIFACT_BINDING")
            state["work_artifacts"] = {row["path"]: deepcopy(row) for row in continued["artifacts"]}
    elif kind == "WorkInstructionRecorded":
        require(state.get("work_session") and not state.get("work_result"), "WORK_CONTEXT")
        require(payload["before_turn"] == len(state["work_turns"])
                and payload["before_turn"] < state["work_session"]["max_turns"], "WORK_CONTEXT")
        instructions = state.setdefault("work_instructions", [])
        require(not any(row["id"] == payload["id"] for row in instructions), "WORK_CONTEXT")
        instructions.append({**deepcopy(payload), **stamp})
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
        review = payload.get("change_review")
        if review is not None:
            require(tool in ("write_candidate", "copy_asset")
                    and review["path"] == payload["request"]["path"]
                    and review["request_id"] == payload["request"]["id"], "WORK_REVIEW_BINDING")
            if review["mode"] == "BYPASS_RUN":
                require(any(row.get("change_review", {}).get("mode") == "BYPASS_GRANTED"
                            and row["change_review"]["grant_id"] == review["grant_id"]
                            for row in state["work_tools"]), "WORK_REVIEW_BINDING")
            if review["mode"] == "BYPASS_GRANTED":
                require(review["grant_id"] == review["review_id"], "WORK_REVIEW_BINDING")
            if payload["status"] == "SUCCEEDED":
                require(review["mode"] != "DENIED" and payload["artifact"] is not None
                        and review["after_sha256"] == payload["artifact"]["sha256"], "WORK_REVIEW_BINDING")
        if payload["status"] == "SUCCEEDED":
            require(tool in ("read_file", "read_candidate", "write_candidate", "copy_asset", "list_files",
                             "ask_stack_experience", "suggest_owner_update", "request_model_change",
                             "consult_child", "read_work_history", "list_mcp_tools",
                             "call_mcp", "run_project_check"), "WORK_TOOL_PERMISSION")
            if tool in ("ask_stack_experience", "suggest_owner_update"):
                require(payload["artifact"] is None and payload["sha256"] is None)
            if tool == "read_file":
                require(payload["request"]["path"] in state["read_scope"], "PATH_SCOPE")
                require(payload["sha256"] == hashlib.sha256(payload["text"].encode()).hexdigest())
            if tool == "read_candidate":
                item = state["work_artifacts"].get(payload["request"]["path"])
                require(item and item["sha256"] == payload["sha256"]
                        == hashlib.sha256(payload["text"].encode()).hexdigest(), "WORK_ARTIFACT_BINDING")
            if tool in ("write_candidate", "copy_asset"):
                item = payload["artifact"]
                require(item and item["path"] == payload["request"]["path"])
                if tool == "write_candidate":
                    require(item["sha256"] == hashlib.sha256(payload["request"]["text"].encode()).hexdigest())
                    require(item["size"] == len(payload["request"]["text"].encode()))
                else:
                    asset = next((row for row in state["work_session"]["context"].get("approved_assets", [])
                                  if row["path"] == payload["request"]["text"]), None)
                    require(asset and asset["path"] in state["read_scope"]
                            and asset["sha256"] == item["sha256"] and asset["size"] == item["size"],
                            "WORK_ARTIFACT_BINDING")
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
        if payload.get("trace_version") == 2:
            from ..agent_schema import reflection_events
            from .codec import digest
            require(result["revision"] <= payload["source_last_revision"] < event["revision"]
                    and payload.get("generation_id") == payload["id"]
                    and "owner_context" in payload
                    and payload.get("owner_context_sha256") == digest(payload["owner_context"]),
                    "REFLECTION_TRACE_CHANGED")
            events = reflection_events(state.get("work_trace_events", []), result["revision"],
                                       payload["source_last_revision"])
        trace = trace_from_events(events)
        require(payload["trace_sha256"] == trace["sha256"]
                and payload["source_event_ids"] == [row["source_ref"] for row in trace["events"]]
                and payload["source_first_revision"] == trace["first_revision"]
                and payload["source_last_revision"] == trace["last_revision"], "REFLECTION_TRACE_CHANGED")
        if payload["schema_version"] == 2:
            from .codec import digest
            require(payload.get("trace_version") == 2 and "skill_context" in payload
                    and payload.get("skill_context_sha256") == digest(payload["skill_context"]),
                    "REFLECTION_TRACE_CHANGED")
        if payload["status"] == "PROPOSED":
            require(payload["proposal"] is not None and not payload["failure_code"])
            validate_output({"format": REFLECTION_SKILLS_REQUEST if payload["schema_version"] == 2 else REFLECTION_REQUEST,
                             "trace": trace, "skill_context": payload.get("skill_context", {})}, payload["proposal"])
        else:
            require(payload["proposal"] is None)
        reflections.append({**deepcopy(payload), **stamp})
