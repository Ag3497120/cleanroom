"""Discoverable project-local settings; opening a menu never calls a model."""
from copy import deepcopy
import json
import shlex
import sys

from . import config
from .agent_console import terminal_text
from .agent_models import reflection_setting
from .cleanroom_io import console_print as print
from .errors import LedgerError
from .model_settings import describe


SECTIONS = ("project", "models", "accounts", "codex", "claude", "learning", "language", "workspace", "boundary", "profile", "pace", "skills", "harness", "sandbox", "notebook", "roles")


def snapshot(root, configuration, section="menu"):
    from .work_harness import snapshot as harness_snapshot
    return {
        "schema_version": 1,
        "command": "settings",
        "section": section,
        "configured": configuration is not None,
        "project_path": str(root),
        "config_path": str(config.config_path(root)),
        "config": deepcopy(configuration),
        "work_ai": describe(configuration) if configuration is not None else None,
        "reflection_ai": reflection_setting(configuration) if configuration is not None else None,
        "work_harness": harness_snapshot(root),
        "model_calls": 0,
        "credentials_checked": False,
        "connection_checked": False,
        "writes": False,
    }


def display(root, configuration):
    value = snapshot(root, configuration)
    print("\nCLEANROOM / SAVED SETTINGS")
    print("Project location: " + terminal_text(value["project_path"]))
    print("Configuration: " + terminal_text(value["config_path"]))
    if configuration is None:
        print("Not configured. Run verantyx setup to choose your settings.")
        return
    print("Name: " + terminal_text(configuration["project"]["name"]))
    print("Purpose: " + terminal_text(configuration["project"]["purpose"] or "Not set"))
    print("Notebook language: " + configuration["ui"]["locale"])
    print("Work AI: " + terminal_text(value["work_ai"]["label"]))
    print("Reflection AI: " + terminal_text(value["reflection_ai"]["label"]))
    print("Work harness: " + terminal_text(value["work_harness"]["label"]))
    print("Learning display: " + configuration["learning"]["mode"])
    print("Learning items per task: " + str(configuration["learning"]["max_items"]))
    print("This shows saved choices, not a successful login or model connection.")


def _save_preferences(root, configuration, section, fields):
    """Preserve all other settings and reject changes made since the form opened."""
    allowed = {"project": {"name", "purpose"}, "learning": {"mode", "max_items"}, "ui": {"locale"}}
    if section not in allowed or set(fields) != allowed[section]:
        raise config.ConfigError("ARGUMENTS")
    current, expected = config.load(root)
    if (current is None or current["project"]["id"] != configuration["project"]["id"]
            or current[section] != configuration[section]):
        raise config.ConfigError("CONFIG_CHANGED")
    updated = deepcopy(current)
    updated[section].update(fields)
    config.validate(updated)
    from .authority import require_current_approval_valid
    require_current_approval_valid()
    changed = config.save(root, updated, expected)
    configuration.clear()
    configuration.update(updated)
    return {"ok": True, "changed": changed, "config_path": str(config.config_path(root))}


def _confirm_save(root, configuration, section, fields):
    from . import development_console as ui
    print("\nProposed settings")
    for key, value in fields.items():
        print("  " + key + ": " + terminal_text(value))
    choice = ui._pick("Save these project settings?", [False, True],
                      lambda value: "Save changes" if value else "Keep current settings")
    if choice is not True:
        return
    result = ui._mutate(root, configuration, _save_preferences, section, fields)
    print("Saved: " + terminal_text(result["config_path"]))


def _section(root, configuration, section):
    from . import development_console as ui
    if section == "notebook":
        from .bridge_console import menu as notebook_menu
        return notebook_menu(root, configuration)
    if section == "roles":
        from .model_roles import menu as roles_menu
        return roles_menu(root, configuration)
    if section == "sandbox":
        from .sandbox_backends import menu as sandbox_menu
        return sandbox_menu(root, configuration)
    if section == "harness":
        from .work_harness import menu as harness_menu
        return harness_menu(root, configuration)
    if section in ("profile", "pace", "skills"):
        from .personal_console import menu
        return menu(root, configuration, section)
    if section in ("accounts", "codex", "claude"):
        from .subscription_setup import configure as connect_subscription
        return connect_subscription(root, configuration, None if section == "accounts" else section)
    if section == "models":
        from .agent_console import configure
        return configure(root, configuration)
    if section == "project":
        print("\nPROJECT / Enter keeps the current value. :clear removes the purpose.")
        name = ui._ask("Project name", configuration["project"]["name"])
        purpose = ui._ask("Project purpose", configuration["project"]["purpose"])
        _confirm_save(root, configuration, "project",
                      {"name": name, "purpose": "" if purpose == ":clear" else purpose})
    elif section == "learning":
        print("\nLEARNING / Display preferences only; this does not mark understanding as achieved.")
        print("To stop model-based organization, choose Reflection: off in Models & organization.")
        mode = ui._pick("When should learning suggestions appear?", ["digest", "manual", "off"],
                        lambda value: {"digest": "Briefly after work", "manual": "Only when I open them",
                                       "off": "Do not show automatic suggestions"}[value])
        if mode is None:
            return
        limit = ui._pick("Maximum suggestions per task", [1, 2, 3], str)
        if limit is not None:
            _confirm_save(root, configuration, "learning", {"mode": mode, "max_items": limit})
    elif section == "language":
        from .i18n import LANGUAGES
        selected = ui._pick("Notebook language", list(LANGUAGES),
                            lambda value: value + " / " + LANGUAGES[value])
        if selected is not None:
            _confirm_save(root, configuration, "ui", {"locale": selected})
            print("Restart the notebook to apply the display language. Settings labels remain English-based.")
    elif section == "workspace":
        print("\nWORKSPACE / " + terminal_text(root))
        print("Settings and work records belong to this project, not every folder on this Mac.")
        print("Use --project to select another existing directory; this menu does not widen access.")
        print("Example: verantyx --project " + shlex.quote(str(root)) + " setup")
        print("Context files must remain within the selected project. Review the send scope before starting.")
        print("Filename-based exclusions do not prove that a file contains no secrets.")
        print("On another Mac, create a fresh Python environment and recreate model connections.")
    elif section == "boundary":
        print("\nAUTHORITY / Read-only explanation, not a permission switch")
        print("Model output is a proposal. It cannot approve itself, prove a test passed, or activate a rule.")
        print("The current Work gateway reads approved text files and writes isolated candidates.")
        print("Shell execution, deletion and publication are not enabled by choosing a model.")
        print("Private Owner notes are not automatically sent to the model.")
        print("AI organization, actual execution receipts, and human understanding remain separate states.")
    else:
        display(root, configuration)


def configure(root, configuration, section="menu"):
    from . import development_console as ui
    if section != "menu":
        return _section(root, configuration, section)
    labels = {
        "accounts": "Accounts / connect ChatGPT or Claude subscription",
        "notebook": "Notebook / Obsidian, imported skills, original learning records",
        "roles": "Parent / child models",
        "models": "Models & organization / Work AI and Reflection AI",
        "harness": "Work harness / built-in or trusted external proposal adapter",
        "sandbox": "Sandbox backend / optional OSS launcher for external Work",
        "skills": "My skills / AI procedures and my personal board",
        "project": "Project / name and purpose",
        "profile": "My profile / personal experience, journal and portfolio",
        "pace": "My pace / person-wide learning, sharing and quiet mode",
        "learning": "Project learning / legacy display preferences",
        "language": "Language / notebook display",
        "workspace": "Workspace / project location and local data",
        "boundary": "Authority / permissions and boundaries",
        "show": "View saved settings / no model call",
    }
    while True:
        print("\nCLEANROOM / SETTINGS")
        print("Keep your project understanding and decisions here. Let AI carry the implementation work.")
        print("Project: " + terminal_text(configuration["project"]["name"]))
        action = ui._pick("Choose a setting", list(labels), labels.get)
        if action is None:
            return
        try:
            _section(root, configuration, action)
        except (config.ConfigError, LedgerError, OSError, ValueError) as error:
            print("This change was not completed: " + terminal_text(getattr(error, "code", type(error).__name__)))
            print("Previously saved settings remain available. No AI work was started.")


def run(root, configuration, expected, locale, *, section="menu", show=False, as_json=False):
    if section in ("notebook", "roles") and (show or as_json):
        if section == "notebook":
            from .notebook_bridge import settings
            value = settings()
        else:
            from .model_roles import load
            value = load(root)
        print(json.dumps(value, ensure_ascii=False, indent=2) if as_json
              else terminal_text(json.dumps(value, ensure_ascii=False, indent=2)))
        return 0
    if section == "sandbox" and (show or as_json):
        from .sandbox_backends import snapshot as sandbox_snapshot
        value = sandbox_snapshot(root)
        print(json.dumps(value, ensure_ascii=False, indent=2) if as_json
              else terminal_text(json.dumps(value, ensure_ascii=False, indent=2)))
        return 0
    if section == "skills" and (show or as_json):
        from .skill_assets import catalogue
        value = catalogue(root, configuration)
        print(json.dumps(value, ensure_ascii=False, indent=2) if as_json
              else terminal_text(json.dumps(value, ensure_ascii=False, indent=2)))
        return 0
    if section == "harness" and (show or as_json):
        from .work_harness import snapshot as harness_snapshot
        value = harness_snapshot(root)
        print(json.dumps(value, ensure_ascii=False, indent=2) if as_json
              else terminal_text(json.dumps(value, ensure_ascii=False, indent=2)))
        return 0
    if section in ("profile", "pace") and (show or as_json):
        from .personal_profile import snapshot as personal_snapshot
        value = personal_snapshot()
        if section == "pace":
            value = {"settings": value["settings"], "scope": "PERSONAL_ACROSS_PROJECTS"}
        print(json.dumps(value, ensure_ascii=False, indent=2) if as_json
              else terminal_text(json.dumps(value, ensure_ascii=False, indent=2)))
        return 0
    if show or as_json:
        if as_json:
            print(json.dumps(snapshot(root, configuration, section), ensure_ascii=False, indent=2))
        else:
            display(root, configuration)
        return 0
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise config.ConfigError("INTERACTIVE_REQUIRED")
    if section in ("profile", "pace", "skills"):
        try:
            _section(root, configuration, section)
        except (EOFError, KeyboardInterrupt):
            return 130
        return 0
    if configuration is None:
        config.save(root, config.defaults(root, locale), expected)
        configuration, _ = config.load(root)
        print("Initialized project-local settings: " + terminal_text(config.config_path(root)))
    try:
        configure(root, configuration, section)
    except (EOFError, KeyboardInterrupt):
        print("\nSettings closed. Earlier saved changes are retained.")
        return 130
    print("\nSettings closed. Run verantyx to open the notebook.")
    return 0
