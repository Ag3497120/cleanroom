"""Human-facing connected work and ownership UI using existing operations."""
from pathlib import Path
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


def show_result(root, result):
    print("\n仕事: " + result.get("request", result.get("run_id", "")))
    print("今回の到達点: " + result.get("status", "UNKNOWN"))
    gate = result.get("task_gate")
    if isinstance(gate, dict):
        print("判断ゲート: " + str(gate.get("status", "UNKNOWN")))
        if gate.get("human_assumption"):
            print("今回だけの人間前提: " + str(gate["human_assumption"]))
    print("正規ファイルへの採用: していません / 人間の習熟: 認定しません")
    if result.get("artifact_directory"):
        print("成果物: " + str(Path(root) / result["artifact_directory"]))
    if result.get("judgment_run"):
        print("条件付き検査の記録: " + result["judgment_run"])
    if result.get("handoff"):
        print("解釈の照合: " + result["handoff"]["status"])
    print("学習候補: " + str(len(result.get("learning_candidates", []))))
    for item in result.get("learning_proposals", []):
        print("  " + item["concept"])
    if result.get("recovery_bundle"):
        print("回収した判断・方法・学習: " + result["recovery_bundle"].get("readme", "未保存"))
    if result.get("reason"):
        print("次に解決する点: " + result["reason"])
    if result.get("next_action"):
        print(result["next_action"])
    if result.get("historical_receipt"):
        print("保存済みの結果です。再送による追加のAI呼び出しはありません。")
    print("同じ仕事への追加依頼は「仕事の続き」から選べます。")


def _new_work(root, configuration, mode, previous=None):
    from .development import run_work
    from .constitution import assess
    request = _ask("追加依頼" if previous else "AIへ任せる仕事（空欄: 戻る）")
    if not request:
        return
    includes = []
    print("外部へ送るファイルを選びます。フォルダ全体は自動送信しません。")
    for _ in range(16):
        path = _ask("ファイル（空欄: 終了）")
        if not path:
            break
        includes.append(path)
    target, conditions = _conditions()
    allow = _yes("代替解釈の文章だけが不一致の場合、合意は未確認のまま候補を受け取りますか")
    preflight = assess(root, configuration, request)
    print("判断ゲート: " + preflight["status"])
    print(preflight["reason"])
    assumption = None
    if preflight.get("question"):
        print("人間に残す判断: " + preflight["question"])
        assumption = _ask("今回だけの前提（空欄: 判断ギャップとして保存）")
    print("モデル: gpt-5.3-codex-spark / low、実装役と検証役。独自の生成回数上限なし。")
    print("送信範囲: " + request + " / " + ", ".join(includes))
    if previous:
        print("引き継ぐ記録: " + previous["label"])
    if not _yes("この範囲を送信し、候補生成と資産回収を開始しますか"):
        return
    result = _mutate(root, configuration, run_work, request=request, key=_key(), include=includes,
                      target=target, expectations=conditions, mode=mode,
                      allow_contested=allow, continue_from=previous["run_id"] if previous else None,
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


def interact(root, configuration):
    mode = "assisted"
    print("Vera / 仕事から、判断と自分の理解を取り戻す")
    print("個人の技能資産: " + str(root))
    print("Spark / low の二役。独自の生成回数上限なし。モデル設定画面はありません。")
    while True:
        print("\n1. AIへ仕事を依頼  2. 外部AIの仕事を取り込む  3. 仕事の続き・成果物")
        print("4. 学習と委譲の辞書  5. ニュースレター  6. 資産化モード")
        print("7. 詳細な既存台帳  0. 終了 / 現在の資産化: " + mode)
        try:
            action = _ask("操作", "0")
            if action == "0":
                return {"ok": True, "command": "develop", "status": "CLOSED"}
            if action == "1":
                result = _new_work(root, configuration, mode)
                if result:
                    _work_detail(root, configuration, mode, result["run_id"])
            elif action == "2":
                result = _import(root, configuration, mode)
                if result:
                    _work_detail(root, configuration, mode, result["run_id"])
            elif action == "3":
                _work_detail(root, configuration, mode)
            elif action == "4":
                _dictionary(root, configuration)
            elif action == "5":
                _newsletter(root, configuration)
            elif action == "6":
                selected = _pick("次の仕事から適用", ["assisted", "auto", "manual"],
                                 lambda x: {"assisted": "原文と局所的な候補を回収。詳しいAI資産化は任意",
                                            "auto": "取り込み時にも二役で資産候補を作成",
                                            "manual": "原文の記録を中心に、明示した条件だけを扱う"}[x])
                mode = selected or mode
            elif action == "7":
                import subprocess
                import sys
                subprocess.run([sys.executable, "-m", "verantyx", "--project", str(root),
                                "--lang", "ja", "skills", "--interactive"], check=False)
        except (EOFError, KeyboardInterrupt):
            print("\n中止しました。保存済みの履歴は残します。")
            return {"ok": True, "command": "develop", "status": "CLOSED"}
        except (LedgerError, OSError) as error:
            print("実行を停止: " + getattr(error, "code", type(error).__name__))
            details = getattr(error, "details", None)
            if details:
                print(str(details))
            print("条件は JSON /retry_limit = 3 のような明示形式です。失敗を合格扱いせず、履歴から続けられます。")
