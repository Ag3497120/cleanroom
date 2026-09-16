"""Closed event vocabulary. Imported text cannot introduce authority events."""
from datetime import datetime
import hashlib
import re
import uuid

from ..adapters.observations import normalize_path
from ..adapters.proposal_validation import valid_id, validate_proposal
from ..errors import LedgerError
from .codec import canonical, decode, digest, MAX_DOCUMENT

ZERO_HASH = "0" * 64
ACTORS = {
    "TaskRequested": "local_cli", "ReadScopeExtended": "local_cli",
    "ObservationRecorded": "file_observer", "ProposalRecorded": "recorded_proposal",
    "EvaluationRecorded": "kernel",
    "HumanDecisionRecorded": "local_cli", "RuleCandidateCreated": "kernel",
    "RuleShadowed": "scope_verifier", "RuleConfirmed": "local_cli", "RuleActivated": "local_cli",
    "RuleRetired": "local_cli", "RuleSuperseded": "local_cli", "RuleContested": "local_cli",
    "PolicyContextRecorded": "kernel",
    "WorkspaceObserved": "workspace_observer",
    "EffectAuthorized": "local_cli", "ExecutionStarted": "execution_gateway",
    "ExecutionReceipt": "execution_backend", "AuthorizationInvalidated": "execution_gateway",
    "PrecedentCandidateCreated": "kernel", "PrecedentAccepted": "local_cli",
}
from .adoption import EVENT_ACTORS as ADOPTION_ACTORS
ACTORS.update(ADOPTION_ACTORS)
from ..learning import EVENT_ACTORS as LEARNING_ACTORS
ACTORS.update(LEARNING_ACTORS)
from .rule_extensions import EVENT_ACTORS as POLICY_ACTORS
ACTORS.update(POLICY_ACTORS)
from .verification import EVENT_ACTORS as VERIFICATION_ACTORS
ACTORS.update(VERIFICATION_ACTORS)
from .integration import EVENT_ACTORS as INTEGRATION_ACTORS
ACTORS.update(INTEGRATION_ACTORS)
from .oracles import EVENT_ACTORS as ORACLE_ACTORS
ACTORS.update(ORACLE_ACTORS)
from .command_effects import EVENT_ACTORS as COMMAND_ACTORS
ACTORS.update(COMMAND_ACTORS)
from ..responses import EVENT_ACTORS as RESPONSE_ACTORS
ACTORS.update(RESPONSE_ACTORS)
from ..shared_context import EVENT_ACTORS as CONTEXT_ACTORS
ACTORS.update(CONTEXT_ACTORS)
from .asset_workflow import EVENT_ACTORS as WORKFLOW_ACTORS
ACTORS.update(WORKFLOW_ACTORS)
from ..external_capture import EVENT_ACTORS as CAPTURE_ACTORS
ACTORS.update(CAPTURE_ACTORS)
from .work import EVENT_ACTORS as WORK_ACTORS
ACTORS.update(WORK_ACTORS)
from .work_checks import EVENT_ACTORS as WORK_CHECK_ACTORS
ACTORS.update(WORK_CHECK_ACTORS)
from .owner_experience import EVENT_ACTORS as OWNER_EXPERIENCE_ACTORS
ACTORS.update(OWNER_EXPERIENCE_ACTORS)
ENVELOPE = {"schema_version", "event_id", "project_id", "stream_id", "revision", "command_id",
            "recorded_at", "type", "actor_kind", "causation_id", "prev_hash", "payload", "event_hash"}


def require(condition, code="EVENT_INVALID"):
    if not condition:
        raise LedgerError(code)


def fields(value, expected):
    require(type(value) is dict and set(value) == set(expected))


def timestamp(value):
    require(type(value) is str and bool(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", value)))
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        raise LedgerError("EVENT_INVALID") from None
    return value


def uuid_value(value):
    try:
        require(type(value) is str and str(uuid.UUID(value)) == value)
    except (ValueError, TypeError, AttributeError):
        raise LedgerError("EVENT_INVALID") from None


def hash_value(value):
    require(type(value) is str and bool(re.fullmatch("[a-f0-9]{64}", value)))


def paths(value, empty=True):
    require(type(value) is list and len(value) <= 32 and (empty or len(value) > 0))
    require(all(type(p) is str for p in value) and len(set(value)) == len(value))
    for path in value:
        require(normalize_path(path) == path)


def context(value):
    fields(value, ("component", "workload", "risk"))
    require(all(type(v) is str and 1 <= len(v) <= 160 for v in value.values()))
    require(value["risk"] in ("LOW", "MEDIUM", "HIGH", "UNSPECIFIED"))


def scope(value):
    fields(value, ("project_id", "component", "workload", "risk", "decision_type"))
    uuid_value(value["project_id"])
    context({k: value[k] for k in ("component", "workload", "risk")})
    require(valid_id(value["decision_type"]))


def rule_base(value):
    fields(value, ("id", "scope", "decision_type", "choice", "options", "reason", "human_ref", "supersedes",
                   "precedent_ref", "owner", "exceptions", "source_decisions", "review_after"))
    uuid_value(value["id"])
    scope(value["scope"])
    require(value["decision_type"] == value["scope"]["decision_type"])
    require(type(value["options"]) is list and 2 <= len(value["options"]) <= 8)
    for option in value["options"]:
        fields(option, ("id", "label"))
        require(valid_id(option["id"]) and type(option["label"]) is str and 1 <= len(option["label"]) <= 1000)
    require(value["choice"] in {option["id"] for option in value["options"]})
    require(len({option["id"] for option in value["options"]}) == len(value["options"]))
    require(type(value["reason"]) is str and 1 <= len(value["reason"]) <= 4000)
    require(valid_id(value["human_ref"]))
    require(valid_id(value["precedent_ref"]) and value["owner"] == value["scope"]["project_id"])
    require(value["exceptions"] == [] and value["source_decisions"] == [value["human_ref"]])
    timestamp(value["review_after"])
    if value["supersedes"] is not None:
        uuid_value(value["supersedes"])


def validate_event(event):
    try:
        fields(event, ENVELOPE)
        require(type(event["schema_version"]) is int and event["schema_version"] == 1)
        for key in ("event_id", "project_id", "command_id"):
            uuid_value(event[key])
        require(valid_id(event["stream_id"]))
        require(type(event["revision"]) is int and event["revision"] > 0)
        timestamp(event["recorded_at"])
        require(type(event["type"]) is str and event["type"] in ACTORS)
        require(event["actor_kind"] == ACTORS[event["type"]])
        if event["causation_id"] is not None:
            uuid_value(event["causation_id"])
        hash_value(event["prev_hash"])
        hash_value(event["event_hash"])
        payload = event["payload"]
        kind = event["type"]
        if kind in OWNER_EXPERIENCE_ACTORS:
            from .owner_experience import validate_payload
            validate_payload(kind, payload)
        elif kind in WORK_CHECK_ACTORS:
            from .work_checks import validate_payload
            validate_payload(kind, payload)
        elif kind in WORK_ACTORS:
            from .work import validate_payload
            validate_payload(kind, payload)
        elif kind in WORKFLOW_ACTORS:
            from .asset_workflow import validate_payload
            validate_payload(kind, payload)
        elif kind in CAPTURE_ACTORS:
            from ..external_capture import validate_payload
            validate_payload(kind, payload)
        elif kind in CONTEXT_ACTORS:
            from ..shared_context import validate_payload
            validate_payload(kind, payload)
        elif kind in RESPONSE_ACTORS:
            from ..responses import validate_payload
            validate_payload(kind, payload)
        elif kind in ORACLE_ACTORS:
            from .oracles import validate_payload
            validate_payload(kind, payload)
        elif kind in COMMAND_ACTORS:
            from .command_effects import validate_payload
            validate_payload(kind, payload)
        elif kind in INTEGRATION_ACTORS:
            from .integration import validate_payload
            validate_payload(kind, payload)
        elif kind in VERIFICATION_ACTORS:
            from .verification import validate_payload
            validate_payload(kind, payload)
        elif kind in POLICY_ACTORS:
            from .rule_extensions import validate_payload
            validate_payload(kind, payload)
        elif kind in LEARNING_ACTORS:
            from ..learning import validate_payload
            validate_payload(kind, payload)
        elif kind in ADOPTION_ACTORS:
            from .adoption import validate_payload
            validate_payload(kind, payload)
        elif kind in ("EffectAuthorized", "ExecutionStarted", "ExecutionReceipt", "AuthorizationInvalidated"):
            from .effects import validate_payload
            validate_payload(kind, payload)
        elif kind == "WorkspaceObserved":
            fields(payload, ("workspace", "as_of", "backend_hash"))
            timestamp(payload["as_of"])
            hash_value(payload["backend_hash"])
            observed = payload["workspace"]
            fields(observed, ("root", "base_version", "files", "index_hash", "tree_hash"))
            require(type(observed["root"]) is str and type(observed["base_version"]) is str)
            hash_value(observed["index_hash"])
            hash_value(observed["tree_hash"])
            require(type(observed["files"]) is dict and len(observed["files"]) <= 1024)
            for path, value in observed["files"].items():
                normalize_path(path)
                fields(value, ("status", "sha256", "size"))
                if value["status"] == "OBSERVED":
                    hash_value(value["sha256"])
                    require(type(value["size"]) is int and 0 <= value["size"] <= 16 * 1024 * 1024)
                else:
                    require(value == {"status": "MISSING", "sha256": None, "size": None})
        elif kind == "TaskRequested":
            fields(payload, ("request", "locale", "read_scope", "context", "learning"))
            require(type(payload["request"]) is str and 1 <= len(payload["request"].strip()) <= 16000)
            require(payload["locale"] in ("en", "ja", "zh-Hans", "ko", "es"))
            paths(payload["read_scope"])
            context(payload["context"])
            fields(payload["learning"], ("mode", "max_items"))
            require(payload["learning"]["mode"] in ("manual", "digest", "off"))
            require(type(payload["learning"]["max_items"]) is int and 1 <= payload["learning"]["max_items"] <= 3)
        elif kind == "ReadScopeExtended":
            fields(payload, ("paths",))
            paths(payload["paths"], empty=False)
        elif kind == "ObservationRecorded":
            fields(payload, ("observer", "path", "status", "sha256", "size", "reason", "observed_at", "expires_at"))
            require(payload["observer"] == "file.sha256.v1")
            require(normalize_path(payload["path"]) == payload["path"])
            require(payload["status"] in ("OBSERVED", "MISSING", "UNREADABLE", "CHANGED"))
            timestamp(payload["observed_at"])
            timestamp(payload["expires_at"])
            require(payload["observed_at"] < payload["expires_at"])
            if payload["status"] == "OBSERVED":
                hash_value(payload["sha256"])
                require(type(payload["size"]) is int and 0 <= payload["size"] <= 16 * 1024 * 1024)
                require(payload["reason"] is None)
            else:
                require(payload["sha256"] is None and payload["size"] is None)
                require(payload["reason"] in ("NOT_FOUND", "NOT_REGULAR", "BYTE_LIMIT", "READ_FAILED", "CHANGED_DURING_READ"))
        elif kind == "ProposalRecorded":
            fields(payload, ("document", "raw", "sha256", "basis_revision"))
            require(type(payload["basis_revision"]) is int and payload["basis_revision"] >= 0)
            require(type(payload["raw"]) is str)
            raw = payload["raw"].encode("utf-8")
            require(len(raw) <= 256 * 1024)
            hash_value(payload["sha256"])
            require(hashlib.sha256(raw).hexdigest() == payload["sha256"])
            require(decode(raw) == payload["document"])
            validate_proposal(payload["document"])
            require(payload["basis_revision"] == payload["document"]["context_revision"])
        elif kind == "HumanDecisionRecorded":
            fields(payload, ("point_id", "choice", "scope", "reason"))
            require(valid_id(payload["point_id"]) and valid_id(payload["choice"]))
            scope(payload["scope"])
            require(type(payload["reason"]) is str and 1 <= len(payload["reason"]) <= 4000)
        elif kind == "PrecedentCandidateCreated":
            fields(payload, ("id", "decision_ref", "scope", "choice", "options", "reason", "review_after", "supersedes"))
            uuid_value(payload["id"])
            rule_base({"id": payload["id"], "scope": payload["scope"], "decision_type": payload["scope"]["decision_type"],
                       "choice": payload["choice"], "options": payload["options"], "reason": payload["reason"],
                       "human_ref": payload["decision_ref"], "precedent_ref": payload["decision_ref"],
                       "owner": payload["scope"]["project_id"], "exceptions": [], "source_decisions": [payload["decision_ref"]],
                       "review_after": payload["review_after"], "supersedes": payload["supersedes"]})
        elif kind == "PrecedentAccepted":
            fields(payload, ("id", "scope_hash"))
            uuid_value(payload["id"])
            hash_value(payload["scope_hash"])
        elif kind == "RuleCandidateCreated":
            fields(payload, ("rule",))
            rule_base(payload["rule"])
        elif kind == "RuleShadowed":
            fields(payload, ("rule_id", "check"))
            uuid_value(payload["rule_id"])
            check = payload["check"]
            fields(check, ("methods", "closure", "scope", "origin", "engine", "identity", "cases", "independence"))
            require(check["methods"] == ["TEST", "NEGATIVE_CONTROL"] and check["closure"] == "BOUNDED" and check["scope"] == "EXACT_MATCH_MECHANISM_ONLY")
            from .rule_extensions import validate_engine_evidence
            validate_engine_evidence(check)
            hash_value(check["engine"])
            require(digest(check["identity"]) == check["engine"])
            require(type(check["cases"]) is list and len(check["cases"]) == 6)
            for case in check["cases"]:
                fields(case, ("case", "target", "expected", "match", "input_hash", "engine"))
                scope(case["target"])
                require(type(case["expected"]) is bool and type(case["match"]) is bool and case["expected"] == case["match"])
                require(case["engine"] == check["engine"])
                hash_value(case["input_hash"])
        elif kind in ("RuleConfirmed", "RuleActivated", "RuleRetired", "RuleSuperseded", "RuleContested"):
            expected = ("rule_id", "successor") if kind == "RuleSuperseded" else (
                ("rule_id", "reason") if kind in ("RuleRetired", "RuleContested") else ("rule_id",))
            fields(payload, expected)
            uuid_value(payload["rule_id"])
            if "successor" in payload:
                uuid_value(payload["successor"])
            if "reason" in payload:
                require(type(payload["reason"]) is str and 1 <= len(payload["reason"]) <= 4000)
        elif kind == "PolicyContextRecorded":
            fields(payload, ("rules", "matches"))
            require(type(payload["rules"]) is list and len(payload["rules"]) <= 256)
            require(type(payload["matches"]) is dict)
            for rule in payload["rules"]:
                base = {k: rule[k] for k in ("id", "scope", "decision_type", "choice", "options", "reason", "human_ref", "supersedes",
                                            "precedent_ref", "owner", "exceptions", "source_decisions", "review_after")}
                rule_base(base)
                if rule.get("scope_policy"):
                    from .rule_extensions import validate_policy
                    validate_policy(rule["scope_policy"], rule["scope"])
                require(rule["state"] in ("DRAFT", "SHADOW", "CONFIRMED", "ACTIVE", "RETIRED", "SUPERSEDED"))
                require(type(rule["contested"]) is bool and type(rule["history"]) is list)
            for point_id, matches in payload["matches"].items():
                require(valid_id(point_id) and type(matches) is dict and len(matches) <= 256)
                for rule_id, receipt in matches.items():
                    uuid_value(rule_id)
                    if set(receipt) == {"error"}:
                        require(valid_id(receipt["error"]))
                    elif receipt.get("schema") == "finite-scope-match.v1":
                        from .rule_extensions import validate_match
                        item = next((rule for rule in payload["rules"] if rule["id"] == rule_id), None)
                        require(item is not None)
                        validate_match(item, receipt["target"], receipt)
                    else:
                        fields(receipt, ("match", "input_hash", "engine"))
                        require(type(receipt["match"]) is bool)
                        hash_value(receipt["input_hash"])
                        hash_value(receipt["engine"])
        elif kind == "EvaluationRecorded":
            fields(payload, ("as_of", "evaluator"))
            timestamp(payload["as_of"])
            require(payload["evaluator"] == "m1.v1")
        require(len(canonical(event).encode("utf-8")) <= MAX_DOCUMENT)
        require(digest({key: value for key, value in event.items() if key != "event_hash"}) == event["event_hash"],
                "STORE_INTEGRITY")
    except LedgerError:
        raise
    except (ValueError, TypeError, AttributeError, KeyError, UnicodeError):
        raise LedgerError("EVENT_INVALID") from None
    return event


def make_event(project_id, stream_id, revision, command_id, recorded_at, kind, payload,
               event_id, previous=None):
    event = {"schema_version": 1, "project_id": project_id, "stream_id": stream_id,
             "revision": revision, "command_id": command_id, "recorded_at": recorded_at,
             "type": kind, "actor_kind": ACTORS[kind], "payload": payload, "event_id": event_id,
             "causation_id": previous["event_id"] if previous else None,
             "prev_hash": previous["event_hash"] if previous else ZERO_HASH}
    event["event_hash"] = digest(event)
    return validate_event(event)


def citation(event):
    return event["project_id"] + ":" + event["event_id"]
