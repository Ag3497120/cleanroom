"""Explicit service-manager effects and bounded dispatch of attested proposal jobs."""
from pathlib import Path
import hashlib
import os
import plistlib
import re
import shlex

from .adapters.command_process import BASE_ENV, BoundedProcess
from .adapters.invocation_journal import InvocationJournal
from .adapters.observations import read_document
from .adapters.proposal_validation import valid_id
from .application import iso, now
from .domain.codec import digest
from .errors import LedgerError


def _require(condition, reason, code="BRIDGE_CONFIG"):
    if not condition:
        raise LedgerError(code, {"reason": reason})


def approval_deadline(root):
    try:
        from .authority import require_current_approval_valid
    except ImportError:
        if (Path(root) / ".verantyx/authority.db").exists():
            raise LedgerError("BRIDGE_CONFIG", {"reason": "AUTHORITY_MODULE_REQUIRED"}) from None
        return None
    return require_current_approval_valid()


def _read_definition(root, definition, expected_sha256, timer_sha256=None):
    """Accept only our proposal-worker template; never arbitrary service code."""
    from .connections_v05 import _systemd_quote
    path = Path(definition).absolute()
    raw = read_document(path, 65536)
    _require(hashlib.sha256(raw).hexdigest() == expected_sha256, "SERVICE_DEFINITION_CHANGED")
    selected_root = str(Path(root).resolve())
    identity = "verantyx.proposals." + hashlib.sha256(selected_root.encode()).hexdigest()[:16]
    timer = None
    try:
        if path.suffix == ".plist":
            _require(timer_sha256 is None, "SERVICE_DEFINITION")
            value = plistlib.loads(raw)
            _require(type(value) is dict and set(value) == {"Label", "ProgramArguments", "StartInterval", "RunAtLoad", "WorkingDirectory", "ProcessType"}, "SERVICE_DEFINITION")
            argv, interval = value["ProgramArguments"], value["StartInterval"]
            _require(value["Label"] == identity and value["RunAtLoad"] is False and value["WorkingDirectory"] == selected_root
                     and value["ProcessType"] == "Background", "SERVICE_DEFINITION")
            kind = "launchd"
        else:
            _require(path.suffix == ".service" and re.fullmatch(r"[A-Za-z0-9_.-]+\.service", path.name), "SERVICE_DEFINITION")
            timer = path.with_suffix(".timer")
            timer_raw = read_document(timer, 65536)
            _require(hashlib.sha256(timer_raw).hexdigest() == timer_sha256, "SERVICE_DEFINITION_CHANGED")
            text, timer_text = raw.decode(), timer_raw.decode()
            starts = [line[10:] for line in text.splitlines() if line.startswith("ExecStart=")]
            intervals = re.findall(r"^OnActiveSec=([0-9]+)$", timer_text, re.MULTILINE)
            _require(len(starts) == len(intervals) == 1, "SERVICE_DEFINITION")
            argv = [arg.replace("%%", "%").replace("$$", "$") for arg in shlex.split(starts[0])]
            interval = int(intervals[0])
            kind = "systemd"
        _require(type(argv) is list and len(argv) == 7 and all(type(arg) is str for arg in argv)
                 and argv[1:6] == ["--project", selected_root, "--json", "service-worker", "--max-jobs"]
                 and argv[6].isdigit() and 1 <= int(argv[6]) <= 100, "SERVICE_WORKER_ONLY")
        executable = Path(argv[0])
        _require(executable.is_absolute() and executable.is_file() and os.access(executable, os.X_OK), "SERVICE_EXECUTABLE")
        _require(type(interval) is int and 10 <= interval <= 86400, "SERVICE_INTERVAL")
        if kind == "systemd":
            expected_service = ("[Unit]\nDescription=Verantyx bounded proposal worker\n\n[Service]\nType=oneshot\n"
                                + "ExecStart=" + " ".join(_systemd_quote(arg) for arg in argv) + "\n"
                                + f"TimeoutStartSec={600 * int(argv[6]) + 60}\nUMask=0077\n")
            expected_timer = ("[Unit]\nDescription=Verantyx proposal polling\n\n[Timer]\n"
                              + f"OnActiveSec={interval}\nOnUnitInactiveSec={interval}\nUnit={path.name}\nPersistent=false\n\n"
                              + "[Install]\nWantedBy=timers.target\n")
            _require(text == expected_service and timer_text == expected_timer, "SERVICE_DEFINITION")
    except (ValueError, TypeError, KeyError, AttributeError, plistlib.InvalidFileException):
        raise LedgerError("BRIDGE_CONFIG", {"reason": "SERVICE_DEFINITION"}) from None
    return {"kind": kind, "definition": str(path), "definition_sha256": expected_sha256,
            "timer": str(timer) if timer else None, "timer_sha256": timer_sha256, "label": identity,
            "worker": argv, "worker_sha256": hashlib.sha256(read_document(executable, 64 * 1024 * 1024)).hexdigest()}


def control(root, configuration, *, operation, definition, expected_sha256, manager, key,
            worker_sha256, timer_sha256=None, timeout=30, clock=now, fault=None):
    _require(operation in ("register", "stop") and valid_id(key) and type(timeout) is int and 1 <= timeout <= 60,
             "SERVICE_ARGUMENTS", "ARGUMENTS")
    spec = _read_definition(root, definition, expected_sha256, timer_sha256)
    _require(spec["worker_sha256"] == worker_sha256, "SERVICE_EXECUTABLE_CHANGED")
    manager = Path(manager).absolute()
    _require(manager.name == ("launchctl" if spec["kind"] == "launchd" else "systemctl")
             and manager.is_file() and os.access(manager, os.X_OK), "SERVICE_MANAGER")
    manager_hash = hashlib.sha256(read_document(manager, 64 * 1024 * 1024)).hexdigest()
    if spec["kind"] == "launchd":
        commands = [[str(manager), "bootstrap", "gui/" + str(os.getuid()), spec["definition"]]] if operation == "register" else [
                    [str(manager), "bootout", "gui/" + str(os.getuid()) + "/" + spec["label"]]]
    else:
        base = [str(manager), "--user", "--no-ask-password", "--no-pager"]
        commands = [base + ["link", spec["definition"], spec["timer"]], base + ["enable", "--now", Path(spec["timer"]).name]] if operation == "register" else [
                    base + ["disable", "--now", Path(spec["timer"]).name], base + ["stop", Path(spec["definition"]).name]]
    intent = {"operation": operation, "spec": spec, "manager": str(manager), "manager_sha256": manager_hash,
              "project_id": configuration["project"]["id"], "timeout": timeout, "uid": os.getuid()}
    intent_hash = digest(intent)
    with InvocationJournal(root, "service-control", key) as journal:
        started = journal.read("started")
        if started:
            _require(started["intent_hash"] == intent_hash, "SERVICE_INTENT_CHANGED", "IDEMPOTENCY_CONFLICT")
            response = journal.read("response")
            if response:
                return {**response, "duplicate": True}
            raise LedgerError("BRIDGE_OUTCOME_UNKNOWN")
        journal.write("started", {"intent_hash": intent_hash, "operation": operation, "recorded_at": iso(clock())})
        if fault:
            fault("after_started")
        environment = {name: os.environ[name] for name in (*BASE_ENV, "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS") if name in os.environ}
        try:
            for index, argv in enumerate(commands):
                _require(_read_definition(root, definition, expected_sha256, timer_sha256) == spec
                         and hashlib.sha256(read_document(manager, 64 * 1024 * 1024)).hexdigest() == manager_hash, "SERVICE_INPUT_CHANGED")
                journal.write("step-" + str(index) + "-started", {"argv_sha256": digest(argv)})
                approval_deadline(root)
                with BoundedProcess({"argv": argv, "env": environment, "cwd": None}, timeout=timeout, max_output=65536) as process:
                    process.document(None, send_input=False)
                journal.write("step-" + str(index) + "-returned", {"returncode": 0})
                if fault:
                    fault("after_step_" + str(index))
        except LedgerError as error:
            journal.write("failed", {"status": "OUTCOME_UNKNOWN", "code": error.code})
            raise LedgerError("BRIDGE_OUTCOME_UNKNOWN") from None
        response = {"schema_version": 1, "ok": True, "command": "service-" + operation, "kind": spec["kind"],
                    "status": "MANAGER_RETURNED_SUCCESS", "operation": operation, "steps": len(commands),
                    "intent_sha256": intent_hash, "automatic_retry": False, "duplicate": False,
                    "worker_job_scope": "ATTESTED_PROPOSAL_JOBS_WHEN_AUTHORITY_ENABLED"}
        journal.write("response", response)
        return response


def worker(root, configuration, *, max_jobs=1, clock=now):
    """An unsigned scheduler may deliver only jobs individually attested by the operator."""
    from . import jobs
    _require(type(max_jobs) is int and 1 <= max_jobs <= 100, "SERVICE_WORKER_LIMIT", "ARGUMENTS")
    try:
        from .authority import require_proposal_job_approval
    except ImportError:
        if (Path(root) / ".verantyx/authority.db").exists():
            raise LedgerError("BRIDGE_CONFIG", {"reason": "AUTHORITY_MODULE_REQUIRED"}) from None
        require_proposal_job_approval = None
    processed, refused = [], []
    for item in jobs.list_jobs(root, configuration, clock=clock)["jobs"]:
        if not item["due"]:
            continue
        journal = InvocationJournal(root, "job", item["job_id"])
        try:
            job = jobs._load(journal, configuration)
            if require_proposal_job_approval is not None:
                require_proposal_job_approval(root, configuration, journal, job)
            processed.append(jobs.run_job(root, configuration, item["job_id"], clock=clock))
        except LedgerError as error:
            refused.append({"job_id": item["job_id"], "code": error.code})
        if len(processed) + len(refused) >= max_jobs:
            break
    return {"schema_version": 1, "ok": not refused and all(item["ok"] for item in processed), "command": "service-worker",
            "processed": processed, "refused": refused, "proposal_only": True}
