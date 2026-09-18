"""Private, serialized native conversations, scoped to one host Work run.

Only hashes and native session IDs are retained here. The host ledger owns
the request/output history. Interrupted conversations are never resumed.
"""
from contextlib import AbstractContextManager
from pathlib import Path
import fcntl
import os
import tempfile
import time
import uuid

from .adapters.observations import read_document
from .domain.codec import canonical, decode, digest
from .errors import LedgerError
from .prompt_cache import text

STATE_ENV = "VERANTYX_TRANSPORT_DIR"
ARRAYS = ("turns", "tool_receipts", "owner_instructions")
RESET_KEYS = ("format", "request", "output_contract", "response_locale", "approved_files",
              "approved_assets", "attachments", "project_context", "personal_context", "tool_capabilities", "model_roles")


def transport_directory(path):
    return str(Path(path).resolve().parent / ".transport")


def private_directory(path):
    path = Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise LedgerError("PATH_SCOPE")
    if not path.parent.exists():
        private_directory(path.parent)
    path.mkdir(mode=0o700, exist_ok=True)
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise LedgerError("PATH_SCOPE")
    return path


def snapshot(value):
    return {"fields": {key: digest(item) for key, item in value.items()},
            "arrays": {key: [digest(row) for row in value[key]] for key in ARRAYS
                       if isinstance(value.get(key), list)}}


def patch(previous, value):
    current = snapshot(value)
    if not set(previous["fields"]) <= set(current["fields"]):
        return None
    if any(previous["fields"].get(key) != current["fields"].get(key) for key in RESET_KEYS):
        return None
    appended, replaced = {}, {}
    for key, item in value.items():
        if key in current["arrays"] and key in previous["arrays"]:
            old, new = previous["arrays"][key], current["arrays"][key]
            if new[:len(old)] != old:
                return None  # Compaction or rewritten history starts a fresh context.
            if len(new) > len(old):
                appended[key] = item[len(old):]
        elif previous["fields"].get(key) != current["fields"].get(key):
            replaced[key] = item
    return {"replace": replaced, "append": appended}


class NativeSession(AbstractContextManager):
    def __init__(self, config, value, schema, instructions=""):
        self.config, self.value, self.schema = config, value, schema
        self.instructions = instructions
        self.thread_id = self.resume_id = None
        self.lock = self.temporary = self.path = None
        self.delta = None
        self.persistent = bool(os.environ.get(STATE_ENV))

    def __enter__(self):
        if not self.persistent:
            self.temporary = tempfile.TemporaryDirectory(prefix="cleanroom-native-")
            self.directory = Path(self.temporary.name)
            self.cwd = self.directory / "empty"
            self.cwd.mkdir()
            return self
        identity = {key: self.config.get(key) for key in
                    ("provider", "model", "role", "executable", "reasoning_effort", "context_window")}
        identity.update(transport_version=1, instructions=digest(self.instructions))
        self.directory = private_directory(Path(os.environ[STATE_ENV]) / "native" / digest(identity)[:24])
        # Keep parent-project AGENTS.md/CLAUDE.md out of the native context.
        isolated = Path(tempfile.gettempdir()).resolve() / ("cleanroom-native-" + str(os.getuid()))
        self.cwd = private_directory(isolated / digest(str(self.directory))[:32] / "empty")
        if self.value.get("format") != "verantyx.work-agent-request.v1" or not self.value.get("run_id"):
            return self
        self.path = self.directory / (digest({"run": self.value["run_id"]}) + ".json")
        descriptor = os.open(str(self.path) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        self.lock = os.fdopen(descriptor, "a")
        deadline = time.monotonic() + min(10, self.config["timeout"])
        try:
            while True:
                try:
                    fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise LedgerError("BRIDGE_TIMEOUT")
                    time.sleep(.02)
            if self.path.exists():
                previous = decode(read_document(self.path, 2 * 1024 * 1024), 2 * 1024 * 1024)
                if previous.get("status") == "SUCCEEDED" and previous.get("schema") == digest(self.schema):
                    delta = patch(previous["snapshot"], self.value)
                    if delta is not None:
                        self.resume_id = str(uuid.UUID(previous["thread_id"]))
                        self.delta = delta
            self._save({"status": "IN_FLIGHT"})
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def prompt(self):
        if self.resume_id:
            return "REQUEST_PATCH\n" + canonical(self.delta)
        return "REQUEST_JSON\n" + text(self.value)

    def schema_file(self):
        target = self.directory / ("schema-" + digest(self.schema) + ".json")
        if target.is_symlink():
            raise LedgerError("PATH_SCOPE")
        if not target.exists():
            fd, name = tempfile.mkstemp(prefix="schema-", dir=self.directory)
            try:
                with os.fdopen(fd, "w") as stream:
                    stream.write(canonical(self.schema))
                os.replace(name, target)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
        elif read_document(target, 524288).decode() != canonical(self.schema):
            raise LedgerError("BRIDGE_CONFIG")
        return target

    def _save(self, value):
        if self.path is None:
            return
        fd, name = tempfile.mkstemp(prefix="state-", dir=self.directory)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(canonical(value))
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def complete(self):
        if self.path is not None and self.thread_id:
            identity = str(uuid.UUID(self.thread_id))
            self._save({"status": "SUCCEEDED", "schema": digest(self.schema),
                        "thread_id": identity, "snapshot": snapshot(self.value)})

    def __exit__(self, *args):
        if self.lock:
            self.lock.close()
            self.lock = None
        if self.temporary:
            self.temporary.cleanup()
