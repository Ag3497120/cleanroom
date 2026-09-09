"""Real isolated processes, hidden expectations, pure replay and adversarial data."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
import hashlib
import json
import os
import tempfile
import unittest

from verantyx import config
from verantyx.application import record_run
from verantyx.domain.codec import digest
from verantyx.domain.verification import AXES
from verantyx.errors import LedgerError
from verantyx.kernel.reducer import replay, projection
from verantyx.oracles import plan_oracle, run_oracle, list_oracles
from verantyx.storage.sqlite import EventStore, parse_archive


class OracleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.cfg = config.defaults(self.root, "ja")
        config.save(self.root, self.cfg, None)
        self.time = datetime(2026, 9, 6, tzinfo=timezone.utc)
        self.clock = lambda: self.time
        self.precedent = os.environ["VERANTYX_PRECEDENT"]
        self.candidate = self.root / "candidate.py"
        self.candidate.write_text("def answer(value):\n    return value * 2\n")
        initial = record_run(self.root, self.cfg, request="oracle fixture", run_id="oracle", observe_paths=["candidate.py"], clock=self.clock)
        proposal = {"schema_version": 1, "task_id": "oracle", "context_revision": initial["state"]["revision"], "response_locale": "ja",
                    "summary": "fixture", "claims": [{"id": "claim", "statement": "arbitrary prose is not certified", "source_refs": [initial["state"]["latest_observations"]["candidate.py"]]}],
                    "actions": [], "unknowns": []}
        (self.root / "proposal.json").write_text(json.dumps(proposal))
        record_run(self.root, self.cfg, run_id="oracle", proposal_path=self.root / "proposal.json", resume=True, clock=self.clock)
        self.spec = {"claim_id": "claim", "target_path": "candidate.py", "function": "answer", "property": "fixed inputs produce doubled integers",
                     "cases": [{"id": "positive", "input": 21, "expected": 42}, {"id": "zero", "input": 0, "expected": 0}],
                     "negative_controls": [{"id": "wrong", "case_id": "positive", "counterexample": 41}],
                     "oracle": {"description": "Synthetic arithmetic contract", "source_refs": []},
                     "provenance": {axis: "" for axis in AXES}, "timeout": 2, "max_output": 4096}

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, **kwargs):
        return plan_oracle(self.root, self.cfg, "oracle", self.spec, "plan", precedent=self.precedent, clock=self.clock, **kwargs)

    def run_oracle(self, identifier, **kwargs):
        return run_oracle(self.root, self.cfg, "oracle", identifier, "run", precedent=self.precedent, clock=self.clock, **kwargs)

    def change(self, source):
        self.candidate.write_text(source)
        record_run(self.root, self.cfg, run_id="oracle", resume=True, clock=self.clock)

    def events(self):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            return store.events("oracle")

    def test_actual_process_success_is_finite_evidence_and_no_adoption_permission(self):
        plan = self.plan()
        self.assertEqual(plan["oracle"]["status"], "PLANNED")
        result = self.run_oracle(plan["oracle_id"])
        evidence = result["oracle"]["receipt"]["result"]
        self.assertEqual(evidence["closure"], "BOUNDED")
        self.assertEqual(evidence["prose_entailment"], "NOT_ASSESSED")
        self.assertFalse(evidence["adoption_authorized"])
        self.assertEqual(result["state"]["assessment"]["claims"][0]["verification"], "UNVERIFIED")
        self.assertFalse(result["state"]["can_execute_effects"])

    def test_wrong_output_is_compared_in_parent_and_true_is_not_integer(self):
        self.change("def answer(value):\n    return True\n")
        self.spec["cases"] = [{"id": "positive", "input": 1, "expected": 1}]
        evidence = self.run_oracle(self.plan()["oracle_id"])["oracle"]["receipt"]["result"]
        self.assertEqual(evidence["closure"], "REFUTED")
        self.assertFalse(evidence["checks"][0]["passed"])

    def test_forged_unittest_report_and_early_normal_exit_are_unknown(self):
        self.change("import os\nprint('Ran 100 tests in 0.01s\\n\\nOK',flush=True)\nos._exit(0)\n")
        result = self.run_oracle(self.plan()["oracle_id"])["oracle"]["receipt"]["result"]
        self.assertEqual(result["closure"], "UNKNOWN")
        self.assertTrue(all(c["reason"] == "ORACLE_PROTOCOL" for c in result["checks"]))

    def test_os_exit_without_output_is_not_a_completed_check(self):
        self.change("import os\nos._exit(0)\n")
        self.assertEqual(self.run_oracle(self.plan()["oracle_id"])["oracle"]["receipt"]["result"]["closure"], "UNKNOWN")

    def test_timeout_and_output_overflow_are_unknown(self):
        self.change("def answer(value):\n    while True: pass\n")
        self.spec["timeout"] = 0.1
        result = self.run_oracle(self.plan()["oracle_id"])["oracle"]["receipt"]["result"]
        self.assertEqual(result["closure"], "UNKNOWN")
        self.assertTrue(all(c["reason"] == "BRIDGE_TIMEOUT" for c in result["checks"]))

    def test_output_overflow_including_stderr_cannot_look_successful(self):
        self.change("import sys\ndef answer(value):\n    sys.stderr.write('X'*5000)\n    return value*2\n")
        result = self.run_oracle(self.plan()["oracle_id"])["oracle"]["receipt"]["result"]
        self.assertEqual(result["closure"], "UNKNOWN")
        self.assertTrue(all(c["reason"] == "BRIDGE_OUTPUT_LIMIT" for c in result["checks"]))

    def test_candidate_cannot_read_ledger_expected_spec_or_write_project(self):
        secret = self.root / "secret.json"
        secret.write_text(json.dumps(self.spec))
        destination = self.root / "changed.txt"
        self.change("import os\ndef answer(value):\n    for path in " + repr([str(secret), str(self.root / '.verantyx/state.db')]) + ":\n        try:\n            open(path).read()\n            return 'LEAK'\n        except PermissionError: pass\n    try:\n        open(" + repr(str(destination)) + ",'w').write('bad')\n        return 'WRITE'\n    except PermissionError: pass\n    return value*2\n")
        result = self.run_oracle(self.plan()["oracle_id"])
        self.assertEqual(result["oracle"]["receipt"]["result"]["closure"], "BOUNDED")
        self.assertFalse(destination.exists())

    def test_target_and_engine_change_prevent_launch(self):
        identifier = self.plan()["oracle_id"]
        self.candidate.write_text("def answer(value): return 0")
        with mock.patch("verantyx.oracles.observe_candidate", side_effect=AssertionError("launched stale target")):
            self.assertEqual(self.run_oracle(identifier)["oracle"]["receipt"]["reason"], "TARGET_CHANGED")

    def test_expiry_after_start_and_after_process_invalidates_evidence(self):
        identifier = self.plan(ttl=1)["oracle_id"]
        def expire(stage):
            if stage == "after_check": self.time += timedelta(seconds=1)
        result = self.run_oracle(identifier, fault=expire)
        self.assertEqual(result["oracle"]["receipt"]["reason"], "PLAN_EXPIRED")

    def test_interrupted_run_is_never_redispatched(self):
        identifier = self.plan()["oracle_id"]
        def interrupt(stage):
            if stage == "after_start": raise RuntimeError("fixture interruption")
        with self.assertRaises(RuntimeError): self.run_oracle(identifier, fault=interrupt)
        with mock.patch("verantyx.oracles.observe_candidate", side_effect=AssertionError("reexecuted")):
            result = self.run_oracle(identifier)
            again = self.run_oracle(identifier)
        self.assertEqual(result["oracle"]["status"], "OUTCOME_UNKNOWN")
        self.assertTrue(again["duplicate"])
        self.assertEqual(result["projection_hash"], again["projection_hash"])

    def test_replay_archive_and_result_tampering_do_not_run_candidates(self):
        result = self.run_oracle(self.plan()["oracle_id"])
        events = self.events()
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            raw = store.export().encode()
        self.candidate.unlink()
        with mock.patch("verantyx.oracles.observe_candidate", side_effect=AssertionError("replay effect")), mock.patch("verantyx.oracles.engine_identity", side_effect=AssertionError("replay I/O")):
            self.assertEqual(projection(replay(events))["projection_hash"], result["projection_hash"])
            parse_archive(raw)
        index = next(i for i,e in enumerate(events) if e["type"] == "OracleRecorded")
        for key, value in (("closure", "PROVED"), ("adoption_authorized", True), ("independence", "INDEPENDENT")):
            forged = deepcopy(events[index])
            forged["payload"]["result"][key] = value
            forged["event_hash"] = digest({k:v for k,v in forged.items() if k != "event_hash"})
            with self.assertRaises(LedgerError): replay([*events[:index], forged])

    def test_bad_negative_control_is_contested_and_declared_independence_is_not_granted(self):
        self.spec["negative_controls"][0]["counterexample"] = 42
        self.spec["provenance"] = {axis: "independent" for axis in AXES}
        result = self.run_oracle(self.plan()["oracle_id"])
        self.assertEqual(result["oracle"]["receipt"]["result"]["closure"], "CONTESTED")
        self.assertEqual(result["oracle"]["plan"]["origins"]["independence"], "NOT_ESTABLISHED")

    def test_changed_backend_is_checked_before_its_top_level_can_execute(self):
        backend = self.root / "synthetic-backend" / "precedent"
        backend.mkdir(parents=True)
        source = backend / "execution.py"
        source.write_text("SYNTHETIC_BACKEND=True\n")
        self.precedent = str(backend.parent)
        identifier = self.plan()["oracle_id"]
        marker = self.root / "must-not-execute.txt"
        source.write_text("from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('untrusted code ran')\n")
        result = self.run_oracle(identifier)
        self.assertFalse(marker.exists())
        self.assertEqual(result["oracle"]["receipt"]["reason"], "ENGINE_CHANGED")

    def test_post_check_backend_change_is_rejected_before_import(self):
        backend = self.root / "synthetic-backend" / "precedent"
        backend.mkdir(parents=True)
        source = backend / "execution.py"
        source.write_text("SYNTHETIC_BACKEND=True\n")
        self.precedent = str(backend.parent)
        identifier = self.plan()["oracle_id"]
        marker = self.root / "must-not-execute.txt"
        def change(stage):
            if stage == "after_check":
                source.write_text("from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('untrusted code ran')\n")
        result = self.run_oracle(identifier, fault=change)
        self.assertFalse(marker.exists())
        self.assertEqual(result["oracle"]["receipt"]["reason"], "ENGINE_CHANGED")
