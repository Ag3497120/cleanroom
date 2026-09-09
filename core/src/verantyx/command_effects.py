"""One-shot command effects. Labels describe authorized intent, not OS isolation.

Only an explicitly selected trusted local command is supported. Dynamic imports,
remote services and effects outside the declared targets remain that command's
trust boundary. Process completion never asserts external business success.
"""
from datetime import timedelta
from pathlib import Path
import hashlib
import time
import uuid

from .adapters.command_process import BoundedProcess, load_command
from .adapters.observations import observe, read_document
from .adapters.proposal_validation import valid_id
from .application import now, iso, get_projection, _receipt_view
from .domain.codec import digest
from .domain.command_effects import validate_spec, context_hash
from .errors import LedgerError
from .kernel.rules import catalog
from .storage.sqlite import EventStore
from .verification import _read, _append


def executor_identity(path, root, dependencies):
    command = load_command(path)
    # Proposal API credentials are late-bound and follow a different contract.
    # They must never enter this frozen, general-effect executor identity.
    if set(command) != {'argv', 'cwd', 'env', 'identity'}:
        raise LedgerError('COMMAND_EXECUTOR_UNAVAILABLE')
    if command["cwd"] is None:
        command["cwd"] = str(Path(root).resolve())
    cwd = Path(command["cwd"]).resolve()
    if not cwd.is_relative_to(Path(root).resolve()):
        raise LedgerError("COMMAND_CWD_OUTSIDE_PROJECT")
    command["cwd"] = str(cwd)
    command["identity"] = digest({k: command[k] for k in ("argv", "cwd", "env")})
    files = {}
    for arg in [*command["argv"], *dependencies]:
        candidate = Path(arg)
        if not candidate.is_absolute():
            candidate = cwd / candidate
        try:
            if candidate.is_file():
                resolved = candidate.resolve()
                files[str(resolved)] = hashlib.sha256(read_document(resolved, 64 * 1024 * 1024)).hexdigest()
        except OSError:
            raise LedgerError("COMMAND_EXECUTOR_UNAVAILABLE") from None
    executable = str(Path(command["argv"][0]).resolve())
    if executable not in files or any(str(Path(p).resolve()) not in files for p in dependencies):
        raise LedgerError("COMMAND_EXECUTOR_UNAVAILABLE")
    identity = {"config_sha256": hashlib.sha256(read_document(path, 65536)).hexdigest(),
                "command_hash": command["identity"], "argv_hash": digest(command["argv"]),
                "environment_hash": digest(command["env"]), "cwd": str(cwd), "files": files,
                "isolation": "NONE_TRUSTED_COMMAND"}
    identity["hash"] = digest(identity)
    return command, identity


def _rules(store):
    return digest(list(catalog(store.events()).values()))


def _target(root, path, when):
    observation = observe(root, path, iso(when), iso(when + timedelta(seconds=300)))
    result = {k: observation[k] for k in ("path", "status", "sha256", "size")}
    if result["status"] not in ("OBSERVED", "MISSING"):
        result.update(status="UNAVAILABLE", sha256=None, size=None)
    return result


def _current_reason(root, state, plan, store, command_path, moment):
    if iso(moment) >= plan["expires_at"]:
        return "PLAN_EXPIRED", None
    if str(Path(root).resolve()) != plan["root"]:
        return "ROOT_CHANGED", None
    if context_hash(state) != plan["context_hash"]:
        return "CONTEXT_CHANGED", None
    if _rules(store) != plan["rules_hash"]:
        return "RULES_CHANGED", None
    try:
        command, identity = executor_identity(command_path, root, plan["spec"]["dependencies"])
    except LedgerError:
        return "EXECUTOR_CHANGED", None
    if identity["hash"] != plan["executor"]["hash"]:
        return "EXECUTOR_CHANGED", None
    for precondition in plan["preconditions"]:
        if digest(_target(root, precondition["path"], moment)) != digest({k:v for k,v in precondition.items() if k != "source_ref"}):
            return "PRECONDITION_CHANGED", None
    return None, command


def _view(receipt, key):
    result = _receipt_view(receipt, key)
    for event in receipt["events"]:
        if event["command_id"] == receipt["command_id"] and event["type"].startswith("CommandEffect"):
            p = event["payload"]
            identifier = p["plan"]["id"] if event["type"] == "CommandEffectProposed" else p["effect_id"]
            result.update(command_effect_id=identifier, command_effect=result["state"]["command_effects"][identifier])
            result["plan_hash"] = digest(result["command_effect"]["plan"])
    result["ok"] = result.get("command_effect", {}).get("status") not in ("INVALIDATED", "OUTCOME_UNKNOWN", "PROCESS_FAILED")
    return result


def propose_command(root, configuration, run_id, spec, key, *, command_path, ttl=300, clock=now):
    validate_spec(spec)
    if not valid_id(run_id) or not valid_id(key) or type(ttl) is not int or not 1 <= ttl <= 86400:
        raise LedgerError("ARGUMENTS")
    intent = {"operation": "command-propose", "run_id": run_id, "spec": spec, "command_path": str(command_path), "ttl": ttl}
    with EventStore(root, configuration["project"]["id"], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached:
            return _view(cached, key)
        previous, state = _read(store, run_id)
        if state["proposal"] is None:
            raise LedgerError("COMMAND_PROPOSAL_REQUIRED")
        moment = clock()
        _, identity = executor_identity(command_path, root, spec["dependencies"])
        preconditions = []
        for path in spec["targets"]:
            ref = state["latest_observations"].get(path)
            observation = state["observations"].get(ref)
            if not observation or observation["status"] not in ("OBSERVED", "MISSING") or not observation["observed_at"] <= iso(moment) < observation["expires_at"]:
                raise LedgerError("COMMAND_TARGET_UNAVAILABLE")
            actual = _target(root, path, moment)
            if digest(actual) != digest({k:observation[k] for k in ("path", "status", "sha256", "size")}):
                raise LedgerError("COMMAND_TARGET_CHANGED")
            preconditions.append({**actual, "source_ref": ref})
        plan = {"id": str(uuid.uuid4()), "spec": spec, "root": str(Path(root).resolve()), "context_hash": context_hash(state),
                "proposal_hash": digest(state["proposal"]), "rules_hash": _rules(store), "executor": identity, "preconditions": preconditions,
                "created_at": iso(moment), "expires_at": iso(moment + timedelta(seconds=ttl))}
        return _view(_append(store, previous, [("CommandEffectProposed", {"plan": plan}, iso(moment))], key, intent, clock), key)


def authorize_command(root, configuration, run_id, effect_id, key, *, plan_hash, command_path, reason,
                      accept_unsandboxed=False, accept_irreversible=False, ttl=300, clock=now):
    if not all(valid_id(v) for v in (run_id, effect_id, key)) or type(ttl) is not int or not 1 <= ttl <= 86400:
        raise LedgerError("ARGUMENTS")
    if accept_unsandboxed is not True or type(accept_irreversible) is not bool:
        raise LedgerError("COMMAND_TRUST_REQUIRED")
    if type(reason) is not str or not 1 <= len(reason.strip()) <= 4000:
        raise LedgerError("ARGUMENTS")
    intent = {"operation": "command-authorize", "run_id": run_id, "effect_id": effect_id, "plan_hash": plan_hash,
              "command_path": str(command_path), "reason": reason, "ttl": ttl,
              "accept_unsandboxed": accept_unsandboxed, "accept_irreversible": accept_irreversible}
    with EventStore(root, configuration["project"]["id"], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached:
            return _view(cached, key)
        previous, state = _read(store, run_id)
        item = state.get("command_effects", {}).get(effect_id)
        if not item or item["status"] != "PROPOSED":
            raise LedgerError("COMMAND_NOT_PROPOSED")
        plan, moment = item["plan"], clock()
        if plan_hash != digest(plan):
            raise LedgerError("COMMAND_PLAN_CHANGED")
        if plan["spec"]["effect_class"] == "IRREVERSIBLE_EXTERNAL" and accept_irreversible is not True:
            raise LedgerError("COMMAND_IRREVERSIBLE_REQUIRED")
        changed, _ = _current_reason(root, state, plan, store, command_path, moment)
        if changed:
            raise LedgerError("COMMAND_AUTHORIZATION_STALE", {"reason": changed})
        authorization = {"effect_id": effect_id, "plan_hash": plan_hash, "basis_revision": state["revision"], "authorized_at": iso(moment),
                         "expires_at": min(plan["expires_at"], iso(moment + timedelta(seconds=ttl))), "accept_unsandboxed": True,
                         "accept_irreversible": accept_irreversible, "reason": reason}
        return _view(_append(store, previous, [("CommandEffectAuthorized", authorization, iso(moment))], key, intent, clock), key)


def execute_command(root, configuration, run_id, effect_id, key, *, command_path, clock=now, fault=None):
    if not all(valid_id(v) for v in (run_id, effect_id, key)):
        raise LedgerError("ARGUMENTS")
    intent = {"operation": "command-execute", "run_id": run_id, "effect_id": effect_id, "command_path": str(command_path)}
    with EventStore(root, configuration["project"]["id"], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached:
            return _view(cached, key)
        previous, state = _read(store, run_id)
        item = state.get("command_effects", {}).get(effect_id)
        if not item or item["status"] not in ("AUTHORIZED", "STARTED"):
            raise LedgerError("COMMAND_NOT_AUTHORIZED")
        plan, interrupted = item["plan"], item["status"] == "STARTED"
        authorization = item["authorization"]
        if not interrupted:
            started = iso(clock())
            payload = {"effect_id": effect_id, "plan_hash": digest(plan), "authorization_ref": item["authorization_ref"], "started_at": started}
            _append(store, previous, [("CommandEffectStarted", payload, started)], "command-start-" + effect_id,
                    {**intent, "operation": "command-start"}, clock)
            previous, state = _read(store, run_id)
            if fault:
                fault("after_start")
        receipt = {"effect_id": effect_id, "plan_hash": digest(plan), "authorization_ref": item["authorization_ref"],
                   "finished_at": None, "outcome": "OUTCOME_UNKNOWN" if interrupted else "INVALIDATED", "process": None,
                   "targets_after": [], "reason": "INTERRUPTED" if interrupted else None}
        if not interrupted:
            moment = clock()
            if iso(moment) >= authorization["expires_at"]:
                changed, command = "AUTHORIZATION_EXPIRED", None
            else:
                changed, command = _current_reason(root, state, plan, store, command_path, moment)
            if changed is None:
                from .writers import assert_no_live_writers
                try:
                    assert_no_live_writers(root, configuration, command['cwd'], clock=clock)
                except LedgerError as error:
                    changed = error.code
                if iso(clock()) >= min(authorization['expires_at'], plan['expires_at']):
                    changed = 'AUTHORIZATION_EXPIRED'
            receipt["reason"] = changed
            if changed is None:
                started_wall, process_result = time.monotonic(), None
                try:
                    with BoundedProcess(command, timeout=plan["spec"]["timeout"], max_output=plan["spec"]["max_output"]) as process:
                        try:
                            output = process.document(plan["spec"]["input"])
                        except LedgerError as error:
                            if error.code != "BRIDGE_PROCESS_FAILED":
                                raise
                            output = bytes(process.stdout)
                        process_result = {"returncode": process.process.returncode, "stdout_sha256": hashlib.sha256(output).hexdigest(),
                                          "output_bytes": process.output_bytes, "elapsed_ms": round((time.monotonic() - started_wall) * 1000),
                                          "effect_confirmation": "NOT_ASSESSED"}
                    if fault:
                        fault("after_process")
                    receipt["finished_at"] = iso(clock())
                    if receipt["finished_at"] >= authorization["expires_at"]:
                        receipt.update(outcome="OUTCOME_UNKNOWN", reason="EXPIRED_DURING_PROCESS")
                    else:
                        receipt.update(outcome="PROCESS_COMPLETED" if process_result["returncode"] == 0 else "PROCESS_FAILED",
                                       reason=None, process=process_result)
                except LedgerError as error:
                    receipt.update(outcome="OUTCOME_UNKNOWN", reason=error.code)
                receipt["targets_after"] = [_target(root, path, clock()) for path in plan["spec"]["targets"]]
        receipt["finished_at"] = receipt["finished_at"] or iso(clock())
        return _view(_append(store, previous, [("CommandEffectRecorded", receipt, receipt["finished_at"])], key, intent, clock), key)


def list_commands(root, configuration, run_id, archive_id=None):
    with EventStore(root, configuration["project"]["id"]) as store:
        view = get_projection(store, run_id, archive_id)
        return {"schema_version": 1, "ok": True, "command": "command-effects", "run_id": run_id,
                "command_effects": list(view["state"].get("command_effects", {}).values()), "trust": view["state"]["trust"], "historical_assessment": True}
