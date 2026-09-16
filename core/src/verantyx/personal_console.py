"""Optional personal notebook. Menus are discoverable; no proficiency examination."""
from pathlib import Path
import json
import os

from . import personal_profile as profile
from .agent_console import terminal_text
from .cleanroom_io import console_print as print
from .errors import LedgerError
from .console_copy import ui_text

LABELS = {
    "experience": "Experience / 使った経験", "understanding": "Understanding / 自分の説明",
    "confidence": "Confidence / 今の手応え", "support": "Support / 希望する助け方",
    "goal": "Goal / 自分に残したいもの", "delegation": "Delegation / 任せたいこと",
    "memo": "Memo / 自分用のメモ",
}
SCOPES = {"GLOBAL": "Across projects / 今後のプロジェクトでも",
          "SESSION": "This session / この起動中だけ", "TODAY": "Today / 今日だけ"}
CHOICES = {
    "NEXT_TIME": "Next time / 関連する仕事の時に続ける",
    "REFERENCE": "Reference / 検索できれば十分",
    "DELEGATE": "Delegate / この話題はAIに任せたい",
    "SELF_REPORTED_UNDERSTOOD": "Explain / 自分の言葉を残す",
    "SELF_REPORTED_APPLIED": "Applied / 試して気づいたことを残す",
    "SELF_REPORTED_TRANSFERRED": "Connected / 別の場面で使ったことを残す",
    "DISMISS": "Not for me / この提案は不要", "REOPEN": "Reopen / 自分から再開する",
}


def line(value=""):
    print(terminal_text(value))


def first_open(root=None, configuration=None):
    """One optional, person-wide welcome. No model is called here."""
    try:
        if profile.preferences()["onboarded"]:
            return
        from . import development_console as ui
        line("\nMY NOTEBOOK / " + ui_text("Your experience can grow alongside your projects."))
        line(ui_text("This is not an exam. Delegating or leaving this blank never removes features."))
        line(ui_text("Describe your experience in your own words; you can change it at any time."))
        line(ui_text("Stored in your personal area on this computer, shared across your projects."))
        choices = ["light", "private", "guided", "skip"]
        mode = ui._pick("How would you like to start?", choices, lambda value: {
            "light": "Light / one suggestion per day; only your chosen excerpts are shared",
            "private": "Private / local journal; open learning suggestions yourself",
            "guided": "Together / small examples, at most once per day",
            "skip": "Skip / start working; open My profile later",
        }[value])
        if mode in (None, "skip"):
            profile.configure({"onboarded": True})
            return
        shared = mode != "private"
        if shared:
            line(ui_text("Shared experience and short learning records are sent only to your selected Work and Reflection AI."))
            line(ui_text("Organization may add model calls after work. Sensitive notes can stay private."))
            if ui._pick("Enable this personal context?", [False, True],
                        lambda v: "Enable / share only this scope" if v else "Private / start without sharing") is not True:
                shared = False
        profile.configure({"onboarded": True, "enabled": True, "share_with_ai": shared,
                           "mode": ("guided" if mode == "guided" else "light") if shared else "on_demand",
                           "weight": "snippet" if mode == "guided" else "brief",
                           "daily_limit": 1, "per_work": 1})
        line(ui_text("You do not need to fill everything in. Experience gained with AI is welcome too."))
        record_technology()
    except Exception as error:
        line(ui_text("Your notebook can be set up later. Work can continue: {reason}", reason=getattr(error, "code", type(error).__name__)))


def record_technology(technology=None, reason=""):
    from . import development_console as ui
    if technology is None:
        technology = ui._ask("One technology you have used (Enter to skip)")
    if not technology:
        return
    line("\n" + technology + " / " + ui_text("No experience statement is recorded yet. This does not mean you lack experience."))
    if reason:
        line(ui_text("Connection to this work: {reason}", reason=reason))
    line(ui_text("For example: built a small app with AI; can read it but want design help; use it regularly."))
    line(ui_text("No precise level is required. Leaving this blank does not stop work."))
    text = ui._ask("Your experience, in your own words")
    if not text:
        return
    shared = profile.preferences()["share_with_ai"]
    line(ui_text("This statement will be shared as context with your selected AI." if shared else "This statement stays private and is not sent to AI."))
    return profile.statement(text, technology=technology, share=shared)


def after_work(root, configuration, result):
    """Display only the exposures reserved at capture time, never reclassify on paint."""
    personal = result.get("personal_growth", {})
    if personal.get("journal_id"):
        line("\nMY JOURNAL / 作業の事実を本人用の日記にも残しました。")
    if personal.get("status") == "UNORGANIZED":
        line("経験の意味整理は未完了です。作業結果は失われていません。後で別のAIでも整理できます。")
    for identity in personal.get("visible_lessons", []):
        row = profile.get_record(identity)
        if not row:
            continue
        line("\nA SMALL NEXT STEP / 今回ひとつだけ持ち帰るなら")
        line(row["title"])
        line(row["why_now"])
        line(row["minimum_step"])
        line("今は読まなくても構いません。F2 > Next time で参照・委譲・次回を選べます。")
    return personal


def edit_statement(row=None):
    from . import development_console as ui
    category = ui._pick("What would you like to record?", list(LABELS), LABELS.get)
    if category is None:
        return
    technology = ui._ask("Technology / 技術・話題（全般なら空欄）", (row or {}).get("technology", ""))
    text = ui._ask("Your words / あなたの言葉", (row or {}).get("text", ""))
    if not text:
        return
    scope = ui._pick("How long should this apply?", list(SCOPES), SCOPES.get)
    if not scope:
        return
    share = ui._pick("Who may use this?", [False, True],
                     lambda v: "Shared with selected AI / AIの文脈へ" if v else "Private / 自分だけ")
    if share is None:
        return
    result = profile.statement(text, technology=technology, kind=category, scope=scope, share=share,
                               record_id=row["id"] if row else None)
    line("保存しました。自己申告であり、能力認定やツール権限ではありません。")
    if share and not profile.preferences()["share_with_ai"]:
        line("全体の共有設定がオフのため、今は送信しません。My paceで変更できます。")
    return result


def pace(root=None, configuration=None):
    from . import development_console as ui
    pref = profile.preferences()
    line("\nMY PACE / 説明の量は本人が選ぶ")
    line("後回しにした項目に期限や督促は付けません。今日だけ静かにすることもできます。")
    mode = ui._pick("Suggestions", ["on_demand", "light", "guided"], lambda v: {
        "on_demand": "On demand / 自分から開くまで静かに",
        "light": "Light / 短い原理を少しだけ", "guided": "Together / 実装しながら小さく学ぶ",
    }[v])
    if not mode:
        return
    weight = ui._pick("Weight", ["brief", "snippet", "practice"], lambda v: {
        "brief": "Brief / 一言の原理", "snippet": "Example / 短い実例",
        "practice": "Optional practice / 希望した時だけ小さな練習",
    }[v])
    if not weight:
        return
    timing = ui._pick("Timing", ["after_work", "at_breaks", "on_demand"], lambda v: {
        "after_work": "After work / 作業の後", "at_breaks": "At a work boundary / 作業単位の区切り",
        "on_demand": "On demand / 開いた時だけ",
    }[v])
    if not timing:
        return
    daily = ui._pick("Daily maximum / 全プロジェクトを合計", [0, 1, 2, 3, 5], str)
    if daily is None:
        return
    maximum = ui._pick("Maximum per work", [0, 1, 2, 3], str)
    if maximum is None:
        return
    scope = ui._pick("Apply for", list(SCOPES), SCOPES.get)
    if not scope:
        return
    shared = ui._pick("Personal excerpts for AI", [False, True],
                      lambda v: "Share selected experience and learning / 選んだ抜粋を引き継ぐ"
                      if v else "Private / 外部AIへ渡さない")
    if shared is None:
        return
    questions = ui._pick("New primary technology", [False, True],
                         lambda v: "Optional short question / 短く一度だけ聞く"
                         if v else "Do not ask / 自分から登録する")
    if questions is None:
        return
    profile.configure({"onboarded": True, "enabled": True, "mode": mode, "weight": weight,
                       "timing": timing, "daily_limit": daily, "per_work": maximum,
                       "share_with_ai": shared, "stack_questions": questions}, scope=scope)
    line("設定しました。学習を選ばなくても、仕事やモデルの権限は変わりません。")


def review_proposal(row):
    from . import development_console as ui
    from .personal_growth import accept_update, reject_update
    value = row["proposal"]
    line("\nPROFILE DRAFT / まだ本人のプロフィールには反映していません")
    line(value["category"] + " / " + value["technology"])
    line(value["text"])
    line("あなたの発言: " + value["human_quote"])
    if value["preference_changes"]:
        line(json.dumps(value["preference_changes"], ensure_ascii=False))
    action = ui._pick("Choose what to keep", ["accept", "edit", "dismiss", "later"], lambda v: {
        "accept": "Keep / この内容を自分の記録にする", "edit": "Rewrite / 自分の言葉に直す",
        "dismiss": "Dismiss / 保存しない", "later": "Later / 今はそのまま",
    }[v])
    if action in (None, "later"):
        return
    if action == "dismiss":
        reject_update(row["id"])
        return
    if action == "edit":
        if edit_statement():
            reject_update(row["id"])
        return
    scope = ui._pick("Apply for", list(SCOPES), SCOPES.get)
    if not scope:
        return
    share = ui._pick("Share with AI?", [False, True],
                     lambda v: "Shared / 選択したAIへ" if v else "Private / 自分用")
    if share is not None:
        accept_update(row["id"], scope=scope, share=share)
        line("本人の選択として保存しました。理解度の自動判定はしていません。")


def talk(root, configuration):
    if configuration is None:
        line("相談に使うAIが未設定です。プロジェクトでverantyx setup modelsを開いてから相談できます。")
        return {"ok": False, "status": "NOT_CONFIGURED"}
    from . import development_console as ui
    from .personal_growth import converse
    line("\nTALK / うまくいかなかったことも、希望する助け方も")
    line("「以前Gitで失敗したので、今回は差分を一緒に見たい」など、必要な時だけ。")
    line("相談を能力の不足に置き換えません。プロフィールの更新は最後に選べます。")
    line("整理案は本人用の下書きになります。最後に削除でき、採用するまで次のAIの個人文脈には入れません。")
    text = ui._ask("What would help? / 相談や更新したいこと（空欄で戻る）")
    if not text:
        return
    if not ui._start("この文章と共有済みの抜粋を、設定した整理AIへ送りますか？"):
        return
    result = ui._mutate(root, configuration, converse, text)
    line(result["reply"])
    line("これはAIの提案です。プロフィールはまだ変更していません。")
    for identity in result["updates"]:
        row = profile.get_record(identity)
        if row:
            review_proposal(row)
    keep = ui._pick("This conversation draft", [False, True],
                    lambda v: "Keep privately / 自分用の下書きとして残す" if v else
                    "Forget draft / 今回の相談の下書きは残さない")
    if keep is not True:
        profile.forget(result["report_id"])
        line("本人用の相談下書きを削除しました。採用した自己申告と外部AI側の履歴は別です。")
    return result


def lesson_menu(identity):
    from . import development_console as ui
    row = profile.get_record(identity)
    profile.require(row and row["kind"] == "lesson", "PERSONAL_LESSON_REQUIRED")
    line("\n" + row["title"] + " / " + row["goal"] + " / AIの候補")
    for label, key in (("今回とのつながり", "why_now"), ("最小の一歩", "minimum_step"),
                       ("前の経験とのつながり", "connection_to_prior"), ("次の機会", "return_context"),
                       ("試したい時だけ", "optional_practice")):
        if row.get(key):
            line(label + ": " + row[key])
    if row.get("previous_id"):
        line("前の記録: " + row["previous_id"])
    line("出典: " + ", ".join(row.get("source_event_ids", [])))
    line("整理AI: " + row.get("model", {}).get("model", "unavailable"))
    for entry in row.get("feedback", [])[-3:]:
        line("自分の記録: " + entry["choice"] + " / " + entry["text"])
    choice = ui._pick("Your next step", list(CHOICES), CHOICES.get)
    if not choice:
        return
    text = ""
    if choice.startswith("SELF_REPORTED"):
        text = ui._ask("What changed? / 説明、試した例、気づいたこと（空欄で中止）")
        if not text:
            return
    profile.choose_lesson(identity, choice, text=text)
    line("本人の選択として保存しました。合否、期限、理解済み認定にはしません。")


def lessons():
    from . import development_console as ui
    while True:
        rows = profile.records("lesson", 300)
        line("\nNEXT TIME / 次の機会に続ける。未提出の宿題ではありません。")
        chosen = ui._pick("Learning, reference and delegation", rows,
                          lambda r: r.get("technology", "") + " / " + r.get("title", "")
                          + " [" + r.get("choice", "OPEN") + "]")
        if chosen is None:
            return
        lesson_menu(chosen["id"])


def _latest_report(journal_id):
    return next((row for row in profile.records("report", 300) if row.get("journal_id") == journal_id), None)


def show_journal(row):
    line("\nMY JOURNAL / " + row["created_at"][:10] + " / " + row["project"]["name"])
    line("目的・依頼: " + row["request"])
    line("作業状態: " + row["facts"]["work_status"])
    line("候補ファイル: " + str(len(row["facts"]["artifacts"])))
    line("作業ツール: " + json.dumps(row["facts"]["tool_counts"], ensure_ascii=False))
    line("保存した検査イベント: " + str(len(row["facts"]["checks"])))
    line("自己申告、AIによる実装、実行記録を区別します。日記の存在は習熟の証明ではありません。")
    report = _latest_report(row["id"])
    if report:
        line("\nAIの見方 / " + report["model"]["model"] + " / " + report["id"])
        for item in report["proposal"]["interpretations"]:
            line(item["kind"] + ": " + item["text"])
            line("  出典: " + ", ".join(item["source_event_ids"]))
        for item in report["proposal"]["technologies"]:
            line("技術についての観測候補: " + item["name"] + " / " + item["reason"])
    else:
        line("意味は未整理です。キーワードから学習項目を作って穴埋めしません。")
    for note in profile.records("note", 500):
        if note.get("journal_id") == row["id"]:
            line("\nあなたの日記: " + note["text"])


def organize_journal(root, configuration, row):
    from . import development_console as ui
    from .agent_runtime import _state
    from .agent_models import selected_work, selected_reflection
    from .personal_growth import capture_safe
    profile.require(configuration is not None and row["project"]["id"] == configuration["project"]["id"],
                    "OPEN_ORIGINAL_PROJECT_TO_REORGANIZE")
    if not profile.preferences()["share_with_ai"]:
        line("My paceで共有を有効にしてから選べます。非共有の記録は送信しません。")
        return
    if not ui._start("この仕事と共有済みの経験を整理AIへ送り、新しい見方を加えますか？"):
        return
    adapter = selected_reflection(root, configuration, selected_work(root, configuration))
    state = _state(root, configuration, row["run_id"])
    result = ui._mutate(root, configuration, capture_safe, state, adapter=adapter, explicit=True)
    line("整理: " + result["status"] + " / 以前の見方は上書きしません。")
    return result


def journal(root=None, configuration=None):
    from . import development_console as ui
    while True:
        rows = profile.records("journal", 300)
        row = ui._pick("My journal / プロジェクトを越えた日記", rows,
                       lambda r: r["created_at"][:10] + " / " + r["project"]["name"] + " / " + r["request"][:70])
        if row is None:
            return
        show_journal(row)
        action = ui._pick("This page", ["note", "lessons", "organize", "history", "forget"], lambda v: {
            "note": "Add my words / 自分の一言", "lessons": "Next steps / この仕事で残った理解",
            "organize": "Another interpretation / 整理AIで新しい見方を加える",
            "history": "Earlier interpretations / 以前の見方も読む", "forget": "Forget / この個人ページを削除",
        }[v])
        if action == "note":
            text = ui._ask("Your note / 自分用の一言")
            if text:
                profile.add_note(text, journal_id=row["id"])
        elif action == "lessons":
            candidates = [r for r in profile.records("lesson", 500) if r.get("journal_id") == row["id"]]
            chosen = ui._pick("This work's learning candidates", candidates, lambda r: r["title"])
            if chosen:
                lesson_menu(chosen["id"])
        elif action == "organize":
            organize_journal(root, configuration, row)
        elif action == "history":
            reports = [r for r in profile.records("report", 300) if r.get("journal_id") == row["id"]]
            chosen = ui._pick("Interpretations / 一致させる必要はありません", reports,
                              lambda r: r["created_at"] + " / " + r["model"]["model"])
            if chosen:
                line(json.dumps(chosen["proposal"], ensure_ascii=False, indent=2))
        elif action == "forget":
            forget(row["id"])


def write_export(path, value):
    target = Path(path).expanduser().absolute()
    for component in [*reversed(target.parents), target]:
        profile.require(not component.is_symlink(), "PERSONAL_EXPORT_SYMLINK")
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    profile.require(len(raw) <= 8 * 1024 * 1024, "PERSONAL_EXPORT_LIMIT")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return str(target)


def portfolio_menu():
    from . import development_console as ui
    from .personal_growth import portfolio
    choices = profile.records("journal", 300)
    selected = []
    while choices:
        row = ui._pick("Select work / 公開候補だけ選ぶ。戻ると選択終了", choices,
                       lambda r: r["created_at"][:10] + " / " + r["project"]["name"])
        if row is None:
            break
        selected.append(row["id"])
        choices = [r for r in choices if r["id"] != row["id"]]
    experiences = [row for row in profile.records("statement", 300)
                   if row["category"] in ("experience", "understanding", "goal")]
    experiences += [row for row in profile.records("lesson", 300)
                    if any(item["choice"].startswith("SELF_REPORTED") and item["text"].strip()
                           for item in row.get("feedback", []))]
    experiences += [row for row in profile.records("skill_progress", 300) if row["human"] != "NO_RECORD"]
    selected_experience = []
    while experiences:
        row = ui._pick("Select your experience / 自己申告・自分の説明だけ。任意", experiences,
                       lambda r: r.get("technology", "") + " / " + (r.get("text") or r.get("title", ""))[:80])
        if row is None:
            break
        selected_experience.append(row["id"])
        experiences = [r for r in experiences if r["id"] != row["id"]]
    if not selected and not selected_experience:
        return
    description = ui._ask("Your contribution / 自分が決めた・理解したことを自分の言葉で")
    value = portfolio(selected, personal_summary=description, experience_ids=selected_experience)
    line(json.dumps(value, ensure_ascii=False, indent=2))
    line("AIとの共同制作として記載します。プロジェクト名とあなたの説明が出力対象です。")
    line("非公開の相談、全プロンプト、ファイルパス、学習推定は含めません。自動公開しません。")
    if ui._start("この内容をローカルファイルへ書き出しますか？"):
        path = ui._ask("New file path / 新しいJSONファイルの場所（空欄で中止）")
        if path:
            line(write_export(path, value))


def forget(identity):
    from . import development_console as ui
    line("本人用の記録と依存する下書きを削除します。プロジェクト台帳や外部AIの履歴は消せません。")
    if ui._pick("Delete this personal record?", [False, True],
                lambda v: "Delete / 削除する" if v else "Keep / 残す") is True:
        profile.forget(identity)
        line("本人用ノートから削除しました。")


def menu(root=None, configuration=None, section="profile"):
    from . import development_console as ui
    if section == "skills":
        from .skill_console import menu as skill_menu
        return skill_menu(root, configuration)
    if section == "pace":
        return pace(root, configuration)
    if section == "journal":
        return journal(root, configuration)
    if section == "next":
        return lessons()
    if section == "portfolio":
        return portfolio_menu()
    if section == "talk":
        return talk(root, configuration)
    while True:
        snap = profile.snapshot()
        line("\nMY PROFILE / 点数ではなく、自分の経験の来歴")
        line("場所: " + snap["home"])
        line("理解・経験・自信・助け方・委譲は別々の記録です。AIへの依頼回数では評価しません。")
        choices = [("add", None, "Add experience / 技術・経験・希望を記録する"),
                   ("talk", None, "Talk / 相談する・自然な言葉で更新案を作る"),
                   ("pace", None, "My pace / 提案の量・共有・今日だけ静かに"),
                   ("journal", None, "My journal / 作ったものと気づき"),
                   ("skills", None, "My skills / AIの手順と、自分が育てる盤面"),
                   ("next", None, "Next time / 理解・参照・委譲の続き"),
                   ("portfolio", None, "Portfolio / 自分の実績として選んで書き出す"),
                   ("backup", None, "Private export / 非公開記録を書き出す"),
                   ("enable", None, "Enable / 日記の自動記録を有効にする"),
                   ("pause", None, "Pause / 自動記録を止める")]
        for row in snap["records"]["report"]:
            if not row.get("journal_id"):
                choices.append(("conversation", row, "Private draft / 相談の下書き " + row["created_at"][:10]))
        for row in snap["records"]["proposal"]:
            if row.get("status") == "PENDING_OWNER":
                choices.append(("proposal", row, "Draft / " + row["proposal"]["text"][:70]))
        for row in snap["records"]["statement"]:
            choices.append(("statement", row, row.get("technology", "") + " / " + row["text"][:70]
                            + (" / 今有効" if profile.active(row) else " / 過去の期間")))
        selected = ui._pick("Choose what helps now", choices, lambda row: row[2])
        if selected is None:
            return
        action, row, _ = selected
        try:
            if action == "add":
                edit_statement()
            elif action == "statement":
                line(row["text"])
                chosen = ui._pick("This statement", ["edit", "forget"], str)
                if chosen == "edit":
                    edit_statement(row)
                elif chosen == "forget":
                    forget(row["id"])
            elif action == "conversation":
                line(row["proposal"].get("reply", ""))
                if ui._pick("This private draft", ["keep", "forget"], str) == "forget":
                    forget(row["id"])
            elif action == "proposal":
                review_proposal(row)
            elif action in ("talk", "pace", "journal", "next", "portfolio", "skills"):
                menu(root, configuration, action)
            elif action == "backup":
                line("この書き出しには非公開の自己申告・日記・相談の下書きが含まれます。公開しないでください。")
                if ui._start("本人用バックアップとして書き出しますか？"):
                    path = ui._ask("New private JSON file path")
                    if path:
                        line(write_export(path, profile.export_bundle()))
            elif action == "pause":
                profile.configure({"enabled": False})
                line("自動記録と個人文脈の送信を止めました。過去の記録は保持しています。")
            elif action == "enable":
                profile.configure({"onboarded": True, "enabled": True})
                line("日記の記録を有効にしました。共有や提案量はMy paceで選べます。")
        except (LedgerError, OSError, ValueError) as error:
            line("この操作だけ未完了です。仕事や以前の記録は残っています。 "
                 + getattr(error, "code", type(error).__name__))
