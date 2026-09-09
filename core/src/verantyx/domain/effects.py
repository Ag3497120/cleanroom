"""Typed bounded effects. Natural-language proposals cannot define new capabilities."""
from .events import fields, require, hash_value, timestamp, uuid_value
from ..adapters.observations import normalize_path
from ..adapters.proposal_validation import valid_id
from ..errors import LedgerError
from .codec import digest
from datetime import datetime, timedelta
from pathlib import PurePosixPath
import hashlib
import math
import re


def plan_for(action):
    tool, args = action["tool_id"], action["arguments"]
    if tool not in ("worktree.prepare", "writer.apply"):
        raise LedgerError("TOOL_UNAVAILABLE")
    keys = {"point_id", "destination"} | ({"files", "tests"} if tool == "writer.apply" else set())
    if type(args) is not dict or set(args) != keys or not valid_id(args["point_id"]) or args["destination"] != "shared":
        raise LedgerError("TOOL_ARGUMENTS_INVALID")
    result = {"tool_id": tool, "point_id": args["point_id"], "requested_destination": "shared",
              "effective_destination": "isolated", "files": {}, "tests": []}
    if tool == "writer.apply":
        files, tests = args["files"], args["tests"]
        if type(files) is not dict or not 1 <= len(files) <= 16 or type(tests) is not list or not 1 <= len(tests) <= 16:
            raise LedgerError("TOOL_ARGUMENTS_INVALID")
        for name, value in files.items():
            normalize_path(name)
            if type(value) is not str or len(value.encode()) > 100000:
                raise LedgerError("TOOL_ARGUMENTS_INVALID")
        from .paths import portable_path_key
        written_names = {portable_path_key(name) for name in files}
        for name in tests:
            normalize_path(name)
            if portable_path_key(name) in written_names or not name.endswith(".py"):
                raise LedgerError("TEST_SCOPE")
        if len(set(tests)) != len(tests):
            raise LedgerError("TEST_SCOPE")
        result.update(files=files, tests=tests)
    return result


def editor_binding(state, action, *, as_of=None):
    """A context handoff cannot be bypassed by replacing the writer proposal."""
    if not state.get("handoff_plan") or action["tool_id"] != "writer.apply":
        return []
    from ..shared_context import current_editor_attempt
    item = current_editor_attempt(state)
    require(item is not None and item["validation"]["status"] == "MATCHED", "HANDOFF_REPAIR_REQUIRED")
    require(item["context_sha256"] == state["shared_context"]["sha256"]
            and item["plan_sha256"] == digest(state["handoff_plan"]["plan"]), "SHARED_CONTEXT_STALE")
    require(action["arguments"].get("files") == item["document"]["files"]
            and action["arguments"].get("tests") == item["document"]["tests"], "SHARED_CONTEXT_STALE")
    for source in item["selected_files"]:
        observed = state["observations"].get(state["latest_observations"].get(source["path"]))
        require(observed is not None and observed.get("sha256") == source["sha256"], "SHARED_CONTEXT_STALE")
    from ..shared_context import require_source_constraints
    require_source_constraints(state["handoff_plan"].get("source_proposal"), state["proposal"])
    from ..decision_context import require_current
    require_current(state, action["arguments"].get("point_id"), as_of)
    # Depend on the value choices of this candidate's own proposal. General
    # UNKNOWN observations and other tasks are retained but are not an all-stop
    # condition, and a model's agreement cannot satisfy a human decision.
    return [point["id"] for point in state["proposal"].get("decision_points", [])
            if point["kind"] == "VALUE_DECISION"]


def validate_payload(kind, payload):
    if kind == "EffectAuthorized":
        fields(payload, ("lease",))
        lease = payload["lease"]
        fields(lease, ("id", "action_id", "proposal_hash", "basis_revision", "precondition_hash", "base_version",
                       "capability", "resource_scope", "effect_class", "expires_at", "idempotency_key", "plan",
                       "backend_identity", "backend_hash", "rule_context_hash"))
        uuid_value(lease["id"])
        require(valid_id(lease["action_id"]) and valid_id(lease["idempotency_key"]))
        for key in ("proposal_hash", "precondition_hash", "backend_hash", "rule_context_hash"):
            hash_value(lease[key])
        require(type(lease["basis_revision"]) is int and lease["basis_revision"] > 0)
        require(lease["capability"] in ("worktree.prepare", "writer.apply") and lease["effect_class"] == "REVERSIBLE_LOCAL")
        require(type(lease["base_version"]) is str and len(lease["base_version"]) in (40, 64))
        timestamp(lease["expires_at"])
        require(type(lease["resource_scope"]) is str and len(lease["resource_scope"]) < 4096)
        require(type(lease["plan"]) is dict and type(lease["backend_identity"]) is dict)
        plan = lease["plan"]
        args = {"point_id": plan["point_id"], "destination": plan["requested_destination"]}
        if lease["capability"] == "writer.apply":
            args.update(files=plan["files"], tests=plan["tests"])
        require(plan_for({"tool_id": lease["capability"], "arguments": args}) == plan)
        fields(lease["backend_identity"], ("backend", "path", "sha256"))
        hash_value(lease["backend_identity"]["sha256"])
        require(digest(lease["backend_identity"]) == lease["backend_hash"])
    elif kind == "ExecutionStarted":
        fields(payload, ("lease_id",))
        uuid_value(payload["lease_id"])
    elif kind == "AuthorizationInvalidated":
        fields(payload, ("lease_id", "reason"))
        uuid_value(payload["lease_id"])
        require(valid_id(payload["reason"]))
    elif kind == "ExecutionReceipt":
        fields(payload, ("lease_id", "outcome", "worktree", "shared_destination_rejected", "applied", "verification", "reason"))
        uuid_value(payload["lease_id"])
        require(payload["outcome"] in ("PREPARED", "CANDIDATE_TESTED", "OUTCOME_UNKNOWN"))
        require(payload["shared_destination_rejected"] is True and type(payload["worktree"]) is str)
        require(type(payload["applied"]) is dict)
        for value in payload["applied"].values():
            hash_value(value)
        require(payload["verification"] is None or type(payload["verification"]) is dict)
        require(payload["reason"] is None or valid_id(payload["reason"]))


def validate_binding(state, event):
    """Validate recorded capability/evidence bindings without touching the filesystem.

    A valid hash chain alone is not a valid state transition. This repeats the
    gateway's structural checks so an archive cannot invent a tested candidate.
    The local OS operator remains the authority source; hashes are not signatures.
    """
    kind, payload = event["type"], event["payload"]
    if kind == "EffectAuthorized":
        lease = payload["lease"]
        action = next((a for a in (state["proposal"] or {}).get("actions", [])
                       if a["id"] == lease["action_id"]), None)
        require(action is not None and plan_for(action) == lease["plan"], "STORE_INTEGRITY")
        editor_binding(state, action, as_of=event["recorded_at"])
        require(lease["capability"] == action["tool_id"], "STORE_INTEGRITY")
        require(state["workspace_observations"], "STORE_INTEGRITY")
        observation = state["workspace_observations"][-1]
        workspace = observation["workspace"]
        root = PurePosixPath(workspace["root"])
        require(root.is_absolute() and str(root / ".verantyx/worktrees" / lease["id"]) == lease["resource_scope"], "STORE_INTEGRITY")
        require(lease["backend_hash"] == observation["backend_hash"]
                and lease["base_version"] == workspace["base_version"], "STORE_INTEGRITY")
        require(state["policy_context"] is not None
                and digest(state["policy_context"]["rules"]) == lease["rule_context_hash"], "STORE_INTEGRITY")
        _decision_binding(state, lease, event["recorded_at"])
        recorded = datetime.strptime(event["recorded_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
        expires = datetime.strptime(lease["expires_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
        require(recorded < expires <= recorded + timedelta(seconds=3600), "STORE_INTEGRITY")
    elif kind in ("ExecutionStarted", "ExecutionReceipt"):
        item = state["effects"].get(payload["lease_id"])
        require(item is not None, "STORE_INTEGRITY")
        lease = item["lease"]
        if kind == "ExecutionStarted":
            require(event["recorded_at"] < lease["expires_at"], "STORE_INTEGRITY")
            require(digest(state["proposal"]) == lease["proposal_hash"], "STORE_INTEGRITY")
            require(state["policy_context"] is not None
                    and digest(state["policy_context"]["rules"]) == lease["rule_context_hash"], "STORE_INTEGRITY")
            require(state["workspace_observations"] and
                    digest(state["workspace_observations"][-1]["workspace"]) == lease["precondition_hash"], "STORE_INTEGRITY")
            from ..learning import EVENT_ACTORS as LEARNING_ACTORS
            sources = state["learning_source_events"]
            authorized_revision = sources[item["source_ref"]]["revision"]
            require(all(source["type"] in {*LEARNING_ACTORS, "EvaluationRecorded"}
                        for source in sources.values() if source["revision"] > authorized_revision), "STORE_INTEGRITY")
            _decision_binding(state, lease, event["recorded_at"])
            return
        require(payload["worktree"] == lease["resource_scope"], "STORE_INTEGRITY")
        if payload["outcome"] == "OUTCOME_UNKNOWN":
            require(payload["reason"] is not None and payload["verification"] is None
                    and payload["applied"] == {}, "STORE_INTEGRITY")
        elif payload["outcome"] == "PREPARED":
            require(lease["capability"] == "worktree.prepare" and payload["reason"] is None
                    and payload["verification"] is None and payload["applied"] == {}, "STORE_INTEGRITY")
        else:
            expected = {name: hashlib.sha256(content.encode("utf-8")).hexdigest()
                        for name, content in lease["plan"]["files"].items()}
            require(lease["capability"] == "writer.apply" and payload["reason"] is None
                    and payload["applied"] == expected, "STORE_INTEGRITY")
            verification = payload["verification"]
            require(type(verification) is dict and set(verification) == {
                "methods", "closure", "scope", "result", "oracle_independence", "adoption_authorized"}, "STORE_INTEGRITY")
            require(verification["methods"] == ["TEST"] and verification["adoption_authorized"] is False
                    and verification["oracle_independence"] == "NOT_ESTABLISHED", "STORE_INTEGRITY")
            require(verification["scope"] == {"property": "frozen unittest suite passes",
                "base_version": lease["base_version"], "tests": lease["plan"]["tests"], "candidate": expected}, "STORE_INTEGRITY")
            result = verification["result"]
            require(type(result) is dict and set(result) == {"passed", "exit", "reason", "seconds", "output", "backend"}, "STORE_INTEGRITY")
            require(type(result["passed"]) is bool and type(result["exit"]) is int
                    and type(result["seconds"]) in (int, float) and math.isfinite(result["seconds"])
                    and result["seconds"] >= 0 and result["backend"] == "macos-seatbelt"
                    and type(result["output"]) is str and len(result["output"]) <= 100000
                    and (result["reason"] is None or type(result["reason"]) is str), "STORE_INTEGRITY")
            closure = unittest_closure(result)
            # v0.3 classified every non-pass as REFUTED, even timeout or an
            # incomplete runner. Preserve those source records, then project
            # them conservatively as UNKNOWN with a visible annotation.
            legacy_incomplete = (not result["passed"] and closure == "UNKNOWN"
                                 and verification["closure"] == "REFUTED")
            require(verification["closure"] == closure or legacy_incomplete, "STORE_INTEGRITY")
            require(not result["passed"] or (result["exit"] == 0 and result["reason"] is None), "STORE_INTEGRITY")
            require(not result["passed"] or completed_unittest_report(result["output"]), "STORE_INTEGRITY")


def _decision_binding(state, lease, as_of):
    """The recorded authorization must have the same decision gate as the CLI."""
    from ..kernel.evaluate import evaluate
    point_id = lease["plan"]["point_id"]
    point = next((item for item in (state["proposal"] or {}).get("decision_points", []) if item["id"] == point_id), None)
    require(point is not None and point["kind"] == "VALUE_DECISION"
            and point["decision_type"] == "parallel_writers", "STORE_INTEGRITY")
    assessment = evaluate(state, as_of)
    chosen = next((item for item in assessment["judgments"] if item["point_id"] == point_id), None)
    require(chosen is not None and chosen["status"] in ("HUMAN_DECIDED", "PRECEDENT_MATCHED")
            and chosen["choice"] == "isolate", "STORE_INTEGRITY")
    action = next(item for item in assessment["actions"] if item["id"] == lease["action_id"])
    require(not action.get("unresolved_decision_dependencies"), "STORE_INTEGRITY")


def completed_unittest_report(output):
    """Require a completed, non-empty, unskipped suite, not merely exit status 0.

    This is a completion check, not an independent oracle: hostile code in the
    test interpreter can still forge text. Independent claim checks are separate.
    """
    return bool(re.search(r"(?:^|\n)Ran [1-9][0-9]* tests? in [0-9.]+s\n\nOK\s*\Z", output))


def unittest_closure(result):
    """A missing completion or runner error is not an empirical counterexample."""
    if result["reason"] is not None:
        return "UNKNOWN"
    output = result["output"]
    if result["passed"]:
        return "BOUNDED" if result["exit"] == 0 and completed_unittest_report(output) else "UNKNOWN"
    failed = re.search(r"(?:^|\n)Ran [1-9][0-9]* tests? in [0-9.]+s\n\nFAILED \(([^\n)]+)\)\s*\Z", output)
    if result["exit"] != 0 and failed and re.search(r"(?:^|, )failures=[1-9][0-9]*(?:, |$)", failed.group(1)):
        return "REFUTED"
    return "UNKNOWN"


def project_receipt(payload):
    """Keep legacy source values in the event; separate conservative current view."""
    from copy import deepcopy
    projected = deepcopy(payload)
    verification = projected.get("verification")
    annotation = None
    if verification is not None:
        actual = unittest_closure(verification["result"])
        if verification["closure"] != actual:
            annotation = {"recorded_closure": verification["closure"], "current_closure": actual,
                          "reason": "LEGACY_INCOMPLETE_TEST_CLASSIFICATION"}
            verification["closure"] = actual
    return projected, annotation
