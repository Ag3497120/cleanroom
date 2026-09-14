"""Small, voluntary learning margins derived from existing work records.

Reading a card never changes mastery, rights, or the event ledger. Recurrence
means the same recorded concept ID appeared again, not that its applicability
has been proved. The Owner explicitly chooses what to retain and how.
"""
from copy import deepcopy

from .learning import project_learning
from .presentation import safe_text


SUBMISSIONS = {
    "SelfExplanationSubmitted": "自分の言葉",
    "CounterexampleIdentified": "反例についてのメモ",
    "AppliedInProject": "今回への適用についての自己申告",
    "TransferredToNewProblem": "別の場面への転用についての自己申告",
}


def _safe(value):
    return safe_text(str(value), multiline=True)


def project(snapshot, configuration, run_ids):
    """Project existing candidates and their histories from one ledger version."""
    selected = set(run_ids)
    items, concepts = [], {}
    for state in snapshot["states"]:
        run_id = state["run_id"]
        enabled = (configuration["learning"]["mode"] != "off"
                   and state.get("learning_preferences", {}).get("mode") != "off")
        for candidate in project_learning(state, include_suggestions=False):
            proposed = candidate.get("target_is_suggestion", True)
            statements = []
            for event in candidate.get("history", []):
                kind = event.get("type")
                payload = event.get("payload") or {}
                statement = payload.get("statement")
                if kind in SUBMISSIONS and isinstance(statement, str):
                    statements.append({"kind": kind, "label": SUBMISSIONS[kind], "statement": statement,
                                       "source_ref": event.get("source_ref"), "recorded_at": event.get("recorded_at"),
                                       "basis": "SELF_REPORT_NOT_MASTERY"})
            item = {**deepcopy(candidate), "run_id": run_id, "revision": state["revision"],
                    "request": state.get("request", ""), "statements": statements,
                    "target_is_suggestion": proposed, "suggestions_enabled": enabled}
            concept_id = candidate.get("concept_id")
            if concept_id:
                concepts.setdefault(concept_id, []).append(item)
            if run_id in selected and (enabled or not proposed):
                items.append(item)
    for item in items:
        earlier = [row for row in concepts.get(item.get("concept_id"), [])
                   if row["run_id"] != item["run_id"]]
        # Separate references, never blended votes, inherited mastery or rights.
        item["related_experiences"] = [{"run_id": row["run_id"], "concept": row["concept"],
                                        "ownership_target": row.get("ownership_target", "REVIEW"),
                                        "target_is_suggestion": row["target_is_suggestion"],
                                        "self_report_count": len(row["statements"]),
                                        "source_ref": row.get("source_ref")}
                                       for row in earlier]
        item["recurrence_count"] = len({row["run_id"] for row in earlier})
    candidates = [item for item in items
                  if item["suggestions_enabled"] and item.get("status") != "DEFERRED"
                  and not item["statements"]
                  and (item["target_is_suggestion"] or item.get("ownership_target") in ("OWN", "REVIEW"))]
    # This orders optional reading, not truth, confidence or human competence.
    candidates.sort(key=lambda item: (item.get("ownership_target") != "OWN", -item["recurrence_count"]))
    counts = {
        "awaiting_choice": sum(item["target_is_suggestion"] and item.get("status") != "DEFERRED" for item in items),
        "deferred": sum(item.get("status") == "DEFERRED" for item in items),
        "self_reports": sum(len(item["statements"]) for item in items),
        "reference": sum(not item["target_is_suggestion"] and item.get("ownership_target") == "REFERENCE" for item in items),
        "delegated": sum(not item["target_is_suggestion"] and item.get("ownership_target") == "DELEGATE" for item in items),
    }
    return {"items": items, "focus": candidates[0] if candidates else None, "counts": counts,
            "automatic_card": configuration["learning"]["mode"] == "digest",
            "authority": "REFERENCE_ONLY", "mastery": "NOT_ASSESSED", "model_calls": 0}


def card(item):
    repeated = f" / 同じ概念の別の仕事 {item['recurrence_count']}件" if item["recurrence_count"] else ""
    target = item.get("ownership_target", "REVIEW")
    status = "目標の候補" if item["target_is_suggestion"] else "あなたが選んだ目標"
    return (f" {target} / {status}{repeated}\n " + _safe(item["concept"])
            + "\n 今学ばなくても作業は進められます。読むだけでは理解済みにしません。")


def lesson(item):
    target = item.get("ownership_target", "REVIEW")
    ownership = "候補。まだ本人の選択ではありません。" if item["target_is_suggestion"] else "本人が選択した目標。習熟の認定ではありません。"
    lines = ["LEARN TOGETHER / この仕事から理解を持ち帰る", _safe(item["concept"]), "",
             "PROJECT ANCHOR / なぜこの仕事と関係するか", _safe(item["request"]),
             "Run: " + item["run_id"] + " / revision " + str(item["revision"]), "",
             "WHY NOW / 学習候補になった理由"]
    reasons = item.get("why_now") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    lines.extend("  " + _safe(reason) for reason in reasons)
    lines += ["", "ONE PRINCIPLE / まず持ち帰る原理", _safe(item.get("minimum_model") or "原理の説明は未記録です。"),
              "", "BOUNDARY / どこで誤るか", _safe(item.get("counterexample") or "反例は未記録です。"),
              "", "TRY YOUR WORDS / 今回の変更へ結び付ける問い", _safe(item.get("check") or "使える条件と使えない条件を一つずつ説明できますか。"),
              "", "YOUR CHOICE / 人間側に残す水準", target + " / " + ownership,
              "状態: " + str(item.get("status", "RECORDED")), ""]
    lines += ["YOUR NOTES / 自分の言葉・判断の記録"]
    if not item["statements"]:
        lines += ["まだ自己説明などの記録はありません。理解していないと断定する意味ではありません。"]
    for statement in item["statements"][-4:]:
        lines += [statement["label"] + " / 自己申告・採点なし", _safe(statement["statement"]),
                  "Source: " + str(statement.get("source_ref") or "記録参照なし"), ""]
    lines += ["", "PREVIOUS EXPERIENCE / 同じ概念の別の仕事"]
    if not item["related_experiences"]:
        lines += ["同じ概念IDの別の仕事はまだありません。"]
    for other in item["related_experiences"][-4:]:
        status = "目標候補" if other["target_is_suggestion"] else "本人が選んだ目標"
        lines += [other["run_id"], f"  {other['ownership_target']} / {status} / 自己申告 {other['self_report_count']}件"]
    lines += ["別の仕事の記録は参照です。今回への適用や習熟を自動で認定しません。", "",
              "SOURCE / 出典", str(item.get("source_ref") or item.get("project_anchor") or "参照未記録"),
              "教材は保存された候補です。この画面では外部モデルによる説明・採点を行いません。", "",
              "F4または下の操作から、メモ・後回し・参照・委譲を選べます。Escで仕事へ戻ります。"]
    return "\n".join(lines)


def summary(growth):
    counts = growth["counts"]
    return ("LEARN TOGETHER / この仕事から残った理解\n"
            f"目標の選択待ち {counts['awaiting_choice']} / 後で確認 {counts['deferred']}\n"
            f"自分のメモ {counts['self_reports']} / 参照として保持 {counts['reference']} / 委譲を選択 {counts['delegated']}\n"
            "これは記録件数です。理解度の点数でも、AIへの実行許可でもありません。")
