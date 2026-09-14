"""Human-facing connected work and ownership UI using existing operations."""
from pathlib import Path
import os
import uuid

from .errors import LedgerError


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
    value = input(prompt + (" [" + default + "]" if default else "") + "> ").strip()
    return value or default


def _yes(prompt):
    return _ask(prompt + " [y/N]").lower() == "y"


def _start(prompt):
    return _ask(prompt + " [Y/n]", "y").lower() not in ("n", "no")


def _pick(title, rows, label):
    from .cli import visible
    if not rows:
        print(title + ": まだ記録がありません。")
        return None
    print("\n" + title)
    for i, row in enumerate(rows, 1):
        print(str(i) + ". " + visible(label(row)))
    value = _ask("番号（0: 戻る）", "0")
    if not value.isdigit() or not 1 <= int(value) <= len(rows):
        return None
    return rows[int(value) - 1]


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
    print("\n--- 今日の記録 ------------------------------------------------")
    print("ノートに書いたこと: " + result.get("request", result.get("run_id", "")))
    print("いまの状態: " + _friendly_status(result.get("status", "UNKNOWN")))
    gate = result.get("task_gate")
    print("\n[ Cleanroom / あなたのプロジェクト ]")
    if result.get("artifact_directory"):
        print("AIの候補帳: " + str(Path(root) / result["artifact_directory"]))
        print("本体: 変更していません。採用はあなたが決めます。")
    else:
        print("本体: 今回もCleanroomの外からは変更していません")
    print("\n[ 作業帳 / Veraが残したもの ]")
    if result.get("judgment_run"):
        print("次回も使える検査: " + result["judgment_run"])
    else:
        print("判断、仮定、検証方法、失敗候補を作業帳へ保存しました")
    print("\n[ あなたへの付箋 ]")
    if isinstance(gate, dict) and gate.get("human_assumption"):
        print("今回あなたが決めたこと: " + str(gate["human_assumption"]))
    for item in result.get("learning_proposals", [])[:2]:
        if item.get("concept"):
            print("後から見直せる理解: " + item["concept"])
    if not result.get("learning_proposals"):
        print("学習候補: 今回は付箋を増やしませんでした")
    if result.get("next_action"):
        print("確認したいこと: " + result["next_action"])
    elif result.get("reason"):
        print("確認が必要な点: " + result["reason"])
    print("続きは「これまでの仕事を見る」とノートに書けば開けます。")


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
    print("\n--- 作業前のメモ ----------------------------------------------")
    print("Cleanroom: 本体はあなたが採用するまで変えません")
    print("AIの作業帳: 現在の構成を読み、候補と検査記録を作ります")
    print("あなたへの付箋: " + ("今回の前提を一つ確認します" if preflight.get("question") else "必要になったときだけ判断を返します"))
    print("送信する範囲: プロジェクト内の関連ファイル " + str(len(context_files)) + "件")
    print("送信しないもの: プロジェクト外、秘密情報候補、既存の作業帳")
    if previous:
        print("前の頁から続ける: " + previous["label"])


def _confirm_context(context_files):
    while True:
        choice = input("Enterで作業帳を開く、vで送信範囲、nで中止> ").strip().casefold()
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


def _new_work(root, configuration, mode, previous=None, request=None):
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


def _notebook_index():
    print("\n--- ノートの索引 ----------------------------------------------")
    print("コマンドを覚える必要はありません。次の言葉を、そのままノートに書けます。")
    print("  これまでの仕事を見る     過去の候補と続きを開く")
    print("  学習ノートを開く         後から身につける理解と委譲を開く")
    print("  残した資産を見る         判断、検査、失敗事例を読む")
    print("  判断と証拠を見る         人間の判断、AIの仮定、UNKNOWNを確認する")
    print("  送信範囲を見る           次の作業でAIに渡るファイルを確認する")
    print("  設定を見る               Cleanroomの通常設定を確認する")
    print("  ローカル要約を作る       今回までの記録をまとめる")
    print("  終了                     ノートを閉じる")
    print("? でもこの索引を開けます。")


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
        "設定を見る": "settings",
        "設定を確認する": "settings",
        "ローカル要約を作る": "export",
        "要約を作る": "export",
        "操作一覧": "index",
        "使い方": "index",
        "?": "index",
        "終了": "quit",
        "終わる": "quit",
        "やめる": "quit",
        "/history": "history",
        "/learn": "learn",
        "/assets": "assets",
        "/decisions": "decisions",
        "/details": "decisions",
        "/scope": "scope",
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
    if action == "quit":
        return True
    if action == "index":
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
    elif action == "settings":
        print("\n--- Cleanroomの設定 ------------------------------------------")
        print("通常設定: プロジェクト内のみ / 候補を隔離保存 / 本体への採用は明示確認後 / 学習は作業後に短く表示")
        print("詳細設定: verantyx setup --guided")
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
    mode = "assisted"
    if onboarding:
        print("\nVera / Cleanroom Notebook")
        print("AIに作らせても、開発者であることまで手放さない。")
        print("\n" + Path(root).name + " をCleanroomとして開きます")
        print("  読み取り  このプロジェクト内だけ")
        print("  書き込み  隔離された候補にだけ行う")
        print("  本体採用  あなたの確認後")
        print("  記録      判断・検査・失敗・学びを作業帳へ残す")
        choice = input("\nEnterで共同開発を始める、dで詳細を見る> ").strip().casefold()
        if choice == "d":
            print("AIはCleanroomの外に候補を書きます。あなたが採用したものだけが本体に入ります。判断・検査・失敗・理解は、モデルではなくローカルの作業帳に残ります。")
    print("\nVera / " + Path(root).name + " の作業ノート")
    print("Cleanroomは未変更  |  AIは候補帳に書く  |  ? でノートの索引")
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
