"""Replaceable Work proposal producers; authority and receipts stay with the host.

An external process is trusted code with the current OS user's privileges.
This is a protocol boundary, NOT a sandbox for an autonomous external agent.
"""
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import hashlib
import os
import stat
import uuid

from .adapters.command_process import load_command
from .adapters.invocation_journal import InvocationJournal
from .agent_models import identity, invoke, invoke_prepared, selected_work
from .authority import require_current_approval_valid
from .domain.codec import canonical, decode
from .errors import LedgerError

CONFIG = ".verantyx/work-harness.json"
FORMAT = "verantyx.work-harness.v1"
DEFAULT = {"format": FORMAT, "mode": "builtin", "label": "Cleanroom",
           "adapter": None, "adapter_sha256": None, "trusted_process": False}


def _read(root, relative, *, optional=False):
    parts = Path(relative).parts
    parent = os.open(Path(root).resolve(), os.O_RDONLY | os.O_DIRECTORY)
    try:
        try:
            for part in parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                os.close(parent)
                parent = child
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        except FileNotFoundError:
            if optional:
                return None
            raise
    finally:
        os.close(parent)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536:
            raise LedgerError("HARNESS_CONFIG")
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise LedgerError("HARNESS_CONFIG")
    return raw


def _relative(root, adapter):
    path = Path(adapter).expanduser()
    if path.is_absolute():
        try:
            path = path.relative_to(Path(root).resolve())
        except ValueError:
            raise LedgerError("PATH_SCOPE") from None
    if (path.parts[:2] != (".verantyx", "model-adapters") or ".." in path.parts
            or path.suffix != ".json"):
        raise LedgerError("PATH_SCOPE")
    return path.as_posix()


def saved(root):
    raw = _read(root, CONFIG, optional=True)
    value = decode(raw, 65536) if raw is not None else deepcopy(DEFAULT)
    if (type(value) is not dict or set(value) != set(DEFAULT) or value["format"] != FORMAT
            or value["mode"] not in ("builtin", "process")
            or type(value["label"]) is not str or not 1 <= len(value["label"]) <= 120):
        raise LedgerError("HARNESS_CONFIG")
    if value["mode"] == "builtin":
        if value["adapter"] is not None or value["adapter_sha256"] is not None or value["trusted_process"] is not False:
            raise LedgerError("HARNESS_CONFIG")
    else:
        if (type(value["adapter"]) is not str or value["adapter"] != _relative(root, value["adapter"])
                or type(value["adapter_sha256"]) is not str or len(value["adapter_sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in value["adapter_sha256"])
                or value["trusted_process"] is not True):
            raise LedgerError("HARNESS_CONFIG")
    return value, hashlib.sha256(raw).hexdigest() if raw is not None else None


def snapshot(root):
    value, fingerprint = saved(root)
    from .sandbox_backends import snapshot as sandbox_snapshot
    return {**value, "config_sha256": fingerprint, "sandbox": sandbox_snapshot(root), "transport": "JSON_STDIN_STDOUT",
            "external_process_started": False, "connection_checked": False,
            "OS_sandbox": False, "native_external_tools_observed": False,
            "reflection": "Configured Reflection AI; same means configured Work model, not the external process"}


def _prepare_external(root, relative, expected=None):
    raw = _read(root, relative)
    fingerprint = hashlib.sha256(raw).hexdigest()
    if expected is not None and fingerprint != expected:
        raise LedgerError("HARNESS_ADAPTER_CHANGED")
    value = decode(raw, 65536)
    # Existing generic command adapters, not vendor-native tool/handoff modes.
    if type(value) is not dict or "argv" not in value or set(value) - {"argv", "cwd", "env", "inherit_env"}:
        raise LedgerError("HARNESS_PROTOCOL", {"reason": "GENERIC_JSON_COMMAND_ADAPTER_REQUIRED"})
    command = load_command(Path(root) / relative)
    if _read(root, relative) != raw:
        raise LedgerError("HARNESS_ADAPTER_CHANGED")
    model = {"provider": "external_work_harness", "model": "adapter_declared_runtime_unknown",
             "adapter_sha256": fingerprint}
    return model, command


class WorkHarness(Protocol):
    adapter: str
    model: dict
    descriptor: dict
    external: bool

    def propose(self, root, request, *, key, timeout=None): ...


@dataclass(frozen=True)
class SelectedHarness:
    adapter: str
    model: dict
    descriptor: dict
    external: bool = False
    command: dict | None = None

    def propose(self, root, request, *, key, timeout=None):
        if not self.external:
            return invoke(root, self.adapter, request, key=key, timeout=timeout)
        # Execute the captured command, not a new adapter read between turns.
        return invoke_prepared(root, self.model, self.command, request, key=key, timeout=timeout)


def select(root, configuration, *, explicit_adapter=None):
    value, fingerprint = saved(root) if explicit_adapter is None else (deepcopy(DEFAULT), None)
    from .sandbox_backends import saved as saved_sandbox, wrap as wrap_sandbox
    sandbox_config, _ = saved_sandbox(root)
    if value["mode"] == "builtin":
        if sandbox_config["mode"] != "off":
            raise LedgerError("SANDBOX_REQUIRES_EXTERNAL_WORK_HARNESS")
        adapter = str(explicit_adapter or selected_work(root, configuration))
        model = identity(adapter)
        return SelectedHarness(adapter, model, {"kind": "builtin", "label": "Cleanroom",
            "authority": "HOST_TOOLS_ONLY", "adapter_sha256": model["adapter_sha256"]})
    relative = value["adapter"]
    model, command = _prepare_external(root, relative, value["adapter_sha256"])
    command, sandbox_descriptor = wrap_sandbox(root, command)
    return SelectedHarness(str(Path(root) / relative), model,
        {"kind": "external_process", "label": value["label"], "config_sha256": fingerprint,
         "adapter": relative, "adapter_sha256": model["adapter_sha256"],
         "authority": "TRUSTED_PROPOSAL_PROCESS_EXTERNAL_EFFECTS_UNOBSERVED",
         "sandbox": sandbox_descriptor}, True, command)


def configure(root, configuration, *, mode, adapter=None, label="External Work harness",
              trust_process=False, expected=None):
    if configuration is None or mode not in ("builtin", "process"):
        raise LedgerError("ARGUMENTS")
    value = deepcopy(DEFAULT)
    if mode == "process":
        if trust_process is not True or type(label) is not str or not 1 <= len(label) <= 120 or not adapter:
            raise LedgerError("HARNESS_TRUST_REQUIRED")
        relative = _relative(root, adapter)
        model, _ = _prepare_external(root, relative)
        value = {"format": FORMAT, "mode": mode, "label": label, "adapter": relative,
                 "adapter_sha256": model["adapter_sha256"], "trusted_process": True}
    with InvocationJournal(root, "work-harness-settings", "configuration"):
        _, current = saved(root)
        if current != expected:
            raise LedgerError("CONFIG_CHANGED")
        require_current_approval_valid()
        parent = os.open(Path(root).resolve(), os.O_RDONLY | os.O_DIRECTORY)
        try:
            child = os.open(".verantyx", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        finally:
            os.close(parent)
        temp = ".work-harness-" + uuid.uuid4().hex
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=child)
            with os.fdopen(fd, "wb") as stream:
                stream.write((canonical(value) + "\n").encode())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, "work-harness.json", src_dir_fd=child, dst_dir_fd=child)
            os.fsync(child)
        finally:
            try:
                os.unlink(temp, dir_fd=child)
            except FileNotFoundError:
                pass
            os.close(child)
    return {"ok": True, "saved": value, "process_started": False, "host_tool_permissions_changed": False}


def menu(root, configuration):
    from . import development_console as ui
    from .personal_console import line
    current, fingerprint = saved(root)
    line("\nWORK HARNESS / " + current["label"])
    line("The built-in loop is enough for normal use. An external harness is optional.")
    line("Work proposals, actual host tool receipts and personal skill progress remain separate.")
    mode = ui._pick("Work runtime", ["builtin", "process"],
                    lambda v: "Built-in / Cleanroomの軽い作業ループ" if v == "builtin"
                    else "External proposal process / 信頼する外部アダプター")
    if mode is None:
        return
    kwargs = {"mode": mode, "expected": fingerprint}
    if mode == "process":
        line("Only compatible JSON proposal adapters are supported, not an arbitrary interactive agent CLI.")
        line("Without an external sandbox backend this process uses your OS privileges. Configured isolation is not attested.")
        line("Native operations inside it are NOT visible as verified Cleanroom tool receipts.")
        line("The Reflection AI remains the model chosen in Models & organization.")
        adapter = ui._ask("Existing adapter under .verantyx/model-adapters / 空欄で戻る")
        if not adapter:
            return
        label = ui._ask("Display name", "External Work harness")
        if ui._pick("Trust this local executable and select it?", [False, True],
                    lambda v: "Trust and select / 信頼して接続する" if v else "Cancel / 変更しない") is not True:
            return
        kwargs.update(adapter=adapter, label=label, trust_process=True)
    elif not ui._start("Use the built-in harness?"):
        return
    result = ui._mutate(root, configuration, configure, **kwargs)
    line("Saved. No process was started and no connection test was performed.")
    return result
