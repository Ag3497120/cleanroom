"""Common editor ingress and replay preserve every selected fixed test.

All adapters and operator decisions here are artificial temporary fixtures.
"""
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

import test_shared_context as shared_fixtures
from verantyx.application import dispatch
from verantyx.cli import parse
from verantyx.coordination_schema import schema
from verantyx.domain.events import make_event
from verantyx.errors import LedgerError
from verantyx.kernel.reducer import replay
from verantyx.responses import ask
from verantyx.storage.sqlite import EventStore


class FixedEditorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = shared_fixtures.SharedContextTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.cfg = self.fixture.root, self.fixture.cfg

    def prepare(self, mutation="", extra_paths=()):
        vera, editor = self.fixture.adapters("d['tests']=list(v['fixed_tests']); " + (mutation or "pass"))
        (self.root / "tests").mkdir(exist_ok=True)
        (self.root / "tests/test_smoke.py").write_text("import unittest\nclass Smoke(unittest.TestCase):\n    def test_smoke(self):\n        self.assertTrue(True)\n")
        return dict(request="Connect first; independence is deferred.", adapter_path=vera, editor_adapter=editor,
                    include_paths=["calc.py", "test_calc.py", "tests/test_smoke.py", *extra_paths], key="work", run_id="work",
                    context={"component": "calculator", "workload": "fixture", "risk": "LOW"})

    def workflow(self, mutation="", extra_paths=()):
        return ask(self.root, self.cfg, **self.prepare(mutation, extra_paths))

    def error(self, code, call, *args, **kwargs):
        with self.assertRaises(LedgerError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def rejected_command(self, mutation):
        kwargs = self.prepare(mutation)
        original = {p: (self.root / p).read_bytes() for p in kwargs["include_paths"]}
        self.error("TEST_SCOPE", ask, self.root, self.cfg, **kwargs)
        calls = self.fixture.fixture.invocations()
        self.assertEqual(len(calls), 3)
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            events = store.events("work")
        self.assertNotIn("EditorAttemptRecorded", [event["type"] for event in events])
        self.assertFalse(replay(events)["effects"])
        self.assertTrue(all((self.root / p).read_bytes() == raw for p, raw in original.items()))
        # A retry must preserve the rejected result, without another model call.
        self.error("TEST_SCOPE", ask, self.root, self.cfg, **kwargs)
        self.assertEqual(len(self.fixture.fixture.invocations()), 3)

    def events(self):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            return store.events("work")

    @staticmethod
    def rechain(events):
        result = []
        for event in events:
            result.append(make_event(event["project_id"], event["stream_id"], event["revision"], event["command_id"],
                                     event["recorded_at"], event["type"], event["payload"], event["event_id"], result[-1] if result else None))
        return result

    def test_common_command_preserves_root_and_nested_fixed_tests(self):
        (self.root / "test_unselected.py").write_text("raise RuntimeError('not selected')\n")
        (self.root / "checks.py").write_text("# Selected support file, not an implicit fixed test.\n")
        result = self.workflow(extra_paths=["checks.py"])
        state = result["state"]
        expected = ["test_calc.py", "tests/test_smoke.py"]
        self.assertEqual(state["editor_attempt"]["document"]["tests"], expected)
        self.assertEqual(state["proposal"]["actions"][0]["arguments"]["tests"], expected)
        self.assertEqual(state["editor_attempt"]["validation"]["status"], "MATCHED")
        self.assertEqual(state["effects"], {})

    def test_common_command_cannot_omit_one_of_two_fixed_tests(self):
        self.rejected_command("d['tests']=['tests/test_smoke.py']")

    def test_common_command_cannot_omit_and_rewrite_the_stronger_test(self):
        self.rejected_command("d['tests']=['tests/test_smoke.py']; d['files']['test_calc.py']='print(\"weakened\")\\n'")

    def test_common_command_cannot_remove_all_fixed_tests(self):
        self.rejected_command("d['tests']=[]")

    def test_common_command_cannot_rewrite_a_retained_fixed_test(self):
        self.rejected_command("d['files']['test_calc.py']='print(\"weakened\")\\n'")

    def test_common_command_cannot_reorder_the_frozen_test_list(self):
        self.rejected_command("d['tests'].reverse()")

    def test_common_command_cannot_name_unselected_test(self):
        self.rejected_command("d['tests'].append('test_unselected.py')")

    def test_recorded_test_omission_and_rewrite_fail_even_after_hash_chain_is_rebuilt(self):
        self.workflow()
        recorded = self.events()
        # Isolate the editor event from downstream response snapshots: the
        # ingress contract must reject it even before a candidate is generated.
        through = next(i for i, e in enumerate(recorded) if e["type"] == "EditorAttemptRecorded")
        events = recorded[:through + 1]
        saved = deepcopy(events)
        for rewrite in (False, True):
            with self.subTest(rewrite=rewrite):
                forged = deepcopy(events)
                attempt = next(e for e in forged if e["type"] == "EditorAttemptRecorded")
                attempt["payload"]["document"]["tests"] = ["tests/test_smoke.py"]
                if rewrite:
                    attempt["payload"]["document"]["files"]["test_calc.py"] = "print('weakened')\n"
                with mock.patch("subprocess.run", side_effect=AssertionError("replay executed a process")):
                    self.error("TEST_SCOPE", replay, self.rechain(forged))
        self.assertEqual(events, saved)

    def test_valid_recorded_history_replays_without_files_models_or_cross(self):
        first = self.workflow()
        events = self.events()
        for path in ("calc.py", "test_calc.py", "tests/test_smoke.py"):
            (self.root / path).unlink()
        with mock.patch("subprocess.run", side_effect=AssertionError("replay executed a process")), \
             mock.patch("verantyx.adapters.command_process.BoundedProcess", side_effect=AssertionError("replay invoked model")):
            restored = replay(events)
        self.assertEqual(restored["editor_attempt"], first["state"]["editor_attempt"])

    def test_generation_contract_derives_tests_from_selected_sources(self):
        from jsonschema import Draft202012Validator
        self.workflow()
        request = deepcopy(self.fixture.fixture.invocations()[2])
        doc = deepcopy(next(e for e in self.events() if e["type"] == "EditorAttemptRecorded")["payload"]["document"])
        request["fixed_tests"] = ["tests/test_smoke.py"]
        doc["tests"] = ["tests/test_smoke.py"]
        self.assertFalse(Draft202012Validator(schema(request)).is_valid(doc))
        doc["tests"] = ["test_calc.py", "tests/test_smoke.py"]
        self.assertTrue(Draft202012Validator(schema(request)).is_valid(doc))
        from verantyx.coordination_schema import encode_editor_document
        encoded = encode_editor_document(doc)
        encoded["tests"] = ["tests/test_smoke.py"]
        self.assertFalse(Draft202012Validator(schema(request, line_blocks=True)).is_valid(encoded))

    def test_explicit_selected_python_test_remains_supported_without_test_prefix(self):
        vera, editor = self.fixture.adapters("d['tests']=['checks.py']")
        (self.root / "checks.py").write_text((self.root / "test_calc.py").read_text())
        result = ask(self.root, self.cfg, request="Connect first; independence is deferred.", adapter_path=vera,
                     editor_adapter=editor, include_paths=["calc.py", "checks.py"], key="work", run_id="work")
        self.assertEqual(result["state"]["proposal"]["actions"][0]["arguments"]["tests"], ["checks.py"])

    def test_actual_execution_runs_all_fixed_tests_and_refutes_bad_candidate(self):
        result = self.workflow("d['files']['calc.py']='def answer():\\n    return 1\\n'")
        for args in (["init", "-q"], ["add", "calc.py", "test_calc.py", "tests/test_smoke.py"],
                     ["-c", "user.name=ARTIFICIAL FIXTURE", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixed tests"]):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)
        _, args = parse(["decide", "work", "--point", "editor-isolation", "--choice", "isolate", "--reason",
                         "ARTIFICIAL FIXTURE, not an actual user decision", "--key", "decision", "--expected-revision",
                         str(result["recorded_revision"])])
        dispatch(self.root, self.cfg, args, "ja")
        from verantyx.effects import authorize, execute
        auth = authorize(self.root, self.cfg, "work", "editor-apply", os.environ["VERANTYX_PRECEDENT"], "allow")
        executed = execute(self.root, self.cfg, "work", auth["lease_id"], os.environ["VERANTYX_PRECEDENT"], "execute")
        effect = executed["state"]["effects"][auth["lease_id"]]
        verification = effect["receipt"]["verification"]
        self.assertEqual(verification["scope"]["tests"], ["test_calc.py", "tests/test_smoke.py"])
        self.assertEqual(verification["closure"], "REFUTED")
        self.assertFalse(verification["result"]["passed"])
        self.assertIn("Ran 2 tests", verification["result"]["output"])
        self.assertFalse(verification["adoption_authorized"])
        self.assertEqual((self.root / "test_calc.py").read_bytes(), (Path(effect["lease"]["resource_scope"]) / "test_calc.py").read_bytes())


if __name__ == "__main__":
    unittest.main()
