"""Human-facing connected work and ownership UI using existing operations."""
from pathlib import Path
import os
import uuid

from .errors import LedgerError
from .cleanroom_io import current as owner_io, console_print as print


def _key():
    return uuid.uuid4().hex


def _mutate(root, configuration, operation, *args, **kwargs):
    """The interactive menu is not an umbrella signature for future choices."""
    from argparse import Namespace
    from .authority import command_scope
    selected = Namespace(command="develop", interactive_operation=operation.__name__,
                         arguments=list(args), keyword_arguments=kwargs)
    with command_scope(root, configuration, selected):
        return operation(root, configuration, *args, **kwargs)


def _ask(prompt, default=""):
    if owner_io.get() is not None:
        return owner_io.get().ask(prompt, default)
    value = input(prompt + (" [" + default + "]" if default else "") + "> ").strip()
    return value or default


def _yes(prompt):
    return _ask(prompt + " [y/N]").lower() == "y"


def _start(prompt):
    return _ask(prompt + " [Y/n]", "y").lower() not in ("n", "no")


def _pick(title, rows, label):
    from .choice_navigation import choose, description
    from .interaction_text import locale
    if not rows:
        print(title + ": no entries")
        return None
    session = owner_io.get()
    lang = session.configuration["ui"]["locale"] if session is not None else locale()
    choices = [(index, label(row)) for index, row in enumerate(rows)]
    descriptions = {index: description(title, row, label(row), lang) for index, row in enumerate(rows)}
    if session is not None:
        selected = session.choose(title, choices, descriptions=descriptions,
                                  aliases={str(row).casefold(): index for index, row in enumerate(rows)
                                           if isinstance(row, (str, int, bool))})
    else:
        selected = choose(title, choices, descriptions, lang)
    return None if selected is None else rows[selected]

def _conditions(default_target=""):
    target = _ask("検査するファイル（未指定: 検査しない）", default_target)
    if not target:
        return None, []
    print('明示する有限条件。例: JSON /retry_limit = 3。コード全体の動作検査ではありません。')
    values = []
    for _ in range(16):
        value = _ask("条件（空欄: 終了）")
        if not value:
            break
        values.append(value)
    if not values:
        print("条件がないため、検証済みとは扱わず候補保存にします。")
        return None, []
    from .judgment_compiler import compile_conditions
    compile_conditions(target, values)
    return target, values


def _friendly_status(status):
    return {
        "CANDIDATE_SAVED": "安全な候補を作成しました",
        "COMPLETE_BOUNDED": "候補と検査を記録しました",
        "DECISION_REQUIRED": "人間の判断を待っています",
        "UNKNOWN_CONTEXT": "追加の情報が必要です",
        "MODEL_CALL_FAILED": "AIへの接続を完了できませんでした",
        "MODEL_OUTCOME_UNKNOWN": "AIの結果を確認できませんでした",
        "SOURCE_RECORDED": "外部AIの仕事を記録しました",
    }.get(status, "作業の状態を記録しました")


def show_result(root, result):
    if "work" in result:
        from .agent_console import show_result as show_agent_result
        return show_agent_result(root, result)
    from .cleanroom_notebook import render_work_receipt
    print("\n╭─ WORK NOTE ─────────────────────────────────────────────────")
    print("│ " + result.get("request", result.get("run_id", "This work")))
    print("│ State: " + _friendly_status(result.get("status", "UNKNOWN")))
    print("╰─────────────────────────────────────────────────────────────")
    gate = result.get("task_gate")
    print("\nPROJECT DELTA")
    if result.get("artifact_directory"):
        print("候補ノート: " + str(Path(root) / result["artifact_directory"]))
        print("本体プロジェクト: 未変更。採用はあなたが決めます。")
    else:
        print("本体プロジェクト: 今回もCleanroomの外からは変更していません")
    print("\nSYSTEM DELTA")
    if result.get("judgment_run"):
        print("次回も使える検査: " + result["judgment_run"])
    else:
        print("判断、仮定、検証方法、失敗候補を作業帳へ保存しました")
    print("\nHUMAN DELTA")
    if isinstance(gate, dict) and gate.get("human_assumption"):
        print("今回あなたが決めたこと: " + str(gate["human_assumption"]))
    for item in result.get("learning_proposals", [])[:2]:
        if item.get("concept"):
            print("回収する価値がある理解: " + item["concept"])
    if not result.get("learning_proposals"):
        print("学習候補: 今回は新しい付箋を増やしませんでした")
    print("\nEVIDENCE & UNKNOWN")
    if result.get("next_action"):
        print("確認したいこと: " + result["next_action"])
    elif result.get("reason"):
        print("確認が必要な点: " + result["reason"])
    else:
        print("この作業の証拠と未解決点は、作業ノートに分けて残しています。")
    render_work_receipt(root, result)
    print("続きは「今の仕事を見せて」または「確認が必要なことを見る」と書けば開けます。")


_CONTEXT_FILENAMES = {
    "readme.md", "package.json", "pyproject.toml", "requirements.txt", "composer.json",
    "cargo.toml", "go.mod", "index.html", "app.py", "main.py", "main.ts", "main.js",
    "vite.config.ts", "vite.config.js", "next.config.js", "next.config.mjs",
}
_CONTEXT_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".html", ".css", ".md", ".json",
                       ".toml", ".yaml", ".yml", ".swift", ".rs", ".go", ".java", ".php"}
_EXCLUDED_DIRECTORIES = {".git", ".verantyx", ".venv", "venv", "node_modules", "dist", "build", "__pycache__"}
_SECRET_MARKERS = (".env", "secret", "credential", "password", "private", "id_rsa", ".pem", ".key")


def _context_files(root, limit=8):
    """Choose a small, project-local context set without asking for raw paths."""
    root = Path(root).resolve()
    preferred, fallback = [], []
    for current, directories, filenames in os.walk(root):
        folder = Path(current)
        relative_folder = folder.relative_to(root)
        if len(relative_folder.parts) > 3:
            directories[:] = []
            continue
        directories[:] = [name for name in directories
                           if name not in _EXCLUDED_DIRECTORIES and not name.startswith(".")]
        for name in sorted(filenames):
            lowered = name.casefold()
            if lowered.startswith(".") or any(marker in lowered for marker in _SECRET_MARKERS):
                continue
            path = folder / name
            try:
                if not path.is_file() or path.stat().st_size > 65536:
                    continue
            except OSError:
                continue
            relative = path.relative_to(root).as_posix()
            if lowered in _CONTEXT_FILENAMES:
                preferred.append(relative)
            elif path.suffix.casefold() in _CONTEXT_EXTENSIONS:
                fallback.append(relative)
    selected = []
    for path in preferred + fallback:
        if path not in selected:
            selected.append(path)
        if len(selected) == limit:
            break
    return selected


def _show_start_plan(context_files, preflight, previous=None):
    from .cleanroom_notebook import render_task_workspace
    render_task_workspace(context_files, preflight, previous)


def _confirm_context(context_files):
    while True:
        choice = _ask("Enterで作業帳を開く、vで送信範囲、nで中止").casefold()
        if choice in ("", "y", "yes", "start"):
            return True
        if choice in ("n", "no", "q", "quit"):
            return False
        if choice in ("v", "view"):
            print("\n今回送るプロジェクト内ファイル")
            if context_files:
                for path in context_files:
                    print("  " + path)
            else:
                print("  自動選択できる小さなテキストファイルはありません。プロジェクト文脈だけを使います。")
            continue
        print("Enterで作業帳を開く、vで一覧、nで中止を選んでください。")


def _new_work(root, configuration, mode, previous=None, request=None, attachments=()):
    from .agent_console import start_work
    return start_work(root, configuration, mode, previous=previous, request=request, attachments=attachments)


def _legacy_new_work(root, configuration, mode, previous=None, request=None):
    from .development import run_work
    from .constitution import assess
    request = request if request is not None else _ask(
        "追加でAIに頼みたいこと（空欄: 戻る）" if previous else "何を一緒に進めますか？"
    )
    if not request:
        return
    preflight = assess(root, configuration, request)
    assumption = None
    if preflight.get("question"):
        print("\nあなたに決めてほしいことが1件あります")
        print(preflight["question"])
        assumption = _ask("今回の前提（空欄: 判断待ちとして保存）")
        if not assumption and preflight["status"] in ("ASK_ONE_DECISION", "UNKNOWN"):
            result = _mutate(root, configuration, run_work, request=request, key=_key(), include=[],
                             target=None, expectations=[], mode=mode, allow_contested=False,
                             continue_from=previous["run_id"] if previous else None, assumption=None)
            show_result(root, result)
            return result
    context_files = _context_files(root)
    _show_start_plan(context_files, preflight, previous)
    if not _confirm_context(context_files):
        return
    result = _mutate(root, configuration, run_work, request=request, key=_key(), include=context_files,
                     target=None, expectations=[], mode=mode, allow_contested=False,
                     continue_from=previous["run_id"] if previous else None,
                     assumption=assumption or None)
    show_result(root, result)
    return result


def _import(root, configuration, mode):
    from .development import import_job
    path = _ask("外部AIとの仕事の原文ファイル（空欄: 戻る）")
    if not path:
        return
    label = _ask("仕事の名前", Path(path).name)
    origin = _ask("元のプロジェクト", Path(path).parent.name)
    target, conditions = _conditions()
    print("自動モードでは選んだ原文を既存の二役へ送信します。" if mode == "auto"
          else "原文はローカルに保存します。追加のモデル呼び出しはありません。")
    if not _yes("取り込んで判断・学習へ回収しますか"):
        return
    result = _mutate(root, configuration, import_job, path=path, origin=origin, label=label,
                        mode=mode, key=_key(), target=target, expectations=conditions)
    show_result(root, result)
    return result


def _choose_work(root, configuration):
    from .development import work_summaries
    return _pick("仕事の履歴", work_summaries(root, configuration),
                 lambda row: row["label"] + " / " + row["status"]
                 + " / 検査 " + str(len(row.get("checks", []))) + "件"
                 + " / " + str(row.get("last_recorded_at") or "時刻未記録"))


def _dictionary(root, configuration, run_ids=None):
    from .owner_experience import read_states, cards
    from .owner_notebook import open_notebook
    owner_states = read_states(root, configuration)
    if any(cards(state) for state in owner_states
           if run_ids is None or state["run_id"] in run_ids):
        selected_run = next(iter(run_ids)) if run_ids and len(run_ids) == 1 else None
        return open_notebook(root, configuration, run_id=selected_run, section="learn")
    from .personal_skills import stack
    library = stack(root, configuration, run_ids=run_ids, limit=100, locale="ja")
    groups = {}
    for work in library["works"]:
        for item in work["skills"]:
            key = (item.get("concept_id", item["concept"]), item["ownership_target"],
                   item.get("target_is_suggestion", True))
            groups.setdefault(key, []).append({**item, "run_id": work["run_id"], "work_label": work["label"]})
    selected = _pick("自分に残す理解と、任せる技能（同じ概念をまとめて表示）", list(groups.values()),
                     lambda group: group[-1]["concept"] + " / " + group[-1]["ownership_target"]
                     + (" / 未選択" if group[-1].get("target_is_suggestion", True) else " / 本人の選択")
                     + " / 関連する仕事 " + str(len(group)) + "件")
    if not selected:
        return
    item = selected[-1] if len(selected) == 1 else _pick("操作する履歴を固定", selected, lambda x: x["work_label"])
    if not item:
        return
    print("\n" + item["concept"])
    print(item.get("minimum_model", ""))
    print("反例: " + item.get("counterexample", ""))
    print("理解を確かめる問い: " + item.get("check", ""))
    action = _pick("この項目でできること", ["target", "explain", "policy", "reuse"],
                   lambda x: {"target": "学ぶ・レビュー・参照・委譲を選ぶ", "explain": "自分の説明を残す",
                              "policy": "AIの担当範囲と再利用モードを設定", "reuse": "保存した条件を再利用"}[x])
    if action == "target":
        target = _pick("本人の選択。実行権限とは別です。", ["OWN", "REVIEW", "REFERENCE", "DELEGATE"], lambda x: x)
        if not target:
            return
        reason = _ask("選ぶ理由")
        if not reason:
            return
        from .learning import control_learning
        from .personal_skills import read_state
        state = read_state(root, configuration, item["run_id"])
        _mutate(root, configuration, control_learning, item["run_id"], "target", candidate_id=item["id"],
                         target=target, reason=reason, key=_key(), expected_revision=state["revision"])
        print("本人の選択として保存しました。技能の所有と自力での習熟は区別します。")
    elif action == "explain":
        statement = _ask("自分の言葉で説明（空欄: 戻る）")
        if statement:
            from .personal_skills import explain
            _mutate(root, configuration, explain, item["run_id"], candidate_id=item["id"], statement=statement, key=_key())
            print("説明を保存しました。モデルによる採点や習熟の自動認定はしていません。")
    elif action in ("policy", "reuse"):
        _reuse(root, configuration, item, configure_only=action == "policy")


def _reuse(root, configuration, item, configure_only=False):
    from .personal_skills import read_state
    from .assets import project_assets
    from .skill_policy import policy_snapshot, set_policy, route, reuse
    state = read_state(root, configuration, item["run_id"])
    methods = project_assets(state, "ja")["verification_methods"]
    method = _pick("この履歴の検査方法", methods,
                   lambda x: x["property"] if "property" in x else x.get("label", x["id"]))
    if not method:
        print("この履歴に有限検査がなければ、仕事の画面から条件を登録できます。")
        return
    verification = state["verifications"][method["plan_id"]]["plan"]
    target = _ask("適用先を固定", verification["spec"]["target_path"])
    claim = verification["spec"]["claim_id"]
    values = dict(candidate_id=item["id"], asset_id=method["id"], claim_id=claim, target_path=target)
    routed = route(root, configuration, item["run_id"], **values)
    if configure_only or routed["reason"] in ("POLICY_REQUIRED", "OUTSIDE_EXPLICIT_SCOPE"):
        print("この選択を引き継いで、適用範囲を登録します。元ファイルの変更許可ではありません。")
        ai = _pick("AIに任せる範囲", ["check", "propose", "explain"],
                   lambda x: {"check": "条件の検査", "propose": "候補の提示まで", "explain": "説明・参照まで"}[x])
        if not ai:
            return
        mode = _pick("再利用モード", ["assisted", "confirm", "auto-check"],
                     lambda x: {"assisted": "提示は自動・検査は確認", "confirm": "毎回理由を添えて確認",
                                "auto-check": "同じ許可範囲では追加質問なしで検査"}[x])
        if not mode:
            return
        reason = _ask("この範囲を選ぶ理由")
        if not reason or not _yes("対象 " + target + " のこの検査だけを登録しますか"):
            return
        snapshot = policy_snapshot(root, configuration)
        _mutate(root, configuration, set_policy, item["run_id"], candidate_id=item["id"], ai_mode=ai,
                   reuse_mode=mode, paths=[target], asset_ids=[method["id"]], reason=reason,
                   key=_key(), expected_policy_revision=snapshot["revision"])
        if configure_only:
            print("範囲とモードを保存しました。検査はまだ実行していません。")
            return
        routed = route(root, configuration, item["run_id"], **values)
    if routed["status"] not in ("READY", "AWAITING_CONFIRMATION"):
        print("実行せず停止: " + routed["reason"])
        return
    reason = None
    if routed["status"] == "AWAITING_CONFIRMATION":
        if not _yes("表示した対象の有限検査を実行しますか"):
            return
        if routed["policy"]["reuse_mode"] == "confirm":
            reason = _ask("今回適用する理由")
            if not reason:
                return
    result = _mutate(root, configuration, reuse, item["run_id"], **values, scope_id=routed["scope"]["id"],
                   key=_key(), execute=True, confirm_scope=routed["scope"]["id"], judgment_reason=reason)
    print("検査の結果: " + str(result.get("workflow", {}).get("status", result.get("status", "UNKNOWN"))))
    print("外部AI呼び出しなし。許可範囲や期待値を勝手に広げていません。")


def _verify_work(root, configuration, work):
    from .judgment_compiler import compile_conditions
    from .partner_delivery import deliver_artifact, judge_target
    from .cli import visible
    document = (work["state"].get("editor_attempt") or {}).get("document") or {}
    files = document.get("files") or {}
    choices = (["candidate"] if len(files) == 1 else []) + ["project"]
    if len(files) > 1:
        print("生成候補が複数ファイルあります。一括候補の検査は未対応です。元ファイルの検査とは区別します。")
    selected = _pick("検査対象を選ぶ（生成候補と元ファイルは別です）", choices,
                     lambda value: {"candidate": "保存したAI生成候補。元ファイルは変更しない",
                                    "project": "プロジェクト内で指定する現在のファイル。生成候補とは限らない"}[value])
    if not selected:
        return
    target, conditions = _conditions(next(iter(files)) if selected == "candidate" else "")
    if not conditions:
        return
    if selected == "candidate" and target not in files:
        print("この生成候補にはそのファイルがありません。別のファイルへ切り替えて検査しません。")
        return
    contract = compile_conditions(target, conditions)
    reason = _ask("この条件を使う理由（候補の値から正解を推測しないでください）")
    if not reason:
        return
    allow = False
    if selected == "candidate":
        validation = (work["state"].get("editor_attempt") or {}).get("validation") or {}
        print("保存された生成候補 / 解釈の照合: " + visible(str(validation.get("status", "NOT_RECORDED"))))
        if validation.get("status") == "REPAIR_REQUIRED":
            allow = _yes("代替解釈の文章だけの不一致に限り、不一致を残したまま有限条件を検査しますか")
    print("対象: " + visible(target) + " / " + ("生成候補" if selected == "candidate" else "現在のファイル"))
    for condition in conditions:
        print("  " + visible(condition))
    print("外部AIの再呼び出し・生成コードの実行・元ファイルへの上書きは行いません。")
    if not _yes("この有限条件だけを実行し、結果と方法・学習候補を保存しますか"):
        return
    key = _key()
    print("検査の操作キー: " + key)
    if selected == "candidate":
        result = _mutate(root, configuration, deliver_artifact,
                         {"run_id": work["run_id"], "state": work["state"]}, contract,
                         key=key, reason=reason, allow_contested_handoff=allow)
    else:
        result = _mutate(root, configuration, judge_target, work["run_id"], contract,
                         key=key, reason=reason)
    print("検査: " + result["status"])
    if result.get("reason"):
        print("停止理由: " + visible(result["reason"]))
    if result.get("run_id"):
        print("検査記録: " + result["run_id"])
    if result.get("artifact"):
        print("検査した候補: " + visible(result["artifact"]))
    if result.get("recovery_bundle"):
        print("保存先: " + visible(result["recovery_bundle"]["readme"]))


def _work_detail(root, configuration, mode, run_id=None):
    from .development import work_summaries
    from .cli import visible
    work = (next((row for row in work_summaries(root, configuration) if row["run_id"] == run_id), None)
            if run_id else _choose_work(root, configuration))
    if not work:
        return
    selected_id = work["run_id"]
    if work.get("work_plane"):
        from .owner_notebook import open_notebook
        return open_notebook(root, configuration, run_id=selected_id)
    while True:
        # Refresh after each explicit operation. Never ask the user to locate
        # the new judgment run or silently repeat the previous verifier/model.
        work = next((row for row in work_summaries(root, configuration)
                     if row["run_id"] == selected_id), None)
        if not work:
            return
        print("\n仕事: " + visible(work["label"]) + " / " + work["status"])
        print("仕事ID: " + work["run_id"] + " / 最終記録: " + str(work.get("last_recorded_at")))
        print("元の広い主張は、個別の検査成功とは別に扱います。現在のファイルを再検査した表示ではありません。")
        if work.get("artifact_directory"):
            print("成果物: " + visible(str(Path(root) / work["artifact_directory"])))
        for check in work.get("checks", []):
            print("  検査: " + check["status"] + " / " + check["run_id"])
            if check.get("target"):
                print("  検査時の対象: " + visible(check["target"]))
        print("再利用できる方法: " + str(work["methods"]) + "件 / 保持した失敗・未確定記録: " + str(work["failures"]) + "件")
        action = _pick("この仕事で続ける操作", ["continue", "verify", "ownership", "dictionary", "recap", "recover", "newsletter"],
                       lambda x: {"continue": "この仕事への追加依頼（送信前に範囲を確認）",
                                  "verify": "生成候補か現在のファイルを選び、明示条件で検査",
                                  "ownership": "目的・判断・AIの前提・証拠・理解・委譲を一枚で見る",
                                  "dictionary": "この仕事と検査から、学ぶ・委譲する・再利用する",
                                  "recap": "実装・証拠・本人の理解を分けて見る（AI呼び出しなし）",
                                  "recover": "この仕事と検査の資産をファイルへ回収",
                                  "newsletter": "この仕事と検査のニュースレター"}[x])
        if not action:
            return
        if action == "continue":
            result = _new_work(root, configuration, mode, work)
            if result:
                selected_id = result["run_id"]
        elif action == "verify":
            _verify_work(root, configuration, work)
        elif action == "ownership":
            from .ownership_report import report, display
            display(report(root, configuration, work["run_id"], "ja"), "ja")
        elif action == "dictionary":
            _dictionary(root, configuration, run_ids=work["related_runs"])
        elif action == "recap":
            from .experience_report import report
            from .commands_experience import display
            for identity in work["related_runs"]:
                display(report(root, configuration, identity, "ja"), "ja", "recap")
        elif action == "recover":
            from .recovery_bundle import save_recovery
            for identity in work["related_runs"]:
                print(identity + ": " + visible(_mutate(root, configuration, save_recovery, identity)["readme"]))
        elif action == "newsletter":
            _newsletter(root, configuration, work)


def _newsletter(root, configuration, work=None):
    from .personal_skills import stack
    from .skill_newsletter import render
    from .recovery_bundle import _write_files
    work = work or _choose_work(root, configuration)
    if not work:
        return
    library = stack(root, configuration, run_ids=work.get("related_runs", [work["run_id"]]), locale="ja")
    output = "vera-newsletters/" + _key() + ".md"
    body = render(library, title=work["label"], format="markdown")
    def save_draft(project, _configuration):
        _write_files(project, ("vera-newsletters",), {Path(output).name: body.encode("utf-8")})
    _mutate(root, configuration, save_draft)
    print("ローカル原稿: " + str(Path(root) / output))
    print("公開・配信は行っていません。")


_MODEL_PRESETS = {
    "ollama": {
        "title": "Ollamaのローカルモデル",
        "provider": "ollama",
        "endpoint": "http://127.0.0.1:11434/api/chat",
        "key_env": None,
        "loopback": True,
    },
    "openai": {
        "title": "OpenAI API",
        "provider": "openai",
        "endpoint": "https://api.openai.com/v1/responses",
        "key_env": "OPENAI_API_KEY",
        "loopback": False,
    },
    "anthropic": {
        "title": "Anthropic API",
        "provider": "anthropic",
        "endpoint": "https://api.anthropic.com/v1/messages",
        "key_env": "ANTHROPIC_API_KEY",
        "loopback": False,
    },
    "gemini": {
        "title": "Gemini API",
        "provider": "gemini",
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "key_env": "GEMINI_API_KEY",
        "loopback": False,
    },
    "openai_compatible": {
        "title": "OpenAI互換ローカルサーバー",
        "provider": "openai_compatible",
        "endpoint": "http://127.0.0.1:1234/v1/chat/completions",
        "key_env": None,
        "loopback": True,
    },
}


def _model_name(prompt, available=(), unavailable=None):
    value = _ask(prompt).strip()
    if value.isdigit() and 1 <= int(value) <= len(available):
        value = available[int(value) - 1]
    if not value:
        return None
    if value == unavailable:
        print("Creator and reviewer need different models or different endpoints.")
        return None
    return value


def _configure_model_api(root, configuration, preset_name):
    from . import model_settings
    preset = _MODEL_PRESETS[preset_name]
    print("\n--- " + preset["title"] + " ----------------------------------------")
    if preset["key_env"]:
        print("Vera never asks for or stores an API key. It reads " + preset["key_env"] + " only when calling this provider.")
    else:
        print("No API key is stored. This connection is intended for a local server.")
    endpoint = preset["endpoint"]
    if preset_name == "openai_compatible":
        endpoint = _ask("Local server URL", endpoint).strip() or endpoint
        print("Use a server that exposes /v1/responses or /v1/chat/completions.")
    available = model_settings.ollama_models() if preset_name == "ollama" else []
    if available:
        print("Ollama models found on this Mac")
        for index, model in enumerate(available, 1):
            print("  " + str(index) + ". " + model)
    creator = _model_name("Creator model" + (" or number" if available else ""), available)
    if creator is None:
        return
    reviewer = _model_name("Reviewer model (different)" + (" or number" if available else ""), available, creator)
    if reviewer is None:
        return
    creator_endpoint = endpoint.format(model=creator) if "{model}" in endpoint else endpoint
    reviewer_endpoint = endpoint.format(model=reviewer) if "{model}" in endpoint else endpoint
    try:
        saved = model_settings.activate_api(
            root, configuration, provider=preset["provider"],
            label=preset["title"] + " / " + creator + " -> " + reviewer,
            creator_model=creator, reviewer_model=reviewer,
            creator_endpoint=creator_endpoint, reviewer_endpoint=reviewer_endpoint,
            key_env=preset["key_env"], allow_loopback_http=preset["loopback"],
        )
    except (LedgerError, OSError) as error:
        print("Model settings could not be saved. Check the endpoint, model name, or current settings.")
        if getattr(error, "code", "") == "ROLE_COLLISION":
            print("The same external model cannot fill both roles. Choose a different reviewer model.")
        return
    print("Saved for this Cleanroom: " + saved["selection"]["label"])
    print("The next request will use this creator and reviewer pair.")


def _settings_hub(root, configuration):
    from .settings_console import configure
    return configure(root, configuration)


def _legacy_settings_hub(root, configuration):
    from .model_settings import describe
    while True:
        current = describe(configuration)
        print("\n╭─ CLEANROOM SETTINGS ───────────────────────────────────────")
        print("│ Active model: " + current["label"])
        print("│ Project files stay sealed until you explicitly adopt a candidate.")
        print("├────────────────────────────────────────────────────────────")
        print("│ 1. Models & Providers   Choose proposal and review engines")
        print("│ 2. Workspace            View local context and candidate scope")
        print("│ 3. Boundary             Review what AI may and may not change")
        print("│ 4. Notebook             Review learning and retained assets")
        print("│ 5. Advanced             Open the detailed project setup")
        print("│ 0. Back to Notebook")
        print("╰────────────────────────────────────────────────────────────")
        choice = _ask("Select").strip().casefold()
        if choice in ("", "0", "back"):
            return
        if choice == "1":
            _model_settings(root, configuration)
        elif choice == "2":
            print("\nWORKSPACE")
            print("Cleanroom root: " + str(Path(root).resolve()))
            print("Context: project-local related files only")
            print("Excluded: secrets, project-external paths, prior notebooks")
            print("Candidates: isolated Vera work records")
        elif choice == "3":
            print("\nBOUNDARY")
            print("Read project context → write an isolated candidate → human adoption")
            print("A model response cannot grant itself permission, evidence, or a project change.")
        elif choice == "4":
            print("\nNOTEBOOK")
            print("After work, Vera retains Project Delta, System Delta, and Human Delta.")
            print("Learning is visible debt, not a gate that blocks safe work.")
        elif choice == "5":
            print("Advanced setup remains explicit: verantyx setup --guided")
        else:
            print("Choose a numbered setting or 0 to return to the notebook.")


def _model_settings(root, configuration):
    from .agent_console import configure
    return configure(root, configuration)


def _legacy_model_settings(root, configuration):
    from . import model_settings
    while True:
        current = model_settings.describe(configuration)
        print("\n╭─ MODELS & PROVIDERS ───────────────────────────────────────")
        print("│ Active: " + current["label"])
        print("│ Model output is a candidate. Cleanroom adoption and evidence remain in Vera.")
        print("├────────────────────────────────────────────────────────────")
        print("│ 1. ChatGPT Codex Subscription")
        print("│ 2. Ollama Local Models")
        print("│ 3. OpenAI API")
        print("│ 4. Anthropic API")
        print("│ 5. Gemini API")
        print("│ 6. OpenAI-Compatible Local Server")
        print("│ 7. Restore the Default Codex Connection")
        print("│ 0. Back to Cleanroom Settings")
        print("╰────────────────────────────────────────────────────────────")
        choice = _ask("Select").strip().casefold()
        if choice in ("", "0", "back"):
            return
        try:
            if choice == "1":
                saved = model_settings.activate_codex(root, configuration)
                print("Saved for this Cleanroom: " + saved["selection"]["label"])
            elif choice == "2":
                _configure_model_api(root, configuration, "ollama")
            elif choice == "3":
                _configure_model_api(root, configuration, "openai")
            elif choice == "4":
                _configure_model_api(root, configuration, "anthropic")
            elif choice == "5":
                _configure_model_api(root, configuration, "gemini")
            elif choice == "6":
                _configure_model_api(root, configuration, "openai_compatible")
            elif choice == "7":
                model_settings.clear(root, configuration)
                print("Restored the default Codex connection.")
            else:
                print("Choose a numbered provider or 0 to return to Cleanroom Settings.")
        except (LedgerError, OSError):
            print("Model settings could not be saved. The existing Cleanroom configuration is unchanged.")


def _notebook_index():
    from .cleanroom_notebook import render_notebook_index
    render_notebook_index()


def _notebook_intent(value):
    normalized = value.strip().rstrip("。！？!?").casefold()
    phrases = {
        "これまでの仕事を見る": "history",
        "仕事を見る": "history",
        "履歴を見る": "history",
        "学習ノートを開く": "learn",
        "学習を見る": "learn",
        "理解を見る": "learn",
        "残した資産を見る": "assets",
        "資産を見る": "assets",
        "判断と証拠を見る": "decisions",
        "判断を見る": "decisions",
        "証拠を見る": "decisions",
        "送信範囲を見る": "scope",
        "送るファイルを見る": "scope",
        "モデルを設定する": "models",
        "AIを設定する": "models",
        "モデルを見る": "models",
        "設定を見る": "settings",
        "設定を確認する": "settings",
        "設定を開く": "settings",
        "モデル接続を変える": "models",
        "ローカル要約を作る": "export",
        "要約を作る": "export",
        "project": "project",
        "プロジェクト": "project",
        "今のプロジェクト": "project",
        "今のプロジェクトを見せて": "project",
        "プロジェクトを理解したい": "project",
        "review": "review",
        "レビュー": "review",
        "確認が必要なことを見る": "review",
        "レビューを開く": "review",
        "notebook": "notebook",
        "ノート": "notebook",
        "ノートを見る": "notebook",
        "記録を見る": "notebook",
        "今の仕事": "history",
        "今の仕事を見せて": "history",
        "操作一覧": "index",
        "使い方": "index",
        "?": "index",
        "終了": "quit",
        "終わる": "quit",
        "やめる": "quit",
        "/profile": "personal-profile",
        "/journal": "personal-journal",
        "/next": "personal-next",
        "/pace": "personal-pace",
        "/history": "history",
        "/learn": "learn",
        "/assets": "assets",
        "/decisions": "decisions",
        "/details": "decisions",
        "/scope": "scope",
        "/model": "models",
        "/settings": "settings",
        "/mode": "settings",
        "/export": "export",
        "/digest": "export",
        "/help": "index",
        "/quit": "quit",
        "/exit": "quit",
    }
    return phrases.get(normalized)


def _notebook_action(root, configuration, mode, action):
    if action.startswith("personal-"):
        from .personal_console import menu
        menu(root, configuration, action.removeprefix("personal-"))
        return False
    if action in ("project", "review", "notebook", "history", "learn", "assets", "decisions"):
        from .owner_notebook import show_project, open_notebook
        if action == "project":
            show_project(root, configuration)
        else:
            open_notebook(root, configuration, section="learn" if action == "learn" else action)
        return False
    if action == "quit":
        return True
    if action == "project":
        from .cleanroom_notebook import render_project_map
        render_project_map(root, configuration, _context_files(root))
    elif action == "review":
        from .cleanroom_notebook import render_review_queue
        render_review_queue(root, configuration)
    elif action == "notebook":
        _work_detail(root, configuration, mode)
    elif action == "index":
        _notebook_index()
    elif action == "history":
        _work_detail(root, configuration, mode)
    elif action in ("learn", "assets"):
        _dictionary(root, configuration)
    elif action == "decisions":
        print("仕事を選ぶと、人間の判断、AIの仮定、証拠、UNKNOWNを確認できます。")
        _work_detail(root, configuration, mode)
    elif action == "scope":
        files = _context_files(root)
        print("\n--- Cleanroomの送信範囲 --------------------------------------")
        print("通常の送信範囲: 現在のプロジェクト内のみ")
        print("秘密情報候補とプロジェクト外は送信しません。")
        for path in files:
            print("  " + path)
    elif action == "models":
        _model_settings(root, configuration)
    elif action == "settings":
        _settings_hub(root, configuration)
    elif action == "export":
        _newsletter(root, configuration)
    else:
        _notebook_index()
    return False


def _friendly_error(error):
    code = getattr(error, "code", type(error).__name__)
    if code == "PATH_SCOPE":
        print("開始できませんでした。フォルダやプロジェクト外の場所は通常の送信範囲に含めません。")
        print("通常はファイルを選ぶ必要はありません。依頼だけを入力すれば、Veraがプロジェクト内の関連ファイルを選びます。")
    elif code in ("BRIDGE_START_FAILED", "BRIDGE_PROCESS_FAILED", "CODEX_CALL_FAILED"):
        print("AIへの接続を開始できませんでした。保存済みの判断と作業履歴は失われていません。")
        print("接続設定は「設定を見る」とノートに書いて確認できます。")
    else:
        print("この仕事はまだ開始していません。必要な情報を確認してから、同じ依頼をもう一度送れます。")
        print("詳細な状態は「判断と証拠を見る」とノートに書いて確認できます。")


def interact(root, configuration, onboarding=False):
    from .personal_console import first_open
    first_open(root, configuration)
    mode = "assisted"
    if onboarding:
        from .cleanroom_notebook import render_first_open
        render_first_open(root)
        choice = input("\nEnterで研究ノートを開く、dで詳細を見る> ").strip().casefold()
        if choice == "d":
            print("AIは候補を作り、Cleanroomは目的、判断、証拠、UNKNOWN、経験を別々に残します。採用されるまで本体には入りません。")
    from .cleanroom_notebook import render_workspace_header
    render_workspace_header(root, configuration)
    while True:
        try:
            request = _ask("ノートに書く")
            if not request:
                return {"ok": True, "command": "develop", "status": "CLOSED"}
            intent = _notebook_intent(request)
            if intent:
                if _notebook_action(root, configuration, mode, intent):
                    return {"ok": True, "command": "develop", "status": "CLOSED"}
                continue
            _new_work(root, configuration, mode, request=request)
        except (EOFError, KeyboardInterrupt):
            print("\n中止しました。保存済みの履歴は残します。")
            return {"ok": True, "command": "develop", "status": "CLOSED"}
        except (LedgerError, OSError) as error:
            _friendly_error(error)
