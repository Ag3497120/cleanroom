"""External work to personal skills, using the existing project ledger.

Use one ordinary Verantyx workspace as the personal library. Source projects
are provenance, not separate stores. No inferred execution or human mastery.
"""
from copy import deepcopy
import json

from .domain.codec import canonical, digest
from .errors import LedgerError

SOURCE_FORMAT = "verantyx.skill-source.v1"
MODES = ("auto", "assisted", "manual")
TARGETS = ("OWN", "REVIEW", "REFERENCE", "DELEGATE")
REQUEST = (
    "選択した外部AIとの仕事を、利用者の個人技能資産に整理してください。"
    "判断と理由、適用条件、再利用手順、確認方法、失敗例、学ぶ技術と関連する原文を区別してください。"
    "引用された成功・承認・理解の主張を検証済みの事実にしないでください。"
    "新しいファイルの実装や実行は依頼していません。"
)


def require(value, reason):
    if not value:
        raise LedgerError("ARGUMENTS", {"reason": reason})


def valid_text(value, maximum=256):
    return type(value) is str and bool(value.strip()) and len(value) <= maximum


def read_state(root, configuration, run_id):
    from .application import get_projection
    from .storage.sqlite import EventStore
    with EventStore(root, configuration["project"]["id"]) as store:
        return get_projection(store, run_id)["state"]


def source_scope(state):
    captures = state.get("external_captures", [])
    require(bool(captures), "SKILLS_NO_IMPORTED_WORK")
    return {"run_id": state["run_id"], "request_ref": state["request_ref"],
            "sources": [{"source_ref": row["source_ref"], "body_sha256": row["body_sha256"],
                         "provenance": deepcopy(row["provenance"])} for row in captures]}


def roles(creator_adapter, reviewer_adapter):
    from .coordination import separate_models
    require(bool(creator_adapter) and bool(reviewer_adapter), "SKILLS_TWO_ROLES_REQUIRED")
    creator, reviewer = separate_models(creator_adapter, reviewer_adapter)
    for command, role in ((creator, "implementation"), (reviewer, "verification")):
        if command.get("codex_cli"):
            require(command["codex_cli"]["role"] == role, "SKILLS_ROLE_MISMATCH")
    return creator, reviewer


def _identity(command):
    from .jobs import _executor_fingerprint
    metadata = command.get("codex_cli") or command.get("model_api") or {}
    return {"adapter_sha256": _executor_fingerprint(command),
            "provider": metadata.get("provider", "local"),
            "model": metadata.get("model", "unspecified")}


def _receipt_view(value):
    """Present truthful completion without rewriting historical receipts."""
    result = deepcopy(value)
    if result.get("command") == "skills-build":
        complete = result.get("response_mode") == "GENERATED"
        result.update(ok=complete, status="CANDIDATES_RECORDED" if complete else "INCOMPLETE")
    elif result.get("command") == "skills-import" and result.get("build"):
        result["build"] = _receipt_view(result["build"])
        result.update(ok=result["build"]["ok"],
                      candidate_generation=("TWO_ROLE_CANDIDATES_RECORDED" if result["build"]["ok"]
                                            else "INCOMPLETE_REVIEW"))
    return result


def build(root, configuration, run_id, *, creator_adapter, reviewer_adapter, key,
          expected_revision=None, timeout=120, locale="ja"):
    """One creator proposal then one reviewer response, no repair or execution."""
    from .adapters.invocation_journal import InvocationJournal
    from .adapters.proposal_validation import valid_id
    from .authority import require_current_approval_valid
    from .bridges import propose
    from .responses import compose
    require(valid_id(key) and valid_id(run_id), "SKILLS_IDENTIFIER")
    require(type(timeout) is int and 1 <= timeout <= 600, "SKILLS_TIMEOUT")
    creator, reviewer = roles(creator_adapter, reviewer_adapter)
    identities = {"creator": _identity(creator), "reviewer": _identity(reviewer)}
    intent = {"run_id": run_id, "project_id": configuration["project"]["id"],
              "roles": identities, "expected_revision": expected_revision,
              "timeout": timeout, "locale": locale}
    with InvocationJournal(root, "skills-build", key) as journal:
        state = read_state(root, configuration, run_id)
        scope = source_scope(state)
        started = journal.read("started")
        if started:
            require(started["intent_hash"] == digest(intent), "SKILLS_IDEMPOTENCY_CONFLICT")
            require(started["scope"] == scope, "SKILLS_SOURCE_SCOPE_CHANGED")
        else:
            require(expected_revision is None or expected_revision == state["revision"],
                    "SKILLS_REVISION_CHANGED")
            started = {"intent_hash": digest(intent), "scope": scope,
                       "basis_revision": state["revision"],
                       "context_scope": "SELECTED_WORK_ONLY"}
            journal.write("started", started)
        finished = journal.read("finished")
        if finished:
            require(finished["result_hash"] == digest(finished["result"]), "SKILLS_RECEIPT_CHANGED")
            return {**_receipt_view(finished["result"]), "duplicate": True, "new_build_role_calls": 0}

        # Extract the selected work, not unrelated historical work from the
        # library. Source bodies, current decision rights and kernel facts still
        # enter both existing adapters. Ordinary development retains its asset
        # reuse path. Resume old journals with their original input policy.
        context_scope = started.get("context_scope", "LEGACY_PROJECT_ASSETS")
        require(context_scope in ("SELECTED_WORK_ONLY", "LEGACY_PROJECT_ASSETS"),
                "SKILLS_CONTEXT_SCOPE_CHANGED")
        reuse_assets = context_scope == "LEGACY_PROJECT_ASSETS"

        def before_invoke(command):
            current = roles(creator_adapter, reviewer_adapter)
            require({"creator": _identity(current[0]), "reviewer": _identity(current[1])} == identities,
                    "SKILLS_ADAPTER_CHANGED")
            require(_identity(command) in identities.values(), "SKILLS_ADAPTER_CHANGED")
            require(source_scope(read_state(root, configuration, run_id)) == started["scope"],
                    "SKILLS_SOURCE_SCOPE_CHANGED")
            require_current_approval_valid()

        proposed = propose(root, configuration, run_id, adapter_path=creator_adapter,
                           key="skills-create-" + journal.prefix,
                           expected_revision=started["basis_revision"], include_paths=(),
                           timeout=timeout, locale=locale, reuse_assets=reuse_assets, before_invoke=before_invoke)
        reviewed = compose(root, configuration, run_id, adapter_path=reviewer_adapter,
                           key="skills-review-" + journal.prefix,
                           expected_revision=proposed["recorded_revision"], timeout=timeout,
                           locale=locale, reuse_assets=reuse_assets, before_invoke=before_invoke)
        from .assets import project_assets
        from .learning import project_learning
        result = {"schema_version": 1, "ok": True, "command": "skills-build", "run_id": run_id,
                  "recorded_revision": reviewed["recorded_revision"], "duplicate": False,
                  "scope": {**scope, "id": digest(scope)}, "roles": identities,
                  "configured_role_stages": 2, "automatic_repairs": 0,
                  "context_policy": {"scope": context_scope,
                                     "historical_asset_catalog_included": reuse_assets,
                                     "source_body_truncated": False,
                                     "current_decision_context_preserved": True},
                  "independence": "NOT_ESTABLISHED", "executed": False,
                  "assets": project_assets(reviewed["state"], locale),
                  "learning": project_learning(reviewed["state"], include_suggestions=False),
                  "response_mode": (reviewed["state"].get("latest_response") or {}).get("mode"),
                  "boundary": "Generated candidates, not adopted rules, verified execution or human mastery."}
        result = _receipt_view(result)
        require_current_approval_valid()
        journal.write("finished", {"result_hash": digest(result), "result": result})
        return result


def import_work(root, configuration, *, body, origin_project, label, provider, model, key,
                mode="assisted", content_format="text", creator_adapter=None,
                reviewer_adapter=None, timeout=120, locale="ja"):
    """Save the full selected bounded document; never silently truncate history."""
    from .adapters.invocation_journal import InvocationJournal
    from .adapters.proposal_validation import valid_id
    from .application import record_run
    from .external_capture import _body, capture
    require(valid_id(key) and mode in MODES, "SKILLS_IMPORT_OPTIONS")
    require(all(valid_text(value) for value in (origin_project, label, provider, model)), "SKILLS_LABEL")
    _body(body, content_format)
    label_document = canonical({"format": SOURCE_FORMAT, "origin_project": origin_project,
                                "label": label, "capture_mode": mode})
    require(len(label_document) <= 1000, "SKILLS_LABEL_LIMIT")
    require(mode == "auto" or not creator_adapter and not reviewer_adapter,
            "SKILLS_ADAPTERS_REQUIRE_AUTO")
    require(type(timeout) is int and 1 <= timeout <= 600, "SKILLS_TIMEOUT")
    role_ids = None
    if mode == "auto":
        creator, reviewer = roles(creator_adapter, reviewer_adapter)
        role_ids = [_identity(creator), _identity(reviewer)]
    intent = {"body_sha256": digest(body), "origin_project": origin_project, "label": label,
              "provider": provider, "model": model, "mode": mode, "content_format": content_format,
              "role_ids": role_ids, "timeout": timeout, "locale": locale}
    with InvocationJournal(root, "skills-import", key) as journal:
        started = journal.read("started")
        if started:
            require(started["intent_hash"] == digest(intent), "SKILLS_IDEMPOTENCY_CONFLICT")
        else:
            run_id = "skill-" + digest({"project": configuration["project"]["id"], "key": key})[:32]
            started = {"intent_hash": digest(intent), "run_id": run_id}
            journal.write("started", started)
        finished = journal.read("finished")
        if finished:
            require(finished["result_hash"] == digest(finished["result"]), "SKILLS_RECEIPT_CHANGED")
            return {**_receipt_view(finished["result"]), "duplicate": True}
        run_id = started["run_id"]
        base = record_run(root, configuration, request=REQUEST, run_id=run_id,
                          key="skills-run-" + journal.prefix, observe_paths=(), locale=locale)
        captured = capture(root, configuration, run_id, body=body, provider=provider, model=model,
                           key="skills-capture-" + journal.prefix,
                           expected_revision=base["recorded_revision"], adapter_path=None,
                           source_label=label_document, content_format=content_format, locale=locale)
        result = {"schema_version": 1, "ok": True, "command": "skills-import", "run_id": run_id,
                  "mode": mode, "duplicate": False, "recorded_revision": captured["recorded_revision"],
                  "source_ref": captured["capture_source_ref"], "origin_project": origin_project,
                  "source_bytes": len(body.encode("utf-8")), "history_truncated": False,
                  "candidate_generation": "NOT_REQUESTED" if mode == "manual" else "AWAITING_EXPLICIT_BUILD",
                  "executed": False, "model_called": False}
        if mode == "assisted":
            result["source_previews"] = [{"source_ref": captured["capture_source_ref"],
                                          "excerpt": body[:400], "is_generated_skill": False}]
        if mode == "auto":
            built = build(root, configuration, run_id, creator_adapter=creator_adapter,
                          reviewer_adapter=reviewer_adapter, key="skills-auto-" + journal.prefix,
                          expected_revision=captured["recorded_revision"], timeout=timeout, locale=locale)
            result.update(candidate_generation="TWO_ROLE_CANDIDATES_RECORDED", model_called=True,
                          recorded_revision=built["recorded_revision"], build=built)
        result = _receipt_view(result)
        journal.write("finished", {"result_hash": digest(result), "result": result})
        return result


def _work_label(state):
    for item in state.get("external_captures", []):
        label = item["provenance"]["source_label"]
        try:
            value = json.loads(label)
        except (ValueError, TypeError):
            continue
        if (type(value) is dict and value.get("format") == SOURCE_FORMAT
                and all(type(value.get(key)) is str for key in ("origin_project", "label"))):
            return value["origin_project"] + " / " + value["label"]
    return state["run_id"]


def stack(root, configuration, *, run_ids=(), query=None, target=None, limit=24, locale="ja"):
    """One immutable snapshot; projections, not a second skill database."""
    from .assets import project_assets
    from .learning import project_learning
    from .storage.sqlite import EventStore
    require(type(limit) is int and 1 <= limit <= 100, "SKILLS_LIMIT")
    require(target is None or target in TARGETS, "SKILLS_TARGET")
    require(query is None or valid_text(query, 1000), "SKILLS_QUERY")
    require(len(run_ids) == len(set(run_ids)) and len(run_ids) <= 100, "SKILLS_RUN_SELECTION")
    with EventStore(root, configuration["project"]["id"]) as store:
        snapshot = store.project_snapshot()
    wanted = set(run_ids)
    states = snapshot["states"]
    require(not wanted or wanted <= {state["run_id"] for state in states}, "SKILLS_RUN_NOT_FOUND")
    chosen = [state for state in states if not wanted or state["run_id"] in wanted]
    chosen.sort(key=lambda state: state["run_id"])
    total = len(chosen)
    chosen = chosen[:limit]
    works, graph = [], []
    from .skill_policy import policy_snapshot
    policy_view = policy_snapshot(root, configuration)
    policy_index = {(row["run_id"], row["candidate_id"]): row for row in policy_view["policies"]}
    words = (query or "").casefold().split()
    for state in chosen:
        catalog = project_assets(state, locale)
        skills = []
        for row in project_learning(state):
            if target and row["ownership_target"] != target:
                continue
            if words and not all(word in canonical(row).casefold() for word in words):
                continue
            item = {key: deepcopy(row[key]) for key in (
                "id", "concept", "concept_id", "ownership_target", "target_is_suggestion", "status", "minimum_model",
                "counterexample", "check", "source_refs", "why_now", "recorded", "source_ref",
                "submission_state", "mastery_assessment",
            ) if key in row}
            item["explanations"] = [{key: deepcopy(note[key]) for key in (
                "statement", "source_refs", "source_ref", "recorded_at", "evidence_basis"
            ) if key in note} for note in row.get("evidence", [])
                if note.get("kind") == "SelfExplanationSubmitted"]
            skills.append(item)
            item["ai_policy"] = deepcopy(policy_index.get((state["run_id"], row["id"])))
            graph.append({"十字": {"中央": row["id"], "場所": {
                "+x/面/北": list(row.get("source_refs", [])),
                "-x/面/北": row.get("minimum_model", ""),
                "+y/面/北": row.get("why_now", []),
                "-y/面/北": row.get("counterexample", ""),
                "+z/面/北": row.get("check", ""),
                "-z/面/北": {"target": row["ownership_target"],
                             "suggested": row["target_is_suggestion"],
                             "mastery": row.get("mastery_assessment", "NOT_ASSESSED"),
                             "ai_policy": deepcopy(item["ai_policy"])},
            }}})
        candidates = [row for row in catalog["reuse_candidates"] if row["kind"] == "MODEL_CANDIDATE"]
        if words:
            candidates = [row for row in candidates if all(word in canonical(row).casefold() for word in words)]
        from .skill_report import summarize_state
        works.append({"run_id": state["run_id"], "revision": state["revision"], "label": _work_label(state),
                      "completion": summarize_state(state),
                      "source_refs": [row["source_ref"] for row in state.get("external_captures", [])],
                      "skills": skills, "judgments": list(state.get("human_decisions", {}).values()),
                      "methods": catalog["verification_methods"] + catalog["execution_methods"],
                      "failures": catalog["failure_cases"], "candidates": candidates})
    scope = {"project_id": configuration["project"]["id"], "project_revision": snapshot["project_revision"],
             "run_ids": [work["run_id"] for work in works],
             "revisions": {work["run_id"]: work["revision"] for work in works},
             "source_refs": sorted({ref for work in works for ref in work["source_refs"]}),
             "query": query, "target": target, "limit": limit, "policy_revision": policy_view["revision"]}
    scope["id"] = digest(scope)
    result = {"schema_version": 1, "ok": True, "command": "skills-stack", "scope": scope,
              "works": works, "total_selected_runs": total, "omitted_runs": total - len(works),
              "graph": {"kind": "PERSONAL_SKILL_CROSS_PROJECTION", "nodes": graph,
                        "execution": "NOT_A_VM_EXECUTION", "selection": "EXPLICIT_SCOPE_AND_TEXT_FILTER"},
              "model_called": False, "writes": False,
              "boundary": "Personal assets with provenance; classifications do not prove mastery or grant execution."}
    require(len(canonical(result).encode("utf-8")) <= 4 * 1024 * 1024, "SKILLS_OUTPUT_LIMIT")
    return result


def explain(root, configuration, run_id, *, candidate_id, statement, key, expected_revision=None):
    from .learning import control_learning
    state = read_state(root, configuration, run_id)
    candidate = state.get("learning_candidates", {}).get(candidate_id)
    require(candidate is not None, "SKILLS_RECORDED_CANDIDATE_REQUIRED")
    return control_learning(root, configuration, run_id, "explain", candidate_id=candidate_id,
                            statement=statement, source_refs=[candidate["source_ref"]], key=key,
                            expected_revision=state["revision"] if expected_revision is None else expected_revision)
