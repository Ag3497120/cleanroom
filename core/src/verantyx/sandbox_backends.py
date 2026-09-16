"""A trusted OSS launcher boundary; Cleanroom does not implement OS isolation.

The selected launcher owns namespaces/VMs, filesystem policy and networking.
A configured prefix is not proof that those controls were enforced.
"""
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import hashlib
import os
import uuid

from .adapters.command_process import SHELLS
from .adapters.invocation_journal import InvocationJournal
from .authority import require_current_approval_valid
from .domain.codec import canonical, decode, digest
from .errors import LedgerError

CONFIG = ".verantyx/sandbox.json"
DEFAULT = {"format": "verantyx.sandbox.v1", "mode": "off", "label": "No external sandbox",
           "argv_prefix": [], "requested_policy": {"source": "read-only", "network": "deny"},
           "trusted_launcher": False}


def validate(value):
    if (type(value) is not dict or set(value) != set(DEFAULT) or value["format"] != DEFAULT["format"]
            or value["mode"] not in ("off", "command") or type(value["label"]) is not str
            or not 1 <= len(value["label"]) <= 120
            or value["requested_policy"] not in (
                {"source": "read-only", "network": "deny"},
                {"source": "read-only", "network": "launcher-managed"})):
        raise LedgerError("SANDBOX_CONFIG")
    args = value["argv_prefix"]
    if value["mode"] == "off":
        if args != [] or value["trusted_launcher"] is not False:
            raise LedgerError("SANDBOX_CONFIG")
    else:
        if (value["trusted_launcher"] is not True or type(args) is not list or not 1 <= len(args) <= 100
                or any(type(arg) is not str or not arg or len(arg) > 8192 or "\x00" in arg for arg in args)
                or not Path(args[0]).is_absolute() or Path(args[0]).name.lower() in SHELLS):
            raise LedgerError("SANDBOX_CONFIG")
        if "{" in args[0] or "}" in args[0]:
            raise LedgerError("SANDBOX_CONFIG")
    return deepcopy(value)


def saved(root):
    from .work_harness import _read
    raw = _read(root, CONFIG, optional=True)
    value = validate(decode(raw, 65536)) if raw is not None else deepcopy(DEFAULT)
    return value, hashlib.sha256(raw).hexdigest() if raw is not None else None


def snapshot(root):
    value, fingerprint = saved(root)
    return {**value, "config_sha256": fingerprint, "process_started": False,
            "isolation_verified": False, "enforcement": "EXTERNAL_LAUNCHER_RESPONSIBILITY",
            "scope": "EXTERNAL_WORK_PROPOSAL_PROCESS_ONLY",
            "model_api_and_reflection_covered": False, "host_tools_covered": False}


class SandboxBackend(Protocol):
    def prepare(self, command: dict, project: Path) -> tuple[dict, dict]: ...


@dataclass(frozen=True)
class CommandSandboxBackend:
    configuration: dict
    config_sha256: str | None

    def prepare(self, command, project):
        value = validate(self.configuration)
        project = Path(project).resolve()
        prefix = [arg.replace("{project}", str(project)).replace(
            "{candidate_root}", str(project / ".verantyx/workspaces")).replace(
            "{workspace_root}", str(project / ".verantyx/workspaces")).replace(
            "{candidate_store}", str(project / ".verantyx/work-candidates")) for arg in value["argv_prefix"]]
        if not os.access(prefix[0], os.X_OK) or not Path(prefix[0]).is_file():
            raise LedgerError("SANDBOX_LAUNCHER_UNAVAILABLE")
        wrapped = deepcopy(command)
        wrapped["argv"] = [*prefix, *command["argv"]]
        wrapped["identity"] = digest({"child": command["identity"], "sandbox": self.config_sha256,
                                     "argv": wrapped["argv"]})
        descriptor = {"kind": "external_launcher", "label": value["label"],
                      "config_sha256": self.config_sha256, "requested_policy": value["requested_policy"],
                      "isolation_verified": False, "status": "REQUESTED_NOT_ATTESTED",
                      "fallback_to_unsandboxed": False}
        return wrapped, descriptor


def wrap(root, command):
    value, fingerprint = saved(root)
    if value["mode"] == "off":
        return command, {"status": "OFF", "isolation_verified": False}
    return CommandSandboxBackend(value, fingerprint).prepare(command, Path(root))


def configure(root, configuration, *, value, trusted=False, expected=None):
    if configuration is None or (value.get("mode") == "command" and not trusted):
        raise LedgerError("SANDBOX_TRUST_REQUIRED")
    value = validate(value)
    with InvocationJournal(root, "sandbox-settings", "configuration"):
        _, current = saved(root)
        if current != expected:
            raise LedgerError("CONFIG_CHANGED")
        require_current_approval_valid()
        parent = os.open(Path(root).resolve(), os.O_RDONLY | os.O_DIRECTORY)
        try:
            directory = os.open(".verantyx", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        finally:
            os.close(parent)
        temporary = ".sandbox-" + uuid.uuid4().hex
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(fd, "wb") as stream:
                stream.write((canonical(value) + "\n").encode())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, "sandbox.json", src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
            os.close(directory)
    return {"ok": True, "saved": value, "isolation_verified": False, "process_started": False}


def menu(root, configuration):
    from . import development_console as ui
    from .skill_console import line
    from .adapters.observations import read_document
    current, fingerprint = saved(root)
    line("\nSANDBOX BACKEND / " + current["label"])
    line("Optional OSS launcher for external Work JSON processes. No engine is bundled.")
    line("The launcher, not Cleanroom, must enforce filesystem, network and process isolation.")
    line("Configured does not mean verified. Native effects still remain UNKNOWN.")
    action = ui._pick("Backend", ["off", "command"], lambda name:
                      "Off / no external launcher" if name == "off" else "Connect a trusted launcher configuration")
    if action is None:
        return
    if action == "off":
        value = deepcopy(DEFAULT)
    else:
        path = ui._ask("Existing sandbox JSON configuration / 空欄で戻る")
        if not path:
            return
        value = validate(decode(read_document(path, 65536), 65536))
        if value["mode"] != "command":
            raise LedgerError("SANDBOX_CONFIG")
        line(canonical(value))
        line("Only the external Work harness is wrapped. Reflection, search adapters and host tools are separate.")
    if not ui._start("Save this explicit launcher choice?"):
        return
    result = ui._mutate(root, configuration, configure, value=value, trusted=action == "command", expected=fingerprint)
    line("Saved. The launcher was not started; isolation has not been verified.")
    return result
