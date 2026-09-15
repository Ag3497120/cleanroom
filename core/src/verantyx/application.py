"""M1 controller: record requests, observe explicit files, and assess proposals."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import os
import uuid

from .adapters.observations import normalize_path, observe, read_document
from .adapters.proposal_validation import validate_proposal, valid_id
from .domain.codec import decode, digest, MAX_ARCHIVE
from .domain.events import make_event, require
from .errors import LedgerError
from .kernel.reducer import projection, replay
from .storage.sqlite import EventStore

CAPABILITIES = {"tutorial": True, "setup": True, "event_ledger": True, "recorded_proposals": True,
                "file_observations": True, "deterministic_replay": True, "archive_import_export": True,
                "agent_execution": False, "model_connection": "EXPLICIT_COMMAND_ADAPTER", "rule_enforcement": "SCOPED_LOCAL_EFFECTS",
                "cross_policy_backend": "EXTERNAL_VM_REQUIRED", "learning_candidates": True, "mastery_assessment": False,
                "learning_submissions": True, "precedent_execution_port": True,
                "canonical_adoption": "UNCHECKED_OUT_BRANCH_CAS", "memory_connection": "EXPLICIT_REVIEWED_MCP_PACKET"}
CAPABILITIES.update(claim_verification="FROZEN_DETERMINISTIC_PROPERTIES", rule_scope="FINITE_ALLOWLIST_WITH_EXCEPTIONS",
                    rule_modes=["OFF", "SHADOW", "WARN", "BLOCK"],
                    learning_assessment="BOUNDED_FIXED_EXERCISES", learning_review_schedule=True,
                    proposal_jobs="EXPLICIT_LOCAL_GENERATORS", cryptographic_operator_identity=False,
                    multi_device_execution=False)
CAPABILITIES.update(operator_command_signatures="EXPLICIT_EXTERNAL_ED25519",
                    writer_process_registry="OBSERVED_PID_START_CWD",
                    candidate_oracle="ISOLATED_PROCESS_PARENT_FINITE_IO_COMPARATOR",
                    general_effects="EXPLICIT_TRUSTED_UNSANDBOXED_COMMAND",
                    canonical_integration="VERIFIED_MERGE_OR_SINGLE_CHANGE_REBASE_WITH_SEPARATE_PERMISSION")
CAPABILITIES.update(model_connection="EXPLICIT_COMMAND_OR_PROVIDER_API_ADAPTER",
                    model_api_providers=["openai", "anthropic", "gemini", "ollama"],
                    external_learning_feedback="ATTRIBUTED_SELECTED_SUBMISSION_AND_RUBRIC_ONLY",
                    notifications="ONE_REVIEWED_PACKET_TO_ONE_ENDPOINT",
                    service_registration="EXPLICIT_LAUNCHD_OR_SYSTEMD_MANAGER",
                    archive_transport="EXPLICIT_SHARED_DIRECTORY_REFERENCE_ONLY")
CAPABILITIES.update(general_response="PROPOSAL_KERNEL_GENERATED_EXPLANATION_AND_CAPTURE",
                    response_languages=["ja", "en", "zh-Hans", "ko", "es"],
                    response_structure="CROSS_VM_FINITE_FACE_EDGE_ROUTING_WITH_EXPLICIT_FALLBACK",
                    experience_dictionary="PROJECT_RULES_METHODS_FAILURES_AND_LEARNING_WITH_SOURCES",
                    automatic_experience_capture="RECORDED_CHECKS_AND_UNVERIFIED_MODEL_CANDIDATES",
                    reusable_verification="EXPLICIT_NEW_TARGET_AND_EXISTING_VERIFICATION_GATE")


def now():
    return datetime.now(timezone.utc)


def iso(value):
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def load_proposal(path):
    if path is None:
        return None
    raw = read_document(path, 256 * 1024)
    document = validate_proposal(decode(raw))
    if not valid_id(document["task_id"]):
        raise LedgerError("PROPOSAL_INVALID")
    return {"raw": raw.decode("utf-8"), "document": document, "sha256": hashlib.sha256(raw).hexdigest(),
            "basis_revision": document["context_revision"]}


def record_run(root, configuration, *, request=None, run_id=None, proposal_path=None, observe_paths=(),
               ttl=300, key=None, expected_revision=None, resume=False, locale=None, clock=now, fault=None, context=None, backend=None,
               expected_project_revision=None, before_record=None):
    if type(ttl) is not int or not 1 <= ttl <= 86400:
        raise LedgerError("ARGUMENTS")
    explicit = sorted({normalize_path(p) for p in observe_paths})
    if len(explicit) > 32 or (expected_revision is not None and (type(expected_revision) is not int or expected_revision < 0)):
        raise LedgerError("ARGUMENTS")
    if not resume and (type(request) is not str or not 1 <= len(request.strip()) <= 16000):
        raise LedgerError("ARGUMENTS")
    proposal = load_proposal(proposal_path)
    chosen = run_id or (proposal["document"]["task_id"] if proposal is not None and not resume else None)
    if chosen is not None and not valid_id(chosen):
        raise LedgerError("ARGUMENTS")
    if resume and chosen is None:
        raise LedgerError("ARGUMENTS")
    if key is None:
        key = str(uuid.uuid4())
    if not valid_id(key):
        raise LedgerError("ARGUMENTS")
    locale = locale or configuration["ui"]["locale"]
    intent = {"operation": "resume" if resume else "run", "request": request, "run_id": chosen,
              "proposal": proposal, "observe": explicit, "ttl": ttl, "expected_revision": expected_revision,
              "locale": locale, "context": context, "learning": configuration["learning"]}
    input_hash = digest(intent)
    if expected_project_revision is not None:
        if type(expected_project_revision) is not int or expected_project_revision < 0:
            raise LedgerError("ARGUMENTS")
        # Preserve old command hashes unless the external proposal boundary is used.
        input_hash = digest({**intent, "expected_project_revision": expected_project_revision})
    project_id = configuration["project"]["id"]
    with EventStore(root, project_id, create=True) as store:
        receipt = store.receipt(key, input_hash)
        if receipt:
            return _receipt_view(receipt, key)
        chosen = chosen or str(uuid.uuid4())
        project_revision = store.project_revision()
        if expected_project_revision is not None and project_revision != expected_project_revision:
            raise LedgerError("REVISION_CONFLICT", {"reason": "PROJECT_CONTEXT_CHANGED"})
        if before_record is not None:
            before_record()
        all_events = store.events()
        previous = [e for e in all_events if e["stream_id"] == chosen]
        if resume and not previous:
            raise LedgerError("RUN_NOT_FOUND")
        if not resume and previous:
            raise LedgerError("RUN_EXISTS")
        state = replay(previous)
        revision = state["revision"] if state else 0
        if expected_revision is not None and expected_revision != revision:
            raise LedgerError("REVISION_CONFLICT", {"expected": expected_revision, "actual": revision})
        if proposal is not None:
            if proposal["document"]["task_id"] != chosen:
                raise LedgerError("PROPOSAL_CONTEXT", {"reason": "TASK_MISMATCH"})
            if proposal["basis_revision"] != revision:
                raise LedgerError("PROPOSAL_CONTEXT", {"expected": revision, "actual": proposal["basis_revision"]})
        scope = sorted(set(state["read_scope"] if state else []) | set(explicit))
        if len(scope) > 32:
            raise LedgerError("ARGUMENTS")
        command_id = str(uuid.uuid4())
        batch = []

        def add(kind, payload, when=None):
            prior = batch[-1] if batch else (previous[-1] if previous else None)
            event = make_event(project_id, chosen, revision + len(batch) + 1, command_id,
                               iso(when or clock()), kind, payload, str(uuid.uuid4()), prior)
            batch.append(event)

        if not resume:
            add("TaskRequested", {"request": request, "locale": locale, "read_scope": scope,
                                  "context": context or {"component": "UNSPECIFIED", "workload": "UNSPECIFIED", "risk": "UNSPECIFIED"},
                                  "learning": configuration["learning"]})
        if proposal is not None:
            add("ProposalRecorded", proposal)
        if resume:
            additions = [path for path in explicit if path not in state["read_scope"]]
            if additions:
                add("ReadScopeExtended", {"paths": additions})
        # A resume refreshes all previously selected files. Replay never does.
        for path in scope:
            started = clock()
            observation = observe(root, path, iso(started), iso(started + timedelta(seconds=ttl)))
            add("ObservationRecorded", observation, started)
        from .governance import policy_context
        add("PolicyContextRecorded", policy_context(all_events, replay([*previous, *batch]), backend))
        evaluated = clock()
        add("EvaluationRecorded", {"as_of": iso(evaluated), "evaluator": "m1.v1"}, evaluated)
        receipt = store.append(key, input_hash, chosen, revision, batch, fault=fault, project_revision=project_revision)
        return _receipt_view(receipt, key)


def _receipt_view(receipt, key):
    view = projection(replay(receipt["events"]))
    created = {}
    for event in receipt["events"]:
        if event["command_id"] != receipt["command_id"]:
            continue
        if event["type"] == "PrecedentCandidateCreated":
            created["precedent_id"] = event["payload"]["id"]
        elif event["type"] == "RuleCandidateCreated":
            created["rule_id"] = event["payload"]["rule"]["id"]
        elif event["type"] == "EffectAuthorized":
            created["lease_id"] = event["payload"]["lease"]["id"]
    return {**created, "schema_version": 1, "ok": True, "command": "record", "idempotency_key": key,
            "duplicate": receipt["duplicate"], "recorded_revision": receipt["last_revision"], **view}


def get_events(store, run_id=None, archive_id=None):
    events = store.archive(archive_id)["events"] if archive_id else store.events(run_id)
    if archive_id and run_id is not None:
        events = [event for event in events if event["stream_id"] == run_id]
    if run_id is not None and not events:
        raise LedgerError("RUN_NOT_FOUND")
    return events


def get_projection(store, run_id, archive_id=None):
    return projection(replay(get_events(store, run_id, archive_id)), trusted=archive_id is None)


def proposal_template(store, run_id, locale):
    state = get_projection(store, run_id)["state"]
    actions = []
    for index, (path, ref) in enumerate(sorted(state["latest_observations"].items()), 1):
        actions.append({"id": f"observation-{index}", "tool_id": "file.observe", "arguments": {"path": path},
                        "reason": "Review this recorded file observation.", "source_refs": [ref]})
    # The schema allows at most sixteen proposed actions.
    return {"schema_version": 1, "task_id": run_id, "context_revision": state["revision"],
            "response_locale": locale, "summary": "Editable recorded proposal; this is not a verification result.",
            "claims": [], "actions": actions[:16], "unknowns": []}


def write_new_output(root, target, contents):
    """Atomic publication of an explicit export; never overwrite an existing file."""
    target = Path(target).expanduser()
    if target.resolve().is_relative_to((Path(root) / ".verantyx").resolve()):
        raise LedgerError("PATH_SCOPE")
    temporary = target.parent / (".verantyx-export-" + uuid.uuid4().hex)
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            raise LedgerError("OUTPUT_EXISTS") from None
    finally:
        temporary.unlink(missing_ok=True)


def dispatch(root, configuration, args, locale):
    from .authority import command_scope
    with command_scope(root, configuration, args):
        return _dispatch(root, configuration, args, locale)


def _dispatch(root, configuration, args, locale):
    command = args.command
    if command == "organize":
        from .agent_runtime import organize
        return organize(root, configuration, args.run_id, adapter=args.adapter,
                        key=args.key, timeout=args.timeout)
    from .commands_v04 import handler
    extension = handler(command)
    if extension is not None:
        return extension.dispatch(root, configuration, args, locale)
    from .commands_v03 import COMMANDS, dispatch as dispatch_v03
    if command in COMMANDS:
        return dispatch_v03(root, configuration, args, locale)
    if command == "learn":
        from .learning import list_learning
        return list_learning(root, configuration, args.run_id, getattr(args, "archive", None))
    if command in ("run", "resume"):
        return record_run(root, configuration, request=getattr(args, "request", None),
                          run_id=getattr(args, "run_id", None), proposal_path=args.proposal,
                          observe_paths=args.observe, ttl=args.ttl, key=args.key,
                          expected_revision=args.expected_revision, resume=command == "resume", locale=locale,
                          context={key: getattr(args, key) for key in ("component", "workload", "risk")} if command == "run" else None)
    project_id = configuration["project"]["id"]
    controls = {"decide", "precedent-accept", "rule-draft", "rule-shadow", "rule-confirm", "rule-activate",
                "rule-retire", "rule-amend", "rule-contest"}
    if command in ("authorize", "execute", "inspect-workspace"):
        from .effects import dispatch_effect
        return dispatch_effect(root, configuration, args)
    with EventStore(root, project_id, create=command == "import" or command in controls) as store:
        if command in controls:
            from .governance import control
            return control(store, configuration, command, args.target, point_id=getattr(args, "point", None),
                           choice=getattr(args, "choice", None), reason=getattr(args, "reason", None),
                           key=args.key, expected_revision=args.expected_revision)
        if command in ("rules", "precedents"):
            from .governance import precedents
            from .kernel.rules import catalog
            return {"schema_version": 1, "ok": True, "command": command,
                    command: list((catalog if command == "rules" else precedents)(store.events()).values())}
        if command == "learn":
            view = get_projection(store, args.run_id)
            return {"schema_version": 1, "ok": True, "command": command, "run_id": args.run_id,
                    **view["state"]["deltas"]}

        archive_id = getattr(args, "archive", None)
        if command in ("replay", "gaps", "rights"):
            view = get_projection(store, args.run_id, archive_id)
            if command == "gaps":
                view = {"run_id": args.run_id, "gaps": view["state"]["assessment"]["gaps"],
                        "question": view["state"]["assessment"]["question"], "trust": view["state"]["trust"]}
            elif command == "rights":
                view = {"run_id": args.run_id, **view["state"]["rights"]}
            return {"schema_version": 1, "ok": True, "command": command, **view}
        if command == "events":
            return {"schema_version": 1, "ok": True, "command": command,
                    "events": get_events(store, args.run_id, archive_id),
                    "trust": "ARCHIVE_ONLY" if archive_id else "LOCAL_HISTORY"}
        if command == "runs":
            events = get_events(store, archive_id=archive_id)
            runs = []
            for run_id in dict.fromkeys(event["stream_id"] for event in events):
                state = replay(event for event in events if event["stream_id"] == run_id)
                runs.append({"run_id": run_id, "request": state["request"], "revision": state["revision"],
                             "assessment": state["assessment"], "trust": "ARCHIVE_ONLY" if archive_id else "LOCAL_HISTORY"})
            return {"schema_version": 1, "ok": True, "command": command, "runs": runs}
        if command == "proposal-template":
            return proposal_template(store, args.run_id, locale)
        if command == "export":
            bundle = store.export(archive_id)
            if args.output:
                write_new_output(root, args.output, bundle.encode("utf-8"))
            return {"schema_version": 1, "ok": True, "command": command, "output": args.output, "bundle": bundle}
        if command == "import":
            raw = read_document(args.path, MAX_ARCHIVE)
            return {"schema_version": 1, "ok": True, "command": command, **store.import_archive(raw, iso(now()))}
        if command == "archives":
            return {"schema_version": 1, "ok": True, "command": command, "archives": store.archives()}
    raise LedgerError("ARGUMENTS")
