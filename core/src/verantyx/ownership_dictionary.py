"""Read-only ownership views over the existing project catalog and learning ledger.

Ownership is a human-selected learning target, independent of retained system
assets, execution authority, and mastery. No events are created by these views.
"""
from .assets import project_catalog
from .domain.codec import canonical
from .errors import LedgerError
from .learning import learning_references


PLACEMENT = {"OWN": "learn", "REVIEW": "learn", "REFERENCE": "learn", "DELEGATE": "delegate"}
SYSTEM_SECTIONS = ("rules", "verification_methods", "execution_methods", "failure_cases", "reuse_candidates")
LABELS = {
    "en": {
        "learn": "Human learning and reference choices (learn)",
        "delegate": "Human-selected delegation targets and system references (delegate)",
        "placement": "OWN: learn; REVIEW: retain human review; REFERENCE: consult when needed. All three stay in learn. Only an explicit DELEGATE choice goes in delegate. Suggestions remain undecided in learn.",
        "boundary": "Learning is voluntary; lookup does not resume it. DELEGATE grants no permission and proves no mastery. BUILD, EVIDENCE and OWNERSHIP remain separate. System retention is independent; lookup activates nothing. Reuse still requires current scope, preconditions and permission checks.",
        "selected": "HUMAN_SELECTED", "suggested": "SUGGESTED (undecided)",
        "system_reference": "SYSTEM_REFERENCE: retained reference, not a human-selected delegation; no automatic activation.",
        "source": "Source", "target_ref": "Latest target choice", "latest_learning_ref": "Latest learning record",
    },
    "ja": {
        "learn": "人間の学習・確認・参照の選択 (learn)",
        "delegate": "本人が選んだ委任目標とシステムの参照資産 (delegate)",
        "placement": "OWN: 自分で学ぶ、REVIEW: 人間の確認を残す、REFERENCE: 必要時に参照する。この3種は learn に残します。明示した DELEGATE のみ delegate に置き、未選択の提案は learn に残します。",
        "boundary": "学習は任意で、参照しても再開しません。DELEGATE は許可でも習熟の証明でもありません。BUILD・EVIDENCE・OWNERSHIP は別軸です。システムへの保存は独立し、参照だけで有効化しません。再利用には現在の範囲・前提・許可の確認が必要です。",
        "selected": "HUMAN_SELECTED: 本人の選択", "suggested": "SUGGESTED: 未選択の提案",
        "system_reference": "SYSTEM_REFERENCE: 保存した参照資産。本人が選んだ委任ではなく、自動有効化しません。",
        "source": "出典", "target_ref": "最新の所有目標の選択", "latest_learning_ref": "最新の学習記録",
    },
    "zh-Hans": {
        "learn": "人的学习、审核与参考选择 (learn)",
        "delegate": "本人选择的委托目标与系统参考资产 (delegate)",
        "placement": "OWN: 自己学习；REVIEW: 保留人工审核；REFERENCE: 按需查阅。三者均在 learn 中。仅明确选择的 DELEGATE 进入 delegate，未决定的建议留在 learn。",
        "boundary": "学习自愿，查阅不会恢复学习。DELEGATE 不授予权限，也不证明掌握。BUILD、EVIDENCE、OWNERSHIP 分开。系统保存是独立的，查阅不激活任何内容。复用仍需检查当前范围、前提与权限。",
        "selected": "HUMAN_SELECTED: 本人选择", "suggested": "SUGGESTED: 未决定的建议",
        "system_reference": "SYSTEM_REFERENCE: 保存的参考资产，并非本人选择的委托；不会自动激活。",
        "source": "来源", "target_ref": "最新目标选择", "latest_learning_ref": "最新学习记录",
    },
    "ko": {
        "learn": "사람의 학습, 검토, 참조 선택 (learn)",
        "delegate": "본인이 선택한 위임 목표와 시스템 참조 자산 (delegate)",
        "placement": "OWN: 직접 학습; REVIEW: 사람의 검토 유지; REFERENCE: 필요할 때 참조. 세 가지 모두 learn에 둡니다. 명시적으로 선택한 DELEGATE만 delegate에 두며 미결정 제안은 learn에 남습니다.",
        "boundary": "학습은 선택이며 조회로 재개되지 않습니다. DELEGATE는 권한이나 숙련의 증명이 아닙니다. BUILD, EVIDENCE, OWNERSHIP은 별개입니다. 시스템 보존은 독립적이며 조회로 활성화되지 않습니다. 재사용 시 현재 범위, 전제조건, 권한을 확인해야 합니다.",
        "selected": "HUMAN_SELECTED: 본인의 선택", "suggested": "SUGGESTED: 미결정 제안",
        "system_reference": "SYSTEM_REFERENCE: 보존된 참조 자산이며 본인이 선택한 위임이 아닙니다. 자동 활성화하지 않습니다.",
        "source": "출처", "target_ref": "최신 목표 선택", "latest_learning_ref": "최신 학습 기록",
    },
    "es": {
        "learn": "Elecciones de aprendizaje, revisión y referencia (learn)",
        "delegate": "Objetivos de delegación elegidos y referencias del sistema (delegate)",
        "placement": "OWN: aprender; REVIEW: mantener revisión humana; REFERENCE: consultar cuando sea necesario. Los tres quedan en learn. Solo una elección explícita DELEGATE pasa a delegate. Las sugerencias sin decidir quedan en learn.",
        "boundary": "Aprender es voluntario; consultar no lo reanuda. DELEGATE no concede permiso ni demuestra dominio. BUILD, EVIDENCE y OWNERSHIP siguen separados. La conservación del sistema es independiente; consultar no activa nada. Reutilizar exige comprobar alcance, condiciones y permisos actuales.",
        "selected": "HUMAN_SELECTED: elección personal", "suggested": "SUGGESTED: sin decidir",
        "system_reference": "SYSTEM_REFERENCE: referencia conservada, no una delegación elegida; sin activación automática.",
        "source": "Fuente", "target_ref": "Última elección de objetivo", "latest_learning_ref": "Último registro de aprendizaje",
    },
}


def project_ownership_dictionary(store, state, locale, query=None, *, view, limit=24, max_bytes=65536):
    """Filter full saved history before bounding, without changing the short delta.

    --run retains the catalog's context/ranking semantics: it is not a filter
    excluding other runs. Target choices are resolved from the latest snapshot.
    Private learning submissions and feedback are not copied into this catalog.
    """
    if view not in ("all", "learn", "delegate"):
        raise LedgerError("ARGUMENTS")
    if view == "all":
        return project_catalog(store, state, locale, query=query, limit=limit, max_bytes=max_bytes)
    snapshot = store.project_snapshot()
    # The catalog metadata and ownership rows must describe the same revision.
    # A second snapshot could otherwise splice a newer target onto older assets.
    class SnapshotCatalog:
        project_id = store.project_id

        def project_snapshot(self):
            return snapshot

    catalog = project_catalog(SnapshotCatalog(), state, locale, query=query,
                              limit=limit, max_bytes=max_bytes)
    catalog.update(view=view, ownership={
        "placement": dict(PLACEMENT), "undecided_view": "learn",
        "learning_voluntary": True, "lookup_resumes_learning": False,
        "delegation_grants_authority": False, "delegation_proves_mastery": False,
        "automatic_activation": False, "system_references_are_selected_delegations": False,
        "boundary": LABELS[locale]["boundary"], "placement_explanation": LABELS[locale]["placement"],
    })
    for section in SYSTEM_SECTIONS:
        if view == "learn":
            catalog[section] = []
            catalog["truncated"][section] = 0
        else:
            for row in catalog[section]:
                row.update(ownership_role="SYSTEM_REFERENCE", selected_target=None,
                           selection_status="NOT_A_LEARNING_TARGET")

    rows = []
    tokens = (query or "").casefold().split()
    contexts = {current["run_id"]: current["context"] for current in snapshot["states"]}
    for current in snapshot["states"]:
        recorded = current.get("learning_candidates", {})
        for row in learning_references(current, explicit_lookup=True):
            original = recorded.get(row["id"], {})
            selected = original.get("target_is_suggestion") is False and bool(original.get("target_ref"))
            target = row["ownership_target"] if selected else None
            placement = PLACEMENT[target] if selected else "learn"
            if placement != view:
                continue
            row.update(selected_target=target, selection_status="HUMAN_SELECTED" if selected else "SUGGESTED",
                       ownership_role="HUMAN_SELECTED_TARGET" if selected else "UNDECIDED_SUGGESTION",
                       target_ref=original.get("target_ref"), source_ref=original.get("source_ref"),
                       latest_learning_ref=(original.get("history") or [{}])[-1].get("source_ref"),
                       mastery_evidence="SELF_REPORTED" if original.get("evidence") else "NONE",
                       learning_voluntary=True)
            if not tokens or all(token in canonical(row).casefold() for token in tokens):
                rows.append(row)

    def priority(row):
        same_context = bool(state and contexts.get(row["owner_run"]) == state["context"])
        return (not same_context, row["owner_run"] != (state or {}).get("run_id"),
                row["selection_status"] != "HUMAN_SELECTED", row["id"])

    rows.sort(key=priority)
    catalog["learning"] = rows[:limit]
    catalog["truncated"]["learning"] = len(rows) - len(catalog["learning"])
    # Explicit ownership rows have byte-budget priority over optional system
    # references. Retain omission counts so a narrower query can recover them.
    removal_order = (*reversed(SYSTEM_SECTIONS), "learning")
    while len(canonical(catalog).encode("utf-8")) > max_bytes:
        section = next((key for key in removal_order if catalog[key]), None)
        if section is None:
            raise LedgerError("DOCUMENT_LIMIT")
        catalog[section].pop()
        catalog["truncated"][section] += 1
    return catalog


def item_lines(item, locale, *, include_references):
    """Escape every dynamic value before returning ordinary terminal text."""
    from .cli import visible
    labels = LABELS[locale]
    lines = []
    if "ownership_target" in item:
        selected = item.get("selection_status") == "HUMAN_SELECTED" if "selection_status" in item else item.get("target_is_suggestion") is False
        lines.append(visible(item["ownership_target"]) + " | " + labels["selected" if selected else "suggested"]
                     + " | " + visible(item.get("status", "")))
        lines.append("mastery_assessment=" + visible(item.get("mastery_assessment", "NOT_ASSESSED")))
        if item["ownership_target"] == "DELEGATE":
            lines.append("delegation_grants_authority=False | ownership_target_is_preference=True")
    if include_references:
        for field in ("scope", "scope_policy", "status", "review_after", "applicable_to_requested_context", "reuse_requires", "latest_outcome"):
            if field in item:
                lines.append(field + ": " + visible(canonical(item[field])))
        refs = list(dict.fromkeys([*item.get("source_refs", []), *([item["source_ref"]] if item.get("source_ref") else [])]))
        lines.extend(labels["source"] + ": " + visible(ref) for ref in refs)
        for field in ("target_ref", "latest_learning_ref"):
            if item.get(field):
                lines.append(labels[field] + ": " + visible(item[field]))
    return lines
