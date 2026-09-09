"""Durable delivery of explicitly selected proposal generators.

Immutable invocation markers are operational records. The project's SQLite
event ledger remains the sole authority for proposals and project decisions.
Jobs never dispatch execution, adoption, governance or memory-save commands.
"""
from datetime import timedelta
from pathlib import Path
import hashlib

from .adapters.command_process import load_command
from .adapters.invocation_journal import InvocationJournal
from .adapters.observations import normalize_path, read_document
from .adapters.proposal_validation import valid_id
from .application import get_projection, iso, now
from .bridges import _selected_files, propose
from .domain.codec import decode, digest
from .domain.events import fields, hash_value, require, timestamp, uuid_value
from .errors import LedgerError
from .kernel.rules import catalog
from .storage.sqlite import EventStore

FORMAT = "verantyx.proposal-job.v1"


def _executor_fingerprint(command):
    # Bind the launcher and an explicit script, not just strings naming them.
    # Dynamically imported modules/services are not covered by this manifest.
    pinned = {}
    for argument in command["argv"]:
        path = Path(argument)
        if not path.is_absolute() and command["cwd"] is not None:
            path = Path(command["cwd"]) / path
        if path.is_absolute() and path.is_file():
            resolved = path.resolve()
            pinned[str(resolved)] = hashlib.sha256(read_document(resolved, 64 * 1024 * 1024)).hexdigest()
    return digest({"command_identity": command["identity"], "launcher_files": pinned})


def _rules(store):
    return digest(list(catalog(store.events()).values()))


def _assets(store, state, locale):
    from .assets import project_catalog
    return digest(project_catalog(store, state, locale))


def _attest(root, configuration, journal, job):
    # Optional signature support retains the legacy local operator mode.
    try:
        from .authority import attest_proposal_job
    except ImportError:
        if (Path(root) / ".verantyx/authority.db").exists():
            raise LedgerError("BRIDGE_CONFIG", {"reason": "AUTHORITY_MODULE_REQUIRED"}) from None
        return
    attest_proposal_job(root, configuration, journal, job)


def _fingerprints(root, state, include):
    return [{k: f[k] for k in ("path", "sha256", "source_ref")}
            for f in _selected_files(root, state, include)]


def _validate(job):
    extended = type(job) is dict and "collect" in job
    fields(job, ("format", "id", "project_id", "run_id", "adapter", "adapter_sha256", "executor_sha256",
                 "expected_revision", "include_paths", "files", "rules_hash", "locale", "timeout", "max_output",
                 "available_at", "expires_at", "created_at", "intent_hash") +
                 (("collect", "assets_hash") if extended else ()))
    if extended:
        require(job["collect"] is True, "JOB_INVALID")
        hash_value(job["assets_hash"])
    require(job["format"] == FORMAT and valid_id(job["id"]) and valid_id(job["run_id"]), "JOB_INVALID")
    uuid_value(job["project_id"])
    require(type(job["adapter"]) is str and Path(job["adapter"]).is_absolute(), "JOB_INVALID")
    for key in ("adapter_sha256", "executor_sha256", "rules_hash", "intent_hash"):
        hash_value(job[key])
    require(type(job["expected_revision"]) is int and job["expected_revision"] > 0, "JOB_INVALID")
    require(type(job["include_paths"]) is list and len(job["include_paths"]) <= 16, "JOB_INVALID")
    require(job["include_paths"] == sorted(set(normalize_path(p) for p in job["include_paths"])), "JOB_INVALID")
    require(job["locale"] in ("en", "ja", "zh-Hans", "ko", "es"), "JOB_INVALID")
    require(type(job["timeout"]) is int and 1 <= job["timeout"] <= 600
            and type(job["max_output"]) is int and 1024 <= job["max_output"] <= 4 * 1024 * 1024, "JOB_INVALID")
    for key in ("available_at", "expires_at", "created_at"):
        timestamp(job[key])
    require(job["created_at"] <= job["available_at"] < job["expires_at"], "JOB_INVALID")
    require(type(job["files"]) is list and len(job["files"]) == len(job["include_paths"]), "JOB_INVALID")
    for value, path in zip(job["files"], job["include_paths"]):
        fields(value, ("path", "sha256", "source_ref"))
        require(value["path"] == path and type(value["source_ref"]) is str, "JOB_INVALID")
        hash_value(value["sha256"])
    return job


def _load(journal, configuration):
    value = journal.read("queued")
    if value is None:
        raise LedgerError("JOB_NOT_FOUND")
    _validate(value)
    require(value["project_id"] == configuration["project"]["id"] and
            journal.prefix == digest({"operation": "job", "key": value["id"]}), "JOB_INVALID")
    return value


def _view(journal, job):
    state, details = "QUEUED", None
    for stage, status in (("started", "RUNNING_OR_INTERRUPTED"), ("cancelled", "CANCELLED"),
                          ("failed", "FAILED"), ("response", "COMPLETED")):
        value = journal.read(stage)
        if value is not None:
            state, details = value.get("status", status), value
    value = {"schema_version": 1, "ok": state not in ("FAILED", "STALE", "OUTCOME_UNKNOWN"),
            "command": "job", "job_id": job["id"], "run_id": job["run_id"], "status": state,
            "available_at": job["available_at"], "expires_at": job["expires_at"],
            "expected_revision": job["expected_revision"], "adapter_sha256": job["adapter_sha256"],
            "proposal_only": True, "details": details}
    if job.get("collect"):
        value["collect"] = True
    return value


def submit(root, configuration, run_id, *, adapter_path, key, expected_revision,
           include_paths=(), delay=0, ttl=3600, timeout=60, max_output=262144, locale=None, clock=now, collect=False):
    require(valid_id(key) and valid_id(run_id), "ARGUMENTS")
    require(type(collect) is bool, "ARGUMENTS")
    require(type(delay) is int and 0 <= delay <= 604800 and type(ttl) is int and 1 <= ttl <= 604800, "ARGUMENTS")
    adapter = str(Path(adapter_path).expanduser().resolve())
    raw = read_document(adapter, 65536)
    command = load_command(adapter)
    include = sorted(set(normalize_path(p) for p in include_paths))
    intent = {"run_id": run_id, "adapter": adapter, "adapter_sha256": hashlib.sha256(raw).hexdigest(),
              "executor_sha256": _executor_fingerprint(command), "expected_revision": expected_revision,
              "include_paths": include, "delay": delay, "ttl": ttl, "timeout": timeout,
              "max_output": max_output, "locale": locale or configuration["ui"]["locale"]}
    if collect:
        intent["collect"] = True
    with InvocationJournal(root, "job", key) as journal:
        previous = journal.read("queued")
        if previous:
            job = _load(journal, configuration)
            require(job["intent_hash"] == digest(intent), "IDEMPOTENCY_CONFLICT")
            _attest(root, configuration, journal, job)
            return {**_view(journal, job), "duplicate": True}
        with EventStore(root, configuration["project"]["id"]) as store:
            state = get_projection(store, run_id)["state"]
            require(state["revision"] == expected_revision, "REVISION_CONFLICT")
            fingerprints, rules_hash = _fingerprints(root, state, include), _rules(store)
            assets_hash = _assets(store, state, intent["locale"]) if collect else None
        started = clock()
        job = {k: v for k, v in intent.items() if k not in ("delay", "ttl")}
        job.update(format=FORMAT, id=key, project_id=configuration["project"]["id"],
                   created_at=iso(started), available_at=iso(started + timedelta(seconds=delay)),
                   expires_at=iso(started + timedelta(seconds=delay + ttl)),
                   files=fingerprints, rules_hash=rules_hash, intent_hash=digest(intent))
        if collect:
            job["assets_hash"] = assets_hash
        _validate(job)
        journal.write("queued", job)
        _attest(root, configuration, journal, job)
        return {**_view(journal, job), "duplicate": False}


def list_jobs(root, configuration, *, clock=now):
    directory = Path(root) / ".verantyx/bridges"
    if directory.is_symlink():
        raise LedgerError("STORE_PATH")
    results = []
    for path in sorted(directory.glob("*.queued.json")):
        require(len(results) < 10000, "DOCUMENT_LIMIT")
        job = _validate(decode(read_document(path, 65536), 65536))
        # Published stages are immutable; status can be read while a worker holds
        # the per-job dispatch lock. Only mutations need exclusive access.
        journal = InvocationJournal(root, "job", job["id"])
        value = _view(journal, _load(journal, configuration))
        value["due"] = value["status"] == "QUEUED" and job["available_at"] <= iso(clock())
        results.append(value)
    return {"schema_version": 1, "ok": True, "command": "jobs", "jobs": sorted(results, key=lambda x: (x["available_at"], x["job_id"]))}


def cancel(root, configuration, job_id, *, reason, clock=now):
    require(valid_id(job_id) and type(reason) is str and 1 <= len(reason.strip()) <= 4000, "ARGUMENTS")
    with InvocationJournal(root, "job", job_id) as journal:
        job = _load(journal, configuration)
        if journal.read("cancelled"):
            return {**_view(journal, job), "duplicate": True}
        require(_view(journal, job)["status"] == "QUEUED", "JOB_STAGE")
        journal.write("cancelled", {"recorded_at": iso(clock()), "reason": reason})
        return _view(journal, job)


def run_job(root, configuration, job_id, *, recover=False, clock=now, fault=None):
    require(valid_id(job_id), "ARGUMENTS")
    with InvocationJournal(root, "job", job_id) as journal:
        job = _load(journal, configuration)
        view = _view(journal, job)
        if view["status"] in ("COMPLETED", "CANCELLED", "FAILED", "STALE", "OUTCOME_UNKNOWN"):
            return {**view, "duplicate": True}
        started = journal.read("started")
        bridge_key = "job-" + digest(job)
        if started:
            require(recover, "JOB_OUTCOME_UNKNOWN")
            # Only an already persisted response can be recovered. No remote call
            # is repeated after an ambiguous interruption.
            with InvocationJournal(root, "propose", bridge_key) as bridge:
                if bridge.read("response") is None:
                    journal.write("failed", {"status": "OUTCOME_UNKNOWN", "code": "BRIDGE_OUTCOME_UNKNOWN", "recorded_at": iso(clock())})
                    return _view(journal, job)
        else:
            require(job["available_at"] <= iso(clock()), "JOB_NOT_DUE")

        def before_invoke(command):
            # propose loads a command and persists its own start marker. Check
            # again at that final boundary, including time spent preparing input.
            # These checks do not make arbitrary OS file access atomic.
            raw = read_document(job["adapter"], 65536)
            current = load_command(job["adapter"])
            require(hashlib.sha256(raw).hexdigest() == job["adapter_sha256"]
                    and current["identity"] == command["identity"]
                    and _executor_fingerprint(command) == job["executor_sha256"], "JOB_ADAPTER_CHANGED")
            require(iso(clock()) < job["expires_at"], "JOB_EXPIRED")
            with EventStore(root, configuration["project"]["id"]) as store:
                project_revision = store.project_revision()
                state = get_projection(store, job["run_id"])["state"]
                require(state["revision"] == job["expected_revision"] and _rules(store) == job["rules_hash"], "JOB_CONTEXT_CHANGED")
                if job.get("collect"):
                    require(_assets(store, state, job["locale"]) == job["assets_hash"], "JOB_CONTEXT_CHANGED")
                require(_fingerprints(root, state, job["include_paths"]) == job["files"]
                        and store.project_revision() == project_revision, "JOB_CONTEXT_CHANGED")

        try:
            raw = read_document(job["adapter"], 65536)
            command = load_command(job["adapter"])
            require(hashlib.sha256(raw).hexdigest() == job["adapter_sha256"]
                    and _executor_fingerprint(command) == job["executor_sha256"], "JOB_ADAPTER_CHANGED")
            if not started:
                require(iso(clock()) < job["expires_at"], "JOB_EXPIRED")
                with EventStore(root, configuration["project"]["id"]) as store:
                    state = get_projection(store, job["run_id"])["state"]
                    require(state["revision"] == job["expected_revision"] and _rules(store) == job["rules_hash"], "JOB_CONTEXT_CHANGED")
                    if job.get("collect"):
                        require(_assets(store, state, job["locale"]) == job["assets_hash"], "JOB_CONTEXT_CHANGED")
                    require(_fingerprints(root, state, job["include_paths"]) == job["files"], "JOB_CONTEXT_CHANGED")
                journal.write("started", {"recorded_at": iso(clock()), "bridge_key": bridge_key})
                if fault:
                    fault("after_started")
                require(iso(clock()) < job["expires_at"], "JOB_EXPIRED")
            result = propose(root, configuration, job["run_id"], adapter_path=job["adapter"], key=bridge_key,
                             expected_revision=job["expected_revision"], include_paths=job["include_paths"],
                             timeout=job["timeout"], max_output=job["max_output"], locale=job["locale"],
                             before_invoke=before_invoke,
                             reuse_assets=job.get("collect", False),
                             fault=(lambda stage: fault("bridge." + stage)) if fault else None)
            if fault:
                fault("after_proposal")
            completion = {"recorded_at": iso(clock()), "revision": result["recorded_revision"],
                                       "proposal_ref": result["state"]["proposal_ref"],
                                       "input_sha256": result["input_sha256"], "recovered": bool(started)}
            if job.get("collect"):
                from .responses import compose
                response_key = "job-respond-" + digest(job)
                with InvocationJournal(root, "respond", response_key) as response_journal:
                    # An expired job cannot start another model call. A stored
                    # result can still be recovered, and an ambiguous call must
                    # keep its unknown outcome rather than become mere staleness.
                    if response_journal.read("started") is None:
                        require(iso(clock()) < job["expires_at"], "JOB_EXPIRED")

                def before_compose(command):
                    require(iso(clock()) < job["expires_at"], "JOB_EXPIRED")
                    require(hashlib.sha256(read_document(job["adapter"], 65536)).hexdigest() == job["adapter_sha256"]
                            and _executor_fingerprint(command) == job["executor_sha256"], "JOB_ADAPTER_CHANGED")

                captured = compose(root, configuration, job["run_id"], adapter_path=job["adapter"],
                                   key=response_key, expected_revision=result["recorded_revision"],
                                   locale=job["locale"], timeout=job["timeout"], reuse_assets=True, clock=clock,
                                   before_invoke=before_compose,
                                   fault=(lambda stage: fault("respond." + stage)) if fault else None)
                if fault:
                    fault("after_collection")
                response = captured["state"]["latest_response"]
                if response["generator_error"] == "JOB_EXPIRED":
                    raise LedgerError("JOB_EXPIRED")
                completion.update(revision=captured["recorded_revision"], response_ref=response["source_ref"],
                                  collection_mode=response["mode"], generator_error=response["generator_error"])
            journal.write("response", completion)
        except (OSError, LedgerError) as error:
            code = getattr(error, "code", "JOB_INPUT_UNAVAILABLE")
            unknown = code in {"BRIDGE_OUTCOME_UNKNOWN", "BRIDGE_TIMEOUT", "BRIDGE_PROCESS_FAILED", "BRIDGE_PROTOCOL", "BRIDGE_OUTPUT_LIMIT"}
            journal.write("failed", {"status": "OUTCOME_UNKNOWN" if unknown else "STALE" if code.startswith("JOB_") else "FAILED",
                                     "code": code, "recorded_at": iso(clock())})
        return _view(journal, job)


def worker(root, configuration, *, max_jobs=1, clock=now):
    require(type(max_jobs) is int and 1 <= max_jobs <= 100, "ARGUMENTS")
    completed = []
    for job in list_jobs(root, configuration, clock=clock)["jobs"]:
        if job["due"]:
            try:
                completed.append(run_job(root, configuration, job["job_id"], clock=clock))
            except LedgerError as error:
                if error.code != "STORE_BUSY":
                    raise
            if len(completed) >= max_jobs:
                break
    return {"schema_version": 1, "ok": all(item["ok"] for item in completed), "command": "worker", "processed": completed}
