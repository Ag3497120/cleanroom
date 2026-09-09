"""Evaluate recorded observations. Sourced prose is never verified truth."""
from .rules import classify_gap, evaluate_decisions, epistemic_axes
from ..domain.verification import assess_claim


def _source_status(state, refs, as_of):
    if not refs:
        return "UNKNOWN", "MISSING_SOURCE"
    for ref in refs:
        observation = state["observations"].get(ref)
        if observation is None:
            return "UNKNOWN", "UNKNOWN_SOURCE"
        if observation["status"] != "OBSERVED":
            return "UNKNOWN", "UNAVAILABLE_SOURCE"
        if not observation["observed_at"] <= as_of < observation["expires_at"]:
            return "UNKNOWN", "STALE_SOURCE"
        current = state["observations"][state["latest_observations"][observation["path"]]]
        if current["status"] != "OBSERVED" or current["sha256"] != observation["sha256"]:
            return "UNKNOWN", "SOURCE_CHANGED"
        if not current["observed_at"] <= as_of < current["expires_at"]:
            return "UNKNOWN", "STALE_SOURCE"
    return "SOURCED", None


def evaluate(state, as_of, *, _editor_check=None):
    proposal = state["proposal"]
    result = {"strategy": "UNKNOWN", "build": "IN_PROGRESS", "evidence": "UNKNOWN",
              "ownership": "UNASSESSED", "claims": [], "actions": [], "gaps": [], "question": None, "judgments": [],
              "ownership_target": None, "mastery_evidence": "NONE", "system_capture": []}
    if proposal is None:
        result["gaps"].append({"code": "NO_PROPOSAL", "classification": "UNKNOWN_EVIDENCE", "source_ref": state["request_ref"], **epistemic_axes("NO_PROPOSAL")})
        return result
    judgments, judgment_gaps = evaluate_decisions({**state, "assessment_as_of": as_of})
    for claim in proposal["claims"]:
        status, reason = _source_status(state, claim["source_refs"], as_of)
        verified = assess_claim(state, claim, as_of)
        assessment = {**claim, "status": status, "reason": reason, "verification": "UNVERIFIED"}
        if verified is not None:
            assessment.update(verified)
            reason = verified["verification_reason"]
            assessment.update(status=verified["epistemic_status"], reason=reason, source_status=status)
        result["claims"].append(assessment)
        if verified is None or reason:
            result["gaps"].append({"code": reason or "CLAIM_NOT_VERIFIED", "item_id": claim["id"],
                                   "source_ref": state["proposal_ref"]})
    if result["claims"]:
        statuses = {claim.get("epistemic_status", "UNKNOWN") for claim in result["claims"]}
        if "CONTESTED" in statuses:
            result["evidence"] = "CONTESTED"
        elif "REFUTED" in statuses:
            result["evidence"] = "REFUTED"
        elif statuses == {"SUPPORTED"}:
            result["evidence"] = "BOUNDED"
    for action in proposal["actions"]:
        status, reason = _source_status(state, action["source_refs"], as_of)
        assessment = {**action, "gate": "NEED_EVIDENCE", "reason": reason,
                      "observation_ref": None, "effect_executed": False}
        # Only this exact metadata query is registered in M1.
        if action["tool_id"] in ("worktree.prepare", "writer.apply"):
            from ..domain.effects import plan_for, editor_binding
            from ..errors import LedgerError
            try:
                plan_for(action)
                dependencies = _editor_check(state, action) if _editor_check else editor_binding(state, action, as_of=as_of)
                if _editor_check is None and state.get("handoff_plan") and action["tool_id"] == "writer.apply":
                    statuses = {item["point_id"]: item["status"] for item in judgments}
                    pending = [point for point in dependencies if statuses.get(point) not in ("HUMAN_DECIDED", "PRECEDENT_MATCHED")]
                    assessment.update(decision_dependencies=dependencies, unresolved_decision_dependencies=pending,
                                      dependency_source_ref=state["handoff_plan"]["source_proposal_ref"])
                assessment.update(gate="NEED_AUTHORITY", reason="AUTHORITY_REQUIRED")
                from ..domain.codec import digest
                current = [item for item in state["effects"].values() if item["lease"]["action_id"] == action["id"]
                           and item["lease"]["proposal_hash"] == digest(proposal)]
                if current:
                    item = current[-1]
                    if item["status"] in ("PREPARED", "CANDIDATE_TESTED"):
                        assessment.update(gate=item["status"], reason=None, effect_executed=True,
                                          receipt_ref=item["receipt_ref"])
                        if item["status"] == "CANDIDATE_TESTED":
                            from ..domain.effects import unittest_closure
                            closure = unittest_closure(item["receipt"]["verification"]["result"])
                            if closure == "REFUTED":
                                assessment.update(gate="CANDIDATE_REFUTED", reason="CANDIDATE_TEST_FAILED")
                            elif closure != "BOUNDED":
                                assessment.update(gate="CANDIDATE_UNVERIFIED", reason="CANDIDATE_TEST_INCOMPLETE")
                    elif item["status"] == "OUTCOME_UNKNOWN":
                        assessment.update(gate="UNKNOWN", reason="EXECUTION_OUTCOME_UNKNOWN")
                    elif item["status"] == "INVALIDATED":
                        assessment.update(gate="DENY", reason="AUTHORIZATION_STALE")
                    elif item["status"] == "AUTHORIZED" and as_of < item["lease"]["expires_at"]:
                        assessment.update(gate="AUTHORIZED", reason=None)
                if assessment.get("unresolved_decision_dependencies"):
                    assessment.update(gate="NEED_DECISION", reason="EDITOR_DECISION_REQUIRED")

            except LedgerError as error:
                assessment.update(gate="DENY", reason=error.code)
        elif action["tool_id"] != "file.observe":
            assessment.update(gate="DENY", reason="TOOL_UNAVAILABLE")
        elif set(action["arguments"]) != {"path"} or type(action["arguments"]["path"]) is not str:
            assessment.update(gate="DENY", reason="TOOL_ARGUMENTS_INVALID")
        elif action["arguments"]["path"] not in state["read_scope"]:
            assessment.update(gate="NEED_DECISION", reason="READ_SCOPE_NOT_GRANTED")
        elif status == "SOURCED":
            path = action["arguments"]["path"]
            ref = state["latest_observations"].get(path)
            if ref and any(state["observations"][source]["path"] == path for source in action["source_refs"]):
                current = state["observations"][ref]
                if current["status"] == "OBSERVED" and current["observed_at"] <= as_of < current["expires_at"]:
                    assessment.update(gate="OBSERVATION_AVAILABLE", reason=None, observation_ref=ref)
                else:
                    assessment["reason"] = "STALE_SOURCE"
            else:
                assessment["reason"] = "SOURCE_TARGET_MISMATCH"
        result["actions"].append(assessment)
        if assessment["reason"]:
            result["gaps"].append({"code": assessment["reason"], "item_id": action["id"],
                                   "source_ref": state["proposal_ref"]})
    for unknown in proposal["unknowns"]:
        result["gaps"].append({"code": "MODEL_UNKNOWN", "item_id": unknown["id"],
                              "question": unknown["question"], "needed_observation": unknown["needed_observation"],
                              "source_ref": state["proposal_ref"]})
    decisions = [a for a in result["actions"] if a["gate"] == "NEED_DECISION" and a["reason"] == "READ_SCOPE_NOT_GRANTED"]
    if decisions:
        action = decisions[0]
        result["strategy"] = "ASK_ONE_DECISION"
        result["question"] = {"code": "READ_SCOPE_NOT_GRANTED", "item_id": action["id"],
                              "path": action["arguments"]["path"], "reason": "NOT_DELEGATED",
                              "source_ref": state["proposal_ref"],
                              "choices": ["OBSERVE_EXPLICITLY", "KEEP_UNGRANTED"]}
    elif not result["gaps"] and result["actions"]:
        # Every requested metadata query is answered by a host observation.
        # This is not permission to execute a command, nor proof of the prose task.
        result["strategy"] = "EXECUTE"
    if not proposal["claims"] and not proposal["actions"] and not proposal["unknowns"]:
        if not proposal.get("decision_points"):
            result["gaps"].append({"code": "EMPTY_PROPOSAL", "source_ref": state["proposal_ref"]})
    result["judgments"] = judgments
    result["gaps"].extend(judgment_gaps)
    for gap in result["gaps"]:
        gap["classification"] = classify_gap(gap["code"])
        gap.update(epistemic_axes(gap["code"]))
        if gap["code"] == "VERIFICATION_CONFLICT":
            gap.update(classification="CONTESTED", epistemic_status="CONTESTED", blocker="NONE")
        elif gap["code"] in ("PROPERTY_REFUTED", "CANDIDATE_TEST_FAILED"):
            gap.update(classification="REFUTED", epistemic_status="REFUTED", blocker="NONE")
    human_points = [j for j in judgments if j["kind"] == "VALUE_DECISION" and j["status"] in ("UNDECIDED_HUMAN", "UNSCOPED_RULE")]
    if any(gap["classification"] == "CONTESTED" for gap in result["gaps"]):
        result["strategy"], result["question"] = "UNKNOWN", None
    elif human_points:
        point = human_points[0]
        result["strategy"] = "ASK_ONE_DECISION"
        result["question"] = {"code": "VALUE_DECISION_REQUIRED", "point_id": point["point_id"],
                              "question": point["question"], "kind": "VALUE_DECISION", "source_ref": state["proposal_ref"]}
    elif not result["gaps"] and (result["actions"] or judgments):
        result["strategy"] = "EXECUTE"
    return result
