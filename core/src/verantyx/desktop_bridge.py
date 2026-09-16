"""Local, one-request JSON transport for the optional macOS UI.

The installed CLI remains the application. This module does not classify work,
select models, grant capabilities, activate rules, or certify understanding.
Never expose this human-facing transport as an unauthenticated network service.
"""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import re
import signal
import sys

from . import __version__
from .errors import LedgerError

PROTOCOL = "cleanroom.desktop.v1"
MAX_INPUT = 256 * 1024
MAX_OUTPUT = 8 * 1024 * 1024
ACTIONS = ("hello", "snapshot", "initialize", "work", "organize", "memo")


def _string(value, field, limit=12000, optional=False):
    if optional and value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\0" in value:
        raise LedgerError("DESKTOP_ARGUMENT", {"field": field})
    return value


def _strings(value, field, maximum):
    if not isinstance(value, list) or len(value) > maximum:
        raise LedgerError("DESKTOP_ARGUMENT", {"field": field})
    return [_string(item, field, 4096) for item in value]


def _root(request):
    value = _string(request.get("project"), "project", 4096)
    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise LedgerError("DESKTOP_PROJECT_MISSING")
    return root


def _configuration(root):
    from . import config
    return config.load(root)[0]


def _read(root, selected=None):
    from .cleanroom_view import Reader
    configuration = _configuration(root)
    if configuration is None:
        return None, None
    reader = Reader(root, configuration)
    try:
        return configuration, reader.read(selected=selected)
    finally:
        reader.close()


def _items(view):
    # Selection IDs include their recorded revision. A stale selection is not
    # silently rebound to a newer note or to similarly worded AI output.
    from .cleanroom_owner import make_item
    result = list(view.get("owner_items", []))
    for card in view.get("owner_experience_cards", []):
        result.append(make_item(
            "learning", card["kind"] + ": " + card["text"], {
                key: card[key] for key in ("kind", "text", "reason", "target",
                                          "target_is_suggestion", "human_understanding",
                                          "status", "reference") if key in card
            }, source_ref=card.get("reference"), run_id=view.get("run_id"),
            revision=view.get("revision")))
    return list({item["id"]: item for item in result}.values())


def snapshot(root, selected=None):
    from .cleanroom_view import public_view
    configuration, view = _read(root, selected)
    if configuration is None:
        return {"configured": False, "project_name": root.name, "purpose": "",
                "works": [], "items": [], "panes": {}, "run_id": None,
                "writes": False, "model_calls": 0}
    # Export a projection, not the reducer state or any authorization object.
    projection = view.get("ownership_projection") or {}
    works = [{
        key: work.get(key) for key in ("run_id", "label", "status",
                                      "reflection_status", "artifact_directory",
                                      "last_recorded_at")
    } for work in view.get("works", [])[:50]]
    return {
        **public_view(view), "configured": True,
        "project_name": configuration["project"]["name"],
        "purpose": configuration["project"].get("purpose", ""),
        "works": works, "items": _items(view),
        "work_status": projection.get("work_status"),
        "reflection_status": projection.get("reflection_status"),
        "owner_question": projection.get("owner_question", ""),
        "candidate_directory": next((row.get("artifact_directory") for row in works
                                     if row["run_id"] == view.get("run_id")), None),
    }


class _LimitedOutput(io.StringIO):
    def write(self, text):
        if self.tell() + len(text) > MAX_OUTPUT:
            raise LedgerError("DESKTOP_OUTPUT_LIMIT")
        return super().write(text)


def _cli(root, arguments):
    # Invoke the same entry point, including its authority gate. Prompts travel
    # over stdin to this process rather than being exposed as process arguments.
    from .cli import main
    output, errors = _LimitedOutput(), _LimitedOutput()
    with redirect_stdout(output), redirect_stderr(errors):
        code = main(["--project", str(root), "--json", "--plain", *arguments])
    try:
        value = json.loads(output.getvalue())
    except (ValueError, TypeError):
        # Do not turn a broken transport into a fabricated failed WorkResult.
        # The recorded work remains available through snapshot/the regular CLI.
        raise LedgerError("DESKTOP_CLI_OUTPUT_INVALID", {"cli_exit_code": code}) from None
    if not isinstance(value, dict):
        raise LedgerError("DESKTOP_CLI_OUTPUT_INVALID")
    return code, value


def dispatch(request):
    if not isinstance(request, dict) or request.get("protocol") != PROTOCOL:
        raise LedgerError("DESKTOP_PROTOCOL")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not re.fullmatch(r"[a-f0-9]{32}", request_id):
        raise LedgerError("DESKTOP_REQUEST_ID")
    action = request.get("action")
    if action not in ACTIONS:
        raise LedgerError("DESKTOP_ACTION")
    if action == "hello":
        return 0, {"cli_version": __version__, "actions": list(ACTIONS),
                   "transport": "local-stdio", "rules_activated": 0,
                   "work_runtime": "installed-cli", "ownership_runtime": "installed-cli"}

    root = _root(request)
    selected = _string(request.get("run_id"), "run_id", 200, optional=True)
    if action == "snapshot":
        return 0, snapshot(root, selected)
    if action == "initialize":
        # Initialization is a separate human UI action, never a side effect of
        # opening a project, polling a pane, or taking a snapshot.
        if _configuration(root) is not None:
            return 0, {"ok": True, "already_configured": True}
        return _cli(root, ["setup", "--non-interactive"])
    if action == "memo":
        from .cleanroom_owner import save_note
        if _configuration(root) is None:
            raise LedgerError("NOT_CONFIGURED")
        if selected:
            _, view = _read(root, selected)
            if view.get("state") is None:
                raise LedgerError("RUN_NOT_FOUND")
        note = save_note(root, _string(request.get("text"), "text", 4000),
                         key=request_id, run_id=selected)
        return 0, {"ok": True, "note": note, "shared_with_ai": False,
                   "authority": "REFERENCE_ONLY"}

    if request.get("send_confirmed") is not True:
        raise LedgerError("DESKTOP_SEND_CONFIRMATION_REQUIRED")
    if action == "organize":
        selected = _string(selected, "run_id", 200)
        return _cli(root, ["organize", selected, "--key", request_id])
    prompt = _string(request.get("text"), "text")
    include = _strings(request.get("include", []), "include", 64)
    references = _strings(request.get("reference_ids", []), "reference_ids", 8)
    if references:
        from .cleanroom_owner import expand_request
        _, view = _read(root, selected)
        if view is None:
            raise LedgerError("NOT_CONFIGURED")
        available = {item["id"]: item for item in _items(view)}
        if any(identity not in available for identity in references):
            raise LedgerError("DESKTOP_REFERENCE_STALE")
        prompt = expand_request(prompt, [available[identity] for identity in references])
    arguments = ["develop", "--key", request_id]
    if selected:
        arguments += ["--continue-from", selected]
    for path in include:
        arguments += ["--include", path]
    # A request beginning with '-' must remain prose, not become an option.
    return _cli(root, [*arguments, "--", prompt])


def _interrupt(_signum, _frame):
    # Propagate a human stop request only to descendants of this invocation.
    # Do not kill a port owner, an unrelated CLI, or any other IDE process.
    import psutil
    try:
        children = psutil.Process().children(recursive=True)
    except psutil.Error:
        children = []
    for child in children:
        try:
            child.send_signal(signal.SIGINT)
        except psutil.Error:
            pass
    raise KeyboardInterrupt


def serve():
    request_id = None
    prior_handler = signal.signal(signal.SIGINT, _interrupt)
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise LedgerError("DESKTOP_INPUT_LIMIT")
        request = json.loads(raw)
        request_id = request.get("request_id") if isinstance(request, dict) else None
        code, result = dispatch(request)
        response = {"protocol": PROTOCOL, "request_id": request_id,
                    "transport_ok": True, "cli_exit_code": code, "result": result}
    except (KeyboardInterrupt, EOFError):
        code = 130
        response = {"protocol": PROTOCOL, "request_id": request_id,
                    "transport_ok": False, "cli_exit_code": code,
                    "error": {"code": "CANCELLED",
                              "message": "Stop requested. Recorded work is retained; inspect its current state."}}
    except Exception as error:
        code = 2
        response = {"protocol": PROTOCOL, "request_id": request_id,
                    "transport_ok": False, "cli_exit_code": code,
                    "error": {"code": getattr(error, "code", "DESKTOP_REQUEST_FAILED"),
                              "message": "The desktop request could not complete. The CLI ledger is retained."}}
    finally:
        signal.signal(signal.SIGINT, prior_handler)
    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    raise SystemExit(serve())

