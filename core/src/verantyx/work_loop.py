"""Connect an explicit candidate execution to frozen tests and experience capture.

The existing effect gate owns authorization; this module never chooses a human
decision, activates a rule, adopts a candidate, or retries an uncertain effect.
"""
from pathlib import Path
import hashlib

from .adapters.invocation_journal import InvocationJournal
from .adapters.proposal_validation import valid_id
from .application import get_projection
from .domain.codec import digest
from .errors import LedgerError
from .storage.sqlite import EventStore


def candidate_view(state, action_id=None):
    actions = [row for row in (state.get("proposal") or {}).get("actions", [])
               if row["tool_id"] == "writer.apply" and (action_id is None or row["id"] == action_id)]
    if len(actions) != 1:
        return {"status": "NO_CANDIDATE" if not actions else "SELECT_ACTION", "action_id": None,
                "files": [], "tests": [], "executed": False}
    action = actions[0]
    from .domain.effects import plan_for
    plan = plan_for(action)
    return {"status": "CANDIDATE_READY", "action_id": action["id"], "proposal_sha256": digest(state["proposal"]),
            "files": [{"path": path, "sha256": hashlib.sha256(body.encode()).hexdigest(), "content": body}
                      for path, body in plan["files"].items()],
            "tests": list(plan["tests"]), "executed": False,
            "question": (state.get("assessment") or {}).get("question")}


def _outcome(result):
    item = result["execution"]
    receipt = item.get("receipt") or {}
    verification = receipt.get("verification") or {}
    closure = verification.get("closure", "UNKNOWN")
    status = ("COMPLETED" if closure == "BOUNDED" else closure) if item["status"] == "CANDIDATE_TESTED" else item["status"]
    return {"status": status, "executed": item["status"] == "CANDIDATE_TESTED",
            "lease_id": item["lease"]["id"], "worktree": receipt.get("worktree"),
            "build": "COMPLETE" if item["status"] == "CANDIDATE_TESTED" else "UNKNOWN",
            "evidence": closure, "ownership": "NOT_ASSESSED", "canonical_adopted": False,
            "reason": item.get("reason") or receipt.get("reason"),
            "source_ref": item.get("receipt_ref"), "verification": verification or None}


def run_candidate(root, configuration, run_id, *, key, expected_revision, precedent_path=None,
                  action_id=None, execute=False, collect=True, adapter_path=None, locale=None, timeout=60,
                  fault=None, refresh=False, editor_adapter=None, include_paths=(), max_repairs=1):
    if (not valid_id(run_id) or not valid_id(key) or type(expected_revision) is not int or expected_revision <= 0
            or type(execute) is not bool or type(collect) is not bool or type(refresh) is not bool
            or type(timeout) is not int or not 1 <= timeout <= 600
            or type(max_repairs) is not int or not 0 <= max_repairs <= 2
            or (action_id is not None and not valid_id(action_id)) or (execute and not precedent_path)):
        raise LedgerError("ARGUMENTS")
    if refresh and (not adapter_path or not editor_adapter):
        raise LedgerError("ARGUMENTS")
    if not refresh and (editor_adapter or include_paths or max_repairs != 1):
        raise LedgerError("ARGUMENTS")
    intent = {"project_id": configuration["project"]["id"], "run_id": run_id, "expected_revision": expected_revision,
              "precedent": str(Path(precedent_path).expanduser().resolve()) if precedent_path else None,
              "action_id": action_id, "execute": execute, "collect": collect,
              "adapter": str(adapter_path) if adapter_path else None, "locale": locale, "timeout": timeout,
              "refresh": refresh, "editor_adapter": str(editor_adapter) if editor_adapter else None,
              "include_paths": list(include_paths), "max_repairs": max_repairs}
    # Preview is read-only, including the operation journal.
    if not execute and not refresh:
        with EventStore(root, configuration["project"]["id"]) as store:
            view = get_projection(store, run_id)
        if view["state"]["revision"] != expected_revision:
            raise LedgerError("REVISION_CONFLICT")
        return {**view, "ok": True, "command": "work", "recorded_revision": expected_revision,
                "work_loop": candidate_view(view["state"], action_id)}
    with InvocationJournal(root, "work-loop", key) as journal:
        started = journal.read("started")
        if started and started["intent_hash"] != digest(intent):
            raise LedgerError("IDEMPOTENCY_CONFLICT")
        if started is None:
            with EventStore(root, configuration["project"]["id"]) as store:
                view = get_projection(store, run_id)
            if view["state"]["revision"] != expected_revision:
                raise LedgerError("REVISION_CONFLICT")
            candidate = candidate_view(view["state"], action_id)
            started = {"intent_hash": digest(intent), "candidate": candidate}
            journal.write("started", started)
        candidate = started["candidate"]
        if refresh:
            from .coordination import coordinate, stage_candidate
            updated = coordinate(root, configuration, run_id, proposer_adapter=adapter_path, editor_adapter=editor_adapter,
                                 key="work-editor-" + journal.prefix, expected_revision=expected_revision,
                                 include_paths=include_paths, timeout=timeout, max_repairs=max_repairs)
            attempt = updated["state"]["editor_attempt"]
            if attempt["validation"]["status"] == "MATCHED" and attempt["document"]["files"] and attempt["document"]["tests"]:
                updated = stage_candidate(root, configuration, run_id, key="work-stage-" + journal.prefix,
                                          expected_revision=updated["recorded_revision"])
                candidate = candidate_view(updated["state"], action_id)
            else:
                candidate = {"status": "REPAIR_REQUIRED", "action_id": None, "files": [], "tests": [], "executed": False}
            expected_revision = updated["recorded_revision"]
            if not execute:
                return {**updated, "ok": candidate["action_id"] is not None, "command": "work", "work_loop": candidate}
        from .effects import authorize, execute as execute_effect
        if candidate["action_id"] is None:
            with EventStore(root, configuration["project"]["id"]) as store:
                from .kernel.reducer import projection, replay
                view = projection(replay(store.events(run_id, through=expected_revision)))
            return {**view, "ok": False, "command": "work", "recorded_revision": view["state"]["revision"],
                    "work_loop": candidate}
        # Revision validation happens under authorize's mutation lock. Calling
        # with the same key reuses its receipt, never issues a second lease.
        from .authority import require_current_approval_valid
        from .progress import report
        require_current_approval_valid()
        report("candidate_execute")
        blocked = journal.read("blocked")
        if blocked is None:
            try:
                permission = authorize(root, configuration, run_id, candidate["action_id"], precedent_path,
                                       "work-authorize-" + journal.prefix, expected_revision=expected_revision)
            except LedgerError as error:
                if error.code not in {"EXECUTION_BLOCKED", "DECISION_KIND", "EDITOR_DECISION_REQUIRED",
                                      "EDITOR_DECISION_CHANGED", "EDITOR_REFERENCE_CHANGED", "HANDOFF_REPAIR_REQUIRED",
                                      "EXECUTION_OUTCOME_UNKNOWN"}:
                    raise
                blocked = {"reason": error.code}
                journal.write("blocked", blocked)
        if blocked is not None:
            with EventStore(root, configuration["project"]["id"]) as store:
                from .kernel.reducer import projection, replay
                result = projection(replay(store.events(run_id, through=expected_revision)))
            result["recorded_revision"] = expected_revision
            outcome = {**candidate, "status": "BLOCKED", "reason": blocked["reason"]}
        else:
            if fault:
                fault("after_authorize")
            result = execute_effect(root, configuration, run_id, permission["lease_id"], precedent_path,
                                    "work-execute-" + journal.prefix, fault=fault)
            outcome = _outcome(result)
        if collect:
            from .responses import compose
            answer = compose(root, configuration, run_id, key="work-collect-" + journal.prefix,
                             expected_revision=result["recorded_revision"], adapter_path=adapter_path,
                             locale=locale, timeout=timeout)
            result = {**answer, **({"execution": result["execution"]} if "execution" in result else {})}
        return {**result, "ok": outcome["status"] == "COMPLETED", "command": "work", "work_loop": outcome}
