"""Project setup, explicit candidate workflows and voluntary learning."""
import argparse
import copy
import json
from pathlib import Path
import sys
import sqlite3
import unicodedata

from . import __version__
from . import config
from .i18n import LANGUAGES, environment_locale, normalize, text
from .errors import LedgerError


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's English prose must not become the localized public API.
        raise config.ConfigError("ARGUMENTS")


def parse(argv):
    common = Parser(add_help=False, allow_abbrev=False)
    common.add_argument("--lang")
    common.add_argument("--project", default=".")
    common.add_argument("--json", action="store_true")
    common.add_argument("--plain", action="store_true")
    common.add_argument("--tutorial", action="store_true")
    common.add_argument("--version", action="store_true")
    common.add_argument("-h", "--help", action="store_true")
    options, rest = common.parse_known_args(argv)
    parser = Parser(add_help=False, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", parser_class=Parser)
    sub.add_parser("desktop-bridge", add_help=False, allow_abbrev=False)
    for command in ("tutorial", "status", "config", "doctor"):
        sub.add_parser(command, add_help=False, allow_abbrev=False)
    watcher = sub.add_parser("watch", add_help=False, allow_abbrev=False)
    watcher.add_argument("run_id", nargs="?")
    watcher.add_argument("--run", dest="watch_run")
    watcher.add_argument("--once", action="store_true")
    starter = sub.add_parser("start", add_help=False, allow_abbrev=False)
    starter.add_argument("--adapter")
    starter.add_argument("--editor-adapter")
    starter.add_argument("--max-repairs", type=int, choices=(0, 1, 2), default=1)
    starter.add_argument("--auto-check", action="store_true")
    starter.add_argument("--economy", action="store_true")
    starter.add_argument("--execute-candidate", action="store_true")
    starter.add_argument("--precedent")
    starter.add_argument("--component", default="UNSPECIFIED")
    starter.add_argument("--workload", default="UNSPECIFIED")
    starter.add_argument("--risk", choices=("LOW", "MEDIUM", "HIGH", "UNSPECIFIED"), default="UNSPECIFIED")
    starter.add_argument("--check-rounds", type=int, choices=(1, 2, 3), default=2)
    starter.add_argument("--max-checks", type=int, choices=range(1, 9), default=4)
    starter.add_argument("--timeout", type=int, default=600)
    starter.add_argument("--include", action="append", default=[])
    starter.add_argument("--plain", action="store_true")
    setup = sub.add_parser("setup", add_help=False, allow_abbrev=False)
    sections = ("project", "models", "accounts", "codex", "claude", "learning", "language", "workspace", "boundary", "profile", "pace", "skills", "harness", "sandbox", "notebook", "roles")
    setup.add_argument("section", nargs="?", choices=sections)
    setup.add_argument("--show", action="store_true")
    setup.add_argument("--non-interactive", action="store_true")
    setup.add_argument("--guided", action="store_true")
    setup.add_argument("--name")
    setup.add_argument("--purpose")
    setup.add_argument("--learning", choices=("manual", "digest", "off"))
    setup.add_argument("--max-items", type=int)
    settings = sub.add_parser("settings", add_help=False, allow_abbrev=False)
    settings.add_argument("section", nargs="?", choices=sections)
    settings.add_argument("--show", action="store_true")
    models = sub.add_parser("models", aliases=["model"], add_help=False, allow_abbrev=False)
    models.add_argument("--show", action="store_true")
    for command in ("run", "resume"):
        task = sub.add_parser(command, add_help=False, allow_abbrev=False)
        if command == "run":
            task.add_argument("request")
            task.add_argument("--task-id", dest="run_id")
            task.add_argument("--component", default="UNSPECIFIED")
            task.add_argument("--workload", default="UNSPECIFIED")
            task.add_argument("--risk", choices=("LOW", "MEDIUM", "HIGH", "UNSPECIFIED"), default="UNSPECIFIED")
        else:
            task.add_argument("run_id")
        task.add_argument("--proposal")
        task.add_argument("--observe", action="append", default=[])
        task.add_argument("--ttl", type=int, default=300)
        task.add_argument("--key")
        task.add_argument("--expected-revision", type=int)
    for command in ("replay", "gaps", "rights", "proposal-template", "events"):
        reader = sub.add_parser(command, add_help=False, allow_abbrev=False)
        reader.add_argument("run_id", **({"nargs": "?"} if command == "events" else {}))
        if command != "proposal-template":
            reader.add_argument("--archive")
    runs = sub.add_parser("runs", add_help=False, allow_abbrev=False)
    runs.add_argument("--archive")
    exporter = sub.add_parser("export", add_help=False, allow_abbrev=False)
    exporter.add_argument("--output")
    exporter.add_argument("--archive")
    importer = sub.add_parser("import", add_help=False, allow_abbrev=False)
    importer.add_argument("path")
    sub.add_parser("archives", add_help=False, allow_abbrev=False)
    for command in ("rules", "precedents"):
        sub.add_parser(command, add_help=False, allow_abbrev=False)
    learner = sub.add_parser("learn", add_help=False, allow_abbrev=False)
    learner.add_argument("run_id")
    learner.add_argument("--archive")
    for command in ("decide", "precedent-accept", "rule-draft", "rule-shadow", "rule-confirm", "rule-activate",
                    "rule-retire", "rule-contest", "rule-amend"):
        control = sub.add_parser(command, add_help=False, allow_abbrev=False)
        control.add_argument("target")
        control.add_argument("--key")
        control.add_argument("--expected-revision", type=int)
        if command == "decide":
            control.add_argument("--point", required=True)
        if command in ("decide", "rule-amend"):
            control.add_argument("--choice", required=True)
        if command in ("decide", "rule-amend", "rule-retire", "rule-contest"):
            control.add_argument("--reason", required=True)
    for command in ("authorize", "execute", "inspect-workspace"):
        effect = sub.add_parser(command, add_help=False, allow_abbrev=False)
        effect.add_argument("run_id")
        effect.add_argument("--key", required=True)
        effect.add_argument("--precedent", required=True)
        if command == "authorize":
            effect.add_argument("--action", required=True)
            effect.add_argument("--ttl", type=int, default=300)
        elif command == "execute":
            effect.add_argument("--lease", required=True)
    from .commands_v03 import register
    register(sub)
    from .commands_v04 import register as register_v04
    register_v04(sub)
    from .commands_personal import register as register_personal
    register_personal(sub)
    from .commands_notebook_bridge import register as register_connections
    register_connections(sub)
    from .commands_toolbox import register as register_toolbox
    register_toolbox(sub)
    organize = sub.add_parser("organize", help="Organize recorded work with the selected Reflection AI")
    organize.add_argument("run_id")
    organize.add_argument("--adapter", help="Explicit adapter override for this organization run")
    organize.add_argument("--key")
    organize.add_argument("--perspective", default="", help="A free-form lens; earlier interpretations are retained")
    organize.add_argument("--timeout", type=int, default=120)
    if options.help or options.version:
        return options, argparse.Namespace(command=None)
    try:
        args = parser.parse_args(rest)
    except config.ConfigError:
        # A normal agent accepts `verantyx "do this work"` without requiring
        # users to learn a verb before their first task. Flags still retain the
        # strict command parser and are never guessed as a request.
        if rest and rest[0] not in sub.choices and all(not value.startswith("-") for value in rest):
            args = argparse.Namespace(command="develop", request=" ".join(rest), input=None,
                                      origin_project=None, capture_mode="assisted", key=None, include=[],
                                      target=None, expect=[], reject_json=[], continue_from=None,
                                      assumption=None, allow_contested_handoff=False)
        else:
            raise
    if args.command == "commands":
        from .commands_toolbox import catalogue
        args.catalogue = catalogue(sub)
    if options.tutorial:
        if args.command is not None:
            raise config.ConfigError("ARGUMENTS")
        args.command = "tutorial"
    return options, args


def visible(value):
    # Terminal controls from user-owned paths/config must remain visible text.
    return "".join(f"\\u{ord(c):04x}" if unicodedata.category(c) in ("Cc", "Cf") else c for c in str(value))


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def prompt(locale, key, default):
    answer = input(text(locale, key, default=visible(default)) + " ").strip()
    if answer == ":q":
        raise KeyboardInterrupt()
    return answer or str(default)


def select_number(locale, key, default, low, high):
    while True:
        answer = prompt(locale, key, default)
        try:
            number = int(answer)
            if low <= number <= high:
                return number
        except ValueError:
            pass
        print(text(locale, "invalid_choice"))


def guide(locale, as_json=False):
    steps = [text(locale, f"guide_{i}") for i in range(1, 5)]
    if as_json:
        emit({"schema_version": 1, "command": "tutorial", "locale": locale, "steps": steps,
              "setup_command": f"verantyx setup --lang {locale}", "writes": False})
    else:
        print(f"verantyx {__version__}\n")
        print("\n\n".join(steps))


def help_text(locale, as_json=False):
    from .commands_experience import help_lines
    value = "\n\n".join(text(locale, key) for key in ("slogan", "usage", "commands", "options", "phase"))
    value += "\n\n" + "\n".join(help_lines(locale))
    value += ("\n\nCleanroom settings (no AI call on opening):"
              "\n  verantyx setup                 Settings menu"
              "\n  verantyx setup accounts        Connect an official subscription CLI"
              "\n  verantyx setup codex           ChatGPT subscription sign-in and model"
              "\n  verantyx setup claude          Claude subscription sign-in and model"
              "\n  verantyx setup models          Work AI and Reflection AI"
              "\n  verantyx models                Shortcut to model settings"
              "\n  verantyx settings              Settings menu (alias)"
              "\n  verantyx setup project         Project name and purpose"
              "\n  verantyx setup learning        Learning display preferences"
              "\n  verantyx setup language        Notebook language"
              "\n  verantyx setup workspace       Project location and local data"
              "\n  verantyx setup boundary        Permission boundaries (read-only)"
              "\n  verantyx settings --show       Saved settings; no changes"
              "\n  verantyx settings --json       Saved settings as JSON; no changes"
              "\n  verantyx setup --guided        Previous detailed setup"
              "\n  verantyx --project PATH setup  Settings for another project")
    if as_json:
        emit({"schema_version": 1, "command": "help", "locale": locale, "text": value})
    else:
        print(value)


def summary(root, value, locale, review=False):
    print(text(locale, "review" if review else "current_settings"))
    pairs = [
        ("project_path", root), ("project_name", value["project"]["name"]),
        ("purpose", value["project"]["purpose"]),
        ("language", LANGUAGES[value["ui"]["locale"]]),
        ("learning", text(locale, "learning_" + value["learning"]["mode"])),
        ("max_items", value["learning"]["max_items"]), ("config_location", config.config_path(root)),
    ]
    for key, item in pairs:
        print(text(locale, key) + ": " + visible(item))


def setup(root, existing, expected, locale, args, explicit_locale, as_json, show_guide=False):
    non_interactive = getattr(args, "non_interactive", False)
    guided = getattr(args, "guided", False)
    if not non_interactive and (as_json or not sys.stdin.isatty() or not sys.stdout.isatty()):
        raise config.ConfigError("INTERACTIVE_REQUIRED")
    value = copy.deepcopy(existing) if existing is not None else config.defaults(root, locale)
    value["ui"]["locale"] = locale
    if not non_interactive:
        if not explicit_locale:
            print("Language / 言語 / 语言 / 언어 / Idioma")
            for index, name in enumerate(LANGUAGES.values(), 1):
                print(f"  {index}. {name}")
            chosen = select_number(locale, "language_prompt", list(LANGUAGES).index(locale) + 1, 1, 5)
            locale = list(LANGUAGES)[chosen - 1]
            value["ui"]["locale"] = locale
        if show_guide:
            guide(locale)
        print("\n" + text(locale, "setup_title"))
        print(text(locale, "project_path") + ": " + visible(root))
        if locale == "ja":
            print("AIに任せたいことを一文で入力してください。詳細な設定は後から変更できます。")
        else:
            print("Describe what you want to build. Advanced settings can be changed later.")
        value["project"]["purpose"] = prompt(locale, "purpose_prompt", value["project"]["purpose"])
        if guided:
            value["project"]["name"] = prompt(locale, "name_prompt", value["project"]["name"])
            modes = ("manual", "digest", "off")
            for number, mode in enumerate(modes, 1):
                print(f"  {number}. {text(locale, 'learning_' + mode)}")
            choice = select_number(locale, "learning_prompt", modes.index(value["learning"]["mode"]) + 1, 1, 3)
            value["learning"]["mode"] = modes[choice - 1]
            value["learning"]["max_items"] = select_number(locale, "limit_prompt", value["learning"]["max_items"], 1, 3)
    for key in ("name", "purpose"):
        if getattr(args, key, None) is not None:
            value["project"][key] = getattr(args, key)
    if getattr(args, "learning", None) is not None:
        value["learning"]["mode"] = args.learning
    if getattr(args, "max_items", None) is not None:
        value["learning"]["max_items"] = args.max_items
    config.validate(value)
    if not non_interactive and guided:
        summary(root, value, locale, review=True)
        if select_number(locale, "save_prompt", 2, 1, 2) != 1:
            print(text(locale, "cancelled"))
            return 130
    changed = config.save(root, value, expected)
    if as_json:
        emit({"schema_version": 1, "ok": True, "command": "setup", "changed": changed,
              "config_path": str(config.config_path(root)), "config": value, "agent_execution": False})
    else:
        print(text(locale, "saved", path=visible(config.config_path(root))))
        if locale == "ja":
            print("準備できました。次は `verantyx --lang ja develop` を実行し、AIに頼みたいことをそのまま入力してください。")
        else:
            print("Ready. Run `verantyx develop` and enter the work you want to delegate.")
    return 0


def status(root, value, locale, command, as_json):
    from .application import CAPABILITIES
    result = {"schema_version": 1, "ok": value is not None, "command": command,
              "phase": "0.6 hybrid answers and experience capture", "configured": value is not None,
              "config_path": str(config.config_path(root)), "config": value,
              "capabilities": CAPABILITIES}
    if command == "doctor":
        result["checks"] = {"python_supported": sys.version_info >= (3, 11),
                            "project_exists": root.is_dir(), "configuration_valid": value is not None}
    if as_json:
        emit(result)
    else:
        print(text(locale, "status_title"))
        if value is None:
            print(text(locale, "error.NOT_CONFIGURED"))
        else:
            summary(root, value, locale)
            if command == "doctor":
                print(text(locale, "doctor_ok"))
        print(text(locale, "phase"))
        print(text(locale, "next"))
    return 0 if value is not None else 3


def print_question(question, locale):
    if "path" in question:
        print(text(locale, "ledger.question", path=visible(question["path"])))
    else:
        print(visible(question["question"]))


def kernel_output(result, locale, as_json, command):
    if command == "export" and not as_json and not result["output"]:
        print(result["bundle"], end="")
        return
    if as_json or command == "proposal-template":
        if command == "export" and result["output"]:
            result = {k: v for k, v in result.items() if k != "bundle"}
        emit(result)
        return
    from .commands_v04 import handler
    if command == "organize":
        from .agent_console import show_result
        show_result(".", result)
        return
    extension = handler(command)
    if extension is not None:
        if command in ("verify-plan", "verify-run") and result.get("verification"):
            from .presentation import display_verification
            display_verification(result, locale)
            return
        extension.display(result, locale, command)
        return
    from .commands_v03 import COMMANDS, display
    if command in COMMANDS - {"propose"} or command == "learn":
        display(result, locale, command)
        return
    print(text(locale, "ledger.saved" if command in ("run", "resume", "import") else "ledger.title"))
    if "state" in result:
        state = result["state"]
        print(text(locale, "ledger.run", run=visible(state["run_id"]), revision=state["revision"]))
        print(text(locale, "ledger.request", request=visible(state["request"])))
        if result.get("duplicate"):
            print(text(locale, "ledger.duplicate"))
        assessment = state["assessment"]
        from .presentation import display_reply
        display_reply(state, locale)
        print(text(locale, "ledger.observations", count=len(state["latest_observations"])))
        print(text(locale, "ledger.gaps", count=len(assessment["gaps"])))
        if assessment["question"]:
            print_question(assessment["question"], locale)
        print(text(locale, "ledger.next", run=visible(state["run_id"])))
        for name in ("precedent_id", "rule_id", "lease_id"):
            if name in result:
                print(name + ": " + result[name])
        if result.get("execution"):
            item = result["execution"]
            print(text(locale, "effect.status." + item["status"]))
            if item.get("receipt"):
                receipt = item["receipt"]
                print(text(locale, "effect.path", path=visible(receipt["worktree"])))
                print(text(locale, "effect.shared_rejected"))
                if receipt["verification"]:
                    from .domain.effects import unittest_closure
                    closure = unittest_closure(receipt["verification"]["result"])
                    message = {"BOUNDED": "effect.test_pass", "REFUTED": "effect.test_fail"}.get(closure, "effect.test_unknown")
                    print(text(locale, message))
            if item.get("reason"):
                print(text(locale, "effect.reason", reason=visible(item["reason"])))
    elif command in ("rules", "precedents"):
        for item in result[command]:
            print(item["id"] + " : " + visible(item["scope"]) + " → " + visible(item["choice"]))
    elif command == "learn":
        for item in result["human_delta"]:
            print(visible(item["concept"]) + " (" + item["ownership_target"] + "; " + item["mastery_evidence"] + ")")
            print(visible(item["minimum_model"]))
            print(visible(item["check"]))
    elif command == "runs":
        for run in result["runs"]:
            print(text(locale, "ledger.run", run=visible(run["run_id"]), revision=run["revision"]))
            print("  " + visible(run["request"]))
    elif command == "events":
        for event in result["events"]:
            print(f'{event["revision"]}. {text(locale, "event." + event["type"])} — {event["project_id"]}:{event["event_id"]}')
    elif command == "gaps":
        from .presentation import gap_text
        for gap in result["gaps"]:
            print(gap_text(gap, locale))
            if gap.get("question"):
                print("  " + visible(gap["question"]))
        if result["question"]:
            print_question(result["question"], locale)
    elif command == "rights":
        for path in result["effective_read_paths"]:
            print("  " + visible(path))
        print(text(locale, "ledger.rights_limit"))
    elif command == "import":
        print(text(locale, "ledger.archive", archive=result["archive_id"]))
    elif command == "archives":
        for archive in result["archives"]:
            print(text(locale, "ledger.archive", archive=archive["archive_id"]))
    elif command == "export":
        print(text(locale, "ledger.export", path=visible(result["output"])))
    if result.get("trust") == "ARCHIVE_ONLY" or result.get("state", {}).get("trust") == "ARCHIVE_ONLY":
        print(text(locale, "ledger.archive_only"))
    print(text(locale, "ledger.boundary"))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    locale, as_json = environment_locale(), "--json" in argv
    # Recover the requested language even when another argument is invalid.
    for index, argument in enumerate(argv):
        wanted = argument.split("=", 1)[1] if argument.startswith("--lang=") else (
            argv[index + 1] if argument == "--lang" and index + 1 < len(argv) else None)
        if wanted:
            try:
                locale = normalize(wanted)
            except ValueError:
                pass
    try:
        options, args = parse(argv)
        if options.lang:
            try:
                locale = normalize(options.lang)
            except ValueError:
                raise config.ConfigError("LOCALE_UNSUPPORTED") from None
        if options.version:
            emit({"version": __version__}) if as_json else print(f"verantyx {__version__}")
            return 0
        if args.command == "desktop-bridge":
            from .desktop_bridge import serve
            return serve()
        root = Path(options.project).expanduser().resolve()
        if options.help:
            # Help remains accessible with missing/corrupt project configuration.
            try:
                existing, _ = config.load(root)
                if existing is not None and not options.lang:
                    locale = existing["ui"]["locale"]
            except (config.ConfigError, OSError):
                pass
            help_text(locale, as_json)
            if not as_json:
                print("\nCleanroom: verantyx | verantyx \"your task\" | verantyx watch [run-id]")
                print("Tab/arrow keys/Enter: menu. --plain: scrollback UI. watch --once --json: read-only snapshot.")
                print("Personal notebook: setup profile | setup pace | my-profile | my-journal | my-portfolio | my-skills")
                print("My Atlas: verantyx web [--no-open] [--port 4310] | read-only local experience map")
                print("Unpack: my-learning | my-skills unpack --id ID | summary, full explanation, original sources")
                print("Sandbox connector: setup sandbox | trusted OSS launcher; isolation not attested")
                print("My skills: optional board. setup harness: built-in or trusted external proposal adapter.")
                print("Optional self-reports, not a skill exam. Delegating work never lowers a score.")
            return 0
        if args.command == "commands":
            rows = args.catalogue
            if args.name:
                rows = [row for row in rows if row["command"] == args.name]
                if not rows:
                    raise LedgerError("ARGUMENTS")
            if as_json:
                emit({"ok": True, "commands": rows})
            else:
                for row in rows:
                    print(row["usage"])
                print("\nUse: verantyx commands NAME --json for argument details.")
            return 0
        if args.command == "toolbox":
            from .commands_toolbox import dispatch as dispatch_toolbox
            from .authority import command_scope
            tool_configuration, _ = config.load(root)
            if tool_configuration is None:
                raise LedgerError("NOT_CONFIGURED")
            with command_scope(root, tool_configuration, args):
                result = dispatch_toolbox(root, tool_configuration, args)
            emit(result)
            return 0
        from .commands_notebook_bridge import COMMANDS as CONNECTION_COMMANDS
        if args.command in CONNECTION_COMMANDS:
            connection_configuration, _ = config.load(root)
            if args.command == "mcp":
                from .notebook_mcp import serve as serve_mcp
                return serve_mcp(root, connection_configuration, allow_personal=args.allow_personal,
                                 allow_import=args.allow_import)
            from .commands_notebook_bridge import dispatch as dispatch_connections
            result = dispatch_connections(root, connection_configuration, args)
            if result.get("status") != "CLOSED":
                emit(result)
            return 0
        from .commands_personal import COMMANDS as PERSONAL_COMMANDS
        if args.command in PERSONAL_COMMANDS:
            from .commands_personal import dispatch as dispatch_personal
            try:
                personal_configuration, _ = config.load(root)
            except (config.ConfigError, OSError):
                personal_configuration = None
            personal_locale = locale
            if personal_configuration is not None and not options.lang:
                personal_locale = personal_configuration.get("ui", {}).get("locale", locale)
            args.locale_override = bool(options.lang)
            result = dispatch_personal(root, personal_configuration, args,
                                       as_json=as_json, locale=personal_locale)
            if as_json:
                emit(result)
            elif result.get("status") != "CLOSED":
                from .agent_console import terminal_text
                print(terminal_text(json.dumps(result, ensure_ascii=False, indent=2)))
            return 0
        existing, expected = config.load(root)
        if existing is not None and not options.lang:
            locale = existing["ui"]["locale"]
        if args.command in ("setup", "settings", "models", "model"):
            section = getattr(args, "section", None)
            project_options = args.command == "setup" and (
                args.guided or args.non_interactive or any(
                    getattr(args, name, None) is not None
                    for name in ("name", "purpose", "learning", "max_items")))
            if project_options:
                if section not in (None, "project") or args.show:
                    raise config.ConfigError("ARGUMENTS")
            else:
                from .settings_console import run as run_settings
                return run_settings(root, existing, expected, locale,
                                    section=section or ("models" if args.command in ("models", "model") else "menu"),
                                    show=args.show, as_json=as_json)
        if args.command == "watch":
            if existing is None:
                raise LedgerError("NOT_CONFIGURED")
            if args.run_id and args.watch_run and args.run_id != args.watch_run:
                raise config.ConfigError("ARGUMENTS")
            from .cleanroom_tui import watch
            return watch(root, existing, run_id=args.watch_run or args.run_id,
                         once=args.once, as_json=as_json, plain=options.plain)
        if args.command == "setup":
            if existing is not None:
                from .authority import command_scope
                with command_scope(root, existing, args):
                    return setup(root, existing, expected, locale, args, bool(options.lang), as_json)
            return setup(root, existing, expected, locale, args, bool(options.lang), as_json)
        if args.command == "tutorial":
            if sys.stdin.isatty() and sys.stdout.isatty() and not as_json:
                from .onboarding_walkthrough import offer
                offer(root, existing or config.defaults(root, locale), force=True)
            else:
                from .interaction_text import help_text as interaction_help
                if as_json:
                    emit({"command": "tutorial", "locale": locale, "text": interaction_help(locale),
                          "simulated": True, "model_calls": 0, "writes": False})
                else:
                    print(interaction_help(locale))
            return 0
        if args.command is None and sys.stdin.isatty() and sys.stdout.isatty() and not as_json:
            onboarding = existing is None
            if existing is None:
                config.save(root, config.defaults(root, locale), expected)
                existing, expected = config.load(root)
            from .terminal_ui import capable_terminal
            if not options.plain and capable_terminal():
                from .cleanroom_tui import interact
            else:
                from .development_console import interact
            result = interact(root, existing, onboarding=onboarding)
            return 0 if result.get("ok", True) else 4
        if args.command == "start":
            if existing is None:
                raise LedgerError("NOT_CONFIGURED")
            from .console import start
            args.plain = args.plain or options.plain
            return start(root, existing, locale, args, as_json)
        if existing is None and args.command == "develop" and args.request:
            config.save(root, config.defaults(root, locale), expected)
            existing, expected = config.load(root)
        if args.command not in (None, "status", "config", "doctor"):
            if existing is None:
                raise LedgerError("NOT_CONFIGURED")
            if args.command == "develop" and not args.request and not args.input:
                if as_json or not sys.stdin.isatty() or not sys.stdout.isatty():
                    raise LedgerError("INTERACTIVE_REQUIRED")
                # Wait for input outside the global command lock. Each selected
                # mutation enters the normal authority gate independently.
                from .terminal_ui import capable_terminal
                if not options.plain and capable_terminal():
                    from .cleanroom_tui import interact
                else:
                    from .development_console import interact
                result = interact(root, existing)
                return 0 if result.get("ok", True) else 4
            if args.command == "develop" and args.request and not args.input and not options.plain and not as_json:
                from .terminal_ui import capable_terminal
                explicit = any(getattr(args, name, None) for name in (
                    "key", "include", "target", "expect", "reject_json", "continue_from", "assumption", "allow_contested_handoff"))
                if capable_terminal() and not explicit:
                    from .cleanroom_tui import interact
                    result = interact(root, existing, initial_request=args.request)
                    return 0 if result.get("ok", True) else 4
            from .application import dispatch
            result = dispatch(root, existing, args, locale)
            kernel_output(result, locale, as_json, args.command)
            return 0 if result.get("ok", True) else 4
        return status(root, existing, locale, args.command or "status", as_json)
    except (KeyboardInterrupt, EOFError):
        code, exit_code = "CANCELLED", 130
    except config.ConfigError as error:
        code = error.code
        exit_code = 3 if code == "INTERACTIVE_REQUIRED" else (4 if code in ("CONFIG_LOCKED", "CONFIG_CHANGED") else 2)
    except LedgerError as error:
        code = error.code
        exit_code = 4 if code in ("IDEMPOTENCY_CONFLICT", "REVISION_CONFLICT", "RUN_EXISTS", "PROPOSAL_CONTEXT") else (
            3 if code in ("NOT_CONFIGURED", "RUN_NOT_FOUND") else 2)
        if as_json:
            emit({"schema_version": 1, "ok": False,
                  "error": {"code": code, "message": text(locale, "error." + code), "details": error.details}})
            return exit_code
    except sqlite3.Error as error:
        code = "STORE_BUSY" if "locked" in str(error).lower() else "STORE_INTEGRITY"
        exit_code = 4 if code == "STORE_BUSY" else 5
    except OSError:
        code, exit_code = "IO", 5
    message = text(locale, "error." + code)
    if as_json:
        emit({"schema_version": 1, "ok": False, "error": {"code": code, "message": message}})
    else:
        print(f"{code}: {message}", file=sys.stderr)
    return exit_code
