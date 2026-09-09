"""Versioned, pure verification contracts. No I/O occurs during replay."""
from copy import deepcopy
import base64
import binascii
import hashlib
import re

from .codec import canonical, decode, digest
from ..adapters.proposal_validation import valid_id
from ..errors import LedgerError

MAX_INPUT = 65536
AXES = ("model", "provider", "implementation", "dependencies", "oracle", "data", "environment")
METHODS = ("OBSERVATION", "TEST", "REPRODUCTION", "NEGATIVE_CONTROL")
EVENT_ACTORS = {"VerificationPlanned": "local_cli", "VerificationStarted": "verification_gateway",
                "VerificationRecorded": "bounded_verifier"}
CHECKS = ("bytes.sha256", "bytes.size", "text.equals", "text.contains", "json.equals", "json.type")


def _require(value, code="VERIFICATION_INVALID"):
    if not value:
        raise LedgerError(code)


def _fields(value, names):
    _require(type(value) is dict and set(value) == set(names))


def _string(value, limit=2000, empty=False):
    _require(type(value) is str and (empty or bool(value.strip())) and len(value) <= limit)


def unseal(value):
    _require(type(value) is str and len(value) <= ((MAX_INPUT + 2) // 3) * 4)
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise LedgerError("VERIFICATION_INVALID") from None
    _require(len(raw) <= MAX_INPUT and base64.b64encode(raw).decode("ascii") == value)
    return raw


def validate_spec(value):
    """Only local CLI plans use this shape. Models have no verification field."""
    _fields(value, ("claim_id", "target_path", "property", "method", "checks", "negative_controls",
                    "reproduces", "oracle", "provenance"))
    _require(valid_id(value["claim_id"]))
    from ..adapters.observations import normalize_path
    normalize_path(value["target_path"])
    _string(value["property"])
    _require(value["method"] in METHODS)
    _require(type(value["checks"]) is list and len(value["checks"]) <= 16)
    _require(bool(value["checks"]) == (value["method"] != "OBSERVATION"))
    seen = set()
    for check in value["checks"]:
        _fields(check, ("id", "kind", "pointer", "expected"))
        _require(valid_id(check["id"]) and check["id"] not in seen)
        seen.add(check["id"])
        _require(check["kind"] in CHECKS)
        pointer = check["pointer"]
        _require(type(pointer) is str and len(pointer) <= 1024)
        if check["kind"].startswith("json."):
            _require(pointer == "" or (pointer.startswith("/") and not re.search(r"~(?![01])", pointer)))
        else:
            _require(pointer == "")
        if check["kind"] == "bytes.sha256":
            _require(type(check["expected"]) is str and bool(re.fullmatch(r"[0-9a-f]{64}", check["expected"])))
        elif check["kind"] == "bytes.size":
            _require(type(check["expected"]) is int and 0 <= check["expected"] <= MAX_INPUT)
        elif check["kind"].startswith("text."):
            _string(check["expected"], MAX_INPUT, empty=check["kind"] == "text.equals")
        elif check["kind"] == "json.type":
            _require(check["expected"] in ("null", "boolean", "integer", "number", "string", "array", "object"))
        _require(len(canonical(check["expected"]).encode("utf-8")) <= 32768)
    controls = value["negative_controls"]
    _require(type(controls) is list and len(controls) <= 8)
    if value["method"] == "NEGATIVE_CONTROL":
        _require(bool(controls))
    elif value["method"] != "REPRODUCTION":
        _require(not controls)
    control_ids = set()
    for control in controls:
        _fields(control, ("id", "input_base64"))
        _require(valid_id(control["id"]) and control["id"] not in control_ids)
        control_ids.add(control["id"])
        unseal(control["input_base64"])
    _require(sum(len(c["input_base64"]) for c in controls) <= 90000)
    from .events import uuid_value
    if value["method"] == "REPRODUCTION":
        uuid_value(value["reproduces"])
    else:
        _require(value["reproduces"] is None)
    _fields(value["oracle"], ("description", "source_refs"))
    _string(value["oracle"]["description"])
    refs = value["oracle"]["source_refs"]
    _require(type(refs) is list and len(refs) <= 16 and all(valid_id(ref) for ref in refs))
    _require(len(set(refs)) == len(refs))
    _fields(value["provenance"], AXES)
    for declaration in value["provenance"].values():
        _string(declaration, 1000, empty=True)
    _require(len(canonical(value).encode("utf-8")) <= 192000)
    return value


def _pointer(document, pointer):
    current = document
    for part in pointer.split("/")[1:] if pointer else []:
        key = part.replace("~1", "/").replace("~0", "~")
        if type(current) is list:
            if not re.fullmatch(r"0|[1-9][0-9]*", key) or len(key) > 8:
                raise KeyError(key)
            current = current[int(key)]
        elif type(current) is dict:
            current = current[key]
        else:
            raise KeyError(key)
    return current


def check_input(raw, checks):
    results = []
    for check in checks:
        try:
            kind = check["kind"]
            if kind == "bytes.sha256":
                actual = hashlib.sha256(raw).hexdigest()
            elif kind == "bytes.size":
                actual = len(raw)
            elif kind.startswith("text."):
                actual = raw.decode("utf-8")
            else:
                actual = _pointer(decode(raw, MAX_INPUT), check["pointer"])
                if kind == "json.type":
                    actual = {type(None): "null", bool: "boolean", int: "integer", float: "number",
                              str: "string", list: "array", dict: "object"}[type(actual)]
            passed = check["expected"] in actual if kind == "text.contains" else canonical(actual) == canonical(check["expected"])
            results.append({"id": check["id"], "passed": passed, "actual_hash": digest(actual), "error": None})
        except (LedgerError, UnicodeError, KeyError, IndexError, TypeError):
            # Invalid input is a rejected predicate, never a successful test.
            results.append({"id": check["id"], "passed": False, "actual_hash": None, "error": "INPUT_NOT_APPLICABLE"})
    return results


def evidence_result(plan, raw, prior=None):
    """Calculate solely from sealed data and the recorded contract."""
    spec = plan["spec"]
    checks = check_input(raw, spec["checks"])
    controls = []
    for control in spec["negative_controls"]:
        result = check_input(unseal(control["input_base64"]), spec["checks"])
        controls.append({"id": control["id"], "rejected": not all(c["passed"] for c in result), "checks": result})
    reproduced = None
    if spec["method"] == "REPRODUCTION":
        _require(prior is not None and prior.get("receipt") is not None)
        original = prior["receipt"]
        reproduced = (original["input_sha256"] == hashlib.sha256(raw).hexdigest()
                      and digest(original["result"]["checks"]) == digest(checks)
                      and digest(original["result"]["negative_controls"]) == digest(controls))
    if spec["method"] == "OBSERVATION":
        status, closure, reason = "UNKNOWN", "SUPPORTED", "OBSERVATION_ONLY"
    elif any(not item["rejected"] for item in controls) or reproduced is False:
        status, closure, reason = "CONTESTED", "CONTESTED", "CONTROL_FAILED" if controls else "REPRODUCTION_DISAGREES"
    elif all(item["passed"] for item in checks):
        status, closure, reason = "SUPPORTED", "BOUNDED", None
    else:
        status, closure, reason = "REFUTED", "REFUTED", "PROPERTY_REFUTED"
    return {"method": spec["method"], "closure": closure, "epistemic_status": status,
            "blocker": "EVIDENCE_MISSING" if reason == "OBSERVATION_ONLY" else "NONE", "reason": reason,
            "checks": checks, "negative_controls": controls, "reproduction_match": reproduced,
            "property": spec["property"], "scope": "FIXED_TARGET_AND_PREDICATES_ONLY",
            "prose_entailment": "NOT_ASSESSED", "independence": "NOT_ESTABLISHED"}


def validate_payload(kind, payload):
    from .events import timestamp, uuid_value, hash_value, fields
    if kind == "VerificationPlanned":
        fields(payload, ("plan",))
        plan = payload["plan"]
        fields(plan, ("id", "spec", "claim_hash", "proposal_hash", "target", "created_at", "expires_at",
                      "engine", "engine_hash", "origins"))
        uuid_value(plan["id"])
        validate_spec(plan["spec"])
        hash_value(plan["claim_hash"])
        hash_value(plan["proposal_hash"])
        target = plan["target"]
        fields(target, ("path", "sha256", "size", "source_ref"))
        _require(target["path"] == plan["spec"]["target_path"] and valid_id(target["source_ref"]))
        hash_value(target["sha256"])
        _require(type(target["size"]) is int and 0 <= target["size"] <= MAX_INPUT)
        timestamp(plan["created_at"])
        timestamp(plan["expires_at"])
        _require(plan["created_at"] < plan["expires_at"])
        fields(plan["engine"], ("id", "source_sha256", "python", "platform"))
        _require(plan["engine"]["id"] == "bounded.predicates.v1")
        hash_value(plan["engine"]["source_sha256"])
        _string(plan["engine"]["python"], 1000)
        _string(plan["engine"]["platform"], 1000)
        _require(digest(plan["engine"]) == plan["engine_hash"])
        expected = origins(plan)
        _require(digest(plan["origins"]) == digest(expected))
    elif kind == "VerificationStarted":
        fields(payload, ("verification_id", "plan_hash", "started_at"))
        uuid_value(payload["verification_id"])
        hash_value(payload["plan_hash"])
        timestamp(payload["started_at"])
    elif kind == "VerificationRecorded":
        fields(payload, ("verification_id", "plan_hash", "finished_at", "outcome", "input_base64", "input_sha256", "result", "reason"))
        uuid_value(payload["verification_id"])
        hash_value(payload["plan_hash"])
        timestamp(payload["finished_at"])
        _require(payload["outcome"] in ("COMPLETED", "INVALIDATED", "OUTCOME_UNKNOWN"))
        if payload["outcome"] == "COMPLETED":
            raw = unseal(payload["input_base64"])
            _require(hashlib.sha256(raw).hexdigest() == payload["input_sha256"])
            _require(payload["reason"] is None and type(payload["result"]) is dict)
        else:
            _require(payload["input_base64"] is None and payload["input_sha256"] is None and payload["result"] is None)
            _require(payload["reason"] in ("TARGET_CHANGED", "TARGET_UNAVAILABLE", "PLAN_EXPIRED", "PROPOSAL_CHANGED", "ENGINE_CHANGED", "INTERRUPTED", "ORACLE_CHANGED", "ORACLE_UNAVAILABLE"))


def origins(plan):
    return {"axes": {axis: {"declaration": plan["spec"]["provenance"][axis], "assurance": "DECLARED_ONLY"} for axis in AXES},
            "observed": {"implementation": plan["engine"]["source_sha256"], "data": plan["target"]["sha256"],
                         "environment": {"python": plan["engine"]["python"], "platform": plan["engine"]["platform"]},
                         "oracle_source_refs": plan["spec"]["oracle"]["source_refs"]},
            "independence": "NOT_ESTABLISHED", "summary": "I0_UNASSESSED"}


def apply_event(state, event):
    if event["type"] not in EVENT_ACTORS:
        return
    from .events import citation, require
    items = state.setdefault("verifications", {})
    payload, kind = event["payload"], event["type"]
    if kind == "VerificationPlanned":
        plan = deepcopy(payload["plan"])
        require(plan["id"] not in items)
        require(state["proposal"] is not None and plan["proposal_hash"] == digest(state["proposal"]))
        claims = {claim["id"]: claim for claim in state["proposal"]["claims"]}
        claim = claims.get(plan["spec"]["claim_id"])
        require(claim is not None and digest(claim) == plan["claim_hash"])
        target = plan["target"]
        require(target["path"] in state["read_scope"])
        observation = state["observations"].get(target["source_ref"])
        require(observation and observation["status"] == "OBSERVED" and all(observation[k] == target[k] for k in ("path", "sha256", "size")))
        require(state["latest_observations"].get(target["path"]) == target["source_ref"])
        require(observation["observed_at"] <= plan["created_at"] < observation["expires_at"])
        require(plan["created_at"] == event["recorded_at"])
        for ref in plan["spec"]["oracle"]["source_refs"]:
            source = state["observations"].get(ref)
            require(source and source["status"] == "OBSERVED")
            require(source["observed_at"] <= plan["created_at"] < source["expires_at"])
            require(state["latest_observations"].get(source["path"]) == ref)
        if plan["spec"]["method"] == "REPRODUCTION":
            prior = items.get(plan["spec"]["reproduces"])
            require(prior and prior["status"] == "COMPLETED")
            original = prior["plan"]
            require(original["spec"]["method"] != "OBSERVATION")
            require(original["claim_hash"] == plan["claim_hash"] and original["proposal_hash"] == plan["proposal_hash"])
            require(digest(original["spec"]["checks"]) == digest(plan["spec"]["checks"]) and original["spec"]["property"] == plan["spec"]["property"])
            require(digest(original["spec"]["negative_controls"]) == digest(plan["spec"]["negative_controls"]))
            require(all(original["target"][k] == target[k] for k in ("path", "sha256", "size")))
        items[plan["id"]] = {"plan": plan, "status": "PLANNED", "source_ref": citation(event)}
    else:
        item = items.get(payload["verification_id"])
        require(item and payload["plan_hash"] == digest(item["plan"]))
        plan = item["plan"]
        if kind == "VerificationStarted":
            require(item["status"] == "PLANNED")
            require(payload["started_at"] == event["recorded_at"] and plan["created_at"] <= payload["started_at"])
            item.update(status="STARTED", started_at=payload["started_at"], started_ref=citation(event))
        else:
            require(item["status"] == "STARTED")
            require(payload["finished_at"] == event["recorded_at"] and item["started_at"] <= payload["finished_at"])
            if payload["outcome"] == "COMPLETED":
                require(payload["finished_at"] < plan["expires_at"] and item["started_at"] < plan["expires_at"])
                require(digest(state["proposal"]) == plan["proposal_hash"])
                require(payload["input_sha256"] == plan["target"]["sha256"])
                raw = unseal(payload["input_base64"])
                require(len(raw) == plan["target"]["size"])
                current = state["observations"].get(state["latest_observations"].get(plan["target"]["path"]))
                require(current and current["status"] == "OBSERVED" and current["sha256"] == payload["input_sha256"])
                require(current["observed_at"] <= payload["finished_at"] < current["expires_at"])
                for ref in plan["spec"]["oracle"]["source_refs"]:
                    source = state["observations"][ref]
                    current_oracle = state["observations"][state["latest_observations"][source["path"]]]
                    require(current_oracle["status"] == "OBSERVED" and current_oracle["sha256"] == source["sha256"])
                    require(current_oracle["observed_at"] <= payload["finished_at"] < current_oracle["expires_at"])
                prior = items.get(plan["spec"]["reproduces"])
                # Python container equality treats True as 1 and False as 0.
                # Evidence is a typed JSON contract, so compare its canonical form.
                require(digest(payload["result"]) == digest(evidence_result(plan, raw, prior)), "VERIFICATION_RECEIPT_INVALID")
            item.update(status=payload["outcome"], receipt=deepcopy(payload), receipt_ref=citation(event))


def assess_claim(state, claim, as_of):
    """Only current, bound property evidence participates in the projection."""
    active, historical = [], []
    for item in state.get("verifications", {}).values():
        plan = item["plan"]
        if plan["spec"]["claim_id"] != claim["id"] or plan["claim_hash"] != digest(claim) or plan["proposal_hash"] != digest(state["proposal"]):
            continue
        summary = {"verification_id": plan["id"], "source_ref": item.get("receipt_ref", item["source_ref"]),
                   "property": plan["spec"]["property"], "method": plan["spec"]["method"], "status": item["status"],
                   "origins": plan["origins"], "target": plan["target"], "expires_at": plan["expires_at"]}
        reason = "VERIFICATION_INCOMPLETE"
        if item["status"] == "COMPLETED":
            reason = None
            if not plan["created_at"] <= as_of < plan["expires_at"]:
                reason = "STALE_SOURCE"
            current = state["observations"].get(state["latest_observations"].get(plan["target"]["path"]))
            if not current or current["status"] != "OBSERVED" or current["sha256"] != plan["target"]["sha256"]:
                reason = "SOURCE_CHANGED"
            elif not current["observed_at"] <= as_of < current["expires_at"]:
                reason = "STALE_SOURCE"
            for ref in plan["spec"]["oracle"]["source_refs"]:
                source = state["observations"][ref]
                recent = state["observations"][state["latest_observations"][source["path"]]]
                if recent["status"] != "OBSERVED" or recent["sha256"] != source["sha256"]:
                    reason = "SOURCE_CHANGED"
                elif not recent["observed_at"] <= as_of < recent["expires_at"]:
                    reason = "STALE_SOURCE"
            summary["result"] = item["receipt"]["result"]
            if reason is None:
                active.append(summary)
        summary["current"] = reason is None
        summary["reason"] = reason
        historical.append(summary)
    if not historical:
        return None
    statuses = {item["result"]["epistemic_status"] for item in active}
    if "CONTESTED" in statuses or {"SUPPORTED", "REFUTED"} <= statuses:
        status, closure, code = "CONTESTED", "CONTESTED", "VERIFICATION_CONFLICT"
    elif "REFUTED" in statuses:
        status, closure, code = "REFUTED", "REFUTED", "PROPERTY_REFUTED"
    elif "SUPPORTED" in statuses:
        status, closure, code = "SUPPORTED", "BOUNDED", None
    else:
        stale = next((item["reason"] for item in historical if item["reason"] in ("STALE_SOURCE", "SOURCE_CHANGED")), None)
        status, closure, code = "UNKNOWN", "SUPPORTED" if active else "UNKNOWN", stale or "CLAIM_NOT_VERIFIED"
    property_evidence = {"epistemic_status": status, "closure": closure,
                         "blocker": "OBSERVATION_STALE" if code in ("STALE_SOURCE", "SOURCE_CHANGED") else (
                             "EVIDENCE_MISSING" if status == "UNKNOWN" else "NONE"),
                         "reason": code, "scope": "FIXED_TARGET_AND_PREDICATES_ONLY",
                         "current_evidence_refs": [item["source_ref"] for item in active]}
    # A local operator can pair an arbitrary prose claim with a trivial byte
    # predicate. Its success establishes that predicate, not the prose claim.
    # Preserve failures/conflicts as property evidence without certifying or
    # refuting unrelated prose from them.
    return {"verification": "UNVERIFIED", "closure": "UNKNOWN", "epistemic_status": "UNKNOWN",
            "blocker": "OBSERVATION_STALE" if code in ("STALE_SOURCE", "SOURCE_CHANGED") else "EVIDENCE_MISSING",
            "verification_reason": code or "CLAIM_NOT_VERIFIED", "property_evidence": property_evidence,
            "evidence": historical, "prose_entailment": "NOT_ASSESSED", "evidence_scope": "FIXED_TARGET_AND_PREDICATES_ONLY"}
