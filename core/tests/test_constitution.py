"""Behavioral product gates, executed against temporary projects only."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid

from verantyx import config
from verantyx.application import record_run
from verantyx.adapters.cross_policy import CrossPolicyBackend
from verantyx.domain.codec import digest
from verantyx.domain.events import make_event
from verantyx.effects import authorize, execute
from verantyx.errors import LedgerError
from verantyx.governance import control, precedents
from verantyx.kernel.reducer import projection, replay
from verantyx.kernel.rules import catalog
from verantyx.storage.sqlite import EventStore, parse_archive

PRECEDENT = os.environ.get("VERANTYX_PRECEDENT")
SCOPE = {"component": "writer", "workload": "parallel", "risk": "HIGH"}


def proposal(task, revision=0, kind="VALUE_DECISION", decision_type="parallel_writers", action=False):
    result = {"schema_version": 1, "task_id": task, "context_revision": revision, "response_locale": "ja",
              "summary": "記録済みの提案", "claims": [], "actions": [], "unknowns": [],
              "decision_points": [{"id": "separation", "kind": kind, "decision_type": decision_type,
                                   "question": "作業場所を分離しますか？", "options": [
                                       {"id": "isolate", "label": "個別のworktree"}, {"id": "shared", "label": "共有の作業場所"}]}]}
    if action:
        result["actions"] = [{"id": "writer", "tool_id": "writer.apply", "arguments": {
            "point_id": "separation", "destination": "shared", "files": {"calc.py": "def add(a, b):\n    return a + b\n"},
            "tests": ["test_calc.py"]}, "reason": "二つ目のwriterで修正する", "source_refs": []}]
    return result


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.cfg = config.defaults(self.root, "ja")
        config.save(self.root, self.cfg, None)
        self.time = datetime(2026, 9, 6, tzinfo=timezone.utc)
        self.clock = lambda: self.time
        self.backend = CrossPolicyBackend()

    def tearDown(self):
        self.tmp.cleanup()

    def run_task(self, task, document=None, context=None, **kwargs):
        document = document or proposal(task)
        path = self.root.parent / ("proposal-" + uuid.uuid4().hex + ".json")
        try:
            path.write_text(json.dumps(document))
            return record_run(self.root, self.cfg, request="並列作業", run_id=task, proposal_path=path,
                              context=context or SCOPE, clock=self.clock, backend=self.backend, **kwargs)
        finally:
            path.unlink()

    def command(self, operation, target, **kwargs):
        with EventStore(self.root, self.cfg["project"]["id"], create=True) as store:
            return control(store, self.cfg, operation, target, clock=self.clock, backend=self.backend, **kwargs)

    def promote(self, task="first"):
        first = self.run_task(task)
        self.assertEqual(first["state"]["assessment"]["strategy"], "ASK_ONE_DECISION")
        decision = self.command("decide", task, point_id="separation", choice="isolate", reason="未完了の変更を失わない", key="decision-" + task)
        case_id = decision["precedent_id"]
        duplicate = self.command("decide", task, point_id="separation", choice="isolate", reason="未完了の変更を失わない", key="decision-" + task)
        self.assertEqual(duplicate["precedent_id"], case_id)
        with self.assertRaises(LedgerError):
            self.command("rule-draft", case_id)
        self.command("precedent-accept", case_id)
        draft = self.command("rule-draft", case_id)
        rule_id = draft["rule_id"]
        with self.assertRaises(LedgerError):
            self.command("rule-activate", rule_id)
        self.command("rule-shadow", rule_id)
        with self.assertRaises(LedgerError):
            self.command("rule-activate", rule_id)
        self.command("rule-confirm", rule_id)
        active = self.command("rule-activate", rule_id)
        return rule_id, active

    def init_git(self):
        def git(*args):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)
        git("init", "-q")
        (self.root / "calc.py").write_text("def add(a, b):\n    return 0\n")
        (self.root / "test_calc.py").write_text("import unittest\nfrom calc import add\nclass Check(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n        self.assertEqual(add(-3, 2), -1)\n")
        git("add", "calc.py", "test_calc.py")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@invalid", "-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture")
        # This unpublished work must survive every execution.
        (self.root / "calc.py").write_text("# first writer's uncommitted work\ndef add(a, b):\n    return 0\n")


class ConstitutionTests(Fixture):
    def test_G1_G3_second_task_reuses_model_independent_rule(self):
        rule_id, active = self.promote()
        second_proposal = proposal("second")
        second_proposal["summary"] = "別の提案生成器の出力を同じ公開契約で読み込む"
        second = self.run_task("second", second_proposal)
        self.assertIsNone(second["state"]["assessment"]["question"])
        judgment = second["state"]["assessment"]["judgments"][0]
        self.assertEqual((judgment["status"], judgment["choice"]), ("PRECEDENT_MATCHED", "isolate"))
        self.assertTrue(judgment["rule_refs"])
        self.assertEqual(len(active["state"]["deltas"]["human_delta"]), 1)
        self.assertEqual(active["state"]["deltas"]["human_delta"][0]["mastery_evidence"], "NONE")

    def test_G2_no_scope_widening(self):
        self.promote()
        for key in SCOPE:
            context = {**SCOPE, key: "LOW" if key == "risk" else "different"}
            view = self.run_task("other-" + key, context=context)
            self.assertEqual(view["state"]["assessment"]["judgments"][0]["reason"], "SCOPE_MISMATCH")
            self.assertIsNotNone(view["state"]["assessment"]["question"])
        view = self.run_task("different-decision", proposal("different-decision", decision_type="parser_memory"))
        self.assertNotEqual(view["state"]["assessment"]["judgments"][0]["status"], "PRECEDENT_MATCHED")

    def test_G4_value_does_not_verify_empirical_claim(self):
        self.promote()
        view = self.run_task("claim", proposal("claim", kind="EMPIRICAL_CLAIM"))
        self.assertEqual(view["state"]["assessment"]["evidence"], "UNKNOWN")
        with self.assertRaises(LedgerError) as error:
            self.command("decide", "claim", point_id="separation", choice="isolate", reason="合意")
        self.assertEqual(error.exception.code, "DECISION_KIND")

    def test_G5_proposer_cannot_inject_authority_or_mastery(self):
        for key, value in (("approved", True), ("actor_kind", "local_cli"), ("RuleActivated", {}), ("mastery", "TRANSFERRED")):
            document = proposal("injection")
            document[key] = value
            with self.assertRaises(LedgerError) as error:
                self.run_task("injection", document)
            self.assertEqual(error.exception.code, "PROPOSAL_INVALID")
        self.assertFalse((self.root / ".verantyx/state.db").exists())

    def test_G6_deltas_are_distinct_and_learning_optional(self):
        _, active = self.promote()
        delta = active["state"]["deltas"]
        self.assertEqual(set(delta), {"project_delta", "system_delta", "human_delta"})
        self.assertEqual(delta["project_delta"]["canonical_changes"], [])
        item = delta["human_delta"][0]
        self.assertEqual(item["concept"], "branch分離とworktree分離の違い")
        self.assertEqual(item["system_capture"], ["RULE"])
        self.cfg["learning"]["mode"] = "off"
        view = self.run_task("off")
        self.assertEqual(view["state"]["deltas"]["human_delta"], [])
        self.assertIsNone(view["state"]["assessment"]["question"])

    def test_G7_contestation_and_amendment_preserve_history(self):
        rule, _ = self.promote()
        self.command("rule-contest", rule, reason="境界で反例が報告された")
        blocked = self.run_task("blocked")
        self.assertEqual(blocked["state"]["assessment"]["judgments"][0]["reason"], "RULE_CONTESTED")
        case = self.command("rule-amend", rule, choice="shared", reason="狭い範囲の選択を修正")["precedent_id"]
        self.command("precedent-accept", case)
        revised = self.command("rule-draft", case)["rule_id"]
        self.command("rule-confirm", revised)
        self.command("rule-shadow", revised)
        self.command("rule-activate", revised)
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            rules = catalog(store.events())
        self.assertEqual(rules[rule]["validity"], "SUPERSEDED")
        self.assertTrue(rules[rule]["counterexamples"])
        self.assertEqual(rules[revised]["choice"], "shared")
        self.assertEqual(rules[revised]["supersedes"], rule)

    def test_K1_pure_replay_freezes_external_dependencies(self):
        self.promote()
        self.run_task("second")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            events = store.events("second")
        expected = projection(replay(events))
        with mock.patch("builtins.open", side_effect=AssertionError("I/O")), \
             mock.patch("pathlib.Path.open", side_effect=AssertionError("I/O")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("uuid.uuid4", side_effect=AssertionError("random")), \
             mock.patch("time.time", side_effect=AssertionError("clock")), \
             mock.patch("socket.socket", side_effect=AssertionError("network")):
            self.assertEqual(projection(replay(events)), expected)

    def test_cross_negative_control_rejects_mutated_scope_program(self):
        original = self.backend.program.decode()
        # A deliberately wrong program using a constant truth must not pass the host/VM contract.
        mutant = self.root / "constant.cross"
        mutant.write_text(original.replace('「規則_risk」と「対象_risk」が等しいか', '「規則_risk」と「規則_risk」が等しいか'))
        try:
            bad = CrossPolicyBackend(program=mutant)
            with self.assertRaises(LedgerError) as error:
                bad.shadow_check({"project_id": self.cfg["project"]["id"], **SCOPE, "decision_type": "parallel_writers"})
            self.assertEqual(error.exception.code, "CROSS_DISAGREEMENT")
        finally:
            mutant.unlink()

    @unittest.skipUnless(PRECEDENT, "set VERANTYX_PRECEDENT for the actual existing executor")
    def test_vertical_slice_actual_precedent_writer_and_negative_control(self):
        self.init_git()
        canonical = (self.root / "calc.py").read_bytes()
        self.promote()
        second = self.run_task("second", proposal("second", action=True))
        self.assertIsNone(second["state"]["assessment"]["question"])
        allowed = authorize(self.root, self.cfg, "second", "writer", PRECEDENT, "lease", clock=self.clock)
        result = execute(self.root, self.cfg, "second", allowed["lease_id"], PRECEDENT, "execute", clock=self.clock)
        receipt = result["execution"]["receipt"]
        self.assertEqual(receipt["outcome"], "CANDIDATE_TESTED", receipt)
        self.assertEqual(receipt["verification"]["closure"], "BOUNDED", receipt)
        self.assertTrue(receipt["shared_destination_rejected"])
        self.assertNotEqual(Path(receipt["worktree"]), self.root)
        self.assertEqual((self.root / "calc.py").read_bytes(), canonical)
        repeated = execute(self.root, self.cfg, "second", allowed["lease_id"], PRECEDENT, "execute", clock=self.clock)
        self.assertTrue(repeated["duplicate"])
        bad = proposal("bad", action=True)
        bad["actions"][0]["arguments"]["files"]["calc.py"] = "def add(a, b):\n    return 5\n"
        self.run_task("bad", bad)
        lease = authorize(self.root, self.cfg, "bad", "writer", PRECEDENT, "bad-lease", clock=self.clock)
        rejected = execute(self.root, self.cfg, "bad", lease["lease_id"], PRECEDENT, "bad-exec", clock=self.clock)
        self.assertEqual(rejected["execution"]["receipt"]["verification"]["closure"], "REFUTED")
        self.assertEqual((self.root / "calc.py").read_bytes(), canonical)

    @unittest.skipUnless(PRECEDENT, "set VERANTYX_PRECEDENT")
    def test_K2_changed_source_expiry_and_rule_withdrawal(self):
        self.init_git()
        rule, _ = self.promote()
        for reason in ("source", "expiry", "withdrawal"):
            self.run_task(reason, proposal(reason, action=True))
            lease = authorize(self.root, self.cfg, reason, "writer", PRECEDENT, reason + "-lease", clock=self.clock)
            if reason == "source":
                (self.root / "calc.py").write_text("# changed after authorization\n")
            elif reason == "expiry":
                self.time += timedelta(minutes=6)
            else:
                self.command("rule-retire", rule, reason="実行前に撤回")
            result = execute(self.root, self.cfg, reason, lease["lease_id"], PRECEDENT, reason + "-exec", clock=self.clock)
            self.assertEqual(result["execution"]["status"], "INVALIDATED")
            self.assertFalse(Path(result["execution"]["lease"]["resource_scope"]).exists())

    @unittest.skipUnless(PRECEDENT, "set VERANTYX_PRECEDENT")
    def test_interrupted_external_effect_is_never_repeated(self):
        self.init_git()
        self.promote()
        self.run_task("writer", proposal("writer", action=True))
        lease = authorize(self.root, self.cfg, "writer", "writer", PRECEDENT, "lease", clock=self.clock)
        def crash(stage):
            if stage == "after_effect":
                raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            execute(self.root, self.cfg, "writer", lease["lease_id"], PRECEDENT, "exec", clock=self.clock, fault=crash)
        with mock.patch("verantyx.adapters.precedent_backend.PrecedentBackend.prepare", side_effect=AssertionError("repeat")):
            result = execute(self.root, self.cfg, "writer", lease["lease_id"], PRECEDENT, "exec", clock=self.clock)
        self.assertEqual(result["execution"]["status"], "OUTCOME_UNKNOWN")


if __name__ == "__main__":
    unittest.main()

class BoundaryTests(Fixture):
    def test_changed_cross_engine_is_not_invoked_for_existing_rules(self):
        self.promote()
        class DifferentBackend:
            fingerprint = '0' * 64
            def match(self, *args):
                raise AssertionError('changed binary must not be invoked')
        self.backend = DifferentBackend()
        result = self.run_task('new-runtime')
        self.assertEqual(result['state']['assessment']['judgments'][0]['reason'], 'RULE_ENGINE_CHANGED')

    @unittest.skipUnless(PRECEDENT, 'set VERANTYX_PRECEDENT')
    def test_no_rule_cannot_authorize_writer(self):
        self.init_git()
        self.run_task('unapproved', proposal('unapproved', action=True))
        with self.assertRaises(LedgerError) as error:
            authorize(self.root, self.cfg, 'unapproved', 'writer', PRECEDENT, 'lease', clock=self.clock)
        self.assertEqual(error.exception.code, 'EXECUTION_BLOCKED')
        self.assertFalse((self.root / '.verantyx/worktrees').exists())

    @unittest.skipUnless(PRECEDENT, 'set VERANTYX_PRECEDENT')
    def test_changed_precedent_is_rejected_before_module_code_executes(self):
        self.init_git()
        self.promote()
        self.run_task('writer', proposal('writer', action=True))
        with tempfile.TemporaryDirectory() as temporary:
            backend = Path(temporary)
            source = backend / 'precedent/execution.py'
            source.parent.mkdir()
            source.write_bytes((Path(PRECEDENT) / 'precedent/execution.py').read_bytes())
            lease = authorize(self.root, self.cfg, 'writer', 'writer', backend, 'lease', clock=self.clock)
            sentinel = backend / 'loaded-mutant'
            source.write_text(source.read_text() + '\nPath(' + repr(str(sentinel)) + ').touch()\n')
            result = execute(self.root, self.cfg, 'writer', lease['lease_id'], backend, 'exec', clock=self.clock)
            self.assertEqual(result['execution']['status'], 'INVALIDATED')
            self.assertEqual(result['execution']['reason'], 'PRECEDENT_CHANGED')
            self.assertFalse(sentinel.exists())
            self.assertFalse(Path(result['execution']['lease']['resource_scope']).exists())
            retry = execute(self.root, self.cfg, 'writer', lease['lease_id'], backend, 'exec', clock=self.clock)
            self.assertFalse(retry['ok'])

    @unittest.skipUnless(PRECEDENT, 'set VERANTYX_PRECEDENT')
    def test_existing_precedent_sandbox_denies_writes_and_network(self):
        from verantyx.adapters.precedent_backend import PrecedentBackend
        test = self.root / 'test_boundary.py'
        marker = self.root / 'forbidden'
        test.write_text('import unittest,socket\nfrom pathlib import Path\nclass Boundary(unittest.TestCase):\n'
                        '    def test_write(self):\n        with self.assertRaises(PermissionError):\n            Path(' + repr(str(marker)) + ').write_text("bad")\n'
                        '    def test_network(self):\n        with self.assertRaises(PermissionError):\n            socket.create_connection(("127.0.0.1", 9), timeout=0.5)\n')
        executor = PrecedentBackend(PRECEDENT)
        evidence = executor.module.run_tests(self.root, [test])
        self.assertTrue(evidence['passed'], evidence['output'])
        self.assertFalse(marker.exists())

    @unittest.skipUnless(PRECEDENT, 'set VERANTYX_PRECEDENT')
    def test_git_hooks_and_smudge_filters_are_not_executed(self):
        self.init_git()
        marker = self.root / 'hook-was-run'
        hook = self.root / '.git/hooks/post-checkout'
        hook.write_text('#!/bin/sh\ntouch ' + repr(str(marker)) + '\n')
        hook.chmod(0o755)
        (self.root / '.gitattributes').write_text('calc.py filter=fixture\n')
        subprocess.run(['git', '-C', str(self.root), 'config', 'filter.fixture.smudge', 'touch ' + repr(str(marker))], check=True)
        subprocess.run(['git', '-C', str(self.root), 'add', '.gitattributes'], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@invalid',
                        'commit', '-qm', 'filter fixture'], check=True)
        self.promote()
        self.run_task('writer', proposal('writer', action=True))
        lease = authorize(self.root, self.cfg, 'writer', 'writer', PRECEDENT, 'lease', clock=self.clock)
        result = execute(self.root, self.cfg, 'writer', lease['lease_id'], PRECEDENT, 'exec', clock=self.clock)
        self.assertEqual(result['execution']['status'], 'CANDIDATE_TESTED')
        self.assertFalse(marker.exists())
