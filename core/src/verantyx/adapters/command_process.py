"""Bounded stdio for explicitly configured, trusted local executors.

This is not an OS sandbox. No model response can set the command, environment,
working directory, timeout, or stream limits.
"""
from pathlib import Path
import os
import re
import selectors
import signal
import subprocess
import tempfile
import time

from .observations import read_document
from ..domain.codec import canonical, decode, digest
from ..errors import LedgerError

BASE_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "WINDIR")
SHELLS = {"sh", "bash", "zsh", "dash", "fish", "csh", "tcsh", "cmd", "cmd.exe", "powershell", "pwsh"}


def load_command(path):
    value = decode(read_document(path, 65536), 65536)
    if type(value) is dict and value.get("format") == "verantyx.model-api.v1":
        from ..model_api import command_for
        return command_for(path, value)
    if type(value) is dict and value.get("format") == "verantyx.codex-cli.v1":
        from ..codex_cli import command_for
        return command_for(path, value)
    if type(value) is dict and value.get("format") == "verantyx.claude-cli.v1":
        from ..claude_cli import command_for
        return command_for(path, value)
    if type(value) is not dict or not {"argv"} <= set(value) <= {"argv", "cwd", "env", "inherit_env"}:
        raise LedgerError("BRIDGE_CONFIG")
    argv = value["argv"]
    if (type(argv) is not list or not 1 <= len(argv) <= 128 or
            any(type(arg) is not str or not arg or len(arg) > 8192 or "\x00" in arg for arg in argv)):
        raise LedgerError("BRIDGE_CONFIG")
    executable = Path(argv[0])
    if not executable.is_absolute() or executable.name.lower() in SHELLS:
        raise LedgerError("BRIDGE_CONFIG")
    if "cwd" in value and (type(value["cwd"]) is not str or not Path(value["cwd"]).is_absolute()
                           or not Path(value["cwd"]).is_dir()):
        raise LedgerError("BRIDGE_CONFIG")
    overrides, inherited = value.get("env", {}), value.get("inherit_env", [])
    if type(overrides) is not dict or type(inherited) is not list or len(overrides) + len(inherited) > 64:
        raise LedgerError("BRIDGE_CONFIG")
    if any(type(name) is not str or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name)
           for name in [*overrides, *inherited]):
        raise LedgerError("BRIDGE_CONFIG")
    if any(type(v) is not str or "\x00" in v or len(v) > 16384 for v in overrides.values()):
        raise LedgerError("BRIDGE_CONFIG")
    environment = {name: os.environ[name] for name in (*BASE_ENV, *inherited) if name in os.environ}
    environment.update(overrides)
    command = {"argv": list(argv), "cwd": value.get("cwd"), "env": environment}
    # Credentials and argument values never appear in receipts or errors.
    command["identity"] = digest(command)
    return command


class BoundedProcess:
    def __init__(self, command, *, timeout=60, max_output=262144):
        from ..model_timeouts import process_limit
        if (type(timeout) not in (int, float) or not 0 < timeout <= process_limit(command) or
                type(max_output) is not int or not 1024 <= max_output <= 4 * 1024 * 1024):
            raise LedgerError("ARGUMENTS")
        self.command, self.timeout, self.max_output = command, timeout, max_output
        self.process = self.selector = self.temporary = None
        self.stdout = bytearray()
        self.pending = bytearray()
        self.output_bytes = 0
        self.eof = set()
        self.stdin_closed = False
        self.model_stderr = bytearray()
        self.model_failure = None
        self.thinking_characters = 0

    def __enter__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="verantyx-executor-")
        self.deadline = time.monotonic() + self.timeout
        try:
            environment = dict(self.command["env"])
            # Only closed built-in model adapters may defer credential reads.
            # Enqueuing/checking a job never reads this selected environment.
            if "model_api" in self.command:
                from ..model_api import validate_config
                configuration = validate_config(self.command["model_api"])
                for name in ([configuration["key_env"]] if configuration["key_env"] else []):
                    if name in os.environ:
                        environment[name] = os.environ[name]
            if "notification_api" in self.command:
                from ..notification_http import validate_connection
                configuration = validate_connection(self.command["notification_api"])
                if configuration["key_env"] and configuration["key_env"] in os.environ:
                    environment[configuration["key_env"]] = os.environ[configuration["key_env"]]
            self.process = subprocess.Popen(self.command["argv"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, bufsize=0, shell=False,
                                            cwd=self.command["cwd"] or self.temporary.name,
                                            env=environment, start_new_session=True)
            self.selector = selectors.DefaultSelector()
            for name in ("stdin", "stdout", "stderr"):
                stream = getattr(self.process, name)
                os.set_blocking(stream.fileno(), False)
                if name != "stdin":
                    self.selector.register(stream, selectors.EVENT_READ, name)
            return self
        except OSError:
            self.__exit__(None, None, None)
            raise LedgerError("BRIDGE_START_FAILED") from None

    def __exit__(self, *unused):
        if self.process is not None:
            # Also stop descendants which retained a pipe after the launcher exited.
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.process.wait(timeout=5)
            for name in ("stdin", "stdout", "stderr"):
                stream = getattr(self.process, name)
                if stream is not None:
                    stream.close()
        if self.selector is not None:
            self.selector.close()
        if self.temporary is not None:
            self.temporary.cleanup()

    def send(self, raw):
        if self.stdin_closed or len(self.pending) + len(raw) > 1024 * 1024:
            raise LedgerError("BRIDGE_PROTOCOL")
        self.pending.extend(raw)
        try:
            self.selector.get_key(self.process.stdin)
        except KeyError:
            self.selector.register(self.process.stdin, selectors.EVENT_WRITE, "stdin")

    def _step(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise LedgerError("BRIDGE_TIMEOUT")
        ready = self.selector.select(min(remaining, 0.1))
        for key, _ in ready:
            if key.data == "stdin":
                try:
                    sent = os.write(key.fd, self.pending[:65536])
                except BrokenPipeError:
                    raise LedgerError("BRIDGE_PROTOCOL") from None
                del self.pending[:sent]
                if not self.pending:
                    self.selector.unregister(key.fileobj)
            else:
                raw = os.read(key.fd, min(65536, self.max_output - self.output_bytes + 1))
                if not raw:
                    self.eof.add(key.data)
                    self.selector.unregister(key.fileobj)
                    continue
                self.output_bytes += len(raw)
                if self.output_bytes > self.max_output:
                    raise LedgerError("BRIDGE_OUTPUT_LIMIT")
                if key.data == "stdout":
                    self.stdout.extend(raw)
                elif self.command.get("model_api") or self.command.get("codex_cli") or self.command.get("claude_cli"):
                    self._model_observation(raw)
                # Other stderr counts toward the bound, but is never returned or stored.

    def _model_observation(self, raw):
        from ..model_observation import MAX_LINE, MAX_THINKING, parse
        from ..progress import model_event
        self.model_stderr.extend(raw)
        while b"\n" in self.model_stderr:
            line, _, rest = self.model_stderr.partition(b"\n")
            self.model_stderr = bytearray(rest)
            event = parse(line)
            if event is None:
                continue
            if event["kind"] == "error":
                self.model_failure = event
            elif event["kind"] == "thinking":
                event["text"] = event["text"][:max(0, MAX_THINKING - self.thinking_characters)]
                self.thinking_characters += len(event["text"])
                model_event(event)
            else:
                model_event(event)
        if len(self.model_stderr) > MAX_LINE:
            self.model_stderr.clear()

    def document(self, value, *, send_input=True):
        if send_input:
            if self.command.get("model_api") and value.get("shared_context"):
                from ..model_api import payload
                payload(self.command["model_api"], value)  # Pure size/context preflight before sending any input.
            if any(self.command.get(key) for key in ("model_api", "codex_cli", "claude_cli")):
                from ..progress import model_event
                from ..model_api import generation_policy
                cfg = next(self.command[key] for key in ("model_api", "codex_cli", "claude_cli") if self.command.get(key))
                policy = generation_policy(cfg, value) if cfg["provider"] == "ollama" else {}
                model_event({"kind": "start", "model": cfg["provider"] + " / " + cfg["model"],
                             "thinking": policy.get("thinking", False), "reserve_output": policy.get("reserve_output", False),
                             "output_tokens": cfg.get("max_output_tokens"), "timeout": min(self.timeout, cfg["timeout"])})
            self.send(canonical(value).encode("utf-8") + b"\n")
        while True:
            if not self.pending and not self.stdin_closed:
                self.process.stdin.close()
                self.stdin_closed = True
            if {"stdout", "stderr"} <= self.eof and self.process.poll() is not None:
                if self.process.returncode != 0:
                    if self.model_failure:
                        raise LedgerError(self.model_failure["code"], self.model_failure["details"])
                    raise LedgerError("BRIDGE_PROCESS_FAILED", {"returncode": self.process.returncode})
                return bytes(self.stdout)
            self._step()

    def send_json(self, value):
        self.send(canonical(value).encode("utf-8") + b"\n")

    def receive_json(self):
        while True:
            index = self.stdout.find(b"\n")
            if index >= 0:
                raw = bytes(self.stdout[:index])
                del self.stdout[:index + 1]
                return decode(raw, self.max_output)
            if "stdout" in self.eof:
                raise LedgerError("BRIDGE_PROTOCOL")
            self._step()
