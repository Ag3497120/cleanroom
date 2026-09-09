"""Observed process registrations for isolated candidate destinations.

Registration is coordination evidence, never permission to write. It does not
launch, stop, signal or sandbox a process. Expiry does not make a live writer safe.
"""
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
import os
import subprocess
import sys
import uuid
from functools import lru_cache


@lru_cache(maxsize=1)
def _mac_boot_session():
    try:
        value = subprocess.run(["/usr/sbin/sysctl", "-n", "kern.bootsessionuuid"], capture_output=True, text=True,
                               timeout=5, check=True).stdout.strip()
        return str(uuid.UUID(value))
    except (OSError, ValueError, subprocess.SubprocessError):
        return None

from .domain.codec import digest
from .domain.events import fields, require, timestamp, uuid_value
from .errors import LedgerError
from .security_journal import Journal, exclusive


def process_identity(pid):
    """Fresh PID plus start identity; never use a cached Process instance."""
    import psutil
    require(type(pid) is int and pid > 0, "WRITER_PROCESS_INVALID")
    try:
        process = psutil.Process(pid)
        if process.status() in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD) or not process.is_running():
            return {"status": "DEAD", "pid": pid}
        if sys.platform.startswith("linux"):
            # Linux boot UUID + monotonic start ticks does not depend on wall time.
            boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            stat = Path(f"/proc/{pid}/stat").read_text()
            start = stat[stat.rfind(")") + 2:].split()[19]
            identity = "linux:" + boot + ":" + start
        elif sys.platform == "darwin":
            boot = _mac_boot_session()
            if boot is None:
                return {"status": "UNKNOWN", "pid": pid}
            identity = "darwin:" + boot + ":" + float(process.create_time()).hex()
        else:
            raise LedgerError("WRITER_PLATFORM_UNSUPPORTED")
        uid = process.uids().effective
        result = {"status": "ALIVE", "pid": pid, "start_id": identity, "uid": uid,
                  "cwd": str(Path(process.cwd()).resolve()), "executable": process.exe()}
        if not process.is_running():
            return {"status": "DEAD", "pid": pid}
        return result
    except (psutil.NoSuchProcess, FileNotFoundError):
        return {"status": "DEAD", "pid": pid}
    except (psutil.AccessDenied, PermissionError, ProcessLookupError):
        return {"status": "UNKNOWN", "pid": pid}
    except (subprocess.SubprocessError, ValueError):
        return {"status": "UNKNOWN", "pid": pid}


def _validate_process(value):
    require(type(value) is dict and value.get("status") == "ALIVE", "SECURITY_INTEGRITY")
    fields(value, ("status", "pid", "start_id", "uid", "cwd", "executable"))
    require(type(value["pid"]) is int and value["pid"] > 0 and type(value["uid"]) is int and value["uid"] >= 0,
            "SECURITY_INTEGRITY")
    require(type(value["start_id"]) is str and value["start_id"].startswith(("linux:", "darwin:")), "SECURITY_INTEGRITY")
    require(all(type(value[key]) is str and Path(value[key]).is_absolute() for key in ("cwd", "executable")), "SECURITY_INTEGRITY")


def replay(entries):
    """Reconstruct only recorded evidence; never query a process during replay."""
    result = {"revision": 0, "hash": "0" * 64, "writers": {}}
    for entry in entries:
        require(entry["revision"] == result["revision"] + 1 and entry["previous_hash"] == result["hash"], "SECURITY_INTEGRITY")
        payload, kind = entry["payload"], entry["kind"]
        if kind == "WriterRegistered":
            fields(payload, ("id", "run_id", "effect_lease", "workspace", "responsible", "process", "origin", "expires_at"))
            uuid_value(payload["id"])
            uuid_value(payload["effect_lease"])
            require(payload["id"] not in result["writers"] and type(payload["run_id"]) is str
                    and type(payload["workspace"]) is str and Path(payload["workspace"]).is_absolute()
                    and type(payload["responsible"]) is str and 1 <= len(payload["responsible"].strip()) <= 1000
                    and payload["origin"] in ("EXTERNAL_PROCESS", "EXECUTION_GATEWAY"), "SECURITY_INTEGRITY")
            timestamp(payload["expires_at"])
            require(entry["recorded_at"] < payload["expires_at"], "SECURITY_INTEGRITY")
            _validate_process(payload["process"])
            require(payload["origin"] != "EXTERNAL_PROCESS" or payload["process"]["cwd"] == payload["workspace"],
                    "SECURITY_INTEGRITY")
            for registered in result["writers"].values():
                if registered["status"] == "REGISTERED" and _overlap(registered["workspace"], payload["workspace"]):
                    require(registered["observation"] is not None and registered["observation"]["status"] in ("DEAD", "PID_REUSED"),
                            "SECURITY_INTEGRITY")
            result["writers"][payload["id"]] = {**payload, "status": "REGISTERED", "observation": None}
        elif kind == "WriterObserved":
            fields(payload, ("id", "observation"))
            current = result["writers"].get(payload["id"])
            require(current is not None and current["status"] == "REGISTERED", "SECURITY_INTEGRITY")
            observation = payload["observation"]
            fields(observation, ("status", "at", "process"))
            require(observation["status"] in ("ALIVE", "DEAD", "PID_REUSED", "UNKNOWN", "LOCATION_CHANGED", "LEASE_EXPIRED_LIVE"),
                    "SECURITY_INTEGRITY")
            timestamp(observation["at"])
            require(observation["at"] == entry["recorded_at"], "SECURITY_INTEGRITY")
            actual = observation["process"]
            require(type(actual) is dict and type(actual.get("pid")) is int and actual["pid"] == current["process"]["pid"],
                    "SECURITY_INTEGRITY")
            if actual.get("status") == "ALIVE":
                _validate_process(actual)
            else:
                fields(actual, ("status", "pid"))
                require(actual["status"] in ("DEAD", "UNKNOWN"), "SECURITY_INTEGRITY")
            require(_classify(current, actual, observation["at"]) == observation["status"], "SECURITY_INTEGRITY")
            current["observation"] = observation
        elif kind == "WriterRenewed":
            fields(payload, ("id", "expires_at", "process"))
            current = result["writers"].get(payload["id"])
            require(current is not None and current["status"] == "REGISTERED", "SECURITY_INTEGRITY")
            timestamp(payload["expires_at"])
            _validate_process(payload["process"])
            require(_classify(current, payload["process"], entry["recorded_at"]) == "ALIVE"
                    and entry["recorded_at"] < current["expires_at"] < payload["expires_at"], "SECURITY_INTEGRITY")
            current["expires_at"] = payload["expires_at"]
        elif kind == "WriterReleased":
            fields(payload, ("id", "reason"))
            current = result["writers"].get(payload["id"])
            require(current is not None and current["status"] == "REGISTERED", "SECURITY_INTEGRITY")
            if payload["reason"] == "GATEWAY_COMPLETED":
                require(current["origin"] == "EXECUTION_GATEWAY", "SECURITY_INTEGRITY")
            else:
                require(current["observation"] is not None and current["observation"]["status"] in ("DEAD", "PID_REUSED")
                        and payload["reason"] == current["observation"]["status"], "SECURITY_INTEGRITY")
            current.update(status="RELEASED", release_reason=payload["reason"])
        else:
            raise LedgerError("SECURITY_INTEGRITY")
        result.update(revision=entry["revision"], hash=entry["hash"])
    return result


def _classify(writer, actual, at):
    if actual["status"] != "ALIVE":
        return actual["status"]
    if (actual["pid"], actual["start_id"], actual["uid"]) != (writer["process"]["pid"], writer["process"]["start_id"], writer["process"]["uid"]):
        return "PID_REUSED"
    if writer["origin"] == "EXTERNAL_PROCESS" and actual["cwd"] != writer["workspace"]:
        return "LOCATION_CHANGED"
    return "LEASE_EXPIRED_LIVE" if at >= writer["expires_at"] else "ALIVE"


def _observe(writer, at):
    actual = process_identity(writer["process"]["pid"])
    return {"status": _classify(writer, actual, at), "at": at, "process": actual}


def _journal(root, configuration):
    return Journal(root, "writers", configuration["project"]["id"])


def _overlap(left, right):
    left, right = Path(left), Path(right)
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def assert_no_live_writers(root, configuration, workspace, *, clock=None):
    """Reject live/unknown registrations, including expired ones and path overlaps."""
    from .application import iso, now
    clock = clock or now
    with exclusive(root, "writers"):
        current = replay(_journal(root, configuration).read())
        for writer in current["writers"].values():
            if writer["status"] != "REGISTERED" or not _overlap(str(Path(workspace).resolve()), writer["workspace"]):
                continue
            observation = _observe(writer, iso(clock()))
            if observation["status"] not in ("DEAD", "PID_REUSED"):
                raise LedgerError("WRITER_CONFLICT", {"writer_id": writer["id"], "workspace": writer["workspace"],
                                                       "status": observation["status"]})


def _lease(root, configuration, run_id, lease_id, *, preparing=False):
    from .storage.sqlite import EventStore
    from .kernel.reducer import replay as project_replay
    with EventStore(root, configuration["project"]["id"]) as store:
        state = project_replay(store.events(run_id))
    require(state is not None and lease_id in state["effects"], "LEASE_NOT_FOUND")
    effect = state["effects"][lease_id]
    workspace = Path(root).resolve() / ".verantyx/worktrees" / lease_id
    require(effect["lease"]["resource_scope"] == str(workspace) and not workspace.is_symlink()
            and not workspace.parent.is_symlink(), "WRITER_WORKSPACE_INVALID")
    if preparing:
        require(effect["status"] == "STARTED" and not workspace.exists(), "WRITER_WORKSPACE_INVALID")
    else:
        require(workspace.is_dir() and effect["status"] in ("PREPARED", "CANDIDATE_TESTED"), "WRITER_WORKSPACE_INVALID")
    return workspace


def register(root, configuration, run_id, lease_id, *, pid, responsible, ttl=300, clock=None, _gateway=False):
    from .application import iso, now
    clock = clock or now
    require(type(ttl) is int and 1 <= ttl <= 3600 and type(responsible) is str and 1 <= len(responsible.strip()) <= 1000,
            "ARGUMENTS")
    require(not _gateway or pid == os.getpid(), "WRITER_PROCESS_INVALID")
    with exclusive(root, "writers"):
        workspace = _lease(root, configuration, run_id, lease_id, preparing=_gateway)
        assert_no_live_writers(root, configuration, workspace, clock=clock)
        actual = process_identity(pid)
        require(actual["status"] == "ALIVE" and actual["uid"] == os.geteuid(), "WRITER_PROCESS_INVALID")
        require(_gateway or actual["cwd"] == str(workspace), "WRITER_WORKSPACE_INVALID")
        journal = _journal(root, configuration)
        current = replay(journal.read())
        at = clock()
        # Persist the evidence that lets a later registration reuse a dead
        # writer's directory. Replay must not infer death from the live OS.
        for previous in current["writers"].values():
            if previous["status"] == "REGISTERED" and _overlap(previous["workspace"], str(workspace)):
                observation = _observe(previous, iso(at))
                require(observation["status"] in ("DEAD", "PID_REUSED"), "WRITER_CONFLICT")
                journal.append("WriterObserved", {"id": previous["id"], "observation": observation}, iso(at), len(journal.read()))
        value = {"id": str(uuid.uuid4()), "run_id": run_id, "effect_lease": lease_id, "workspace": str(workspace),
                 "responsible": responsible, "process": actual, "origin": "EXECUTION_GATEWAY" if _gateway else "EXTERNAL_PROCESS",
                 "expires_at": iso(at + timedelta(seconds=ttl))}
        journal.append("WriterRegistered", value, iso(at), len(journal.read()))
        return {"schema_version": 1, "ok": True, "command": "writer-register", "writer": value,
                "grants_write_authority": False, "responsible_identity": "OPERATOR_SUPPLIED_LABEL"}


def observe(root, configuration, writer_id=None, *, clock=None):
    from .application import iso, now
    clock = clock or now
    with exclusive(root, "writers"):
        journal = _journal(root, configuration)
        current = replay(journal.read())
        if writer_id is not None:
            require(writer_id in current["writers"], "WRITER_NOT_FOUND")
        results = []
        for writer in current["writers"].values():
            if (writer_id and writer["id"] != writer_id) or writer["status"] != "REGISTERED":
                continue
            at = iso(clock())
            observation = _observe(writer, at)
            journal.append("WriterObserved", {"id": writer["id"], "observation": observation}, at, len(journal.read()))
            results.append({"writer_id": writer["id"], **observation})
        return {"schema_version": 1, "ok": True, "command": "writer-observe", "observations": results}


def renew(root, configuration, writer_id, *, ttl=300, clock=None):
    from .application import iso, now
    clock = clock or now
    require(type(ttl) is int and 1 <= ttl <= 3600, "ARGUMENTS")
    with exclusive(root, "writers"):
        journal = _journal(root, configuration)
        current = replay(journal.read())
        writer = current["writers"].get(writer_id)
        require(writer is not None and writer["status"] == "REGISTERED", "WRITER_NOT_FOUND")
        at = clock()
        observation = _observe(writer, iso(at))
        require(observation["status"] == "ALIVE", "WRITER_PROCESS_INVALID")
        expiry = iso(at + timedelta(seconds=ttl))
        require(expiry > writer["expires_at"], "ARGUMENTS")
        journal.append("WriterRenewed", {"id": writer_id, "expires_at": expiry, "process": observation["process"]},
                       iso(at), current["revision"])
        return {"schema_version": 1, "ok": True, "command": "writer-renew", "writer_id": writer_id, "expires_at": expiry}


def release(root, configuration, writer_id, *, clock=None, _gateway=False):
    from .application import iso, now
    clock = clock or now
    with exclusive(root, "writers"):
        journal = _journal(root, configuration)
        current = replay(journal.read())
        writer = current["writers"].get(writer_id)
        require(writer is not None and writer["status"] == "REGISTERED", "WRITER_NOT_FOUND")
        at = iso(clock())
        observation = _observe(writer, at)
        if _gateway:
            require(writer["origin"] == "EXECUTION_GATEWAY" and writer["process"]["pid"] == os.getpid()
                    and observation["process"].get("start_id") == writer["process"]["start_id"], "WRITER_PROCESS_INVALID")
            reason = "GATEWAY_COMPLETED"
        else:
            require(observation["status"] in ("DEAD", "PID_REUSED"), "WRITER_STILL_RUNNING")
            reason = observation["status"]
        journal.append("WriterObserved", {"id": writer_id, "observation": observation}, at, current["revision"])
        journal.append("WriterReleased", {"id": writer_id, "reason": reason}, at, current["revision"] + 1)
        return {"schema_version": 1, "ok": True, "command": "writer-release", "writer_id": writer_id,
                "reason": reason, "process_signalled": False}


def inspect(root, configuration):
    current = replay(_journal(root, configuration).read())
    return {"schema_version": 1, "ok": True, "command": "writers", "revision": current["revision"],
            "writers": list(current["writers"].values()), "view": "RECORDED_OBSERVATIONS_ONLY",
            "grants_write_authority": False, "os_security_boundary": False}


@contextmanager
def execution_writer(root, configuration, run_id, lease_id, *, clock=None):
    """Record the actual gateway PID for the duration of candidate writes."""
    registered = register(root, configuration, run_id, lease_id, pid=os.getpid(),
                          responsible="Verantyx execution gateway", clock=clock, _gateway=True)
    try:
        yield registered["writer"]
    finally:
        release(root, configuration, registered["writer"]["id"], clock=clock, _gateway=True)
