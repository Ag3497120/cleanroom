"""Cache boundaries and native continuation, using synthetic transports only."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest import TestCase, mock
import uuid

from verantyx import claude_cli, codex_cli, model_api, model_usage, prompt_cache, subscription_cli
from verantyx.agent_schema import WORK_REQUEST, validate_output
from verantyx.domain.codec import canonical
from verantyx.errors import LedgerError
from verantyx.native_session import NativeSession, STATE_ENV, patch, snapshot


def request():
    return {"format": WORK_REQUEST, "run_id": "work-fixture", "request": "Read the provided file.",
            "generation_id": "one", "output_contract": "Return the specified work proposal.",
            "approved_files": ["fixture.py"], "tool_capabilities": {"tools": ["read_file"]},
            "project_context": {"source": "shared context " * 2000},
            "tool_receipts": [], "turns": [], "learning_sources": []}


DOCUMENT = {"format": "verantyx.work-proposal.v1", "status": "COMPLETE", "answer": "Synthetic result.",
            "tool_requests": [], "owner_question": "", "assumptions": [], "learning_notes": []}


class PromptCaching(TestCase):
    def test_base_prefix_and_routing_survive_new_task_and_changed_scope(self):
        first = request()
        changed = dict(first, run_id="different-task", request="A different question",
                       approved_files=["other.py"], project_context={"source": "changed"})
        before, first_marks = prompt_cache.fragments(first)
        after, second_marks = prompt_cache.fragments(changed)
        self.assertEqual(before[0], after[0])
        self.assertIn(0, first_marks)
        self.assertIn(0, second_marks)
        self.assertEqual(prompt_cache.cache_key(first), prompt_cache.cache_key(changed))
        self.assertNotIn("Read the provided", before[0])
        self.assertEqual(json.loads("".join(after)), changed)

    def test_fragments_are_lossless_for_missing_empty_and_grouped_receipts(self):
        for value in [{}, {"other": None}, request(), dict(request(), tool_receipts=None),
                      dict(request(), tool_receipts=[{"turn_index": i // 3, "text": str(i)} for i in range(12)])]:
            parts, boundaries = prompt_cache.fragments(value)
            self.assertEqual(json.loads("".join(parts)), value)
            self.assertLessEqual(len(boundaries), 4)
            self.assertNotIn(len(parts) - 1, boundaries)

    def test_generation_state_changes_do_not_invalidate_cached_prefix(self):
        first = request()
        first["tool_receipts"] = [{"turn_index": 0, "text": "large file " * 2000}]
        second = deepcopy(first)
        second.update(generation_id="two", candidate_manifest=[{"changed": True}])
        second["tool_receipts"].append({"turn_index": 1, "text": "new result"})
        before, positions = prompt_cache.fragments(first)
        after, _ = prompt_cache.fragments(second)
        boundary = max(positions)
        self.assertEqual(before[:boundary + 1], after[:boundary + 1])
        self.assertGreater(len("".join(before[:boundary + 1])) / len("".join(after)), .95)

    def api_config(self, provider, model):
        return {"provider": provider, "model": model, "max_output_tokens": 1024,
                "endpoint": "https://api.example.test/v1/responses"}

    def test_anthropic_caches_stable_content_not_volatile_tail(self):
        body = model_api.payload(self.api_config("anthropic", "claude-sonnet-4-6"), request())
        blocks = body["messages"][0]["content"]
        self.assertTrue(any("cache_control" in block for block in blocks))
        self.assertNotIn("cache_control", blocks[-1])
        self.assertEqual(json.loads("".join(block["text"] for block in blocks)), request())

    def test_openai_cache_fields_are_model_and_provider_compatible(self):
        for provider, model, explicit in [("openai", "gpt-5.6-sol", True), ("openai", "gpt-6-astra", True),
                                          ("openai", "gpt-5.5", False), ("openai_compatible", "gpt-6-astra", False)]:
            body = model_api.payload(self.api_config(provider, model), request())
            self.assertEqual("prompt_cache_options" in body, explicit)
            self.assertEqual("prompt_cache_key" in body, provider == "openai")
            self.assertFalse(body["store"])
            blocks = body["input"][0]["content"]
            self.assertEqual(any("prompt_cache_breakpoint" in block for block in blocks), explicit)
            self.assertNotIn("prompt_cache_breakpoint", blocks[-1])
            self.assertEqual(json.loads("".join(block["text"] for block in blocks)), request())

    def test_native_schema_stays_stable_when_source_identifiers_grow(self):
        first = request()
        second = dict(first, learning_sources=["source-1", "source-2"])
        one, schema_one = prompt_cache.native_contract(first)
        two, schema_two = prompt_cache.native_contract(second)
        self.assertEqual(schema_one, schema_two)
        self.assertNotIn("output_schema", one)
        self.assertEqual(two["learning_sources"], second["learning_sources"])
        with self.assertRaises(LedgerError):
            validate_output(second, dict(DOCUMENT, tool_requests=[{"id": "duplicate", "tool": "read_file", "path": "", "text": ""}] * 2))

    def test_patch_reconstructs_exact_request_and_is_smaller(self):
        first = request()
        second = deepcopy(first)
        second.update(generation_id="two", candidate_manifest=[{"path": "new.py"}])
        second["tool_receipts"].append({"turn_index": 0, "text": "new tool receipt"})
        delta = patch(snapshot(first), second)
        reconstructed = deepcopy(first)
        reconstructed.update(delta["replace"])
        for key, rows in delta["append"].items():
            reconstructed[key].extend(rows)
        self.assertEqual(reconstructed, second)
        self.assertLess(len(canonical(delta)), len(canonical(second)) // 20)

    def test_compaction_and_scope_changes_require_a_new_conversation(self):
        first = request()
        first["turns"] = [{"index": 0}, {"index": 1}]
        for change in [{"turns": []}, {"turns": [{"changed": True}]}, {"approved_files": []},
                       {"tool_capabilities": {"tools": []}}, {"attachments": [{"sha256": "new"}]}]:
            self.assertIsNone(patch(snapshot(first), dict(first, **change)))


class NativeContinuation(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        env = mock.patch.dict(os.environ, {STATE_ENV: str(self.root / ".transport")})
        env.start()
        self.addCleanup(env.stop)
        self.cfg = {"provider": "fixture", "model": "fixture", "timeout": 3}
        self.schema = {"type": "object"}
        self.thread = str(uuid.uuid4())

    def test_same_run_reuses_id_and_cwd_other_runs_do_not(self):
        first = request()
        with NativeSession(self.cfg, first, self.schema) as session:
            self.assertIsNone(session.resume_id)
            cwd = session.cwd
            session.thread_id = self.thread
            session.complete()
        with NativeSession(self.cfg, dict(first, generation_id="two"), self.schema) as session:
            self.assertEqual(session.resume_id, self.thread)
            self.assertEqual(session.cwd, cwd)
            self.assertTrue(session.prompt().startswith("REQUEST_PATCH\n"))
            session.thread_id = self.thread
            session.complete()
        with NativeSession(self.cfg, dict(first, run_id="different"), self.schema) as session:
            self.assertIsNone(session.resume_id)
            self.assertEqual(session.cwd, cwd)
        self.assertFalse(cwd.is_relative_to(self.root))

    def test_interrupted_conversation_is_not_resumed(self):
        with NativeSession(self.cfg, request(), self.schema) as session:
            session.thread_id = self.thread
        with NativeSession(self.cfg, dict(request(), generation_id="next"), self.schema) as session:
            self.assertIsNone(session.resume_id)

    def test_configuration_and_schema_changes_start_fresh(self):
        with NativeSession(self.cfg, request(), self.schema) as session:
            session.thread_id = self.thread
            session.complete()
        with NativeSession(dict(self.cfg, model="changed"), request(), self.schema) as session:
            self.assertIsNone(session.resume_id)
        with NativeSession(self.cfg, request(), {"type": "string"}) as session:
            self.assertIsNone(session.resume_id)

    def test_updated_instructions_do_not_resume_old_native_context(self):
        with NativeSession(self.cfg, request(), self.schema, "old instructions") as session:
            session.thread_id = self.thread
            session.complete()
        with NativeSession(self.cfg, request(), self.schema, "new instructions") as session:
            self.assertIsNone(session.resume_id)

    def test_state_retains_hashes_not_prompt_text(self):
        with NativeSession(self.cfg, request(), self.schema) as session:
            session.thread_id = self.thread
            session.complete()
            saved = session.path.read_text()
            self.assertNotIn("shared context", saved)
            self.assertNotIn("Read the provided file", saved)

    def test_real_codex_protocol_resumes_with_delta_without_native_tools(self):
        executable = self.root / "fake-codex"
        log = self.root / "calls.jsonl"
        executable.write_text(f'''#!{sys.executable}
import json,sys,os
text=sys.stdin.read()
with open({str(log)!r}, 'a') as f:
    f.write(json.dumps({{'argv':sys.argv[1:],'cwd':os.getcwd(),'prompt':text}})+'\\n')
for row in [{{'type':'thread.started','thread_id':{self.thread!r}}},{{'type':'turn.started'}},
            {{'type':'item.completed','item':{{'type':'agent_message','text':json.dumps({{'document':{DOCUMENT!r}}})}}}},
            {{'type':'turn.completed','usage':{{'input_tokens':100,'cached_input_tokens':50,'output_tokens':10}}}}]:
    print(json.dumps(row),flush=True)
''')
        executable.chmod(0o700)
        cfg = codex_cli.configuration(self.root, "implementation", executable=str(executable))
        cfg["timeout"] = 5
        first = request()
        self.assertEqual(codex_cli._invoke(cfg, first, lambda usage: None), DOCUMENT)
        self.assertEqual(codex_cli._invoke(cfg, dict(first, generation_id="two"), lambda usage: None), DOCUMENT)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertNotIn("resume", calls[0]["argv"])
        self.assertIn("resume", calls[1]["argv"])
        self.assertIn(self.thread, calls[1]["argv"])
        self.assertEqual(calls[0]["cwd"], calls[1]["cwd"])
        self.assertIn('features.shell_tool=false', calls[1]["argv"])
        self.assertIn('sandbox_mode="read-only"', calls[1]["argv"])
        self.assertNotIn("--ephemeral", calls[0]["argv"])
        self.assertLess(len(calls[1]["prompt"]), len(calls[0]["prompt"]) // 20)

    def test_claude_continuation_keeps_restrictions_and_only_sends_delta(self):
        cfg = claude_cli.configuration("/fake/claude")
        result = {"type": "result", "subtype": "success", "session_id": self.thread,
                  "structured_output": {"document": DOCUMENT}, "usage": {}}
        with mock.patch.object(claude_cli, "status", return_value={"subscription_login": True}), \
                mock.patch.object(claude_cli, "_exchange", return_value=result) as exchange, \
                mock.patch("uuid.uuid4", return_value=uuid.UUID(self.thread)):
            claude_cli.request(cfg, request())
            claude_cli.request(cfg, dict(request(), generation_id="two"))
        first, second = exchange.call_args_list
        self.assertIn("--session-id", first.args[0])
        self.assertIn("--resume", second.args[0])
        self.assertIn(self.thread, second.args[0])
        for flag in ("--safe-mode", "--restricted", "--strict-mcp-config", "--tools", "--system-prompt-snapshot"):
            self.assertIn(flag, second.args[0])
        self.assertEqual(first.kwargs["cwd"], second.kwargs["cwd"])
        self.assertLess(len(second.args[1]), len(first.args[1]) // 20)

    def test_claude_rejects_a_mismatched_session_and_does_not_resume_it(self):
        cfg = claude_cli.configuration("/fake/claude")
        result = {"type": "result", "subtype": "success", "session_id": "wrong-session",
                  "structured_output": {"document": DOCUMENT}, "usage": {}}
        with mock.patch.object(claude_cli, "status", return_value={"subscription_login": True}), \
                mock.patch.object(claude_cli, "_exchange", return_value=result) as exchange:
            for value in (request(), dict(request(), generation_id="two")):
                with self.assertRaises(LedgerError) as failure:
                    claude_cli.request(cfg, value)
                self.assertEqual(failure.exception.details["reason"], "CLAUDE_SESSION_MISMATCH")
            for call in exchange.call_args_list:
                self.assertNotIn("--resume", call.args[0])


class NativeCompatibility(TestCase):
    def test_old_claude_never_receives_an_unknown_auth_subcommand(self):
        old_help = SimpleNamespace(returncode=0, stdout=b"Usage: claude [prompt] --help", stderr=b"")
        with mock.patch.object(subscription_cli.subprocess, "run", return_value=old_help) as run:
            self.assertEqual(subscription_cli.status("claude", "/fake/claude")["state"], "UPDATE_REQUIRED")
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["/fake/claude", "--help"])

    def test_current_claude_auth_check_does_not_generate_a_response(self):
        help_result = SimpleNamespace(returncode=0, stdout=b"--safe-mode --restricted --system-prompt-snapshot", stderr=b"")
        auth_result = SimpleNamespace(returncode=0, stdout=b'{"loggedIn":true,"authMethod":"claude.ai"}', stderr=b"")
        with mock.patch.object(subscription_cli.subprocess, "run", side_effect=[help_result, auth_result]) as run:
            self.assertTrue(subscription_cli.status("claude", "/fake/claude")["subscription_login"])
        self.assertEqual(run.call_args.args[0], ["/fake/claude", "auth", "status"])


class UsageCounters(TestCase):
    def test_claude_input_total_includes_read_and_write_only_once(self):
        tokens = model_usage.normalize("anthropic", {"usage": {"input_tokens": 10,
            "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 100, "output_tokens": 25}})
        self.assertEqual(tokens["input_tokens"], 1110)
        self.assertEqual(tokens["cached_input_tokens"], 1000)
        self.assertEqual(tokens["cache_write_input_tokens"], 100)

    def test_missing_counters_are_not_invented_as_zero(self):
        self.assertEqual(model_usage.normalize("openai", {}), {})
        self.assertEqual(model_usage.normalize("openai", {"usage": {"input_tokens": 50}}), {"input_tokens": 50})
        self.assertNotIn("input_tokens", model_usage.normalize("anthropic", {"usage": {"input_tokens": 50}}))

    def test_usage_persists_only_metrics_and_reading_does_not_create_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.assertEqual(model_usage.summary(root)["calls"], 0)
            self.assertFalse((root / ".verantyx").exists())
            directory = root / ".verantyx/model-adapters/fixture/.transport"
            with mock.patch.dict(os.environ, {STATE_ENV: str(directory)}):
                model_usage.publish({"provider": "openai", "model": "fixture"}, request(),
                    tokens={"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 10}, observer=lambda event: None)
                model_usage.publish({"provider": "openai", "model": "fixture"}, request(),
                    tokens={"input_tokens": 50}, observer=lambda event: None)
            stats = model_usage.summary(root)
            self.assertEqual(stats["calls"], 2)
            self.assertEqual(stats["cache_measured_calls"], 1)
            self.assertEqual(stats["cached_input_ratio"], .8)
            self.assertNotIn(b"Read the provided file", (directory / "usage.sqlite3").read_bytes())
