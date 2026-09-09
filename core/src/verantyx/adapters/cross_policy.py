"""The existing .cross VM evaluates exact scope matches; it grants no authority."""
from importlib.resources import files
from pathlib import Path
import hashlib
import json
import os
import subprocess
import tempfile

from .observations import read_document
from ..domain.codec import decode, digest
from ..errors import LedgerError

SCOPE_KEYS = ("project_id", "component", "workload", "risk", "decision_type")


class CrossPolicyBackend:
    def __init__(self, binary=None, program=None):
        configured = binary or os.environ.get("VERANTYX_CROSS")
        if configured is None:
            # Development checkout convenience; installed packages use VERANTYX_CROSS.
            project = Path(__file__).resolve().parents[3]
            candidate = project.parent / "cross/build/cross"
            configured = candidate if candidate.is_file() else None
        if configured is None:
            raise LedgerError("CROSS_UNAVAILABLE")
        self.binary = Path(configured).expanduser().resolve()
        self.program = Path(program).read_bytes() if program else files("verantyx").joinpath("policies", "scope.cross").read_bytes()
        self.meaning = files("verantyx").joinpath("policies", "structure.cross").read_bytes()
        try:
            runtime = read_document(self.binary, 16 * 1024 * 1024)
        except (OSError, LedgerError):
            raise LedgerError("CROSS_UNAVAILABLE") from None
        self.identity = {"backend": "cross-scope.v1", "runtime_sha256": hashlib.sha256(runtime).hexdigest(),
                         "program_sha256": hashlib.sha256(self.program).hexdigest(),
                         "meaning_sha256": hashlib.sha256(self.meaning).hexdigest()}
        self.fingerprint = digest(self.identity)

    def match(self, scope, target):
        if hashlib.sha256(read_document(self.binary, 16 * 1024 * 1024)).hexdigest() != self.identity["runtime_sha256"]:
            raise LedgerError("CROSS_CHANGED")
        if set(scope) != set(SCOPE_KEYS) or set(target) != set(SCOPE_KEYS):
            raise LedgerError("RULE_INVALID")
        if any(type(v) is not str or not v for v in [*scope.values(), *target.values()]):
            raise LedgerError("RULE_INVALID")
        value = {**{"rule_" + key: scope[key] for key in SCOPE_KEYS},
                 **{"target_" + key: target[key] for key in SCOPE_KEYS}}
        with tempfile.TemporaryDirectory(prefix="verantyx-cross-") as directory:
            directory = Path(directory)
            (directory / "scope.cross").write_bytes(self.program)
            (directory / "meaning.cross").write_bytes(self.meaning)
            (directory / "input.json").write_text(json.dumps(value))
            try:
                result = subprocess.run(
                    [str(self.binary), "run", str(directory / "scope.cross"), "--meaning", str(directory / "meaning.cross"),
                     "--input", str(directory / "input.json"), "--memory", "compact", "--steps", "10000"],
                    capture_output=True, timeout=5,
                )
                if result.returncode != 0 or len(result.stdout) > 1024 * 1024:
                    raise LedgerError("CROSS_FAILED")
                output = decode(result.stdout)
                if output.get("status") != "COMPLETE" or type(output.get("value")) is not bool:
                    raise LedgerError("CROSS_FAILED")
            except (OSError, subprocess.TimeoutExpired):
                raise LedgerError("CROSS_FAILED") from None
        # A second, conventional evaluator checks the VM boundary contract.
        expected = all(scope[key] == target[key] for key in SCOPE_KEYS)
        if output["value"] != expected:
            raise LedgerError("CROSS_DISAGREEMENT")
        return {"match": output["value"], "input_hash": digest(value), "engine": self.fingerprint}

    def shadow_check(self, scope):
        cases = [(dict(scope), True, "exact")]
        for key in SCOPE_KEYS:
            target = dict(scope)
            target[key] = {"project_id": "00000000-0000-0000-0000-000000000000",
                           "risk": "HIGH" if scope[key] != "HIGH" else "LOW"}.get(key, "outside-" + digest({"key": key, "scope": scope})[:24])
            if target[key] == scope[key]:
                target[key] = "11111111-1111-1111-1111-111111111111"
            cases.append((target, False, key))
        receipts = []
        for target, expected, label in cases:
            receipt = self.match(scope, target)
            if receipt["match"] != expected:
                raise LedgerError("CROSS_DISAGREEMENT")
            receipts.append({"case": label, "target": target, "expected": expected, **receipt})
        return {"methods": ["TEST", "NEGATIVE_CONTROL"], "closure": "BOUNDED", "scope": "EXACT_MATCH_MECHANISM_ONLY",
                "independence": {"generator": {"same_model": None, "same_provider": None},
                                 "implementation": {"same_code_path": False, "shared_dependency": True},
                                 "oracle": {"same_expected_value_source": True},
                                 "data": {"dataset_overlap": "complete"}, "environment": {"same_machine": True}},
                "origin": {"kind": "I3", "mechanism": "cross-vm-and-host-reference",
                           "independent_design": False, "note": "Mechanism agreement does not prove the value decision."},
                "engine": self.fingerprint, "identity": self.identity, "cases": receipts}

    def match_policy(self, policy, target):
        from ..domain.rule_extensions import validate_policy, within_scope, scopes
        validate_policy(policy)
        inside = within_scope(policy, target)
        # The finite selector is a host operation. The selected exact five-axis
        # comparison still runs in the existing .cross VM, with its host check.
        cell = dict(target) if inside else scopes(policy)[0]
        witness = self.match(cell, target)
        if witness["match"] != inside:
            raise LedgerError("CROSS_DISAGREEMENT")
        exceptions = [item["id"] for item in policy["exceptions"] if item["scope"] == target]
        return {"schema": "finite-scope-match.v1", "policy_hash": digest(policy), "target": dict(target),
                "within_scope": inside, "exceptions": exceptions, "match": inside and not exceptions,
                "input_hash": digest({"policy": policy, "target": target}), "engine": self.fingerprint,
                "witness": {"scope": cell, "receipt": witness}}

    def shadow_policy_check(self, policy):
        from ..domain.rule_extensions import validate_policy, shadow_cases
        validate_policy(policy)
        receipts = []
        for target, expected, label in shadow_cases(policy):
            receipt = self.match_policy(policy, target)
            if receipt["match"] is not expected:
                raise LedgerError("CROSS_DISAGREEMENT")
            receipts.append({"case": label, "target": target, "expected": expected, "receipt": receipt})
        return {"methods": ["TEST", "NEGATIVE_CONTROL"], "closure": "BOUNDED", "scope": "FINITE_SCOPE_MECHANISM_ONLY",
                "policy_hash": digest(policy), "engine": self.fingerprint, "identity": self.identity, "cases": receipts,
                "independence": {"generator": {"same_model": None, "same_provider": None},
                                 "implementation": {"same_code_path": False, "shared_dependency": True},
                                 "oracle": {"same_expected_value_source": True},
                                 "data": {"dataset_overlap": "complete"}, "environment": {"same_machine": True}},
                "origin": {"kind": "I3", "mechanism": "finite-host-selector-and-cross-vm-exact-comparison",
                           "independent_design": False, "note": "Finite case coverage checks the mechanism, not the value decision."}}
