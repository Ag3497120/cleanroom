"""Execution facts for an explicitly approved candidate check, not a proof."""
from copy import deepcopy
from jsonschema import Draft202012Validator
from ..agent_schema import obj, array
from .codec import digest
from ..errors import LedgerError

EVENT_ACTORS = {"WorkCheckStarted": "local_cli", "WorkCheckRecorded": "work_gateway"}
HASH = {"type": "string", "pattern": "^[a-f0-9]{64}$"}
TEXT = {"type": "string", "maxLength": 65536}
START = obj({
    "id": {"type": "string", "minLength": 1, "maxLength": 120},
    "label": {"type": "string", "minLength": 1, "maxLength": 240},
    "argv": array({"type": "string", "maxLength": 4096}, 64),
    "timeout": {"type": "integer", "minimum": 1, "maximum": 600},
    "manifest_sha256": HASH, "work_result_source_ref": TEXT,
    "execution_boundary": {"const": "EXPLICIT_TRUSTED_COMMAND_NOT_OS_SANDBOX"},
})
RESULT = obj({
    "id": {"type": "string", "minLength": 1, "maxLength": 120},
    "status": {"enum": ["PASSED", "FAILED", "TIMED_OUT", "START_FAILED", "INTERRUPTED", "UNKNOWN"]},
    "exit_code": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
    "elapsed_ms": {"type": "integer", "minimum": 0},
    "stdout": TEXT, "stderr": TEXT,
    "output_truncated": {"type": "boolean"},
    "output_sha256": HASH,
    "manifest_sha256": HASH, "reason": TEXT,
    "evidence_scope": {"const": "RECORDED_COMMAND_ON_CANDIDATE_COPY_ONLY"},
})


def manifest_hash(artifacts):
    return digest(sorted(({key: row[key] for key in ("path", "size", "sha256")}
                          for row in artifacts), key=lambda row: row["path"]))


def validate_payload(kind, payload):
    shape = {"WorkCheckStarted": START, "WorkCheckRecorded": RESULT}.get(kind)
    if shape is None or not Draft202012Validator(shape).is_valid(payload):
        raise LedgerError("WORK_CHECK_INVALID")
    if kind == "WorkCheckStarted" and not payload["argv"]:
        raise LedgerError("WORK_CHECK_INVALID")
    if kind == "WorkCheckRecorded":
        if (payload["status"] == "PASSED" and payload["exit_code"] != 0
                or payload["status"] == "FAILED" and (payload["exit_code"] is None or payload["exit_code"] == 0)
                or payload["output_sha256"] != digest({"stdout": payload["stdout"], "stderr": payload["stderr"]})):
            raise LedgerError("WORK_CHECK_INVALID")


def apply_event(state, event):
    if event["type"] not in EVENT_ACTORS:
        return
    from .events import citation
    payload = event["payload"]
    validate_payload(event["type"], payload)
    work = state.get("work_result")
    if not work or not work["artifacts"] or manifest_hash(work["artifacts"]) != payload["manifest_sha256"]:
        raise LedgerError("WORK_CHECK_BINDING")
    entries = state.setdefault("work_checks", {})
    stamp = {"source_ref": citation(event), "revision": event["revision"], "recorded_at": event["recorded_at"]}
    if event["type"] == "WorkCheckStarted":
        if payload["id"] in entries or payload["work_result_source_ref"] != work["source_ref"]:
            raise LedgerError("WORK_CHECK_BINDING")
        entries[payload["id"]] = {"request": {**deepcopy(payload), **stamp}, "result": None}
    else:
        entry = entries.get(payload["id"])
        if not entry or entry["result"] is not None:
            raise LedgerError("WORK_CHECK_BINDING")
        entry["result"] = {**deepcopy(payload), **stamp}
