"""Independent boundary regressions for the one-shot candidate work loop."""
import contextlib
import io
import json
from unittest import mock
import unittest

import test_work_loop_v072 as fixtures
from verantyx.application import get_projection
from verantyx.cli import main
from verantyx.effects import authorize, execute
from verantyx.errors import LedgerError
from verantyx.storage.sqlite import EventStore
from verantyx.work_loop import run_candidate


class WorkLoopReviewTests(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.WorkLoopTests()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.root, self.cfg = self.h.root, self.h.cfg

    def current(self):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            return get_projection(store, "first")

    def interrupted(self, *, collect_unknown):
        base = self.h.prepared()
        def crash(stage):
            if stage == "after_effect":
                raise RuntimeError("Interrupted after an actual candidate effect")
        with self.assertRaises(RuntimeError):
            self.h.run_work(base, fault=crash)
        if collect_unknown:
            self.h.run_work(base)
        return self.current()

    def test_new_operation_key_cannot_reauthorize_an_unresolved_candidate(self):
        state = self.interrupted(collect_unknown=False)["state"]
        with self.assertRaises(LedgerError) as raised:
            authorize(self.root, self.cfg, "first", self.h.action["id"], self.h.precedent,
                      "different-key", expected_revision=state["revision"])
        self.assertEqual(raised.exception.code, "EXECUTION_OUTCOME_UNKNOWN")
        self.assertEqual(len(self.current()["state"]["effects"]), 1)

    def test_work_with_new_key_cannot_repeat_a_recorded_unknown_effect(self):
        state = self.interrupted(collect_unknown=True)["state"]
        with mock.patch("verantyx.adapters.precedent_backend.PrecedentBackend.apply_and_test",
                        side_effect=AssertionError("The same unknown candidate executed again")):
            result = run_candidate(self.root, self.cfg, "first", key="console-next-key",
                                   expected_revision=state["revision"], execute=True,
                                   precedent_path=self.h.precedent)
        self.assertFalse(result["ok"])
        self.assertEqual(result["work_loop"]["reason"], "EXECUTION_OUTCOME_UNKNOWN")
        self.assertEqual(len(result["state"]["effects"]), 1)
        self.assertTrue(result["state"]["deltas"]["system_delta"]["failure_assets"])

    def test_refresh_cannot_hide_the_same_unresolved_effect_in_a_new_proposal(self):
        state = self.interrupted(collect_unknown=True)["state"]
        with mock.patch("verantyx.adapters.precedent_backend.PrecedentBackend.apply_and_test",
                        side_effect=AssertionError("Refresh repeated the unknown candidate")):
            result = run_candidate(self.root, self.cfg, "first", key="refresh-unknown",
                                   expected_revision=state["revision"], execute=True, refresh=True,
                                   precedent_path=self.h.precedent, adapter_path=self.h.proposer,
                                   editor_adapter=self.h.editor, include_paths=["calc.py", "test_calc.py"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["work_loop"]["reason"], "EXECUTION_OUTCOME_UNKNOWN")
        self.assertEqual(len(result["state"]["effects"]), 1)

    def test_a_legacy_duplicate_lease_is_refused_at_execution_without_rewriting_history(self):
        state = self.interrupted(collect_unknown=True)["state"]
        # Reproduce the earlier release's ability to issue this lease; the
        # execution under test runs with the corrected boundary enabled.
        with mock.patch("verantyx.effects._unresolved_execution", return_value=False):
            permission = authorize(self.root, self.cfg, "first", self.h.action["id"], self.h.precedent,
                                   "legacy-permission", expected_revision=state["revision"])
        with mock.patch("verantyx.adapters.precedent_backend.PrecedentBackend.apply_and_test",
                        side_effect=AssertionError("A legacy lease repeated the uncertain effect")):
            result = execute(self.root, self.cfg, "first", permission["lease_id"], self.h.precedent,
                             "execute-legacy-permission")
        self.assertFalse(result["ok"])
        self.assertEqual(result["execution"]["status"], "INVALIDATED")
        self.assertEqual(result["execution"]["reason"], "EXECUTION_OUTCOME_UNKNOWN")
        self.assertEqual(len(result["state"]["effects"]), 2)

    def test_a_changed_decision_invalidates_the_old_lease_without_an_effect(self):
        base = self.h.prepared()
        permission = authorize(self.root, self.cfg, "first", self.h.action["id"], self.h.precedent,
                               "old-permission", expected_revision=base["recorded_revision"])
        self.h.command("decide", "first", "--point", self.h.action["arguments"]["point_id"],
                       "--choice", "share", "--reason", "Artificial changed decision", "--key", "changed")
        with mock.patch("verantyx.adapters.precedent_backend.PrecedentBackend.apply_and_test",
                        side_effect=AssertionError("An old lease executed")):
            result = execute(self.root, self.cfg, "first", permission["lease_id"], self.h.precedent,
                             "execute-old-permission")
        self.assertFalse(result["ok"])
        self.assertEqual(result["execution"]["status"], "INVALIDATED")
        self.assertEqual(result["execution"]["reason"], "CONTEXT_CHANGED")

    def test_refresh_execution_and_collection_replay_without_model_or_effect_calls(self):
        base = self.h.prepared()
        options = dict(key="refresh", expected_revision=base["recorded_revision"], execute=True,
                       refresh=True, precedent_path=self.h.precedent, adapter_path=self.h.proposer,
                       editor_adapter=self.h.editor, include_paths=["calc.py", "test_calc.py"])
        result = run_candidate(self.root, self.cfg, "first", **options)
        calls = len(self.h.h.fixture.invocations())
        with mock.patch("verantyx.adapters.precedent_backend.PrecedentBackend.apply_and_test",
                        side_effect=AssertionError("Refresh replay repeated an effect")):
            repeated = run_candidate(self.root, self.cfg, "first", **options)
        self.assertTrue(result["ok"])
        self.assertEqual(result["projection_hash"], repeated["projection_hash"])
        self.assertEqual(len(self.h.h.fixture.invocations()), calls)
        self.assertEqual(len(repeated["state"]["effects"]), 1)

    def test_console_refresh_rejects_changed_selected_model_configuration(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True
        lines = iter(["Correct calculator", "/work refresh", "/quit"])
        def read(_ui):
            line = next(lines)
            if line == "/work refresh":
                data = json.loads(self.h.editor.read_text())
                data["argv"] = [*data["argv"], "changed-model-config"]
                self.h.editor.write_text(json.dumps(data))
            return line
        output = Terminal()
        with mock.patch("sys.stdin", Terminal()), contextlib.redirect_stdout(output), \
                mock.patch("verantyx.terminal_ui.ConsoleUI.read", read):
            code = main(["--project", str(self.root), "--lang", "en", "start", "--plain",
                         "--adapter", str(self.h.proposer), "--editor-adapter", str(self.h.editor),
                         "--include", "calc.py", "--include", "test_calc.py"])
        self.assertEqual(code, 0)
        calls = self.h.h.fixture.invocations()
        self.assertEqual(sum(row["format"] == "verantyx.editor-request.v1" for row in calls), 1)
        self.assertIn("The selected adapter has changed", output.getvalue())
