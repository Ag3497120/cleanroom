"""Many interpretations of one recorded experience; never a consensus gate."""
from copy import deepcopy
from . import owner_experience
from .domain.codec import digest
from .work_checks import projection as check_projection


def perspectives(state):
    rows = []
    for reflection in state.get("work_reflections", []):
        items = (reflection.get("proposal") or {}).get("owner_items", [])
        rows.append({
            "id": reflection["id"], "status": reflection["status"], "model": deepcopy(reflection["model"]),
            "perspective": reflection.get("perspective", ""),
            "generation_id": reflection.get("generation_id"),
            "recorded_at": reflection["recorded_at"], "source_ref": reflection["source_ref"],
            "trace_sha256": reflection["trace_sha256"],
            "source_event_ids": deepcopy(reflection["source_event_ids"]),
            "failure_code": reflection["failure_code"], "owner_items": deepcopy(items),
            "content_sha256": digest(reflection.get("proposal")),
            "authority": "PROPOSAL_ONLY",
        })
    return rows


def notebook(root, configuration, run_id=None):
    states = owner_experience.read_states(root, configuration)
    if run_id is not None:
        states = [state for state in states if state["run_id"] == run_id]
    document = owner_experience.project(states, configuration)
    document["perspectives"] = [{"run_id": state["run_id"], "request": state["request"],
                                "revisions": perspectives(state)} for state in states if state.get("work_result")]
    document["check_receipts"] = [{"run_id": state["run_id"], **row}
                                 for state in states for row in check_projection(state)]
    document["all_perspective_cards"] = [card for state in states
                                       for card in owner_experience.cards(state, include_archived=True)]
    document["interpretation_policy"] = "DIVERSITY_ALLOWED_NO_AGREEMENT_REQUIRED"
    document["contains_local_owner_records"] = True
    document["boundary"] = ("Local notebook, potentially private. Reading does not send it to a model, "
                            "certify understanding, authorize execution or activate a rule.")
    return {"schema_version": 1, "ok": True, "command": "notebook", **document}
