"""Discoverable Work AI / Reflection AI settings and factual notebook receipts."""
import unicodedata
from .cleanroom_io import console_print as print

from .agent_models import (activate_work_api, create_api_profile, reflection_setting,
                           select_reflection)
from .errors import LedgerError


def terminal_text(value):
    return "".join(character if character in "\n\t" or unicodedata.category(character) not in ("Cc", "Cf")
                   else "\\u%04x" % ord(character) for character in str(value))


def failure_message(code):
    return {
        "CODEX_MODEL_UNAVAILABLE": "選択したモデルをこの接続では利用できません。F2 > Models、または verantyx setup models で選び直してください。",
        "CODEX_LOGIN_REQUIRED": "Codexのログインが必要です。verantyx setup codex から接続してください。",
        "CODEX_RATE_LIMIT": "モデルの利用上限に達しました。保存した候補を保持し、自動再試行はしません。",
    }.get(code, code)


def show_result(root, result):
    from .owner_notebook import show_receipt
    return show_receipt(root, result)


def _legacy_show_result(root, result):
    from .agent_projection import owner_projection, notebook_lines
    state = result.get("state")
    if state and state.get("work_session"):
        projected = owner_projection(state)
        for line in notebook_lines(projected):
            print(terminal_text(line))
        print("\nOWNER / " + result.get("reflection", {}).get("status", "PENDING"))
        for line in notebook_lines(projected, owner=True):
            print(terminal_text(line))
    else:
        print(terminal_text(result.get("work", {}).get("answer", result.get("answer", ""))))
        print("Reflection: " + terminal_text(result.get("reflection", {}).get("status", "PENDING")))
    if result.get("reflection", {}).get("status") == "FAILED":
        print("作業結果は保存済みです。整理だけ未完了のため、後から別モデルでも再整理できます。")
    work = result.get("work", {})
    if work.get("artifact_directory"):
        print("Candidate directory: " + str(root) + "/" + work["artifact_directory"])
    print("実装候補・検証・本人の理解は別状態です。整理AIは規則を有効化できません。")


def _connection(root, configuration, role):
    from . import development_console as ui
    from .model_settings import ollama_models
    provider = ui._pick("Choose a connection", ["codex", "claude", "ollama", "openai", "anthropic", "gemini", "openai_compatible"],
                        lambda name: {"codex": "ChatGPT subscription / Codex",
                                      "claude": "Claude subscription / Claude Code",
                                      "ollama": "Ollama / local",
                                      "openai": "OpenAI API", "anthropic": "Anthropic API",
                                      "gemini": "Gemini API", "openai_compatible": "OpenAI-compatible server"}[name])
    if provider is None:
        return
    if provider in ("codex", "claude"):
        from .subscription_setup import configure as connect_subscription
        return connect_subscription(root, configuration, provider, role=role)
    preset = ui._MODEL_PRESETS[provider]
    available = ollama_models() if provider == "ollama" else []
    model = ui._pick("Installed local models", available, str) if available else None
    if model is None:
        model = ui._ask("Model name (blank to cancel)")
    if not model:
        return
    endpoint = preset["endpoint"].format(model=model)
    if provider in ("ollama", "openai_compatible"):
        endpoint = ui._ask("Server endpoint", endpoint)
    print("Credentials remain in " + (preset["key_env"] or "the configured local server") + "; no API key is stored here.")
    parameters = dict(provider=preset["provider"], model=model, endpoint=endpoint,
                      key_env=preset["key_env"], allow_loopback_http=preset["loopback"])
    if role == "work":
        ui._mutate(root, configuration, activate_work_api, **parameters)
    else:
        directory = create_api_profile(root, **parameters)
        ui._mutate(root, configuration, select_reflection, "custom",
                   adapter=str(directory / "implementation.json"), label=provider + " / " + model)


def configure(root, configuration):
    from . import development_console as ui
    from .model_settings import describe
    while True:
        reflection = reflection_setting(configuration)
        print("\nWork AI: " + terminal_text(describe(configuration)["label"]))
        print("Reflection AI: " + terminal_text(reflection["label"]))
        action = ui._pick("Models & organization", ["work", "roles", "same", "custom", "off", "organize"],
                          lambda value: {"work": "Choose Work AI", "roles": "Parent / child model roles",
                                         "same": "Reflection: same as Work AI (default)",
                                         "custom": "Reflection: choose a different AI",
                                         "off": "Reflection: off; keep work facts only",
                                         "organize": "Organize recorded work again"}[value])
        if action is None:
            return
        try:
            if action == "roles":
                from .model_roles import menu as roles_menu
                roles_menu(root, configuration)
            elif action in ("work", "custom"):
                _connection(root, configuration, "work" if action == "work" else "reflection")
            elif action in ("same", "off"):
                ui._mutate(root, configuration, select_reflection, action)
            else:
                organize_menu(root, configuration)
        except (LedgerError, OSError, ValueError) as error:
            print("Settings were not completed: " + getattr(error, "code", "INVALID_CONNECTION"))


def organize_menu(root, configuration, run_id=None):
    from . import development_console as ui
    from .development import work_summaries
    from .agent_runtime import organize
    chosen = next((row for row in work_summaries(root, configuration)
                   if row["run_id"] == run_id and row.get("work_plane")), None) if run_id else ui._pick(
                       "Recorded work", [row for row in work_summaries(root, configuration) if row.get("work_plane")],
                       lambda row: row["label"])
    if not chosen:
        return
    perspective = ui._ask("Perspective / 見たい観点（空欄ならAIに任せる）")
    label = reflection_setting(configuration)["label"]
    print("This creates a fresh interpretation. Earlier viewpoints and human choices remain.")
    if not ui._start("Send this recorded work to " + label + "?"):
        return
    result = ui._mutate(root, configuration, organize, chosen["run_id"], perspective=perspective)
    show_result(root, result)


def start_work(root, configuration, mode, previous=None, request=None):
    import json
    from . import development_console as ui
    from .development import run_work
    from .model_settings import describe
    request = request if request is not None else ui._ask("What shall we work on?")
    if not request:
        return
    files = ui._context_files(root)
    from .work_harness import snapshot as harness_snapshot
    harness = harness_snapshot(root)
    print("Work runtime: " + terminal_text(harness["label"]))
    print("Work AI: " + terminal_text(describe(configuration)["label"])
          + (" / external proposal process selected" if harness["mode"] == "process" else ""))
    if harness["mode"] == "process":
        print("Trusted external process, not an OS sandbox. Only its host proposals have Cleanroom tool receipts.")
    print("Reflection AI: " + terminal_text(reflection_setting(configuration)["label"]))
    print("Only selected project files are sent. Candidate writes stay isolated.")
    print("Purpose, your ownership choices and explicitly shared notes are also context.")
    print("Private notes from the owner notebook are not sent to the AI.")
    from .personal_growth import context as personal_context
    personal = personal_context()
    if personal.get("sharing") == "OWNER_OPTED_IN":
        print("Personal context: explicitly shared experience and learning excerpts across projects.")
        print("The selected Reflection AI may make one extra call to draft your personal journal.")
    print("Requests are interpreted by your AI, not by keyword rules.")
    if not ui._confirm_context(files):
        return
    from .personal_growth import owner_input
    from .personal_console import record_technology
    from .model_roles import owner_confirmation
    def confirm_model(proposal):
        print("MODEL CHANGE / " + terminal_text(json.dumps(proposal, ensure_ascii=False)))
        return ui._start("Use this model for future calls? The provider and cost may change.")
    with owner_input(record_technology), owner_confirmation(confirm_model):
        result = ui._mutate(root, configuration, run_work, request=request, key=ui._key(),
                            include=files, mode=mode, target=None, expectations=[],
                            continue_from=previous["run_id"] if previous else None)
    show_result(root, result)
    return result
