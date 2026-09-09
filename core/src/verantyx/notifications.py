"""Review a selected due item, authorize an endpoint, then send it at most once."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import os
import sys

from .adapters.command_process import BASE_ENV, BoundedProcess
from .adapters.invocation_journal import InvocationJournal
from .adapters.observations import read_document
from .adapters.proposal_validation import valid_id
from .application import get_projection, iso, now, write_new_output
from .domain.codec import canonical, decode, digest
from .domain.events import fields, require, timestamp
from .errors import LedgerError
from .notification_http import validate_connection
from .storage.sqlite import EventStore


def _executor():
    # A permit covers the inspected sender implementation, not a mutable name.
    # Pin our package as well as the Python launcher; external runtime libraries
    # remain part of the explicitly trusted local installation.
    package = Path(__file__).resolve().parent
    runtime = Path(sys.executable).resolve()
    paths = [runtime, *sorted(package.rglob("*.py"))]
    require(len(paths) <= 256, "DOCUMENT_LIMIT")
    manifest = [{"path": str(path), "sha256": hashlib.sha256(read_document(path, 64 * 1024 * 1024)).hexdigest()}
                for path in paths]
    return {"argv": [str(runtime), "-I", str(package / "notification_http.py")], "manifest": manifest}


def _validate_lease(lease, delivery_id, project_id):
    fields(lease, ("packet_sha256", "packet", "connection", "executor", "ttl", "timeout", "project_id", "delivery_id", "authorized_at",
                   "expires_at", "intent_hash", "effect_class", "scope", "lease_sha256"))
    require(lease["delivery_id"] == delivery_id and lease["project_id"] == project_id, "LEASE_NOT_FOUND")
    intent = {k: lease[k] for k in ("packet_sha256", "packet", "connection", "executor", "ttl", "timeout", "project_id")}
    require(digest(intent) == lease["intent_hash"] and digest({k: v for k, v in lease.items() if k != "lease_sha256"}) == lease["lease_sha256"]
            and lease["effect_class"] == "IRREVERSIBLE_EXTERNAL" and lease["scope"] == "ONE_REVIEWED_PACKET_TO_ONE_ENDPOINT", "PRECONDITION_CHANGED")
    require(type(lease["ttl"]) is int and 1 <= lease["ttl"] <= 3600
            and type(lease["timeout"]) is int and 1 <= lease["timeout"] <= 60, "PRECONDITION_CHANGED")
    timestamp(lease["authorized_at"])
    timestamp(lease["expires_at"])
    at = datetime.strptime(lease["authorized_at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    require(iso(at + timedelta(seconds=lease["ttl"])) == lease["expires_at"], "PRECONDITION_CHANGED")
    require(hashlib.sha256((canonical(lease["packet"]) + "\n").encode()).hexdigest() == lease["packet_sha256"], "PRECONDITION_CHANGED")
    validate_connection(lease["connection"])


def _packet(root, configuration, run_id, candidate_id, exercise_id, as_of):
    from .learning_exercises import inspect_exercises
    require(all(valid_id(value) for value in (run_id, candidate_id, exercise_id)), "ARGUMENTS")
    timestamp(as_of)
    due = inspect_exercises(root, configuration, run_id, as_of=as_of)
    matches = [item for item in due["items"] if (item["candidate_id"], item["exercise_id"]) == (candidate_id, exercise_id)]
    require(len(matches) == 1, "LEARNING_STAGE")
    with EventStore(root, configuration["project"]["id"]) as store:
        state = get_projection(store, run_id)["state"]
    return {"format": "verantyx.notification-packet.v1", "project_id": configuration["project"]["id"],
            "run_id": run_id, "revision": state["revision"], "head_hash": state["head_hash"], "as_of": as_of,
            "item": matches[0], "scope": "SELECTED_DUE_LEARNING_ITEM_ONLY", "mastery_assessment": "NOT_ASSESSED",
            "contains_raw_answers": False}


def prepare(root, configuration, run_id, *, candidate_id, exercise_id, output, clock=now):
    packet = _packet(root, configuration, run_id, candidate_id, exercise_id, iso(clock()))
    raw = (canonical(packet) + "\n").encode()
    require(len(raw) <= 65536, "DOCUMENT_LIMIT")
    write_new_output(root, output, raw)
    return {"schema_version": 1, "ok": True, "command": "notification-packet", "packet": packet,
            "file_sha256": hashlib.sha256(raw).hexdigest(), "output": str(output), "network_called": False}


def _review(root, configuration, packet):
    fields(packet, ("format", "project_id", "run_id", "revision", "head_hash", "as_of", "item", "scope", "mastery_assessment", "contains_raw_answers"))
    require(packet["project_id"] == configuration["project"]["id"] and type(packet["item"]) is dict, "MEMORY_PACKET_INVALID")
    try:
        expected = _packet(root, configuration, packet["run_id"], packet["item"]["candidate_id"], packet["item"]["exercise_id"], packet["as_of"])
    except (KeyError, TypeError):
        raise LedgerError("MEMORY_PACKET_INVALID") from None
    require(canonical(expected) == canonical(packet), "MEMORY_PACKET_CHANGED")
    return packet


def authorize(root, configuration, *, packet_path, expected_sha256, endpoint, key, key_env=None,
              allow_loopback_http=False, ttl=300, timeout=30, clock=now):
    require(valid_id(key) and type(ttl) is int and 1 <= ttl <= 3600 and type(timeout) is int and 1 <= timeout <= 60, "ARGUMENTS")
    raw = read_document(packet_path, 65536)
    require(hashlib.sha256(raw).hexdigest() == expected_sha256, "MEMORY_PACKET_CHANGED")
    packet = _review(root, configuration, decode(raw, 65536))
    connection = validate_connection({"endpoint": endpoint, "key_env": key_env, "allow_loopback_http": allow_loopback_http})
    intent = {"packet_sha256": expected_sha256, "packet": packet, "connection": connection, "executor": _executor(), "ttl": ttl, "timeout": timeout,
              "project_id": configuration["project"]["id"]}
    with InvocationJournal(root, "notification-delivery", key) as journal:
        previous = journal.read("authorized")
        if previous:
            _validate_lease(previous, key, configuration["project"]["id"])
            require(previous["intent_hash"] == digest(intent), "IDEMPOTENCY_CONFLICT")
            return {"schema_version": 1, "ok": True, "command": "notification-authorize", "delivery_id": key,
                    "expires_at": previous["expires_at"], "duplicate": True, "network_called": False}
        at = clock()
        require(packet["as_of"] <= iso(at), "ARGUMENTS")
        lease = {**intent, "delivery_id": key, "authorized_at": iso(at), "expires_at": iso(at + timedelta(seconds=ttl)),
                 "intent_hash": digest(intent), "effect_class": "IRREVERSIBLE_EXTERNAL", "scope": "ONE_REVIEWED_PACKET_TO_ONE_ENDPOINT"}
        lease["lease_sha256"] = digest(lease)
        journal.write("authorized", lease)
    return {"schema_version": 1, "ok": True, "command": "notification-authorize", "delivery_id": key,
            "expires_at": lease["expires_at"], "effect_class": lease["effect_class"], "network_called": False, "duplicate": False}


def send(root, configuration, delivery_id, *, clock=now, fault=None):
    require(valid_id(delivery_id), "ARGUMENTS")
    with InvocationJournal(root, "notification-delivery", delivery_id) as journal:
        lease = journal.read("authorized")
        require(lease is not None and lease.get("delivery_id") == delivery_id
                and lease.get("project_id") == configuration["project"]["id"], "LEASE_NOT_FOUND")
        _validate_lease(lease, delivery_id, configuration["project"]["id"])
        response = journal.read("response")
        if response:
            return {**response, "duplicate": True}
        if journal.read("started"):
            raise LedgerError("BRIDGE_OUTCOME_UNKNOWN")
        require(_executor() == lease["executor"], "PRECONDITION_CHANGED")
        _review(root, configuration, lease["packet"])
        require(lease["authorized_at"] <= iso(clock()) < lease["expires_at"], "LEASE_EXPIRED")
        journal.write("started", {"lease_sha256": digest(lease), "recorded_at": iso(clock())})
        if fault:
            fault("after_started")
        try:
            _review(root, configuration, lease["packet"])
            require(_executor() == lease["executor"], "PRECONDITION_CHANGED")
            require(lease["authorized_at"] <= iso(clock()) < lease["expires_at"], "LEASE_EXPIRED")
            from .service_runtime import approval_deadline
            signed_expires_at = approval_deadline(root)
            expires_at = min(lease["expires_at"], signed_expires_at) if signed_expires_at else lease["expires_at"]
            command = {"argv": lease["executor"]["argv"], "cwd": None,
                       "env": {name: os.environ[name] for name in BASE_ENV if name in os.environ}, "notification_api": lease["connection"]}
            value = {"connection": lease["connection"], "packet": lease["packet"], "delivery_id": delivery_id,
                     "expires_at": expires_at, "timeout": lease["timeout"]}
            with BoundedProcess(command, timeout=lease["timeout"], max_output=65536) as process:
                receipt = decode(process.document(value), 65536)
            fields(receipt, ("status", "http_status", "response_bytes", "delivery_confirmed", "response_body_retained"))
            require(receipt["status"] == "HTTP_ACCEPTED" and type(receipt["http_status"]) is int and 200 <= receipt["http_status"] < 300
                    and type(receipt["response_bytes"]) is int and 0 <= receipt["response_bytes"] <= 65536
                    and receipt["delivery_confirmed"] is False and receipt["response_body_retained"] is False, "BRIDGE_PROTOCOL")
            if fault:
                fault("after_http")
            response = {"schema_version": 1, "ok": True, "command": "notification-send", "delivery_id": delivery_id,
                        "receipt": receipt, "scope": lease["scope"], "mastery_assessment": "NOT_ASSESSED", "duplicate": False}
            journal.write("response", response)
            return response
        except LedgerError as error:
            journal.write("failed", {"code": error.code, "outcome": "UNKNOWN_NO_RETRY"})
            raise
