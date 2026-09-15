"""Discoverable Work AI / Reflection AI settings and factual notebook receipts."""
import unicodedata
from .cleanroom_io import console_print as print

from .agent_models import (activate_work_api, create_api_profile, reflection_setting,
                           select_reflection)
from .errors import LedgerError


def terminal_text(value):
    return "".join(character if character in "\n\t" or unicodedata.category(character) not in ("Cc", "Cf")
                   else "\\u%04x" % ord(character) for character in str(value))


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
    from .model_settings import ollama_models, activate_codex
    provider = ui._pick("Choose a connection", ["codex", "ollama", "openai", "anthropic", "gemini", "openai_compatible"],
                        lambda name: {"codex": "Codex subscription", "ollama": "Ollama / local",
                                      "openai": "OpenAI API", "anthropic": "Anthropic API",
                                      "gemini": "Gemini API", "openai_compatible": "OpenAI-compatible server"}[name])
    if provider is None:
        return
    if provider == "codex":
        if role == "work":
            ui._mutate(root, configuration, activate_codex)
        else:
            from .model_settings import _profile
            from .commands_codex import create_configs
            directory = _profile(root, "reflection-codex")
            created = create_configs(directory)
            ui._mutate(root, configuration, select_reflection, "custom",
                       adapter=created["adapters"]["implementation"], label="Codex subscription")
        return
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
        action = ui._pick("Models & organization", ["work", "same", "custom", "off", "organize"],
                          lambda value: {"work": "Choose Work AI",
                                         "same": "Reflection: same as Work AI (default)",
                                         "custom": "Reflection: choose a different AI",
                                         "off": "Reflection: off; keep work facts only",
                                         "organize": "Organize recorded work again"}[value])
        if action is None:
            return
        try:
            if action in ("work", "custom"):
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
    label = reflection_setting(configuration)["label"]
    if not ui._start("Send this recorded work to " + label + "?"):
        return
    result = ui._mutate(root, configuration, organize, chosen["run_id"])
    show_result(root, result)


def start_work(root, configuration, mode, previous=None, request=None):
    from . import development_console as ui
    from .development import run_work
    from .model_settings import describe
    request = request if request is not None else ui._ask("What shall we work on?")
    if not request:
        return
    files = ui._context_files(root)
    print("Work AI: " + terminal_text(describe(configuration)["label"]))
    print("Reflection AI: " + terminal_text(reflection_setting(configuration)["label"]))
    print("Only selected project files are sent. Candidate writes stay isolated.")
    print("Purpose, your ownership choices and explicitly shared notes are also context.")
    print("Private notes from the owner notebook are not sent to the AI.")
    print("Requests are interpreted by your AI, not by keyword rules.")
    if not ui._confirm_context(files):
        return
    result = ui._mutate(root, configuration, run_work, request=request, key=ui._key(),
                        include=files, mode=mode, target=None, expectations=[],
                        continue_from=previous["run_id"] if previous else None)
    show_result(root, result)
    return result
