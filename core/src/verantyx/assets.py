"""Sourced, reusable method contracts and failure cases, projected from history.

The catalog is reference data. Retrieving or copying a contract never executes
it, grants a permission, certifies prose, or assesses a person's understanding.
"""
from copy import deepcopy
import base64

from .domain.codec import canonical, decode, digest
from .errors import LedgerError

COLLECTIONS = {
    "VERIFICATION": "verifications", "ORACLE": "oracles", "WORKTREE": "effects",
    "COMMAND": "command_effects", "INTEGRATION": "integrations", "ADOPTION": "adoptions",
}
RECEIPTS = {
    "VerificationRecorded": ("VERIFICATION", "verification_id"),
    "OracleRecorded": ("ORACLE", "oracle_id"), "ExecutionReceipt": ("WORKTREE", "lease_id"),
    "AuthorizationInvalidated": ("WORKTREE", "lease_id"),
    "CommandEffectRecorded": ("COMMAND", "effect_id"),
    "IntegrationChecked": ("INTEGRATION", "integration_id"),
    "IntegrationInvalidated": ("INTEGRATION", "integration_id"),
    "IntegrationReceipt": ("INTEGRATION", "integration_id"),
    "AdoptionReceipt": ("ADOPTION", "adoption_id"),
    "AdoptionInvalidated": ("ADOPTION", "adoption_id"),
}
BOUNDARIES = {
    "en": "Historical contracts and outcomes. Rebind targets and verify scope before reuse; this catalog grants no authority.",
    "ja": "記録された契約と結果です。再利用時は対象と範囲を確認し直してください。この辞書は権限を与えません。",
    "zh-Hans": "这是已记录的契约和结果。复用前须重新绑定对象并核对范围；此目录不授予权限。",
    "ko": "기록된 계약과 결과입니다. 재사용 전에 대상과 범위를 다시 확인해야 하며, 이 목록은 권한을 부여하지 않습니다.",
    "es": "Contratos y resultados históricos. Vincula de nuevo los objetos y comprueba el alcance antes de reutilizarlos; el catálogo no concede autoridad.",
}


def _pick(value, keys):
    return {key: deepcopy(value[key]) for key in keys if key in value}


def _safe_value(value):
    # Scalar measurements can be shown without copying arbitrary target text.
    return value if type(value) in (int, float, bool, type(None)) else {"sha256": digest(value)}


def _plan(item, family):
    return item["lease"] if family == "WORKTREE" else item["plan"]


def _method_id(state, family, item):
    return digest({"project_id": state["project_id"], "run_id": state["run_id"],
                   "family": family, "source_ref": item["source_ref"]})


def _measurements(family, plan, payload):
    result = payload.get("result") or {}
    by_id = {item["id"]: item for item in (plan.get("spec") or {}).get("checks", [])}
    if family == "ORACLE":
        by_id = {item["id"]: item for item in plan["spec"]["cases"]}
    values = []
    for check in result.get("checks", []):
        value = _pick(check, ("id", "passed", "actual_hash", "error", "reason"))
        contract = by_id.get(check["id"], {})
        value.update(_pick(contract, ("kind", "pointer")))
        if "expected" in contract:
            value["expected"] = _safe_value(contract["expected"])
        if family == "VERIFICATION" and contract.get("kind") in ("json.equals", "json.type", "bytes.size") and payload.get("input_base64"):
            from .domain.verification import unseal, _pointer
            raw = unseal(payload["input_base64"])
            try:
                actual = len(raw) if contract["kind"] == "bytes.size" else _pointer(decode(raw), contract["pointer"])
                if contract["kind"] == "json.type":
                    actual = {type(None): "null", bool: "boolean", int: "integer", float: "number", str: "string", list: "array", dict: "object"}[type(actual)]
                if digest(actual) == check.get("actual_hash"):
                    value["observed"] = actual if contract["kind"] == "json.type" else _safe_value(actual)
            except (LedgerError, KeyError, IndexError, TypeError):
                pass
        if family == "ORACLE":
            observation = next((obs for obs in payload.get("observations", []) if obs["case_id"] == check["id"]), None)
            if observation and observation["outcome"] == "RETURNED" and check.get("actual_hash"):
                try:
                    actual = decode(base64.b64decode(observation["stdout_base64"]))["value"]
                    if digest(actual) == check["actual_hash"]:
                        value["observed"] = _safe_value(actual)
                except (LedgerError, KeyError, ValueError):
                    pass
        values.append(value)
    return values


def capture_event(state, event):
    """Called after the existing reducers; keep old failed checks across revisions."""
    from .domain.events import citation
    kind, payload = event["type"], event["payload"]
    if kind == "IntegrationPlanned" and payload["plan"]["conflicts"]:
        family, identity = "INTEGRATION", payload["plan"]["id"]
    elif kind in RECEIPTS:
        family, field = RECEIPTS[kind]
        identity = payload[field]
    else:
        return
    item = state[COLLECTIONS[family]][identity]
    plan = _plan(item, family)
    result = payload.get("result") or {}
    if family == "WORKTREE":
        result = (item.get("receipt") or {}).get("verification") or {}
    closure = payload.get("closure") or result.get("closure")
    outcome = "CONFLICTED" if kind == "IntegrationPlanned" else payload.get("outcome", item["status"])
    reason = payload.get("reason") or result.get("reason")
    checks = _measurements(family, plan, payload)
    unresolved = outcome in ("INVALIDATED", "OUTCOME_UNKNOWN", "CONFLICTED") or closure == "UNKNOWN"
    failed = outcome == "PROCESS_FAILED" or closure in ("REFUTED", "CONTESTED")
    if kind == "IntegrationChecked":
        reason = (payload["result"].get("reason") or ("TEST_ASSERTION_FAILED" if closure == "REFUTED" else None))
    if kind == "IntegrationPlanned":
        reason = "INTEGRATION_CONFLICT"
    if not reason and unresolved:
        reason = next((check.get("reason") or check.get("error") for check in checks if check.get("reason") or check.get("error")), "RESULT_UNAVAILABLE")
    ref = citation(event)
    row = {"id": digest({"source_ref": ref, "kind": "outcome"}), "family": family, "plan_id": identity,
           "method_id": _method_id(state, family, item), "source_ref": ref, "event_type": kind,
           "recorded_at": event["recorded_at"], "revision": event["revision"], "outcome": outcome,
           "closure": closure, "reason": reason, "checks": checks,
           "negative_controls": [_pick(control, ("id", "case_id", "rejected")) for control in result.get("negative_controls", [])],
           "case_kind": "REFUTATION" if closure == "REFUTED" else ("CONTESTED_CHECK" if closure == "CONTESTED" else
                        ("EXECUTION_FAILURE" if failed else ("UNRESOLVED_EXECUTION" if unresolved else "RECORDED_SUCCESS"))),
           "is_failure_case": failed or unresolved, "prose_entailment": "NOT_ASSESSED", "independence": "NOT_ESTABLISHED"}
    if family == "COMMAND":
        row["process"] = _pick(payload.get("process") or {}, ("returncode", "stdout_sha256", "effect_confirmation"))
        row["effect_confirmation"] = "NOT_ASSESSED"
    if family in ("WORKTREE", "INTEGRATION"):
        runner = (result.get("result") or {}) if family == "WORKTREE" else payload.get("result", {})
        if "output" in runner:
            row["test_summary"] = {**_pick(runner, ("passed", "exit", "reason")), "output_hash": digest(runner["output"])}
    if family == "INTEGRATION":
        row.update(_pick(payload, ("files_hash", "commit")))
        if kind == "IntegrationPlanned":
            row["conflicts"] = list(payload["plan"]["conflicts"])
    state.setdefault("asset_outcomes", {})[ref] = row


def _definition(family, plan):
    spec = plan.get("spec") or {}
    if family in ("VERIFICATION", "ORACLE"):
        value = _pick(spec, ("method", "function", "timeout", "max_output"))
        checks = spec.get("checks", spec.get("cases", []))
        value["checks"] = [{**_pick(check, ("id", "kind", "pointer")),
                             **({"expected": _safe_value(check["expected"])} if "expected" in check else {}),
                             **({"input_hash": digest(check["input"])} if "input" in check else {})} for check in checks]
        value["negative_controls"] = [{**_pick(control, ("id", "case_id")), "contract_hash": digest(control)}
                                      for control in spec["negative_controls"]]
        if family == "ORACLE":
            from .domain.oracles import SCOPE
            value.update(method="PYTHON_JSON_IO", scope=SCOPE,
                         negative_control_scope="PARENT_COMPARATOR_REJECTS_DECLARED_COUNTEREXAMPLE_VALUES")
        return value, digest(spec)
    if family == "COMMAND":
        value = {**_pick(spec, ("effect_class", "targets", "timeout", "max_output")),
                 "input_hash": digest(spec["input"]), "executor_hash": plan["executor"]["hash"],
                 "executor_configuration_hash": plan["executor"]["config_sha256"],
                 "isolation": "NONE_TRUSTED_COMMAND"}
        return value, digest({"spec": spec, "executor": plan["executor"]})
    frozen = plan["plan"] if family == "WORKTREE" else plan
    value = {"tests": list(frozen.get("tests", [])), "backend_hash": plan.get("backend_hash"),
             "base_version": plan.get("base_version", plan.get("base_commit")),
             "method": "FROZEN_UNITTEST", "scope": "FIXED_CANDIDATE_TESTS_ONLY"}
    if family == "WORKTREE" and not value["tests"]:
        value.update(method="WORKTREE_PREPARATION", scope="WORKTREE_METADATA_ONLY")
    if family == "ADOPTION":
        value["method"] = "ADOPTION_OF_TESTED_CANDIDATE"
        value["candidate_hash"] = plan["candidate_hash"]
    if family == "INTEGRATION":
        # The destination can contain newer test definitions than base_commit.
        # Bind their exact recorded bytes as well as their paths and Git version.
        value["target_version"] = plan["target_commit"]
        value["test_file_hashes"] = {name: digest(plan["files"][name]) for name in plan["tests"]}
    if family in ("INTEGRATION", "ADOPTION"):
        value.update(_pick(plan, ("mode", "target_ref")))
    return value, digest(value)


def project_assets(state, locale=None):
    """Pure compact projection; expected file bodies and process output stay out."""
    methods, executions, failures, suggestions = [], [], [], []
    if state is None:
        return {"verification_methods": methods, "execution_methods": executions, "failure_cases": failures,
                "reuse_candidates": suggestions}
    history = list(state.get("asset_outcomes", {}).values())
    for family, collection in COLLECTIONS.items():
        for identity, item in state.get(collection, {}).items():
            # Older summary projections may carry only an adoption receipt.
            # Retain their normal delta, but do not invent a method contract.
            if ("lease" if family == "WORKTREE" else "plan") not in item or "source_ref" not in item:
                continue
            plan = _plan(item, family)
            definition, contract_hash = _definition(family, plan)
            ref = item["source_ref"]
            method_id = _method_id(state, family, item)
            outcomes = [row for row in history if row["method_id"] == method_id]
            spec = plan.get("spec") or {}
            target = spec.get("target_path") or spec.get("targets") or definition.get("tests", [])
            name = spec.get("property") or (" / ".join(target) if type(target) is list else target)
            execution_only = family in ("COMMAND", "ADOPTION") or (family == "WORKTREE" and not definition["tests"])
            asset = {"id": method_id, "kind": "EXECUTION_METHOD" if execution_only else "VERIFICATION_METHOD",
                     "family": family, "owner_run": state["run_id"], "plan_id": identity, "name": name,
                     "target": deepcopy(target), "contract_hash": contract_hash, "contract_summary": definition,
                     "status": item["status"], "source_refs": [ref, *[row["source_ref"] for row in outcomes][-31:]],
                     "outcome_count": len(outcomes), "latest_outcome": deepcopy(outcomes[-1]) if outcomes else None,
                     "origin": "RECORDED_EXECUTABLE_CONTRACT", "authority": "REFERENCE_ONLY",
                     "reusable_via": "verification_template_from_asset" if family in ("VERIFICATION", "ORACLE") else "execution_template_from_asset",
                     "reuse_requires": ["EXPLICIT_TARGET_BINDING", "CURRENT_OBSERVATIONS", "NEW_PLAN", "NORMAL_PERMISSION_AND_SCOPE_CHECKS"],
                     "prose_entailment": "NOT_ASSESSED", "independence": "NOT_ESTABLISHED"}
            if family == "ORACLE":
                # Preserve the recorded execution boundary, not a portable
                # Python runner or a transferable authorization.
                asset.update(scope=definition["scope"], target_binding=deepcopy(plan["target"]),
                             claim_binding=_pick(plan, ("claim_hash", "proposal_hash")),
                             oracle_source_refs=list(spec["oracle"]["source_refs"]),
                             engine=deepcopy(plan["engine"]), engine_hash=plan["engine_hash"],
                             origins=deepcopy(plan["origins"]), outcome_history=deepcopy(outcomes),
                             portable_execution=False,
                             remaining="REQUIRES_FRESH_ORACLE_PLAN_AND_SANDBOX",
                             reuse_requires=["EXPLICIT_TARGET_BINDING", "CURRENT_OBSERVATIONS",
                                             "EXPLICIT_CLAIM", "REVIEWED_ORACLE_SOURCES",
                                             "ORIGINAL_ENGINE_IDENTITY", "FRESH_ORACLE_PLAN",
                                             "AVAILABLE_SANDBOX", "NEW_AUTHORIZATION",
                                             "NORMAL_PERMISSION_AND_SCOPE_CHECKS"])
            (executions if asset["kind"] == "EXECUTION_METHOD" else methods).append(asset)
            for outcome in outcomes:
                if outcome["is_failure_case"]:
                    failures.append({**deepcopy(outcome), "kind": "FAILURE_CASE", "owner_run": state["run_id"],
                                     "name": name, "target": deepcopy(target), "contract_hash": contract_hash,
                                     "source_refs": [ref, outcome["source_ref"]], "authority": "REFERENCE_ONLY"})
    for response in state.get("responses", []):
        for index, candidate in enumerate(response["document"].get("reusable_candidates", [])):
            ref = response["source_ref"]
            suggestions.append({**_pick(candidate, ("title", "situation", "procedure", "counterexample")),
                                "id": digest({"response_ref": ref, "candidate_index": index}),
                                "kind": "MODEL_CANDIDATE", "candidate_kind": candidate["kind"],
                                "owner_run": state["run_id"], "locale": response["locale"],
                                "source_refs": list(dict.fromkeys([ref, *candidate["source_refs"]])),
                                **_pick(response, ("mode", "evidence_role", "document_sha256", "basis_revision", "recorded_revision")),
                                "origin": "MODEL_CANDIDATE", "verification": "UNVERIFIED", "enforcement": "OFF",
                                "authority": "REFERENCE_ONLY", "prose_entailment": "NOT_ASSESSED",
                                "reusable_via": "EXPLICIT_REVIEW_AND_NEW_PLAN", "executed": False,
                                "reuse_requires": ["HUMAN_REVIEW", "EXECUTABLE_CONTRACT", "NEW_PLAN", "NORMAL_PERMISSION_AND_SCOPE_CHECKS"]})
    for attempt in state.get("editor_attempts", []):
        validation, ref = attempt["validation"], attempt["source_ref"]
        if validation["status"] == "REPAIR_REQUIRED":
            failures.append({"id": digest({"handoff": ref}), "kind": "FAILURE_CASE", "family": "HANDOFF",
                             "revision": attempt["basis_revision"] + 1,
                             "owner_run": state["run_id"], "source_ref": ref, "source_refs": [ref, state["request_ref"]],
                             "title": attempt["document"]["notes"], "outcome": "INTERPRETATION_DISAGREEMENT",
                             "mismatch_ids": list(validation["mismatch_ids"]),
                             "contract": {"context_sha256": attempt["context_sha256"], "plan_sha256": attempt["plan_sha256"],
                                          "checks": deepcopy(validation["structure"]["十字"]["場所"]["+z/面/北"])},
                             "expectation_origin": "MODEL_INTERPRETATION", "prose_entailment": "NOT_ASSESSED",
                             "authority": "REFERENCE_ONLY", "enforcement": "OFF", "reusable_via": "handoff-editor"})
    # Runtime error captures remain attributed reports, not proof of a model's
    # reasoning or a reusable execution permission.
    for capture in state.get("external_captures", []):
        provenance = capture.get("provenance", {})
        if provenance.get("provider") != "verantyx" or provenance.get("model") != "none":
            continue
        try:
            report = decode(capture["body"])
        except LedgerError:
            continue
        if type(report) is not dict or report.get("format") != "verantyx.work-recovery.v1":
            continue
        summary = report.get("summary")
        if type(summary) is not dict or summary.get("status") not in ("MODEL_CALL_FAILED", "MODEL_OUTCOME_UNKNOWN"):
            continue
        error = summary.get("error")
        if type(error) is not dict or type(error.get("code")) is not str:
            continue
        ref = capture["source_ref"]
        failures.append({"id": digest({"model_failure_ref": ref}), "kind": "FAILURE_CASE",
                         "family": "MODEL_CALL", "owner_run": state["run_id"],
                         "revision": capture["basis_revision"] + 1,
                         "source_ref": ref, "source_refs": [state["request_ref"], ref],
                         "title": "モデル処理の失敗・結果不明", "outcome": summary["status"],
                         "closure": "UNKNOWN", "reason": error["code"],
                         "error": deepcopy(error), "origin": "ATTRIBUTED_RUNTIME_REPORT",
                         "case_kind": "REPORTED_PROCESS_FAILURE", "prose_entailment": "NOT_ASSESSED",
                         "authority": "REFERENCE_ONLY", "enforcement": "OFF",
                         "automatic_retry": False, "reusable_via": "EXPLICIT_REVIEW_OF_RECORDED_FAILURE"})
    from .external_capture import project_assets as external_assets
    suggestions.extend(external_assets(state))
    return {"verification_methods": methods, "execution_methods": executions, "failure_cases": failures,
            "reuse_candidates": suggestions}


def _states(store):
    snapshot = store.project_snapshot()
    return snapshot["events"], snapshot["states"]


def get_asset(store, asset_id):
    """Resolve an exact asset against this local ledger, never a caller-made object."""
    from .adapters.proposal_validation import valid_id
    if not valid_id(asset_id):
        raise LedgerError("ARGUMENTS")
    _, states = _states(store)
    for state in states:
        for items in project_assets(state).values():
            for item in items:
                if item["id"] == asset_id:
                    return item
    raise LedgerError("ASSET_NOT_FOUND")


def _asset_plan(store, asset_id):
    """Resolve only recorded executable contracts, including linked failures."""
    asset = get_asset(store, asset_id)
    if (asset.get("kind") == "FAILURE_CASE" and asset.get("family") in COLLECTIONS
            and asset.get("method_id")):
        asset = get_asset(store, asset["method_id"])
    # HANDOFF failures and model suggestions are useful references, but do not
    # supply a stored verification or execution method for either template API.
    if (asset.get("kind") not in ("VERIFICATION_METHOD", "EXECUTION_METHOD")
            or asset.get("family") not in COLLECTIONS):
        raise LedgerError("ASSET_NOT_REUSABLE", {
            "asset_id": asset["id"], "kind": asset.get("kind"),
            "family": asset.get("family"), "reusable_via": asset.get("reusable_via"),
        })
    from .kernel.reducer import replay
    state = replay(store.events(asset["owner_run"]))
    item = state[COLLECTIONS[asset["family"]]][asset["plan_id"]]
    return asset, _plan(item, asset["family"])


def verification_template_from_asset(store, asset_id, *, claim_id, target_path, oracle_source_refs=(), reproduces=None):
    """Return a full executable spec for an explicit new plan; perform no I/O check."""
    asset, plan = _asset_plan(store, asset_id)
    family = asset["family"]
    if family not in ("VERIFICATION", "ORACLE"):
        raise LedgerError("ASSET_NOT_REUSABLE")
    if type(oracle_source_refs) not in (list, tuple):
        raise LedgerError("ARGUMENTS")
    spec = deepcopy(plan["spec"])
    spec.update(claim_id=claim_id, target_path=target_path)
    spec["oracle"]["source_refs"] = list(oracle_source_refs)
    if family == "VERIFICATION":
        if spec["method"] == "REPRODUCTION" and reproduces is None:
            raise LedgerError("ARGUMENTS")
        spec["reproduces"] = reproduces
        from .domain.verification import validate_spec
    else:
        if reproduces is not None:
            raise LedgerError("ARGUMENTS")
        from .domain.oracles import validate_spec
    validate_spec(spec)
    result = {"schema_version": 1, "ok": True, "asset_id": asset["id"], "family": family,
              "source_refs": asset["source_refs"], "source_contract_hash": asset["contract_hash"],
              "spec": spec, "spec_hash": digest(spec), "command": "verify-plan" if family == "VERIFICATION" else "oracle-plan",
              "executed": False, "authority": "REFERENCE_ONLY", "new_target_and_oracle_sources_require_review": True}
    if family == "ORACLE":
        result.update(portable_execution=False, remaining=asset["remaining"],
                      reuse_requires=list(asset["reuse_requires"]),
                      source_engine=deepcopy(plan["engine"]), source_engine_hash=plan["engine_hash"])
    return result


def execution_template_from_asset(store, asset_id):
    """Return an exact plan recipe and bindings; no command, Git, or tests are run."""
    asset, plan = _asset_plan(store, asset_id)
    family = asset["family"]
    if family in ("VERIFICATION", "ORACLE"):
        raise LedgerError("ASSET_NOT_REUSABLE")
    if family == "COMMAND":
        recipe = {"command": "command-propose", "spec": deepcopy(plan["spec"]),
                  "expected_executor_hash": plan["executor"]["hash"],
                  "requires": ["EXPLICIT_COMMAND_CONFIG", "NEW_RUN", "NEW_OBSERVATIONS", "NEW_AUTHORIZATION"]}
    else:
        definition, _ = _definition(family, plan)
        recipe = {"command": "integration-plan" if family == "INTEGRATION" else ("adoption-propose" if family == "ADOPTION" else "authorize"),
                  "tests": definition["tests"], "base_version": definition["base_version"], "backend_hash": definition["backend_hash"],
                  "contract_summary": definition,
                  "requires": ["EXPLICIT_CANDIDATE_OR_ADOPTION", "CURRENT_GIT_CONTEXT", "NEW_PLAN", "NEW_AUTHORIZATION"]}
        if family == "WORKTREE":
            recipe["proposed_action"] = {"tool_id": plan["plan"]["tool_id"], "arguments": {
                "point_id": plan["plan"]["point_id"], "destination": "shared"}}
            if plan["plan"]["tool_id"] == "writer.apply":
                recipe["proposed_action"]["arguments"].update(files=deepcopy(plan["plan"]["files"]), tests=list(plan["plan"]["tests"]))
    return {"schema_version": 1, "ok": True, "asset_id": asset["id"], "family": family,
            "source_refs": asset["source_refs"], "source_contract_hash": asset["contract_hash"],
            "recipe": recipe, "executed": False, "authority": "REFERENCE_ONLY"}


def project_catalog(store, state, locale, query=None, *, limit=24, max_bytes=65536):
    """Bounded cross-task dictionary with exact canonical option contracts.

    Currentness is as of recorded project time, not a hidden wall clock. A new
    request provides a fresh recorded time; the execution gate still rechecks.
    """
    if locale not in BOUNDARIES or (query is not None and (type(query) is not str or len(query) > 512)):
        raise LedgerError("ARGUMENTS")
    if type(limit) is not int or not 1 <= limit <= 64 or type(max_bytes) is not int or not 2048 <= max_bytes <= 262144:
        raise LedgerError("ARGUMENTS")
    if state is not None and state["project_id"] != store.project_id:
        raise LedgerError("STORE_PROJECT")
    snapshot = store.project_snapshot()
    states = snapshot["states"]
    from .domain.rule_extensions import options_contract, effective_scope, exceptions_at, config_hash
    as_of = snapshot["as_of"]
    categories = {"rules": [], "verification_methods": [], "execution_methods": [], "failure_cases": [],
                  "reuse_candidates": [], "learning": []}
    for rule in snapshot["rules"].values():
        if rule["validity"] != "CURRENT" or rule["enforcement"] not in ("SHADOW", "WARN", "BLOCK") or rule["contested"]:
            continue
        if as_of is not None and rule["review_after"] <= as_of:
            continue
        target = {"project_id": store.project_id, **(state or {}).get("context", {}), "decision_type": rule["decision_type"]}
        applicable = bool(state and effective_scope(rule, target) and not exceptions_at(rule, target))
        row = {**_pick(rule, ("id", "decision_type", "choice", "options", "scope", "maturity", "enforcement", "validity", "review_after", "owner_run")),
               "kind": "CANONICAL_DECISION_CONTRACT", "options_contract_hash": options_contract(rule["options"]),
               "rule_config_hash": config_hash(rule), "source_refs": [rule["human_ref"], rule["precedent_ref"], *rule["history"][-16:]],
               "applicable_to_requested_context": applicable, "authority": "REFERENCE_ONLY"}
        if rule.get("scope_policy"):
            policy = rule["scope_policy"]
            row["scope_policy"] = {"scope": deepcopy(policy["scope"]),
                                   "exceptions": [_pick(item, ("id", "scope")) for item in policy["exceptions"]],
                                   "contract_hash": digest(policy)}
        categories["rules"].append(row)
    from .learning import learning_references
    for current in states:
        for category, items in project_assets(current, locale).items():
            categories[category].extend(items)
        categories["learning"].extend(learning_references(current, explicit_lookup=bool(query and query.strip())))
    tokens = (query or "").casefold().split()
    result = {"schema_version": 1, "format": "verantyx.project-catalog.v1", "project_id": store.project_id,
              "locale": locale, "as_of": as_of, "currentness": "AS_OF_RECORDED_PROJECT_TIME",
              "authority": "REFERENCE_ONLY", "boundary": BOUNDARIES[locale], "query": query,
              "project_revision": snapshot["project_revision"], "truncated": {}, **{key: [] for key in categories}}
    requested_paths = set((state or {}).get("read_scope", []))
    requested_decisions = {point["decision_type"] for point in ((state or {}).get("proposal") or {}).get("decision_points", [])}
    contexts = {current["run_id"]: current["context"] for current in states}

    def priority(row):
        if row.get("kind") == "CANONICAL_DECISION_CONTRACT":
            relevant = row["applicable_to_requested_context"]
            detail = row["decision_type"] in requested_decisions
        else:
            target = row.get("target", [])
            paths = {target} if type(target) is str else set(target) if type(target) is list else set()
            relevant = bool(paths & requested_paths)
            # Exact recorded context is a retrieval hint, never an applicability grant.
            detail = bool(state and contexts.get(row.get("owner_run")) == state["context"])
        return (not relevant, not detail, row.get("owner_run") != (state or {}).get("run_id"), row["id"])

    for category, rows in categories.items():
        filtered = [row for row in rows if not tokens or all(token in canonical(row).casefold() for token in tokens)]
        filtered.sort(key=priority)
        result["truncated"][category] = len(filtered)
        for row in filtered[:limit]:
            result[category].append(row)
            result["truncated"][category] -= 1
            if len(canonical(result).encode("utf-8")) > max_bytes:
                result[category].pop()
                result["truncated"][category] += 1
    # Account for later truncation counters, including multibyte locales.
    while len(canonical(result).encode("utf-8")) > max_bytes:
        category = next((key for key in reversed(categories) if result[key]), None)
        if category is None:
            raise LedgerError("DOCUMENT_LIMIT")
        result[category].pop()
        result["truncated"][category] += 1
    return result
