"""Model proposals for work and ownership. No semantic keyword classification."""
from copy import deepcopy

from jsonschema import Draft202012Validator

from .domain.codec import canonical, digest
from .errors import LedgerError

WORK_REQUEST = "verantyx.work-agent-request.v1"
REFLECTION_REQUEST = "verantyx.reflection-request.v1"
REFLECTION_SKILLS_REQUEST = "verantyx.reflection-skills-request.v1"
PERSONAL_REQUEST = "verantyx.personal-growth-request.v1"
FORMATS = (WORK_REQUEST, REFLECTION_REQUEST, REFLECTION_SKILLS_REQUEST, PERSONAL_REQUEST)
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
        output = obj({
            "format": {"type": "string", "const": "verantyx.work-proposal.v1"},
            "status": {"type": "string", "enum": ["CONTINUE", "COMPLETE", "NEEDS_OWNER"]},
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
        # Invalid optional teaching notes must not invalidate otherwise useful work.
        output["properties"]["learning_notes"] = {}
        return output
    if request["format"] in (REFLECTION_REQUEST, REFLECTION_SKILLS_REQUEST):
        output = obj({
            "format": {"type": "string", "const": "verantyx.reflection-proposal.v1"},
            "owner_items": array(obj({
                "kind": {"type": "string", "enum": list(KINDS)},
                "text": {"type": "string", "minLength": 1, "maxLength": 4000},
                "reason": {"type": "string", "minLength": 1, "maxLength": 4000},
                "source_event_ids": {"type": "array", "items": SOURCE,
                                     "minItems": 1, "maxItems": 16, "uniqueItems": True},
                "minimum_model": TEXT,
                "counterexample": TEXT,
                "understanding_check": TEXT,
            })),
        })
        if request["format"] == REFLECTION_SKILLS_REQUEST:
            from .skill_assets import candidate_schema
            output["properties"]["format"]["const"] = "verantyx.reflection-proposal.v2"
            output["properties"]["skill_candidates"] = array(candidate_schema(), 8)
            output["required"].append("skill_candidates")
        return output
    if request["format"] == PERSONAL_REQUEST:
        if request.get("mode") == "unpack":
            from .learning_guides import output_schema
            return output_schema()
        from .personal_growth import output_schema
        return output_schema()
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
    elif request["format"] == PERSONAL_REQUEST:
        if request.get("mode") == "unpack":
            from .learning_guides import validate
            return validate(request, document)
        from .personal_growth import validate
        return validate(request, document)
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
        if request["format"] == REFLECTION_SKILLS_REQUEST:
            from .skill_assets import validate_candidates
            validate_candidates(request, document["skill_candidates"])
    return deepcopy(document)


def transport_schema(value):
    """Use a shared structured-output subset, without weakening local validation.

    The full contract remains in the prompt and validate_output(). Provider
    support for string/array bounds differs; those limits are enforced locally.
    No task text or domain-specific examples participate in this conversion.
    """
    if isinstance(value, list):
        return [transport_schema(item) for item in value]
    if not isinstance(value, dict):
        return deepcopy(value)
    unsupported = {"minLength", "maxLength", "minItems", "maxItems", "uniqueItems"}
    result = {}
    for key, item in value.items():
        if key in unsupported:
            continue
        if key == "const":
            result["enum"] = [deepcopy(item)]
        elif key == "properties":
            result[key] = {name: transport_schema(child) for name, child in item.items()}
        else:
            result[key] = transport_schema(item)
    return result


def generation_schema(request):
    """Constrain provenance identifiers, never the model's interpretation."""
    output = schema(request)
    if request.get("format") == WORK_REQUEST:
        from .learning_capture import note_schema, profile_refs
        note = note_schema()
        for field, refs in (
                ("source_event_ids", list(dict.fromkeys(request.get("learning_sources", [])))),
                ("profile_refs", profile_refs(request.get("personal_context", {})))):
            if refs:
                note["properties"][field]["items"] = {**SOURCE, "enum": refs}
            else:
                note["properties"][field]["maxItems"] = 0
        output["properties"]["learning_notes"] = array(note, 4)
        output["required"].append("learning_notes")
    if request.get("format") == PERSONAL_REQUEST and request.get("mode") == "unpack":
        refs = [row["source_ref"] for row in request.get("trace", {}).get("events", [])]
        for name in ("parts", "can_delegate"):
            if refs:
                output["properties"][name]["items"]["properties"]["source_event_ids"]["items"] = {**SOURCE, "enum": refs}
            else:
                output["properties"][name]["maxItems"] = 0
        resources = [row["id"] for row in request.get("web_search", {}).get("results", [])]
        if resources:
            output["properties"]["resources"]["items"]["properties"]["resource_id"] = {**SOURCE, "enum": resources}
        else:
            output["properties"]["resources"]["maxItems"] = 0
        return output
    if request.get("format") in (REFLECTION_REQUEST, REFLECTION_SKILLS_REQUEST) and "trace" in request:
        refs = list(dict.fromkeys(row["source_ref"] for row in request["trace"]["events"]))
        owner_items = output["properties"]["owner_items"]
        if refs:
            owner_items["items"]["properties"]["source_event_ids"]["items"] = {
                **SOURCE, "enum": refs}
        else:
            # With no recorded source, an empty interpretation is honest.
            owner_items["maxItems"] = 0
    if request.get("format") == REFLECTION_SKILLS_REQUEST:
        refs = list(dict.fromkeys(row["source_ref"] for row in request.get("trace", {}).get("events", [])))
        candidates = output["properties"]["skill_candidates"]
        if refs:
            candidates["items"]["properties"]["source_event_ids"]["items"] = {**SOURCE, "enum": refs}
        else:
            candidates["maxItems"] = 0
        candidates["items"]["properties"]["extends_skill_id"]["enum"] = [
            "", *dict.fromkeys(row["id"] for row in request.get("skill_context", {}).get("items", []))]
    if request.get("format") == PERSONAL_REQUEST:
        refs = list(dict.fromkeys(row["source_ref"] for row in request.get("trace", {}).get("events", [])))
        for name in ("technologies", "interpretations", "lessons", "profile_updates"):
            entries = output["properties"][name]
            if refs:
                entries["items"]["properties"]["source_event_ids"]["items"] = {**SOURCE, "enum": refs}
            else:
                entries["maxItems"] = 0
    return output


def native_contract(request):
    output = generation_schema(request)
    value = {**deepcopy(request), "output_schema": output}
    return value, transport_schema(obj({"document": output}))


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


def reflection_events(events, work_revision, through_revision=None):
    """An immutable work prefix plus shareable follow-up facts, never private notes.

    Earlier ReflectionRecorded events are not fresh evidence. Excluding them
    avoids circular self-citation and does not discard their separate history.
    """
    through_revision = through_revision if through_revision is not None else work_revision
    public_followups = {"WorkOwnerReplyRecorded", "WorkCheckStarted", "WorkCheckRecorded"}
    shareable = {"OwnerExperienceNoteRecorded", "OwnerItemChoiceRecorded", "OwnerDesignDecisionRecorded"}
    rows = []
    for event in events:
        if event["revision"] > through_revision:
            continue
        if event["revision"] <= work_revision:
            rows.append(event)
        elif event["type"] in public_followups:
            rows.append(event)
        elif event["type"] in shareable and event["payload"].get("share_with_ai") is True:
            rows.append(event)
    return rows
