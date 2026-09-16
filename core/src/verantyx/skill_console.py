"""A small optional skill board, not an exam, completion target, or approval bypass."""
import json
import shutil
import unicodedata

from . import personal_profile as profile
from . import skill_assets as skills
from .agent_console import terminal_text
from .cleanroom_io import console_print
from .errors import LedgerError

PLAN_LABELS = {
    "UNSELECTED": "Unselected / まだ選ばない", "WANT": "On my board / 今後身につけたい",
    "NEXT_TIME": "Next opportunity / 次の仕事で少しずつ",
    "REFERENCE": "Reference / 参照できれば十分", "DELEGATE": "Delegate / 自分では覚えなくてよい",
    "NOT_NEEDED": "Not for me / 今は自分に不要",
}
HUMAN_LABELS = {
    "NO_RECORD": "No record / 記録なし。未経験という意味ではありません",
    "SELF_REPORTED": "Self-report / 扱えると思う",
    "EXPLAINED": "My explanation / 自分の言葉で説明を残す",
    "APPLIED": "My application / 自分で使った場面を残す",
    "TRANSFERRED": "Another situation / 別の問題へ使った例を残す",
}
AI_LABELS = {
    "DRAFT": "Draft / AIが残した仮の手順", "REFERENCE": "Use as reference / 次のAIの参考にできる",
    "REVIEW_REQUIRED": "Needs review / 条件が変わったので見直す",
    "RETIRED": "Retired / 今後の参考にしない",
}


def line(value):
    console_print(terminal_text(str(value)))


def _fit(value, width):
    result, size = "", 0
    for char in terminal_text(str(value)).replace("\n", " "):
        cells = 0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
        if size + cells > width:
            break
        result += char
        size += cells
    return result + " " * (width - size)


def render_board(rows, columns=None):
    width = columns or shutil.get_terminal_size((90, 30)).columns
    count = 3 if width >= 90 else 2 if width >= 60 else 1
    cell_width = max(12, min(32, (width - count - 1) // count))
    lines = ["MY SKILLS / 必要な穴だけ、自分のペースで"]
    if not rows:
        return lines + ["まだ盤面に項目を選んでいません。AIの手順はCatalogueに残っています。"]
    border = "+" + "+".join("-" * cell_width for _ in range(count)) + "+"
    for start in range(0, len(rows), count):
        group = rows[start:start + count]
        lines.append(border)
        for field in ("title", "human", "plan"):
            cells = []
            for row in group:
                value = (row["title"] if field == "title" else
                         skills.MARKS[row["human"]] + " " + row["human"] if field == "human" else
                         row["plan"] + " / AI:" + row["ai_use"])
                cells.append(_fit(value, cell_width))
            cells += [" " * cell_width] * (count - len(group))
            lines.append("|" + "|".join(cells) + "|")
    return lines + [border, "[S]自己申告 [E]自分の説明 [A]適用例 [T]転用例。認定や能力点数ではありません。",
                    "全てを埋める必要はありません。委譲・参照・次回は同じく正当な選択です。"]


def inspect(asset, root=None, configuration=None):
    from . import development_console as ui
    while True:
        with profile.connection() as db:
            progress = skills._progress(db, asset)
        definition = asset["definition"]
        line("\n" + definition["title"])
        line("AI: " + AI_LABELS[progress["ai_use"]])
        line("Human: " + HUMAN_LABELS[progress["human"]])
        line("Plan: " + PLAN_LABELS[progress["plan"]])
        line("Purpose: " + definition["purpose"])
        for name, label in (("inputs", "Inputs"), ("outputs", "Outputs"), ("steps", "Procedure"),
                            ("applicable_when", "When to use"), ("stop_when", "Stop / boundaries"),
                            ("verification_methods", "Verification method drafts"),
                            ("human_decisions", "Decisions that stay with the owner")):
            line(label + ":")
            for value in definition[name]:
                line("  - " + value)
        line("Provenance: " + asset["project_name"] + " / " + asset["run_id"])
        line("Model: " + asset["model"]["provider"] + " / " + asset["model"]["model"])
        line("Version: " + asset["definition_sha256"][:16])
        if definition["extends_skill_id"]:
            line("Proposed continuation of: " + definition["extends_skill_id"] + " / 習得状態は自動転写しません")
        line("Source events: " + ", ".join(definition["source_event_ids"]))
        line("検査方法は案です。検査実行や手順の安全性を保証していません。")
        action = ui._pick("Only if useful now", ["later", "unpack", "plan", "human", "ai", "share", "history", "export"],
                         lambda v: {
                             "later": "Keep working / 何も変えず仕事へ戻る",
                             "unpack": "Unpack / 省略した手順・前提・学び方を紐解く",
                             "plan": "Choose my part / 身につける・次回・参照・委譲・不要",
                             "human": "My experience / 自分の言葉や実例を残す",
                             "ai": "AI procedure / 手順の利用方針",
                             "share": "Sharing / この手順と自分の記録の共有",
                             "history": "History / 以前の選択と説明",
                             "export": "Portfolio / この自己申告を実績として書き出す",
                         }[v])
        if action is None or action == "later":
            return
        if action == "unpack":
            from .learning_console import unpack
            unpack(root, configuration, skill_id=asset["id"])
        elif action == "plan":
            value = ui._pick("My part", list(skills.PLANS), PLAN_LABELS.get)
            if value:
                skills.choose(asset, plan=value)
        elif action == "human":
            value = ui._pick("What I want to record", list(skills.HUMAN), HUMAN_LABELS.get)
            if value:
                note = ui._ask("My words / 自分の説明・使った場面（強制評価はしません）")
                if value in ("EXPLAINED", "APPLIED", "TRANSFERRED") and not note:
                    line("説明や実例は後で構いません。今回の習得記録は変更しませんでした。")
                else:
                    skills.choose(asset, human=value, note=note)
        elif action == "ai":
            value = ui._pick("Reference policy, not execution permission", list(skills.AI_USE), AI_LABELS.get)
            if value:
                skills.choose(asset, ai_use=value)
        elif action == "share":
            line("この手順、本人の選択、説明・実例を、他のプロジェクトのAI文脈へ含められます。")
            line("プロジェクト内の作業来歴は既存の文脈に残ります。個人共有の取り消しで過去送信は消えません。")
            value = ui._pick("Personal cross-project sharing", [False, True],
                             lambda v: "Share selected record / この記録を共有候補にする" if v else "Private / 個人文脈では送らない")
            if value is not None:
                skills.choose(asset, share=value)
                if value and not (profile.preferences()["enabled"] and profile.preferences()["share_with_ai"]):
                    line("個人ノートの全体共有がオフなので、今は送信しません。My paceで変更できます。")
        elif action == "history":
            page = 0
            while True:
                rows = skills.history(asset["id"], page=page)
                for row in rows:
                    line(json.dumps(row, ensure_ascii=False, indent=2))
                if len(rows) < 30 or not ui._start("Older entries / 以前の記録を開きますか？"):
                    break
                page += 1
        elif action == "export":
            from .personal_console import write_export
            value = skills.portfolio([asset["id"]])
            line("本人の説明・実例が含まれます。公開はせず、新規ファイルに書き出します。")
            path = ui._ask("New JSON file path / 空欄で戻る")
            if path and ui._start("Export this selected self-report?"):
                line(write_export(path, value))


def quiet():
    from . import development_console as ui
    line("手順候補は残し、学習の質問・自動表示だけを後回しにします。")
    line("ファイル送信・実行・削除・公開・本体採用の承認は変更しません。")
    scope = ui._pick("Keep working", ["SESSION", "TODAY", "GLOBAL"],
                     lambda v: {"SESSION": "This session", "TODAY": "Today", "GLOBAL": "Until I change it"}[v])
    if scope:
        return profile.configure({"onboarded": True, "mode": "on_demand", "timing": "on_demand",
                                  "stack_questions": False}, scope=scope)


def menu(root=None, configuration=None):
    from . import development_console as ui
    page, search = 0, ""
    while True:
        view = skills.board(page=page)
        for value in render_board(view["items"]):
            line(value)
        line("AIの手順と自分の経験は別です。スキップ・依頼・承認省略から習熟を判定しません。")
        choices = [("catalogue", None, "Catalogue / AIの手順を選ぶ"),
                   ("search", None, "Find a skill / 技術や手順の名前で探す"),
                   ("quiet", None, "Keep working / 学習確認は後で"),
                   ("back", None, "Return to work / このまま作業を続ける")]
        if configuration:
            choices.append(("sync", None, "Keep across projects / このプロジェクトの手順を個人ノートへ収録"))
        if page:
            choices.append(("previous", None, "Previous page"))
        if view["has_next"]:
            choices.append(("next", None, "Next page"))
        for row in view["items"]:
            choices.append(("open", row["asset_id"], skills.MARKS[row["human"]] + " " + row["title"]))
        selected = ui._pick("My skill board", choices, lambda row: row[2])
        if not selected or selected[0] == "back":
            return
        action, identity, _ = selected
        try:
            if action == "open":
                inspect(skills.resolve(identity, root, configuration), root, configuration)
            elif action == "quiet":
                quiet()
            elif action == "sync":
                line("AIが書いた手順と出典参照を個人ノートへ保存します。コード本文や権限は移しません。")
                if ui._start("Store these private procedure drafts across projects?"):
                    line(json.dumps(skills.sync_project(root, configuration), ensure_ascii=False))
            elif action in ("next", "previous"):
                page += 1 if action == "next" else -1
            elif action in ("catalogue", "search"):
                if action == "search":
                    search = ui._ask("Find / 技術・手順・プロジェクト")
                browse(root, configuration, search=search)
        except (LedgerError, OSError, ValueError) as error:
            line("この操作だけ未完了です。作業の成果は残っています: "
                 + getattr(error, "code", type(error).__name__))


def browse(root=None, configuration=None, *, search=""):
    from . import development_console as ui
    page = 0
    while True:
        view = skills.catalogue(root, configuration, page=page, search=search)
        line("\nAI PROCEDURES / " + str(view["total"]) + "件。本人の必修項目数ではありません。")
        choices = [("open", row["asset"], row["asset"]["definition"]["title"] + " / "
                    + row["asset"]["project_name"] + " / " + row["progress"]["ai_use"])
                   for row in view["items"]]
        if page:
            choices.append(("previous", None, "Previous page"))
        if view["has_next"]:
            choices.append(("next", None, "Next page"))
        if not choices:
            line("まだ候補がありません。整理AIがオフ・失敗・候補なしの場合は、意味をルールで補いません。")
            return
        selected = ui._pick("Choose only what helps", choices, lambda row: row[2])
        if not selected:
            return
        if selected[0] == "open":
            inspect(selected[1], root, configuration)
        else:
            page += 1 if selected[0] == "next" else -1
