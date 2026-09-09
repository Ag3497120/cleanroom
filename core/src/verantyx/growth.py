"""Deterministic, voluntary growth candidates; no claim about human understanding."""
from .domain.codec import digest

WORKTREE = {
    "en": ("Branch separation and worktree separation", "Branches separate commit references; worktrees separate working files and indexes.",
           "Two writers switch branches in one directory and overwrite unfinished files.", "Design a two-writer setup that preserves both unfinished changes."),
    "ja": ("branch分離とworktree分離の違い", "branchはコミットの参照を分け、worktreeは作業ファイルとindexを分けます。",
           "同じディレクトリでbranchだけを切り替え、二人の未完了の変更が上書きされる例。", "二人の未完了の変更を両方残せる作業場所の構成を説明してください。"),
    "zh-Hans": ("分支隔离与工作树隔离的区别", "分支隔离提交引用；工作树隔离工作文件和索引。", "两个写入者在同一目录切换分支并覆盖未完成的修改。", "设计一个保留双方未完成修改的双写入者方案。"),
    "ko": ("브랜치 분리와 워크트리 분리의 차이", "브랜치는 커밋 참조를, 워크트리는 작업 파일과 인덱스를 분리합니다.", "두 작성자가 같은 디렉터리에서 브랜치를 바꾸며 미완료 변경을 덮어쓰는 경우.", "두 작성자의 미완료 변경을 모두 보존하는 구성을 설명하세요."),
    "es": ("Separar ramas y separar árboles de trabajo", "Las ramas separan referencias; los árboles de trabajo separan archivos e índices.", "Dos escritores cambian de rama en un directorio y sobrescriben cambios pendientes.", "Diseña una configuración que conserve ambos cambios pendientes."),
}
GENERIC = {
    "en": ("State the conditions under which this decision applies.", "The same choice applied outside its recorded scope.", "Explain a case where this decision must not be reused."),
    "ja": ("この判断を使える条件を、記録された適用範囲から説明します。", "適用範囲が異なる問題にも同じ選択を使ってしまう例。", "この判断を再利用してはいけない例を説明してください。"),
    "zh-Hans": ("说明记录的适用条件。", "将同一选择用于范围以外的问题。", "说明一个不应复用此判断的例子。"),
    "ko": ("기록된 적용 조건을 설명합니다.", "적용 범위 밖에서 같은 선택을 사용하는 경우.", "이 판단을 재사용하면 안 되는 사례를 설명하세요."),
    "es": ("Describe las condiciones registradas de aplicación.", "Aplicar la misma elección fuera de su alcance.", "Explica un caso en que no deba reutilizarse esta decisión."),
}

FAILURE_LESSONS = {
    "en": ("Review the recorded failure: {target}", "The recorded {family} result is {outcome}; closure: {closure}.",
           "Compare the declared contract with the observed result: {details}. A result only covers its recorded scope.",
           "Do not treat {case} as proof of success or as a diagnosis of the person's understanding.",
           "For {target}, identify the failing check or missing evidence, then describe a change and a separate negative control."),
    "ja": ("記録された失敗を確認する：{target}", "{family} の結果は {outcome}、検証の到達点は {closure} です。",
           "定めた契約と観測結果を比較します：{details}。結果を使える範囲は、記録された検査対象に限られます。",
           "{case} を成功の証明や、本人が理解しているかどうかの判定として扱わない例。",
           "{target} で失敗した検査か不足する証拠を特定し、修正案と、それを別途確かめる反例を説明してください。"),
    "zh-Hans": ("检查已记录的失败：{target}", "{family} 记录的结果为 {outcome}；验证结论为 {closure}。",
                "对比明确约定与观测结果：{details}。结果仅覆盖已记录的检查范围。",
                "不要将 {case} 当作成功证明，也不要据此判断个人是否理解。",
                "针对 {target}，指出失败的检查或缺失的证据，再说明修正方法和单独的反例检查。"),
    "ko": ("기록된 실패 확인: {target}", "{family}의 기록된 결과는 {outcome}이며 검증 결과는 {closure}입니다.",
           "명시한 계약과 관측 결과를 비교합니다: {details}. 결과는 기록된 검사 범위에만 적용됩니다.",
           "{case}를 성공의 증거나 사람의 이해 여부에 대한 판단으로 취급하지 마세요.",
           "{target}에서 실패한 검사나 부족한 증거를 찾고, 수정 방법과 별도의 반례 검사를 설명하세요."),
    "es": ("Revisar el fallo registrado: {target}", "El resultado registrado de {family} es {outcome}; conclusión: {closure}.",
           "Compara el contrato declarado con el resultado observado: {details}. El resultado solo cubre el alcance registrado.",
           "No trates {case} como prueba de éxito ni como una evaluación de la comprensión de la persona.",
           "Para {target}, identifica la comprobación fallida o la evidencia que falta; después describe una corrección y un control negativo independiente."),
}
FAILURE_WORDS = {
    "en": ("expected", "observed", "not established", "verification", "separate-process oracle", "candidate tests", "command", "integration", "adoption"),
    "ja": ("期待値", "観測値", "確定していません", "ファイル検証", "別プロセスのオラクル", "候補テスト", "コマンド", "統合", "採用"),
    "zh-Hans": ("预期值", "观测值", "尚未确定", "文件验证", "独立进程的预期结果检查", "候选测试", "命令", "集成", "采纳"),
    "ko": ("예상값", "관측값", "확정되지 않음", "파일 검증", "별도 프로세스 오라클", "후보 테스트", "명령", "통합", "채택"),
    "es": ("esperado", "observado", "sin determinar", "verificación de archivo", "oráculo en otro proceso", "pruebas del candidato", "comando", "integración", "adopción"),
}
FAILURE_STATUS = {
    "en": {"REFUTED": "the fixed expectation was not met", "CONTESTED": "the check needs review", "UNKNOWN": "the result is not established",
           "PROCESS_FAILED": "the process ended with an error", "INVALIDATED": "the recorded preconditions no longer hold", "OUTCOME_UNKNOWN": "the outcome could not be confirmed", "CONFLICTED": "changes conflict"},
    "ja": {"REFUTED": "固定した期待値と一致しませんでした", "CONTESTED": "検査自体の見直しが必要です", "UNKNOWN": "結果を確定できません",
           "PROCESS_FAILED": "処理がエラーで終了しました", "INVALIDATED": "記録した前提が成立しなくなりました", "OUTCOME_UNKNOWN": "処理結果を確認できませんでした", "CONFLICTED": "変更が競合しています"},
    "zh-Hans": {"REFUTED": "未满足固定的预期值", "CONTESTED": "需要重新检查验证方法", "UNKNOWN": "结果尚未确定",
                "PROCESS_FAILED": "进程以错误结束", "INVALIDATED": "已记录的前提不再成立", "OUTCOME_UNKNOWN": "无法确认处理结果", "CONFLICTED": "修改存在冲突"},
    "ko": {"REFUTED": "고정된 예상값과 일치하지 않음", "CONTESTED": "검사 방법 재검토가 필요함", "UNKNOWN": "결과를 확정할 수 없음",
           "PROCESS_FAILED": "처리가 오류로 종료됨", "INVALIDATED": "기록된 전제조건이 더 이상 성립하지 않음", "OUTCOME_UNKNOWN": "처리 결과를 확인할 수 없음", "CONFLICTED": "변경이 충돌함"},
    "es": {"REFUTED": "no se cumplió la expectativa fijada", "CONTESTED": "la comprobación requiere revisión", "UNKNOWN": "el resultado no está establecido",
           "PROCESS_FAILED": "el proceso terminó con un error", "INVALIDATED": "las condiciones registradas ya no se cumplen", "OUTCOME_UNKNOWN": "no se pudo confirmar el resultado", "CONFLICTED": "hay cambios en conflicto"},
}


def failure_candidates(state):
    from .assets import project_assets
    from .domain.codec import canonical
    locale = state["locale"]
    words, phrases = FAILURE_WORDS[locale], FAILURE_LESSONS[locale]
    families = dict(zip(("VERIFICATION", "ORACLE", "WORKTREE", "COMMAND", "INTEGRATION", "ADOPTION"), words[3:]))
    rows = sorted(project_assets(state)["failure_cases"], key=lambda item: item["revision"], reverse=True)
    candidates = []
    for row in rows:
        if row["family"] == "HANDOFF":
            from .i18n import text
            candidates.append({"id": digest({"anchor": row["source_ref"], "concept": "handoff_fidelity"}),
                               "concept": text(locale, "context.lesson"), "concept_id": "handoff_fidelity",
                               "why_now": [text(locale, "context.REPAIR_REQUIRED") + " " + ", ".join(row["mismatch_ids"])],
                               "project_anchor": row["source_ref"], "source_refs": row["source_refs"],
                               "ownership_target": "REVIEW", "target_is_suggestion": True, "mastery_evidence": "NONE",
                               "system_capture": ["REFERENCE"], "minimum_model": text(locale, "context.boundary"),
                               "counterexample": text(locale, "context.counterexample"), "check": text(locale, "context.exercise"),
                               "assessment": None})
            continue
        target = ", ".join(row["target"]) if type(row["target"]) is list else row["target"]
        target = target or families[row["family"]]
        details = []
        for check in row["checks"]:
            if check.get("passed") is True:
                continue
            text = ": ".join(str(check.get(key)) for key in ("id", "kind", "pointer") if check.get(key))
            for key, label in (("expected", words[0]), ("observed", words[1])):
                if key in check:
                    text += "; " + label + " " + canonical(check[key])
            details.append(text)
        for control in row["negative_controls"]:
            if control.get("rejected") is False:
                details.append(control["id"] + ": " + FAILURE_STATUS[locale]["CONTESTED"])
        if row.get("process"):
            details.append("exit=" + str(row["process"].get("returncode")))
        if row.get("test_summary"):
            details.append("tests=" + canonical(row["test_summary"]))
        if row.get("reason"):
            details.append(row["reason"])
        status = FAILURE_STATUS[locale]
        closure = status.get(row["closure"], words[2])
        outcome = status.get(row["outcome"], closure)
        values = {"target": target[:300], "family": families[row["family"]], "closure": closure,
                  "outcome": outcome, "details": "; ".join(details)[:5000] or closure, "case": closure if row["closure"] else outcome}
        title, why, model, counterexample, check = [phrase.format(**values) for phrase in phrases]
        concept = row["family"].lower() + "_failure"
        candidates.append({"id": digest({"anchor": row["source_ref"], "concept": concept}), "concept": title,
                           "concept_id": concept, "why_now": [why], "project_anchor": row["source_ref"],
                           "source_refs": row["source_refs"], "ownership_target": "REVIEW", "target_is_suggestion": True,
                           "mastery_evidence": "NONE", "system_capture": ["TEST"] if row["closure"] is not None else ["REFERENCE"],
                           "minimum_model": model, "counterexample": counterexample, "check": check, "assessment": None})
    return candidates


def template_candidates(state, *, include_off=False):
    """The original deterministic suggestions, available for explicit collection."""
    human, concepts = [], {}
    for trigger in state.get("growth_triggers", []):
        concepts.setdefault(trigger["concept"], []).append(trigger)
    if include_off or state["learning_preferences"]["mode"] != "off":
        for concept, triggers in concepts.items():
            trigger = triggers[0]
            if concept == "parallel_writers":
                title, model, counterexample, check = WORKTREE[state["locale"]]
            else:
                title = concept
                model, counterexample, check = GENERIC[state["locale"]]
            refs = list(dict.fromkeys(t["source_ref"] for t in triggers))
            # Keep the original anchor and the most recent bounded sources.
            refs = refs if len(refs) <= 32 else [refs[0], *refs[-31:]]
            human.append({"id": digest({"anchor": trigger["source_ref"], "concept": concept}),
                          "concept": title, "concept_id": concept, "why_now": list(dict.fromkeys(t["kind"] for t in triggers)),
                          "project_anchor": trigger["source_ref"], "source_refs": refs,
                          "ownership_target": "REVIEW", "target_is_suggestion": True, "mastery_evidence": "NONE",
                          "system_capture": ["RULE"] if any(t["kind"] == "RulePromoted" for t in triggers) else ["REFERENCE"],
                          "minimum_model": model, "counterexample": counterexample, "check": check,
                          "assessment": None})
    if include_off or state["learning_preferences"]["mode"] != "off":
        return [*failure_candidates(state), *human]
    return human


def deltas(state):
    from .learning import project_learning
    from .assets import project_assets
    assets = project_assets(state)
    human = project_learning(state, include_deferred=False) if state["learning_preferences"]["mode"] != "off" else []
    receipts = [item for item in state["effects"].values() if item.get("receipt")]
    adoptions = [item for item in state.get("adoptions", {}).values()
                 if item.get("status") == "ADOPTED" and item.get("receipt")]
    return {
        "project_delta": {"request": state["request"], "observations": dict(state["latest_observations"]),
                          "candidate_changes": [{"receipt_ref": item["receipt_ref"], **item["receipt"]} for item in receipts],
                          "canonical_changes": [dict(item["receipt"]) for item in adoptions],
                          "workspace_observations": state["workspace_observations"], "unresolved": (state["assessment"] or {}).get("gaps", [])},
        "system_delta": {"rule_event_refs": list(state["rule_event_refs"]),
                         "reused_rules": [j for j in (state["assessment"] or {}).get("judgments", []) if j["status"] == "PRECEDENT_MATCHED"],
                         "verification_scope": "RECORDED_METHOD_CONTRACTS_AND_THEIR_FIXED_TARGETS_ONLY",
                         "verification_assets": assets["verification_methods"], "execution_assets": assets["execution_methods"],
                         "failure_assets": assets["failure_cases"], "reuse_candidates": assets["reuse_candidates"]},
        "human_delta": human[:state["learning_preferences"]["max_items"]],
    }
