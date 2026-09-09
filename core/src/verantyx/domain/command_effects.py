"""Pure, append-only lifecycle for explicitly trusted, unsandboxed commands."""
from copy import deepcopy
from pathlib import PurePosixPath

from .codec import canonical, digest
from ..adapters.observations import normalize_path
from ..adapters.proposal_validation import valid_id

EVENT_ACTORS = {"CommandEffectProposed": "local_cli", "CommandEffectAuthorized": "local_cli",
                "CommandEffectStarted": "command_gateway", "CommandEffectRecorded": "command_executor"}
CLASSES = ("READ_ONLY", "REVERSIBLE_LOCAL", "COMPENSATABLE_EXTERNAL", "IRREVERSIBLE_EXTERNAL")


def context_hash(state):
    return digest({k: state[k] for k in ("request_ref", "context", "proposal", "read_scope", "policy_context", "human_decisions")})


def validate_spec(spec):
    from .events import fields, require, paths
    fields(spec, ("description", "effect_class", "targets", "external_target", "input", "timeout", "max_output", "dependencies", "compensation"))
    for key in ("description", "compensation"):
        require(type(spec[key]) is str and len(spec[key]) <= 2000)
    require(bool(spec["description"].strip()) and spec["effect_class"] in CLASSES)
    paths(spec["targets"], empty=False)
    require(type(spec["external_target"]) is str and len(spec["external_target"]) <= 2000)
    if spec["effect_class"].endswith("_EXTERNAL"):
        require(bool(spec["external_target"].strip()))
    else:
        require(spec["external_target"] == "")
    if spec["effect_class"] == "COMPENSATABLE_EXTERNAL":
        require(bool(spec["compensation"].strip()))
    require(type(spec["timeout"]) in (int, float) and 0 < spec["timeout"] <= 600)
    require(type(spec["max_output"]) is int and 1024 <= spec["max_output"] <= 4 * 1024 * 1024)
    require(type(spec["dependencies"]) is list and len(spec["dependencies"]) <= 16)
    require(all(type(p) is str and PurePosixPath(p).is_absolute() and len(p) <= 4096 for p in spec["dependencies"]))
    require(len(set(spec["dependencies"])) == len(spec["dependencies"]))
    require(len(canonical(spec["input"]).encode()) <= 65536)
    return spec


def validate_target(value, source=False):
    from .events import fields, require, hash_value
    fields(value, ("path", "status", "sha256", "size", "source_ref") if source else ("path", "status", "sha256", "size"))
    normalize_path(value["path"])
    require(value["status"] in ("OBSERVED", "MISSING", "UNAVAILABLE"))
    if value["status"] == "OBSERVED":
        hash_value(value["sha256"])
        require(type(value["size"]) is int and value["size"] >= 0)
    else:
        require(value["sha256"] is None and value["size"] is None)
    if source:
        require(valid_id(value["source_ref"]) and value["status"] != "UNAVAILABLE")


def validate_payload(kind, payload):
    from .events import fields, require, uuid_value, timestamp, hash_value
    if kind == "CommandEffectProposed":
        fields(payload, ("plan",))
        p = payload["plan"]
        fields(p, ("id", "spec", "root", "context_hash", "proposal_hash", "rules_hash", "executor", "preconditions", "created_at", "expires_at"))
        uuid_value(p["id"])
        validate_spec(p["spec"])
        require(type(p["root"]) is str and PurePosixPath(p["root"]).is_absolute())
        for key in ("context_hash", "proposal_hash", "rules_hash"):
            hash_value(p[key])
        timestamp(p["created_at"])
        timestamp(p["expires_at"])
        require(p["created_at"] < p["expires_at"])
        e = p["executor"]
        fields(e, ("config_sha256", "command_hash", "argv_hash", "environment_hash", "cwd", "files", "hash", "isolation"))
        for key in ("config_sha256", "command_hash", "argv_hash", "environment_hash", "hash"):
            hash_value(e[key])
        require(type(e["cwd"]) is str and PurePosixPath(e["cwd"]).is_absolute())
        require(e["isolation"] == "NONE_TRUSTED_COMMAND")
        require(type(e["files"]) is dict and 1 <= len(e["files"]) <= 145)
        for path, sha in e["files"].items():
            require(type(path) is str and PurePosixPath(path).is_absolute())
            hash_value(sha)
        require(digest({k:v for k,v in e.items() if k != "hash"}) == e["hash"])
        require(type(p["preconditions"]) is list and len(p["preconditions"]) == len(p["spec"]["targets"]))
        for target, path in zip(p["preconditions"], p["spec"]["targets"]):
            validate_target(target, True)
            require(target["path"] == path)
    elif kind == "CommandEffectAuthorized":
        fields(payload, ("effect_id", "plan_hash", "basis_revision", "authorized_at", "expires_at", "accept_unsandboxed", "accept_irreversible", "reason"))
        uuid_value(payload["effect_id"])
        hash_value(payload["plan_hash"])
        require(type(payload["basis_revision"]) is int and payload["basis_revision"] > 0)
        timestamp(payload["authorized_at"])
        timestamp(payload["expires_at"])
        require(payload["authorized_at"] < payload["expires_at"] and payload["accept_unsandboxed"] is True)
        require(type(payload["accept_irreversible"]) is bool)
        require(type(payload["reason"]) is str and 1 <= len(payload["reason"].strip()) <= 4000)
    elif kind == "CommandEffectStarted":
        fields(payload, ("effect_id", "plan_hash", "authorization_ref", "started_at"))
        uuid_value(payload["effect_id"])
        hash_value(payload["plan_hash"])
        require(valid_id(payload["authorization_ref"]))
        timestamp(payload["started_at"])
    elif kind == "CommandEffectRecorded":
        fields(payload, ("effect_id", "plan_hash", "authorization_ref", "finished_at", "outcome", "process", "targets_after", "reason"))
        uuid_value(payload["effect_id"])
        hash_value(payload["plan_hash"])
        require(valid_id(payload["authorization_ref"]))
        timestamp(payload["finished_at"])
        require(payload["outcome"] in ("PROCESS_COMPLETED", "PROCESS_FAILED", "INVALIDATED", "OUTCOME_UNKNOWN"))
        require(type(payload["targets_after"]) is list and len(payload["targets_after"]) <= 32)
        for target in payload["targets_after"]:
            validate_target(target)
        process = payload["process"]
        if process is not None:
            fields(process, ("returncode", "stdout_sha256", "output_bytes", "elapsed_ms", "effect_confirmation"))
            require(type(process["returncode"]) is int and process["effect_confirmation"] == "NOT_ASSESSED")
            hash_value(process["stdout_sha256"])
            require(type(process["output_bytes"]) is int and process["output_bytes"] >= 0)
            require(type(process["elapsed_ms"]) is int and process["elapsed_ms"] >= 0)
        if payload["outcome"] in ("PROCESS_COMPLETED", "PROCESS_FAILED"):
            require(process is not None and payload["reason"] is None)
            require((process["returncode"] == 0) == (payload["outcome"] == "PROCESS_COMPLETED"))
        else:
            require(process is None and type(payload["reason"]) is str and 1 <= len(payload["reason"]) <= 160)


def apply_event(state, event):
    if event["type"] not in EVENT_ACTORS:
        return
    from .events import citation, require
    kind, p = event["type"], event["payload"]
    items = state.setdefault("command_effects", {})
    if kind == "CommandEffectProposed":
        plan = deepcopy(p["plan"])
        require(plan["id"] not in items and plan["created_at"] == event["recorded_at"])
        require(state["proposal"] is not None and digest(state["proposal"]) == plan["proposal_hash"])
        require(context_hash(state) == plan["context_hash"])
        for target in plan["preconditions"]:
            observation = state["observations"].get(target["source_ref"])
            require(observation is not None and all(observation[k] == target[k] for k in ("path", "status", "sha256", "size")))
            require(state["latest_observations"].get(target["path"]) == target["source_ref"])
            require(observation["observed_at"] <= plan["created_at"] < observation["expires_at"])
        items[plan["id"]] = {"plan": plan, "status": "PROPOSED", "source_ref": citation(event)}
        return
    item = items.get(p["effect_id"])
    require(item is not None and digest(item["plan"]) == p["plan_hash"])
    plan = item["plan"]
    if kind == "CommandEffectAuthorized":
        require(item["status"] == "PROPOSED" and p["authorized_at"] == event["recorded_at"])
        require(p["basis_revision"] == state["command_start_revision"] and context_hash(state) == plan["context_hash"])
        require(plan["created_at"] <= p["authorized_at"] < p["expires_at"] <= plan["expires_at"])
        require(plan["spec"]["effect_class"] != "IRREVERSIBLE_EXTERNAL" or p["accept_irreversible"] is True)
        item.update(status="AUTHORIZED", authorization=deepcopy(p), authorization_ref=citation(event))
    elif kind == "CommandEffectStarted":
        require(item["status"] == "AUTHORIZED" and p["authorization_ref"] == item["authorization_ref"])
        require(item["authorization"]["authorized_at"] <= p["started_at"] == event["recorded_at"])
        item.update(status="STARTED", started_at=p["started_at"], started_ref=citation(event))
    else:
        require(item["status"] == "STARTED" and p["authorization_ref"] == item["authorization_ref"])
        require(item["started_at"] <= p["finished_at"] == event["recorded_at"])
        if p["outcome"] in ("PROCESS_COMPLETED", "PROCESS_FAILED"):
            require(context_hash(state) == plan["context_hash"])
            require(item["started_at"] < item["authorization"]["expires_at"] and p["finished_at"] < item["authorization"]["expires_at"])
            require(p["process"]["output_bytes"] <= plan["spec"]["max_output"])
            require([t["path"] for t in p["targets_after"]] == plan["spec"]["targets"])
        item.update(status=p["outcome"], receipt=deepcopy(p), receipt_ref=citation(event))
