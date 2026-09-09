"""Share recorded value choices with both generators, without granting effects."""
from copy import deepcopy

from .domain.codec import digest
from .errors import LedgerError

FORMAT = "verantyx.decision-context.v1"


def snapshot(state, as_of=None):
    """Pure, scoped projection of effective choices at a recorded time."""
    from .kernel.rules import evaluate_decisions
    as_of = as_of or state.get("evaluated_at") or state.get("assessment_as_of")
    if as_of is None:
        as_of = ((state.get("handoff_plan") or {}).get("decision_context") or {}).get("as_of")
    judgments, _ = evaluate_decisions({**state, "assessment_as_of": as_of})
    by_id = {row["point_id"]: row for row in judgments}
    rows = []
    for point in (state.get("proposal") or {}).get("decision_points", []):
        if point["kind"] != "VALUE_DECISION":
            continue
        judgment = by_id[point["id"]]
        resolved = judgment["status"] in ("HUMAN_DECIDED", "PRECEDENT_MATCHED")
        selected = next((choice for choice in point["options"] if resolved and choice["id"] == judgment["choice"]), None)
        human = state["human_decisions"].get(point["id"]) if judgment["status"] == "HUMAN_DECIDED" else None
        rows.append({"point": deepcopy(point), "status": judgment["status"],
                     "selected_option": deepcopy(selected), "reason": human["reason"] if human else None,
                     "source_refs": list(judgment["rule_refs"]) if resolved else [],
                     "blocker_reason": judgment.get("reason"), "scope": deepcopy(judgment.get("scope"))})
    value = {"format": FORMAT, "project_id": state["project_id"], "run_id": state["run_id"],
             "scope": deepcopy(state["context"]), "as_of": as_of, "items": rows,
             "execution_authorized": False, "code_conformance": "UNPROVEN"}
    value["sha256"] = digest(value)
    return value


def require_current(state, isolation_point, as_of=None):
    """An edit generated before a value choice must be regenerated with it.

    The action's worktree-isolation choice is an execution prerequisite, not a
    code-generation choice. It remains enforced separately by the effect gate.
    Legacy plans carry no decision snapshot; retain their historical semantics.
    """
    from .external_capture import require_handoff_current
    require_handoff_current(state)
    recorded = (state.get("handoff_plan") or {}).get("decision_context")
    if recorded is None:
        return
    current = snapshot(state, as_of)
    def relevant(value):
        return {row["point"]["id"]: row for row in value["items"] if row["point"]["id"] != isolation_point}
    if relevant(recorded) != relevant(current):
        raise LedgerError("EDITOR_DECISION_CHANGED")


def change_reason(state):
    """Why the visible writer candidate needs refreshed model input."""
    for action in (state.get("proposal") or {}).get("actions", []):
        if action["tool_id"] == "writer.apply":
            try:
                require_current(state, action["arguments"].get("point_id"))
            except LedgerError as error:
                if error.code in ("EDITOR_DECISION_CHANGED", "EDITOR_REFERENCE_CHANGED"):
                    return error.code
                raise
    return None


def changed(state):
    return change_reason(state) is not None


def handoff_status(state):
    from .shared_context import current_editor_attempt
    attempt = current_editor_attempt(state)
    reason = change_reason(state)
    if reason:
        return reason
    return attempt["validation"]["status"] if attempt else "AWAITING_EDITOR"


INPUT_CONTRACT = (
    " decision_context is a host-provided snapshot of this task's recorded value choices. "
    "Use selected_option only for HUMAN_DECIDED or PRECEDENT_MATCHED, preserving the choice, "
    "its reason, scope and source_refs. These are preferences, not proof, test success or permission. "
    "Unresolved or conflicting entries have no selected option: never choose for the person. "
    "Use the recorded choices when interpreting the request and proposing code; if they conflict "
    "with an original constraint, keep the disagreement explicit rather than silently replacing either."
)
