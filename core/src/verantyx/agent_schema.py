"""Model proposals for work and ownership. No semantic keyword classification."""
from copy import deepcopy

from jsonschema import Draft202012Validator

from .domain.codec import canonical, digest
from .errors import LedgerError

WORK_REQUEST = "verantyx.work-agent-request.v1"
REFLECTION_REQUEST = "verantyx.reflection-request.v1"
FORMATS = (WORK_REQUEST, REFLECTION_REQUEST)
KINDS = ("PROJECT_DELTA", "HUMAN_REQUEST", "HUMAN_DECISION", "AI_DECISION",
         "ASSUMPTION", "OWN", "REVIEW", "REFERENCE", "DELEGATE", "FAILURE",
         "UNKNOWN", "RULE_CANDIDATE", "CHECK_CANDIDATE")
TEXT = {"type": "string", "maxLength": 4000}
SOURCE = {"type": "string", "minLength": 1, "maxLength": 160}


def obj(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def array(items, maximum=24):
    return {"type": "array", "items": items, "maxItems": maximum}


def schema(request):
    if request["format"] == WORK_REQUEST:
        return obj({
            "format": {"const": "verantyx.work-proposal.v1"},
            "status": {"enum": ["CONTINUE", "COMPLETE", "NEEDS_OWNER"]},
            "answer": {"type": "string", "maxLength": 65536},
            "tool_requests": array(obj({
                "id": {"type": "string", "minLength": 1, "maxLength": 80},
                "tool": {"type": "string", "minLength": 1, "maxLength": 80},
                "path": {"type": "string", "maxLength": 1000},
                "text": {"type": "string", "maxLength": 65536},
            }), 8),
            "owner_question": TEXT,
            "assumptions": array(TEXT, 8),
        })
    if request["format"] == REFLECTION_REQUEST:
        return obj({
            "format": {"const": "verantyx.reflection-proposal.v1"},
            "owner_items": array(obj({
                "kind": {"enum": list(KINDS)},
                "text": {"type": "string", "minLength": 1, "maxLength": 4000},
                "reason": {"type": "string", "minLength": 1, "maxLength": 4000},
                "source_event_ids": {"type": "array", "items": SOURCE,
                                     "minItems": 1, "maxItems": 16, "uniqueItems": True},
                "minimum_model": TEXT,
                "counterexample": TEXT,
                "understanding_check": TEXT,
            })),
        })
    raise LedgerError("BRIDGE_PROTOCOL", {"reason": "AGENT_REQUEST_FORMAT"})


def validate_output(request, document):
    if not Draft202012Validator(schema(request)).is_valid(document):
        raise LedgerError("BRIDGE_PROTOCOL", {"reason": "AGENT_OUTPUT_SCHEMA"})
    if len(canonical(document).encode("utf-8")) > 262144:
        raise LedgerError("DOCUMENT_LIMIT")
    if request["format"] == WORK_REQUEST:
        tools = document["tool_requests"]
        if len({row["id"] for row in tools}) != len(tools):
            raise LedgerError("BRIDGE_PROTOCOL", {"reason": "DUPLICATE_TOOL_ID"})
        if document["status"] == "COMPLETE" and not document["answer"].strip():
            raise LedgerError("BRIDGE_PROTOCOL", {"reason": "EMPTY_WORK_ANSWER"})
        if document["status"] == "CONTINUE" and not tools:
            raise LedgerError("BRIDGE_PROTOCOL", {"reason": "EMPTY_WORK_STEP"})
        if document["status"] == "NEEDS_OWNER" and (tools or not document["owner_question"].strip()):
            raise LedgerError("BRIDGE_PROTOCOL", {"reason": "OWNER_QUESTION_BOUNDARY"})
    else:
        sources = {row["source_ref"]: row for row in request["trace"]["events"]}
        for item in document["owner_items"]:
            if any(ref not in sources for ref in item["source_event_ids"]):
                raise LedgerError("REFLECTION_SOURCE_UNKNOWN")
            if item["kind"] == "HUMAN_DECISION" and not any(
                sources[ref]["type"] in ("HumanDecisionRecorded", "WorkOwnerReplyRecorded", "OwnerDesignDecisionRecorded")
                for ref in item["source_event_ids"]
            ):
                raise LedgerError("REFLECTION_HUMAN_SOURCE_REQUIRED")
    return deepcopy(document)


def native_contract(request):
    output = schema(request)
    value = {**deepcopy(request), "output_schema": output}
    return value, obj({"document": output})


def trace_from_events(events):
    # Only immutable recorded bytes enter this fingerprint. No live file reads.
    rows = [{"source_ref": event["project_id"] + ":" + event["event_id"],
             "revision": event["revision"], "type": event["type"],
             "actor_kind": event["actor_kind"], "recorded_at": event["recorded_at"],
             "event_hash": event["event_hash"], "payload": deepcopy(event["payload"])}
            for event in events]
    return {"events": rows, "sha256": digest(rows),
            "first_revision": rows[0]["revision"] if rows else 0,
            "last_revision": rows[-1]["revision"] if rows else 0}
