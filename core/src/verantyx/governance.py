"""Local operator commands for decision records, precedents, and scoped rules."""
from datetime import timedelta
import uuid

from .adapters.cross_policy import CrossPolicyBackend
from .domain.codec import digest
from .domain.events import citation, make_event, require
from .errors import LedgerError
from .kernel.reducer import replay
from .kernel.rules import catalog
from .domain.rule_extensions import (validate_policy, config_hash, qualifying_shadow)


def precedents(events):
    result = {}
    for event in events:
        payload = event["payload"]
        if event["type"] == "PrecedentCandidateCreated":
            item = dict(payload)
            require(item["id"] not in result, "STORE_INTEGRITY")
            item.update(status="CANDIDATE", owner_run=event["stream_id"], source_ref=citation(event))
            result[item["id"]] = item
        elif event["type"] == "PrecedentAccepted":
            item = result.get(payload["id"])
            require(item and item["status"] == "CANDIDATE" and digest(item["scope"]) == payload["scope_hash"], "STORE_INTEGRITY")
            item.update(status="ACCEPTED", accepted_ref=citation(event))
    return result


def policy_context(events, state, backend=None):
    rules = list(catalog(events).values())
    if len(rules) > 256:
        raise LedgerError("DOCUMENT_LIMIT")
    results = {}
    for point in (state["proposal"] or {}).get("decision_points", []):
        if point["kind"] != "VALUE_DECISION":
            continue
        target = {"project_id": state["project_id"], **state["context"], "decision_type": point["decision_type"]}
        matches = {}
        for rule in rules:
            if rule["validity"] != "CURRENT" or rule["enforcement"] not in ("SHADOW", "WARN", "BLOCK") or rule["decision_type"] != point["decision_type"]:
                continue
            try:
                backend = backend or CrossPolicyBackend()
                if not rule["check"] or rule["check"]["engine"] != backend.fingerprint:
                    raise LedgerError("RULE_ENGINE_CHANGED")
                matches[rule["id"]] = (backend.match_policy(rule["scope_policy"], target) if rule.get("scope_policy")
                                       else backend.match(rule["scope"], target))
            except LedgerError as error:
                matches[rule["id"]] = {"error": error.code}
        results[point["id"]] = matches
    return {"rules": rules, "matches": results}


def policy_history(events, rule_id=None):
    """Read append-only task observations, preserving the project event order."""
    streams, sequence = {}, {}
    for index, event in enumerate(events):
        streams.setdefault(event["stream_id"], []).append(event)
        sequence[citation(event)] = index
    rows = [row for stream in streams.values() for row in replay(stream).get("rule_observations", [])
            if rule_id is None or row["rule_id"] == rule_id]
    return sorted(rows, key=lambda row: sequence[row["source_ref"]])


def policy_report(store, rule_id):
    events = store.events()
    rule = catalog(events).get(rule_id)
    if rule is None:
        raise LedgerError("RULE_NOT_FOUND")
    rows = policy_history(events, rule_id)
    counts = {}
    for row in rows:
        counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
    return {"ok": True, "rule_id": rule_id, "rule": rule, "observations": rows,
            "outcomes": counts, "distinct_tasks": len({row["run_id"] for row in rows}),
            "value_correctness": "NOT_PROVED", "authority": "READ_ONLY"}


def control(store, configuration, operation, target, *, point_id=None, choice=None, reason=None,
            key=None, expected_revision=None, clock=None, backend=None, policy=None, expected_policy_sha256=None, enforcement=None):
    from .application import iso, now, _receipt_view
    clock = clock or now
    key = key or str(uuid.uuid4())
    from .adapters.proposal_validation import valid_id
    if not valid_id(key) or not valid_id(target):
        raise LedgerError("ARGUMENTS")
    intent = {"operation": operation, "target": target, "point": point_id, "choice": choice,
              "reason": reason, "expected_revision": expected_revision}
    if operation in ("rule-policy-propose", "rule-policy-accept", "rule-policy-confirm", "rule-enforce"):
        intent.update(policy=policy, expected_policy_sha256=expected_policy_sha256, enforcement=enforcement)
    input_hash = digest(intent)
    cached = store.receipt(key, input_hash)
    if cached:
        result = _receipt_view(cached, key)
        if operation.startswith("rule-policy-") or operation == "rule-enforce":
            _policy_result(result, target)
        return result
    project_revision = store.project_revision()
    all_events = store.events()
    rules, previous_cases = catalog(all_events), precedents(all_events)
    if operation == "decide":
        owner_run = target
    elif operation in ("precedent-accept", "rule-draft"):
        if target not in previous_cases:
            raise LedgerError("RULE_NOT_FOUND")
        owner_run = previous_cases[target]["owner_run"]
    else:
        if target not in rules:
            raise LedgerError("RULE_NOT_FOUND")
        owner_run = rules[target]["owner_run"]
    previous = [event for event in all_events if event["stream_id"] == owner_run]
    state = replay(previous)
    if state is None:
        raise LedgerError("RUN_NOT_FOUND")
    revision = state["revision"]
    if expected_revision is not None and expected_revision != revision:
        raise LedgerError("REVISION_CONFLICT")
    batch, command_id = [], str(uuid.uuid4())

    def add(kind, payload):
        event = make_event(store.project_id, owner_run, revision + len(batch) + 1, command_id,
                           iso(clock()), kind, payload, str(uuid.uuid4()), batch[-1] if batch else previous[-1])
        batch.append(event)
        return citation(event)

    created = {}
    if operation in ("decide", "rule-amend"):
        if not reason or not reason.strip() or len(reason) > 4000:
            raise LedgerError("ARGUMENTS")
        if operation == "decide":
            points = {p["id"]: p for p in (state["proposal"] or {}).get("decision_points", [])}
            point = points.get(point_id)
            if point is None or point["kind"] != "VALUE_DECISION":
                raise LedgerError("DECISION_KIND")
            scope = {"project_id": store.project_id, **state["context"], "decision_type": point["decision_type"]}
            options, supersedes = point["options"], None
        else:
            old = rules[target]
            scope, options, supersedes = old["scope"], old["options"], target
            point_id = target
        if choice not in {option["id"] for option in options}:
            raise LedgerError("ARGUMENTS")
        if any(scope[key] == "UNSPECIFIED" for key in ("component", "workload", "risk")):
            raise LedgerError("SCOPE_INCOMPLETE")
        decision_ref = add("HumanDecisionRecorded", {"point_id": point_id, "choice": choice, "scope": scope, "reason": reason})
        precedent_id = str(uuid.uuid4())
        add("PrecedentCandidateCreated", {"id": precedent_id, "decision_ref": decision_ref, "scope": scope,
                                          "choice": choice, "options": options, "reason": reason,
                                          "review_after": iso(clock() + timedelta(days=30)), "supersedes": supersedes})
        created["precedent_id"] = precedent_id
    elif operation == "precedent-accept":
        precedent = previous_cases[target]
        if precedent["status"] != "CANDIDATE":
            raise LedgerError("RULE_STAGE")
        add("PrecedentAccepted", {"id": target, "scope_hash": digest(precedent["scope"])})
    elif operation == "rule-draft":
        precedent = previous_cases[target]
        if precedent["status"] != "ACCEPTED":
            raise LedgerError("RULE_STAGE")
        rule_id = str(uuid.uuid4())
        rule = {"id": rule_id, "scope": precedent["scope"], "decision_type": precedent["scope"]["decision_type"],
                "choice": precedent["choice"], "options": precedent["options"], "reason": precedent["reason"],
                "human_ref": precedent["decision_ref"], "precedent_ref": precedent["accepted_ref"],
                "supersedes": precedent["supersedes"], "owner": store.project_id, "exceptions": [],
                "source_decisions": [precedent["decision_ref"]], "review_after": precedent["review_after"]}
        add("RuleCandidateCreated", {"rule": rule})
        created["rule_id"] = rule_id
    elif operation == "rule-shadow":
        rule = rules[target]
        if rule["validity"] != "CURRENT" or rule["enforcement"] != "OFF":
            raise LedgerError("RULE_STAGE")
        engine = backend or CrossPolicyBackend()
        if rule.get("scope_policy"):
            check = engine.shadow_policy_check(rule["scope_policy"])
            add("RulePolicyShadowed", {"rule_id": target, "policy_hash": digest(rule["scope_policy"]), "check": check})
        else:
            add("RuleShadowed", {"rule_id": target, "check": engine.shadow_check(rule["scope"])})
    elif operation == "rule-confirm":
        rule = rules[target]
        if rule.get("scope_policy") or rule["validity"] != "CURRENT" or rule["maturity"] != "DRAFT":
            raise LedgerError("RULE_STAGE")
        add("RuleConfirmed", {"rule_id": target})
    elif operation == "rule-activate":
        rule = rules[target]
        engine = backend or CrossPolicyBackend()
        if rule.get("scope_policy") or rule["validity"] != "CURRENT" or rule["maturity"] != "VALIDATED" or rule["contested"]:
            raise LedgerError("RULE_STAGE")
        if rule["check"]["engine"] != engine.fingerprint or rule["review_after"] <= iso(clock()):
            raise LedgerError("RULE_STALE")
        if rule["supersedes"]:
            old = rules.get(rule["supersedes"])
            if not old or old["scope"] != rule["scope"] or old["validity"] != "CURRENT":
                raise LedgerError("RULE_STAGE")
            add("RuleSuperseded", {"rule_id": old["id"], "successor": rule["id"]})
        add("RuleActivated", {"rule_id": target})
    elif operation in ("rule-policy-propose", "rule-policy-accept", "rule-policy-confirm", "rule-enforce"):
        rule = rules[target]
        if rule["validity"] != "CURRENT" or type(reason) is not str or not 1 <= len(reason.strip()) <= 4000:
            raise LedgerError("RULE_STAGE")
        if operation == "rule-policy-propose":
            validate_policy(policy, rule["scope"])
            add("RulePolicyProposed", {"rule_id": target, "proposal_id": str(uuid.uuid4()), "policy": policy,
                                       "policy_hash": digest(policy), "basis_hash": config_hash(rule), "reason": reason})
        elif operation == "rule-policy-accept":
            pending = rule.get("policy_proposal")
            if not pending or pending["policy_hash"] != expected_policy_sha256:
                raise LedgerError("RULE_POLICY_CHANGED")
            if pending["basis_hash"] != config_hash(rule):
                raise LedgerError("RULE_STALE")
            add("RulePolicyAccepted", {"rule_id": target, "proposal_id": pending["proposal_id"],
                                       "policy_hash": expected_policy_sha256, "reason": reason})
        else:
            effective_hash = digest(rule["scope_policy"]) if rule.get("scope_policy") else None
            if effective_hash != expected_policy_sha256:
                raise LedgerError("RULE_POLICY_CHANGED")
            if not rule["check"] or rule["check"]["engine"] != (backend or CrossPolicyBackend()).fingerprint or rule["review_after"] <= iso(clock()):
                raise LedgerError("RULE_STALE")
            if operation == "rule-policy-confirm":
                if not rule.get("scope_policy") or rule["enforcement"] != "SHADOW" or rule["maturity"] != "DRAFT" or rule["contested"]:
                    raise LedgerError("RULE_STAGE")
                refs = qualifying_shadow(rule, policy_history(all_events))
                add("RulePolicyConfirmed", {"rule_id": target, "policy_hash": effective_hash, "shadow_refs": refs, "reason": reason})
            else:
                if rule["maturity"] != "VALIDATED" or rule["contested"] or enforcement not in ("WARN", "BLOCK"):
                    raise LedgerError("RULE_STAGE")
                if rule.get("scope_policy"):
                    qualifying_shadow(rule, policy_history(all_events))
                if rule["supersedes"]:
                    old = rules.get(rule["supersedes"])
                    if not old or old["scope"] != rule["scope"] or old.get("scope_policy") != rule.get("scope_policy"):
                        raise LedgerError("RULE_STAGE")
                    if old["validity"] == "CURRENT":
                        add("RuleSuperseded", {"rule_id": old["id"], "successor": target})
                    elif old["validity"] != "SUPERSEDED" or old.get("successor") != target:
                        raise LedgerError("RULE_STAGE")
                add("RuleEnforcementSet", {"rule_id": target, "policy_hash": effective_hash, "enforcement": enforcement, "reason": reason})
    elif operation in ("rule-retire", "rule-contest"):
        if not reason or not reason.strip() or len(reason) > 4000 or rules[target]["validity"] != "CURRENT":
            raise LedgerError("RULE_STAGE")
        add("RuleRetired" if operation == "rule-retire" else "RuleContested", {"rule_id": target, "reason": reason})
    else:
        raise LedgerError("ARGUMENTS")
    current = replay([*previous, *batch])
    add("PolicyContextRecorded", policy_context([*all_events, *batch], current, backend=backend))
    add("EvaluationRecorded", {"as_of": iso(clock()), "evaluator": "m1.v1"})
    receipt = store.append(key, input_hash, owner_run, revision, batch, project_revision=project_revision)
    result = _receipt_view(receipt, key)
    # IDs are already in events and remain discoverable after an idempotent retry.
    result.update(created)
    if operation.startswith("rule-policy-") or operation == "rule-enforce":
        _policy_result(result, target)
    return result


def _policy_result(result, target):
    rule = next(rule for rule in result["state"]["policy_context"]["rules"] if rule["id"] == target)
    result.update(rule_id=target, rule=rule)
    pending = rule.get("policy_proposal")
    result["policy_sha256"] = pending["policy_hash"] if pending else (digest(rule["scope_policy"]) if rule.get("scope_policy") else None)
