"""Numbered views and explicitly confirmed, existing finite-contract commands."""
from pathlib import Path

from .commands_skills_home import _call, _choose, _key, _path, _safe


def _field(label, value, _indent=0):
    prefix = "  " * _indent
    if value is None or value == "" or value == [] or value == {}:
        value = "未記録 / UNKNOWN"
    if isinstance(value, (dict, list)):
        print(prefix + _safe(label) + ":")
        entries = value.items() if isinstance(value, dict) else enumerate(value, 1)
        for key, item in entries:
            _field(str(key), item, _indent + 1)
    else:
        lines = str(value).splitlines() or [""]
        print(prefix + _safe(label) + ": " + _safe(lines[0]))
        for line in lines[1:]:
            print(prefix + "  " + _safe(line))


def show_error_reason(error):
    details = getattr(error, "details", None)
    if not isinstance(details, dict):
        return
    # Only bounded symbolic reason codes, never arbitrary payloads or paths.
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
    for key in ("reason", "code", "cause"):
        value = details.get(key)
        if isinstance(value, str) and 0 < len(value) <= 96 and all(char in alphabet for char in value):
            _field("詳細の理由コード / " + key, value)
            if "EXPIRED" in value or "STALE" in value:
                print("観測が期限切れの場合は、13. 観測を更新 で再観測し、9 で新しい範囲を選び直してください。")


def _skill(work, *, recorded=False):
    rows = work.get("skills", [])
    if recorded:
        rows = [row for row in rows if row.get("recorded")]
        if not rows:
            print("先に 3. 保有対象を選択 で候補を明示的に選んでください。学習選択は実行許可ではありません。")
            return None
    return _choose("対象のスキル", rows, lambda row: row.get("concept", row["id"]))


def inspect_skill(root, locale, work):
    skill = _skill(work)
    if skill is None:
        return
    print("\nスキルの記録。モデルの意見は証拠ではなく、自己説明は習熟の認定ではありません。")
    _field("概念", skill.get("concept"))
    _field("保有対象", skill.get("ownership_target"))
    print("保有対象の由来: " + ("提案・未選択" if skill.get("target_is_suggestion", True) else "人が選択"))
    for label, name in (("理由・今学ぶ理由", "why_now"), ("最小モデル", "minimum_model"),
                        ("反例", "counterexample"), ("確認方法", "check"),
                        ("出典", "source_refs"), ("記録参照", "source_ref"),
                        ("提出状態", "submission_state"), ("習熟評価の記録値", "mastery_assessment")):
        _field(label, skill.get(name))
    _field("本人の説明（自己申告）", skill.get("explanations"))
    for row in work.get("judgments", []):
        _field("同じ作業の人の判断（このスキルの根拠と自動認定しない）",
               {key: row.get(key) for key in ("point_id", "choice", "reason", "source_ref")})
    _field("別途記録された実行ポリシー", skill.get("ai_policy"))
    _failures(work)


def _failures(work):
    for row in work.get("failures", []):
        _field("記録済みの失敗", {key: row.get(key) for key in
               ("id", "reason", "outcome", "closure", "source_refs")})


def _binding(root, locale, work, *, claim_required):
    skill = _skill(work, recorded=True)
    if skill is None:
        return None
    library = _call(root, locale, ["skills-stack", "--limit", "100"])
    methods = [(owner, method) for owner in library.get("works", [])
               for method in owner.get("methods", [])
               if method.get("family") == "VERIFICATION"
               and (method.get("contract_summary") or {}).get("method") in ("TEST", "NEGATIVE_CONTROL")]
    if library.get("omitted_runs"):
        print("一覧は最大100作業です。ここにない方法を未保存とは判断しません。")
    if not methods:
        print("表示範囲には再利用できる有限 TEST / NEGATIVE_CONTROL 契約がありません。")
        print("候補の文章は実行可能な方法ではありません。12. 検証方法をファイルから登録 を選んでください。")
        return None
    selected = _choose("記録済みの検証方法（記録済み != 今回合格）", methods,
                       lambda pair: str(pair[0].get("label", pair[0]["run_id"])) + " / "
                       + str(pair[1].get("name", pair[1]["id"])) + " / " + str(pair[1].get("status", "UNKNOWN")))
    if selected is None:
        return None
    owner, method = selected
    _field("方法", {key: method.get(key) for key in
                   ("id", "family", "status", "contract_hash", "contract_summary", "latest_outcome", "source_refs")})
    _failures(owner)
    state = _call(root, locale, ["replay", work["run_id"]]).get("state", {})
    paths = sorted(state.get("latest_observations", {}))
    target = _choose("この作業で観測が記録された対象（現在の内容は経路判定で確認）", paths, str)
    if target is None:
        print("対象の入力観測が必要です。メニューから新しい対象や検証仕様は作りません。")
        return None
    claim = None
    if claim_required:
        claims = (state.get("proposal") or {}).get("claims", [])
        claim = _choose("この作業の記録済み claim", claims,
                        lambda row: str(row.get("statement", row["id"])) + " / " + row["id"])
        if claim is None:
            return None
    return skill, method, target, claim


def partner(root, locale):
    request = input("相談・実装したい依頼（空欄: 中止）> ").strip()
    if not request:
        return
    creator = _path(root, "creator adapter の既存ファイル（空欄: 中止）> ")
    if creator is None:
        return
    reviewer = _path(root, "reviewer adapter の既存ファイル（空欄: 中止）> ")
    if reviewer is None:
        return
    selection = input("モード 1. discuss / 相談  2. implement / 実装（空欄: 1）> ").strip() or "1"
    mode = {"1": "discuss", "2": "implement"}.get(selection)
    if mode is None:
        print("1 または 2 を選んでください。呼出しは行っていません。")
        return
    includes = []
    for _ in range(16):
        path = _path(root, "追加で含めるファイル（最大16件、空欄: 入力終了）> ")
        if path is None:
            break
        from .adapters.observations import normalize_path
        selected_path = Path(path)
        if selected_path.is_absolute():
            try:
                selected_path = selected_path.relative_to(root)
            except ValueError:
                print("追加ファイルはライブラリ内を指定してください。外部送信は行っていません。")
                return
        relative = normalize_path(selected_path.as_posix())
        if relative not in includes:
            includes.append(relative)
    _field("外部送信する依頼", request)
    _field("使用する adapter", {"creator": creator, "reviewer": reviewer})
    _field("モード", mode)
    if includes:
        _field("追加で送信するファイル", includes)
    else:
        print("追加ファイル: なし")
    print("依頼・既存の作業文脈・指定ファイルが設定先へ送信されます。外部呼出しは最大2回、既存の予算制限に従います。")
    print("--execute / --precedent は付けません。自動承認・自動修復・自動再試行は行いません。")
    if input("表示した設定で外部送信を開始しますか [y/N]> ").strip().lower() != "y":
        return
    key = _key()
    print("今回の key: " + key + "（結果不明でも自動再試行しません）")
    args = ["partner", request, "--creator-adapter", creator, "--reviewer-adapter", reviewer,
            "--mode", mode, "--key", key]
    for path in includes:
        args.extend(["--include", path])
    result = _call(root, locale, args)
    from .cli import kernel_output
    kernel_output(result, locale, False, "partner")


def register_spec(root, locale, work):
    path = _path(root, "既存形式の検証仕様ファイル（相対パスはこのライブラリ基準、空欄: 中止）> ")
    if path is None:
        return
    _field("読み込むファイル", path)
    _field("登録先の作業", work.get("label", work["run_id"]))
    _field("確認する現在の revision", work["revision"])
    print("仕様内には既存の claim・対象・明示した期待値が必要です。内容を生成・補完しません。")
    print("keep --check の通常の入力署名・権限・観測・revision 検査を通して計画だけ保存します。")
    print("検証実行・合格認定・習熟認定・自動実行の許可は行いません。")
    if input("表示したファイルから検証方法を登録しますか [y/N]> ").strip().lower() != "y":
        return
    key = _key()
    print("今回の key: " + key + "（結果不明でも自動再試行しません）")
    result = _call(root, locale, ["keep", work["run_id"], "--check", path, "--key", key,
                                 "--expected-revision", str(work["revision"])])
    _field("登録結果", {"ok": result.get("ok"), "operation": result.get("operation"),
                     "writes": result.get("writes"), "error": result.get("error"),
                     "method_status": (result.get("capture") or {}).get("method_status")})
    print("DRAFT / PLANNED は方法の保存であり、検証成功ではありません。")
    print("保存済みの TEST / NEGATIVE_CONTROL は 8 で範囲を登録し、9 で別途確認して再利用できます。")


def refresh_observations(root, locale, work):
    replay = _call(root, locale, ["replay", work["run_id"]])
    state = replay.get("state") or {}
    paths = sorted({path for path in [*(state.get("read_scope") or []),
                   *(state.get("latest_observations") or {})] if isinstance(path, str)})
    if paths:
        choices = [{"label": "すべての記録済み対象", "paths": paths}]
        choices.extend({"label": path, "paths": [path]} for path in paths)
        selected = _choose("再観測する対象", choices, lambda row: row["label"])
        if selected is None:
            return
        paths = selected["paths"]
    else:
        path = input("観測する明示的な相対パス（空欄: 中止）> ").strip()
        if not path:
            return
        if Path(path).is_absolute():
            print("ライブラリ基準の相対パスを指定してください。読み取りは行っていません。")
            return
        paths = [path]
    revision = replay.get("revision", state.get("revision", work["revision"]))
    _field("読み直す対象（ライブラリ基準）", paths)
    _field("確認する現在の revision", revision)
    print("通常の権限・パス検査に従って対象を読み、観測を記録します。検証・モデル呼出しはしません。")
    if input("表示した対象の読み取りと観測更新を許可しますか [y/N]> ").strip().lower() != "y":
        return
    key = _key()
    print("今回の key: " + key + "（自動再試行しません）")
    args = ["resume", work["run_id"], "--expected-revision", str(revision), "--key", key]
    for path in paths:
        args.extend(["--observe", path])
    result = _call(root, locale, args)
    _field("観測更新の結果", {key: result.get(key) for key in
           ("ok", "run_id", "revision", "recorded_revision", "duplicate", "error")})
    print("更新後の自動検証は行いません。9 を選び直し、新しい範囲を確認してから再利用してください。")


def register_method(root, locale, work):
    binding = _binding(root, locale, work, claim_required=False)
    if binding is None:
        return
    skill, method, target, _ = binding
    current = _call(root, locale, ["skills-policies", "--run", work["run_id"]])
    for row in current.get("policies", []):
        if row.get("candidate_id") == skill["id"]:
            _field("置き換える既存ポリシー", row)
    print("登録範囲: 選んだ方法 + 対象パスのみ。claim と現在の内容は再利用時に確認します。")
    selected_mode = _choose("次回からの確認方法（学習の保有対象とは別）", [
        {"mode": "confirm", "label": "毎回、理由と対象を確認する"},
        {"mode": "assisted", "label": "対象だけ確認する。理由を繰り返し聞かない"},
        {"mode": "auto-check", "label": "登録した方法・対象内では追加確認を省略する"},
    ], lambda row: row["label"])
    if selected_mode is None:
        return
    print("ai-mode=check / reuse-mode=" + selected_mode["mode"]
          + "。検証は今は実行しません。保有対象・習熟評価は変更しません。")
    print("範囲外・内容の変化・期限切れ・通常の権限不足は、確認省略でも停止します。")
    _field("対象", target)
    reason = input("この範囲で方法を利用する人の理由（空欄: 中止）> ").strip()
    if not reason or input("このポリシーを登録しますか [y/N]> ").strip().lower() != "y":
        return
    result = _call(root, locale, ["skills-policy-set", work["run_id"], "--candidate", skill["id"],
        "--ai-mode", "check", "--reuse-mode", selected_mode["mode"], "--path", target, "--asset", method["id"],
        "--reason", reason, "--key", _key(), "--expected-policy-revision", str(current["revision"])])
    _field("ポリシー登録", {key: result.get(key) for key in
           ("ok", "policy_id", "recorded_revision", "duplicate", "execution_authorized", "error")})
    print("登録は検証の実行でも合格でもありません。再利用は 9 から別途確認してください。")


def reuse_method(root, locale, work):
    binding = _binding(root, locale, work, claim_required=True)
    if binding is None:
        return
    skill, method, target, claim = binding
    args = [work["run_id"], "--candidate", skill["id"], "--asset", method["id"],
            "--claim", claim["id"], "--target", target]
    route = _call(root, locale, ["skills-route", *args])
    _field("経路判定（まだ検証していません）", {key: route.get(key) for key in
           ("ok", "status", "reason", "scope", "cross", "execution_performed")})
    if not route.get("ok") or route.get("status") not in ("READY", "AWAITING_CONFIRMATION"):
        print("実行しません。BLOCKED / UNKNOWN / PLAN_ONLY は合格ではありません。")
        return
    scope = route.get("scope") or {}
    if not scope.get("id"):
        print("確認可能な範囲 ID がないため停止しました。")
        return
    _field("今回の変更しない検証契約", route.get("method"))
    _field("現在のポリシー", route.get("policy"))
    print("上記の方法・claim・対象・現在の内容に限定した有限検証です。モデル呼出しや自動修復はしません。")
    mode = route["policy"]["reuse_mode"]
    reason = None
    if mode == "confirm":
        reason = input("この範囲で今回検証する人の理由（空欄: 中止）> ").strip()
        if not reason:
            return
    if mode != "auto-check":
        if input("表示した範囲で一度だけ検証しますか [y/N]> ").strip().lower() != "y":
            return
    else:
        print("登録済みの範囲内です。保存した方針に従い、同じ判断をもう一度質問せず有限検証を実行します。")
    key = _key()
    print("今回の key: " + key + "（結果不明でも自動再試行しません）")
    execution_args = ["skills-reuse", *args, "--scope-id", scope["id"], "--key", key, "--execute"]
    if mode != "auto-check":
        execution_args.extend(["--confirm-scope", scope["id"]])
    if reason:
        execution_args.extend(["--judgment-reason", reason])
    result = _call(root, locale, execution_args)
    workflow = result.get("workflow") or {}
    _field("有限検証の結果", {key: result.get(key) for key in
           ("ok", "workflow_id", "status", "reason", "error", "execution_performed", "duplicate", "historical_receipt")})
    _field("workflow の状態", workflow.get("status"))
    for row in workflow.get("results") or []:
        if isinstance(row, dict):
            _field("検証ステップの結果", {key: row.get(key) for key in
                   ("step_id", "status", "closure", "reason", "source_ref")})
    print("COMPLETED もこの範囲の結果のみです。REFUTED / CONTESTED / UNKNOWN を成功と扱いません。")
    print("習熟・一般的正しさ・新しい実行権限は認定しません。自動修復・自動再試行は行いません。")


def report(root, locale, view):
    scope = _choose("成果レポートの範囲", [{"run_id": None, "label": "すべての作業（最大24件）"},
                    *view.get("works", [])], lambda row: row["label"])
    if scope is None:
        return
    args = ["skills-report", "--limit", "24"]
    if scope["run_id"] is not None:
        args.extend(["--run", scope["run_id"]])
    query = input("絞込語（空欄: 絞込なし）> ").strip()
    if query:
        args.extend(["--query", query])
    result = _call(root, locale, args)
    from .cli import kernel_output
    kernel_output(result, locale, False, "skills-report")
