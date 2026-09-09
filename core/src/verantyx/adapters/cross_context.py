"""Execute finite handoff comparisons in .cross; replay is pure Python.

The graph retains original text, alternative interpretations, typed edges and
case choices. Equality is a bounded contract check, not semantic proof.
"""
from copy import deepcopy
from importlib.resources import files
from pathlib import Path
import hashlib
import subprocess
import tempfile

from .cross_response import _configured_binary, _runtime_hash, EXPECTED_IDENTITY
from ..domain.codec import canonical, decode, digest
from ..errors import LedgerError

BACKEND = "cross-context.v1"
PROGRAM_SHA256 = "1a06ed35013b8b0ae37462fb3f89ab70adfd7a6da87608794cffbaf85951fc5f"
SLOTS = {"sources": "+x/面/北", "version": "-x/面/北", "interpretations": "+y/面/北",
         "acknowledgements": "-y/面/北", "checks": "+z/面/北", "priorities": "+x/辺/北東",
         "dependencies": "+y/辺/北東", "exceptions": "+z/辺/北東", "cases": "+x/頂点/北東端"}


def reference(inputs):
    mismatches = [c["id"] for c in inputs["checks"] if c["expected"] != c["actual"]]
    return {"十字": {"中央": len(mismatches), "場所": {slot: deepcopy(inputs[key]) for key, slot in SLOTS.items()}}}


def compare(inputs, binary=None):
    expected = reference(inputs)
    structure = expected
    identity = {"backend": BACKEND, "runtime_sha256": None, "program_sha256": None}
    mode, reason, steps = "HOST_FALLBACK", None, 0
    try:
        raw = files("verantyx").joinpath("policies/context.cross").read_bytes()
        identity["program_sha256"] = hashlib.sha256(raw).hexdigest()
        selected = _configured_binary(binary)
        identity["runtime_sha256"] = _runtime_hash(selected)
        if identity["program_sha256"] != PROGRAM_SHA256 or identity["runtime_sha256"] != EXPECTED_IDENTITY["runtime_sha256"]:
            raise LedgerError("CROSS_CHANGED")
        with tempfile.TemporaryDirectory(prefix="verantyx-context-") as temporary:
            root = Path(temporary)
            (root / "context.cross").write_bytes(raw)
            (root / "input.json").write_text(canonical(inputs), encoding="utf-8")
            result = subprocess.run([str(selected), "run", str(root / "context.cross"), "--input", str(root / "input.json"),
                                     "--memory", "compact", "--steps", "100000", "--max-nodes", "200000"],
                                    capture_output=True, timeout=10)
            if result.returncode or len(result.stdout) > 4 * 1024 * 1024:
                raise LedgerError("CROSS_FAILED")
            output = decode(result.stdout, 4 * 1024 * 1024)
            if output.get("status") != "COMPLETE" or output.get("value") != expected:
                raise LedgerError("CROSS_DISAGREEMENT")
            steps = output["steps"]
            if type(steps) is not int or steps <= 0 or _runtime_hash(selected) != identity["runtime_sha256"]:
                raise LedgerError("CROSS_CHANGED")
            mode = "CROSS_VM"
            structure = output["value"]
    except (OSError, subprocess.SubprocessError, LedgerError) as error:
        reason = error.code if isinstance(error, LedgerError) else "CROSS_FAILED"
    result = {"scope": "FINITE_HANDOFF_CONTRACT_ONLY", "input_sha256": digest(inputs), "mode": mode,
              "fallback_reason": reason, "identity": identity, "steps": steps, "structure": structure,
              "mismatch_ids": [c["id"] for c in inputs["checks"] if c["expected"] != c["actual"]],
              "status": "MATCHED" if structure["十字"]["中央"] == 0 else "REPAIR_REQUIRED",
              "semantic_fidelity": "UNPROVEN", "execution_authorized": False}
    validate_result(result, inputs)
    return result


def validate_result(result, inputs):
    from ..shared_context import require, fields
    fields(result, ("scope", "input_sha256", "mode", "fallback_reason", "identity", "steps", "structure",
                    "mismatch_ids", "status", "semantic_fidelity", "execution_authorized"))
    expected = reference(inputs)
    require(result["scope"] == "FINITE_HANDOFF_CONTRACT_ONLY" and result["input_sha256"] == digest(inputs))
    require(canonical(result["structure"]) == canonical(expected), "SHARED_CONTEXT_STALE")
    require(result["mismatch_ids"] == [c["id"] for c in inputs["checks"] if c["expected"] != c["actual"]])
    require(result["status"] == ("MATCHED" if expected["十字"]["中央"] == 0 else "REPAIR_REQUIRED"))
    require(result["semantic_fidelity"] == "UNPROVEN" and result["execution_authorized"] is False)
    fields(result["identity"], ("backend", "runtime_sha256", "program_sha256"))
    require(result["identity"]["backend"] == BACKEND and type(result["steps"]) is int and result["steps"] >= 0)
    if result["mode"] == "CROSS_VM":
        require(result["fallback_reason"] is None and result["steps"] > 0)
        require(result["identity"]["runtime_sha256"] == EXPECTED_IDENTITY["runtime_sha256"]
                and result["identity"]["program_sha256"] == PROGRAM_SHA256)
    else:
        require(result["mode"] == "HOST_FALLBACK" and result["fallback_reason"] in
                ("CROSS_UNAVAILABLE", "CROSS_CHANGED", "CROSS_FAILED", "CROSS_DISAGREEMENT"))
