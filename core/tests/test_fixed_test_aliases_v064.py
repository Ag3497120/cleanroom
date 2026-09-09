"""Independent portable enforcement tests; every project and choice is artificial.

These tests intentionally reject path aliases even on a case-sensitive host.
The actual macOS filesystem exploit is recorded separately in validation JSON.
"""
from copy import deepcopy
import os
import subprocess
import unittest
from unittest import mock

import test_fixed_editor_tests as fixed_fixtures
from verantyx.application import dispatch
from verantyx.cli import parse
from verantyx.coordination import validate_editor
from verantyx.coordination_schema import encode_editor_document
from verantyx.domain.effects import plan_for
from verantyx.effects import authorize, execute
from verantyx.errors import LedgerError
from verantyx.kernel.reducer import replay
from verantyx.model_api import _validate_output
from verantyx.responses import ask


class FixedTestAliasTests(unittest.TestCase):
    def fixture(self):
        h = fixed_fixtures.FixedEditorTests(methodName="runTest")
        h.setUp()
        self.addCleanup(h.doCleanups)
        return h

    def alias_request(self, h, mutation=""):
        kwargs = h.prepare(mutation, extra_paths=["TEST_CALC.py"])
        # On case-sensitive hosts this creates another file. The comparison
        # rule is deliberately conservative and must still reject the write.
        (h.root / "TEST_CALC.py").write_bytes((h.root / "test_calc.py").read_bytes())
        return kwargs

    def test_common_command_rejects_selected_case_alias_write_without_recording_an_attempt(self):
        for legacy_name in (False, True):
            with self.subTest(legacy_name=legacy_name):
                h = self.fixture()
                if legacy_name:
                    vera, editor = h.fixture.adapters("d['tests']=['checks.py']; d['files']['CHECKS.py']='print(\"weakened test\")\\n'")
                    for name in ("checks.py", "CHECKS.py"):
                        (h.root / name).write_bytes((h.root / "test_calc.py").read_bytes())
                    kwargs = dict(request="Connect first; independence is deferred.", adapter_path=vera,
                                  editor_adapter=editor, include_paths=["calc.py", "checks.py", "CHECKS.py"], key="work", run_id="work")
                else:
                    kwargs = self.alias_request(h, "d['files']['TEST_CALC.py']='print(\"weakened test\")\\n'")
                before = {path: (h.root / path).read_bytes() for path in kwargs["include_paths"]}
                with self.assertRaises(LedgerError) as caught:
                    ask(h.root, h.cfg, **kwargs)
                self.assertEqual(caught.exception.code, "TEST_SCOPE")
                events = h.events()
                self.assertNotIn("EditorAttemptRecorded", {event["type"] for event in events})
                self.assertFalse(replay(events)["effects"])
                self.assertEqual({path: (h.root / path).read_bytes() for path in before}, before)

    def test_api_transport_and_pure_replay_reject_the_same_alias_write(self):
        h = self.fixture()
        result = ask(h.root, h.cfg, **self.alias_request(h))
        state = result["state"]
        request = h.fixture.fixture.invocations()[2]
        document = deepcopy(state["editor_attempt"]["document"])
        document["files"]["TEST_CALC.py"] = "print('weakened test')\n"
        for wire_document in (document, encode_editor_document(document)):
            # API transport decoding is followed by the same common ingress.
            decoded = _validate_output(request, wire_document)
            with self.assertRaises(LedgerError) as caught:
                validate_editor(decoded, state["shared_context"], state["handoff_plan"]["plan"],
                                selected_files=request["selected_files"])
            self.assertEqual(caught.exception.code, "TEST_SCOPE")
        recorded = h.events()
        index = next(i for i, event in enumerate(recorded) if event["type"] == "EditorAttemptRecorded")
        forged = deepcopy(recorded[:index + 1])
        forged[-1]["payload"]["document"] = document
        rebuilt = h.rechain(forged)
        with mock.patch("subprocess.Popen", side_effect=AssertionError("replay launched a process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("replay ran a command")), \
             mock.patch("verantyx.application.now", side_effect=AssertionError("replay read the clock")):
            with self.assertRaises(LedgerError) as caught:
                replay(rebuilt)
        self.assertEqual(caught.exception.code, "TEST_SCOPE")
        self.assertEqual(h.events(), recorded)

    def test_direct_writer_rejects_case_and_unicode_aliases_but_keeps_distinct_paths(self):
        for test, candidate in (("test_calc.py", "TEST_CALC.py"),
                                ("tests/test_calc.py", "Tests/TEST_CALC.py"),
                                ("test_caf\u00e9.py", "TEST_CAFE\u0301.py"),
                                ("checks.py", "CHECKS.py"),
                                ("checks_caf\u00e9.py", "CHECKS_CAFE\u0301.py")):
            with self.subTest(test=test, candidate=candidate):
                action = {"tool_id": "writer.apply", "arguments": {"point_id": "isolation", "destination": "shared",
                          "files": {candidate: "# proposed replacement\n"}, "tests": [test]}}
                with self.assertRaises(LedgerError) as caught:
                    plan_for(action)
                self.assertEqual(caught.exception.code, "TEST_SCOPE")
        for test in ("test_calc.py", "checks.py"):
            action = {"tool_id": "writer.apply", "arguments": {"point_id": "isolation", "destination": "shared",
                      "files": {"calc.py": "def answer():\n    return 2\n"}, "tests": [test]}}
            self.assertEqual(plan_for(action)["tests"], [test])
        self.assertEqual(plan_for({"tool_id": "worktree.prepare", "arguments": {
            "point_id": "isolation", "destination": "shared"}})["files"], {})

    def test_explicit_nonprefix_test_still_executes_and_replays_without_files(self):
        h = self.fixture()
        vera, editor = h.fixture.adapters("d['tests']=['checks.py']")
        (h.root / "checks.py").write_bytes((h.root / "test_calc.py").read_bytes())
        result = ask(h.root, h.cfg, request="Connect first; independence is deferred.", adapter_path=vera,
                     editor_adapter=editor, include_paths=["calc.py", "checks.py"], key="work", run_id="work",
                     context={"component": "calculator", "workload": "fixture", "risk": "LOW"})
        action = result["state"]["proposal"]["actions"][0]
        self.assertEqual(action["arguments"]["tests"], ["checks.py"])
        for args in (["init", "-q"], ["add", "calc.py", "checks.py"],
                     ["-c", "user.name=Artificial fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Explicit test"]):
            subprocess.run(["git", "-C", str(h.root), *args], check=True, capture_output=True)
        _, args = parse(["decide", "work", "--point", action["arguments"]["point_id"], "--choice", "isolate",
                         "--reason", "Artificial fixture decision; not user approval", "--key", "decision"])
        dispatch(h.root, h.cfg, args, "ja")
        permission = authorize(h.root, h.cfg, "work", action["id"], os.environ["VERANTYX_PRECEDENT"], "permit")
        executed = execute(h.root, h.cfg, "work", permission["lease_id"], os.environ["VERANTYX_PRECEDENT"], "execute")
        verification = executed["execution"]["receipt"]["verification"]
        self.assertEqual(verification["scope"]["tests"], ["checks.py"])
        self.assertEqual(verification["closure"], "BOUNDED")
        events = h.events()
        for path in ("calc.py", "checks.py"):
            (h.root / path).unlink()
        with mock.patch("subprocess.run", side_effect=AssertionError("replay ran a command")), \
             mock.patch("subprocess.Popen", side_effect=AssertionError("replay launched a process")):
            self.assertEqual(replay(events)["effects"], executed["state"]["effects"])
