"""Notebook actions reachable by a menu, not by memorizing command names."""
import shlex
from .cleanroom_io import console_print as print
from .agent_console import terminal_text


def perspectives_menu(root, configuration, run_id=None):
    from . import development_console as ui
    from .owner_experience import read_states, cards
    from .owner_notebook import _browse_card
    from .agent_runtime import organize
    from .agent_models import reflection_setting
    states = [state for state in read_states(root, configuration) if state.get("work_result")]
    state = next((row for row in states if row["run_id"] == run_id), None) if run_id else None
    if state is None:
        state = ui._pick("Whose experience? / 仕事のノート", states, lambda row: row["request"][:120])
    if state is None:
        return
    run_id = state["run_id"]
    while True:
        state = next(row for row in read_states(root, configuration) if row["run_id"] == run_id)
        reflections = state.get("work_reflections", [])
        rows = [("new", None, "New perspective / 同じAIでも、新しく整理する")]
        rows += [("view", row, row["model"]["model"] + " / " + row["status"] + " / " +
                  (row.get("perspective") or "Open perspective")[:80]) for row in reversed(reflections)]
        selected = ui._pick("Perspectives / 一致させず、見方の来歴を残す", rows, lambda row: row[2])
        if selected is None:
            return
        action, reflection, _ = selected
        if action == "new":
            perspective = ui._ask("What would you like to see? / 見たい観点（空欄ならAIに任せる）")
            label = reflection_setting(configuration)["label"]
            print("Work and check records plus explicitly shared Owner notes will be sent to " + terminal_text(label))
            print("Private notes stay local. Earlier interpretations and your choices are retained.")
            if ui._start("Create a new interpretation? / 新しく整理しますか"):
                result = ui._mutate(root, configuration, organize, run_id, perspective=perspective)
                print("Reflection: " + result["reflection"]["status"])
            continue
        if reflection["status"] != "PROPOSED":
            print(terminal_text(reflection.get("failure_code") or reflection["status"]))
            continue
        choices = [row for row in cards(state, include_archived=True)
                   if row["reflection_id"] == reflection["id"]]
        card = ui._pick("This interpretation / この見方から選ぶ", choices,
                        lambda row: row["kind"] + ": " + row["text"][:110])
        if card is not None:
            _browse_card(root, configuration, card)


def check_menu(root, configuration, run_id):
    from . import development_console as ui
    from .work_checks import run_check
    from .commands_notebook import display
    label = ui._ask("What are you checking? / 確認すること", "Candidate check")
    command = ui._ask("Command to run on a COPY of the saved candidate / 空欄で戻る")
    if not command:
        return
    try:
        argv = shlex.split(command)
    except ValueError:
        print("Quotation marks are incomplete. Nothing was executed.")
        return
    if not argv:
        return
    print("COMMAND / " + terminal_text(shlex.join(argv)))
    print("Recorded candidate bytes are copied; the source project is not the working directory.")
    print("This command is NOT an OS sandbox: only run code you trust. It retains your OS permissions.")
    print("API-key variables are not passed. A program can still access files/network allowed by your OS.")
    print("Results stay local. A later organization request can send these logs to the selected AI.")
    if not ui._yes("Run this exact command? / このコマンドの実行を許可しますか"):
        return
    result = ui._mutate(root, configuration, run_check, run_id, argv=argv, label=label, confirmed=True)
    display(result, configuration["ui"]["locale"], "check")
    return result
