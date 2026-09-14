"""Human-selected, exact-scope skill policies; no inferred mastery or authority."""
from copy import deepcopy

from .domain.codec import canonical, digest
from .errors import LedgerError
from .personal_skills import read_state, require, valid_text
from .security_journal import Journal, exclusive

AI_MODES = ("explain", "propose", "check")
REUSE_MODES = ("confirm", "assisted", "auto-check")
FORMAT = "verantyx.skill-policy.v1"


def _candidate(state, candidate_id):
    candidate = state.get("learning_candidates", {}).get(candidate_id)
    require(candidate is not None, "SKILL_POLICY_RECORDED_CANDIDATE_REQUIRED")
    return candidate


def _validate(document):
    from .adapters.observations import normalize_path
    from .adapters.proposal_validation import valid_id
    require(type(document) is dict and set(document) == {
        "format", "project_id", "run_id", "candidate_id", "candidate_source_ref",
        "ai_mode", "reuse_mode", "paths", "asset_ids", "reason",
    }, "SKILL_POLICY_DOCUMENT")
    require(document["format"] == FORMAT, "SKILL_POLICY_FORMAT")
    require(all(valid_id(document[key]) for key in ("run_id", "candidate_id")), "SKILL_POLICY_IDENTIFIER")
    require(valid_text(document["candidate_source_ref"], 1000), "SKILL_POLICY_SOURCE")
    require(document["ai_mode"] in AI_MODES and document["reuse_mode"] in REUSE_MODES, "SKILL_POLICY_MODE")
    require(valid_text(document["reason"], 2000), "SKILL_POLICY_REASON")
    for field in ("paths", "asset_ids"):
        values = document[field]
        require(type(values) is list and len(values) <= 16
                and all(type(value) is str for value in values), "SKILL_POLICY_SCOPE")
        require(values == sorted(set(values)), "SKILL_POLICY_SCOPE")
    for path in document["paths"]:
        require(normalize_path(path) == path, "SKILL_POLICY_PATH")
    require(all(valid_id(value) for value in document["asset_ids"]), "SKILL_POLICY_ASSET")
    if document["ai_mode"] == "check":
        require(bool(document["paths"]) and bool(document["asset_ids"]), "SKILL_POLICY_CHECK_SCOPE")
    return document


def policy_snapshot(root, configuration):
    """Read the operational policy journal without changing the skill ledger."""
    rows = Journal(root, "skill-policies", configuration["project"]["id"]).read()
    policies, seen = {}, set()
    for row in rows:
        payload = row["payload"]
        require(row["kind"] == "SkillPolicySet" and type(payload) is dict
                and set(payload) == {"key", "intent_hash", "document", "policy_id"}, "SKILL_POLICY_INTEGRITY")
        document = _validate(payload["document"])
        require(document["project_id"] == configuration["project"]["id"]
                and payload["policy_id"] == digest(document)
                and payload["intent_hash"] == digest({"document": document})
                and payload["key"] not in seen, "SKILL_POLICY_INTEGRITY")
        seen.add(payload["key"])
        policy = {**deepcopy(document), "policy_id": payload["policy_id"],
                  "policy_revision": row["revision"], "recorded_at": row["recorded_at"]}
        policies[(document["run_id"], document["candidate_id"])] = policy
    return {"revision": len(rows), "policies": list(policies.values()), "entries": rows}


def _find(snapshot, run_id, candidate_id):
    return next((row for row in snapshot["policies"]
                 if row["run_id"] == run_id and row["candidate_id"] == candidate_id), None)


def set_policy(root, configuration, run_id, *, candidate_id, ai_mode, reuse_mode,
               paths, asset_ids, reason, key, expected_policy_revision):
    from .adapters.proposal_validation import valid_id
    from .application import iso, now
    from .authority import require_current_approval_valid
    require(valid_id(key), "SKILL_POLICY_KEY")
    require(type(expected_policy_revision) is int and expected_policy_revision >= 0, "SKILL_POLICY_REVISION")
    with exclusive(root, "skill-policies"):
        state = read_state(root, configuration, run_id)
        candidate = _candidate(state, candidate_id)
        document = _validate({
            "format": FORMAT, "project_id": configuration["project"]["id"],
            "run_id": run_id, "candidate_id": candidate_id,
            "candidate_source_ref": candidate["source_ref"],
            "ai_mode": ai_mode, "reuse_mode": reuse_mode, "paths": sorted(set(paths)),
            "asset_ids": sorted(set(asset_ids)), "reason": reason,
        })
        intent_hash = digest({"document": document})
        current = policy_snapshot(root, configuration)
        previous = next((row for row in current["entries"] if row["payload"]["key"] == key), None)
        if previous is not None:
            require(previous["payload"]["intent_hash"] == intent_hash, "SKILL_POLICY_IDEMPOTENCY_CONFLICT")
            return {"ok": True, "command": "skills-policy-set", "duplicate": True,
                    "policy": deepcopy(previous["payload"]["document"]),
                    "policy_id": previous["payload"]["policy_id"], "recorded_revision": previous["revision"],
                    "current_revision": current["revision"], "execution_authorized": False}
        require(current["revision"] == expected_policy_revision, "SKILL_POLICY_REVISION_CHANGED")
        require_current_approval_valid()
        row = Journal(root, "skill-policies", configuration["project"]["id"]).append(
            "SkillPolicySet", {"key": key, "intent_hash": intent_hash, "document": document,
                               "policy_id": digest(document)}, iso(now()), current["revision"])
        return {"ok": True, "command": "skills-policy-set", "duplicate": False,
                "policy": document, "policy_id": digest(document), "recorded_revision": row["revision"],
                "current_revision": row["revision"], "execution_authorized": False}


def route(root, configuration, run_id, *, candidate_id, asset_id, claim_id, target_path):
    """Resolve only explicit identifiers; never infer scope from semantic similarity."""
    from .adapters.observations import normalize_path
    from .adapters.proposal_validation import valid_id
    from .asset_workflow import _context, EXPLICIT_REUSE_IDENTITY
    from .storage.sqlite import EventStore
    require(all(valid_id(value) for value in (run_id, candidate_id, asset_id, claim_id)), "SKILL_ROUTE_IDENTIFIER")
    target_path = normalize_path(target_path)
    state = read_state(root, configuration, run_id)
    candidate = _candidate(state, candidate_id)
    current = policy_snapshot(root, configuration)
    policy = _find(current, run_id, candidate_id)
    result = {"ok": True, "command": "skills-route", "run_id": run_id, "candidate_id": candidate_id,
              "status": "UNKNOWN", "reason": "POLICY_REQUIRED", "policy": deepcopy(policy), "scope": None,
              "ownership_target": candidate.get("ownership_target"), "model_calls": 0,
              "execution_authorized": False, "execution_performed": False}
    if policy is None:
        return result
    if policy["candidate_source_ref"] != candidate["source_ref"]:
        return {**result, "reason": "SKILL_SOURCE_CHANGED"}
    if policy["ai_mode"] == "explain":
        return {**result, "status": "REFERENCE_ONLY", "reason": "EXPLANATION_NOT_EXECUTION"}
    if target_path not in policy["paths"] or asset_id not in policy["asset_ids"]:
        return {**result, "status": "BLOCKED", "reason": "OUTSIDE_EXPLICIT_SCOPE"}
    with EventStore(root, configuration["project"]["id"]) as store:
        context = _context(root, store, run_id, [target_path], EXPLICIT_REUSE_IDENTITY, exact_asset_id=asset_id)
    require(any(claim["id"] == claim_id for claim in context["claims"]), "SKILL_ROUTE_CLAIM_NOT_FOUND")
    require(len(context["available_methods"]) == 1, "SKILL_ROUTE_AMBIGUOUS_ASSET")
    scope = {"project_id": configuration["project"]["id"], "run_id": run_id,
             "basis_revision": context["basis_revision"], "policy_revision": current["revision"],
             "policy_id": policy["policy_id"], "candidate_source_ref": candidate["source_ref"],
             "asset_id": asset_id, "claim_id": claim_id, "target_path": target_path,
             "context_sha256": digest(context)}
    scope["id"] = digest(scope)
    status = "PLAN_ONLY" if policy["ai_mode"] == "propose" else (
        "READY" if policy["reuse_mode"] == "auto-check" else "AWAITING_CONFIRMATION")
    result.update(status=status, reason="EXACT_SCOPED_CONTRACT", scope=scope,
                  method=deepcopy(context["available_methods"][0]),
                  minimum_model=candidate.get("minimum_model"), counterexample=candidate.get("counterexample"),
                  understanding_required_to_continue=False,
                  system_capture="RECORDED_VERIFICATION_CONTRACT",
                  boundary="A method record and human-selected policy are not a passing result or general execution authority.")
    result["cross"] = {"center": candidate_id, "slots": {
        "+x": {"candidate_source_ref": candidate["source_ref"],
               "method_source_ref": context["available_methods"][0]["source_ref"]},
        "-x": {"paths": list(policy["paths"]), "assets": list(policy["asset_ids"])},
        "+y": {"claim_id": claim_id, "target_path": target_path},
        "-y": {"counterexample": candidate.get("counterexample"), "outside_scope": "BLOCK"},
        "+z": {"policy_id": policy["policy_id"], "reuse_mode": policy["reuse_mode"]},
        "-z": {"status": status, "result": "NOT_EXECUTED"},
    }, "selection": "EXPLICIT_IDENTIFIERS_NOT_LEARNED_ROUTING"}
    return result


def reuse(root, configuration, run_id, *, candidate_id, asset_id, claim_id, target_path,
          scope_id, key, execute=False, confirm_scope=None, judgment_reason=None):
    from .adapters.invocation_journal import InvocationJournal
    from .adapters.proposal_validation import valid_id
    from .asset_workflow import run_asset_workflow
    from .authority import require_current_approval_valid
    require(valid_id(key) and valid_text(scope_id, 64) and len(scope_id) == 64, "SKILL_REUSE_IDENTIFIER")
    arguments = {"run_id": run_id, "candidate_id": candidate_id, "asset_id": asset_id,
                 "claim_id": claim_id, "target_path": target_path, "scope_id": scope_id,
                 "confirm_scope": confirm_scope, "judgment_reason": judgment_reason}
    if not execute:
        return route(root, configuration, run_id, candidate_id=candidate_id, asset_id=asset_id,
                     claim_id=claim_id, target_path=target_path)
    with exclusive(root, "skill-policies"), InvocationJournal(root, "skill-reuse", key) as journal:
        intent_hash = digest(arguments)
        started, finished = journal.read("started"), journal.read("finished")
        if started:
            require(started["intent_hash"] == intent_hash, "SKILL_REUSE_IDEMPOTENCY_CONFLICT")
        if finished:
            require(started is not None and finished["result_hash"] == digest(finished["result"]),
                    "SKILL_REUSE_RECEIPT_CHANGED")
            return {**finished["result"], "duplicate": True, "execution_performed": False,
                    "historical_receipt": True}
        if started is None:
            decision = route(root, configuration, run_id, candidate_id=candidate_id, asset_id=asset_id,
                             claim_id=claim_id, target_path=target_path)
            require(decision["status"] in ("READY", "AWAITING_CONFIRMATION"), "SKILL_REUSE_NOT_ALLOWED")
            require(decision["scope"]["id"] == scope_id, "SKILL_REUSE_SCOPE_CHANGED")
            mode = decision["policy"]["reuse_mode"]
            if mode != "auto-check":
                require(confirm_scope == scope_id, "SKILL_REUSE_CONFIRMATION_REQUIRED")
            if mode == "confirm":
                require(valid_text(judgment_reason, 2000), "SKILL_REUSE_JUDGMENT_REASON_REQUIRED")
            require_current_approval_valid()
            started = {"intent_hash": intent_hash, "decision": decision}
            journal.write("started", started)
        decision = started["decision"]
        current = policy_snapshot(root, configuration)
        policy = _find(current, run_id, candidate_id)
        candidate = _candidate(read_state(root, configuration, run_id), candidate_id)
        require(policy is not None and policy["policy_id"] == decision["scope"]["policy_id"]
                and current["revision"] == decision["scope"]["policy_revision"]
                and candidate["source_ref"] == decision["scope"]["candidate_source_ref"],
                "SKILL_REUSE_POLICY_CHANGED")
        require_current_approval_valid()
        receipt = run_asset_workflow(root, configuration, run_id,
            key="skill-check-" + journal.prefix, expected_revision=decision["scope"]["basis_revision"],
            include_paths=(), max_rounds=1, max_checks=8, execute=True,
            reuse_asset=asset_id, claim_id=claim_id, target_path=target_path,
            expected_context_hash=decision["scope"]["context_sha256"])
        result = {"ok": receipt["ok"], "command": "skills-reuse", "run_id": run_id,
                  "candidate_id": candidate_id, "scope": decision["scope"],
                  "workflow_id": receipt["workflow_id"], "workflow": receipt["workflow"],
                  "recorded_revision": receipt["recorded_revision"], "duplicate": False,
                  "execution_performed": True, "model_calls": 0, "automatic_repairs": 0,
                  "source_method_rewritten": False, "authority_granted": False,
                  "boundary": "Finite recorded checks only; no code editing, general correctness or mastery certification."}
        require_current_approval_valid()
        journal.write("finished", {"result_hash": digest(result), "result": result})
        return result
