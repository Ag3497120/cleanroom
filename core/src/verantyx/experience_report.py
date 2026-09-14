"""Read-only, source-linked recap of recorded work; no new evaluation or rights.

The three status objects retain the last recorded kernel assessment. ``ok``
means the report was read successfully, including when work failed. Current
project rule records are separate from the run's historical rule assessment;
neither is a check of today's files, expiry, environment or authorization.
"""
from copy import deepcopy

from .adapters.proposal_validation import valid_id
from .assets import BOUNDARIES, COLLECTIONS, project_assets
from .domain.events import citation
from .errors import LedgerError
from .kernel.reducer import projection
from .learning import project_learning
from .storage.sqlite import EventStore


def _pick(value, fields):
    return {key: deepcopy(value[key]) for key in fields if key in value}


def _learning_summary(item):
    value = _pick(item, (
        "id", "concept", "concept_id", "why_now", "project_anchor", "source_ref",
        "source_refs", "origin", "owner_run", "recorded", "status", "cycle",
        "ownership_target", "target_is_suggestion", "target_ref", "minimum_model",
        "counterexample", "check", "system_capture", "submission_state",
        "submission_stages", "mastery_evidence",
    ))
    value.update(mastery_assessment="NOT_ASSESSED", authority_granted=False)
    value["submissions"] = [_pick(row, (
        "kind", "source_ref", "source_refs", "recorded_at", "cycle",
        "evidence_basis", "externally_verified",
    )) for row in item.get("evidence", [])]
    return value


def _next_action(asset):
    # asset-template dispatches only verification_template_from_asset. The
    # execution-template Python API is not an asset-reuse CLI command.
    family = asset["family"]
    available = family in ("VERIFICATION", "ORACLE")
    requires = list(asset["reuse_requires"])
    if available:
        requires.append("NEW_CLAIM_BINDING")
    if asset["contract_summary"].get("method") == "REPRODUCTION":
        requires.append("EXPLICIT_REPRODUCES_BINDING")
    if family != "VERIFICATION":
        requires.append("NEW_AUTHORIZATION")
    if family == "ORACLE":
        requires.extend(("CURRENT_EXECUTED_CANDIDATE", "CURRENT_PRECEDENT_BACKEND"))
    if not available:
        requires.append("EXPLICIT_EXECUTION_RECIPE_BINDINGS")
    return {
        "asset_id": asset["id"], "family": family,
        "owner_run": asset["owner_run"], "plan_id": asset["plan_id"],
        "source_refs": list(asset["source_refs"]), "contract_hash": asset["contract_hash"],
        "reusable_via_current_cli": available,
        "cli_command": "asset-template" if available else None,
        "cli_scope": "TEMPLATE_ONLY" if available else "NO_ASSET_REUSE_COMMAND",
        "template_api": asset["reusable_via"], "requires": list(dict.fromkeys(requires)),
        "ready_to_execute": False, "authority_granted": False,
        "current_preconditions": "NOT_CHECKED",
    }


def report(root, configuration, run_id, locale="ja"):
    """Return a JSON-serializable recap using one validated read-only snapshot.

    Raises the ordinary LedgerError (ARGUMENTS, RUN_NOT_FOUND, store integrity
    errors). No raw state, prompts, response bodies, target bytes, command input
    or learning submission text is included. Learning suggestions honor both
    recorded preferences and the current configuration, and remain voluntary.
    """
    if not valid_id(run_id) or type(locale) is not str or locale not in BOUNDARIES:
        raise LedgerError("ARGUMENTS")
    with EventStore(root, configuration["project"]["id"]) as store:
        snapshot = store.project_snapshot()
    recorded = next((row for row in snapshot["states"] if row["run_id"] == run_id), None)
    if recorded is None:
        raise LedgerError("RUN_NOT_FOUND")
    state = projection(recorded)["state"]
    events = [row for row in snapshot["events"] if row["stream_id"] == run_id]
    evaluation = next((row for row in reversed(events) if row["type"] == "EvaluationRecorded"), None)
    assessment = state["assessment"] or {}
    basis = {
        "source_refs": [citation(evaluation)] if evaluation and assessment else [],
        "assessed_at": state["evaluated_at"], "historical": True,
        "current_preconditions": "NOT_CHECKED",
    }
    assets = project_assets(state, locale)
    methods = [*assets["verification_methods"], *assets["execution_methods"]]
    outcomes = deepcopy(list(state.get("asset_outcomes", {}).values()))
    claims = [_pick(row, (
        "id", "source_refs", "status", "source_status", "reason", "verification",
        "closure", "epistemic_status", "blocker", "verification_reason",
        "property_evidence", "prose_entailment", "evidence_scope",
    )) for row in assessment.get("claims", [])]
    for claim, original in zip(claims, assessment.get("claims", [])):
        claim["recorded_evidence"] = [_pick(row, (
            "verification_id", "source_ref", "property", "method", "status",
            "origins", "target", "expires_at", "reason",
        )) | {"current_at_recorded_assessment": row["current"]}
            for row in original.get("evidence", [])]

    executions, changes, canonical_changes = [], [], []
    for asset in methods:
        if asset["family"] in ("VERIFICATION", "ORACLE"):
            continue
        item = state[COLLECTIONS[asset["family"]]][asset["plan_id"]]
        row = _pick(asset, ("family", "plan_id", "status", "target", "source_refs", "latest_outcome"))
        row.update(asset_id=asset["id"], current_preconditions="NOT_CHECKED")
        row.update(_pick(item, ("authorization_ref", "started_ref", "receipt_ref", "invalidated_ref",
                                "reason", "verification_annotation")))
        executions.append(row)
        receipt = item.get("receipt")
        if receipt and asset["family"] == "WORKTREE":
            changes.append({"asset_id": asset["id"], "receipt_ref": item["receipt_ref"],
                            **_pick(receipt, ("lease_id", "outcome", "worktree", "applied", "reason"))})
        if receipt and asset["family"] in ("ADOPTION", "INTEGRATION"):
            canonical_changes.append({"asset_id": asset["id"], "receipt_ref": item["receipt_ref"],
                                      **_pick(receipt, ("outcome", "target_ref", "base_version", "commit",
                                                       "execution_ref", "reason", "recovered"))})

    workflows, reused_asset_refs = [], []
    for identity, item in state.get("asset_workflows", {}).items():
        plan = item["plan"]
        row = {"id": identity, **_pick(item, ("status", "source_ref", "finished_ref", "results")),
               "unresolved": deepcopy(plan["document"]["unresolved"]),
               "rejected": deepcopy(plan["rejected"]), "steps": []}
        for step in plan["steps"]:
            row["steps"].append(_pick(step, (
                "id", "mode", "asset_id", "source_refs", "spec_sha256",
                "expectation_origin", "independence", "prose_entailment",
            )))
            if step["asset_id"]:
                reused_asset_refs.append({"asset_id": step["asset_id"], "mode": step["mode"],
                                          "source_refs": list(step["source_refs"])})
        workflows.append(row)

    judgments = []
    for event in events:
        if event["type"] == "HumanDecisionRecorded":
            payload, ref = event["payload"], citation(event)
            latest = state["human_decisions"][payload["point_id"]]
            judgments.append({**deepcopy(payload), "source_ref": ref,
                              "recorded_at": event["recorded_at"], "revision": event["revision"],
                              "is_latest_recorded": latest["source_ref"] == ref,
                              "current_applicability": "NOT_CHECKED", "authority_granted": False})
    learning = project_learning(state, include_suggestions=False)
    choices = []
    for item in learning:
        if not item["target_is_suggestion"]:
            row = _learning_summary(item)
            row["target_history"] = [
                {**_pick(event, ("type", "source_ref", "recorded_at", "revision")),
                 **_pick(event["payload"], ("target", "reason"))}
                for event in item["history"] if event["type"] == "LearningTargetSelected"]
            choices.append(row)
    recorded_preferences = state["learning_preferences"]
    current_preferences = configuration["learning"]
    suggestions = []
    if recorded_preferences["mode"] != "off" and current_preferences["mode"] != "off":
        limit = min(recorded_preferences["max_items"], current_preferences["max_items"])
        candidates = project_learning({**state, "locale": locale}, include_deferred=False)
        suggestions = [_learning_summary(row) for row in candidates if row["target_is_suggestion"]][:limit]

    referenced_rules = {row["id"] for row in (state["policy_context"] or {}).get("rules", [])}
    current_rules = [_pick(row, (
        "id", "owner_run", "state", "scope", "scope_policy", "choice", "reason",
        "human_ref", "precedent_ref", "review_after", "origin_ref", "history",
        "contested", "counterexamples", "maturity", "enforcement", "validity",
        "evidence_refs", "exceptions", "successor", "supersedes",
    )) for row in snapshot["rules"].values()
        if row["owner_run"] == run_id or row["id"] in referenced_rules]
    # Outside-AI quotes are references, not recorded execution failures. Keep
    # their hash and attributed provenance without repeating arbitrary bodies.
    references = [_pick(row, (
        "id", "kind", "owner_run", "provenance", "body_sha256", "source_refs",
        "origin", "verification", "enforcement", "authority", "executed",
    )) for row in assets["reuse_candidates"] if row["kind"] == "EXTERNAL_CAPTURE"]
    model_candidates = [_pick(row, (
        "id", "kind", "candidate_kind", "owner_run", "locale", "title", "source_refs",
        "mode", "evidence_role", "document_sha256", "basis_revision", "recorded_revision",
        "origin", "verification", "enforcement", "authority", "prose_entailment",
        "reusable_via", "executed", "reuse_requires",
    )) for row in assets["reuse_candidates"] if row["kind"] == "MODEL_CANDIDATE"]
    return {
        "schema_version": 1, "ok": True, "command": "recap", "run_id": run_id,
        "revision": state["revision"], "project_revision": snapshot["project_revision"],
        "locale": locale, "trust": state["trust"], "writes": False, "model_called": False,
        "build": {"status": assessment.get("build", "UNKNOWN"), **deepcopy(basis)},
        "evidence": {"status": assessment.get("evidence", "UNKNOWN"), **deepcopy(basis),
                     "claims": claims, "recorded_outcomes": outcomes,
                     "scope": "RECORDED_METHOD_CONTRACTS_AND_THEIR_FIXED_TARGETS_ONLY",
                     "prose_entailment": "NOT_ASSESSED", "independence": "NOT_ESTABLISHED"},
        "ownership": {"status": assessment.get("ownership", "UNASSESSED"), **deepcopy(basis),
                      "mastery_assessment": "NOT_ASSESSED", "authority_granted": False},
        "project_delta": {
            "request_ref": state["request_ref"], "proposal_ref": state["proposal_ref"],
            "observations": [{"source_ref": ref, **_pick(state["observations"][ref], (
                "path", "status", "sha256", "size", "observed_at", "expires_at", "reason",
            ))} for ref in state["latest_observations"].values()],
            "candidate_changes": changes, "canonical_changes": canonical_changes,
            "execution_records": executions, "workflows": workflows,
            "unresolved": deepcopy(assessment.get("gaps", [])),
            "historical": True, "current_preconditions": "NOT_CHECKED",
        },
        "system_delta": {
            "verification_assets": assets["verification_methods"],
            "execution_assets": assets["execution_methods"], "failure_assets": assets["failure_cases"],
            "model_candidates": model_candidates, "external_references": references,
            "rule_event_refs": list(state["rule_event_refs"]),
            "reused_rules": [deepcopy(row) for row in assessment.get("judgments", [])
                             if row["status"] == "PRECEDENT_MATCHED"],
            "current_rules": current_rules, "reused_asset_refs": reused_asset_refs,
            "current_rules_basis": "PROJECT_LEDGER_SNAPSHOT", "authority_granted": False,
        },
        "human_delta": {
            "judgments": judgments, "ownership_choices": choices, "suggestions": suggestions,
            "preferences": {"recorded": deepcopy(recorded_preferences), "current": deepcopy(current_preferences)},
            "mastery_assessment": "NOT_ASSESSED", "authority_granted": False,
        },
        "next_actions": [_next_action(asset) for asset in methods],
        "boundaries": {
            "message": BOUNDARIES[locale], "read_only": True,
            "assessment_basis": "LAST_RECORDED_EVALUATION", "current_preconditions": "NOT_CHECKED",
            "stages": ["PROPOSAL", "AUTHORIZATION", "EXECUTION", "VERIFICATION", "ADOPTION"],
            "stages_are_distinct": True, "finite_tests_are_general_proof": False,
            "ownership_is_system_retention": False, "delegation_is_understanding": False,
            "delegation_grants_authority": False, "learning_is_optional": True,
        },
    }
