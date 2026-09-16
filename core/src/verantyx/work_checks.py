"""Run a human-selected check on a disposable copy of recorded candidate bytes.

This is deliberately not a general model tool or an OS sandbox. Confirmation
authorizes this exact local command, which still runs with the user's OS rights.
No automatic dependency install, native shell expansion, retry, or adoption.
"""
from copy import deepcopy
from pathlib import Path
import os
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
import uuid

from .adapters.invocation_journal import InvocationJournal
from .agent_candidate_files import read_bytes
from .agent_runtime import _state, _record, _relative
from .authority import require_current_approval_valid
from .domain.codec import digest
from .domain.work_checks import manifest_hash
from .errors import LedgerError


def projection(state):
    rows = []
    for entry in state.get("work_checks", {}).values():
        request, result = entry["request"], entry["result"]
        rows.append({**deepcopy(request), **deepcopy(result or {}),
                     "status": result["status"] if result else "UNKNOWN",
                     "completed": result is not None,
                     "source_ref": result["source_ref"] if result else request["source_ref"]})
    return rows


def _stop(process):
    if process is None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def _execute(argv, cwd, timeout):
    started = time.monotonic()
    streams = {"stdout": bytearray(), "stderr": bytearray()}
    truncated, process, status, reason, code = False, None, "START_FAILED", "", None
    environment = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")
                   if key in os.environ}
    home = Path(tempfile.mkdtemp(prefix=".cleanroom-check-home-", dir=cwd))
    environment.update(HOME=str(home), XDG_CONFIG_HOME=str(home), XDG_CACHE_HOME=str(home),
                       PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", NO_COLOR="1", CI="1")
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   shell=False, start_new_session=True)
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            for name in streams:
                handle = getattr(process, name)
                os.set_blocking(handle.fileno(), False)
                selector.register(handle, selectors.EVENT_READ, name)
            while selector.get_map() or process.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    status, reason = "TIMED_OUT", "CHECK_DEADLINE"
                    break
                require_current_approval_valid()
                for key, _ in selector.select(min(remaining, 0.1)):
                    raw = os.read(key.fd, 65536)
                    if not raw:
                        selector.unregister(key.fileobj)
                        continue
                    room = max(0, 16000 - len(streams[key.data]))
                    streams[key.data].extend(raw[:room])
                    truncated = truncated or len(raw) > room
            else:
                code = process.returncode
                status = "PASSED" if code == 0 else "FAILED"
    except KeyboardInterrupt:
        status, reason = "INTERRUPTED", "USER_INTERRUPTED"
    except (OSError, LedgerError) as error:
        status, reason = ("UNKNOWN" if process is not None else "START_FAILED"), getattr(error, "code", type(error).__name__)
    finally:
        _stop(process)
        if process is not None:
            for name in streams:
                getattr(process, name).close()
    output = {name: bytes(raw).decode("utf-8", errors="replace") for name, raw in streams.items()}
    return {"status": status, "exit_code": code, "elapsed_ms": int((time.monotonic() - started) * 1000),
            **output, "output_truncated": truncated, "output_sha256": digest(output), "reason": reason,
            "evidence_scope": "RECORDED_COMMAND_ON_CANDIDATE_COPY_ONLY"}


def run_check(root, configuration, run_id, *, argv, label="Candidate check", confirmed=False,
              timeout=120, key=None):
    if confirmed is not True:
        raise LedgerError("CHECK_CONFIRMATION_REQUIRED")
    if (type(argv) not in (list, tuple) or not 1 <= len(argv) <= 64
            or any(type(arg) is not str or len(arg) > 4096 or "\0" in arg for arg in argv)
            or not argv[0] or type(timeout) is not int or not 1 <= timeout <= 600
            or type(label) is not str or not label.strip() or len(label) > 240):
        raise LedgerError("ARGUMENTS")
    key = key or "check-" + uuid.uuid4().hex
    if type(key) is not str or not 1 <= len(key) <= 120:
        raise LedgerError("ARGUMENTS")
    argv = list(argv)
    # Resolve only the executable; remaining arguments keep their exact meaning.
    executable = shutil.which(argv[0])
    if executable is None:
        raise LedgerError("CHECK_EXECUTABLE_MISSING")
    argv[0] = str(Path(executable).absolute())
    state = _state(root, configuration, run_id)
    work = state.get("work_result")
    if not work or not work["artifacts"]:
        raise LedgerError("WORK_CANDIDATE_REQUIRED")
    fingerprint = manifest_hash(work["artifacts"])
    intent = {"id": key, "label": label, "argv": argv, "timeout": timeout,
              "manifest_sha256": fingerprint, "work_result_source_ref": work["source_ref"],
              "execution_boundary": "EXPLICIT_TRUSTED_COMMAND_NOT_OS_SANDBOX"}
    with InvocationJournal(root, "candidate-check", key) as journal:
        previous = journal.read("intent")
        if previous is not None and previous != intent:
            raise LedgerError("IDEMPOTENCY_CONFLICT")
        if previous is None:
            journal.write("intent", intent)
        existing = state.get("work_checks", {}).get(key)
        if existing and existing["result"]:
            return {"ok": existing["result"]["status"] == "PASSED", "command": "check",
                    "run_id": run_id, "check": deepcopy(existing["result"]), "state": state, "replayed": True}
        if not existing:
            state = _record(root, configuration, run_id, "WorkCheckStarted", intent, key + "-started")
        completed = journal.read("result")
        if completed is None:
            if journal.read("started") is not None:
                completed = {"status": "UNKNOWN", "exit_code": None, "elapsed_ms": 0,
                             "stdout": "", "stderr": "", "output_truncated": False,
                             "output_sha256": digest({"stdout": "", "stderr": ""}),
                             "reason": "PREVIOUS_PROCESS_OUTCOME_UNKNOWN_NO_RETRY",
                             "evidence_scope": "RECORDED_COMMAND_ON_CANDIDATE_COPY_ONLY"}
            else:
                # Verify every immutable source before launching anything.
                files = [(_relative(root, row["path"]),
                          read_bytes(root, row["storage_path"], expected=row, internal=True))
                         for row in work["artifacts"]]
                with tempfile.TemporaryDirectory(prefix="cleanroom-check-") as directory:
                    for relative, raw in files:
                        path = Path(directory) / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        with path.open("xb") as handle:
                            handle.write(raw)
                    require_current_approval_valid()
                    journal.write("started", {"manifest_sha256": fingerprint})
                    completed = _execute(argv, directory, timeout)
            completed = {**completed, "id": key, "manifest_sha256": fingerprint}
            journal.write("result", completed)
        state = _record(root, configuration, run_id, "WorkCheckRecorded", completed, key + "-recorded")
        return {"ok": completed["status"] == "PASSED", "command": "check", "run_id": run_id,
                "check": deepcopy(state["work_checks"][key]["result"]), "state": state, "replayed": False}
