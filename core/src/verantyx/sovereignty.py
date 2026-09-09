"""Measured local experience inventory, with unavailable metrics left unknown."""
from collections import Counter

from .assets import project_assets
from .asset_workflow import EXPLICIT_REUSE_IDENTITY
from .storage.sqlite import EventStore


def report(root, configuration):
    with EventStore(root, configuration["project"]["id"]) as store:
        snapshot = store.project_snapshot()
        revision = snapshot["project_revision"]
        events = snapshot["events"]
        if store.project_revision() != revision:
            from .errors import LedgerError
            raise LedgerError("REVISION_CONFLICT")
    states, rules = snapshot["states"], snapshot["rules"]
    metrics = dict.fromkeys(("tasks", "human_decisions", "active_rules", "reused_decisions", "verification_methods",
                            "executed_checks", "reused_checks", "model_free_reuses", "retained_failures", "learning_candidates"), 0)
    metrics["tasks"] = len(states)
    metrics["human_decisions"] = sum(event["type"] == "HumanDecisionRecorded" for event in events)
    metrics["active_rules"] = sum(row["validity"] == "CURRENT" and row["enforcement"] in ("WARN", "BLOCK")
                                  and not row["contested"] and row["review_after"] > (snapshot["as_of"] or "")
                                  for row in rules.values())
    choices, concepts, tasks = Counter(), {}, []
    from .learning import project_learning
    for state in states:
        assets = project_assets(state)
        metrics["verification_methods"] += len(assets["verification_methods"])
        metrics["retained_failures"] += len(assets["failure_cases"])
        metrics["learning_candidates"] += len(state["learning_candidates"])
        reused = [row for row in (state.get("assessment") or {}).get("judgments", []) if row["status"] == "PRECEDENT_MATCHED"]
        metrics["reused_decisions"] += len(reused)
        for row in state.get("asset_outcomes", {}).values():
            if row["family"] in ("VERIFICATION", "ORACLE", "WORKTREE") and row.get("closure") is not None:
                metrics["executed_checks"] += 1
        for workflow in state.get("asset_workflows", {}).values():
            plan = workflow["plan"]
            results = {row["step_id"]: row for row in workflow.get("results", [])}
            for step in plan["steps"]:
                if step["mode"] == "REUSE" and results.get(step["id"], {}).get("status") == "COMPLETED":
                    metrics["reused_checks"] += 1
                    metrics["model_free_reuses"] += plan["context"]["adapter_identity"] == EXPLICIT_REUSE_IDENTITY
        for item in project_learning(state, include_deferred=True):
            if item["id"] not in state["learning_candidates"]:
                continue
            if not item["target_is_suggestion"]:
                choices[item["ownership_target"]] += 1
            concept = concepts.setdefault(item["concept_id"], {"concept_id": item["concept_id"], "occurrences": []})
            concept["occurrences"].append({"run_id": state["run_id"], "candidate_id": item["id"],
                                           "concept": item["concept"], "source_refs": item["source_refs"],
                                           "target": item["ownership_target"], "suggested": item["target_is_suggestion"],
                                           "mastery": item["mastery_assessment"]})
        tasks.append({"run_id": state["run_id"], "revision": state["revision"], "reused_decisions": reused,
                      "verification_assets": [row["id"] for row in assets["verification_methods"]],
                      "failure_assets": [row["id"] for row in assets["failure_cases"]]})
    return {"schema_version": 1, "ok": True, "command": "sovereignty", "project_revision": revision,
            "metrics": metrics, "human_selected_targets": {key: choices[key] for key in ("OWN", "REVIEW", "REFERENCE", "DELEGATE")},
            "concepts": list(concepts.values()), "tasks": tasks,
            "scope": "LOCAL_RECORDED_EVENTS; current rule assessment uses last recorded time; concept groups use exact IDs only",
            "unmeasured": {"token_savings": None, "cloud_call_reduction": None, "human_mastery": None,
                           "arbitrary_model_equivalence": None, "unknown_bypasses_outside_gateway": None},
            "authority_granted": False}
