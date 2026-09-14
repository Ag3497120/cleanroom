"""Acceptance boundaries for the connected recovery path, not another agent loop."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from verantyx.domain.codec import digest
from verantyx.errors import LedgerError
from verantyx.recovery_bundle import _write_files, project_bundle
from verantyx.recovery_replay import replay


class RecoveryAcceptance(unittest.TestCase):
    def fixture(self):
        spec = {
            "claim_id": "claim-1", "target_path": "result.json",
            "property": "retry_limit is integer 3", "method": "TEST",
            "checks": [{"id": "three", "kind": "json.equals", "pointer": "/retry_limit", "expected": 3}],
            "negative_controls": [], "reproduces": None,
            "oracle": {"description": "Explicit fixed expectation", "source_refs": []},
            "provenance": {name: "synthetic acceptance" for name in
                           ("model", "provider", "implementation", "dependencies", "oracle", "data", "environment")},
        }
        item = {"id": "method-1", "family": "VERIFICATION", "portable_execution": True,
                "spec": spec, "contract_hash": digest(spec)}
        payload = {"format": "verantyx.recovery-bundle.v1", "methods": [item]}
        return {"bundle_id": digest(payload), "payload": payload}

    def test_same_contract_accepts_and_refutes_without_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pass.json").write_text('{"retry_limit":3}')
            (root / "fail.json").write_text('{"retry_limit":4}')
            bundle = self.fixture()
            before = deepcopy(bundle)
            good = replay(bundle, "method-1", root, "pass.json")
            bad = replay(bundle, "method-1", root, "fail.json")
            self.assertEqual(good["result"]["closure"], "BOUNDED")
            self.assertEqual(bad["result"]["closure"], "REFUTED")
            self.assertEqual(bundle, before)
            self.assertFalse(good["project_database_used"])
            self.assertEqual(good["model_calls"], 0)
            self.assertFalse((root / ".verantyx").exists())

    def test_hash_change_is_rejected(self):
        bundle = self.fixture()
        bundle["payload"]["methods"][0]["spec"]["checks"][0]["expected"] = 4
        with self.assertRaises(LedgerError):
            replay(bundle, "method-1", Path("."))

    def test_rebinding_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "result.json").write_text('{"retry_limit":3}')
            (root / "link.json").symlink_to(root / "result.json")
            for target in ("../result.json", str(root / "result.json"), "link.json"):
                with self.subTest(target=target), self.assertRaises((LedgerError, OSError)):
                    replay(self.fixture(), "method-1", root, target)

    def test_export_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_files(root, ("recovery",), {"manifest.json": b"original"})
            _write_files(root, ("recovery",), {"manifest.json": b"original"})
            with self.assertRaises(LedgerError):
                _write_files(root, ("recovery",), {"manifest.json": b"changed"})
            self.assertEqual((root / "recovery/manifest.json").read_bytes(), b"original")

    def test_export_does_not_follow_symlink(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as other:
            root = Path(directory)
            (root / "recovery").symlink_to(other, target_is_directory=True)
            with self.assertRaises(OSError):
                _write_files(root, ("recovery",), {"manifest.json": b"blocked"})
            self.assertFalse((Path(other) / "manifest.json").exists())

    def test_suggested_delegation_is_not_human_choice(self):
        state = {"run_id": "run-1", "project_id": "project-1",
                 "revision": 1, "request_ref": "request-1"}
        empty = {name: [] for name in ("verification_methods", "execution_methods",
                                      "failure_cases", "reuse_candidates")}
        skills = [
            {"id": "a", "ownership_target": "DELEGATE", "target_is_suggestion": True},
            {"id": "b", "ownership_target": "DELEGATE", "target_is_suggestion": False},
        ]
        with patch("verantyx.assets.project_assets", return_value=empty), \
             patch("verantyx.learning.project_learning", return_value=skills), \
             patch("verantyx.skill_report.summarize_state", return_value={}):
            data = project_bundle(state, {"revision": 0, "policies": []})["payload"]
        self.assertEqual([i["id"] for i in data["dictionary"]["delegate"]], ["b"])
        self.assertEqual([i["id"] for i in data["dictionary"]["learn"]], ["a"])
        self.assertEqual(data["remaining"], ["NO_PORTABLE_EXECUTABLE_CONTRACT"])


if __name__ == "__main__":
    unittest.main()
