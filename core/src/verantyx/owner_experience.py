"""Project-linked human experience over the existing append-only event store."""
from copy import deepcopy
import uuid

from .application import now, record_run, _receipt_view
from .authority import require_current_approval_valid
from .domain.codec import canonical, digest
from .domain.owner_experience import (TARGETS, empty_state, item_id, item_reference,
                                      resolve_item, validate_payload)
from .errors import LedgerError
from .kernel.reducer import replay
from .storage.sqlite import EventStore
from .verification import _read, _append


def read_states(root, configuration):
    try:
        with EventStore(root, configuration["project"]["id"]) as store:
            events = store.events()
    except LedgerError as error:
        if error.code == "STORE_MISSING":
            return []
        raise
    streams = {}
    for event in events:
        streams.setdefault(event["stream_id"], []).append(event)
    return [replay(rows) for rows in sorted(streams.values(),
            key=lambda rows: rows[-1]["recorded_at"], reverse=True)]


def _commit(root, configuration, run_id, kind, payload, key=None, expected_revision=None):
    validate_payload(kind, payload)
    key = key or "owner-" + uuid.uuid4().hex
    intent = {"operation": kind, "run_id": run_id, "payload": payload,
              "expected_revision": expected_revision}
    with EventStore(root, configuration["project"]["id"], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached:
            return _receipt_view(cached, key)
        previous, state = _read(store, run_id)
        if expected_revision is not None and state["revision"] != expected_revision:
            raise LedgerError("REVISION_CONFLICT")
        require_current_approval_valid()
        receipt = _append(store, previous, [(kind, payload, None)], key, intent, now)
        return _receipt_view(receipt, key)


def choose(root, configuration, run_id, reference, action, *, target=None, reason="",
           share_with_ai=True, key=None, expected_revision=None):
    return _commit(root, configuration, run_id, "OwnerItemChoiceRecorded",
                   {"item": reference, "action": action, "target": target,
                    "reason": reason, "share_with_ai": share_with_ai}, key, expected_revision)


def add_note(root, configuration, run_id, *, text, reference=None, kind="NOTE",
             share_with_ai=False, key=None, expected_revision=None):
    return _commit(root, configuration, run_id, "OwnerExperienceNoteRecorded",
                   {"item": reference, "kind": kind, "text": text, "share_with_ai": share_with_ai},
                   key, expected_revision)


def decide(root, configuration, run_id, *, statement, reason="", reference=None,
           category="DESIGN", scope="PROJECT", share_with_ai=True, key=None, expected_revision=None):
    return _commit(root, configuration, run_id, "OwnerDesignDecisionRecorded",
                   {"basis_item": reference, "category": category, "statement": statement,
                    "reason": reason, "scope": scope, "share_with_ai": share_with_ai},
                   key, expected_revision)


def withdraw(root, configuration, run_id, decision_source_ref, *, reason="", key=None, expected_revision=None):
    return _commit(root, configuration, run_id, "OwnerDesignDecisionWithdrawn",
                   {"decision_source_ref": decision_source_ref, "reason": reason},
                   key, expected_revision)


def project_note_run(root, configuration):
    run_id = "owner-notebook-" + configuration["project"]["id"]
    result = record_run(root, configuration, request="Owner project notebook", run_id=run_id,
                        key=run_id, context={"component": "OWNER_NOTEBOOK", "workload": "LOCAL_NOTES",
                                             "risk": "UNSPECIFIED"})
    return result["state"]["run_id"]


def cards(state, *, include_dismissed=False):
    owned = state.get("owner_experience", empty_state())
    successful = [row for row in state.get("work_reflections", []) if row["status"] == "PROPOSED"]
    latest = successful[-1]["id"] if successful else None
    notes = owned["notes"]
    values = []
    for reflection in successful:
        for index, proposal in enumerate(reflection["proposal"]["owner_items"]):
            reference = item_reference(reflection, index)
            identifier = item_id(reference)
            choice = owned["cards"].get(identifier)
            local_notes = [row for row in notes if row["item"] == reference]
            # Reclassification never discards a human's earlier choice or notes.
            if reflection["id"] != latest and not choice and not local_notes:
                continue
            status = choice["status"] if choice else "PROPOSED"
            if status == "DISMISSED" and not include_dismissed:
                continue
            values.append({
                **deepcopy(proposal), "id": identifier, "reference": reference,
                "run_id": state["run_id"], "request": state["request"],
                "revision": state["revision"], "reflection_id": reflection["id"],
                "model": deepcopy(reflection["model"]), "source_ref": reflection["source_ref"],
                "status": status, "authority": "PROPOSAL_ONLY",
                "target": choice["target"] if choice else (proposal["kind"] if proposal["kind"] in TARGETS else None),
                "target_is_suggestion": choice["target_is_suggestion"] if choice else True,
                "human_choice": deepcopy(choice), "human_notes": deepcopy(local_notes),
                "human_understanding": "SELF_REPORT_RECORDED" if any(
                    note["kind"] in ("SELF_EXPLANATION", "APPLICATION", "TRANSFER") for note in local_notes)
                    else "NOT_ASSESSED",
                "earlier_reflection": reflection["id"] != latest,
            })
    return values


def project(states, configuration):
    all_cards, decisions, notes, works, questions = [], [], [], [], []
    for state in states:
        owned = state.get("owner_experience", empty_state())
        all_cards.extend(cards(state))
        decisions.extend({**deepcopy(row), "run_id": state["run_id"]} for row in owned["decisions"])
        notes.extend({**deepcopy(row), "run_id": state["run_id"]} for row in owned["notes"])
        result = state.get("work_result")
        if result:
            works.append({"run_id": state["run_id"], "request": state["request"],
                          "result": deepcopy(result),
                          "reflection_status": (state.get("work_reflections") or [{"status": "PENDING"}])[-1]["status"]})
            if result["status"] == "WAITING_OWNER" and not state.get("work_owner_reply"):
                questions.append({"run_id": state["run_id"], "request": state["request"],
                                  "question": result["question"], "source_ref": result["source_ref"]})
    active = [row for row in decisions if row["status"] == "ACTIVE_STATEMENT"]
    learning = [row for row in all_cards if row["target"] in ("OWN", "REVIEW")]
    priorities = [row for row in learning if row["status"] not in ("DEFERRED", "DISMISSED")
                  and row["human_understanding"] == "NOT_ASSESSED"]
    return {"format": "verantyx.owner-notebook.v1", "project": deepcopy(configuration["project"]),
            "works": works, "cards": all_cards, "questions": questions, "decisions": decisions,
            "active_decisions": active, "notes": notes,
            "reading_suggestions": priorities[:configuration["learning"]["max_items"]],
            "counts": {
                "work_notes": len(works), "questions": len(questions),
                "human_decisions": len(active),
                "ownership_choices": sum(not row["target_is_suggestion"] for row in all_cards),
                "explanations": sum(row["kind"] in ("SELF_EXPLANATION", "APPLICATION", "TRANSFER") for row in notes),
                "reference": sum(row["target"] == "REFERENCE" and not row["target_is_suggestion"] for row in all_cards),
                "delegation_preferences": sum(row["target"] == "DELEGATE" and not row["target_is_suggestion"] for row in all_cards),
                "deferred": sum(row["status"] == "DEFERRED" for row in all_cards),
            }, "mastery": "NOT_ASSESSED", "writes": False, "model_calls": 0}


def shared_context(states):
    """Only explicitly shareable human records enter the next model request.

    This is reference context, never a tool grant, asset activation or mastery.
    """
    sections = {"project_decisions": [], "ownership_choices": [], "shared_notes": []}
    omitted = {key: 0 for key in sections}
    candidates = {key: [] for key in sections}
    for state in states:
        owned = state.get("owner_experience", empty_state())
        for decision in owned["decisions"]:
            if decision["share_with_ai"] and decision["status"] == "ACTIVE_STATEMENT":
                candidates["project_decisions"].append({
                    **deepcopy(decision), "run_id": state["run_id"],
                    "applies_to": "PROJECT" if decision["scope"] == "PROJECT" else "RECORDED_WORK_ONLY"})
        for row in cards(state, include_dismissed=True):
            selected = row["human_choice"]
            if not selected or not selected["latest_action"]["share_with_ai"]:
                continue
            candidates["ownership_choices"].append({
                "run_id": state["run_id"], "text": row["text"], "target": row["target"],
                "status": row["status"], "target_is_suggestion": row["target_is_suggestion"],
                "source_ref": selected["latest_action"]["source_ref"],
                "basis_item": row["reference"], "mastery": "NOT_ASSESSED",
                "authority": "LEARNING_PREFERENCE_NOT_EXECUTION_PERMISSION"})
        for note in owned["notes"]:
            if note["share_with_ai"]:
                candidates["shared_notes"].append({**deepcopy(note), "run_id": state["run_id"],
                                                   "authority": "REFERENCE_ONLY"})
    for section, rows in candidates.items():
        for row in rows:
            trial = {**sections, section: [*sections[section], row]}
            if len(sections[section]) >= 24 or len(canonical(trial).encode("utf-8")) > 24000:
                omitted[section] += 1
            else:
                sections[section].append(row)
    return {**sections, "omitted": omitted, "private_notes_included": False,
            "authority": "REFERENCE_ONLY", "human_mastery": "NOT_ASSESSED"}
