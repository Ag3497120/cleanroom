"""Explicit local bounded verification; arbitrary commands are not registered."""
from datetime import timedelta
from pathlib import Path
import base64
import hashlib
import os
import platform
import stat
import uuid

from .adapters.observations import _open_under, observe, read_document
from .adapters.proposal_validation import valid_id
from .application import now, iso, _receipt_view, get_projection
from .domain.codec import decode, digest
from .domain.events import make_event
from .domain.verification import MAX_INPUT, AXES, validate_spec, evidence_result, origins
from .errors import LedgerError
from .kernel.reducer import replay
from .storage.sqlite import EventStore


def engine_identity():
    # Measured outside replay. Its checksum is pinned before a run starts.
    from .domain import verification
    return {"id": "bounded.predicates.v1", "source_sha256": hashlib.sha256(Path(verification.__file__).read_bytes()).hexdigest(),
            "python": platform.python_version(), "platform": platform.platform()}


def _read_input(root, path):
    try:
        fd = _open_under(root, path)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_INPUT:
                raise LedgerError("VERIFICATION_INPUT_LIMIT")
            raw = stream.read(MAX_INPUT + 1)
            after = os.fstat(stream.fileno())
            if len(raw) > MAX_INPUT:
                raise LedgerError("VERIFICATION_INPUT_LIMIT")
        current_fd = _open_under(root, path)
        try:
            current = os.fstat(current_fd)
        finally:
            os.close(current_fd)
        fingerprint = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        if fingerprint(before) != fingerprint(after) or fingerprint(after) != fingerprint(current):
            raise LedgerError("VERIFICATION_TARGET_CHANGED")
        return raw
    except OSError:
        raise LedgerError("VERIFICATION_TARGET_UNAVAILABLE") from None


def _read(store, run_id):
    previous = store.events(run_id)
    if not previous:
        raise LedgerError("RUN_NOT_FOUND")
    return previous, replay(previous)


def _append(store, previous, changes, key, intent, clock):
    batch, command_id = [], str(uuid.uuid4())
    for kind, payload, when in [*changes, ("EvaluationRecorded", {"as_of": iso(clock()), "evaluator": "m1.v1"}, None)]:
        batch.append(make_event(store.project_id, previous[-1]["stream_id"], previous[-1]["revision"] + len(batch) + 1,
                                command_id, when or iso(clock()), kind, payload, str(uuid.uuid4()), batch[-1] if batch else previous[-1]))
    return store.append(key, digest(intent), previous[-1]["stream_id"], previous[-1]["revision"], batch)


def _view(receipt, key):
    result = _receipt_view(receipt, key)
    for event in receipt["events"]:
        if event["command_id"] != receipt["command_id"] or not event["type"].startswith("Verification"):
            continue
        payload = event["payload"]
        identifier = payload["plan"]["id"] if event["type"] == "VerificationPlanned" else payload["verification_id"]
        result.update(verification_id=identifier, verification=result["state"]["verifications"][identifier])
        result["plan_hash"] = digest(result["verification"]["plan"])
    result["ok"] = result.get("verification", {}).get("status") not in ("INVALIDATED", "OUTCOME_UNKNOWN")
    return result


def verification_template(root, configuration, run_id, claim_id, target_path, locale=None):
    if not valid_id(run_id) or not valid_id(claim_id):
        raise LedgerError("ARGUMENTS")
    from .adapters.observations import normalize_path
    normalize_path(target_path)
    with EventStore(root, configuration["project"]["id"]) as store:
        _, state = _read(store, run_id)
        if not state["proposal"] or claim_id not in {c["id"] for c in state["proposal"]["claims"]}:
            raise LedgerError("VERIFICATION_CLAIM_UNKNOWN")
        ref = state["latest_observations"].get(target_path)
        if not ref or state["observations"][ref]["status"] != "OBSERVED":
            raise LedgerError("VERIFICATION_TARGET_UNAVAILABLE")
        labels = {
            "en": ("The selected file has the explicitly expected JSON value at this pointer.", "Replace with the source of the expected value."),
            "ja": ("選択したファイルの指定箇所が、明示したJSONの期待値と一致する。", "期待値を定めた根拠に置き換えてください。"),
            "zh-Hans": ("所选文件指定位置的JSON值与明确指定的预期值一致。", "请填写预期值的来源。"),
            "ko": ("선택한 파일의 지정 위치에 있는 JSON 값이 명시한 예상값과 일치합니다.", "예상값을 정한 근거로 바꾸세요."),
            "es": ("El valor JSON de la posición indicada coincide con el valor esperado explícito.", "Sustituye este texto por la fuente del valor esperado."),
        }
        property_label, oracle_label = labels.get(locale or configuration["ui"]["locale"], labels["en"])
        return {"claim_id": claim_id, "target_path": target_path, "property": property_label,
                "method": "TEST", "checks": [{"id": "property-1", "kind": "json.equals", "pointer": "", "expected": None}],
                "negative_controls": [], "reproduces": None,
                "oracle": {"description": oracle_label, "source_refs": []},
                "provenance": {axis: "" for axis in AXES}}


def plan_verification(root, configuration, run_id, spec, key, *, ttl=300, expected_revision=None, clock=now):
    if not valid_id(run_id) or not valid_id(key) or type(ttl) is not int or not 1 <= ttl <= 86400:
        raise LedgerError("ARGUMENTS")
    validate_spec(spec)
    if expected_revision is not None and (type(expected_revision) is not int or expected_revision < 0):
        raise LedgerError("ARGUMENTS")
    intent = {"operation": "verification-plan", "run_id": run_id, "spec": spec, "ttl": ttl, "expected_revision": expected_revision}
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
        observation = state["observations"].get(ref)
        moment = clock()
        created = iso(moment)
        if not observation or observation["status"] != "OBSERVED" or not observation["observed_at"] <= created < observation["expires_at"]:
            raise LedgerError("VERIFICATION_TARGET_UNAVAILABLE")
        raw = _read_input(root, spec["target_path"])
        if hashlib.sha256(raw).hexdigest() != observation["sha256"]:
            raise LedgerError("VERIFICATION_TARGET_CHANGED")
        identity = engine_identity()
        plan = {"id": str(uuid.uuid4()), "spec": spec, "claim_hash": digest(claim), "proposal_hash": digest(state["proposal"]),
                "target": {"path": spec["target_path"], "sha256": observation["sha256"], "size": observation["size"], "source_ref": ref},
                "created_at": created, "expires_at": iso(moment + timedelta(seconds=ttl)),
                "engine": identity, "engine_hash": digest(identity)}
        plan["origins"] = origins(plan)
        return _view(_append(store, previous, [("VerificationPlanned", {"plan": plan}, created)], key, intent, clock), key)


def run_verification(root, configuration, run_id, verification_id, key, *, clock=now, fault=None, expected_revision=None):
    if not valid_id(run_id) or not valid_id(verification_id) or not valid_id(key):
        raise LedgerError("ARGUMENTS")
    intent = {"operation": "verification-run", "run_id": run_id, "verification_id": verification_id}
    if expected_revision is not None:
        if type(expected_revision) is not int or expected_revision <= 0:
            raise LedgerError("ARGUMENTS")
        intent["expected_revision"] = expected_revision
    with EventStore(root, configuration["project"]["id"], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached:
            return _view(cached, key)
        previous, state = _read(store, run_id)
        item = state.get("verifications", {}).get(verification_id)
        if item is None:
            raise LedgerError("VERIFICATION_UNKNOWN")
        if item["status"] not in ("PLANNED", "STARTED"):
            raise LedgerError("VERIFICATION_ALREADY_FINISHED")
        plan = item["plan"]
        interrupted = item["status"] == "STARTED"
        if expected_revision is not None and state["revision"] != expected_revision:
            own_start = (interrupted and state["revision"] == expected_revision + 2
                         and previous[-2]["type"] == "VerificationStarted"
                         and previous[-2]["payload"]["verification_id"] == verification_id
                         and previous[-1]["command_id"] == previous[-2]["command_id"])
            if not own_start:
                raise LedgerError("REVISION_CONFLICT")
        if not interrupted:
            started = iso(clock())
            start_intent = {**intent, "operation": "verification-start"}
            start_key = "verification-start-" + verification_id
            _append(store, previous, [("VerificationStarted", {"verification_id": verification_id,
                      "plan_hash": digest(plan), "started_at": started}, started)], start_key, start_intent, clock)
            previous, state = _read(store, run_id)
            if fault:
                fault("after_start")
        receipt = {"verification_id": verification_id, "plan_hash": digest(plan), "finished_at": None,
                   "outcome": "OUTCOME_UNKNOWN" if interrupted else "INVALIDATED", "input_base64": None,
                   "input_sha256": None, "result": None, "reason": "INTERRUPTED" if interrupted else None}
        changes = []
        if not interrupted:
            reason, raw = None, None
            if iso(clock()) >= plan["expires_at"]:
                reason = "PLAN_EXPIRED"
            elif digest(state["proposal"]) != plan["proposal_hash"]:
                reason = "PROPOSAL_CHANGED"
            elif digest(engine_identity()) != plan["engine_hash"]:
                reason = "ENGINE_CHANGED"
            else:
                try:
                    raw = _read_input(root, plan["target"]["path"])
                    if hashlib.sha256(raw).hexdigest() != plan["target"]["sha256"]:
                        reason = "TARGET_CHANGED"
                    result = evidence_result(plan, raw, state.get("verifications", {}).get(plan["spec"]["reproduces"])) if reason is None else None
                    if fault:
                        fault("after_check")
                    moment = clock()
                    observation = observe(root, plan["target"]["path"], iso(moment), iso(moment + timedelta(seconds=300)))
                    changes.append(("ObservationRecorded", observation, iso(moment)))
                    if observation["status"] != "OBSERVED":
                        reason = "TARGET_UNAVAILABLE"
                    elif observation["sha256"] != plan["target"]["sha256"]:
                        reason = "TARGET_CHANGED"
                except LedgerError as error:
                    reason = "TARGET_CHANGED" if error.code == "VERIFICATION_TARGET_CHANGED" else "TARGET_UNAVAILABLE"
                    moment = clock()
                    observation = observe(root, plan["target"]["path"], iso(moment), iso(moment + timedelta(seconds=300)))
                    changes.append(("ObservationRecorded", observation, iso(moment)))
            if reason is None:
                for ref in plan["spec"]["oracle"]["source_refs"]:
                    source = state["observations"][ref]
                    moment = clock()
                    oracle = observe(root, source["path"], iso(moment), iso(moment + timedelta(seconds=300)))
                    changes.append(("ObservationRecorded", oracle, iso(moment)))
                    if oracle["status"] != "OBSERVED":
                        reason = "ORACLE_UNAVAILABLE"
                    elif oracle["sha256"] != source["sha256"]:
                        reason = "ORACLE_CHANGED"
            if reason is None and digest(engine_identity()) != plan["engine_hash"]:
                reason = "ENGINE_CHANGED"
            receipt["finished_at"] = iso(clock())
            if reason is None and receipt["finished_at"] >= plan["expires_at"]:
                reason = "PLAN_EXPIRED"
            if reason is None:
                receipt.update(outcome="COMPLETED", input_base64=base64.b64encode(raw).decode("ascii"),
                               input_sha256=hashlib.sha256(raw).hexdigest(), result=result, reason=None)
            else:
                receipt["reason"] = reason
        if receipt["finished_at"] is None:
            receipt["finished_at"] = iso(clock())
        changes.append(("VerificationRecorded", receipt, receipt["finished_at"]))
        return _view(_append(store, previous, changes, key, intent, clock), key)


def list_verifications(root, configuration, run_id, archive_id=None):
    if not valid_id(run_id):
        raise LedgerError("ARGUMENTS")
    with EventStore(root, configuration["project"]["id"]) as store:
        view = get_projection(store, run_id, archive_id)
        return {"schema_version": 1, "ok": True, "command": "verifications", "run_id": run_id,
                "verifications": list(view["state"].get("verifications", {}).values()), "trust": view["state"]["trust"],
                "historical_assessment": True}
