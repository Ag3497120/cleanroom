"""Replayable adoption authority, separate from a successful candidate test."""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib

EVENT_ACTORS = {
    "AdoptionProposed": "kernel", "AdoptionAuthorized": "local_cli",
    "AdoptionStarted": "execution_gateway", "AdoptionInvalidated": "execution_gateway",
    "AdoptionReceipt": "execution_backend",
}


def verified_effect(effect):
    """Eligibility depends on the frozen inputs, not only a passed flag."""
    if not effect or effect["status"] != "CANDIDATE_TESTED":
        return False
    lease, receipt = effect["lease"], effect["receipt"]
    verification = receipt.get("verification")
    if type(verification) is not dict or type(verification.get("result")) is not dict:
        return False
    expected = {name: hashlib.sha256(content.encode("utf-8")).hexdigest()
                for name, content in lease["plan"]["files"].items()}
    return (lease["capability"] == "writer.apply" and receipt["worktree"] == lease["resource_scope"]
            and receipt["reason"] is None and receipt["applied"] == expected
            and verification.get("methods") == ["TEST"] and verification.get("closure") == "BOUNDED"
            and verification.get("result", {}).get("passed") is True
            and verification.get("adoption_authorized") is False
            and verification.get("scope") == {"property": "frozen unittest suite passes",
                                                "base_version": lease["base_version"],
                                                "tests": lease["plan"]["tests"], "candidate": expected})


def validate_payload(kind, payload):
    from .events import fields, require, uuid_value, hash_value, timestamp
    from ..adapters.observations import normalize_path
    if kind == "AdoptionProposed":
        fields(payload, ("plan",))
        plan = payload["plan"]
        fields(plan, ("id", "effect_lease_id", "execution_ref", "proposal_hash", "base_version", "target_ref",
                      "target_before", "source_hash", "candidate_hash", "backend_hash", "backend_identity",
                      "files", "tests", "message"))
        uuid_value(plan["id"])
        uuid_value(plan["effect_lease_id"])
        require(type(plan["execution_ref"]) is str and len(plan["execution_ref"]) == 73)
        for name in ("proposal_hash", "source_hash", "candidate_hash", "backend_hash"):
            hash_value(plan[name])
        require(type(plan["base_version"]) is str and len(plan["base_version"]) in (40, 64))
        require(plan["target_before"] in (None, plan["base_version"]))
        require(type(plan["target_ref"]) is str and plan["target_ref"].startswith("refs/heads/"))
        require(type(plan["message"]) is str and 1 <= len(plan["message"].strip()) <= 2000)
        require(type(plan["files"]) is dict and 1 <= len(plan["files"]) <= 16)
        for path, sha in plan["files"].items():
            normalize_path(path)
            hash_value(sha)
        require(type(plan["tests"]) is list and 1 <= len(plan["tests"]) <= 16)
        for path in plan["tests"]:
            normalize_path(path)
        fields(plan["backend_identity"], ("backend", "path", "sha256"))
        from .codec import digest
        require(digest(plan["backend_identity"]) == plan["backend_hash"])
    elif kind == "AdoptionAuthorized":
        fields(payload, ("adoption_id", "plan_hash", "basis_revision", "expires_at", "rule_context_hash", "reason"))
        uuid_value(payload["adoption_id"])
        hash_value(payload["plan_hash"])
        hash_value(payload["rule_context_hash"])
        timestamp(payload["expires_at"])
        require(type(payload["basis_revision"]) is int and payload["basis_revision"] > 0)
        require(type(payload["reason"]) is str and 1 <= len(payload["reason"].strip()) <= 4000)
    elif kind == "AdoptionStarted":
        fields(payload, ("adoption_id", "commit"))
        uuid_value(payload["adoption_id"])
        require(type(payload["commit"]) is str and len(payload["commit"]) in (40, 64))
    elif kind == "AdoptionInvalidated":
        fields(payload, ("adoption_id", "reason"))
        uuid_value(payload["adoption_id"])
        require(type(payload["reason"]) is str and 1 <= len(payload["reason"]) <= 160)
    elif kind == "AdoptionReceipt":
        fields(payload, ("adoption_id", "outcome", "target_ref", "base_version", "commit", "execution_ref", "recovered", "reason"))
        uuid_value(payload["adoption_id"])
        require(payload["outcome"] in ("ADOPTED", "OUTCOME_UNKNOWN"))
        require(type(payload["recovered"]) is bool)
        require(type(payload["commit"]) is str and len(payload["commit"]) in (40, 64))
        require(payload["reason"] is None or type(payload["reason"]) is str)


def apply_event(state, event):
    from .events import citation, require
    from .codec import digest
    kind, payload = event["type"], event["payload"]
    if kind not in EVENT_ACTORS:
        return
    items = state.setdefault("adoptions", {})
    if kind == "AdoptionProposed":
        plan = payload["plan"]
        effect = state["effects"].get(plan["effect_lease_id"])
        require(verified_effect(effect), "STORE_INTEGRITY")
        require(plan["execution_ref"] == effect["receipt_ref"] and plan["proposal_hash"] == effect["lease"]["proposal_hash"], "STORE_INTEGRITY")
        require(plan["files"] == effect["receipt"]["applied"] and plan["tests"] == effect["lease"]["plan"]["tests"], "STORE_INTEGRITY")
        require(plan["base_version"] == effect["lease"]["base_version"] and plan["id"] not in items, "STORE_INTEGRITY")
        require(plan["backend_hash"] == effect["lease"]["backend_hash"] and digest(state["proposal"]) == plan["proposal_hash"], "STORE_INTEGRITY")
        items[plan["id"]] = {"status": "PROPOSED", "plan": deepcopy(plan), "source_ref": citation(event)}
        return
    item = items.get(payload["adoption_id"])
    require(item is not None, "STORE_INTEGRITY")
    if kind == "AdoptionAuthorized":
        require(item["status"] == "PROPOSED" and digest(item["plan"]) == payload["plan_hash"], "STORE_INTEGRITY")
        require(payload["basis_revision"] == state["command_start_revision"], "STORE_INTEGRITY")
        require(digest(state["proposal"]) == item["plan"]["proposal_hash"], "STORE_INTEGRITY")
        require(state["policy_context"] is not None
                and digest(state["policy_context"]["rules"]) == payload["rule_context_hash"], "STORE_INTEGRITY")
        recorded = datetime.strptime(event["recorded_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
        expires = datetime.strptime(payload["expires_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
        require(recorded < expires <= recorded + timedelta(seconds=3600), "STORE_INTEGRITY")
        item.update(status="AUTHORIZED", authorization=deepcopy(payload), authorization_ref=citation(event))
    elif kind == "AdoptionStarted":
        require(item["status"] == "AUTHORIZED", "STORE_INTEGRITY")
        require(event["recorded_at"] < item["authorization"]["expires_at"], "STORE_INTEGRITY")
        require(digest(state["proposal"]) == item["plan"]["proposal_hash"], "STORE_INTEGRITY")
        require(state["policy_context"] is not None
                and digest(state["policy_context"]["rules"]) == item["authorization"]["rule_context_hash"], "STORE_INTEGRITY")
        item.update(status="STARTED", commit=payload["commit"], started_ref=citation(event))
    elif kind == "AdoptionInvalidated":
        require(item["status"] == "AUTHORIZED", "STORE_INTEGRITY")
        item.update(status="INVALIDATED", reason=payload["reason"], invalidated_ref=citation(event))
    else:
        require(item["status"] == "STARTED", "STORE_INTEGRITY")
        plan = item["plan"]
        require(payload["commit"] == item["commit"] and all(payload[k] == plan[k] for k in ("target_ref", "base_version", "execution_ref")),
                "STORE_INTEGRITY")
        require((payload["outcome"] == "ADOPTED") == (payload["reason"] is None), "STORE_INTEGRITY")
        item.update(status=payload["outcome"], receipt=deepcopy(payload), receipt_ref=citation(event))
