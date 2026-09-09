"""Pure rule catalog derived from local control events, not model proposals."""
from copy import deepcopy

from ..domain.events import citation, require
from ..domain.codec import digest
from ..domain.rule_extensions import (EVENT_ACTORS as POLICY_ACTORS, options_contract, effective_scope,
                                      exceptions_at, audit_rows, apply_rule_event, validate_match)

RULE_TYPES = {"RuleCandidateCreated", "RuleShadowed", "RuleConfirmed", "RuleActivated",
              "RuleRetired", "RuleSuperseded", "RuleContested"}
RULE_TYPES.update(POLICY_ACTORS)


def validate_context(state, payload):
    points = {point["id"]: point for point in (state.get("proposal") or {}).get("decision_points", [])
              if point["kind"] == "VALUE_DECISION"}
    require(set(payload["matches"]) == set(points), "STORE_INTEGRITY")
    rules = {rule["id"]: rule for rule in payload["rules"]}
    require(len(rules) == len(payload["rules"]), "STORE_INTEGRITY")
    for point_id, matches in payload["matches"].items():
        point = points[point_id]
        target = {"project_id": state["project_id"], **state["context"], "decision_type": point["decision_type"]}
        applicable = {key: rule for key, rule in rules.items() if rule["validity"] == "CURRENT"
                      and rule["enforcement"] in ("SHADOW", "WARN", "BLOCK") and rule["decision_type"] == point["decision_type"]}
        mandatory = {key for key, rule in applicable.items() if rule["enforcement"] != "SHADOW" or rule.get("scope_policy")}
        # Older archives did not observe SHADOW contexts. They stay readable.
        require(mandatory <= set(matches) <= set(applicable), "STORE_INTEGRITY")
        for rule_id, receipt in matches.items():
            validate_match(rules[rule_id], target, receipt)


def catalog(events):
    from ..domain.asset_workflow import validate_project_bindings
    validate_project_bindings(events)
    rules, decisions, precedents, accepted, tasks, history = {}, {}, {}, {}, {}, []
    for event in events:
        kind, payload = event["type"], event["payload"]
        stream = event["stream_id"]
        if kind == "TaskRequested":
            tasks[stream] = {"project_id": event["project_id"], "run_id": stream, "context": payload["context"],
                             "proposal": None, "proposal_ref": None, "human_decisions": {}}
        elif kind == "ProposalRecorded":
            require(stream in tasks, "STORE_INTEGRITY")
            tasks[stream].update(proposal=payload["document"], proposal_ref=citation(event))
        elif kind == "HumanDecisionRecorded":
            task = tasks.get(stream)
            require(task is not None, "STORE_INTEGRITY")
            point = next((point for point in (task["proposal"] or {}).get("decision_points", [])
                          if point["id"] == payload["point_id"]), None)
            if point:
                require(point["kind"] == "VALUE_DECISION" and payload["scope"] == {"project_id": task["project_id"],
                        **task["context"], "decision_type": point["decision_type"]}, "STORE_INTEGRITY")
                options = point["options"]
            else:
                old_rule = rules.get(payload["point_id"])
                if old_rule:
                    require(old_rule["owner_run"] == stream and old_rule["scope"] == payload["scope"], "STORE_INTEGRITY")
                options = old_rule["options"] if old_rule else None
            if options is not None:
                require(payload["choice"] in {option["id"] for option in options}, "STORE_INTEGRITY")
            decisions[citation(event)] = (stream, payload, options)
            task["human_decisions"][payload["point_id"]] = {**payload, "source_ref": citation(event),
                                                          "options_hash": options_contract(options) if options is not None else None}
        elif kind == "PrecedentCandidateCreated":
            source = decisions.get(payload["decision_ref"])
            require(source and source[0] == event["stream_id"], "STORE_INTEGRITY")
            require(all(source[1][key] == payload[key] for key in ("scope", "choice", "reason")), "STORE_INTEGRITY")
            require(source[2] is not None and options_contract(source[2]) == options_contract(payload["options"]), "STORE_INTEGRITY")
            require(payload["id"] not in precedents, "STORE_INTEGRITY")
            precedents[payload["id"]] = (event["stream_id"], payload)
        elif kind == "PrecedentAccepted":
            precedent = precedents.get(payload["id"])
            require(precedent and precedent[0] == event["stream_id"], "STORE_INTEGRITY")
            require(digest(precedent[1]["scope"]) == payload["scope_hash"], "STORE_INTEGRITY")
            require(not any(p["id"] == payload["id"] for p in accepted.values()), "STORE_INTEGRITY")
            accepted[citation(event)] = precedent[1]
        elif kind == "PolicyContextRecorded":
            require(payload["rules"] == list(rules.values()), "STORE_INTEGRITY")
            require(stream in tasks, "STORE_INTEGRITY")
            validate_context(tasks[stream], payload)
            history.extend(audit_rows(tasks[stream], payload, citation(event), event["recorded_at"]))
        if kind not in RULE_TYPES:
            continue
        if kind == "RuleCandidateCreated":
            rule = deepcopy(payload["rule"])
            require(rule["id"] not in rules, "STORE_INTEGRITY")
            source = accepted.get(rule["precedent_ref"])
            require(source is not None and source["decision_ref"] == rule["human_ref"], "STORE_INTEGRITY")
            require(all(source[key] == rule[key] for key in ("scope", "choice", "options", "reason", "supersedes", "review_after")), "STORE_INTEGRITY")
            rule.update(state="DRAFT", owner_run=event["stream_id"], origin_ref=citation(event),
                        history=[citation(event)], check=None, contested=False, maturity="DRAFT",
                        enforcement="OFF", validity="CURRENT", evidence_refs=[])
            rules[rule["id"]] = rule
            continue
        rule = rules.get(payload["rule_id"])
        require(rule is not None and rule["owner_run"] == event["stream_id"], "STORE_INTEGRITY")
        if kind in POLICY_ACTORS:
            apply_rule_event(rule, event, history)
            continue
        before = rule["state"]
        if kind == "RuleShadowed":
            require(not rule.get("scope_policy"), "STORE_INTEGRITY")
            require(rule["validity"] == "CURRENT" and rule["enforcement"] == "OFF")
            cases = payload["check"]["cases"]
            require({c["case"] for c in cases} == {"exact", *rule["scope"]}, "STORE_INTEGRITY")
            for case in cases:
                differing = {k for k in rule["scope"] if rule["scope"][k] != case["target"][k]}
                require(differing == (set() if case["case"] == "exact" else {case["case"]}), "STORE_INTEGRITY")
                require(case["expected"] == (case["case"] == "exact"), "STORE_INTEGRITY")
                value = {**{"rule_" + k: v for k, v in rule["scope"].items()},
                         **{"target_" + k: v for k, v in case["target"].items()}}
                require(digest(value) == case["input_hash"], "STORE_INTEGRITY")
            rule.update(state="SHADOW", enforcement="SHADOW", check=deepcopy(payload["check"]))
            rule["evidence_refs"].append(citation(event))
            if rule["maturity"] == "REVIEWED":
                rule["maturity"] = "VALIDATED"
        elif kind == "RuleConfirmed":
            require(not rule.get("scope_policy"), "STORE_INTEGRITY")
            require(rule["validity"] == "CURRENT" and rule["maturity"] == "DRAFT")
            rule.update(maturity="VALIDATED" if rule["check"] else "REVIEWED",
                        state="SHADOW" if rule["check"] else "CONFIRMED")
        elif kind == "RuleActivated":
            require(not rule.get("scope_policy"), "STORE_INTEGRITY")
            require(rule["validity"] == "CURRENT" and rule["maturity"] == "VALIDATED" and not rule["contested"])
            require(rule["review_after"] > event["recorded_at"], "RULE_STALE")
            rule.update(state="ACTIVE", enforcement="BLOCK")
        elif kind == "RuleRetired":
            require(before not in ("RETIRED", "SUPERSEDED"))
            rule.update(state="RETIRED", validity="RETIRED", enforcement="OFF")
        elif kind == "RuleSuperseded":
            require(before not in ("RETIRED", "SUPERSEDED"))
            successor = rules.get(payload["successor"])
            require(successor and successor["supersedes"] == rule["id"] and successor["scope"] == rule["scope"]
                    and successor.get("scope_policy") == rule.get("scope_policy")
                    and successor["id"] != rule["id"] and successor["owner_run"] == rule["owner_run"]
                    and successor["validity"] == "CURRENT" and not successor["contested"]
                    and successor["review_after"] > event["recorded_at"]
                    and successor["maturity"] == "VALIDATED", "STORE_INTEGRITY")
            rule.update(state="SUPERSEDED", validity="SUPERSEDED", enforcement="OFF", successor=payload["successor"])
        elif kind == "RuleContested":
            require(before not in ("RETIRED", "SUPERSEDED"))
            rule["contested"] = True
            rule.setdefault("counterexamples", []).append({"reason": payload["reason"], "source_ref": citation(event),
                                                         "evidence_kind": "LOCAL_REPORT"})
        rule["history"].append(citation(event))
    return rules


def classify_gap(code):
    if code in ("STALE_SOURCE", "SOURCE_CHANGED", "RULE_ENGINE_CHANGED", "AUTHORIZATION_STALE", "EDITOR_DECISION_CHANGED", "EDITOR_REFERENCE_CHANGED"):
        return "STALE_OBSERVATION"
    if code in ("TOOL_UNAVAILABLE", "CROSS_UNAVAILABLE", "CROSS_FAILED", "CROSS_DISAGREEMENT", "CROSS_CHANGED", "CROSS_INVALID_OUTPUT"):
        return "UNAVAILABLE_CAPABILITY"
    if code in ("RULE_CONFLICT", "RULE_CONTESTED"):
        return "CONTESTED"
    if code in ("SCOPE_MISMATCH", "RULE_OPTION_UNAVAILABLE", "RULE_OPTION_CHANGED"):
        return "UNSCOPED_RULE"
    if code in ("READ_SCOPE_NOT_GRANTED", "VALUE_DECISION_REQUIRED", "AUTHORITY_REQUIRED", "RULE_EXCEPTION_APPLIES", "EDITOR_DECISION_REQUIRED"):
        return "UNDECIDED_HUMAN"
    return "UNKNOWN_EVIDENCE"


def evaluate_decisions(state):
    points = (state["proposal"] or {}).get("decision_points", [])
    judgments, gaps = [], []
    snapshot = state["policy_context"]
    rules = snapshot["rules"] if snapshot else []
    for point in points:
        item = {"point_id": point["id"], "kind": point["kind"], "choice": None,
                "status": "UNKNOWN_EVIDENCE", "rule_refs": [], "question": point["question"]}
        code = None
        if point["kind"] != "VALUE_DECISION":
            code = "AUTHORITY_REQUIRED" if point["kind"] in ("AUTHORITY_GRANT", "IMPLEMENTATION_CHOICE") else (
                "TOOL_UNAVAILABLE" if point["kind"] == "CAPABILITY_LIMIT" else "CLAIM_NOT_VERIFIED")
        else:
            target = {"project_id": state["project_id"], **state["context"], "decision_type": point["decision_type"]}
            human = state["human_decisions"].get(point["id"])
            human_valid = (human and human["scope"] == target and human.get("options_hash") == options_contract(point["options"])
                           and human["choice"] in {option["id"] for option in point["options"]})
            relevant = [rule for rule in rules if rule["decision_type"] == point["decision_type"] and rule["validity"] == "CURRENT"]
            matching = [rule for rule in relevant if rule["enforcement"] == "BLOCK" and effective_scope(rule, target)
                        and not exceptions_at(rule, target)]
            matches = snapshot.get("matches", {}).get(point["id"], {}) if snapshot else {}
            advisory_rows = audit_rows(state, snapshot, "assessment", state["assessment_as_of"]) if snapshot else []
            item["advisories"] = [row for row in advisory_rows if row["point_id"] == point["id"]
                                  and (row["enforcement"] in ("SHADOW", "WARN") or row["outcome"] == "EXEMPTED")]
            # Enforced constraints are checked before a later local decision.
            # Changing a decision does not silently retire an existing BLOCK.
            if any(rule["contested"] for rule in matching):
                code = "RULE_CONTESTED"
            elif len({(rule["choice"], options_contract(rule["options"])) for rule in matching}) > 1:
                code = "RULE_CONFLICT"
            elif any(options_contract(rule["options"]) != options_contract(point["options"]) for rule in matching):
                code = "RULE_OPTION_CHANGED"
            elif matching:
                for rule in matching:
                    receipt = matches.get(rule["id"], {})
                    if receipt.get("error"):
                        code = receipt["error"]
                    elif rule["review_after"] <= state["assessment_as_of"]:
                        code = "RULE_ENGINE_CHANGED"
                    elif not rule["check"] or rule["check"]["engine"] != receipt.get("engine"):
                        code = "RULE_ENGINE_CHANGED"
                    elif receipt.get("match") is not True:
                        code = "CROSS_FAILED"
                    if code:
                        break
                if code is None:
                    choice = matching[0]["choice"]
                    if human_valid and human["choice"] != choice:
                        code = "RULE_CONFLICT"
                    else:
                        refs = [ref for rule in matching for ref in rule["history"]]
                        item.update(status="HUMAN_DECIDED" if human_valid else "PRECEDENT_MATCHED", choice=choice,
                                    rule_refs=([human["source_ref"]] if human_valid else []) + refs)
            elif human_valid:
                item.update(status="HUMAN_DECIDED", choice=human["choice"], rule_refs=[human["source_ref"]])
            else:
                exempt = any(rule["enforcement"] == "BLOCK" and exceptions_at(rule, target) for rule in relevant)
                code = "RULE_EXCEPTION_APPLIES" if exempt else (
                    "SCOPE_MISMATCH" if any(rule["enforcement"] == "BLOCK" for rule in relevant) else "VALUE_DECISION_REQUIRED")
            item["scope"] = target
        if code:
            item.update(status=classify_gap(code), reason=code)
            gaps.append({"code": code, "classification": classify_gap(code), "item_id": point["id"],
                         "question": point["question"], "source_ref": state["proposal_ref"], "kind": point["kind"]})
        judgments.append(item)
    return judgments, gaps


def epistemic_axes(code):
    classification = classify_gap(code)
    return {"epistemic_status": "CONTESTED" if classification == "CONTESTED" else "UNKNOWN",
            "blocker": {"STALE_OBSERVATION": "OBSERVATION_STALE", "UNAVAILABLE_CAPABILITY": "CAPABILITY_MISSING",
                        "UNDECIDED_HUMAN": "HUMAN_DECISION_MISSING", "UNSCOPED_RULE": "RULE_SCOPE_UNRESOLVED",
                        "CONTESTED": "NONE"}.get(classification, "EVIDENCE_MISSING")}
