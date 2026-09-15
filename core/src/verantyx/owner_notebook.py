"""A project research notebook that is written by work, not assigned as homework."""
from pathlib import Path

from .agent_console import terminal_text
from .cleanroom_io import console_print as print, current
from .domain.owner_experience import TARGETS
from .errors import LedgerError
from . import owner_experience as experience

TARGET_LABELS = {"OWN": "原理から理解して判断したい", "REVIEW": "危険や誤りを見分けたい",
                 "REFERENCE": "必要なときに参照できればよい", "DELEGATE": "定型作業として委譲したい"}
KIND_LABELS = {
    "PROJECT_DELTA": "プロジェクトの変化", "HUMAN_REQUEST": "あなたの目的",
    "HUMAN_DECISION": "人間の判断についてのAIの解釈", "AI_DECISION": "AIが選んだこと",
    "ASSUMPTION": "まだ確認していない前提", "OWN": "原理を自分に残す", "REVIEW": "判断するための理解",
    "REFERENCE": "必要なときに引く", "DELEGATE": "任せる候補", "FAILURE": "失敗から残すもの",
    "UNKNOWN": "まだ分からないこと", "RULE_CANDIDATE": "次回の方針候補", "CHECK_CANDIDATE": "確認方法の候補",
}


def _line(value=""):
    print(terminal_text(value))


def _snapshot(root, configuration):
    states = experience.read_states(root, configuration)
    return states, experience.project(states, configuration)


def show_project(root, configuration, context_files=()):
    _, notebook = _snapshot(root, configuration)
    _line("\nPROJECT / 一緒に育てているもの")
    _line(configuration["project"]["name"])
    _line("目的: " + (configuration["project"]["purpose"] or "まだ文章として固定していません。作業を始められます。"))
    _line("\nあなたが残した判断")
    if not notebook["active_decisions"]:
        _line("判断として保存した記録はまだありません。AIの解釈を人間の決定にはしません。")
    for decision in notebook["active_decisions"][:8]:
        _line("  " + decision["statement"])
        _line("  理由: " + (decision["reason"] or "未記録") + " / " +
              ("プロジェクトの方針" if decision["scope"] == "PROJECT" else "この仕事だけ"))
    _line("\n最近の仕事")
    for work in notebook["works"][:5]:
        _line("  " + work["request"][:120])
        for artifact in work["result"]["artifacts"][:4]:
            _line("    候補: " + artifact["path"])
        _line("    検証: " + work["result"]["evidence_status"] + " / 本体への採用は別操作")
    if not notebook["works"]:
        _line("まだ仕事の記録はありません。最初の依頼からノートが育ちます。")
    counts = notebook["counts"]
    _line("\nあなたの側に残った記録")
    _line("  判断 {human_decisions} / 自分の説明・適用例 {explanations} / 参照を選択 {reference} / 委譲を希望 {delegation_preferences}".format(**counts))
    _line("記録の件数であり、理解度や安全な自動化の達成率ではありません。")
    for card in [row for row in notebook["cards"] if row["kind"] in ("ASSUMPTION", "UNKNOWN")][:3]:
        _line("未確認の候補: " + card["text"])
    return notebook


def show_receipt(root, result):
    state = result.get("state")
    if not state or not state.get("work_result"):
        _line(result.get("answer", result.get("work", {}).get("answer", "")))
        return
    work = state["work_result"]
    _line("\nWORK / " + {"SUCCEEDED": "結果を保存しました", "WAITING_OWNER": "あなたの判断を待っています",
                         "PARTIAL": "進めた範囲を保存しました", "FAILED": "作業を完了できませんでした"}[work["status"]])
    _line(work["answer"])
    if work["question"]:
        _line("\nあなたに決めてほしいこと: " + work["question"])
    _line("\nYOUR CONTRIBUTION / あなたが与えたもの")
    _line(state["request"])
    owned = state.get("owner_experience", {})
    for decision in owned.get("decisions", []):
        if decision["status"] == "ACTIVE_STATEMENT":
            _line("判断: " + decision["statement"])
    _line("\nPROJECT / 今回残ったもの")
    for artifact in work["artifacts"]:
        _line("候補: " + artifact["path"])
    if not work["artifacts"]:
        _line("回答を作業ノートへ保存しました。")
    _line("本体は未変更。候補の採用と、正しさの確認は別です。")
    _line("検査: この作業経路では未実行。AIの説明を検証結果にはしません。")
    reflected = result.get("reflection") or (state.get("work_reflections") or [{"status": "PENDING"}])[-1]
    status = reflected["status"]
    if status == "FAILED":
        _line("\nノートの意味整理だけ未完了です。回答と候補は残っています。")
    elif status == "OFF":
        _line("\n意味整理はオフです。実際の作業記録は保存しています。")
    else:
        limit = state.get("learning_preferences", {}).get("max_items", 1)
        learning_mode = state.get("learning_preferences", {}).get("mode", "manual")
        values = experience.cards(state)
        if learning_mode == "digest":
            suggestions = [row for row in values if row["target"] in ("OWN", "REVIEW")
                           and row["status"] not in ("DEFERRED", "DISMISSED")
                           and row["human_understanding"] == "NOT_ASSESSED"][:limit]
            if suggestions:
                _line("\nTAKE WITH YOU / 今回、自分に残す候補")
            for card in suggestions:
                _line(card["text"])
                _line("今回とのつながり: " + card["reason"])
        reusable = [row for row in values if row["kind"] in ("FAILURE", "RULE_CANDIDATE", "CHECK_CANDIDATE")]
        if reusable:
            _line("\nNEXT TIME / 次の仕事へ残す候補")
            _line(reusable[0]["text"] + "（まだ有効規則ではありません）")
    _line("\nReviewで、読む・メモする・参照・委譲を選べます。今すべて理解する必要はありません。")


def publish_saved_work(root, result):
    if current.get() is None:
        return
    _line("\n作業結果を保存しました。ノートの整理を待たず、回答と候補を保持しています。")
    _line(result.get("answer", ""))
    if result.get("next_action"):
        _line("あなたへの問い: " + result["next_action"])


def show_card(card):
    _line("\n" + KIND_LABELS.get(card["kind"], card["kind"]) + " / " + card["text"])
    _line("この仕事: " + card["request"][:300])
    _line("なぜ残すか: " + card["reason"])
    for title, key in (("まず持ち帰る原理", "minimum_model"), ("間違いやすい例", "counterexample"),
                       ("自分の言葉で考える問い", "understanding_check")):
        if card.get(key):
            _line("\n" + title)
            _line(card[key])
    if card["target"]:
        _line("\n関わり方: " + TARGET_LABELS[card["target"]] +
              (" / AIの候補" if card["target_is_suggestion"] else " / あなたの選択"))
    if card["status"] == "DEFERRED":
        _line("今は後回しにしています。")
    if card["earlier_reflection"]:
        _line("以前の整理から、あなたの選択・メモを保持しています。")
    for note in card["human_notes"]:
        _line("\nあなたの記録 / " + ("次のAIにも引き継ぐ" if note["share_with_ai"] else "自分用・AIへ送らない"))
        _line(note["text"])
    _line("\n出典: " + ", ".join(card["source_event_ids"]))
    _line("整理したAI: " + card["model"]["provider"] + " / " + card["model"]["model"])
    _line("説明や適用例を残しても、自動で理解済みにはしません。")


def _browse_card(root, configuration, card):
    from . import development_console as ui
    show_card(card)
    options = ["target", "later", "memo", "explain", "apply", "shared-note", "decision", "dismiss", "restore"]
    action = ui._pick("この項目とどう関わりますか", options, lambda name: {
        "target": "理解する・参照する・委譲するを選ぶ",
        "later": "今は後で見る",
        "memo": "自分用のメモを残す（AIへ送らない）",
        "explain": "自分の言葉で説明してみる（AIへ送らない）",
        "apply": "自分で使った例を残す（AIへ送らない）",
        "shared-note": "次の仕事へ引き継ぐメモを残す",
        "decision": "自分の設計判断として残す",
        "dismiss": "今回は残す必要がない",
        "restore": "もう一度、通常の一覧へ戻す",
    }[name])
    if action is None:
        return
    kwargs = {"expected_revision": card["revision"]}
    run_id, reference = card["run_id"], card["reference"]
    if action == "target":
        target = ui._pick("あなたが選ぶ関わり方。理解済み・実行許可とは別です。", list(TARGETS),
                          lambda name: TARGET_LABELS[name])
        if target:
            ui._mutate(root, configuration, experience.choose, run_id, reference, "SELECT_TARGET",
                       target=target, share_with_ai=True, **kwargs)
            _line("あなたの選択を保存しました。次のAIへの文脈にも含めます。")
    elif action in ("later", "dismiss", "restore"):
        value = {"later": "DEFER", "dismiss": "DISMISS", "restore": "RESTORE"}[action]
        ui._mutate(root, configuration, experience.choose, run_id, reference, value, **kwargs)
        _line("選択を保存しました。仕事を止めず、後から変更できます。")
    elif action == "decision":
        _decision(root, configuration, run_id, card)
    else:
        prompts = {"memo": "自分に残すメモ", "explain": "今回の仕事に結び付けて、自分の言葉で説明",
                   "apply": "自分で使った場面と、どこまで確かめたか", "shared-note": "次のAIにも引き継ぐ内容"}
        value = ui._ask(prompts[action] + "（空欄で戻る）")
        if value:
            kind = {"explain": "SELF_EXPLANATION", "apply": "APPLICATION"}.get(action, "NOTE")
            ui._mutate(root, configuration, experience.add_note, run_id, text=value, reference=reference,
                       kind=kind, share_with_ai=action == "shared-note", **kwargs)
            _line("記録を残しました。理解・正しさの認定ではありません。")


def _decision(root, configuration, run_id, card=None):
    from . import development_console as ui
    statement = ui._ask("あなたが採用する判断", card["text"] if card else "")
    if not statement:
        return
    scope = ui._pick("この判断を使う範囲", ["WORK", "PROJECT"],
                     lambda value: "この仕事だけ" if value == "WORK" else "次の仕事にも使うプロジェクト方針")
    if not scope:
        return
    reason = ui._ask("判断の理由（任意）")
    ui._mutate(root, configuration, experience.decide, run_id, statement=statement, reason=reason,
               reference=card["reference"] if card else None, scope=scope, share_with_ai=True)
    _line("あなたの判断として保存しました。ファイル採用や規則有効化は行っていません。")


def _new_memo(root, configuration, run_id=None):
    from . import development_console as ui
    value = ui._ask("自分に残すメモ（AIへ送らない。空欄で戻る）")
    if not value:
        return
    if run_id is None:
        run_id = ui._mutate(root, configuration, experience.project_note_run)
    ui._mutate(root, configuration, experience.add_note, run_id, text=value, share_with_ai=False)
    _line("自分用のノートに残しました。")


def open_notebook(root, configuration, run_id=None, section="review"):
    from . import development_console as ui
    from .agent_console import organize_menu
    query, filter_name = "", "all"
    while True:
        states, notebook = _snapshot(root, configuration)
        if run_id:
            states = [state for state in states if state["run_id"] == run_id]
            notebook = experience.project(states, configuration)
        cards = notebook["cards"]
        if query:
            cards = [row for row in cards if query.casefold() in
                     (" ".join([row["text"], row["reason"], row["request"]])).casefold()]
        if filter_name != "all":
            cards = [row for row in cards if
                     (filter_name == "later" and row["status"] == "DEFERRED") or
                     (filter_name == "learn" and row["target"] in ("OWN", "REVIEW")) or
                     (filter_name == "reference" and row["target"] == "REFERENCE") or
                     (filter_name == "delegate" and row["target"] == "DELEGATE")]
        if section == "learn":
            cards = [row for row in cards if row["target"] in TARGETS]
        rows = []
        for question in notebook["questions"]:
            rows.append(("question", question, "今決める: " + question["question"][:100]))
        for card in cards[:100]:
            target = TARGET_LABELS.get(card["target"], KIND_LABELS.get(card["kind"], card["kind"]))
            prefix = "後で / " if card["status"] == "DEFERRED" else ""
            rows.append(("card", card, prefix + card["text"][:80] + " / " + target))
        for memo in [row for row in notebook["notes"] if row["item"] is None][-10:]:
            rows.append(("memo", memo, "自分のメモ: " + memo["text"][:90]))
        rows += [("project", None, "プロジェクトの目的・判断・変化を見る"),
                 ("notes", None, "自分のメモを残す"),
                 ("decisions", None, "自分の判断を見直す"),
                 ("search", None, "このノートから探す"),
                 ("filter", None, "理解・参照・委譲・後で見るを切り替える"),
                 ("history", None, "仕事を選ぶ・続きを進める"),
                 ("organize", None, "別の整理AIで、この仕事を整理し直す")]
        _line("\nOWNER / 人間に残るプロジェクトノート")
        _line("一度に全部読む必要はありません。Escで仕事へ戻れます。")
        selected = ui._pick("必要なものだけ選ぶ", rows, lambda row: row[2])
        if selected is None:
            return
        action, item, _ = selected
        try:
            if action == "card":
                _browse_card(root, configuration, item)
            elif action == "question":
                _line(item["request"])
                reply = ui._ask(item["question"] + "（空欄で後にする）")
                if reply:
                    return ui._new_work(root, configuration, "assisted", previous={"run_id": item["run_id"]}, request=reply)
            elif action == "project":
                show_project(root, configuration)
            elif action == "notes":
                _new_memo(root, configuration, run_id)
            elif action == "memo":
                _line(item["text"])
                _line("自分用・外部AIへは送らない" if not item["share_with_ai"] else "次のAIへの文脈に含める記録")
            elif action == "search":
                query = ui._ask("ノート内の文字を検索（空欄で全件）")
            elif action == "filter":
                chosen = ui._pick("表示するもの", ["all", "learn", "reference", "delegate", "later"],
                                  lambda value: {"all": "すべて", "learn": "理解を残す", "reference": "参照",
                                                 "delegate": "委譲", "later": "後で見る"}[value])
                if chosen:
                    filter_name = chosen
            elif action == "organize":
                organize_menu(root, configuration, run_id)
            elif action == "decisions":
                choices = [(None, "新しく自分の判断を残す")] + [
                    (row, row["statement"]) for row in notebook["active_decisions"]]
                chosen = ui._pick("あなたの設計判断", choices, lambda row: row[1])
                if chosen:
                    decision, _ = chosen
                    if decision is None:
                        target = run_id or ui._mutate(root, configuration, experience.project_note_run)
                        _decision(root, configuration, target)
                    else:
                        _line(decision["statement"])
                        _line("理由: " + (decision["reason"] or "未記録"))
                        confirm = ui._pick("この判断", ["keep", "withdraw"],
                                           lambda value: "そのまま保持" if value == "keep" else "以後の文脈から撤回する")
                        if confirm == "withdraw":
                            ui._mutate(root, configuration, experience.withdraw, decision["run_id"],
                                       decision["source_ref"])
            elif action == "history":
                chosen = ui._pick("仕事のノート", notebook["works"], lambda row: row["request"][:100])
                if chosen:
                    operation = ui._pick("この仕事", ["open", "continue"],
                                         lambda name: "ノートを開く" if name == "open" else "追加の依頼をする")
                    if operation == "open":
                        run_id = chosen["run_id"]
                    elif operation == "continue":
                        return ui._new_work(root, configuration, "assisted", previous={"run_id": chosen["run_id"]})
        except (LedgerError, OSError) as error:
            _line("選択を保存できませんでした。既存の記録は残っています。")
            _line("詳細: " + getattr(error, "code", "LOCAL_IO_ERROR"))
