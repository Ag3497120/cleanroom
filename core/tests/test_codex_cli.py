"""Deterministic artificial adapters only. Never launch the installed Codex."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from verantyx import codex_budget, codex_cli, commands_codex
from verantyx.adapters.command_process import BoundedProcess
from verantyx.domain.codec import canonical, decode, digest
from verantyx.errors import LedgerError

REQUEST = {"format": "verantyx.proposal-request.v1", "task": {"task_id": "fixture", "context_revision": 1,
           "request": "Artificial answer"}, "proposal_schema": {"malicious": "not used as validation authority"}}
DOCUMENT = {"schema_version": 1, "task_id": "fixture", "context_revision": 1, "response_locale": "en",
            "summary": "Artificial answer", "claims": [], "actions": [], "unknowns": []}
TOKENS = {"input_tokens": 13, "cached_input_tokens": 4, "output_tokens": 7}


class CodexCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="verantyx-codex-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.created = commands_codex.create_configs(self.root / "session")
        self.configs = {role: codex_cli.load_config(path) for role, path in self.created["adapters"].items()}
        for value in self.configs.values():
            value.update(model="gpt-5.3-codex-spark", reasoning_effort="low")
        self.cfg = self.configs["implementation"]
        # Every test fails closed if it accidentally reaches the real launcher.
        self.guard = mock.patch("verantyx.codex_cli._invoke", side_effect=AssertionError("real model forbidden"))
        self.launcher = self.guard.start()
        self.addCleanup(self.guard.stop)

    def successful(self, config, value, on_usage):
        on_usage(TOKENS)
        return deepcopy(DOCUMENT)

    def usage(self):
        return codex_budget.usage(self.cfg["budget_directory"])

    def assert_reason(self, reason, function, *args, **kwargs):
        with self.assertRaises(LedgerError) as error:
            function(*args, **kwargs)
        self.assertEqual(error.exception.details.get("reason"), reason)

    def test_two_roles_keep_receipts_and_exact_cache_costs_zero_calls_without_a_generation_cap(self):
        self.launcher.side_effect = self.successful
        for role in codex_cli.ROLES:
            for version in range(2):
                value = {**REQUEST, "artificial_version": version}
                self.assertEqual(codex_cli.request(self.configs[role], value), DOCUMENT)
        self.assertEqual(self.launcher.call_count, 4)
        before = self.usage()
        self.assertEqual(before["calls_by_role"], {"implementation": 2, "verification": 2})
        self.assertIsNone(before["calls_remaining"])
        self.assertEqual(before["provider_reported_tokens"]["input_tokens"], 52)
        self.assertEqual(codex_cli.request(self.cfg, {**REQUEST, "artificial_version": 0}), DOCUMENT)
        self.assertEqual(self.usage(), before)
        self.assertEqual(self.launcher.call_count, 4)
        self.assertEqual(codex_cli.request(self.cfg, REQUEST), DOCUMENT)
        self.assertEqual(self.launcher.call_count, 5)

    def test_changed_input_role_or_configuration_misses_cache(self):
        self.launcher.side_effect = self.successful
        codex_cli.request(self.cfg, REQUEST)
        codex_cli.request(self.cfg, {**REQUEST, "changed": True})
        codex_cli.request(self.configs["verification"], REQUEST)
        codex_cli.request({**self.cfg, "timeout": 121}, REQUEST)
        self.assertEqual(self.launcher.call_count, 4)
        self.assertEqual(len({row["config_sha256"] for row in self.usage()["calls"]}), 3)

    def test_transactional_reservation_does_not_multiply_cap_under_fanout(self):
        def reserve(index):
            try:
                return codex_budget.reserve(self.configs[codex_cli.ROLES[index % 2]],
                                            {**REQUEST, "parallel": index})["status"]
            except LedgerError as error:
                return error.details["reason"]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(reserve, range(8)))
        self.assertEqual(results.count("IN_FLIGHT"), 8)
        self.assertEqual(self.usage()["calls_reserved"], 8)
        self.launcher.assert_not_called()

    def test_in_flight_and_interrupted_calls_are_never_retried(self):
        codex_budget.reserve(self.cfg, REQUEST)
        self.assert_reason("CODEX_REQUEST_ALREADY_RESERVED", codex_cli.request, self.cfg, REQUEST)
        self.launcher.assert_not_called()
        def interrupted(config, value, on_usage):
            on_usage(TOKENS)
            raise KeyboardInterrupt()
        self.launcher.side_effect = interrupted
        with self.assertRaises(KeyboardInterrupt):
            codex_cli.request(self.configs["verification"], REQUEST)
        self.assert_reason("CODEX_REQUEST_ALREADY_RESERVED", codex_cli.request,
                           self.configs["verification"], REQUEST)
        rows = self.usage()["calls"]
        self.assertEqual([row["status"] for row in rows], ["IN_FLIGHT", "UNKNOWN"])
        self.assertEqual(rows[1]["provider_reported_tokens"], TOKENS)
        self.assertEqual(self.launcher.call_count, 1)

    def test_failed_launch_and_invalid_output_consume_calls_without_cache_or_retry(self):
        self.launcher.side_effect = FileNotFoundError("artificial missing executable")
        with self.assertRaises(LedgerError):
            codex_cli.request(self.cfg, REQUEST)
        self.assertEqual(self.usage()["calls"][0]["status"], "FAILED")
        self.assert_reason("CODEX_REQUEST_ALREADY_RESERVED", codex_cli.request, self.cfg, REQUEST)
        self.launcher.side_effect = lambda *args: {**DOCUMENT, "approved": True}
        with self.assertRaises(LedgerError):
            codex_cli.request(self.configs["verification"], REQUEST)
        self.assertEqual([row["status"] for row in self.usage()["calls"]], ["FAILED", "FAILED"])
        self.assertEqual(self.launcher.call_count, 2)

    def test_cache_rechecks_hash_and_current_contract_without_launch(self):
        self.launcher.side_effect = self.successful
        codex_cli.request(self.cfg, REQUEST)
        path = Path(self.cfg["budget_directory"]) / codex_budget.DB_NAME
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE calls SET output_sha256=?", ("0" * 64,))
        self.assert_reason("CODEX_CACHE_HASH", codex_cli.request, self.cfg, REQUEST)
        invalid = {**DOCUMENT, "task_id": "different-task"}
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE calls SET output_json=?,output_sha256=?", (canonical(invalid), digest(invalid)))
        with self.assertRaises(LedgerError):
            codex_cli.request(self.cfg, REQUEST)
        self.assertEqual(self.launcher.call_count, 1)
        self.assertEqual(self.usage()["calls_reserved"], 1)

    def test_configuration_cannot_replace_model_auth_and_legacy_cap_is_not_an_execution_limit(self):
        for field, replacement in (("provider", "openai"), ("role", "unbounded"),
                                   ("reasoning_effort", "invalid"), ("model", "../invalid")):
            with self.assertRaises(LedgerError):
                codex_cli.validate_config({**self.cfg, field: replacement})
        with self.assertRaises(LedgerError):
            codex_cli.validate_config({**self.cfg, "key_env": "OPENAI_API_KEY"})
        self.assertEqual(codex_cli.validate_config({**self.cfg, "model": "another-model", "reasoning_effort": "high"})["model"], "another-model")
        self.launcher.side_effect = self.successful
        self.assertEqual(codex_cli.request({**self.cfg, "max_calls": 9}, REQUEST), DOCUMENT)
        self.assertEqual(self.usage()["calls_reserved"], 1)
        self.assertEqual(self.launcher.call_count, 1)

    def test_ignore_user_config_is_an_exec_option_in_exact_argv_position(self):
        argv = codex_cli._argv(self.cfg, "/artificial/envelope.json")
        self.assertEqual(argv[:3], [self.cfg["executable"], "exec", "--ignore-user-config"])
        self.assertEqual(argv.count("exec"), 1)
        self.assertGreater(argv.index("-c"), argv.index("--ignore-user-config"))
        self.assertEqual(argv[argv.index("--model") + 1], "gpt-5.3-codex-spark")
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
        self.assertFalse(any(part.startswith("model_providers.openai.") for part in argv))

    def test_config_command_and_read_only_usage_json_text_no_models(self):
        parser = argparse.ArgumentParser()
        commands_codex.register(parser.add_subparsers(dest="command"))
        target = self.root / "other-session"
        args = parser.parse_args(["codex-config", "--directory", str(target), "--max-calls", "2"])
        result = commands_codex.dispatch(self.root, {}, args, "en")
        self.assertIsNone(result["budget"]["max_calls"])
        self.assertEqual(set(result["adapters"]), set(codex_cli.ROLES))
        before = {str(path): path.read_bytes() for path in target.rglob("*") if path.is_file()}
        with mock.patch("subprocess.Popen", side_effect=AssertionError("no model")), \
             mock.patch("socket.socket", side_effect=AssertionError("no network")):
            args = parser.parse_args(["codex-usage", "--directory", str(target)])
            result = commands_codex.dispatch(self.root, {}, args, "en")
            output = StringIO()
            with redirect_stdout(output):
                commands_codex.display(result, "en", "codex-usage")
            self.assertIn("Recorded calls: 0", output.getvalue())
            self.assertIn("generation limits are disabled", output.getvalue())
            self.assertFalse(json.loads(canonical(result))["budget"]["token_or_cost_hard_limit"])
        self.assertEqual(before, {str(path): path.read_bytes() for path in target.rglob("*") if path.is_file()})
        with self.assertRaises(LedgerError):
            commands_codex.create_configs(target)
        self.assertEqual(before, {str(path): path.read_bytes() for path in target.rglob("*") if path.is_file()})
        self.launcher.assert_not_called()

    def test_no_overwrites_and_missing_budget_does_not_create_or_reset(self):
        target = self.root / "occupied"
        target.mkdir()
        existing = target / "implementation.json"
        existing.write_text("artificial preexisting file")
        with self.assertRaises(LedgerError):
            commands_codex.create_configs(target)
        self.assertEqual(existing.read_text(), "artificial preexisting file")
        self.assertFalse((target / "budget").exists())
        missing = self.root / "missing-budget"
        with self.assertRaises(LedgerError):
            codex_budget.usage(missing)
        self.assertFalse(missing.exists())
        self.launcher.assert_not_called()

    def test_input_bound_checked_before_reservation(self):
        with self.assertRaises(LedgerError):
            codex_cli.request({**self.cfg, "max_input_bytes": 1024}, {**REQUEST, "large": "x" * 2048})
        self.assertEqual(self.usage()["calls_reserved"], 0)
        self.launcher.assert_not_called()

    def test_real_response_validator_and_all_format_routes(self):
        template = {"schema_version": 1, "task_id": "fixture", "basis_revision": 1, "response_locale": "en",
                    "norms_sha256": "a" * 64, "answer": "A generated artificial response",
                    "explanations": [], "learning_candidates": [], "reusable_candidates": []}
        value = {"format": "verantyx.response-request.v1", "response_template": template,
                 "allowed_source_refs": [], "max_learning_items": 0}
        self.launcher.side_effect = lambda *args: deepcopy(template)
        self.assertEqual(codex_cli.request(self.cfg, value), template)
        for format_name in codex_cli.REQUEST_FORMATS:
            request = {"format": format_name, "context": {}, "max_checks": 1}
            with mock.patch("verantyx.codex_cli._validate_output", return_value=DOCUMENT) as validator, \
                 mock.patch("verantyx.domain.asset_workflow.compile_document") as compiler:
                self.assertEqual(codex_cli._validated(request, DOCUMENT, 262144), DOCUMENT)
                validator.assert_called_once_with(request, DOCUMENT)
                self.assertEqual(compiler.call_count, int(format_name == "verantyx.asset-workflow-request.v1"))

    def fake_executable(self, *, scenario="success"):
        # Local deterministic stand-in, not a wrapper around any installed model.
        executable = self.root / ("fake-codex-" + scenario)
        executable.write_text("#!" + sys.executable + "\n" + """
import json, os, sys, time
from pathlib import Path
args = sys.argv[1:]
assert args[:2] == ['exec', '--ignore-user-config']
assert args[args.index('--model') + 1] == 'gpt-5.3-codex-spark'
assert args[args.index('--sandbox') + 1] == 'read-only'
assert 'forced_login_method=\"chatgpt\"' in args
assert 'model_reasoning_effort=\"low\"' in args
assert 'features.shell_tool=false' in args and 'web_search=\"disabled\"' in args
assert not any(part.startswith('model_providers.openai.') for part in args)
assert '--ephemeral' in args and '--skip-git-repo-check' in args
assert not list(Path.cwd().iterdir())
assert 'OPENAI_API_KEY' not in os.environ and 'CODEX_API_KEY' not in os.environ
schema = json.loads(Path(args[args.index('--output-schema') + 1]).read_text())
assert schema['required'] == ['document'] and schema['additionalProperties'] is False
request = json.loads(sys.stdin.read().split('REQUEST_JSON\\n', 1)[1])
""" + "scenario = " + repr(scenario) + "\n" + "document = " + repr(DOCUMENT) + "\n" + """
if scenario == 'timeout':
    time.sleep(5)
elif scenario == 'overflow':
    sys.stdout.write('x' * 10000)
elif scenario == 'parser':
    print("error: unexpected argument '--fixture' found PRIVATE_STDERR_MARKER", file=sys.stderr)
    sys.exit(2)
else:
    print(json.dumps({'type': 'thread.started', 'thread_id': 'artificial'}))
    print(json.dumps({'type': 'turn.started'}))
    if scenario == 'tool':
        print(json.dumps({'type': 'item.started', 'item': {'type': 'command_execution'}}))
    else:
        print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message',
              'text': json.dumps({'document': json.dumps(document)})}}))
        if scenario != 'incomplete':
            print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 13, 'output_tokens': 7}}))
""")
        executable.chmod(0o700)
        return executable

    def test_actual_bounded_stdio_process_returns_only_validated_json_and_cached_result(self):
        executable = self.fake_executable()
        configuration = {**self.cfg, "executable": str(executable)}
        path = self.root / "fake-config.json"
        path.write_text(canonical(configuration))
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "ARTIFICIAL_SECRET", "CODEX_API_KEY": "ARTIFICIAL_SECRET"}):
            command = codex_cli.command_for(path, configuration)
        self.assertEqual(command["codex_cli"]["provider"], "chatgpt_codex")
        self.assertNotIn("ARTIFICIAL_SECRET", canonical(command))
        for _ in range(2):
            with BoundedProcess(command, timeout=10) as process:
                raw = process.document(REQUEST)
            self.assertEqual(decode(raw), DOCUMENT)
        self.assertEqual(self.usage()["calls_reserved"], 1)
        self.assertEqual(self.usage()["provider_reported_tokens"], {"input_tokens": 13, "output_tokens": 7})

    def test_fake_process_rejects_tools_incomplete_output_overflow_and_timeout(self):
        # Exercise the real bounded transport with artificial executables only.
        self.guard.stop()
        for scenario, code in (("tool", "BRIDGE_PROTOCOL"), ("incomplete", "BRIDGE_OUTCOME_UNKNOWN"),
                               ("overflow", "BRIDGE_OUTPUT_LIMIT"), ("timeout", "BRIDGE_TIMEOUT")):
            cfg = {**self.cfg, "executable": str(self.fake_executable(scenario=scenario)),
                   "timeout": 1, "max_response_bytes": 1024}
            with self.assertRaises(LedgerError) as error:
                codex_cli.request(cfg, REQUEST)
            self.assertEqual(error.exception.code, code)
        self.assertEqual(self.usage()["calls_reserved"], 4)
        self.assertTrue(all(row["status"] != "SUCCEEDED" for row in self.usage()["calls"]))

    def test_config_hash_is_checked_by_worker_before_launch(self):
        path = self.root / "stale-config.json"
        configuration = {**self.cfg, "executable": str(self.fake_executable())}
        path.write_text(canonical(configuration))
        command = codex_cli.command_for(path, configuration)
        path.write_text(canonical({**configuration, "timeout": 121}))
        with self.assertRaises(LedgerError):
            with BoundedProcess(command, timeout=10) as process:
                process.document(REQUEST)
        self.assertEqual(self.usage()["calls_reserved"], 0)

    def test_parser_failure_keeps_closed_diagnostic_without_exposing_stderr(self):
        cfg = {**self.cfg, "executable": str(self.fake_executable(scenario="parser"))}
        path = self.root / "parser-config.json"
        path.write_text(canonical(cfg))
        command = codex_cli.command_for(path, cfg)
        process = subprocess.run(command["argv"], input=canonical(REQUEST), capture_output=True,
                                 text=True, env=command["env"], cwd=self.root, timeout=10)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(process.stdout, "")
        from verantyx.model_observation import parse
        self.assertEqual(parse(process.stderr.strip().encode()), {"kind": "error", "code": "BRIDGE_PROCESS_FAILED",
                         "details": {"reason": "CODEX_CLI_ARGUMENTS"}})
        self.assertNotIn("PRIVATE_STDERR_MARKER", process.stderr)
        receipt = self.usage()["calls"][0]
        self.assertEqual(receipt["status"], "FAILED")
        self.assertEqual(receipt["error_code"], "CODEX_CLI_ARGUMENTS")
        self.assert_reason("CODEX_REQUEST_ALREADY_RESERVED", codex_cli.request, cfg, REQUEST)
        self.assertEqual(self.usage()["calls_reserved"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
