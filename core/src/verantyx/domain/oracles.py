"""Pure contracts for parent-compared, separate-process candidate observations."""
from copy import deepcopy
import base64
import binascii
import hashlib

from .codec import canonical, decode, digest
from .verification import AXES
from ..adapters.observations import normalize_path
from ..adapters.proposal_validation import valid_id
from ..errors import LedgerError

EVENT_ACTORS = {"OraclePlanned": "local_cli", "OracleStarted": "oracle_gateway", "OracleRecorded": "parent_oracle"}
SCOPE = "FIXED_CANDIDATE_JSON_IO_CASES_ONLY"
MAX_BYTES = 32768


def validate_spec(spec):
    from .events import fields, require
    fields(spec, ("claim_id", "target_path", "function", "property", "cases", "negative_controls", "oracle", "provenance", "timeout", "max_output"))
    require(valid_id(spec["claim_id"]) and valid_id(spec["function"]))
    require(spec["function"].isidentifier() and not spec["function"].startswith("_"))
    normalize_path(spec["target_path"])
    require(spec["target_path"].endswith(".py"))
    require(type(spec["property"]) is str and 1 <= len(spec["property"].strip()) <= 2000)
    require(type(spec["timeout"]) in (int, float) and 0 < spec["timeout"] <= 30)
    require(type(spec["max_output"]) is int and 1024 <= spec["max_output"] <= MAX_BYTES)
    require(type(spec["cases"]) is list and 1 <= len(spec["cases"]) <= 8)
    require(type(spec["negative_controls"]) is list and 1 <= len(spec["negative_controls"]) <= 8)
    ids = set()
    for case in spec["cases"]:
        fields(case, ("id", "input", "expected"))
        require(valid_id(case["id"]) and case["id"] not in ids)
        ids.add(case["id"])
        require(len(canonical(case).encode()) <= 4096)
    controls = set()
    for control in spec["negative_controls"]:
        fields(control, ("id", "case_id", "counterexample"))
        require(valid_id(control["id"]) and control["id"] not in controls and control["case_id"] in ids)
        controls.add(control["id"])
        require(len(canonical(control).encode()) <= 4096)
    fields(spec["oracle"], ("description", "source_refs"))
    require(type(spec["oracle"]["description"]) is str and 1 <= len(spec["oracle"]["description"].strip()) <= 2000)
    refs = spec["oracle"]["source_refs"]
    require(type(refs) is list and len(refs) <= 16 and len(set(refs)) == len(refs) and all(valid_id(ref) for ref in refs))
    fields(spec["provenance"], AXES)
    require(all(type(v) is str and len(v) <= 1000 for v in spec["provenance"].values()))
    return spec


def origins(plan):
    return {"axes": {axis: {"declaration": plan["spec"]["provenance"][axis], "assurance": "DECLARED_ONLY"} for axis in AXES},
            "observed": {"implementation": plan["engine_hash"], "data": plan["target"]["sha256"],
                         "environment": plan["engine"]["environment_hash"], "oracle_source_refs": plan["spec"]["oracle"]["source_refs"],
                         "comparison_process": "TRUSTED_PARENT", "candidate_process": "SEPARATE_MACOS_SEATBELT",
                         "expected_values_sent_to_candidate": False},
            "expected_value_correctness": "NOT_ASSESSED", "independence": "NOT_ESTABLISHED", "summary": "I0_UNASSESSED"}


def compare(plan, observations):
    """Recalculate evidence from observed bytes, never from a candidate verdict."""
    from .events import fields, require
    require(type(observations) is list and len(observations) == len(plan["spec"]["cases"]))
    checks = []
    for case, obs in zip(plan["spec"]["cases"], observations):
        fields(obs, ("case_id", "outcome", "stdout_base64", "stdout_sha256", "returncode", "reason"))
        require(obs["case_id"] == case["id"] and obs["outcome"] in ("RETURNED", "UNAVAILABLE"))
        require(obs["returncode"] is None or type(obs["returncode"]) is int)
        require(obs["reason"] is None or obs["reason"] in ("BRIDGE_TIMEOUT", "BRIDGE_OUTPUT_LIMIT", "BRIDGE_PROCESS_FAILED", "BRIDGE_PROTOCOL", "BRIDGE_START_FAILED", "ORACLE_PROTOCOL"))
        require(type(obs["stdout_base64"]) is str and len(obs["stdout_base64"]) <= 44000)
        try:
            raw = base64.b64decode(obs["stdout_base64"], validate=True)
        except (ValueError, binascii.Error):
            raise LedgerError("ORACLE_RECEIPT_INVALID") from None
        require(len(raw) <= plan["spec"]["max_output"] and base64.b64encode(raw).decode() == obs["stdout_base64"])
        require(hashlib.sha256(raw).hexdigest() == obs["stdout_sha256"])
        actual, passed, reason = None, None, obs["reason"]
        if obs["outcome"] == "RETURNED":
            require(obs["returncode"] == 0 and reason is None)
            try:
                frame = decode(raw, plan["spec"]["max_output"])
                fields(frame, ("protocol", "value"))
                require(frame["protocol"] == "verantyx.oracle.return.v1")
                actual = digest(frame["value"])
                passed = canonical(frame["value"]) == canonical(case["expected"])
            except LedgerError:
                reason = "ORACLE_PROTOCOL"
        else:
            require(reason is not None and raw == b"")
        checks.append({"id": case["id"], "passed": passed, "actual_hash": actual, "reason": reason})
    by_id = {c["id"]: c for c in plan["spec"]["cases"]}
    controls = [{"id": control["id"], "case_id": control["case_id"],
                 "rejected": canonical(control["counterexample"]) != canonical(by_id[control["case_id"]]["expected"])}
                for control in plan["spec"]["negative_controls"]]
    if any(c["passed"] is None for c in checks):
        closure, status = "UNKNOWN", "UNKNOWN"
    elif any(not c["rejected"] for c in controls):
        closure, status = "CONTESTED", "CONTESTED"
    elif all(c["passed"] for c in checks):
        closure, status = "BOUNDED", "SUPPORTED"
    else:
        closure, status = "REFUTED", "REFUTED"
    return {"method": "TEST", "closure": closure, "epistemic_status": status,
            "scope": SCOPE, "property": plan["spec"]["property"], "checks": checks, "negative_controls": controls,
            "negative_control_scope": "PARENT_COMPARATOR_REJECTS_DECLARED_COUNTEREXAMPLE_VALUES",
            "prose_entailment": "NOT_ASSESSED", "independence": "NOT_ESTABLISHED", "adoption_authorized": False}


def validate_payload(kind, payload):
    from .events import fields, require, timestamp, hash_value, uuid_value
    if kind == "OraclePlanned":
        fields(payload, ("plan",))
        p = payload["plan"]
        fields(p, ("id", "spec", "claim_hash", "proposal_hash", "target", "created_at", "expires_at", "engine", "engine_hash", "origins"))
        uuid_value(p["id"])
        validate_spec(p["spec"])
        for name in ("claim_hash", "proposal_hash", "engine_hash"):
            hash_value(p[name])
        fields(p["target"], ("path", "sha256", "size", "source_ref"))
        require(p["target"]["path"] == p["spec"]["target_path"] and valid_id(p["target"]["source_ref"]))
        hash_value(p["target"]["sha256"])
        require(type(p["target"]["size"]) is int and 0 <= p["target"]["size"] <= 65536)
        timestamp(p["created_at"])
        timestamp(p["expires_at"])
        require(p["created_at"] < p["expires_at"])
        fields(p["engine"], ("id", "source_sha256", "runner_sha256", "python_sha256", "environment_hash", "platform", "precedent"))
        require(p["engine"]["id"] == "parent.python-json.v1")
        for name in ("source_sha256", "runner_sha256", "python_sha256", "environment_hash"):
            hash_value(p["engine"][name])
        require(type(p["engine"]["platform"]) is str)
        fields(p["engine"]["precedent"], ("backend", "path", "sha256"))
        hash_value(p["engine"]["precedent"]["sha256"])
        require(digest(p["engine"]) == p["engine_hash"] and digest(origins(p)) == digest(p["origins"]))
    else:
        base = ("oracle_id", "plan_hash", "started_at") if kind == "OracleStarted" else ("oracle_id", "plan_hash", "finished_at", "outcome", "observations", "result", "reason")
        fields(payload, base)
        uuid_value(payload["oracle_id"])
        hash_value(payload["plan_hash"])
        timestamp(payload["started_at"] if kind == "OracleStarted" else payload["finished_at"])
        if kind == "OracleRecorded":
            require(payload["outcome"] in ("COMPLETED", "INVALIDATED", "OUTCOME_UNKNOWN"))
            if payload["outcome"] == "COMPLETED":
                require(type(payload["observations"]) is list and type(payload["result"]) is dict and payload["reason"] is None)
            else:
                require(payload["observations"] is None and payload["result"] is None)
                require(payload["reason"] in ("INTERRUPTED", "PLAN_EXPIRED", "TARGET_CHANGED", "TARGET_UNAVAILABLE", "ORACLE_CHANGED", "ENGINE_CHANGED", "PROPOSAL_CHANGED", "ISOLATION_UNAVAILABLE"))


def apply_event(state, event):
    if event["type"] not in EVENT_ACTORS:
        return
    from .events import require, citation
    kind, p = event["type"], event["payload"]
    items = state.setdefault("oracles", {})
    if kind == "OraclePlanned":
        plan = deepcopy(p["plan"])
        require(plan["id"] not in items and plan["created_at"] == event["recorded_at"])
        require(state["proposal"] is not None and digest(state["proposal"]) == plan["proposal_hash"])
        claim = next((c for c in state["proposal"]["claims"] if c["id"] == plan["spec"]["claim_id"]), None)
        require(claim is not None and digest(claim) == plan["claim_hash"])
        target = state["observations"].get(plan["target"]["source_ref"])
        require(target and target["status"] == "OBSERVED" and all(target[k] == plan["target"][k] for k in ("path", "sha256", "size")))
        for ref in [plan["target"]["source_ref"], *plan["spec"]["oracle"]["source_refs"]]:
            obs = state["observations"].get(ref)
            require(obs and obs["status"] == "OBSERVED" and obs["observed_at"] <= plan["created_at"] < obs["expires_at"])
            require(state["latest_observations"].get(obs["path"]) == ref)
        items[plan["id"]] = {"plan": plan, "status": "PLANNED", "source_ref": citation(event)}
        return
    item = items.get(p["oracle_id"])
    require(item is not None and p["plan_hash"] == digest(item["plan"]))
    plan = item["plan"]
    if kind == "OracleStarted":
        require(item["status"] == "PLANNED" and p["started_at"] == event["recorded_at"] and p["started_at"] >= plan["created_at"])
        item.update(status="STARTED", started_at=p["started_at"], started_ref=citation(event))
    else:
        require(item["status"] == "STARTED" and p["finished_at"] == event["recorded_at"] and p["finished_at"] >= item["started_at"])
        if p["outcome"] == "COMPLETED":
            require(item["started_at"] < plan["expires_at"] and p["finished_at"] < plan["expires_at"])
            require(digest(state["proposal"]) == plan["proposal_hash"])
            for ref in [plan["target"]["source_ref"], *plan["spec"]["oracle"]["source_refs"]]:
                before = state["observations"][ref]
                latest = state["observations"][state["latest_observations"][before["path"]]]
                require(latest["status"] == "OBSERVED" and latest["sha256"] == before["sha256"])
                require(latest["observed_at"] <= p["finished_at"] < latest["expires_at"])
            require(digest(compare(plan, p["observations"])) == digest(p["result"]), "ORACLE_RECEIPT_INVALID")
        item.update(status=p["outcome"], receipt=deepcopy(p), receipt_ref=citation(event))
