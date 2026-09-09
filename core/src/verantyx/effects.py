"""Expiring local leases and crash-conservative execution through Precedent."""
from datetime import timedelta
from pathlib import Path
import uuid

from .adapters.precedent_backend import PrecedentBackend
from .application import now, iso, _receipt_view
from .domain.codec import digest
from .domain.events import make_event
from .domain.effects import plan_for, unittest_closure
from .errors import LedgerError
from .governance import policy_context
from .kernel.evaluate import evaluate
from .kernel.reducer import replay
from .kernel.rules import catalog
from .storage.sqlite import EventStore


def _record(store, previous, kind, payload, key, intent, clock, prefix=()):
    revision = previous[-1]["revision"]
    command_id, batch = str(uuid.uuid4()), []
    for event_type, value in [*prefix, (kind, payload), ("EvaluationRecorded", {"as_of": iso(clock()), "evaluator": "m1.v1"})]:
        batch.append(make_event(store.project_id, previous[-1]["stream_id"], revision + len(batch) + 1,
                                command_id, iso(clock()), event_type, value, str(uuid.uuid4()),
                                batch[-1] if batch else previous[-1]))
    return store.append(key, digest(intent), previous[-1]["stream_id"], revision, batch)


def _state(store, run_id):
    previous = store.events(run_id)
    if not previous:
        raise LedgerError("RUN_NOT_FOUND")
    return previous, replay(previous)


def _unresolved_execution(state, plan, base_version):
    # A judgment-point label identifies the permission question, not a
    # different file write or fixed test. Renaming it cannot resolve an
    # uncertain execution. The recorded plan and its authority remain intact.
    def effect(value):
        return {key: item for key, item in value.items() if key != "point_id"}
    intended = effect(plan)
    return any(item["status"] in ("STARTED", "OUTCOME_UNKNOWN")
               and effect(item["lease"]["plan"]) == intended
               and item["lease"]["base_version"] == base_version
               for item in state["effects"].values())


def _gate(store, state, plan, clock, backend=None):
    context = policy_context(store.events(), state, backend)
    result = evaluate({**state, "policy_context": context}, iso(clock()))
    point = next((p for p in (state["proposal"] or {}).get("decision_points", []) if p["id"] == plan["point_id"]), None)
    chosen = next((j for j in result["judgments"] if j["point_id"] == plan["point_id"]), None)
    if not point or point["kind"] != "VALUE_DECISION" or point["decision_type"] != "parallel_writers":
        raise LedgerError("DECISION_KIND")
    if not chosen or chosen["status"] not in ("HUMAN_DECIDED", "PRECEDENT_MATCHED") or chosen["choice"] != "isolate":
        raise LedgerError("EXECUTION_BLOCKED")
    if any(a.get("unresolved_decision_dependencies") for a in result["actions"]
           if a["tool_id"] == plan["tool_id"] and a["arguments"].get("point_id") == plan["point_id"]):
        raise LedgerError("EDITOR_DECISION_REQUIRED")
    for action in result["actions"]:
        if (action["tool_id"] == plan["tool_id"] and action["arguments"].get("point_id") == plan["point_id"]
                and action.get("reason") in ("EDITOR_DECISION_CHANGED", "EDITOR_REFERENCE_CHANGED")):
            raise LedgerError(action["reason"])
    return context


def inspect_workspace(root, configuration, run_id, precedent_path, key, clock=now):
    intent = {"operation": "inspect-workspace", "run_id": run_id, "precedent": str(Path(precedent_path).expanduser().resolve())}
    with EventStore(root, configuration["project"]["id"], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached:
            return _receipt_view(cached, key)
        previous, state = _state(store, run_id)
        executor = PrecedentBackend(precedent_path)
        payload = {"workspace": executor.snapshot(root), "as_of": iso(clock()), "backend_hash": executor.fingerprint}
        return _receipt_view(_record(store, previous, "WorkspaceObserved", payload, key, intent, clock), key)


def authorize(root, configuration, run_id, action_id, precedent_path, key, ttl=300, clock=now, backend=None,
              expected_revision=None):
    if type(ttl) is not int or not 1 <= ttl <= 3600:
        raise LedgerError("ARGUMENTS")
    intent = {"operation": "authorize", "run_id": run_id, "action_id": action_id,
              "precedent": str(Path(precedent_path).expanduser().resolve()), "ttl": ttl}
    if expected_revision is not None:
        if type(expected_revision) is not int or expected_revision <= 0:
            raise LedgerError("ARGUMENTS")
        intent["expected_revision"] = expected_revision
    with EventStore(root, configuration["project"]["id"], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached:
            return _receipt_view(cached, key)
        previous, state = _state(store, run_id)
        if expected_revision is not None and state["revision"] != expected_revision:
            raise LedgerError("REVISION_CONFLICT")
        from .authority import require_current_approval_valid
        require_current_approval_valid()
        action = next((a for a in (state["proposal"] or {}).get("actions", []) if a["id"] == action_id), None)
        if not action:
            raise LedgerError("TOOL_ARGUMENTS_INVALID")
        plan = plan_for(action)
        context = _gate(store, state, plan, clock, backend)
        from .domain.effects import editor_binding
        from .coordination import assert_editor_sources
        editor_binding(state, action)
        assert_editor_sources(root, state)
        executor = PrecedentBackend(precedent_path)
        observed = executor.snapshot(root)
        # A new command key (including a console retry or a refreshed prose
        # proposal) is not evidence that an earlier execution did not happen.
        # Keep the same effect plan on the same Git base blocked while its
        # outcome is unresolved, even when its proposal/action IDs differ.
        if _unresolved_execution(state, plan, observed["base_version"]):
            raise LedgerError("EXECUTION_OUTCOME_UNKNOWN")
        tracked = executor.git(root, "ls-tree", "-r", "--name-only", "-z", observed["base_version"]).split("\0")
        if any(name not in tracked for name in plan["tests"]):
            raise LedgerError("TEST_SCOPE")
        # Tests are frozen base files, not proposal-authored expected values.
        lease_id = str(uuid.uuid4())
        target = Path(root).resolve() / ".verantyx/worktrees" / lease_id
        lease = {"id": lease_id, "action_id": action_id, "proposal_hash": digest(state["proposal"]),
                 "basis_revision": state["revision"], "precondition_hash": digest(observed), "base_version": observed["base_version"],
                 "capability": plan["tool_id"], "resource_scope": str(target), "effect_class": "REVERSIBLE_LOCAL",
                 "expires_at": iso(clock() + timedelta(seconds=ttl)), "idempotency_key": key, "plan": plan,
                 "backend_identity": executor.identity, "backend_hash": executor.fingerprint,
                 "rule_context_hash": digest(context["rules"])}
        receipt = _record(store, previous, "EffectAuthorized", {"lease": lease}, key, intent, clock,
                          prefix=[("WorkspaceObserved", {"workspace": observed, "as_of": iso(clock()), "backend_hash": executor.fingerprint}),
                                  ("PolicyContextRecorded", context)])
        return _receipt_view(receipt, key)


def execute(root, configuration, run_id, lease_id, precedent_path, key, clock=now, backend=None, fault=None):
    intent = {"operation": "execute", "run_id": run_id, "lease_id": lease_id,
              "precedent": str(Path(precedent_path).expanduser().resolve())}
    with EventStore(root, configuration["project"]["id"], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached:
            result = _receipt_view(cached, key)
            result["execution"] = result["state"]["effects"][lease_id]
            result["ok"] = result["execution"]["status"] not in ("INVALIDATED", "OUTCOME_UNKNOWN")
            return result
        previous, state = _state(store, run_id)
        item = state["effects"].get(lease_id)
        if not item:
            raise LedgerError("LEASE_NOT_FOUND")
        if item["status"] not in ("AUTHORIZED", "STARTED"):
            raise LedgerError("LEASE_USED")
        lease, invalid = item["lease"], None
        if item["status"] == "STARTED":
            # A crashed caller may already have produced an external effect. Never repeat it.
            payload = _unknown(lease, "INTERRUPTED_EXECUTION")
        else:
            try:
                from .learning import is_learning_command
                later = {event["command_id"] for event in previous if event["revision"] > lease["basis_revision"]}
                later.discard(item["authorization_command"])
                if any(not is_learning_command(previous, command_id) for command_id in later) or digest(state["proposal"]) != lease["proposal_hash"]:
                    raise LedgerError("CONTEXT_CHANGED")
                if iso(clock()) >= lease["expires_at"]:
                    raise LedgerError("LEASE_EXPIRED")
                context = _gate(store, state, lease["plan"], clock, backend)
                if digest(context["rules"]) != lease["rule_context_hash"]:
                    raise LedgerError("RULE_CHANGED")
                executor = PrecedentBackend(precedent_path, expected_hash=lease["backend_hash"])
                if executor.fingerprint != lease["backend_hash"]:
                    raise LedgerError("PRECEDENT_CHANGED")
                observed = executor.snapshot(root)
                if digest(observed) != lease["precondition_hash"]:
                    raise LedgerError("PRECONDITION_CHANGED")
                # Previously issued leases must respect the same unresolved
                # outcome boundary without rewriting their recorded history.
                if _unresolved_execution(state, lease["plan"], lease["base_version"]):
                    raise LedgerError("EXECUTION_OUTCOME_UNKNOWN")
                target = Path(lease["resource_scope"])
                expected = Path(root).resolve() / ".verantyx/worktrees" / lease_id
                if target != expected or target.exists() or target.is_symlink():
                    raise LedgerError("DESTINATION_EXISTS")
                parent = target.parent
                if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                    raise LedgerError("STORE_PATH")
            except LedgerError as error:
                invalid = error.code
            if invalid:
                receipt = _record(store, previous, "AuthorizationInvalidated", {"lease_id": lease_id, "reason": invalid},
                                  key, intent, clock)
                result = _receipt_view(receipt, key)
                result["execution"] = result["state"]["effects"][lease_id]
                result["ok"] = False
                return result
            start = _record(store, previous, "ExecutionStarted", {"lease_id": lease_id}, "start-" + lease_id,
                            {"start": lease_id}, clock)
            previous = start["events"]
            if fault:
                fault("after_start")
            try:
                # Candidate contents come from immutable Git blobs. The canonical working tree is never a write target.
                if iso(clock()) >= lease["expires_at"]:
                    raise LedgerError("LEASE_EXPIRED")
                from .authority import require_current_approval_valid
                require_current_approval_valid()
                from .writers import execution_writer
                with execution_writer(root, configuration, run_id, lease_id, clock=clock):
                    parent.mkdir(mode=0o700, exist_ok=True)
                    executor.prepare(Path(root).resolve(), target, lease["base_version"])
                    applied, verification = {}, None
                    if lease["plan"]["tool_id"] == "writer.apply":
                        if iso(clock()) >= lease["expires_at"]:
                            raise LedgerError("LEASE_EXPIRED")
                        require_current_approval_valid()
                        applied, raw = executor.apply_and_test(target, lease["plan"]["files"], lease["plan"]["tests"])
                        verification = {"methods": ["TEST"], "closure": unittest_closure(raw),
                                        "scope": {"property": "frozen unittest suite passes", "base_version": lease["base_version"],
                                                  "tests": lease["plan"]["tests"], "candidate": applied},
                                        "result": raw, "oracle_independence": "NOT_ESTABLISHED",
                                        "adoption_authorized": False}
                payload = {"lease_id": lease_id, "outcome": "CANDIDATE_TESTED" if verification else "PREPARED",
                           "worktree": str(target), "shared_destination_rejected": True, "applied": applied,
                           "verification": verification, "reason": None}
                if digest(executor.snapshot(root)) != lease["precondition_hash"]:
                    payload = _unknown(lease, "SOURCE_CHANGED_DURING_EXECUTION")
            except (LedgerError, OSError, ValueError) as error:
                payload = _unknown(lease, getattr(error, "code", "EXECUTION_FAILED"))
            if fault:
                fault("after_effect")
        receipt = _record(store, previous, "ExecutionReceipt", payload, key, intent, clock)
        result = _receipt_view(receipt, key)
        result["execution"] = result["state"]["effects"][lease_id]
        result["ok"] = payload["outcome"] != "OUTCOME_UNKNOWN"
        return result


def _unknown(lease, reason):
    return {"lease_id": lease["id"], "outcome": "OUTCOME_UNKNOWN", "worktree": lease["resource_scope"],
            "shared_destination_rejected": True, "applied": {}, "verification": None, "reason": reason}


def dispatch_effect(root, configuration, args):
    from .adapters.proposal_validation import valid_id
    if not valid_id(args.key):
        raise LedgerError("ARGUMENTS")
    if args.command == "inspect-workspace":
        return inspect_workspace(root, configuration, args.run_id, args.precedent, args.key)
    if args.command == "authorize":
        return authorize(root, configuration, args.run_id, args.action, args.precedent, args.key, args.ttl)
    return execute(root, configuration, args.run_id, args.lease, args.precedent, args.key)
