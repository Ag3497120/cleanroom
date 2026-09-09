"""Closed, finite rule policies and pure checks for their recorded evidence.

Scope expansion is deliberately a finite set of exact five-axis scopes. A
proposal does not change an effective rule; a separately confirmed hash does.
"""
from copy import deepcopy
from itertools import product

from .codec import digest

SCOPE_KEYS = ("project_id", "component", "workload", "risk", "decision_type")
EVENT_ACTORS = {
    "RulePolicyProposed": "local_cli", "RulePolicyAccepted": "local_cli",
    "RulePolicyShadowed": "scope_verifier", "RulePolicyConfirmed": "local_cli",
    "RuleEnforcementSet": "local_cli",
}


def options_contract(options):
    """IDs alone are not the meaning of a value decision."""
    return digest(sorted(options, key=lambda option: option["id"]))


def exact_policy(origin, minimum_shadow_tasks=2):
    return {"schema_version": 1, "scope": {key: [origin[key]] for key in SCOPE_KEYS},
            "exceptions": [], "minimum_shadow_tasks": minimum_shadow_tasks}


def validate_policy(value, origin=None):
    from .events import fields, require, scope
    from ..adapters.proposal_validation import valid_id
    fields(value, ("schema_version", "scope", "exceptions", "minimum_shadow_tasks"))
    require(type(value["schema_version"]) is int and value["schema_version"] == 1)
    fields(value["scope"], SCOPE_KEYS)
    count = 1
    for key, values in value["scope"].items():
        require(type(values) is list and 1 <= len(values) <= (8 if key in ("component", "workload") else 1))
        require(all(type(item) is str and item and len(item) <= 160 for item in values))
        require(len(set(values)) == len(values) and values == sorted(values))
        require(all(item != "UNSPECIFIED" and not any(c in item for c in "*?[]") for item in values))
        count *= len(values)
        if origin is not None:
            require(origin[key] in values, "RULE_SCOPE_UNSAFE")
            if key not in ("component", "workload"):
                require(values == [origin[key]], "RULE_SCOPE_UNSAFE")
    require(count <= 32)
    for cell in scopes(value):
        scope(cell)
    require(type(value["minimum_shadow_tasks"]) is int and 1 <= value["minimum_shadow_tasks"] <= 100)
    require(type(value["exceptions"]) is list and len(value["exceptions"]) <= 32)
    ids, seen = set(), set()
    for exception in value["exceptions"]:
        fields(exception, ("id", "scope", "reason"))
        require(valid_id(exception["id"]) and exception["id"] not in ids)
        ids.add(exception["id"])
        scope(exception["scope"])
        require(within_scope(value, exception["scope"]), "RULE_SCOPE_UNSAFE")
        scope_hash = digest(exception["scope"])
        require(scope_hash not in seen)
        seen.add(scope_hash)
        require(type(exception["reason"]) is str and 1 <= len(exception["reason"].strip()) <= 4000)
    return value


def scopes(policy):
    return [dict(zip(SCOPE_KEYS, values)) for values in product(*(policy["scope"][key] for key in SCOPE_KEYS))]


def within_scope(policy, target):
    return all(target[key] in policy["scope"][key] for key in SCOPE_KEYS)


def effective_scope(rule, target):
    policy = rule.get("scope_policy")
    return within_scope(policy, target) if policy else rule["scope"] == target


def exceptions_at(rule, target):
    policy = rule.get("scope_policy")
    return [item["id"] for item in (policy or {}).get("exceptions", []) if item["scope"] == target]


def config_hash(rule):
    return digest({key: value for key, value in rule.items() if key not in ("history", "policy_proposal")})


def receipt_input(scope, target):
    return {**{"rule_" + key: scope[key] for key in SCOPE_KEYS},
            **{"target_" + key: target[key] for key in SCOPE_KEYS}}


def validate_match(rule, target, receipt):
    """Verify a receipt against frozen inputs without invoking the VM."""
    from .events import fields, require, hash_value, scope
    from ..adapters.proposal_validation import valid_id
    if set(receipt) == {"error"}:
        require(valid_id(receipt["error"]))
        return
    policy = rule.get("scope_policy")
    if not policy:
        fields(receipt, ("match", "input_hash", "engine"))
        require(type(receipt["match"]) is bool and receipt["match"] == (rule["scope"] == target), "STORE_INTEGRITY")
        require(receipt["input_hash"] == digest(receipt_input(rule["scope"], target)), "STORE_INTEGRITY")
    else:
        fields(receipt, ("schema", "policy_hash", "target", "within_scope", "exceptions", "match", "input_hash", "engine", "witness"))
        require(receipt["schema"] == "finite-scope-match.v1")
        require(receipt["policy_hash"] == digest(policy) and receipt["target"] == target, "STORE_INTEGRITY")
        scope(receipt["target"])
        inside = within_scope(policy, target)
        exempt = exceptions_at(rule, target)
        require(type(receipt["within_scope"]) is bool and receipt["within_scope"] == inside, "STORE_INTEGRITY")
        require(receipt["exceptions"] == exempt, "STORE_INTEGRITY")
        require(type(receipt["match"]) is bool and receipt["match"] == (inside and not exempt), "STORE_INTEGRITY")
        require(receipt["input_hash"] == digest({"policy": policy, "target": target}), "STORE_INTEGRITY")
        witness = receipt["witness"]
        fields(witness, ("scope", "receipt"))
        expected_cell = target if inside else scopes(policy)[0]
        require(witness["scope"] == expected_cell, "STORE_INTEGRITY")
        validate_match({"scope": expected_cell}, target, witness["receipt"])
        require(witness["receipt"]["engine"] == receipt["engine"], "STORE_INTEGRITY")
    hash_value(receipt["engine"])
    if rule.get("check"):
        require(receipt["engine"] == rule["check"]["engine"], "STORE_INTEGRITY")


def shadow_cases(policy):
    cases = [(target, not any(item["scope"] == target for item in policy["exceptions"]), "cell-" + str(index))
             for index, target in enumerate(scopes(policy))]
    anchor = scopes(policy)[0]
    for key in SCOPE_KEYS:
        target = dict(anchor)
        candidate = {"project_id": "00000000-0000-0000-0000-000000000000",
                     "risk": "LOW" if anchor[key] != "LOW" else "HIGH"}.get(key, "outside-" + digest({"key": key, "policy": policy})[:24])
        while candidate in policy["scope"][key]:
            candidate = "11111111-1111-1111-1111-111111111111" if key == "project_id" else "x" + candidate
        target[key] = candidate
        cases.append((target, False, "outside-" + key))
    return cases


def validate_engine_evidence(check):
    """The registered v1 evaluator records shared origins, never I5 proof.

    These fields describe the actual .cross/host path. A caller cannot turn a
    shared oracle or environment into independent evidence by editing prose.
    """
    from .events import fields, require, hash_value
    identity = check["identity"]
    fields(identity, ("backend", "runtime_sha256", "program_sha256", "meaning_sha256"))
    require(identity["backend"] == "cross-scope.v1")
    for field in ("runtime_sha256", "program_sha256", "meaning_sha256"):
        hash_value(identity[field])
    origin = check["origin"]
    fields(origin, ("kind", "mechanism", "independent_design", "note"))
    require(origin["kind"] == "I3" and origin["independent_design"] is False)
    expected = {"EXACT_MATCH_MECHANISM_ONLY": "cross-vm-and-host-reference",
                "FINITE_SCOPE_MECHANISM_ONLY": "finite-host-selector-and-cross-vm-exact-comparison"}
    require(origin["mechanism"] == expected.get(check["scope"]))
    require(type(origin["note"]) is str and 1 <= len(origin["note"]) <= 2000)
    independence = check["independence"]
    fields(independence, ("generator", "implementation", "oracle", "data", "environment"))
    fields(independence["generator"], ("same_model", "same_provider"))
    require(all(value is None for value in independence["generator"].values()))
    fields(independence["implementation"], ("same_code_path", "shared_dependency"))
    require(independence["implementation"]["same_code_path"] is False
            and independence["implementation"]["shared_dependency"] is True)
    fields(independence["oracle"], ("same_expected_value_source",))
    require(independence["oracle"]["same_expected_value_source"] is True)
    fields(independence["data"], ("dataset_overlap",))
    require(independence["data"]["dataset_overlap"] == "complete")
    fields(independence["environment"], ("same_machine",))
    require(independence["environment"]["same_machine"] is True)


def validate_shadow(policy, check):
    from .events import fields, require, hash_value
    fields(check, ("methods", "closure", "scope", "origin", "engine", "identity", "cases", "independence", "policy_hash"))
    require(check["methods"] == ["TEST", "NEGATIVE_CONTROL"] and check["closure"] == "BOUNDED")
    require(check["scope"] == "FINITE_SCOPE_MECHANISM_ONLY" and check["policy_hash"] == digest(policy))
    validate_engine_evidence(check)
    hash_value(check["engine"])
    require(digest(check["identity"]) == check["engine"], "STORE_INTEGRITY")
    cases = shadow_cases(policy)
    require(type(check["cases"]) is list and len(check["cases"]) == len(cases))
    for actual, (target, expected, label) in zip(check["cases"], cases):
        fields(actual, ("case", "target", "expected", "receipt"))
        require(actual["case"] == label and actual["target"] == target and actual["expected"] is expected, "STORE_INTEGRITY")
        validate_match({"scope_policy": policy, "check": check}, target, actual["receipt"])
        require(actual["receipt"]["match"] is expected, "STORE_INTEGRITY")


def validate_payload(kind, payload):
    from .events import fields, require, hash_value, uuid_value
    expected = {
        "RulePolicyProposed": ("rule_id", "proposal_id", "policy", "policy_hash", "basis_hash", "reason"),
        "RulePolicyAccepted": ("rule_id", "proposal_id", "policy_hash", "reason"),
        "RulePolicyShadowed": ("rule_id", "policy_hash", "check"),
        "RulePolicyConfirmed": ("rule_id", "policy_hash", "shadow_refs", "reason"),
        "RuleEnforcementSet": ("rule_id", "policy_hash", "enforcement", "reason"),
    }
    fields(payload, expected[kind])
    uuid_value(payload["rule_id"])
    if payload["policy_hash"] is not None:
        hash_value(payload["policy_hash"])
    if "reason" in payload:
        require(type(payload["reason"]) is str and 1 <= len(payload["reason"].strip()) <= 4000)
    if "proposal_id" in payload:
        uuid_value(payload["proposal_id"])
    if kind == "RulePolicyProposed":
        validate_policy(payload["policy"])
        require(digest(payload["policy"]) == payload["policy_hash"])
        hash_value(payload["basis_hash"])
    elif kind == "RulePolicyShadowed":
        require(type(payload["check"]) is dict)
    elif kind == "RulePolicyConfirmed":
        from ..adapters.proposal_validation import valid_id
        require(type(payload["shadow_refs"]) is list and 1 <= len(payload["shadow_refs"]) <= 100)
        require(all(valid_id(ref) for ref in payload["shadow_refs"]) and len(set(payload["shadow_refs"])) == len(payload["shadow_refs"]))
    elif kind == "RuleEnforcementSet":
        require(payload["enforcement"] in ("WARN", "BLOCK"))


def audit_rows(state, payload, ref, recorded_at):
    """Every recorded context includes shadow hits, misses, exceptions and conflicts."""
    rows = []
    for point in (state.get("proposal") or {}).get("decision_points", []):
        if point["kind"] != "VALUE_DECISION":
            continue
        target = {"project_id": state["project_id"], **state["context"], "decision_type": point["decision_type"]}
        applicable = [rule for rule in payload["rules"] if rule["validity"] == "CURRENT"
                      and rule["enforcement"] in ("SHADOW", "WARN", "BLOCK") and rule["decision_type"] == point["decision_type"]]
        matching = [rule for rule in applicable if effective_scope(rule, target) and not exceptions_at(rule, target)]
        conflict = len({(rule["choice"], options_contract(rule["options"])) for rule in matching}) > 1
        human = state.get("human_decisions", {}).get(point["id"])
        human_choice = human["choice"] if (human and human["scope"] == target and human.get("options_hash") == options_contract(point["options"])) else None
        for rule in applicable:
            receipt = payload["matches"].get(point["id"], {}).get(rule["id"])
            exempt = exceptions_at(rule, target)
            contrary = [other for other in matching if (other["choice"], options_contract(other["options"]))
                        != (rule["choice"], options_contract(rule["options"]))]
            predecessor_only = (bool(contrary) and all(other["id"] == rule.get("supersedes")
                                and other["scope"] == rule["scope"] and other.get("scope_policy") == rule.get("scope_policy")
                                for other in contrary))
            if not effective_scope(rule, target):
                outcome = "OUT_OF_SCOPE"
            elif exempt:
                outcome = "EXEMPTED"
            elif options_contract(rule["options"]) != options_contract(point["options"]):
                outcome = "OPTION_CONTRACT_MISMATCH"
            elif not receipt or receipt.get("error"):
                outcome = "ENGINE_ERROR"
            elif rule["review_after"] <= recorded_at:
                outcome = "STALE"
            elif rule["contested"]:
                outcome = "CONTESTED"
            elif conflict and not predecessor_only:
                outcome = "RULE_CONFLICT"
            elif human_choice is not None and human_choice != rule["choice"]:
                outcome = "HUMAN_DISAGREEMENT"
            elif predecessor_only:
                outcome = "SUPERSESSION_REVIEW" if human_choice is not None else "WOULD_SUPERSEDE"
            else:
                outcome = "MATCHED_HUMAN" if human_choice is not None else "WOULD_APPLY"
            rows.append({"source_ref": ref, "recorded_at": recorded_at, "run_id": state["run_id"],
                         "proposal_ref": state.get("proposal_ref"), "point_id": point["id"], "target": target,
                         "rule_id": rule["id"], "policy_ref": rule.get("policy_ref"),
                         "policy_hash": digest(rule["scope_policy"]) if rule.get("scope_policy") else None,
                         "enforcement": rule["enforcement"], "choice": rule["choice"], "human_choice": human_choice,
                         "outcome": outcome, "exception_ids": exempt, "receipt": deepcopy(receipt)})
    return rows


def qualifying_shadow(rule, history):
    from .events import require
    current = [row for row in history if row["rule_id"] == rule["id"] and row["policy_ref"] == rule.get("policy_ref")
               and row["run_id"] != rule["owner_run"]]
    require(not any(row["outcome"] in ("RULE_CONFLICT", "HUMAN_DISAGREEMENT", "OPTION_CONTRACT_MISMATCH", "CONTESTED", "ENGINE_ERROR")
                    for row in current), "RULE_SHADOW_CONFLICT")
    # Re-evaluating a single task cannot manufacture a long shadow history.
    latest = {}
    for row in current:
        if row["enforcement"] == "SHADOW" and row["outcome"] in ("MATCHED_HUMAN", "SUPERSESSION_REVIEW"):
            latest[row["run_id"]] = row["source_ref"]
    require(len(latest) >= rule["scope_policy"]["minimum_shadow_tasks"], "RULE_SHADOW_INSUFFICIENT")
    return list(latest.values())[-100:]


def apply_rule_event(rule, event, history):
    from .events import require, citation
    kind, payload = event["type"], event["payload"]
    require(rule["validity"] == "CURRENT", "STORE_INTEGRITY")
    if kind == "RulePolicyProposed":
        validate_policy(payload["policy"], rule["scope"])
        require(payload["basis_hash"] == config_hash(rule), "STORE_INTEGRITY")
        rule["policy_proposal"] = {**deepcopy(payload), "source_ref": citation(event), "command_id": event["command_id"]}
    elif kind == "RulePolicyAccepted":
        pending = rule.get("policy_proposal")
        require(pending and payload["proposal_id"] == pending["proposal_id"] and payload["policy_hash"] == pending["policy_hash"], "STORE_INTEGRITY")
        require(pending["command_id"] != event["command_id"], "STORE_INTEGRITY")
        require(pending["basis_hash"] == config_hash(rule), "RULE_STALE")
        rule.update(scope_policy=deepcopy(pending["policy"]), policy_ref=citation(event), policy_proposal=None,
                    state="DRAFT", maturity="DRAFT", enforcement="OFF", check=None, evidence_refs=[])
    elif kind == "RulePolicyShadowed":
        require(rule.get("scope_policy") and payload["policy_hash"] == digest(rule["scope_policy"]), "STORE_INTEGRITY")
        require(rule["enforcement"] == "OFF", "STORE_INTEGRITY")
        validate_shadow(rule["scope_policy"], payload["check"])
        rule.update(state="SHADOW", enforcement="SHADOW", check=deepcopy(payload["check"]))
        rule["evidence_refs"].append(citation(event))
    elif kind == "RulePolicyConfirmed":
        require(rule.get("scope_policy") and payload["policy_hash"] == digest(rule["scope_policy"]), "STORE_INTEGRITY")
        require(rule["enforcement"] == "SHADOW" and rule["maturity"] == "DRAFT" and rule["check"] and not rule["contested"], "STORE_INTEGRITY")
        require(payload["shadow_refs"] == qualifying_shadow(rule, history), "STORE_INTEGRITY")
        rule.update(maturity="VALIDATED", shadow_review_refs=list(payload["shadow_refs"]))
        rule["evidence_refs"].append(citation(event))
    else:
        policy_hash = digest(rule["scope_policy"]) if rule.get("scope_policy") else None
        require(payload["policy_hash"] == policy_hash and rule["maturity"] == "VALIDATED" and rule["check"] and not rule["contested"], "STORE_INTEGRITY")
        if rule.get("scope_policy"):
            qualifying_shadow(rule, history)
        require(rule["review_after"] > event["recorded_at"], "RULE_STALE")
        rule.update(state="ACTIVE", enforcement=payload["enforcement"])
    rule["history"].append(citation(event))
