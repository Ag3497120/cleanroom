"""Owner-granted external tools. Meaning stays with the AI; effects have receipts."""
import asyncio
import base64
from concurrent.futures import Future, TimeoutError as FutureTimeout
from contextlib import AsyncExitStack, contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import timedelta
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import tempfile
import threading
import uuid

from jsonschema import Draft202012Validator
from .adapters.invocation_journal import InvocationJournal
from .authority import require_current_approval_valid
from .domain.codec import canonical, decode, digest
from .errors import LedgerError

FILE = ".verantyx/toolbox.json"
DEFAULT = {"format": "cleanroom.toolbox.v1", "write_candidates": True,
           "checks": {}, "sandbox": None, "mcp_servers": {}}
CURRENT = ContextVar("cleanroom_toolbox", default=None)
TOOLS = ("list_mcp_tools", "call_mcp", "run_project_check")


def require(value, code="TOOLBOX_CONFIG"):
    if not value:
        raise LedgerError(code)


def argv_valid(argv):
    require(type(argv) is list and 1 <= len(argv) <= 64)
    require(all(type(s) is str and s and len(s) <= 4096 and "\0" not in s for s in argv))
    require(Path(argv[0]).is_absolute())
    return argv


def validate(value):
    require(type(value) is dict and set(value) == set(DEFAULT))
    require(value["format"] == DEFAULT["format"] and type(value["write_candidates"]) is bool)
    require(type(value["checks"]) is dict and len(value["checks"]) <= 16)
    require(type(value["mcp_servers"]) is dict and len(value["mcp_servers"]) <= 8)
    for name, row in value["checks"].items():
        require(re.fullmatch(r"[A-Za-z0-9_-]{1,60}", name) and type(row) is dict)
        require(set(row) == {"argv", "timeout"})
        argv_valid(row["argv"])
        require(type(row["timeout"]) is int and 1 <= row["timeout"] <= 180)
    sandbox = value["sandbox"]
    if sandbox is not None:
        require(type(sandbox) is dict and set(sandbox) == {"argv_prefix", "allow_read"})
        argv_valid(sandbox["argv_prefix"])
        require(any("{policy}" in x for x in sandbox["argv_prefix"]))
        require(type(sandbox["allow_read"]) is list and len(sandbox["allow_read"]) <= 16)
        require(all(type(p) is str and Path(p).is_absolute() for p in sandbox["allow_read"]))
    require(not value["checks"] or sandbox is not None, "TOOLBOX_SANDBOX_REQUIRED")
    for name, row in value["mcp_servers"].items():
        require(re.fullmatch(r"[A-Za-z0-9_-]{1,60}", name) and type(row) is dict)
        require(set(row) == {"argv", "tools", "argument_schemas", "timeout", "env"})
        argv_valid(row["argv"])
        require(type(row["tools"]) is list and 1 <= len(row["tools"]) <= 32)
        require(all(type(t) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", t) for t in row["tools"]))
        require(type(row["argument_schemas"]) is dict and set(row["argument_schemas"]) <= set(row["tools"]))
        for schema in row["argument_schemas"].values():
            try:
                Draft202012Validator.check_schema(schema)
            except Exception:
                raise LedgerError("TOOLBOX_CONFIG") from None
        require(type(row["timeout"]) is int and 1 <= row["timeout"] <= 120)
        require(type(row["env"]) is dict and len(row["env"]) <= 12)
        # Owner-supplied literal settings only. No automatic credential inheritance.
        require(all(type(k) is str and re.fullmatch(r"[A-Z_][A-Z0-9_]{0,80}", k)
                    and not k.startswith(("PYTHON", "LD_", "DYLD_"))
                    and type(v) is str and len(v) <= 4096 for k, v in row["env"].items()))
    return deepcopy(value)


def load(root):
    from .work_harness import _read
    raw = _read(root, FILE, optional=True)
    value = validate(decode(raw, 131072)) if raw is not None else deepcopy(DEFAULT)
    return value, digest(value)


def configure(root, value, *, confirmed=False):
    require(confirmed is True, "TOOLBOX_APPROVAL_REQUIRED")
    value = validate(value)
    require_current_approval_valid()
    with InvocationJournal(root, "toolbox-settings", "configuration"):
        base = os.open(Path(root).resolve(), os.O_RDONLY | os.O_DIRECTORY)
        try:
            directory = os.open(".verantyx", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=base)
        finally:
            os.close(base)
        temporary = ".toolbox-" + uuid.uuid4().hex
        try:
            fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(canonical(value) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, "toolbox.json", src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
            os.close(directory)
    return {"ok": True, "configuration_sha256": digest(value), "settings": value,
            "isolation_verified": False, "started_processes": 0}


class MCPWorker:
    """All MCP contexts enter and exit in one async task, including on shutdown."""
    def __init__(self, root, configurations):
        self.root, self.configurations = Path(root), configurations
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._thread, daemon=True)
        self.thread.start()

    def _thread(self):
        try:
            asyncio.run(self._serve())
        except BaseException as error:
            self.failure = type(error).__name__

    async def _serve(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        sessions = {}
        # Stderr never becomes an instruction, and is not printed into the TUI.
        with tempfile.TemporaryFile(mode="w+") as errlog:
            async with AsyncExitStack() as stack:
                while True:
                    item = await asyncio.to_thread(self.queue.get)
                    if item is None:
                        return
                    future, alias, tool, arguments = item
                    try:
                        cfg = self.configurations[alias]
                        if alias not in sessions:
                            env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")
                                   if key in os.environ}
                            # Dedicated ephemeral HOME; never use a signed-in browser profile.
                            directory = stack.enter_context(tempfile.TemporaryDirectory(prefix="cleanroom-mcp-"))
                            env.update(HOME=directory, XDG_CONFIG_HOME=directory, XDG_CACHE_HOME=directory)
                            env.update(cfg["env"])
                            read, write = await stack.enter_async_context(stdio_client(
                                StdioServerParameters(command=cfg["argv"][0], args=cfg["argv"][1:],
                                                      env=env, cwd=directory), errlog=errlog))
                            session = await stack.enter_async_context(ClientSession(
                                read, write, read_timeout_seconds=timedelta(seconds=cfg["timeout"])))
                            await session.initialize()
                            response = await session.list_tools()
                            schemas = {t.name: t for t in response.tools if t.name in cfg["tools"]}
                            sessions[alias] = session, schemas
                        session, schemas = sessions[alias]
                        if tool is None:
                            result = {"server": alias, "tools": [
                                {"name": t.name, "description": (t.description or "")[:1500],
                                 "input_schema": t.inputSchema} for t in schemas.values()],
                                      "authority": "UNTRUSTED_TOOL_DESCRIPTIONS"}
                        else:
                            require(tool in schemas, "MCP_TOOL_NOT_GRANTED")
                            require(Draft202012Validator(schemas[tool].inputSchema).is_valid(arguments),
                                    "MCP_ARGUMENT_SCHEMA")
                            response = await session.call_tool(tool, arguments)
                            blocks = []
                            for block in response.content:
                                if block.type == "text":
                                    blocks.append({"type": "text", "text": block.text[:24000]})
                                elif block.type == "image":
                                    raw = base64.b64decode(block.data, validate=True)
                                    require(len(raw) <= 10 * 1024 * 1024, "MCP_MEDIA_LIMIT")
                                    # Keep image bytes outside the model text, with an immutable digest.
                                    directory = self.root / ".verantyx" / "tool-media"
                                    require(not directory.is_symlink(), "PATH_SCOPE")
                                    directory.mkdir(mode=0o700, exist_ok=True)
                                    sha = hashlib.sha256(raw).hexdigest()
                                    target = directory / (sha + ".bin")
                                    if not target.exists():
                                        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                                        with os.fdopen(fd, "wb") as stream:
                                            stream.write(raw)
                                    blocks.append({"type": "image", "sha256": sha, "mime_type": block.mimeType,
                                                   "path": str(target), "model_saw_pixels": False})
                            result = {"server": alias, "tool": tool, "is_error": bool(response.isError),
                                      "content": blocks, "authority": "EXTERNAL_TOOL_RESULT_NOT_HUMAN_APPROVAL"}
                        future.set_result(result)
                    except Exception as error:
                        future.set_exception(error)

    def call(self, alias, tool=None, arguments=None):
        require(self.thread.is_alive(), "MCP_SESSION_UNAVAILABLE")
        future = Future()
        self.queue.put((future, alias, tool, arguments or {}))
        try:
            return future.result(timeout=self.configurations[alias]["timeout"] + 15)
        except FutureTimeout:
            raise LedgerError("MCP_TIMEOUT") from None
        except LedgerError:
            raise
        except Exception as error:
            raise LedgerError("MCP_CALL_FAILED", {"type": type(error).__name__}) from None

    def close(self):
        self.queue.put(None)
        self.thread.join(timeout=5)


class ToolSession:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.settings, self.fingerprint = load(root)
        self.worker = None
        self.calls = 0

    def describe(self):
        return {"configuration_sha256": self.fingerprint,
                "write_candidates": self.settings["write_candidates"],
                "checks": {name: deepcopy(row) for name, row in self.settings["checks"].items()},
                "mcp_servers": {name: {"tools": cfg["tools"]} for name, cfg in self.settings["mcp_servers"].items()},
                "external_process_effects": "NOT_A_WHOLE_FILESYSTEM_AUDIT",
                "sandbox": "REQUESTED_NOT_ATTESTED" if self.settings["sandbox"] else "NOT_CONFIGURED"}

    def unchanged(self):
        require(load(self.root)[1] == self.fingerprint, "TOOLBOX_CHANGED")
        require_current_approval_valid()

    def execute(self, request, *, run_id, turn, scope, artifacts):
        self.unchanged()
        key = digest({"run": run_id, "turn": turn, "request": request})
        intent = {"request": request, "configuration": self.fingerprint,
                  "artifacts": artifacts, "scope": scope}
        with InvocationJournal(self.root, "work-toolbox", key) as journal:
            prior = journal.read("intent")
            require(prior is None or prior == digest(intent), "IDEMPOTENCY_CONFLICT")
            if journal.read("result") is not None:
                return journal.read("result")
            require(journal.read("started") is None, "TOOL_OUTCOME_UNKNOWN")
            self.calls += 1
            require(self.calls <= 48, "TOOLBOX_CALL_LIMIT")
            if request["tool"] == "run_project_check":
                require(request["path"] in self.settings["checks"] and not request["text"], "CHECK_NOT_GRANTED")
            else:
                alias, _, tool = request["path"].partition("/")
                require(alias in self.settings["mcp_servers"], "MCP_SERVER_NOT_GRANTED")
                cfg = self.settings["mcp_servers"][alias]
                if request["tool"] == "call_mcp":
                    require(tool in cfg["tools"], "MCP_TOOL_NOT_GRANTED")
                    arguments = decode(request["text"].encode(), 16000)
                    require(type(arguments) is dict, "MCP_ARGUMENT_SCHEMA")
                    require(Draft202012Validator(cfg["argument_schemas"].get(tool, {})).is_valid(arguments),
                            "MCP_OWNER_ARGUMENT_SCOPE")
                else:
                    require(not tool and not request["text"], "MCP_ARGUMENT_SCHEMA")
            journal.write("intent", digest(intent))
            journal.write("started", {"configuration_sha256": self.fingerprint})
            if request["tool"] == "run_project_check":
                result = self._check(request["path"], scope, artifacts)
            else:
                if self.worker is None:
                    self.worker = MCPWorker(self.root, self.settings["mcp_servers"])
                result = self.worker.call(alias, tool if request["tool"] == "call_mcp" else None,
                                          arguments if request["tool"] == "call_mcp" else None)
            result["configuration_sha256"] = self.fingerprint
            require(len(canonical(result)) <= 62000, "TOOLBOX_OUTPUT_LIMIT")
            journal.write("result", result)
            return result

    def _check(self, name, scope, artifacts):
        from .agent_runtime import _read_text, _relative
        from .agent_candidate_files import read_bytes
        from .work_checks import _execute
        sandbox = self.settings["sandbox"]
        require(sandbox is not None, "TOOLBOX_SANDBOX_REQUIRED")
        rows = {}
        for path in scope:
            rows[path] = _read_text(self.root, path).encode("utf-8")
        for row in artifacts.values():
            rows[row["path"]] = read_bytes(self.root, row["storage_path"], expected=row, internal=True)
        manifest = [{"path": name, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                    for name, raw in sorted(rows.items())]
        with tempfile.TemporaryDirectory(prefix="cleanroom-check-") as directory:
            workspace = Path(directory).resolve()
            for path, raw in rows.items():
                target = workspace / _relative(self.root, path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            policy = {
                "network": {"allowedDomains": [], "deniedDomains": [], "allowLocalBinding": False},
                "filesystem": {"denyRead": ["/Users", "/home", "/Volumes", "/private/tmp", "/private/var/folders"],
                               "allowRead": [str(workspace), *sandbox["allow_read"]],
                               "allowWrite": [str(workspace)], "denyWrite": []}}
            # The launcher's settings stay outside the disposable candidate tree.
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8") as handle:
                handle.write(canonical(policy))
                handle.flush()
                prefix = [part.replace("{policy}", handle.name).replace("{workspace}", str(workspace))
                          for part in sandbox["argv_prefix"]]
                require(os.access(prefix[0], os.X_OK), "SANDBOX_LAUNCHER_UNAVAILABLE")
                command = self.settings["checks"][name]
                actual = [*prefix, *command["argv"]]
                result = _execute(actual, workspace, command["timeout"])
            return {**result, "label": name, "argv": command["argv"], "manifest": manifest,
                    "manifest_sha256": digest(manifest),
                    "candidate_manifest_sha256": __import__("verantyx.domain.work_checks", fromlist=["manifest_hash"]).manifest_hash(
                        artifacts.values()),
                    "sandbox": {"policy_sha256": digest(policy), "launcher": prefix[0],
                                "isolation_verified": False, "fallback_to_unsandboxed": False},
                    "evidence_scope": "NAMED_CHECK_ON_APPROVED_FILES_AND_CANDIDATE_SNAPSHOT"}


@contextmanager
def session(root):
    value = ToolSession(root)
    token = CURRENT.set(value)
    try:
        yield value
    finally:
        if value.worker:
            value.worker.close()
        CURRENT.reset(token)


def scoped(operation):
    @wraps(operation)
    def run(root, *args, **kwargs):
        with session(root):
            return operation(root, *args, **kwargs)
    return run


def current():
    require(CURRENT.get() is not None, "TOOLBOX_SESSION_REQUIRED")
    return CURRENT.get()


def check_projection(state):
    from .domain.work_checks import manifest_hash
    current_hash = manifest_hash(state.get("work_artifacts", {}).values())
    result = []
    for row in state.get("work_tools", []):
        if row["request"]["tool"] != "run_project_check" or row["status"] != "SUCCEEDED":
            continue
        try:
            value = json.loads(row["text"])
        except ValueError:
            continue
        result.append({**value, "completed": True, "source_ref": row["source_ref"],
                       "stale": value.get("candidate_manifest_sha256") != current_hash,
                       "authority": "HOST_EXECUTION_RECEIPT"})
    return result
