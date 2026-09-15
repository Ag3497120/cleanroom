"""Owner facts and AI interpretations remain distinct in every projection."""
from copy import deepcopy


def summaries(snapshot, legacy=()):
    by_id = {row["run_id"]: row for row in legacy}
    for state in snapshot["states"]:
        work = state.get("work_result")
        if not work:
            continue
        reflection = (state.get("work_reflections") or [{}])[-1]
        by_id[state["run_id"]] = {
            "run_id": state["run_id"], "label": state["request"][:160],
            "request": state["request"], "status": work["status"],
            "artifact_directory": work["artifact_directory"] or None,
            "last_recorded_at": reflection.get("recorded_at", work["recorded_at"]),
            "revision": state["revision"], "checks": [], "methods": 0,
            "failures": work["tool_counts"]["refused"],
            "reflection_status": reflection.get("status", "PENDING"),
            "work_plane": True,
        }
    return sorted(by_id.values(), key=lambda row: row.get("last_recorded_at") or "", reverse=True)


def owner_projection(state):
    work = state.get("work_result")
    revisions = state.get("work_reflections", [])
    latest = revisions[-1] if revisions else None
    # A failed/new classification does not delete the last useful draft.
    effective = next((row for row in reversed(revisions) if row["status"] == "PROPOSED"), None)
    items = (effective.get("proposal") or {}).get("owner_items", []) if effective else []
    from .owner_experience import cards
    proposed = cards(state)
    owned = state.get("owner_experience", {"cards": {}, "notes": [], "decisions": []})
    tools = state.get("work_tools", [])
    return {
        "format": "verantyx.owner-projection.v1",
        "run_id": state["run_id"],
        "purpose": state.get("work_session", {}).get("context", {}).get("purpose", ""),
        "human_request": {"text": state["request"], "source_ref": state["request_ref"]},
        "project_delta": {"candidate_files": deepcopy(work["artifacts"]) if work else [],
                          "source_project_changed": False, "adoption": "NOT_AUTHORIZED"},
        "human_decisions": [*deepcopy(list(state.get("human_decisions", {}).values())),
                            *[deepcopy(row) for row in owned["decisions"] if row["status"] == "ACTIVE_STATEMENT"]],
        "human_decision_history": deepcopy(owned["decisions"]),
        "human_notes": deepcopy(owned["notes"]),
        "owner_experience": deepcopy(owned),
        "human_reply": deepcopy(state.get("work_owner_reply")),
        "ai_decisions_and_assumptions": [row for row in proposed if row["kind"] in
                                         ("AI_DECISION", "ASSUMPTION", "HUMAN_DECISION")],
        "evidence_and_unknowns": {
            "build": "CANDIDATE_SAVED" if work and work["artifacts"] else "NOT_OBSERVED",
            "evidence": "NOT_VERIFIED", "ownership": "UNCONFIRMED",
            "tool_receipts": deepcopy(tools),
            "test_receipts": [],  # No exposed tool in this gateway runs tests.
            "unknown_proposals": [row for row in proposed if row["kind"] == "UNKNOWN"],
        },
        "human_learning_delta": [row for row in proposed if row.get("target") in
                                 ("OWN", "REVIEW", "REFERENCE", "DELEGATE")],
        "system_delta": {"candidates": [row for row in proposed if row["kind"] in
                                       ("RULE_CANDIDATE", "CHECK_CANDIDATE", "FAILURE")],
                         "rules_activated": 0},
        "owner_items": proposed,
        "reflection_status": latest["status"] if latest else "PENDING",
        "reflection_failure": latest.get("failure_code") if latest else None,
        "effective_reflection_id": effective["id"] if effective else None,
        "reflection_revisions": [{"id": row["id"], "status": row["status"], "model": row["model"],
                                 "source_ref": row["source_ref"], "trace_sha256": row["trace_sha256"]}
                                for row in revisions],
        "work_status": work["status"] if work else "RUNNING",
        "work_answer": work["answer"] if work else "",
        "owner_question": work["question"] if work else "",
        "recorded_facts": {"file_reads": sum(row["status"] == "SUCCEEDED"
                                              and row["request"]["tool"] == "read_file" for row in tools),
                           "candidate_writes": sum(row["status"] == "SUCCEEDED"
                                                   and row["request"]["tool"] == "write_candidate" for row in tools),
                           "refused_tools": sum(row["status"] == "REFUSED" for row in tools),
                           "tests_run": 0},
    }


def notebook_lines(projection, *, owner=False, learning_limit=3):
    if not owner:
        lines = ["WORK / " + projection["work_status"], projection["work_answer"],
                 "", "候補と回答を保存します。本体への採用は別の判断です。"]
        if projection["owner_question"]:
            lines += ["", "あなたに決めてほしいこと", projection["owner_question"]]
        return lines
    from .owner_notebook import TARGET_LABELS, KIND_LABELS
    lines = ["OWNER / 自分に残るプロジェクトノート", ""]
    if projection["owner_question"]:
        lines += ["今、あなたが決めること", projection["owner_question"], ""]
    lines += ["あなたが与えた目的", projection["human_request"]["text"]]
    if projection.get("purpose"):
        lines += ["プロジェクトの目的: " + projection["purpose"]]
    if projection["human_decisions"]:
        lines += ["", "あなたが残した判断"]
        for row in projection["human_decisions"][-3:]:
            lines += [row.get("statement", row.get("reason", "詳細はReviewへ")),
                      "  理由: " + (row.get("reason") or "まだ記録していません")]
    suggestions = []
    for item in projection["owner_items"]:
        if item["status"] in ("DEFERRED", "DISMISSED"):
            continue
        if item.get("target") in ("OWN", "REVIEW") and item["human_understanding"] == "NOT_ASSESSED":
            suggestions.append(item)
    if suggestions:
        lines += ["", "今回、自分に残す候補"]
    for item in suggestions[:learning_limit]:
        lines += [item["text"], "  今回とのつながり: " + item["reason"],
                  "  " + TARGET_LABELS[item["target"]] +
                  (" / AIからの提案" if item["target_is_suggestion"] else " / あなたの選択")]
    chosen = [row for row in projection["owner_items"] if not row["target_is_suggestion"]]
    if chosen:
        lines += ["", "あなたが選んだ関わり方"]
        for item in chosen[-3:]:
            lines += [item["text"] + " / " + TARGET_LABELS.get(item["target"], "記録を保持")]
    for note in projection.get("human_notes", [])[-2:]:
        lines += ["", "あなたの言葉 / " + ("次へ引き継ぐ" if note["share_with_ai"] else "自分用・送信しない"),
                  note["text"]]
    reusable = [row for row in projection["owner_items"]
                if row["kind"] in ("FAILURE", "RULE_CANDIDATE", "CHECK_CANDIDATE")]
    if reusable:
        lines += ["", "次の仕事へ残す候補"]
        for item in reusable[:2]:
            lines += [KIND_LABELS[item["kind"]] + ": " + item["text"]]
    facts = projection["recorded_facts"]
    lines += ["", "実際の作業記録",
              "読み取り {file_reads} / 候補の書き込み {candidate_writes} / 許可されなかった操作 {refused_tools}".format(**facts),
              "この経路では検査は未実行。理解済みの認定もしていません。"]
    status = projection["reflection_status"]
    if status == "FAILED":
        lines += ["意味の整理は未完了。作業結果は残っています。"]
    elif status == "OFF":
        lines += ["整理AIはオフ。実際の作業記録を残しています。"]
    elif status == "PENDING":
        lines += ["意味の整理を待たず、回答と候補を保持しています。"]
    lines += ["", "Reviewで選ぶ・メモする・参照・委譲。今すべて学ぶ必要はありません。"]
    return lines


def augment_view(view, snapshot, configuration):
    states = {state["run_id"]: state for state in snapshot["states"]}
    state = states.get(view.get("run_id"))
    if not state or not state.get("work_session"):
        return view
    projected = owner_projection(state)
    view["ownership_projection"] = projected
    view["owner_experience_cards"] = projected["owner_items"]
    view["reflection"] = (state.get("work_reflections") or [{"status": "PENDING"}])[-1]
    if state.get("work_result"):
        from .agent_runtime import _result
        view["outcome"] = _result(state)
    # Preserve the existing view's pane container and styling contract.
    for name, is_owner in (("agent", False), ("owner", True)):
        lines = notebook_lines(projected, owner=is_owner, learning_limit=configuration["learning"]["max_items"])
        pane = view.get("panes", {}).get(name)
        if isinstance(pane, str):
            view["panes"][name] = "\n".join(lines)
        elif isinstance(pane, list):
            view["panes"][name] = lines
        elif isinstance(pane, dict):
            for key in ("lines", "text", "body"):
                if key in pane:
                    pane[key] = lines if isinstance(pane[key], list) else "\n".join(lines)
    return view
