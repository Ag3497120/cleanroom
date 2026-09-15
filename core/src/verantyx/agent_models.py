"""Independent work/reflection connections using the existing bounded adapters."""
from copy import deepcopy
from pathlib import Path
import hashlib
import os
import uuid

from . import config as project_config
from .adapters.command_process import load_command, BoundedProcess
from .adapters.invocation_journal import InvocationJournal
from .adapters.observations import read_document
from .agent_schema import validate_output
from .authority import require_current_approval_valid
from .domain.codec import canonical, decode, digest
from .errors import LedgerError


def reflection_setting(configuration):
    return deepcopy(configuration.get("runtime", {}).get(
        "reflection", {"mode": "same", "adapter": None, "label": "Same as Work AI"}))


def validate_setting(value):
    if (type(value) is not dict or set(value) != {"mode", "adapter", "label"}
            or value["mode"] not in ("same", "custom", "off")
            or type(value["label"]) is not str or not 1 <= len(value["label"]) <= 240):
        raise ValueError("REFLECTION_SETTING")
    if value["mode"] == "custom":
        path = value["adapter"]
        if (type(path) is not str or Path(path).is_absolute() or ".." in Path(path).parts
                or not path.startswith(".verantyx/model-adapters/") or not path.endswith(".json")):
            raise ValueError("REFLECTION_ADAPTER")
    elif value["adapter"] is not None:
        raise ValueError("REFLECTION_ADAPTER")


def select_reflection(root, configuration, mode="same", adapter=None, label=None):
    project = Path(root).resolve()
    relative = None
    if mode == "custom":
        chosen = Path(adapter).expanduser()
        chosen = chosen if chosen.is_absolute() else project / chosen
        if chosen.is_symlink() or not chosen.resolve().is_relative_to(project / ".verantyx/model-adapters"):
            raise LedgerError("PATH_SCOPE")
        relative = chosen.resolve().relative_to(project).as_posix()
        load_command(chosen)
    value = {"mode": mode, "adapter": relative,
             "label": label or {"same": "Same as Work AI", "custom": "Separate Reflection AI", "off": "Off"}[mode]}
    validate_setting(value)
    current, expected = project_config.load(project)
    if current is None or current["project"]["id"] != configuration["project"]["id"]:
        raise LedgerError("CONFIG_CHANGED")
    updated = deepcopy(current)
    updated["runtime"]["reflection"] = value
    project_config.save(project, updated, expected)
    configuration.clear()
    configuration.update(updated)
    return {"ok": True, "reflection": value}


def selected_work(root, configuration):
    selection = configuration.get("runtime", {}).get("model_selection")
    if selection is None:
        from .model_settings import activate_codex
        activate_codex(root, configuration)
        selection = configuration["runtime"]["model_selection"]
    # The old reviewer is deliberately NOT required or loaded here.
    path = Path(root) / selection["creator_adapter"]
    base = Path(root).resolve() / ".verantyx/model-adapters"
    if path.is_symlink() or not path.resolve().is_relative_to(base) or not path.is_file():
        raise LedgerError("MODEL_SETTINGS", {"reason": "WORK_ADAPTER_UNAVAILABLE"})
    return str(path.resolve())


def selected_reflection(root, configuration, work_adapter):
    selected = reflection_setting(configuration)
    validate_setting(selected)
    if selected["mode"] == "off":
        return None
    if selected["mode"] == "same":
        return work_adapter
    path = Path(root) / selected["adapter"]
    if path.is_symlink() or not path.resolve().is_relative_to(Path(root).resolve() / ".verantyx/model-adapters"):
        raise LedgerError("PATH_SCOPE")
    return str(path.resolve())


def identity(adapter):
    raw = read_document(adapter, 65536)
    value = decode(raw, 65536)
    return {"provider": value.get("provider", "codex_subscription" if value.get("format") == "verantyx.codex-cli.v1" else "explicit_adapter"),
            "model": value.get("model", "configured_executable"),
            "adapter_sha256": hashlib.sha256(raw).hexdigest()}


def invoke(root, adapter, request, *, key, timeout=120):
    model = identity(adapter)
    command = load_command(adapter)
    intent = digest({"request": request, "model": model, "executor": command["identity"], "timeout": timeout})
    with InvocationJournal(root, "agent-model-call", key) as journal:
        prior = journal.read("intent")
        if prior is not None and prior != intent:
            raise LedgerError("IDEMPOTENCY_CONFLICT")
        if prior is None:
            journal.write("intent", intent)
        response = journal.read("response")
        if response is not None:
            return {"document": validate_output(request, response), "model": model}
        failure = journal.read("failure")
        if failure is not None:
            raise LedgerError(failure["code"])
        if journal.read("started") is not None:
            raise LedgerError("MODEL_OUTCOME_UNKNOWN")
        require_current_approval_valid()
        journal.write("started", {"request_sha256": digest(request), "model": model})
        try:
            with BoundedProcess(command, timeout=timeout, max_output=524288) as process:
                raw = process.document(request)
            document = decode(raw, 262144)
            # Retain a rejected model response for diagnosis without promoting it.
            journal.write("response", document)
            return {"document": validate_output(request, document), "model": model}
        except (LedgerError, OSError) as error:
            journal.write("failure", {"code": getattr(error, "code", "MODEL_CALL_FAILED")})
            raise


def create_api_profile(root, *, provider, model, endpoint, key_env=None, allow_loopback_http=False):
    from .model_api import validate_config
    from .model_settings import _profile
    value = validate_config({
        "format": "verantyx.model-api.v1", "provider": provider, "model": model,
        "endpoint": endpoint, "key_env": key_env, "allow_loopback_http": allow_loopback_http,
        "timeout": 120, "max_output_tokens": 8192, "max_response_bytes": 262144,
    })
    directory = _profile(root, "connection")
    for name in ("implementation.json", "verification.json"):
        path = directory / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(canonical(value) + "\n")
    return directory


def activate_work_api(root, configuration, **kwargs):
    from .model_settings import _selection, _save_selection
    directory = create_api_profile(root, **kwargs)
    selection = _selection("model_api", kwargs["provider"] + " / " + kwargs["model"],
                           directory / "implementation.json", directory / "verification.json", root)
    return _save_selection(root, configuration, selection)
