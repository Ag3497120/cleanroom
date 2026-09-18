"""Explicit connection setup, inactive service files, and selected archive transport."""
from pathlib import Path
import hashlib
import os
import plistlib
import re

from .adapters.observations import read_document
from .application import iso, now, write_new_output
from .domain.codec import canonical, digest
from .errors import LedgerError
from .model_api import FORMAT, load_config, validate_config
from .storage.sqlite import EventStore, MAX_ARCHIVE, parse_archive


def _require(condition, reason, code="BRIDGE_CONFIG"):
    if not condition:
        raise LedgerError(code, {"reason": reason})


def configure_model(root, *, provider, model, endpoint, key_env, output, allow_loopback_http=False,
                    timeout=None, max_output_tokens=4096, max_response_bytes=262144, thinking=False, context_window=None):
    from .model_timeouts import default_timeout
    value = validate_config({"format": FORMAT, "provider": provider, "model": model, "endpoint": endpoint,
                             "key_env": key_env, "allow_loopback_http": allow_loopback_http,
                             "timeout": default_timeout(provider, endpoint, cloud=30) if timeout is None else timeout, "max_output_tokens": max_output_tokens,
                             "max_response_bytes": max_response_bytes,
                             **({"thinking": thinking} if thinking else {}),
                             **({"context_window": context_window} if context_window is not None else {})})
    _require(type(thinking) is bool or thinking == "auto", "MODEL_API_CONFIG")
    raw = (canonical(value) + "\n").encode("utf-8")
    write_new_output(root, output, raw)
    return {"schema_version": 1, "ok": True, "command": "model-api-config", "output": str(output),
            "provider": provider, "model": model, "config_sha256": digest(value),
            "file_sha256": hashlib.sha256(raw).hexdigest(), "network_called": False,
            "credentials_read": False, "proposal_only": True}


def check_model(path):
    value = load_config(path)
    return {"schema_version": 1, "ok": True, "command": "model-api-check", "provider": value["provider"],
            "model": value["model"], "config_sha256": digest(value), "network_called": False,
            "credentials_read": False, "proposal_only": True}


def _systemd_quote(value):
    # systemd has its own quote, specifier, and environment expansion rules.
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$") + '"'


def service_definition(root, *, executable, kind, output, interval=60, max_jobs=1):
    _require(kind in ("launchd", "systemd") and type(interval) is int and 10 <= interval <= 86400
             and type(max_jobs) is int and 1 <= max_jobs <= 100, "SERVICE_ARGUMENTS", "ARGUMENTS")
    root, binary, target = Path(root).resolve(), Path(executable), Path(output)
    _require(binary.is_absolute() and binary.is_file() and os.access(binary, os.X_OK), "SERVICE_EXECUTABLE")
    binary = binary.resolve()
    worker_sha256 = hashlib.sha256(read_document(binary, 64 * 1024 * 1024)).hexdigest()
    values = (str(root), str(binary), str(target))
    _require(all(not any(ord(c) < 32 or ord(c) == 127 for c in value) for value in values), "SERVICE_PATH")
    argv = [str(binary), "--project", str(root), "--json", "service-worker", "--max-jobs", str(max_jobs)]
    identity = "verantyx.proposals." + hashlib.sha256(str(root).encode()).hexdigest()[:16]
    outputs = []
    if kind == "launchd":
        _require(target.suffix == ".plist", "SERVICE_OUTPUT")
        specification = {"Label": identity, "ProgramArguments": argv, "StartInterval": interval,
                         "RunAtLoad": False, "WorkingDirectory": str(root), "ProcessType": "Background"}
        raw = plistlib.dumps(specification, fmt=plistlib.FMT_XML, sort_keys=True)
        _require(plistlib.loads(raw) == specification, "SERVICE_DEFINITION")
        outputs.append((target, raw))
    else:
        _require(target.suffix == ".service" and bool(re.fullmatch(r"[A-Za-z0-9_.-]+\.service", target.name)), "SERVICE_OUTPUT")
        service = ("[Unit]\nDescription=Verantyx bounded proposal worker\n\n[Service]\nType=oneshot\n"
                   + "ExecStart=" + " ".join(_systemd_quote(arg) for arg in argv) + "\n"
                   + f"TimeoutStartSec={600 * max_jobs + 60}\nUMask=0077\n")
        timer = ("[Unit]\nDescription=Verantyx proposal polling\n\n[Timer]\n"
                 + f"OnActiveSec={interval}\nOnUnitInactiveSec={interval}\nUnit={target.name}\nPersistent=false\n\n"
                 + "[Install]\nWantedBy=timers.target\n")
        outputs.extend(((target, service.encode()), (target.with_suffix(".timer"), timer.encode())))
    for path, _ in outputs:
        _require(path.parent.is_dir() and not path.exists() and not path.is_symlink(), "SERVICE_OUTPUT_EXISTS", "OUTPUT_EXISTS")
    written = []
    for path, raw in outputs:
        write_new_output(root, path, raw)
        written.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()})
    return {"schema_version": 1, "ok": True, "command": "service-definition", "kind": kind,
            "files": written, "argv": argv, "installed": False, "started": False,
            "worker_sha256": worker_sha256,
            "credentials_embedded": False, "proposal_only": True}


def _transport_directory(directory):
    path = Path(directory).expanduser().absolute()
    _require(path.is_dir() and not any(part.is_symlink() for part in (path, *path.parents)), "ARCHIVE_TRANSPORT_PATH", "STORE_PATH")
    return path


def archive_send(root, configuration, *, archive_id, directory):
    """Copy only an explicitly selected existing inert archive to a mounted peer."""
    _require(type(archive_id) is str and bool(re.fullmatch("[a-f0-9]{64}", archive_id)), "ARCHIVE_ID", "ARGUMENTS")
    with EventStore(root, configuration["project"]["id"]) as store:
        raw = store.export(archive_id).encode("utf-8")
    parse_archive(raw)
    _require(hashlib.sha256(raw).hexdigest() == archive_id, "ARCHIVE_SHA256", "ARCHIVE_INVALID")
    target = _transport_directory(directory) / (archive_id + ".jsonl")
    duplicate = target.exists()
    if duplicate:
        _require(read_document(target, MAX_ARCHIVE) == raw, "ARCHIVE_TRANSPORT_CONFLICT", "ARCHIVE_INVALID")
    else:
        write_new_output(root, target, raw)
    return {"schema_version": 1, "ok": True, "command": "archive-send", "archive_id": archive_id,
            "output": str(target), "duplicate": duplicate, "transport": "EXPLICIT_DIRECTORY",
            "trust": "ARCHIVE_ONLY", "authority_imported": False}


def archive_fetch(root, configuration, *, expected_sha256, directory, clock=now):
    _require(type(expected_sha256) is str and bool(re.fullmatch("[a-f0-9]{64}", expected_sha256)), "ARCHIVE_SHA256", "ARGUMENTS")
    source = _transport_directory(directory) / (expected_sha256 + ".jsonl")
    raw = read_document(source, MAX_ARCHIVE)
    _require(hashlib.sha256(raw).hexdigest() == expected_sha256, "ARCHIVE_SHA256", "ARCHIVE_INVALID")
    parse_archive(raw)
    with EventStore(root, configuration["project"]["id"], create=True) as store:
        receipt = store.import_archive(raw, iso(clock()))
    return {"schema_version": 1, "ok": True, "command": "archive-fetch", **receipt,
            "transport": "EXPLICIT_DIRECTORY", "trust": "ARCHIVE_ONLY", "authority_imported": False}
