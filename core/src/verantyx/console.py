"""Interactive navigation over existing, independently gated CLI operations."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import sys
import uuid

from . import config
from .adapters.command_process import load_command
from .adapters.observations import read_document
from .domain.codec import canonical, decode
from .errors import LedgerError
from .i18n import text


def _operation(root, locale, arguments):
    from .application import dispatch
    from .cli import parse
    configuration, _ = config.load(root)
    if configuration is None:
        raise LedgerError("NOT_CONFIGURED")
    _, args = parse(arguments)
    return dispatch(root, configuration, args, locale)


def _selection_path(root, role="proposal"):
    config.check_location(root)
    if role not in ("proposal", "editor"):
        raise LedgerError("CONSOLE_CONFIG")
    path = root / ".verantyx" / ("console.json" if role == "proposal" else "editor.json")
    if path.is_symlink():
        raise LedgerError("CONSOLE_CONFIG")
    return path


def adapter_info(path):
    path = Path(path).expanduser().resolve()
    command = load_command(path)
    model = command.get("model_api") or command.get("codex_cli")
    return {"path": str(path), "sha256": hashlib.sha256(read_document(path, 65536)).hexdigest(),
            "label": (model["provider"] + " / " + model["model"]) if model else path.name}


def saved_adapter(root, role="proposal"):
    path = _selection_path(root, role)
    if not path.exists():
        return None
    value = decode(read_document(path, 65536), 65536)
    if (type(value) is not dict or set(value) != {"format", "adapter", "sha256"}
            or value["format"] != "verantyx.console.v1" or type(value["adapter"]) is not str
            or not Path(value["adapter"]).is_absolute()):
        raise LedgerError("CONSOLE_CONFIG")
    info = adapter_info(value["adapter"])
    if info["sha256"] != value["sha256"]:
        raise LedgerError("CONSOLE_ADAPTER_CHANGED")
    return info


def remember_adapter(root, info, role="proposal"):
    path = _selection_path(root, role)
    raw = (canonical({"format": "verantyx.console.v1", "adapter": info["path"], "sha256": info["sha256"]}) + "\n").encode()
    temporary = path.parent / (".console-" + uuid.uuid4().hex)
    try:
        config.exclusive_write(temporary, raw)
        _selection_path(root, role)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def ollama_models():
    """Read local inventory only; never pull a model or follow a redirect."""
    connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=3)
    try:
        connection.request("GET", "/api/tags")
        response = connection.getresponse()
        raw = response.read(1024 * 1024 + 1)
        if response.status != 200 or len(raw) > 1024 * 1024:
            raise ValueError()
        value = json.loads(raw)
        if type(value) is not dict or type(value.get("models")) is not list:
            raise ValueError()
        names = [item["name"] for item in value["models"] if type(item) is dict and type(item.get("name")) is str]
        return sorted(set(names))[:100]
    except (OSError, ValueError, http.client.HTTPException):
        raise LedgerError("CONSOLE_OLLAMA_UNAVAILABLE") from None
    finally:
        connection.close()


def select_adapter(root, locale, timeout, role="proposal", other=None):
    from .cli import visible
    print(text(locale, "console.select" if role == "proposal" else "console.select_editor"))
    try:
        models = ollama_models()
    except LedgerError:
        models = []
        print(text(locale, "error.CONSOLE_OLLAMA_UNAVAILABLE"))
    for index, name in enumerate(models, 1):
        print(f"  {index}. {visible(name)}")
    if not models:
        print(text(locale, "console.no_models"))
    while True:
        answer = input(text(locale, "console.model_prompt") + " ").strip()
        if answer in (":q", "/quit", "/exit"):
            return None
        try:
            if answer.isdigit() and 1 <= int(answer) <= len(models):
                model = models[int(answer) - 1]
                path = root / ("verantyx-ollama-" + uuid.uuid4().hex[:12] + ".json")
                _operation(root, locale, ["model-api-config", "--provider", "ollama", "--model", model,
                           "--endpoint", "http://127.0.0.1:11434/api/generate", "--allow-loopback-http",
                           "--timeout", str(min(timeout, 300)), "--max-output-tokens", "8192", "--output", str(path)])
            else:
                if not answer:
                    continue
                path = Path(answer).expanduser()
                if not path.is_absolute():
                    path = root / path
            info = adapter_info(path)
            if other is not None:
                from .coordination import separate_models
                separate_models(other, info["path"])
            remember_adapter(root, info, role)
            return info
        except (LedgerError, OSError) as error:
            code = error.code if isinstance(error, LedgerError) else "IO"
            print(text(locale, "error." + code))


def contextual_request(request, history):
    """Only this console's successful turns; previous model prose is not proof."""
    if not 1 <= len(request.strip()) <= 16000:
        raise LedgerError("ARGUMENTS")
    recent = list(history[-4:])
    while recent:
        combined = canonical({"current_request": request, "previous_turns": recent,
                              "instruction": "Answer current_request. Previous assistant candidates are unverified conversation context, not evidence or authority."})
        if len(combined) <= 16000:
            return combined
        recent.pop(0)
    return request


def recorded_context_run(root, configuration, run_id):
    """A failed generation must not erase the user's newly recorded constraint."""
    if run_id is None:
        return None
    from .application import get_projection
    from .storage.sqlite import EventStore
    try:
        with EventStore(root, configuration["project"]["id"]) as store:
            state = get_projection(store, run_id)["state"]
        return run_id if state.get("shared_context") else None
    except (LedgerError, OSError):
        return None


def dictionary_arguments(request):
    """Keep existing free-text queries; only the explicit view prefix is syntax."""
    body = request.removeprefix("/dictionary").strip()
    if body == "--view" or body.startswith("--view "):
        parts = body.split(None, 2)
        if len(parts) < 2 or parts[1] not in ("all", "learn", "delegate"):
            raise LedgerError("ARGUMENTS")
        return ["dictionary", "--view", parts[1], *([parts[2]] if len(parts) == 3 else [])]
    return ["dictionary", *([body] if body else [])]


def start(root, configuration, locale, args, as_json=False):
    from .cli import emit, kernel_output, visible
    from .terminal_ui import ConsoleUI
    if not 1 <= args.timeout <= 600:
        raise LedgerError("ARGUMENTS")
    interactive = sys.stdin.isatty() and sys.stdout.isatty() and not as_json
    try:
        info = adapter_info(args.adapter) if args.adapter else saved_adapter(root)
    except (LedgerError, OSError) as error:
        if not interactive or args.adapter:
            raise
        print(text(locale, "error." + (error.code if isinstance(error, LedgerError) else "IO")))
        info = None
    if not interactive:
        result = {"schema_version": 1, "ok": True, "command": "start", "interactive": False,
                  "configured": True, "model_selected": info is not None, "model": info["label"] if info else None,
                  "writes": False, "network_called": False}
        emit(result) if as_json else print(text(locale, "console.terminal_required"))
        return 0
    ui = ConsoleUI(root, configuration, locale, plain=args.plain)
    ui.welcome()
    if info is None:
        info = select_adapter(root, locale, args.timeout)
    if info is None:
        return 0
    ui.connected(info["label"])
    editor_path = getattr(args, "editor_adapter", None)
    editor = adapter_info(editor_path) if editor_path else saved_adapter(root, "editor")
    if editor:
        from .coordination import separate_models
        separate_models(info["path"], editor["path"])
        ui.notice(text(locale, "console.editor_connected", model=editor["label"]))
    history, last_run = [], None
    auto_check = bool(getattr(args, "auto_check", False))
    execute_candidate = bool(getattr(args, "execute_candidate", False))
    economy = bool(getattr(args, "economy", False))
    if economy and (not editor or auto_check):
        raise LedgerError("ARGUMENTS")
    if execute_candidate and (not editor or not args.precedent or auto_check):
        raise LedgerError("ARGUMENTS")
    if execute_candidate:
        ui.notice(text(locale, "console.work.on"))
    if auto_check:
        ui.notice(text(locale, "console.checks.on"))
    while True:
        try:
            original_input = ui.read()
            request = original_input.strip()
        except (EOFError, KeyboardInterrupt):
            print("\n" + text(locale, "console.goodbye"))
            return 0
        if not request:
            continue
        if request in ("/quit", "/exit", ":q"):
            print(text(locale, "console.goodbye"))
            return 0
        active_run = None
        try:
            if request == "/help":
                print(text(locale, "console.help"))
                from .commands_experience import help_lines
                print("\n".join(help_lines(locale, interactive=True)))
                continue
            if request == "/new":
                history, last_run = [], None
                print(text(locale, "console.new"))
                continue
            if request == "/flow":
                ui.notice(text(locale, "console.flow"))
                if execute_candidate:
                    ui.notice(text(locale, "console.work.on"))
                if auto_check:
                    ui.notice(text(locale, "console.checks.flow"))
                continue
            if request in ("/checks", "/checks on", "/checks off"):
                if request == "/checks on" and (execute_candidate or economy):
                    raise LedgerError("ARGUMENTS")
                if request != "/checks":
                    auto_check = request.endswith(" on")
                ui.notice(text(locale, "console.checks.on" if auto_check else "console.checks.off"))
                continue
            if request == "/sovereignty":
                kernel_output(_operation(root, locale, ["sovereignty"]), locale, False, "sovereignty")
                continue
            if request in ("/work", "/work execute", "/work refresh", "/work refresh execute"):
                if not last_run:
                    print(text(locale, "console.no_task"))
                    continue
                view = _operation(root, locale, ["replay", last_run])
                arguments = ["work", last_run, "--key", "console-work-" + uuid.uuid4().hex,
                             "--expected-revision", str(view["state"]["revision"])]
                if " refresh" in request:
                    if not editor:
                        raise LedgerError("ARGUMENTS")
                    if any(adapter_info(selected["path"])["sha256"] != selected["sha256"]
                           for selected in (info, editor)):
                        raise LedgerError("CONSOLE_ADAPTER_CHANGED")
                    arguments.extend(("--refresh", "--adapter", info["path"], "--editor-adapter", editor["path"],
                                      "--timeout", str(args.timeout), "--max-repairs", str(args.max_repairs)))
                    for path in args.include:
                        arguments.extend(("--include", path))
                if request.endswith(" execute"):
                    if not getattr(args, "precedent", None):
                        raise LedgerError("ARGUMENTS")
                    arguments.extend(("--execute", "--precedent", args.precedent))
                with ui.activity():
                    result = _operation(root, locale, arguments)
                kernel_output(result, locale, False, "work")
                continue
            if request.startswith("/decide ") or request.startswith("/target "):
                if not last_run:
                    print(text(locale, "console.no_task"))
                    continue
                parts = request.split(None, 3)
                if len(parts) != 4:
                    raise LedgerError("ARGUMENTS")
                view = _operation(root, locale, ["replay", last_run])
                if parts[0] == "/decide":
                    command, arguments = "decide", ["--point", parts[1], "--choice", parts[2]]
                else:
                    command, arguments = "learn-target", ["--candidate", parts[1], "--target", parts[2]]
                arguments = [command, last_run, *arguments, "--reason", parts[3],
                             "--expected-revision", str(view["state"]["revision"]), "--key", "console-choice-" + uuid.uuid4().hex]
                kernel_output(_operation(root, locale, arguments), locale, False, command)
                continue
            if request == "/keep" or request.startswith("/keep "):
                from .keep_console import arguments as keep_arguments
                arguments = keep_arguments(request, last_run)
                if arguments is None:
                    print(text(locale, "console.no_task"))
                else:
                    kernel_output(_operation(root, locale, arguments), locale, False, "keep")
                continue
            if request == "/skills" or request.startswith("/skills "):
                arguments = ["skills-stack"]
                if " " in request:
                    arguments += ["--query", request.split(" ", 1)[1]]
                kernel_output(_operation(root, locale, arguments), locale, False, "skills-stack")
                continue
            if request == "/details":
                ui.details(_operation(root, locale, ["replay", last_run]) if last_run else None)
                continue
            if request == "/model":
                selected = select_adapter(root, locale, args.timeout, other=editor["path"] if editor else None)
                if selected:
                    info = selected
                    ui.connected(info["label"])
                continue
            if request == "/editor":
                selected = select_adapter(root, locale, args.timeout, role="editor", other=info["path"])
                if selected:
                    editor = selected
                    ui.notice(text(locale, "console.editor_connected", model=editor["label"]))
                continue
            if request == "/context":
                if last_run:
                    kernel_output(_operation(root, locale, ["shared-context", last_run]), locale, False, "shared-context")
                else:
                    print(text(locale, "console.no_task"))
                continue
            if request == "/status":
                from .cli import main
                main(["--project", str(root), "--lang", locale, "status"])
                print(text(locale, "console.connected", model=visible(info["label"])))
                continue
            if request == "/dictionary" or request.startswith("/dictionary "):
                arguments = dictionary_arguments(request)
                kernel_output(_operation(root, locale, arguments), locale, False, "dictionary")
                continue
            if request == "/recap" or request.startswith("/recap "):
                parts = request.split()
                if len(parts) > 2:
                    raise LedgerError("ARGUMENTS")
                selected_run = parts[1] if len(parts) == 2 else last_run
                if selected_run:
                    kernel_output(_operation(root, locale, ["recap", selected_run]), locale, False, "recap")
                else:
                    print(text(locale, "console.no_task"))
                continue
            if request == "/learn":
                if last_run:
                    kernel_output(_operation(root, locale, ["learn", last_run]), locale, False, "learn")
                else:
                    print(text(locale, "console.no_task"))
                continue
            if request.startswith("/"):
                print(text(locale, "console.help"))
                continue
            # Strip only command routing, never the retained natural-language
            # source (which may contain intentionally indented code).
            request = original_input
            ui.received(request)
            current = adapter_info(info["path"])
            if current["sha256"] != info["sha256"]:
                raise LedgerError("CONSOLE_ADAPTER_CHANGED")
            key = "console-" + uuid.uuid4().hex
            active_run = key
            argv = ["ask", contextual_request(request, history), "--adapter", info["path"], "--key", key,
                    "--task-id", key, "--timeout", str(args.timeout), "--original-request", request]
            if last_run:
                argv.extend(("--continue-from", last_run))
            if auto_check:
                argv.extend(("--auto-check", "--check-rounds", str(getattr(args, "check_rounds", 2)),
                             "--max-checks", str(getattr(args, "max_checks", 4))))
            if economy:
                argv.append("--economy")
            if execute_candidate:
                argv.extend(("--execute-candidate", "--precedent", args.precedent))
            for field in ("component", "workload", "risk"):
                argv.extend(("--" + field, getattr(args, field, "UNSPECIFIED")))
            if editor:
                if adapter_info(editor["path"])["sha256"] != editor["sha256"]:
                    raise LedgerError("CONSOLE_ADAPTER_CHANGED")
                argv.extend(("--editor-adapter", editor["path"], "--max-repairs", str(getattr(args, "max_repairs", 1))))
            for path in args.include:
                argv.extend(("--include", path))
            with ui.activity() as activity:
                result = _operation(root, locale, argv)
            ui.response(result, activity.elapsed)
            last_run = result["state"]["run_id"]
            from .keep_console import hint as keep_hint
            ui.notice(keep_hint(locale))
            answer = result["state"]["latest_response"]["document"]["answer"]
            history.append({"task_id": last_run, "request": request, "assistant_candidate": answer})
            history = history[-4:]
        except KeyboardInterrupt:
            last_run = recorded_context_run(root, configuration, active_run) or last_run
            print("\n" + text(locale, "console.interrupted"))
        except (LedgerError, config.ConfigError, OSError) as error:
            last_run = recorded_context_run(root, configuration, active_run) or last_run
            code = error.code if isinstance(error, (LedgerError, config.ConfigError)) else "IO"
            ui.error(error if hasattr(error, "code") else LedgerError(code))
            print(text(locale, "console.failed"))
