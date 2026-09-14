"""Synthetic CLI/menu boundaries; no external adapters or models are executed."""
from argparse import Namespace
from contextlib import ExitStack, contextmanager, redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest import mock
import io
import json
import tempfile
import unittest

from verantyx import commands_skills_home as home, commands_v04, config, console, personal_skills
from verantyx.cli import main
from verantyx.errors import LedgerError


class Terminal(io.StringIO):
    def isatty(self):
        return True


class SkillsHomeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.cfg = config.defaults(self.root, "ja")
        config.save(self.root, self.cfg, None)
        self.view = {"schema_version": 1, "ok": True, "command": "skills", "root": str(self.root),
                     "interactive_requested": True, "scope": {"id": "initial-scope"}, "omitted_runs": 0,
                     "model_called": False, "writes": False, "works": [{
                         "run_id": "synthetic-work", "label": "合成作業", "revision": 9,
                         "methods": [], "failures": [], "candidates": [], "skills": [{
                             "id": "synthetic-skill", "concept": "適用範囲を説明する", "ownership_target": "REVIEW",
                             "target_is_suggestion": True, "recorded": True, "status": "OPEN"}]}]}
        modules = tuple(module for module in commands_v04.modules() if "skills" not in module.COMMANDS)
        self.registry = mock.patch.object(commands_v04, "modules", return_value=(*modules, home))
        self.registry.start()
        self.addCleanup(self.registry.stop)
        for target in ("subprocess.Popen", "socket.socket"):
            guard = mock.patch(target, side_effect=AssertionError("external call forbidden: " + target))
            guard.start()
            self.addCleanup(guard.stop)

    def files(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()}

    def result_for(self, root, locale, argv):
        if argv[0] == "skills-stack":
            return deepcopy(self.view)
        return {"ok": True, "command": argv[0], "response_mode": "GENERATED"}

    def menu(self, answers, operation=None):
        output = Terminal()
        with mock.patch("sys.stdin", Terminal()), redirect_stdout(output), \
             mock.patch("builtins.input", side_effect=answers), \
             mock.patch.object(console, "_operation", side_effect=operation or self.result_for) as call:
            home.display(deepcopy(self.view), "ja", "skills")
        return output.getvalue(), call

    def adapters(self):
        paths = [self.root / "implementation.json", self.root / "verification.json"]
        for path in paths:
            path.write_text("{}")
        return [str(path) for path in paths]

    def test_dispatch_reads_real_empty_library_without_prompts_or_writes(self):
        before = self.files()
        with mock.patch("builtins.input", side_effect=AssertionError("dispatch prompted")), \
             mock.patch("verantyx.storage.sqlite.EventStore.append", side_effect=AssertionError("ledger write")):
            result = home.dispatch(self.root, self.cfg, Namespace(interactive=True), "ja")
        self.assertEqual(result["command"], "skills")
        self.assertTrue(result["interactive_requested"])
        self.assertFalse(result["writes"])
        self.assertFalse(result["model_called"])
        self.assertEqual(result["works"], [])
        self.assertEqual(self.files(), before)

    def test_default_display_and_nonterminal_interactive_never_prompt(self):
        for interactive in (False, True):
            with self.subTest(interactive=interactive), redirect_stdout(io.StringIO()) as output, \
                 mock.patch("sys.stdin", io.StringIO()), \
                 mock.patch("builtins.input", side_effect=AssertionError("unexpected prompt")), \
                 mock.patch.object(console, "_operation", side_effect=AssertionError("operation")):
                home.display({**self.view, "interactive_requested": interactive}, "ja", "skills")
            self.assertIn("合成作業", output.getvalue())

    def test_json_interactive_is_plain_readonly_json(self):
        with mock.patch.object(personal_skills, "stack", return_value=deepcopy(self.view)), \
             mock.patch("builtins.input", side_effect=AssertionError("JSON prompt")), \
             mock.patch.object(home, "display", side_effect=AssertionError("JSON menu")), \
             redirect_stdout(io.StringIO()) as output:
            code = main(["--project", str(self.root), "--json", "skills", "--interactive"])
        self.assertEqual(code, 0, output.getvalue())
        result = json.loads(output.getvalue())
        self.assertEqual(result["command"], "skills")
        self.assertFalse(result["writes"])
        self.assertTrue(result["interactive_requested"])

    def test_cli_releases_root_command_scope_before_input(self):
        active, entered = [], []
        @contextmanager
        def scope(root, configuration, args):
            active.append(args.command)
            entered.append(args.command)
            try:
                yield
            finally:
                active.pop()
        def answer(prompt):
            self.assertEqual(active, [], "input waited inside root command scope")
            return "0"
        with mock.patch("verantyx.authority.command_scope", side_effect=scope), \
             mock.patch.object(personal_skills, "stack", return_value=deepcopy(self.view)), \
             mock.patch("sys.stdin", Terminal()), redirect_stdout(Terminal()), \
             mock.patch("builtins.input", side_effect=answer):
            code = main(["--project", str(self.root), "skills", "--interactive"])
        self.assertEqual(code, 0)
        self.assertEqual(entered, ["skills"])

    def test_actual_synthetic_example_import_uses_nested_assisted_command(self):
        sample = Path(__file__).resolve().parents[1] / "examples/skills-small-work.txt"
        answers = ["1", str(sample), "synthetic-project", "synthetic-record", "external-fixture", "recorded-fixture", "0"]
        original = console._operation
        output, calls = self.menu(answers, operation=original)
        imported = next(call.args[2] for call in calls.call_args_list if call.args[2][0] == "skills-import")
        self.assertEqual(imported[imported.index("--mode") + 1], "assisted")
        self.assertNotIn("--creator-adapter", imported)
        result = personal_skills.stack(self.root, self.cfg)
        self.assertEqual(len(result["works"]), 1)
        self.assertIn("synthetic-record", result["works"][0]["label"])
        self.assertIn("候補生成は別操作", output)

    def test_all_ownership_targets_use_learn_target_with_bound_revision(self):
        for index, target in enumerate(home.TARGETS, 1):
            with self.subTest(target=target):
                _, calls = self.menu(["3", "1", "1", str(index), "synthetic reason", "0"])
                writes = [call.args[2] for call in calls.call_args_list if call.args[2][0] != "skills-stack"]
                self.assertEqual(len(writes), 1)
                argv = writes[0]
                self.assertEqual(argv[:2], ["learn-target", "synthetic-work"])
                self.assertEqual(argv[argv.index("--target") + 1], target)
                self.assertEqual(argv[argv.index("--candidate") + 1], "synthetic-skill")
                self.assertEqual(argv[argv.index("--expected-revision") + 1], "9")
                self.assertIn("--key", argv)

    def test_explanation_uses_existing_command_and_stays_self_report(self):
        with mock.patch.object(personal_skills, "explain", side_effect=AssertionError("direct mutation")):
            output, calls = self.menu(["4", "1", "1", "My synthetic explanation", "0"])
        argv = next(call.args[2] for call in calls.call_args_list if call.args[2][0] == "skills-explain")
        self.assertEqual(argv[argv.index("--statement") + 1], "My synthetic explanation")
        self.assertIn("自己申告", output)
        self.assertIn("習得認定は行いません", output)

    def test_unrecorded_suggestions_cannot_be_explained_without_selection(self):
        self.view["works"][0]["skills"][0]["recorded"] = False
        _, calls = self.menu(["4", "1", "0"])
        self.assertFalse(any(call.args[2][0] == "skills-explain" for call in calls.call_args_list))

    def test_build_requires_explicit_y_before_adapter_loading_or_dispatch(self):
        creator, reviewer = self.adapters()
        with mock.patch("verantyx.adapters.command_process.load_command", side_effect=AssertionError("unconfirmed adapter")):
            output, calls = self.menu(["2", "1", creator, reviewer, "n", "0"])
        self.assertFalse(any(call.args[2][0] == "skills-build" for call in calls.call_args_list))
        self.assertIn("開始しませんでした", output)

    def test_ok_true_fallback_is_incomplete_and_build_is_not_retried(self):
        creator, reviewer = self.adapters()
        def operation(root, locale, argv):
            if argv[0] == "skills-build":
                return {"ok": True, "command": "skills-build", "response_mode": "FALLBACK"}
            return self.result_for(root, locale, argv)
        with mock.patch("verantyx.adapters.command_process.load_command", side_effect=[
                {"codex_cli": {"role": "implementation"}}, {"codex_cli": {"role": "verification"}}]):
            output, calls = self.menu(["2", "1", creator, reviewer, "y", "0"], operation)
        self.assertEqual(sum(call.args[2][0] == "skills-build" for call in calls.call_args_list), 1)
        self.assertIn("未完了", output)
        self.assertIn("FALLBACK", output)
        self.assertNotIn("生成候補を記録しました", output)

    def test_unknown_build_error_is_not_automatically_retried(self):
        creator, reviewer = self.adapters()
        def operation(root, locale, argv):
            if argv[0] == "skills-build":
                raise LedgerError("BRIDGE_OUTCOME_UNKNOWN")
            return self.result_for(root, locale, argv)
        with mock.patch("verantyx.adapters.command_process.load_command", side_effect=[
                {"codex_cli": {"role": "implementation"}}, {"codex_cli": {"role": "verification"}}]):
            output, calls = self.menu(["2", "1", creator, reviewer, "y", "0"], operation)
        self.assertEqual(sum(call.args[2][0] == "skills-build" for call in calls.call_args_list), 1)
        self.assertIn("BRIDGE_OUTCOME_UNKNOWN", output)

    def test_local_model_adapter_is_rejected_before_build(self):
        creator, reviewer = self.adapters()
        with mock.patch("verantyx.adapters.command_process.load_command", return_value={"model_api": {"provider": "ollama"}}):
            output, calls = self.menu(["2", "1", creator, reviewer, "y", "0"])
        self.assertFalse(any(call.args[2][0] == "skills-build" for call in calls.call_args_list))
        self.assertIn("ローカルモデルは起動しません", output)

    def test_newsletter_uses_fresh_exact_work_scope_and_no_implicit_output(self):
        def operation(root, locale, argv):
            if argv[:2] == ["skills-stack", "--run"]:
                return {**deepcopy(self.view), "scope": {"id": "fresh-exact-scope"}}
            if argv[0] == "skills-newsletter":
                return {"ok": True, "command": "skills-newsletter", "draft": "# local draft", "published": False}
            return self.result_for(root, locale, argv)
        output, calls = self.menu(["5", "1", "Synthetic newsletter", "1", "", "0"], operation)
        argv = next(call.args[2] for call in calls.call_args_list if call.args[2][0] == "skills-newsletter")
        self.assertEqual(argv[argv.index("--scope-id") + 1], "fresh-exact-scope")
        self.assertEqual(argv[argv.index("--run") + 1], "synthetic-work")
        self.assertNotIn("--output", argv)
        self.assertIn("# local draft", output)

    def test_invalid_menu_choices_and_eof_are_inert(self):
        for answers in (["invalid", "99", "0"], [EOFError()]):
            with self.subTest(answers=str(answers)):
                _, calls = self.menu(answers)
                calls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
