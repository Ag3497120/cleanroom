"""Close a bounded artifact job through existing ledger, checks and learning."""
from copy import deepcopy
import hashlib
from pathlib import Path

from .adapters.invocation_journal import InvocationJournal
from .adapters.proposal_validation import validate_proposal
from .domain.codec import canonical, digest
from .errors import LedgerError
from .personal_skills import read_state
from .recovery_bundle import _write_files, save_recovery


def judge_target(root, configuration, parent_run, contract, *, key, reason,
                 target=None, ownership=None, ownership_reason=None):
    from .application import record_run
    from .learning import control_learning
    from .verification import plan_verification, run_verification, _read_input
    from .assets import project_assets
    from .adapters.observations import normalize_path
    from .authority import require_current_approval_valid
    target = normalize_path(target or contract["target"])
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 4000:
        raise LedgerError("ARGUMENTS", {"reason": "EXPLICIT_REASON_REQUIRED"})
    if ownership is not None and (ownership not in ("OWN", "REVIEW", "REFERENCE", "DELEGATE")
                                  or not ownership_reason or not ownership_reason.strip()):
        raise LedgerError("ARGUMENTS", {"reason": "OWNERSHIP_REASON_REQUIRED"})
    if ownership is None and ownership_reason is not None:
        raise LedgerError("ARGUMENTS", {"reason": "UNUSED_OWNERSHIP_REASON"})
    read_state(root, configuration, parent_run)
    intent = {"parent_run": parent_run, "contract": contract, "target": target,
              "reason": reason, "ownership": ownership, "ownership_reason": ownership_reason}
    with InvocationJournal(root, "explicit-judgment", key) as journal:
        started = journal.read("started")
        if started and started["intent_hash"] != digest(intent):
            raise LedgerError("IDEMPOTENCY_CONFLICT")
        finished = journal.read("finished")
        if finished:
            return {**finished, "duplicate": True, "historical_receipt": True,
                    "new_verifier_executions": 0}
        require_current_approval_valid()
        if started is None:
            started = {"intent_hash": digest(intent),
                       "target_sha256": hashlib.sha256(_read_input(root, target)).hexdigest(),
                       "run_id": "judgment-" + digest({"parent": parent_run, "key": key})[:32]}
            journal.write("started", started)
        if hashlib.sha256(_read_input(root, target)).hexdigest() != started["target_sha256"]:
            raise LedgerError("VERIFICATION_TARGET_CHANGED")
        run_id = started["run_id"]
        parts = ("vera-judgments", run_id, digest(intent))
        relative = "/".join(parts)
        source = relative + "/expectations.json"
        _write_files(root, parts, {
            "expectations.json": (canonical({"parent_run": parent_run, "reason": reason,
                                            "contract": contract}) + "\n").encode("utf-8")})
        base = record_run(root, configuration, run_id=run_id,
                          request="Check the explicit conditions linked to work " + parent_run + ". " + reason,
                          observe_paths=[target, source], locale="ja", key="judgment-run-" + journal.prefix)
        proposal = {
            "schema_version": 1, "task_id": run_id, "context_revision": base["recorded_revision"],
            "response_locale": "ja", "summary": "Explicit local predicates, not a claim of general correctness.",
            "claims": [{"id": "explicit-contract", "statement": contract["spec"]["property"],
                        "source_refs": [base["state"]["request_ref"]]}],
            "actions": [], "unknowns": [], "decision_points": [],
        }
        validate_proposal(proposal)
        _write_files(root, parts, {"proposal.json": (canonical(proposal) + "\n").encode("utf-8")})
        proposed = record_run(root, configuration, run_id=run_id, resume=True,
                              proposal_path=Path(root) / relative / "proposal.json",
                              key="judgment-proposal-" + journal.prefix,
                              expected_revision=base["recorded_revision"])
        spec = deepcopy(contract["spec"])
        spec["target_path"] = target
        spec["oracle"]["source_refs"] = [proposed["state"]["latest_observations"][source]]
        plan = plan_verification(root, configuration, run_id, spec,
                                 "judgment-plan-" + journal.prefix,
                                 expected_revision=proposed["recorded_revision"])
        require_current_approval_valid()
        checked = run_verification(root, configuration, run_id, plan["verification_id"],
                                   "judgment-execute-" + journal.prefix)
        outcome = (checked["verification"].get("receipt") or {}).get("result")
        closure = (outcome or {}).get("closure", "UNKNOWN")
        anchor = checked["verification"].get("receipt_ref", checked["verification"]["source_ref"])
        candidate = "conditions-" + digest({"run": run_id, "contract": contract})[:32]
        learned = control_learning(
            root, configuration, run_id, "raise", candidate_id=candidate,
            key="judgment-learning-" + journal.prefix, expected_revision=checked["recorded_revision"],
            concept="明示した検証条件と、まだ証明されていない範囲を分ける",
            concept_id="explicit-predicate-boundary",
            why_now=["外部AIの成果物を、生成後の印象ではなく先に定めた条件で検査したため。"],
            minimum_model="今回固定した条件: " + "; ".join(contract["expressions"])
                          + "。成立するのはこの条件だけで、実装全体や本人の習熟を証明しない。",
            counterexample="一つの値の一致だけで、通信や再試行などプログラム全体も正しいと決めてしまう。",
            check="条件を満たす入力と満たさない入力を挙げ、この検査が判定できない振る舞いを説明する。",
            source_refs=[anchor, checked["state"]["request_ref"]])
        if ownership is not None:
            learned = control_learning(
                root, configuration, run_id, "target", candidate_id=candidate,
                target=ownership, reason=ownership_reason,
                key="judgment-ownership-" + journal.prefix,
                expected_revision=learned["recorded_revision"])
        state = learned["state"]
        methods = project_assets(state, "ja")["verification_methods"]
        status = "COMPLETE_BOUNDED" if closure == "BOUNDED" else "REFUTED" if closure == "REFUTED" else "INCOMPLETE"
        # A navigational reference, not another assertion of success or authority.
        # Keep this on the existing event ledger so later CLI sessions can find
        # a check performed after the original generation receipt was saved.
        from .external_capture import capture
        from .personal_skills import SOURCE_FORMAT
        capture(root, configuration, run_id, body=canonical({
            "format": "verantyx.work-check-link.v1", "parent_run": parent_run,
            "verification_id": plan["verification_id"], "source_ref": anchor,
            "target_sha256": started["target_sha256"],
        }), provider="verantyx", model="none", key="judgment-link-" + journal.prefix,
            expected_revision=learned["recorded_revision"], content_format="json", locale="ja",
            source_label=canonical({
                "format": SOURCE_FORMAT, "origin_project": configuration["project"]["id"],
                "label": "条件検査: " + contract["target"][:80],
                "development": {"kind": "FINITE_JUDGMENT", "parent_run": parent_run,
                                "verification_id": plan["verification_id"]},
            }))
        result = {
            "status": status,
            "parent_run": parent_run, "run_id": run_id, "target": target,
            "target_sha256": started["target_sha256"], "closure": closure,
            "verification_id": plan["verification_id"], "source_ref": anchor,
            "asset_id": next(row["id"] for row in methods if row["plan_id"] == plan["verification_id"]),
            "learning_candidate": candidate, "ownership": ownership or "REVIEW_SUGGESTED",
            "model_calls": 0, "new_verifier_executions": 1, "duplicate": False,
            "recovery_bundle": save_recovery(root, configuration, run_id),
            "canonical_code_adopted": False, "human_mastery": "NOT_ASSESSED",
        }
        journal.write("finished", result)
        return result


def delivery_authorization(state, *, allow_contested_handoff=False):
    """Authorize only a bounded inspection, never change the recorded verdict."""
    attempt = state.get("editor_attempt") or {}
    validation = attempt.get("validation") or {}
    status = validation.get("status", "NOT_RECORDED")
    verdict = {
        "policy": "scoped-delivery.v2", "allowed": status == "MATCHED",
        "status": status, "mismatch_ids": deepcopy(validation.get("mismatch_ids") or []),
        "semantic_fidelity": "UNPROVEN", "canonical_adoption_authorized": False,
        "allow_contested_handoff": bool(allow_contested_handoff),
        "validation_sha256": digest(validation),
        "scope": "EXPLICIT_FINITE_PREDICATES_ONLY",
        "reason": "RECORDED_MATCH" if status == "MATCHED" else "HANDOFF_REPAIR_REQUIRED",
    }
    if status == "MATCHED" or not allow_contested_handoff:
        return verdict
    if status != "REPAIR_REQUIRED" or validation.get("mode") != "CROSS_VM" or validation.get("fallback_reason"):
        return verdict
    packet = state.get("shared_context") or {}
    plan = (state.get("handoff_plan") or {}).get("plan") or {}
    document = attempt.get("document") or {}
    # A recorded VM label alone cannot authorize this exception. Reconstruct
    # the original finite checks without modifying or rerunning either model.
    try:
        from .coordination import comparison_inputs
        if (not plan.get("interpretations") or not plan.get("cases")
                or document.get("context_sha256") != packet.get("sha256")
                or document.get("plan_sha256") != digest(plan)):
            return verdict
        checks = comparison_inputs(packet, plan, document)["checks"]
        mismatches = [row["id"] for row in checks if row["expected"] != row["actual"]]
        alternative_ids = {node["id"] + ":alternatives" for node in plan["interpretations"]}
        if (not mismatches or sorted(mismatches) != sorted(verdict["mismatch_ids"])
                or not set(mismatches).issubset(alternative_ids)):
            return verdict
    except (KeyError, TypeError, ValueError):
        return verdict
    return {**verdict, "allowed": True, "reason": "ALTERNATIVES_DISAGREEMENT_RETAINED",
            "context_sha256": packet["sha256"], "plan_sha256": digest(plan),
            "editor_sha256": digest(document)}


def deliver_artifact(root, configuration, result, contract, *, key, reason,
                     allow_contested_handoff=False):
    handoff = delivery_authorization(result["state"], allow_contested_handoff=allow_contested_handoff)
    if not handoff["allowed"]:
        return {"status": "BLOCKED", "reason": handoff["reason"], "handoff": handoff, "model_calls": 0}
    attempt = result["state"].get("editor_attempt") or {}
    document = attempt.get("document") or {}
    files = document.get("files") or {}
    if set(files) != {contract["target"]}:
        return {"status": "BLOCKED", "reason": "DELIVERY_REQUIRES_ONE_EXPLICIT_TARGET", "model_calls": 0}
    target = contract["target"]
    body = files[target].encode("utf-8")
    if len(body) > 65536:
        raise LedgerError("VERIFICATION_INPUT_LIMIT")
    # No arbitrary code is run. The caller explicitly requested delivery to a new
    # immutable directory, never adoption over the original project files.
    from .authority import require_current_approval_valid
    require_current_approval_valid()
    scoped_contract = {**deepcopy(contract), "handoff": handoff}
    identity = digest({"parent": result["run_id"], "contract": scoped_contract,
                       "body_sha256": hashlib.sha256(body).hexdigest()})
    base_parts = ("vera-deliveries", result["run_id"], identity)
    parts = (*base_parts, "files", *target.split("/")[:-1])
    audit = {"format": "verantyx.scoped-delivery.v2", "parent_run": result["run_id"],
             "parent_revision": result["state"]["revision"], "reason": reason,
             "contract": scoped_contract, "original_validation": deepcopy(attempt.get("validation")),
             "original_plan": deepcopy(result["state"].get("handoff_plan")),
             "original_editor_document": deepcopy(document),
             "canonical_code_adopted": False, "model_calls": 0}
    _write_files(root, base_parts, {"handoff.json": (canonical(audit) + "\n").encode("utf-8")})
    _write_files(root, parts, {target.split("/")[-1]: body})
    relative = "/".join((*parts, target.split("/")[-1]))
    judged = judge_target(root, configuration, result["run_id"], scoped_contract,
                          key="delivery-v2-" + digest(key)[:32], reason=reason, target=relative)
    return {**judged, "artifact": str(Path(root) / relative), "original_untouched": True,
            "handoff": handoff, "handoff_record": str(Path(root).joinpath(*base_parts, "handoff.json")),
            "tests_executed": "EXPLICIT_FINITE_PREDICATES_ONLY"}
