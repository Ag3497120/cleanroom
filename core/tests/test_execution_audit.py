"""Regressions found by inspecting the actual authorization and receipt paths."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import unittest

from test_constitution import Fixture, proposal, PRECEDENT
from verantyx.domain.events import make_event
from verantyx.effects import authorize, execute
from verantyx.kernel.reducer import replay
from verantyx.storage.sqlite import EventStore
from verantyx.errors import LedgerError


@unittest.skipUnless(PRECEDENT, "set VERANTYX_PRECEDENT for actual integration")
class ExecutionAuditTests(Fixture):
    def prepared(self, content=None, ttl=300):
        self.init_git()
        self.promote()
        document = proposal("candidate", action=True)
        if content is not None:
            document["actions"][0]["arguments"]["files"]["calc.py"] = content
        self.run_task("candidate", document)
        self.lease = authorize(self.root, self.cfg, "candidate", "writer", PRECEDENT,
                               "permit", clock=self.clock, ttl=ttl)["lease_id"]

    def execute(self, **kwargs):
        return execute(self.root, self.cfg, "candidate", self.lease, PRECEDENT,
                       "execute", clock=self.clock, **kwargs)

    def test_expiry_after_start_prevents_worktree_creation(self):
        self.prepared(ttl=1)
        def delay(stage):
            if stage == "after_start":
                self.time += timedelta(seconds=2)
        result = self.execute(fault=delay)
        self.assertEqual(result["execution"]["status"], "OUTCOME_UNKNOWN")
        self.assertEqual(result["execution"]["receipt"]["reason"], "LEASE_EXPIRED")
        self.assertFalse((self.root / ".verantyx/worktrees" / self.lease).exists())
        self.assertTrue(self.execute()["duplicate"])

    def test_receipt_cannot_substitute_a_different_change_or_destination(self):
        self.prepared()
        self.execute()
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            events = store.events("candidate")
        mutations = {
            "different_worktree": ("ExecutionReceipt", lambda p: p.update(worktree="/tmp/other")),
            "different_files": ("ExecutionReceipt", lambda p: p["applied"].update({"calc.py": "0" * 64})),
            "changed_authorized_plan": ("EffectAuthorized", lambda p: p["lease"]["plan"]["files"].update({"calc.py": "malicious = True\n"})),
            "expired_authorization": ("EffectAuthorized", lambda p: p["lease"].update(expires_at="2020-01-01T00:00:00.000000Z")),
            "different_rules": ("EffectAuthorized", lambda p: p["lease"].update(rule_context_hash="0" * 64)),
        }
        for label, (kind, mutate) in mutations.items():
            with self.subTest(label=label):
                changed = []
                for event in events:
                    payload = deepcopy(event["payload"])
                    if event["type"] == kind:
                        mutate(payload)
                    changed.append(make_event(event["project_id"], event["stream_id"], event["revision"],
                                              event["command_id"], event["recorded_at"], event["type"], payload,
                                              event["event_id"], changed[-1] if changed else None))
                with self.assertRaises(LedgerError):
                    replay(changed)

    def test_clean_exit_before_any_tests_is_not_verification(self):
        self.prepared("import os\nos._exit(0)\n")
        result = self.execute()
        verification = result["execution"]["receipt"].get("verification")
        self.assertFalse(verification and verification["result"]["passed"])

    def test_failing_suite_remains_an_execution_gap(self):
        self.prepared("def add(a, b):\n    return 5\n")
        result = self.execute()
        self.assertFalse(result["execution"]["receipt"]["verification"]["result"]["passed"])
        codes = {gap["code"] for gap in result["state"]["assessment"]["gaps"]}
        self.assertIn("CANDIDATE_TEST_FAILED", codes)
