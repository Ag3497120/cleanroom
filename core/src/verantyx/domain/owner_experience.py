"""Explicit human choices and experience, distinct from AI interpretations."""
from copy import deepcopy

from jsonschema import Draft202012Validator

from ..agent_schema import obj
from .codec import digest
from ..errors import LedgerError

TARGETS = ("OWN", "REVIEW", "REFERENCE", "DELEGATE")
EVENT_ACTORS = {
    "OwnerItemChoiceRecorded": "local_cli",
    "OwnerExperienceNoteRecorded": "local_cli",
    "OwnerDesignDecisionRecorded": "local_cli",
    "OwnerDesignDecisionWithdrawn": "local_cli",
}
TEXT = {"type": "string", "maxLength": 4000}
STATEMENT = {"type": "string", "minLength": 1, "maxLength": 4000}
REFERENCE = {"type": "string", "minLength": 1, "maxLength": 160}
ITEM = obj({
    "reflection_id": {"type": "string", "minLength": 1, "maxLength": 120},
    "item_index": {"type": "integer", "minimum": 0, "maximum": 23},
    "item_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
})
OPTIONAL_ITEM = {"anyOf": [ITEM, {"type": "null"}]}
SCHEMAS = {
    "OwnerItemChoiceRecorded": obj({
        "item": ITEM,
        "action": {"enum": ["SELECT_TARGET", "DEFER", "DISMISS", "RESTORE"]},
        "target": {"enum": [*TARGETS, None]},
        "reason": TEXT,
        "share_with_ai": {"type": "boolean"},
    }),
    "OwnerExperienceNoteRecorded": obj({
        "item": OPTIONAL_ITEM,
        "kind": {"enum": ["NOTE", "SELF_EXPLANATION", "APPLICATION", "TRANSFER"]},
        "text": STATEMENT,
        "share_with_ai": {"type": "boolean"},
    }),
    "OwnerDesignDecisionRecorded": obj({
        "basis_item": OPTIONAL_ITEM,
        "category": {"enum": ["PURPOSE", "CONSTRAINT", "DESIGN", "TRADEOFF"]},
        "statement": STATEMENT,
        "reason": TEXT,
        "scope": {"enum": ["WORK", "PROJECT"]},
        "share_with_ai": {"type": "boolean"},
    }),
    "OwnerDesignDecisionWithdrawn": obj({
        "decision_source_ref": REFERENCE,
        "reason": TEXT,
    }),
}


def require(condition, code="OWNER_EXPERIENCE_INVALID"):
    if not condition:
        raise LedgerError(code)


def validate_payload(kind, payload):
    require(kind in SCHEMAS and Draft202012Validator(SCHEMAS[kind]).is_valid(payload))
    if kind == "OwnerItemChoiceRecorded":
        require((payload["action"] == "SELECT_TARGET") == (payload["target"] is not None))
    if kind in ("OwnerExperienceNoteRecorded", "OwnerDesignDecisionRecorded"):
        require(bool(payload.get("text", payload.get("statement", "")).strip()))


def item_id(reference):
    return "owner-" + digest(reference)[:24]


def item_reference(reflection, index):
    return {"reflection_id": reflection["id"], "item_index": index,
            "item_sha256": digest(reflection["proposal"]["owner_items"][index])}


def resolve_item(state, reference):
    reflection = next((row for row in state.get("work_reflections", [])
                       if row["id"] == reference["reflection_id"] and row["status"] == "PROPOSED"), None)
    require(reflection is not None, "OWNER_SOURCE_CHANGED")
    items = reflection["proposal"]["owner_items"]
    require(reference["item_index"] < len(items), "OWNER_SOURCE_CHANGED")
    item = items[reference["item_index"]]
    require(digest(item) == reference["item_sha256"], "OWNER_SOURCE_CHANGED")
    return item, reflection


def empty_state():
    return {"cards": {}, "notes": [], "decisions": []}


def apply_event(state, event):
    kind = event["type"]
    if kind not in EVENT_ACTORS:
        return
    from .events import citation
    payload = event["payload"]
    validate_payload(kind, payload)
    owned = state.setdefault("owner_experience", empty_state())
    stamp = {"source_ref": citation(event), "recorded_at": event["recorded_at"],
             "event_hash": event["event_hash"], "revision": event["revision"]}
    if kind == "OwnerItemChoiceRecorded":
        original, _ = resolve_item(state, payload["item"])
        identifier = item_id(payload["item"])
        card = owned["cards"].setdefault(identifier, {
            "item": deepcopy(payload["item"]), "status": "PROPOSED",
            "target": original["kind"] if original["kind"] in TARGETS else None,
            "target_is_suggestion": True, "history": [],
        })
        entry = {**deepcopy(payload), **stamp}
        card["history"].append(entry)
        card["latest_action"] = entry
        if payload["action"] == "SELECT_TARGET":
            card.update(target=payload["target"], target_is_suggestion=False, status="SELECTED")
            card["target_choice"] = entry
        elif payload["action"] == "DEFER":
            card["status"] = "DEFERRED"
        elif payload["action"] == "DISMISS":
            card["status"] = "DISMISSED"
        else:
            card["status"] = "PROPOSED" if card["target_is_suggestion"] else "SELECTED"
    elif kind == "OwnerExperienceNoteRecorded":
        if payload["item"] is not None:
            resolve_item(state, payload["item"])
        owned["notes"].append({**deepcopy(payload), **stamp, "basis": "HUMAN_RECORDED",
                               "mastery": "NOT_ASSESSED"})
    elif kind == "OwnerDesignDecisionRecorded":
        if payload["basis_item"] is not None:
            resolve_item(state, payload["basis_item"])
        owned["decisions"].append({**deepcopy(payload), **stamp, "status": "ACTIVE_STATEMENT",
                                   "authority": "NO_EXECUTION_GRANT"})
    else:
        selected = next((row for row in owned["decisions"]
                         if row["source_ref"] == payload["decision_source_ref"]), None)
        require(selected is not None and selected["status"] == "ACTIVE_STATEMENT", "OWNER_DECISION_CHANGED")
        selected["status"] = "WITHDRAWN"
        selected["withdrawal"] = {**deepcopy(payload), **stamp}
