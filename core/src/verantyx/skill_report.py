"""Read-only three-way ownership report over the existing ledger.

Cross routes are recorded execution witnesses, not extra votes or a new
knowledge store. Human learning choices never grant execution authority.
"""
from copy import deepcopy

from .domain.codec import digest
from .personal_skills import require


def summarize_state(state):
    assessment = state.get("assessment") or {}
    response = state.get("latest_response") or {}
    cross = response.get("response_structure") or {}
    outcomes = list(state.get("asset_outcomes", {}).values())
    return {
        "build": assessment.get("build", "UNKNOWN"),
        "evidence": assessment.get("evidence", "UNKNOWN"),
        "ownership": assessment.get("ownership", "UNASSESSED"),
        "strategy": assessment.get("strategy", "UNKNOWN"),
        "response_mode": response.get("mode", "NOT_REQUESTED"),
        "response_ref": response.get("source_ref"),
        "response_revision": response.get("recorded_revision"),
        "current_revision": state["revision"],
        "proposal_recorded": state.get("proposal") is not None,
        "gaps": [{key: deepcopy(row.get(key)) for key in
                  ("code", "item_id", "source_ref", "classification", "blocker")}
                 for row in assessment.get("gaps", [])],
        "question": deepcopy(assessment.get("question")),
        "outcomes": [{key: deepcopy(row.get(key)) for key in
                     ("id", "source_ref", "outcome", "closure", "reason", "is_failure_case",
                      "case_kind", "method_id", "prose_entailment", "independence")}
                    for row in outcomes],
        "cross": {key: deepcopy(cross.get(key)) for key in
                  ("mode", "scope", "result", "vm", "identity", "structure", "input_hash", "assessment_hash")},
        "cross_currentness": "RECORDED_RESPONSE_BASIS_NOT_A_FRESH_AUTHORIZATION",
        "mastery_certified_by_this_report": False,
    }


def make_report(root, configuration, *, run_ids=(), query=None, limit=24, locale="ja"):
    from .personal_skills import stack
    from .skill_policy import policy_snapshot
    library = stack(root, configuration, run_ids=run_ids, query=query, limit=limit, locale=locale)
    policies = policy_snapshot(root, configuration)
    works, learning, delegated = [], [], []
    totals = {"work_items": 0, "human_judgments": 0, "recorded_methods": 0,
              "failure_cases": 0, "reuse_candidates": 0, "explicit_skill_policies": 0,
              "recorded_bounded_outcomes": 0, "recorded_refutations": 0}
    for work in library["works"]:
        current_policies = [deepcopy(row) for row in policies["policies"]
                            if row["run_id"] == work["run_id"]]
        by_candidate = {row["candidate_id"]: row for row in current_policies}
        skills = []
        for candidate in work["skills"]:
            policy = by_candidate.get(candidate["id"])
            item = {**deepcopy(candidate), "run_id": work["run_id"], "work_label": work["label"],
                    "system_capture": ["REFERENCE"] + (["SCOPED_POLICY"] if policy else []),
                    "policy": policy, "execution_permission_from_learning_target": False}
            if policy and policy["asset_ids"]:
                item["system_capture"].append("EXPLICIT_CHECK_BINDING")
            skills.append(item)
            if (not candidate.get("target_is_suggestion", True)
                    and candidate["ownership_target"] == "DELEGATE"):
                delegated.append(item)
            elif candidate["ownership_target"] in ("OWN", "REVIEW"):
                learning.append(item)
        completion = work["completion"]
        totals["work_items"] += 1
        totals["human_judgments"] += len(work["judgments"])
        totals["recorded_methods"] += len(work["methods"])
        totals["failure_cases"] += len(work["failures"])
        totals["reuse_candidates"] += len(work["candidates"])
        totals["explicit_skill_policies"] += len(current_policies)
        totals["recorded_bounded_outcomes"] += sum(
            row["closure"] == "BOUNDED" for row in completion["outcomes"])
        totals["recorded_refutations"] += sum(
            row["closure"] == "REFUTED" for row in completion["outcomes"])
        works.append({**work, "skills": skills, "policies": current_policies})
    scope = {**library["scope"], "policy_revision": policies["revision"]}
    scope["id"] = digest(scope)
    return {
        "schema_version": 1, "ok": True, "command": "skills-report", "scope": scope,
        "works": works, "totals": totals, "omitted_runs": library["omitted_runs"],
        "human_next": learning[:3], "human_next_omitted": max(0, len(learning) - 3),
        "explicitly_delegated": delegated, "model_calls": 0, "writes": False,
        "capture_coverage": "THIS_KERNEL_AND_EXPLICIT_IMPORTS_ONLY",
        "boundary": (
            "Historical scoped evidence is not general correctness. Learning choices and self-explanations "
            "are not mastery certification. Structural agreement is not independent-source agreement. "
            "Unknown judgments stay unknown; this report does not authorize any action."),
    }


def display_report(result, locale="ja"):
    from .cli import visible
    print("\nPROJECT / SYSTEM / HUMAN")
    print("AIとの仕事から、次回使える判断と、自分に残す理解を回収します。")
    for work in result["works"]:
        completion = work["completion"]
        print("\n" + visible(work["label"]))
        print("  元の仕事: BUILD=" + completion["build"] + " / EVIDENCE=" + completion["evidence"]
              + " / OWNERSHIP=" + completion["ownership"])
        print("  回答=" + completion["response_mode"] + " / 判断=" + str(len(work["judgments"]))
              + " / 検証・実行方法=" + str(len(work["methods"])) + " / 失敗=" + str(len(work["failures"])))
        cross = completion["cross"]
        if cross.get("mode"):
            route = (cross.get("result") or {}).get("route", "UNKNOWN")
            vm = cross.get("vm") or {}
            print("  構造体: " + cross["mode"] + " / " + str(route)
                  + " / 実行証跡=" + str(vm.get("status", "NOT_RECORDED")))
            print("  構造体の経路は回答時点の記録です。現在の実行許可ではありません。")
        if completion["gaps"]:
            print("  未解決: " + ", ".join(sorted({str(row["code"]) for row in completion["gaps"]})))
        for item in work["skills"]:
            selected = "候補" if item.get("target_is_suggestion", True) else "本人の選択"
            print("  " + visible(item["concept"]) + " / " + item["ownership_target"] + " / " + selected)
            print("    システム側: " + ", ".join(item["system_capture"]))
            if item.get("policy"):
                policy = item["policy"]
                print("    適用範囲: " + visible(", ".join(policy["paths"]))
                      + " / " + policy["reuse_mode"])
    counts = result["totals"]
    print("\nSYSTEM: 保存方法=" + str(counts["recorded_methods"])
          + " / 範囲付き方針=" + str(counts["explicit_skill_policies"])
          + " / 有限条件での成功履歴=" + str(counts["recorded_bounded_outcomes"])
          + " / 反証履歴=" + str(counts["recorded_refutations"]))
    print("\nHUMAN: 今回表示する学習候補は最大3件。学習を完了条件にはしません。")
    for index, item in enumerate(result["human_next"], 1):
        print(str(index) + ". " + visible(item["concept"]))
        reason = item.get("why_now") or []
        print("  きっかけ: " + visible("; ".join(reason) if isinstance(reason, list) else str(reason)))
        print("  最小限の理解: " + visible(item.get("minimum_model", "")))
        print("  反例: " + visible(item.get("counterexample", "")))
        print("  自分で確かめる問い: " + visible(item.get("check", "")))
    print("明示的に委譲した項目: " + str(len(result["explicitly_delegated"]))
          + " / 追加の学習候補: " + str(result["human_next_omitted"]))
    if result["omitted_runs"]:
        print("未表示の仕事: " + str(result["omitted_runs"]) + "。--run または --limit で選択できます。")
    print("このレポートのモデル呼出し: 0。保存・説明・委譲は、習得認定や包括的実行許可ではありません。")
