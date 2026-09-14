"""Small, model-free CLI views over the existing recorded work loop."""
COMMANDS = {"recap"}

LABELS = {
    "ja": ("作業の記録", "実装・統合の記録", "次に使う資産", "自分に残す判断・学習",
           "記録時点の状態です。現在の対象・期限・許可を再検査した結果ではありません。",
           "学習・委任の選択は実行許可でも習熟の証明でもありません。",
           "現在の条件を結び直すまで再実行しません。"),
    "en": ("Work recap", "Implementation and integration", "Reusable assets", "Human judgments and learning",
           "Recorded status only; current targets, expiry and permission have not been rechecked.",
           "Learning or delegation preferences grant no authority and prove no mastery.",
           "Rebind current conditions before any execution."),
    "zh-Hans": ("工作记录", "实现与集成记录", "可复用资产", "人的判断与学习",
                "仅为记录时的状态，未重新检查当前对象、期限和权限。",
                "学习或委托偏好不授予权限，也不证明掌握程度。",
                "重新绑定当前条件前不执行。"),
    "ko": ("작업 기록", "구현 및 통합 기록", "재사용 자산", "사람의 판단과 학습",
           "기록 당시 상태이며 현재 대상, 만료 및 권한을 다시 검사하지 않았습니다.",
           "학습이나 위임 선택은 실행 권한이나 숙련의 증거가 아닙니다.",
           "현재 조건을 다시 연결하기 전에는 실행하지 않습니다."),
    "es": ("Resumen del trabajo", "Implementación e integración", "Activos reutilizables", "Juicios y aprendizaje",
           "Estado registrado; no se han revisado los objetos, plazos ni permisos actuales.",
           "Aprender o delegar no concede autoridad ni demuestra dominio.",
           "Vincula las condiciones actuales antes de ejecutar."),
}


def register(sub):
    parser = sub.add_parser("recap", add_help=False, allow_abbrev=False)
    parser.add_argument("run_id")


def dispatch(root, configuration, args, locale):
    from .experience_report import report
    return report(root, configuration, args.run_id, locale)


def help_lines(locale, interactive=False):
    labels = LABELS[locale]
    prefix = "/" if interactive else "verantyx "
    run = "[RUN_ID]" if interactive else "RUN_ID"
    return [prefix + "keep " + run + " : " + labels[2] + " / " + labels[3],
            prefix + "recap " + run + " : " + labels[0],
            prefix + "dictionary --view learn : " + labels[3],
            prefix + "dictionary --view delegate : " + labels[2],
            ("/skills" if interactive else "verantyx skills-stack") + " : personal skill library",
            labels[5]]


def display(result, locale, command):
    from .cli import visible
    labels = LABELS[locale]
    print(labels[0] + ": " + visible(result["run_id"]) + " @ " + str(result["revision"]))
    print(" | ".join(key.upper() + ": " + visible(result[key]["status"])
                     for key in ("build", "evidence", "ownership")))
    print(labels[4])
    project, system, human = (result[key] for key in ("project_delta", "system_delta", "human_delta"))
    print("\n" + labels[1])
    for key in ("candidate_changes", "canonical_changes", "execution_records", "workflows"):
        print("  " + key + ": " + str(len(project[key])))
    print("\n" + labels[2])
    for key in ("verification_assets", "execution_assets", "failure_assets", "model_candidates", "external_references"):
        rows = system[key]
        print("  " + key + ": " + str(len(rows)))
        for row in rows[:5]:
            name = row.get("name") or row.get("title") or row.get("family") or row.get("kind", "")
            print("  " + visible(row["id"]) + "  " + visible(name))
    print("\n" + labels[3])
    print("  judgments: " + str(len(human["judgments"])))
    for row in [*human["ownership_choices"], *human["suggestions"]]:
        marker = "SUGGESTED" if row.get("target_is_suggestion", True) else "HUMAN_SELECTED"
        print("  " + visible(row["id"]) + "  " + visible(row["concept"]))
        print("  " + visible(row["ownership_target"]) + " / " + marker + " / mastery=NOT_ASSESSED")
    print(labels[5])
    print(labels[6])
    print("verantyx recap " + visible(result["run_id"]) + " --json")
