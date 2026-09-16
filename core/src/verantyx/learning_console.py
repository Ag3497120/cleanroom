"""Optional unpacking, with no ability inference or forced learning."""
import json

from . import learning_guides as guides
from . import learning_capture as capture
from .skill_console import line
from .errors import LedgerError


def show(identity, detail="summary"):
    value = guides.read(identity, detail=detail)
    line("\nUNPACK / " + value["title"])
    line("保存した解説です。AIの呼び出し、習得認定、権限変更はありません。")
    line("Source page: " + str(value["coverage"]["page"] + 1) + "/" + str(value["coverage"]["pages"]))
    if value["status"] != "PROPOSED":
        line("解説の生成は未完了。元の記録は保持しています: " + value["failure_code"])
    if detail == "summary":
        line(value.get("summary", ""))
        line(value.get("next_opportunity", ""))
        for gap in value.get("gaps", []):
            line("まだ記録から分からないこと: " + gap)
    else:
        line(json.dumps(value, ensure_ascii=False, indent=2))
    return value


def open_guide(identity):
    from . import development_console as ui
    while True:
        detail = ui._pick("Read at your pace", ["summary", "full", "sources"], lambda value: {
            "summary": "Summary / 今は要点だけ",
            "full": "Full explanation / 省略した手順・前提・小さな練習",
            "sources": "Original records / 保存した作業記録をそのまま",
        }[value])
        if detail is None:
            return
        show(identity, detail)


def unpack(root, configuration, *, skill_id=None, technology="", run_id=None, moment_id=None):
    from . import development_console as ui
    if configuration is None:
        line("解説を生成する場合は、プロジェクトと整理AIの設定が必要です。保存済みの解説はそのまま読めます。")
        return
    page = 0
    packet = guides.prepare(root, configuration, skill_id=skill_id, technology=technology, run_id=run_id, moment_id=moment_id, page=page)
    line("\nUNPACK / 自分が知りたい分だけ")
    line("対象: " + (packet["skill"]["definition"]["title"] if packet["skill"] else technology or run_id or "Recorded work"))
    line("作業中の説明・実際のツール結果: " + str(packet["coverage"]["events"]) + "記録")
    line("資料範囲: " + str(packet["coverage"]["pages"]) + "ページ。今回は最初のページを使います。")
    line("現在共有したプロフィールを使い、保存済みの過去プロフィール原文は自動で再送しません。作業記録自体の内容は送信前に確認できます。")
    line("未記録の判断理由は、元の理由として復元できません。追加説明と区別します。")
    if ui._start("View the exact project records and shared personal context before sending?"):
        line(json.dumps(packet, ensure_ascii=False, indent=2))
    queries = []
    if ui._start("Also search for optional books or official guides?"):
        line("検索語だけを外部へ送ります。プロジェクト本文やプロフィールは検索語に自動変換しません。")
        line("Brave Search API uses BRAVE_SEARCH_API_KEY. A search may incur provider charges.")
        query = ui._ask("Search words you approve / 空欄なら検索しない")
        if query:
            queries.append(query)
    if not ui._start("Send this selected source page to the Reflection AI and create a new guide?"):
        return
    result = ui._mutate(root, configuration, guides.create, send=True, prepared=packet,
                        skill_id=skill_id, queries=queries, approve_web=bool(queries))
    line("作業結果と本人の習得状態は変更していません。")
    open_guide(result["guide"]["id"])
    return result


def menu(root=None, configuration=None):
    from . import development_console as ui
    from . import skill_assets
    while True:
        view = guides.catalogue()
        options = [("moments", None, "During work / 実装中の説明から開く"),
                   ("skill", None, "Unpack a skill / 手順を紐解く"),
                   ("technology", None, "Explore a technology / 実装で使った技術を紐解く"),
                   ("work", None, "Choose a recorded task / 作業IDから開く")]
        options += [("saved", item["id"], item["title"]) for item in view["items"]]
        selected = ui._pick("MY LEARNING / 全部を学ぶ必要はありません", options, lambda row: row[2])
        if selected is None:
            return
        try:
            action, identity, _ = selected
            if action == "moments":
                from .learning_moments import menu as moments_menu
                moments_menu(root, configuration)
            elif action == "saved":
                open_guide(identity)
            elif action == "skill":
                entries = skill_assets.catalogue(root, configuration)["items"]
                asset = ui._pick("Which procedure?", entries, lambda row: row["asset"]["definition"]["title"])
                if asset:
                    unpack(root, configuration, skill_id=asset["asset"]["id"])
            elif action == "technology":
                entries = capture.topics()
                chosen = ui._pick("Technologies recorded during work", entries, lambda row: row["technology"])
                if chosen:
                    unpack(root, configuration, technology=chosen["technology"])
                elif not entries:
                    line("作業中の技術メモはまだありません。過去作業は作業IDを指定して開けます。")
            elif action == "work":
                run_id = ui._ask("Recorded work ID / 空欄で戻る")
                if run_id:
                    technology = ui._ask("Optional technology to focus on / 空欄なら作業全体")
                    unpack(root, configuration, run_id=run_id, technology=technology)
        except (LedgerError, OSError, ValueError) as error:
            line("この解説だけ未完了です。作業結果は保持しています: " + getattr(error, "code", type(error).__name__))
