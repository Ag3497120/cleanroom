"""Explicit unsandboxed fixture commands: grants, stale inputs and unknown outcomes."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
import json
import sys
import tempfile
import unittest

from verantyx import config
from verantyx.application import record_run
from verantyx.command_effects import propose_command, authorize_command, execute_command, list_commands
from verantyx.domain.codec import digest
from verantyx.errors import LedgerError
from verantyx.kernel.reducer import replay, projection
from verantyx.storage.sqlite import EventStore, parse_archive


class CommandEffectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.cfg = config.defaults(self.root, "ja")
        config.save(self.root, self.cfg, None)
        self.time = datetime(2026, 9, 6, tzinfo=timezone.utc)
        self.clock = lambda: self.time
        self.target = self.root / "artifact.txt"
        self.target.write_text("before")
        self.script = self.root / "executor.py"
        self.script.write_text("import json,sys\nfrom pathlib import Path\nx=json.load(sys.stdin)\nPath('artifact.txt').write_text(x['text'])\nprint('completed')\n")
        self.command = self.root / "command.json"
        self.adapter = {"argv": [sys.executable, str(self.script)], "cwd": str(self.root), "env": {"FIXTURE_SECRET": "test-env-value-not-for-receipt"}}
        self.command.write_text(json.dumps(self.adapter))
        first = record_run(self.root, self.cfg, request="fixture command", run_id="command", observe_paths=["artifact.txt"], clock=self.clock)
        proposal = {"schema_version": 1, "task_id": "command", "context_revision": first["state"]["revision"], "response_locale": "ja",
                    "summary": "fixture", "claims": [], "actions": [], "unknowns": []}
        (self.root / "proposal.json").write_text(json.dumps(proposal))
        record_run(self.root, self.cfg, run_id="command", proposal_path=self.root / "proposal.json", resume=True, clock=self.clock)
        self.spec = {"description": "Update local fixture text", "effect_class": "REVERSIBLE_LOCAL", "targets": ["artifact.txt"],
                     "external_target": "", "input": {"text": "after"}, "timeout": 1, "max_output": 4096,
                     "dependencies": [], "compensation": "Rewrite the previous fixture text after review"}

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, key="propose", **kwargs):
        return propose_command(self.root, self.cfg, "command", self.spec, key, command_path=self.command, clock=self.clock, **kwargs)

    def authorize(self, plan, key="authorize", **kwargs):
        args = {"plan_hash": plan["plan_hash"], "command_path": self.command, "reason": "synthetic fixture permission",
                "accept_unsandboxed": True, "clock": self.clock, **kwargs}
        return authorize_command(self.root, self.cfg, "command", plan["command_effect_id"], key, **args)

    def run_command(self, plan, key="execute", **kwargs):
        return execute_command(self.root, self.cfg, "command", plan["command_effect_id"], key, command_path=self.command, clock=self.clock, **kwargs)

    def events(self):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            return store.events("command")

    def test_proposal_and_authorization_do_not_execute_then_actual_fixture_process_runs_once(self):
        planned = self.plan()
        self.assertEqual(self.target.read_text(), "before")
        with self.assertRaises(LedgerError): self.run_command(planned)
        self.authorize(planned)
        self.assertEqual(self.target.read_text(), "before")
        result = self.run_command(planned)
        self.assertEqual(self.target.read_text(), "after")
        self.assertEqual(result["command_effect"]["status"], "PROCESS_COMPLETED")
        self.assertEqual(result["command_effect"]["receipt"]["process"]["effect_confirmation"], "NOT_ASSESSED")
        self.assertNotIn("test-env-value-not-for-receipt", json.dumps(result))
        with mock.patch("verantyx.command_effects.BoundedProcess", side_effect=AssertionError("duplicate effect")):
            self.assertTrue(self.run_command(planned)["duplicate"])
        with self.assertRaises(LedgerError): self.run_command(planned, key="different-key")

    def test_expiry_during_final_preconditions_never_launches_the_process(self):
        from verantyx import command_effects
        planned = self.plan()
        self.authorize(planned, ttl=1)
        original = command_effects._current_reason
        def advance(*args, **kwargs):
            result = original(*args, **kwargs)
            self.time += timedelta(seconds=2)
            return result
        with mock.patch.object(command_effects, '_current_reason', side_effect=advance), \
             mock.patch.object(command_effects, 'BoundedProcess', side_effect=AssertionError('expired effect launched')):
            result = self.run_command(planned)
        self.assertEqual(result['command_effect']['status'], 'INVALIDATED')
        self.assertEqual(result['command_effect']['receipt']['reason'], 'AUTHORIZATION_EXPIRED')
        self.assertEqual(self.target.read_text(), 'before')

    def test_deferred_model_api_command_cannot_be_used_as_general_effect(self):
        from verantyx import command_effects
        original = command_effects.load_command(self.command)
        original['deferred_env'] = ['ARTIFICIAL_API_KEY']
        with mock.patch.object(command_effects, 'load_command', return_value=original), self.assertRaises(LedgerError) as refused:
            self.plan()
        self.assertEqual(refused.exception.code, 'COMMAND_EXECUTOR_UNAVAILABLE')

    def test_unsandboxed_and_irreversible_permissions_are_explicit_and_bound_to_plan_hash(self):
        self.spec.update(effect_class="IRREVERSIBLE_EXTERNAL", external_target="fixture://local-only/no-network")
        planned = self.plan()
        for kw in ({"accept_unsandboxed": False}, {"accept_irreversible": False}, {"plan_hash": "f"*64, "accept_irreversible": True}, {"accept_unsandboxed": 1, "accept_irreversible": True}):
            with self.assertRaises(LedgerError): self.authorize(planned, **kw)
        self.authorize(planned, accept_irreversible=True)
        self.assertEqual(self.run_command(planned)["command_effect"]["status"], "PROCESS_COMPLETED")
        self.assertEqual(self.target.read_text(), "after")

    def test_modified_script_or_environment_invalidates_before_process_launch(self):
        planned = self.plan()
        self.authorize(planned)
        self.script.write_text("raise RuntimeError('changed')")
        with mock.patch("verantyx.command_effects.BoundedProcess", side_effect=AssertionError("changed executable dispatched")):
            result = self.run_command(planned)
        self.assertEqual(result["command_effect"]["receipt"]["reason"], "EXECUTOR_CHANGED")
        self.assertEqual(self.target.read_text(), "before")

    def test_changed_inherited_environment_is_detected_even_when_config_bytes_match(self):
        self.adapter["inherit_env"] = ["VERANTYX_FIXTURE_RUNTIME"]
        self.command.write_text(json.dumps(self.adapter))
        with mock.patch.dict("os.environ", {"VERANTYX_FIXTURE_RUNTIME": "before"}):
            planned = self.plan()
            self.authorize(planned)
        with mock.patch.dict("os.environ", {"VERANTYX_FIXTURE_RUNTIME": "changed"}), mock.patch("verantyx.command_effects.BoundedProcess", side_effect=AssertionError("environment drift")):
            result = self.run_command(planned)
        self.assertEqual(result["command_effect"]["receipt"]["reason"], "EXECUTOR_CHANGED")

    def test_changed_target_and_missing_or_symlink_target_reject_before_launch(self):
        planned = self.plan()
        self.authorize(planned)
        self.target.unlink()
        self.target.symlink_to(self.script)
        with mock.patch("verantyx.command_effects.BoundedProcess", side_effect=AssertionError("target replaced")):
            result = self.run_command(planned)
        self.assertEqual(result["command_effect"]["receipt"]["reason"], "PRECONDITION_CHANGED")

    def test_expiry_after_start_is_rechecked_before_launch(self):
        planned = self.plan(ttl=1)
        self.authorize(planned, ttl=1)
        def expire(stage):
            if stage == "after_start": self.time += timedelta(seconds=1)
        with mock.patch("verantyx.command_effects.BoundedProcess", side_effect=AssertionError("expired effect")):
            result = self.run_command(planned, fault=expire)
        self.assertEqual(result["command_effect"]["receipt"]["reason"], "AUTHORIZATION_EXPIRED")
        self.assertEqual(self.target.read_text(), "before")

    def test_expiry_after_process_records_unknown_and_cannot_retry(self):
        planned = self.plan(ttl=1)
        self.authorize(planned, ttl=1)
        def expire(stage):
            if stage == "after_process": self.time += timedelta(seconds=1)
        result = self.run_command(planned, fault=expire)
        self.assertEqual(result["command_effect"]["status"], "OUTCOME_UNKNOWN")
        self.assertEqual(self.target.read_text(), "after")
        self.assertTrue(self.run_command(planned)["duplicate"])

    def test_interruption_after_effect_is_not_resubmitted_and_partial_output_is_not_confirmation(self):
        planned = self.plan()
        self.authorize(planned)
        def interrupt(stage):
            if stage == "after_process": raise RuntimeError("simulated crash after local effect")
        with self.assertRaises(RuntimeError): self.run_command(planned, fault=interrupt)
        self.assertEqual(self.target.read_text(), "after")
        with mock.patch("verantyx.command_effects.BoundedProcess", side_effect=AssertionError("resubmitted effect")):
            result = self.run_command(planned)
        self.assertEqual(result["command_effect"]["status"], "OUTCOME_UNKNOWN")

    def test_timeout_after_partial_effect_is_unknown(self):
        self.script.write_text("from pathlib import Path\nimport time\nPath('artifact.txt').write_text('partial')\ntime.sleep(2)\n")
        self.spec["timeout"] = 0.1
        planned = self.plan()
        self.authorize(planned)
        result = self.run_command(planned)
        self.assertEqual(result["command_effect"]["status"], "OUTCOME_UNKNOWN")
        self.assertEqual(result["command_effect"]["receipt"]["reason"], "BRIDGE_TIMEOUT")
        self.assertEqual(self.target.read_text(), "partial")

    def test_output_limit_and_failed_exit_do_not_assert_effect_success(self):
        self.script.write_text("import sys\nsys.stderr.write('x'*10000)\n")
        planned = self.plan()
        self.authorize(planned)
        result = self.run_command(planned)
        self.assertEqual(result["command_effect"]["status"], "OUTCOME_UNKNOWN")
        self.assertEqual(result["command_effect"]["receipt"]["reason"], "BRIDGE_OUTPUT_LIMIT")

    def test_nonzero_exit_is_a_process_failure_not_a_verified_external_outcome(self):
        self.script.write_text("import sys\nprint('OK')\nsys.exit(4)\n")
        planned = self.plan()
        self.authorize(planned)
        result = self.run_command(planned)
        self.assertEqual(result["command_effect"]["status"], "PROCESS_FAILED")
        self.assertEqual(result["command_effect"]["receipt"]["process"]["returncode"], 4)
        self.assertFalse(result["ok"])

    def test_targets_must_be_observed_and_compensation_requires_description(self):
        self.spec["targets"] = ["unobserved.txt"]
        with self.assertRaises(LedgerError): self.plan()
        self.spec.update(targets=["artifact.txt"], effect_class="COMPENSATABLE_EXTERNAL", compensation="", external_target="fixture://local")
        with self.assertRaises(LedgerError): self.plan()

    def test_replay_archive_is_inert_and_rehashed_authority_and_receipt_forgery_rejected(self):
        planned = self.plan()
        self.authorize(planned)
        result = self.run_command(planned)
        events = self.events()
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            raw = store.export().encode()
        self.script.unlink()
        with mock.patch("verantyx.command_effects.executor_identity", side_effect=AssertionError("replay executor read")), mock.patch("verantyx.command_effects.BoundedProcess", side_effect=AssertionError("replay process")):
            self.assertEqual(projection(replay(events))["projection_hash"], result["projection_hash"])
            parse_archive(raw)
        ai = next(i for i,e in enumerate(events) if e["type"] == "CommandEffectAuthorized")
        ri = next(i for i,e in enumerate(events) if e["type"] == "CommandEffectRecorded")
        for index, change in ((ai, "grant"), (ai, "expiry"), (ri, "approved"), (ri, "hash")):
            forged = deepcopy(events[index])
            if change == "grant": forged["payload"]["accept_unsandboxed"] = False
            elif change == "expiry": forged["payload"]["expires_at"] = "2030-01-01T00:00:00.000000Z"
            elif change == "approved": forged["payload"]["process"]["effect_confirmation"] = "CONFIRMED"
            else: forged["payload"]["plan_hash"] = "f"*64
            forged["event_hash"] = digest({k:v for k,v in forged.items() if k != "event_hash"})
            with self.assertRaises(LedgerError): replay([*events[:index], forged])

    def test_trust_label_does_not_claim_sandbox_and_command_requires_separate_permission(self):
        self.spec["effect_class"] = "READ_ONLY"
        planned = self.plan()
        self.assertEqual(planned["command_effect"]["plan"]["executor"]["isolation"], "NONE_TRUSTED_COMMAND")
        with self.assertRaises(LedgerError): self.run_command(planned)
