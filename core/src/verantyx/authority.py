"""Explicit Ed25519 command approval using an externally held private key.

The signed command gate authenticates key possession, not a natural person.
Same-user Python calls / file access are outside this cooperating CLI boundary.
It never generates or accepts a private key and never signs for an operator.
"""
from argparse import Namespace
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta
from pathlib import Path
import base64
import hashlib
import os
import uuid

from .adapters.observations import read_document
from .domain.codec import canonical, decode, digest
from .domain.events import fields, hash_value, require, timestamp, uuid_value
from .errors import LedgerError
from .security_journal import Journal, exclusive

FORMAT = "verantyx.command-approval.v1"
# Closed exemptions: every unknown command is protected by default. External
# process / MCP readers are intentionally absent because they execute adapters.
READ_COMMANDS = {"status", "config", "doctor", "replay", "gaps", "rights", "proposal-template", "events", "runs",
                 "archives", "rules", "precedents", "learn", "verifications", "oracles", "command-effects", "integration-review", "rule-policy-template", "rule-shadow-report",
                 "learn-material", "learn-due", "jobs", "writers", "authority-status", "authority-history"}
READ_COMMANDS.add("dictionary")
READ_COMMANDS.add("skills-stack")
READ_COMMANDS.update({"skills-policies", "skills-route", "skills", "skills-report"})
READ_COMMANDS.add("shared-context")
READ_COMMANDS.add("sovereignty")
READ_COMMANDS.update(("recap", "codex-usage"))
READ_COMMANDS.update(("constitution", "constitution-gaps"))
READ_COMMANDS.add("ownership")
CANDIDATE_COMMANDS = {"run", "resume"}
CONTROL_COMMANDS = {"authority-request", "authority-execute"}
CONTROLLED_WORKER_COMMANDS = {"service-worker"}  # Per-job signed attestation is mandatory in its dispatcher.
_APPROVED = ContextVar("verantyx_signed_command", default=None)
_APPROVED_CLOCK = ContextVar("verantyx_signed_command_clock", default=None)
TEXT_ARGUMENTS = {"command", "request", "reason", "summary", "statement", "message", "name", "purpose", "identity",
                  "query", "concept", "minimum_model", "counterexample", "check", "why_now", "owner", "source_ref"}


def signing_bytes(request):
    return canonical(request).encode("utf-8")


def public_key(path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        raw = read_document(path, 16384)
        key = serialization.load_pem_public_key(raw)
        require(isinstance(key, Ed25519PublicKey), "AUTHORITY_KEY_INVALID")
        return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    except (ValueError, TypeError):
        raise LedgerError("AUTHORITY_KEY_INVALID") from None


def verify(request, signature):
    from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        require(type(signature) is bytes and len(signature) == 64, "AUTHORITY_SIGNATURE_INVALID")
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(request["operator_key"])).verify(signature, signing_bytes(request))
    except (InvalidSignature, UnsupportedAlgorithm, ValueError, TypeError, KeyError):
        raise LedgerError("AUTHORITY_SIGNATURE_INVALID") from None


def validate_request(request):
    fields(request, ("format", "project_id", "project_root", "working_directory", "operator_key", "nonce", "issued_at", "expires_at",
                     "authority_revision", "authority_hash", "project_revision", "project_hash", "configuration_hash",
                     "writers_revision", "writers_hash", "operation", "input_files"))
    require(request["format"] == FORMAT, "AUTHORITY_REQUEST_INVALID")
    uuid_value(request["project_id"])
    uuid_value(request["nonce"])
    for name in ("operator_key", "authority_hash", "project_hash", "configuration_hash", "writers_hash"):
        hash_value(request[name])
    for name in ("authority_revision", "project_revision", "writers_revision"):
        require(type(request[name]) is int and request[name] >= 0, "AUTHORITY_REQUEST_INVALID")
    for name in ("project_root", "working_directory"):
        require(type(request[name]) is str and Path(request[name]).is_absolute(), "AUTHORITY_REQUEST_INVALID")
    for name in ("issued_at", "expires_at"):
        timestamp(request[name])
    require(request["issued_at"] < request["expires_at"], "AUTHORITY_REQUEST_INVALID")
    operation = request["operation"]
    fields(operation, ("argv", "arguments", "locale", "next_public_key"))
    require(type(operation["argv"]) is list and 1 <= len(operation["argv"]) <= 256
            and all(type(item) is str and len(item) <= 16000 for item in operation["argv"]), "AUTHORITY_REQUEST_INVALID")
    require(type(operation["arguments"]) is dict and type(operation["arguments"].get("command")) is str,
            "AUTHORITY_REQUEST_INVALID")
    require(operation["locale"] in ("ja", "en", "zh-Hans", "ko", "es"), "AUTHORITY_REQUEST_INVALID")
    if operation["next_public_key"] is not None:
        hash_value(operation["next_public_key"])
    require(type(request["input_files"]) is list and len(request["input_files"]) <= 256, "AUTHORITY_REQUEST_INVALID")
    previous = ""
    for item in request["input_files"]:
        fields(item, ("path", "sha256"))
        require(type(item["path"]) is str and Path(item["path"]).is_absolute() and item["path"] > previous,
                "AUTHORITY_REQUEST_INVALID")
        hash_value(item["sha256"])
        previous = item["path"]
    return request


def replay(entries):
    """Deterministic authorization history, without inspecting a process or clock."""
    result = {"enabled": False, "operator_key": None, "revision": 0, "hash": "0" * 64, "commands": {}, "proposal_jobs": {}}
    for entry in entries:
        kind, payload = entry["kind"], entry["payload"]
        require(entry["revision"] == result["revision"] + 1 and entry["previous_hash"] == result["hash"], "SECURITY_INTEGRITY")
        if kind == "CommandStarted":
            fields(payload, ("request", "signature"))
            request = validate_request(payload["request"])
            try:
                signature = base64.b64decode(payload["signature"], validate=True)
            except (ValueError, TypeError):
                raise LedgerError("SECURITY_INTEGRITY") from None
            verify(request, signature)
            require(request["project_id"] == entry["project_id"] and request["authority_revision"] == result["revision"]
                    and request["authority_hash"] == result["hash"] and request["nonce"] not in result["commands"]
                    and request["issued_at"] <= entry["recorded_at"] < request["expires_at"], "SECURITY_INTEGRITY")
            command = request["operation"]["arguments"]["command"]
            if result["enabled"]:
                require(request["operator_key"] == result["operator_key"] and command != "authority-enable", "SECURITY_INTEGRITY")
            else:
                require(command == "authority-enable" and request["operation"]["next_public_key"] == request["operator_key"],
                        "SECURITY_INTEGRITY")
            result["commands"][request["nonce"]] = {"request": request, "status": "INTERRUPTED_OR_RUNNING", "key_changed": False}
        elif kind == "AuthorityKeyChanged":
            fields(payload, ("nonce", "public_key"))
            current = result["commands"].get(payload["nonce"])
            require(current and current["status"] == "INTERRUPTED_OR_RUNNING" and not current["key_changed"], "SECURITY_INTEGRITY")
            request = current["request"]
            require(request["operation"]["arguments"]["command"] == ("authority-rotate" if result["enabled"] else "authority-enable")
                    and payload["public_key"] == request["operation"]["next_public_key"], "SECURITY_INTEGRITY")
            result.update(enabled=True, operator_key=payload["public_key"])
            current["key_changed"] = True
        elif kind == "ProposalJobAttested":
            fields(payload, ("source_nonce", "job"))
            current = result["commands"].get(payload["source_nonce"])
            require(current and current["status"] == "INTERRUPTED_OR_RUNNING"
                    and current["request"]["operator_key"] == result["operator_key"]
                    and current["request"]["issued_at"] <= entry["recorded_at"] < current["request"]["expires_at"],
                    "SECURITY_INTEGRITY")
            _job_matches(current["request"], payload["job"])
            result["proposal_jobs"][payload["job"]["id"]] = {
                "source_nonce": payload["source_nonce"], "job": payload["job"],
                "job_hash": digest(payload["job"]), "attestation_revision": entry["revision"], "attestation_hash": entry["hash"]}
        elif kind == "CommandFinished":
            fields(payload, ("nonce", "status", "result_hash", "error_code"))
            current = result["commands"].get(payload["nonce"])
            require(current and current["status"] == "INTERRUPTED_OR_RUNNING", "SECURITY_INTEGRITY")
            require(payload["status"] in ("RETURNED_OK", "RETURNED_ERROR", "ERROR_OUTCOME_UNVERIFIED"), "SECURITY_INTEGRITY")
            if payload["result_hash"] is not None:
                hash_value(payload["result_hash"])
            require(payload["error_code"] is None or type(payload["error_code"]) is str, "SECURITY_INTEGRITY")
            current.update({key: payload[key] for key in ("status", "result_hash", "error_code")})
        else:
            raise LedgerError("SECURITY_INTEGRITY")
        result.update(revision=entry["revision"], hash=entry["hash"])
    return result


def state(root, configuration):
    return replay(Journal(root, "authority", configuration["project"]["id"]).read())


def exempt(args):
    command = args.command
    return (command in READ_COMMANDS | CANDIDATE_COMMANDS | CONTROL_COMMANDS | CONTROLLED_WORKER_COMMANDS
            or (command == "keep" and all(getattr(args, name, None) is None
                for name in ("learn_candidate", "delegate_candidate", "check_spec")))
            or (command == "work" and not getattr(args, "execute", False) and not getattr(args, "refresh", False))
            or (command in ("export", "handoff-packet", "verify-template", "asset-template", "skills-newsletter")
                and not getattr(args, "output", None)))


@contextmanager
def command_scope(root, configuration, args):
    """Central CLI gate; new commands require a signature until explicitly exempt."""
    with exclusive(root, "command-gate"):
        current = state(root, configuration)
        approved = _APPROVED.get()
        if approved is not None:
            require(approved["project_root"] == str(Path(root).resolve())
                    and digest(approved["operation"]["arguments"]) == digest(vars(args)), "AUTHORITY_OPERATION_MISMATCH")
            from .application import iso, now
            require(approved["issued_at"] <= iso((_APPROVED_CLOCK.get() or now)()) < approved["expires_at"], "AUTHORITY_EXPIRED")
        elif args.command in ("authority-enable", "authority-rotate") or (current["enabled"] and not exempt(args)):
            raise LedgerError("AUTHORITY_REQUIRED", {"command": args.command})
        yield


def require_current_approval_valid():
    """Recheck a signed command immediately before each separate effect.

    Return its canonical expiry so a child can enforce the same upper bound.
    A caller without an active signed command keeps its existing permission
    path (including the separate signed-job checks used by service-worker).
    """
    approval = _APPROVED.get()
    if approval is None:
        return None
    from .application import iso, now
    at = iso((_APPROVED_CLOCK.get() or now)())
    require(approval["issued_at"] <= at < approval["expires_at"], "AUTHORITY_EXPIRED")
    return approval["expires_at"]


def require_current_input_hash(path, sha256):
    """Bind bytes read at a later stage to this active signed input manifest."""
    approval = _APPROVED.get()
    if approval is None:
        return
    require_current_approval_valid()
    chosen = str(Path(path).expanduser().absolute())
    expected = next((row for row in approval["input_files"] if row["path"] == chosen), None)
    require(expected is not None and expected["sha256"] == sha256, "AUTHORITY_INPUT_CHANGED")


def _parse_operation(argv, locale):
    from .cli import parse
    require(type(argv) is list and argv and all(type(item) is str for item in argv), "AUTHORITY_REQUEST_INVALID")
    require(not any(item == "--project" or item.startswith("--project=") or item in ("--version", "--help", "-h", "--tutorial")
                    for item in argv), "AUTHORITY_REQUEST_INVALID")
    options, args = parse(argv)
    require(args.command is not None and args.command not in CONTROL_COMMANDS | READ_COMMANDS | CANDIDATE_COMMANDS
            and args.command not in ("tutorial", "start"), "AUTHORITY_REQUEST_INVALID")
    if args.command == "setup":
        require(args.non_interactive, "AUTHORITY_REQUEST_INVALID")
    if args.command == "job-submit":
        # Replay cannot consult another machine's HOME for tilde expansion.
        require(not args.adapter.startswith("~"), "AUTHORITY_REQUEST_INVALID")
    from .i18n import normalize
    try:
        effective_locale = normalize(options.lang) if options.lang else locale
    except ValueError:
        raise LedgerError("ARGUMENTS") from None
    return args, effective_locale


def _input_files(arguments, bind_inputs=()):
    import shutil
    paths = set()
    for name, value in arguments.items():
        if name in TEXT_ARGUMENTS or name == "output":
            continue
        for item in value if type(value) is list else [value]:
            if type(item) is str and len(item) < 4096:
                try:
                    path = Path(item).expanduser()
                    if path.is_symlink() or path.is_file():
                        require(not path.is_symlink(), "STORE_PATH")
                        paths.add(str(path.resolve()))
                    if name == "precedent" and path.is_dir():
                        paths.add(str((path.resolve() / "precedent/execution.py")))
                except OSError:
                    raise LedgerError("AUTHORITY_INPUT_CHANGED") from None
    for value in bind_inputs:
        path = Path(value).expanduser()
        require(not path.is_symlink(), "STORE_PATH")
        paths.add(str(path.resolve()))
    # Explicit adapter/spec JSON can name a launcher or script. Hash those
    # files too, without executing them. Imported libraries/services remain
    # outside this bounded input manifest and are stated as such in the docs.
    values, pending = {}, set(paths)
    while pending:
        require(len(values) + len(pending) <= 256, "DOCUMENT_LIMIT")
        path = pending.pop()
        require(not Path(path).is_symlink(), "STORE_PATH")
        raw = read_document(path, 64 * 1024 * 1024)
        values[path] = hashlib.sha256(raw).hexdigest()
        if len(raw) > 1024 * 1024 or not raw.lstrip().startswith(b"{"):
            continue
        try:
            document = decode(raw)
        except LedgerError:
            continue

        def commands(value):
            if type(value) is dict:
                argv = value.get("argv")
                if type(argv) is list and argv and all(type(item) is str for item in argv):
                    cwd = Path(value["cwd"]).expanduser() if type(value.get("cwd")) is str else Path.cwd()
                    for index, item in enumerate(argv):
                        selected = Path(item).expanduser()
                        if not selected.is_absolute():
                            selected = cwd / selected
                        if index == 0 and not selected.exists():
                            executable = shutil.which(item)
                            if executable:
                                selected = Path(executable)
                        if selected.is_file() or selected.is_symlink():
                            # Runtime launcher symlinks resolve to their inspected target.
                            resolved = str(selected.resolve())
                            if resolved not in values:
                                pending.add(resolved)
                for nested in value.values():
                    commands(nested)
            elif type(value) is list:
                for nested in value:
                    commands(nested)
        commands(document)
    return [{"path": path, "sha256": values[path]} for path in sorted(values)]


def _basis(root, configuration):
    from . import config
    from .storage.sqlite import EventStore
    actual, _ = config.load(root)
    require(actual is not None and digest(actual) == digest(configuration), "AUTHORITY_STALE")
    with EventStore(root, configuration["project"]["id"]) as store:
        events = store.events()
        project_revision = store.project_revision()
    writers = Journal(root, "writers", configuration["project"]["id"]).read()
    return {"project_revision": project_revision, "project_hash": digest(events), "configuration_hash": digest(configuration),
            "writers_revision": len(writers), "writers_hash": writers[-1]["hash"] if writers else "0" * 64}


def request(root, configuration, argv, *, ttl=300, bind_inputs=(), clock=None):
    from .application import iso, now
    clock = clock or now
    require(type(ttl) is int and 1 <= ttl <= 3600, "ARGUMENTS")
    args, locale = _parse_operation(argv, configuration["ui"]["locale"])
    with exclusive(root, "command-gate"):
        current = state(root, configuration)
        next_key = public_key(args.public_key) if args.command in ("authority-enable", "authority-rotate") else None
        require((current["enabled"] and args.command != "authority-enable")
                or (not current["enabled"] and args.command == "authority-enable"), "AUTHORITY_NOT_ENABLED")
        issued = clock()
        value = {"format": FORMAT, "project_id": configuration["project"]["id"], "project_root": str(Path(root).resolve()),
                 "working_directory": str(Path.cwd().resolve()), "operator_key": current["operator_key"] or next_key,
                 "nonce": str(uuid.uuid4()), "issued_at": iso(issued), "expires_at": iso(issued + timedelta(seconds=ttl)),
                 "authority_revision": current["revision"], "authority_hash": current["hash"], **_basis(root, configuration),
                 "operation": {"argv": argv, "arguments": vars(args), "locale": locale, "next_public_key": next_key},
                 "input_files": _input_files(vars(args), bind_inputs)}
        return validate_request(value)


def execute(root, configuration, approval, signature, *, clock=None, fault=None):
    from .application import iso, now
    clock = clock or now
    validate_request(approval)
    verify(approval, signature)
    with exclusive(root, "command-gate"):
        journal = Journal(root, "authority", configuration["project"]["id"])
        current = state(root, configuration)
        require(approval["nonce"] not in current["commands"], "AUTHORITY_USED")
        require(approval["project_id"] == configuration["project"]["id"] and approval["project_root"] == str(Path(root).resolve())
                and approval["working_directory"] == str(Path.cwd().resolve()), "AUTHORITY_OPERATION_MISMATCH")
        require(current["revision"] == approval["authority_revision"] and current["hash"] == approval["authority_hash"],
                "AUTHORITY_STALE")
        if current["enabled"]:
            require(approval["operator_key"] == current["operator_key"], "AUTHORITY_KEY_INVALID")
        else:
            require(approval["operation"]["arguments"]["command"] == "authority-enable", "AUTHORITY_NOT_ENABLED")
        args, locale = _parse_operation(approval["operation"]["argv"], configuration["ui"]["locale"])
        require(digest(vars(args)) == digest(approval["operation"]["arguments"]) and locale == approval["operation"]["locale"],
                "AUTHORITY_OPERATION_MISMATCH")
        basis = _basis(root, configuration)
        require(basis == {key: approval[key] for key in basis}, "AUTHORITY_STALE")
        require(_input_files(vars(args), [item["path"] for item in approval["input_files"]]) == approval["input_files"],
                "AUTHORITY_INPUT_CHANGED")
        started_at = iso(clock())
        require(approval["issued_at"] <= started_at < approval["expires_at"], "AUTHORITY_EXPIRED")
        started = journal.append("CommandStarted", {"request": approval, "signature": base64.b64encode(signature).decode("ascii")},
                                 started_at, current["revision"])
        if fault:
            fault("after_started")
        token = _APPROVED.set(approval)
        clock_token = _APPROVED_CLOCK.set(clock)
        try:
            # Consumption is durable before dispatch; interruption never retries an effect.
            require(approval["issued_at"] <= iso(clock()) < approval["expires_at"], "AUTHORITY_EXPIRED")
            require(_basis(root, configuration) == basis, "AUTHORITY_STALE")
            require(_input_files(vars(args), [item["path"] for item in approval["input_files"]]) == approval["input_files"],
                    "AUTHORITY_INPUT_CHANGED")
            require(approval["issued_at"] <= iso(clock()) < approval["expires_at"], "AUTHORITY_EXPIRED")
            if args.command in ("authority-enable", "authority-rotate"):
                value = public_key(args.public_key)
                require(value == approval["operation"]["next_public_key"], "AUTHORITY_INPUT_CHANGED")
                at = iso(clock())
                require(approval["issued_at"] <= at < approval["expires_at"], "AUTHORITY_EXPIRED")
                journal.append("AuthorityKeyChanged", {"nonce": approval["nonce"], "public_key": value},
                               at, started["revision"])
                result = {"ok": True, "command": args.command, "enabled": True, "public_key": value,
                          "identity": "EXTERNAL_KEY_POSSESSION_ONLY"}
            elif args.command == "setup":
                from . import config
                from .cli import setup
                import io
                from contextlib import redirect_stdout
                existing, raw = config.load(root)
                require(digest(existing) == approval["configuration_hash"], "AUTHORITY_STALE")
                require(approval["issued_at"] <= iso(clock()) < approval["expires_at"], "AUTHORITY_EXPIRED")
                with redirect_stdout(io.StringIO()) as output:
                    setup(root, existing, raw, locale, args, True, True)
                result = decode(output.getvalue())
            else:
                from .application import dispatch
                result = dispatch(root, configuration, args, locale)
            if fault:
                fault("after_operation")
            ending = {"nonce": approval["nonce"], "status": "RETURNED_OK" if result.get("ok", True) else "RETURNED_ERROR",
                      "result_hash": digest(result), "error_code": None}
        except LedgerError as error:
            ending = {"nonce": approval["nonce"], "status": "ERROR_OUTCOME_UNVERIFIED", "result_hash": None, "error_code": error.code}
            journal.append("CommandFinished", ending, iso(clock()), len(journal.read()))
            raise
        finally:
            _APPROVED.reset(token)
            _APPROVED_CLOCK.reset(clock_token)
        journal.append("CommandFinished", ending, iso(clock()), len(journal.read()))
        return {"schema_version": 1, "ok": result.get("ok", True), "command": "authority-execute", "nonce": approval["nonce"],
                "authorization": "SIGNATURE_VERIFIED", "operation_status": ending["status"], "result": result,
                "identity": "EXTERNAL_KEY_POSSESSION_ONLY"}


def inspect(root, configuration, *, history=False):
    current = state(root, configuration)
    value = {"schema_version": 1, "ok": True, "command": "authority-history" if history else "authority-status",
             "enabled": current["enabled"], "public_key": current["operator_key"], "revision": current["revision"],
             "identity": "EXTERNAL_KEY_POSSESSION_ONLY" if current["enabled"] else "TRUSTED_LOCAL_OPERATOR_COMPATIBILITY",
             "project_event_ledger": "UNCHANGED; operational authorization history is separate",
             "default_for_new_commands": "SIGNATURE_REQUIRED", "unsigned_candidate_commands": sorted(CANDIDATE_COMMANDS),
             "proposal_jobs_with_attestations": len(current["proposal_jobs"]),
             "os_security_boundary": False}
    if history:
        value["commands"] = [{"nonce": nonce, "command": item["request"]["operation"]["arguments"]["command"],
                              "status": item["status"], "result_hash": item.get("result_hash"), "error_code": item.get("error_code")}
                             for nonce, item in current["commands"].items()]
    return value


def _job_matches(approval, job):
    """Pure binding checks for a signed submit intent and its recorded job."""
    from datetime import datetime
    from .jobs import _validate
    _validate(job)
    args = approval["operation"]["arguments"]
    require(args.get("command") == "job-submit", "AUTHORITY_JOB_MISMATCH")
    expected = {"id": args.get("key"), "run_id": args.get("run_id"), "expected_revision": args.get("expected_revision"),
                "timeout": args.get("timeout"), "max_output": args.get("max_output"),
                "locale": approval["operation"]["locale"], "project_id": approval["project_id"]}
    require(all(digest(job[key]) == digest(value) for key, value in expected.items()), "AUTHORITY_JOB_MISMATCH")
    require(job["include_paths"] == sorted(set(args.get("include", []))), "AUTHORITY_JOB_MISMATCH")
    require(bool(job.get("collect", False)) == bool(args.get("collect", False)), "AUTHORITY_JOB_MISMATCH")
    path = Path(args.get("adapter", ""))
    if not path.is_absolute():
        path = Path(approval["working_directory"]) / path
    # No filesystem resolution occurs during replay. The actual submit uses
    # the same absolute adapter path, and requests reject direct symlink inputs.
    require(job["adapter"] == os.path.normpath(str(path)), "AUTHORITY_JOB_MISMATCH")
    selected = next((item for item in approval["input_files"] if item["path"] == job["adapter"]), None)
    require(selected and selected["sha256"] == job["adapter_sha256"], "AUTHORITY_JOB_MISMATCH")
    times = [datetime.strptime(job[key], "%Y-%m-%dT%H:%M:%S.%fZ") for key in ("created_at", "available_at", "expires_at")]
    require(type(args.get("delay")) is int and type(args.get("ttl")) is int
            and times[1] - times[0] == timedelta(seconds=args["delay"])
            and times[2] - times[1] == timedelta(seconds=args["ttl"]), "AUTHORITY_JOB_MISMATCH")


def _attestation_marker(item):
    return {"format": "verantyx.signed-proposal-job.v1", "source_nonce": item["source_nonce"], "job_hash": item["job_hash"],
            "attestation_revision": item["attestation_revision"], "attestation_hash": item["attestation_hash"]}


def attest_proposal_job(root, configuration, journal, job):
    """Called by job-submit for new and duplicate jobs while the signed call runs."""
    from .application import iso, now
    current = state(root, configuration)
    if not current["enabled"]:
        return None
    approval = _APPROVED.get()
    require(approval is not None and approval["project_root"] == str(Path(root).resolve()), "AUTHORITY_REQUIRED")
    _job_matches(approval, job)
    source = current["commands"].get(approval["nonce"])
    require(source and source["status"] == "INTERRUPTED_OR_RUNNING"
            and approval["operator_key"] == current["operator_key"] and digest(source["request"]) == digest(approval),
            "AUTHORITY_JOB_MISMATCH")
    existing = current["proposal_jobs"].get(job["id"])
    if existing and existing["source_nonce"] == approval["nonce"]:
        require(existing["job_hash"] == digest(job), "AUTHORITY_JOB_MISMATCH")
        marker = _attestation_marker(existing)
        require(journal.read("operator-approval-" + approval["nonce"]) == marker, "AUTHORITY_JOB_MISMATCH")
        return marker
    at = iso((_APPROVED_CLOCK.get() or now)())
    require(approval["issued_at"] <= at < approval["expires_at"], "AUTHORITY_EXPIRED")
    entry = Journal(root, "authority", configuration["project"]["id"]).append(
        "ProposalJobAttested", {"source_nonce": approval["nonce"], "job": job}, at, current["revision"])
    item = {"source_nonce": approval["nonce"], "job_hash": digest(job), "attestation_revision": entry["revision"],
            "attestation_hash": entry["hash"]}
    marker = _attestation_marker(item)
    stage = "operator-approval-" + approval["nonce"]
    recorded = journal.read(stage)
    require(recorded is None or recorded == marker, "AUTHORITY_JOB_MISMATCH")
    if recorded is None:
        journal.write(stage, marker)
    return marker


def require_proposal_job_approval(root, configuration, journal, job):
    """A service may deliver only a completed signed submit under the current key.

    The worker must still run the existing job expiry/context/adapter checks.
    These attestations grant proposal delivery only, never execution or adoption.
    """
    current = state(root, configuration)
    if not current["enabled"]:
        return {"approved": True, "mode": "TRUSTED_LOCAL_OPERATOR_COMPATIBILITY"}
    item = current["proposal_jobs"].get(job.get("id"))
    require(item is not None and item["job_hash"] == digest(job), "AUTHORITY_JOB_MISMATCH")
    source = current["commands"].get(item["source_nonce"])
    require(source and source["status"] == "RETURNED_OK" and source["request"]["operator_key"] == current["operator_key"],
            "AUTHORITY_JOB_MISMATCH")
    _job_matches(source["request"], job)
    marker = journal.read("operator-approval-" + item["source_nonce"])
    require(marker == _attestation_marker(item), "AUTHORITY_JOB_MISMATCH")
    return {"approved": True, "mode": "SIGNED_PROPOSAL_JOB", "source_nonce": item["source_nonce"], "job_hash": item["job_hash"]}
