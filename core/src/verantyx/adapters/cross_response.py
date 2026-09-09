"""Finite response routing through the existing .cross VM, with pure replay.

Faces hold kernel facts and edges combine constraints. The selected response
route is advisory; it never authorizes an effect or verifies arbitrary prose.
"""
from copy import deepcopy
from importlib.resources import files
from pathlib import Path
import hashlib
import json
import os
import subprocess
import tempfile

from .observations import read_document
from ..domain.codec import canonical, decode, digest
from ..errors import LedgerError

BACKEND = "cross-response.v1"
SCOPE = "FINITE_RESPONSE_ROUTING_ONLY"
INPUT_KEYS = ("conflicted", "refuted", "decision_required", "evidence_required", "authority_required", "can_continue")
ROUTES = ("RESOLVE_CONFLICT", "RETEST", "ASK_DECISION", "GATHER_EVIDENCE", "REQUEST_AUTHORITY", "CONTINUE")
FALLBACK_REASONS = ("CROSS_UNAVAILABLE", "CROSS_CHANGED", "CROSS_FAILED", "CROSS_DISAGREEMENT")
EXPECTED_IDENTITY = {
    "backend": BACKEND,
    "runtime_sha256": "3e53381be3fd51262000deafed7dec8b3ae5aa3875dfa985e5ac37713c10d66d",
    "program_sha256": "3b2a20c870a656ada3f15c7a943dda7a88b4026409413f1ae569d0c9f49160ac",
    "meaning_sha256": "cffbd2be864ca96a719ef0efeb28a0b29cac1bd578b9ac18fefd6862efcea36c",
}
# A trusted local build registers its exact binary after the Cross tests pass.
# The file is installation metadata, never model input or a request option.
_build_pin = Path(__file__).resolve().parents[1] / "cross-build.json"
if _build_pin.is_file():
    _pin = json.loads(_build_pin.read_text())
    if set(_pin) != {"runtime_sha256"} or not isinstance(_pin["runtime_sha256"], str) or len(_pin["runtime_sha256"]) != 64 or any(c not in "0123456789abcdef" for c in _pin["runtime_sha256"]):
        raise RuntimeError("Invalid Cross build identity")
    EXPECTED_IDENTITY["runtime_sha256"] = _pin["runtime_sha256"]
FACE_KEYS = dict(zip(INPUT_KEYS, ("+x/面/北", "-x/面/北", "+y/面/北", "-y/面/北", "+z/面/北", "-z/面/北")))


def route_inputs(state):
    """Extract recorded assessment facts without interpreting proposal prose."""
    if type(state) is not dict or state.get("assessment") is not None and type(state["assessment"]) is not dict:
        raise LedgerError("ARGUMENTS")
    assessment = state.get("assessment") or {}
    for key in ("claims", "actions", "gaps", "judgments"):
        if type(assessment.get(key, [])) is not list or any(type(row) is not dict for row in assessment.get(key, [])):
            raise LedgerError("ARGUMENTS")
    gaps = assessment.get("gaps", [])
    claims = assessment.get("claims", [])
    actions = assessment.get("actions", [])
    judgments = assessment.get("judgments", [])
    conflicted = assessment.get("evidence") == "CONTESTED" or any(
        row.get("epistemic_status") == "CONTESTED" or row.get("classification") == "CONTESTED"
        or row.get("code") in ("VERIFICATION_CONFLICT", "RULE_CONFLICT", "RULE_CONTESTED") for row in [*gaps, *claims])
    refuted = assessment.get("evidence") == "REFUTED" or any(
        row.get("epistemic_status") == "REFUTED" or row.get("classification") == "REFUTED"
        or row.get("code") in ("PROPERTY_REFUTED", "CANDIDATE_TEST_FAILED") for row in [*gaps, *claims])
    decision_gaps = [gap for gap in gaps if gap.get("code") != "AUTHORITY_REQUIRED" and (
        gap.get("classification") in ("UNDECIDED_HUMAN", "UNSCOPED_RULE")
        or gap.get("code") in ("VALUE_DECISION_REQUIRED", "READ_SCOPE_NOT_GRANTED"))]
    decision_required = (assessment.get("strategy") == "ASK_ONE_DECISION" or assessment.get("question") is not None
                         or bool(decision_gaps) or any(row.get("gate") == "NEED_DECISION" for row in actions)
                         or any(row.get("kind") == "VALUE_DECISION" and row.get("status") in
                                ("UNDECIDED_HUMAN", "UNSCOPED_RULE") for row in judgments))
    authority_required = any(row.get("gate") == "NEED_AUTHORITY" for row in actions) or any(
        row.get("code") == "AUTHORITY_REQUIRED" for row in gaps)
    explained = {"VERIFICATION_CONFLICT", "RULE_CONFLICT", "RULE_CONTESTED", "PROPERTY_REFUTED",
                 "CANDIDATE_TEST_FAILED", "AUTHORITY_REQUIRED", "VALUE_DECISION_REQUIRED", "READ_SCOPE_NOT_GRANTED"}
    evidence_required = (not assessment or state.get("proposal") is None or any(
        gap.get("code") not in explained and gap not in decision_gaps
        and gap.get("classification") not in ("CONTESTED", "REFUTED") for gap in gaps))
    flags = {"conflicted": conflicted, "refuted": refuted, "decision_required": decision_required,
             "evidence_required": evidence_required, "authority_required": authority_required}
    return {**flags, "can_continue": bool(assessment) and state.get("proposal") is not None and not any(flags.values())}


def _reference_route(inputs):
    # Independent conventional selector; it does not evaluate .cross syntax.
    for key, route in zip(INPUT_KEYS[:5], ROUTES[:5]):
        if inputs[key]:
            return route
    return "CONTINUE" if inputs["can_continue"] else "GATHER_EVIDENCE"


def _reference_structure(inputs):
    locations = {FACE_KEYS[key]: inputs[key] for key in INPUT_KEYS}
    locations["+x/辺/北東"] = inputs["conflicted"] or inputs["refuted"]
    locations["+y/辺/北東"] = inputs["decision_required"] or inputs["authority_required"]
    return {"十字": {"中央": _reference_route(inputs), "場所": locations}}


def _configured_binary(binary):
    configured = binary if binary is not None else os.environ.get("VERANTYX_CROSS")
    if configured is None:
        project = Path(__file__).resolve().parents[3]
        candidate = project.parent / "cross/build/cross"
        configured = candidate if candidate.is_file() else None
    if configured is None:
        raise LedgerError("CROSS_UNAVAILABLE")
    if not isinstance(configured, (str, os.PathLike)):
        raise LedgerError("ARGUMENTS")
    return Path(configured).expanduser().resolve()


def _programs():
    root = files("verantyx").joinpath("policies")
    return root.joinpath("response.cross").read_bytes(), root.joinpath("response-meaning.cross").read_bytes()


def _runtime_hash(binary):
    try:
        return hashlib.sha256(read_document(binary, 16 * 1024 * 1024)).hexdigest()
    except (OSError, LedgerError):
        raise LedgerError("CROSS_UNAVAILABLE") from None


def _run_vm(binary, program, meaning, inputs):
    """One bounded execution; callers pin resources and check result agreement."""
    with tempfile.TemporaryDirectory(prefix="verantyx-response-cross-") as temporary:
        directory = Path(temporary)
        program_path = directory / "response.cross"
        meaning_path = directory / "response-meaning.cross"
        input_path = directory / "input.json"
        program_path.write_bytes(program)
        meaning_path.write_bytes(meaning)
        input_path.write_text(canonical(inputs), encoding="utf-8")
        try:
            result = subprocess.run([str(binary), "run", str(program_path), "--meaning", str(meaning_path),
                                     "--input", str(input_path), "--memory", "compact", "--steps", "10000",
                                     "--max-nodes", "10000"], capture_output=True, timeout=5)
            if result.returncode != 0 or len(result.stdout) > 65536:
                raise LedgerError("CROSS_FAILED")
            output = decode(result.stdout)
            if type(output) is not dict or output.get("status") != "COMPLETE":
                raise LedgerError("CROSS_FAILED")
            if any(type(output.get(key)) is not int or output[key] <= 0 for key in ("steps", "local_transitions")):
                raise LedgerError("CROSS_FAILED")
            return output
        except (OSError, subprocess.SubprocessError, LedgerError):
            raise LedgerError("CROSS_FAILED") from None


def response_route(state, binary=None):
    """Return an auditable route snapshot; VM absence/failure is explicit."""
    inputs = route_inputs(state)
    expected = _reference_structure(inputs)
    identity = {key: None for key in EXPECTED_IDENTITY}
    identity["backend"] = BACKEND
    mode, reason, vm, structure = "HOST_FALLBACK", None, None, expected
    try:
        try:
            program, meaning = _programs()
        except OSError:
            raise LedgerError("CROSS_UNAVAILABLE") from None
        identity.update(program_sha256=hashlib.sha256(program).hexdigest(), meaning_sha256=hashlib.sha256(meaning).hexdigest())
        selected = _configured_binary(binary)
        identity["runtime_sha256"] = _runtime_hash(selected)
        if identity != EXPECTED_IDENTITY:
            raise LedgerError("CROSS_CHANGED")
        try:
            output = _run_vm(selected, program, meaning, inputs)
        except (OSError, subprocess.SubprocessError):
            raise LedgerError("CROSS_FAILED") from None
        try:
            after_hash = _runtime_hash(selected)
        except LedgerError:
            raise LedgerError("CROSS_CHANGED") from None
        if after_hash != identity["runtime_sha256"]:
            raise LedgerError("CROSS_CHANGED")
        if digest(output.get("value")) != digest(expected):
            raise LedgerError("CROSS_DISAGREEMENT")
        # The VM's computed center and geometry are the successful path's result.
        structure = output["value"]
        mode = "CROSS_VM"
        vm = {"status": "COMPLETE", "output_hash": digest(structure), "steps": output["steps"],
              "local_transitions": output["local_transitions"]}
    except LedgerError as error:
        if error.code not in FALLBACK_REASONS:
            raise
        reason = error.code
    result = {"route": structure["十字"]["中央"], "can_execute": False}
    snapshot = {"schema_version": 1, "scope": SCOPE, "inputs": inputs, "input_hash": digest(inputs),
                "assessment_hash": digest(state.get("assessment")), "result": result, "structure": structure,
                "mode": mode, "fallback_reason": reason, "identity": identity, "engine": digest(identity), "vm": vm}
    return validate_route(snapshot, state)


def validate_route(snapshot, state):
    """Pure replay checks: no VM, current policy files, filesystem, or clock."""
    def require(condition):
        if not condition:
            raise LedgerError("STORE_INTEGRITY")
    def is_hash(value):
        return type(value) is str and len(value) == 64 and set(value) <= set("0123456789abcdef")
    try:
        require(type(snapshot) is dict and set(snapshot) == {
            "schema_version", "scope", "inputs", "input_hash", "assessment_hash", "result", "structure",
            "mode", "fallback_reason", "identity", "engine", "vm"})
        require(type(snapshot["schema_version"]) is int and snapshot["schema_version"] == 1 and snapshot["scope"] == SCOPE)
        inputs = route_inputs(state)
        require(type(snapshot["inputs"]) is dict and set(snapshot["inputs"]) == set(INPUT_KEYS))
        require(all(type(value) is bool for value in snapshot["inputs"].values()) and snapshot["inputs"] == inputs)
        require(snapshot["input_hash"] == digest(inputs) and snapshot["assessment_hash"] == digest(state.get("assessment")))
        require(digest(snapshot["structure"]) == digest(_reference_structure(inputs)))
        require(type(snapshot["result"]) is dict and set(snapshot["result"]) == {"route", "can_execute"})
        require(snapshot["result"]["route"] == _reference_route(inputs) and snapshot["result"]["can_execute"] is False)
        identity = snapshot["identity"]
        require(type(identity) is dict and set(identity) == set(EXPECTED_IDENTITY) and identity["backend"] == BACKEND)
        require(all(identity[key] is None or is_hash(identity[key]) for key in EXPECTED_IDENTITY if key != "backend"))
        require(snapshot["engine"] == digest(identity))
        if snapshot["mode"] == "CROSS_VM":
            require(identity == EXPECTED_IDENTITY and snapshot["fallback_reason"] is None)
            vm = snapshot["vm"]
            require(type(vm) is dict and set(vm) == {"status", "output_hash", "steps", "local_transitions"})
            require(vm["status"] == "COMPLETE" and vm["output_hash"] == digest(snapshot["structure"]))
            require(all(type(vm[key]) is int and vm[key] > 0 for key in ("steps", "local_transitions")))
        else:
            require(snapshot["mode"] == "HOST_FALLBACK" and snapshot["fallback_reason"] in FALLBACK_REASONS and snapshot["vm"] is None)
            if snapshot["fallback_reason"] in ("CROSS_FAILED", "CROSS_DISAGREEMENT"):
                require(identity == EXPECTED_IDENTITY)
    except (KeyError, TypeError, ValueError, AttributeError, LedgerError):
        raise LedgerError("STORE_INTEGRITY") from None
    return deepcopy(snapshot)
