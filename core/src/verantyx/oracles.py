"""Execute finite Python-call contracts without importing candidates in the parent.

The child sees only a selected source snapshot and one JSON input. Expected
values, provenance, project files and the ledger stay outside its read scope.
Seatbelt policy is the narrow Precedent-style execution boundary; the original
Precedent module is pinned and never modified. A child return frame is observed
data, not authenticated testimony that the child used any particular algorithm.
"""
from datetime import timedelta
from pathlib import Path
import base64
import hashlib
import json
import platform
import sys
import tempfile
import uuid

from .adapters.command_process import BoundedProcess
from .adapters.observations import observe, read_document
from .adapters.precedent_backend import PrecedentBackend
from .adapters.proposal_validation import valid_id
from .application import now, iso, get_projection, _receipt_view
from .domain.codec import digest
from .domain.oracles import validate_spec, origins, compare
from .errors import LedgerError
from .storage.sqlite import EventStore
from .verification import _read, _append, _read_input

CHILD = '''import json,resource,runpy,sys
resource.setrlimit(resource.RLIMIT_CPU,(12,12))
resource.setrlimit(resource.RLIMIT_FSIZE,(65536,65536))
resource.setrlimit(resource.RLIMIT_NOFILE,(32,32))
request=json.loads(sys.stdin.buffer.read(8192))
namespace=runpy.run_path(sys.argv[1],run_name='candidate')
result=namespace[sys.argv[2]](request)
sys.stdout.write(json.dumps({'protocol':'verantyx.oracle.return.v1','value':result},ensure_ascii=True,allow_nan=False,separators=(',',':'))+'\\n')
'''
CHILD_ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "TMPDIR": "/nonexistent", "LANG": "C.UTF-8"}


def engine_identity(precedent, expected_precedent_hash=None):
    # Verify the selected module's pin before its trusted top-level code runs.
    backend = PrecedentBackend(precedent, expected_hash=expected_precedent_hash)
    return {"id": "parent.python-json.v1", "source_sha256": digest({
                "application": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "domain": hashlib.sha256(Path(__file__).with_name("domain").joinpath("oracles.py").read_bytes()).hexdigest(),
                "process": hashlib.sha256(Path(__file__).with_name("adapters").joinpath("command_process.py").read_bytes()).hexdigest()}),
            "runner_sha256": hashlib.sha256(CHILD.encode()).hexdigest(),
            "python_sha256": hashlib.sha256(read_document(Path(sys.executable).resolve(), 64 * 1024 * 1024)).hexdigest(),
            "environment_hash": digest(CHILD_ENV), "platform": platform.platform(), "precedent": backend.identity}


def _child_command(stage, function):
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise LedgerError("ORACLE_ISOLATION_UNAVAILABLE")
    python = str(Path(sys.executable).resolve())
    # No project root, spec, home, ledger, site packages, inherited environment,
    # file writes, network, process fork, signal or Mach task access is granted.
    # The selected interpreter's runtime may be a Homebrew framework. Allow
    # its resolved base installation, not the project-local virtualenv/home.
    reads = [str(stage), str(Path(sys.base_prefix).resolve()), "/System", "/usr/lib", python]
    policy = ('(version 1)(deny default)(allow process-exec)(allow sysctl-read)(allow file-read-metadata)'
              '(allow file-read* (literal "/") (literal "/dev/null") (literal "/dev/urandom") '
              + ' '.join('(subpath ' + json.dumps(path) + ')' for path in reads) + ')')
    return {"argv": ["/usr/bin/sandbox-exec", "-p", policy, python, "-I", "-S", str(stage / "runner.py"),
                     str(stage / "candidate.py"), function], "cwd": str(stage), "env": dict(CHILD_ENV)}


def observe_candidate(raw, spec):
    observations = []
    for case in spec["cases"]:
        with tempfile.TemporaryDirectory(prefix="verantyx-oracle-") as temporary:
            stage = Path(temporary).resolve()
            (stage / "candidate.py").write_bytes(raw)
            (stage / "runner.py").write_text(CHILD)
            command = _child_command(stage, spec["function"])
            stdout, reason, returncode = b"", None, None
            try:
                with BoundedProcess(command, timeout=spec["timeout"], max_output=spec["max_output"]) as process:
                    stdout = process.document(case["input"])
                    returncode = process.process.returncode
            except LedgerError as error:
                if error.code not in ("BRIDGE_TIMEOUT", "BRIDGE_OUTPUT_LIMIT", "BRIDGE_PROCESS_FAILED", "BRIDGE_PROTOCOL", "BRIDGE_START_FAILED"):
                    raise
                reason, returncode = error.code, error.details.get("returncode")
            observations.append({"case_id": case["id"], "outcome": "RETURNED" if reason is None else "UNAVAILABLE",
                                 "stdout_base64": base64.b64encode(stdout).decode(), "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                                 "returncode": returncode, "reason": reason})
    return observations


def _view(receipt, key):
    result = _receipt_view(receipt, key)
    for event in receipt["events"]:
        if event["command_id"] == receipt["command_id"] and event["type"].startswith("Oracle"):
            p = event["payload"]
            identifier = p["plan"]["id"] if event["type"] == "OraclePlanned" else p["oracle_id"]
            result.update(oracle_id=identifier, oracle=result["state"]["oracles"][identifier])
            result["plan_hash"] = digest(result["oracle"]["plan"])
    result["ok"] = result.get("oracle", {}).get("status") not in ("INVALIDATED", "OUTCOME_UNKNOWN")
    return result


def plan_oracle(root, configuration, run_id, spec, key, *, precedent, ttl=300, expected_revision=None, clock=now):
    validate_spec(spec)
    if not valid_id(run_id) or not valid_id(key) or type(ttl) is not int or not 1 <= ttl <= 86400:
        raise LedgerError("ARGUMENTS")
    if expected_revision is not None and (type(expected_revision) is not int or expected_revision < 0):
        raise LedgerError("ARGUMENTS")
    intent = {"operation": "oracle-plan", "run_id": run_id, "spec": spec, "precedent": str(precedent), "ttl": ttl, "expected_revision": expected_revision}
    with EventStore(root, configuration["project"]["id"], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached:
            return _view(cached, key)
        previous, state = _read(store, run_id)
        if expected_revision is not None and expected_revision != state["revision"]:
            raise LedgerError("REVISION_CONFLICT")
        claim = next((c for c in (state["proposal"] or {}).get("claims", []) if c["id"] == spec["claim_id"]), None)
        if claim is None:
            raise LedgerError("VERIFICATION_CLAIM_UNKNOWN")
        ref = state["latest_observations"].get(spec["target_path"])
        target = state["observations"].get(ref)
        moment = clock()
        created = iso(moment)
        if not target or target["status"] != "OBSERVED" or not target["observed_at"] <= created < target["expires_at"]:
            raise LedgerError("VERIFICATION_TARGET_UNAVAILABLE")
        if hashlib.sha256(_read_input(root, spec["target_path"])).hexdigest() != target["sha256"]:
            raise LedgerError("VERIFICATION_TARGET_CHANGED")
        for source in spec["oracle"]["source_refs"]:
            obs = state["observations"].get(source)
            if not obs or obs["status"] != "OBSERVED" or state["latest_observations"].get(obs["path"]) != source or not obs["observed_at"] <= created < obs["expires_at"]:
                raise LedgerError("ORACLE_SOURCE_INVALID")
            if hashlib.sha256(_read_input(root, obs["path"])).hexdigest() != obs["sha256"]:
                raise LedgerError("ORACLE_SOURCE_INVALID")
        engine = engine_identity(precedent)
        plan = {"id": str(uuid.uuid4()), "spec": spec, "claim_hash": digest(claim), "proposal_hash": digest(state["proposal"]),
                "target": {"path": target["path"], "sha256": target["sha256"], "size": target["size"], "source_ref": ref},
                "created_at": created, "expires_at": iso(moment + timedelta(seconds=ttl)), "engine": engine, "engine_hash": digest(engine)}
        plan["origins"] = origins(plan)
        return _view(_append(store, previous, [("OraclePlanned", {"plan": plan}, created)], key, intent, clock), key)


def run_oracle(root, configuration, run_id, oracle_id, key, *, precedent, clock=now, fault=None):
    if not all(valid_id(value) for value in (run_id, oracle_id, key)):
        raise LedgerError("ARGUMENTS")
    intent = {"operation": "oracle-run", "run_id": run_id, "oracle_id": oracle_id, "precedent": str(precedent)}
    with EventStore(root, configuration["project"]["id"], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached:
            return _view(cached, key)
        previous, state = _read(store, run_id)
        item = state.get("oracles", {}).get(oracle_id)
        if not item:
            raise LedgerError("ORACLE_UNKNOWN")
        if item["status"] not in ("PLANNED", "STARTED"):
            raise LedgerError("ORACLE_FINISHED")
        plan, interrupted = item["plan"], item["status"] == "STARTED"
        if not interrupted:
            started = iso(clock())
            _append(store, previous, [("OracleStarted", {"oracle_id": oracle_id, "plan_hash": digest(plan), "started_at": started}, started)],
                    "oracle-start-" + oracle_id, {**intent, "operation": "oracle-start"}, clock)
            previous, state = _read(store, run_id)
            if fault:
                fault("after_start")
        receipt = {"oracle_id": oracle_id, "plan_hash": digest(plan), "finished_at": None,
                   "outcome": "OUTCOME_UNKNOWN" if interrupted else "INVALIDATED", "observations": None, "result": None,
                   "reason": "INTERRUPTED" if interrupted else None}
        changes = []
        if not interrupted:
            reason = None
            if iso(clock()) >= plan["expires_at"]:
                reason = "PLAN_EXPIRED"
            elif digest(state["proposal"]) != plan["proposal_hash"]:
                reason = "PROPOSAL_CHANGED"
            else:
                try:
                    backend_pin = digest(plan["engine"]["precedent"])
                    if digest(engine_identity(precedent, backend_pin)) != plan["engine_hash"]:
                        reason = "ENGINE_CHANGED"
                    raw = _read_input(root, plan["target"]["path"]) if reason is None else None
                    if raw is not None and hashlib.sha256(raw).hexdigest() != plan["target"]["sha256"]:
                        reason = "TARGET_CHANGED"
                    for ref in plan["spec"]["oracle"]["source_refs"] if reason is None else []:
                        source = state["observations"][ref]
                        if hashlib.sha256(_read_input(root, source["path"])).hexdigest() != source["sha256"]:
                            reason = "ORACLE_CHANGED"
                    if reason is None:
                        observations = observe_candidate(raw, plan["spec"])
                        if fault:
                            fault("after_check")
                        result = compare(plan, observations)
                    for ref in [plan["target"]["source_ref"], *plan["spec"]["oracle"]["source_refs"]]:
                        before = state["observations"][ref]
                        moment = clock()
                        current = observe(root, before["path"], iso(moment), iso(moment + timedelta(seconds=300)))
                        changes.append(("ObservationRecorded", current, iso(moment)))
                        if current["status"] != "OBSERVED" or current["sha256"] != before["sha256"]:
                            reason = "TARGET_CHANGED" if ref == plan["target"]["source_ref"] else "ORACLE_CHANGED"
                    if reason is None and digest(engine_identity(precedent, backend_pin)) != plan["engine_hash"]:
                        reason = "ENGINE_CHANGED"
                except LedgerError as error:
                    reason = ("ISOLATION_UNAVAILABLE" if error.code == "ORACLE_ISOLATION_UNAVAILABLE" else
                              "ENGINE_CHANGED" if error.code.startswith("PRECEDENT_") else "TARGET_UNAVAILABLE")
            receipt["finished_at"] = iso(clock())
            if reason is None and receipt["finished_at"] >= plan["expires_at"]:
                reason = "PLAN_EXPIRED"
            if reason is None:
                receipt.update(outcome="COMPLETED", observations=observations, result=result)
            else:
                receipt["reason"] = reason
        receipt["finished_at"] = receipt["finished_at"] or iso(clock())
        changes.append(("OracleRecorded", receipt, receipt["finished_at"]))
        return _view(_append(store, previous, changes, key, intent, clock), key)


def list_oracles(root, configuration, run_id, archive_id=None):
    with EventStore(root, configuration["project"]["id"]) as store:
        view = get_projection(store, run_id, archive_id)
        return {"schema_version": 1, "ok": True, "command": "oracles", "run_id": run_id,
                "oracles": list(view["state"].get("oracles", {}).values()), "trust": view["state"]["trust"], "historical_assessment": True}
