"""Read-only skills home; optional navigation starts after command dispatch."""
from pathlib import Path
import sys
import uuid

from .errors import LedgerError

COMMANDS = {"skills"}
TARGETS = ("OWN", "REVIEW", "REFERENCE", "DELEGATE")


def register(sub):
    parser = sub.add_parser("skills", add_help=False, allow_abbrev=False)
    parser.add_argument("--interactive", action="store_true")


def dispatch(root, configuration, args, locale):
    from .personal_skills import stack
    return {**stack(root, configuration, locale=locale), "command": "skills",
            "root": str(root), "interactive_requested": bool(args.interactive)}


def _safe(value):
    from .cli import visible
    return visible(str(value))


def _call(root, locale, argv):
    from .console import _operation
    return _operation(root, locale, argv)


def _overview(view):
    works = view.get("works", [])
    print("個人スキルライブラリ / 作業 " + str(len(works)) + "件")
    for number, work in enumerate(works, 1):
        print(str(number) + ". " + _safe(work.get("label", "名称未記録"))[:200])
        skills = work.get("skills", [])
        for skill in skills[:3]:
            selected = "提案" if skill.get("target_is_suggestion", True) else "本人の選択"
            print("   " + _safe(skill.get("concept", "名称未記録"))[:180] + " / "
                  + _safe(skill.get("ownership_target", "未選択")) + " / " + selected)
        if not skills:
            print("   学習項目は未記録。原文の取込だけで技能の完成とは扱いません。")
        print("   学習項目 " + str(len(skills)) + " / 実行契約 " + str(len(work.get("methods", [])))
              + " / 失敗 " + str(len(work.get("failures", [])))
              + " / 未検証候補 " + str(len(work.get("candidates", []))))
    if view.get("omitted_runs"):
        print("表示上限による省略: " + str(view["omitted_runs"]) + "件。詳細は skills-stack で範囲を指定してください。")
    print("この一覧だけでは生成の完了や合格を認定しません。保有対象の選択と実行権限は別です。")
    print("操作を始める: verantyx skills --interactive")
    print("詳細な AI 範囲・経路・再利用: skills-policy-set / skills-route / skills-reuse")


def _choose(title, items, label):
    if not items:
        print("選べる項目がありません。必要なら先に取込・生成・保有対象の選択を行ってください。")
        return None
    print(title)
    for number, item in enumerate(items, 1):
        print(str(number) + ". " + _safe(label(item))[:200])
    answer = input("番号（0: 戻る）> ").strip()
    if answer == "0" or not answer:
        return None
    if not answer.isascii() or not answer.isdigit() or len(answer) > 3 or not 1 <= int(answer) <= len(items):
        print("表示された番号を選んでください。")
        return None
    return items[int(answer) - 1]


def _path(root, prompt, default=""):
    value = input(prompt).strip() or default
    if not value:
        return None
    path = Path(value).expanduser()
    return str(path if path.is_absolute() else root / path)


def _key():
    return "skills-home-" + uuid.uuid4().hex


def _import(root, locale):
    sample = str(Path(__file__).resolve().parents[2] / "examples/skills-small-work.txt")
    source = _path(root, "取込ファイル（空欄: 合成サンプル skills-small-work.txt）> ", sample)
    project = input("元プロジェクト名 [sample]> ").strip() or "sample"
    label = input("この作業の名前 [外部作業の記録]> ").strip() or "外部作業の記録"
    provider = input("記録元の AI サービス [未確認]> ").strip() or "未確認"
    model = input("記録元のモデル [未確認]> ").strip() or "未確認"
    return _call(root, locale, ["skills-import", "--input", source, "--origin-project", project,
                              "--label", label, "--provider", provider, "--model", model,
                              "--mode", "assisted", "--key", _key()])


def _build(root, locale, work):
    from .adapters.command_process import load_command
    creator = _path(root, "既存の実装用 Codex アダプター JSON（空欄: 戻る）> ")
    if not creator:
        return None
    reviewer = _path(root, "既存の検証用 Codex アダプター JSON（空欄: 戻る）> ")
    if not reviewer:
        return None
    print("実装: " + _safe(creator) + " / 検証: " + _safe(reviewer))
    print("選択した原文と既存の辞書・文脈を、設定済みの実装/検証の2段階へ送ります。")
    if input("外部呼出しを開始しますか [y/N]> ").strip().lower() != "y":
        print("外部呼出しを開始しませんでした。")
        return None
    for path, role in ((creator, "implementation"), (reviewer, "verification")):
        metadata = load_command(path).get("codex_cli")
        if not metadata or metadata.get("role") != role:
            raise ValueError("このメニューは対応する役割の既存 Codex 設定専用です。ローカルモデルは起動しません。")
    key = _key()
    print("生成操作キー: " + key)
    return _call(root, locale, ["skills-build", work["run_id"], "--creator-adapter", creator,
                              "--reviewer-adapter", reviewer, "--key", key,
                              "--expected-revision", str(work["revision"])])


def _target(root, locale, work):
    skill = _choose("対象の学習項目", work.get("skills", []), lambda row: row["concept"])
    if skill is None:
        return None
    labels = dict(zip(TARGETS, ("自分で理解し保有したい", "自分で確認したい", "必要時に参照したい", "判断を委ねたい（権限付与なし）")))
    target = _choose("どのように関わりたいですか", TARGETS, lambda value: value + " / " + labels[value])
    if target is None:
        return None
    reason = input("選択の理由（空欄: 戻る）> ").strip()
    if not reason:
        return None
    return _call(root, locale, ["learn-target", work["run_id"], "--candidate", skill["id"],
                              "--target", target, "--reason", reason, "--key", _key(),
                              "--expected-revision", str(work["revision"])])


def _explain(root, locale, work):
    items = [row for row in work.get("skills", []) if row.get("recorded") and row.get("status") == "OPEN"]
    skill = _choose("記録済み・保留していない学習項目", items, lambda row: row["concept"])
    if skill is None:
        return None
    print("自分の言葉を自己申告として残します。採点や習得認定は行いません。")
    statement = input("自分の説明（空欄: 戻る）> ").strip()
    if not statement:
        return None
    return _call(root, locale, ["skills-explain", work["run_id"], "--candidate", skill["id"],
                              "--statement", statement, "--key", _key(),
                              "--expected-revision", str(work["revision"])])


def _newsletter(root, locale, work):
    title = input("便りのタイトル [スキル便り]> ").strip() or "スキル便り"
    output_format = _choose("下書きの形式", ("markdown", "html"), str)
    if output_format is None:
        return None
    output = _path(root, "保存先（空欄: 画面に下書き表示、公開なし）> ")
    current = _call(root, locale, ["skills-stack", "--run", work["run_id"]])
    if not current.get("ok") or current.get("omitted_runs"):
        raise ValueError("選択範囲を確定できません。便りは作成しませんでした。")
    argv = ["skills-newsletter", "--run", work["run_id"], "--scope-id", current["scope"]["id"],
            "--title", title, "--format", output_format]
    return _call(root, locale, argv + (["--output", output] if output else []))


def _status(result):
    command = result.get("command")
    if command == "skills-build":
        mode = result.get("response_mode")
        if not result.get("ok") or mode != "GENERATED":
            print("候補生成は未完了または要確認です。response_mode=" + _safe(mode or "UNKNOWN"))
        else:
            print("生成候補を記録しました。採用・実行・習得認定は行っていません。")
        print("自動再試行は行いません。記録された状態を確認してから次の操作を選んでください。")
    elif not result.get("ok"):
        print("操作は完了していません。" + _safe(result.get("error", "記録を確認してください。")))
    elif command == "skills-newsletter":
        if result.get("output"):
            print("ローカル下書き: " + _safe(result["output"]) + " / 公開なし")
        else:
            lines = (result.get("draft") or "").splitlines()
            print("\n".join(_safe(line) for line in lines[:40]))
            if len(lines) > 40:
                print("表示は先頭40行です。全体を残す場合は保存先を指定してください。")
    elif command == "skills-import":
        print("原文をローカルに記録しました。候補生成は別操作で明示的に開始します。")
    else:
        print("選択または自己説明を記録しました。理解や実行権限の認定ではありません。")


def display(result, locale, command):
    _overview(result)
    if not result.get("interactive_requested"):
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("対話メニューは端末で skills --interactive を実行してください。")
        return
    root = Path(result["root"])
    from . import skills_home_actions
    actions = {"2": _build, "3": _target, "4": _explain, "5": _newsletter,
               "7": skills_home_actions.inspect_skill,
               "8": skills_home_actions.register_method,
               "9": skills_home_actions.reuse_method,
               "12": skills_home_actions.register_spec,
               "13": skills_home_actions.refresh_observations}
    while True:
        try:
            print("\n1. 原文をローカル取込  2. 候補を生成  3. 保有対象を選択\n4. 自分の説明を残す  5. 便りを作成  6. 一覧を更新\n7. スキルの中身を読む  8. 記録済み検証の範囲を登録\n9. 有限検証を確認して再利用  10. 成果レポート\n11. Partner で相談・実装（外部AI）  12. 検証方法をファイルから登録\n13. 観測を更新  0. 終了")
            choice = input("操作番号> ").strip()
            if choice in ("0", "q", "/quit"):
                return
            if choice not in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"):
                print("表示された番号を選んでください。")
                continue
            if choice == "1":
                outcome = _import(root, locale)
            elif choice == "11":
                outcome = skills_home_actions.partner(root, locale)
            else:
                view = _call(root, locale, ["skills-stack", "--limit", "100"])
                if choice == "6":
                    _overview(view)
                    continue
                if choice == "10":
                    skills_home_actions.report(root, locale, view)
                    continue
                work = _choose("対象の作業", view.get("works", []), lambda row: row["label"])
                outcome = actions[choice](root, locale, work) if work is not None else None
            if outcome is not None:
                _status(outcome)
                _overview(_call(root, locale, ["skills-stack", "--limit", "100"]))
        except (EOFError, KeyboardInterrupt):
            print("\nメニューを終了しました。自動再試行は行いません。")
            return
        except (LedgerError, OSError, ValueError) as error:
            print("操作を停止しました: " + _safe(error.code if isinstance(error, LedgerError) else error))
            if isinstance(error, LedgerError):
                skills_home_actions.show_error_reason(error)
            print("自動再試行は行いません。権限や既存の実行記録を確認してください。")
