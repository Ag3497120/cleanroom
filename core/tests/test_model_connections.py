"""Real local HTTP, stdio, queue and CLI paths; no live model or production memory."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import threading
import unittest
from unittest import mock

from test_constitution import Fixture
from verantyx.adapters.command_process import load_command
from verantyx.application import get_projection
from verantyx.bridges import _input, propose
from verantyx.connections_v05 import configure_model, check_model
from verantyx.domain.codec import canonical
from verantyx.errors import LedgerError
from verantyx.jobs import submit, run_job
from verantyx.model_api import FORMAT, request, validate_config, response_text
from verantyx.storage.sqlite import EventStore


class HTTPFixture:
    def __init__(self):
        self.calls = []
        self.mode = "normal"
        fixture = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fixture.calls.append({"path": self.path, "headers": dict(self.headers), "body": body})
                if "messages" in body:
                    provider, value = "anthropic", json.loads(body["messages"][0]["content"])
                elif "contents" in body:
                    provider, value = "gemini", json.loads(body["contents"][0]["parts"][0]["text"])
                elif "input" in body:
                    provider, value = "openai", json.loads(body["input"])
                else:
                    provider, value = "ollama", json.loads(body["prompt"])
                result = deepcopy(value.get("proposal_template", value.get("response_template")))
                if fixture.mode == "self_approve":
                    result["approved"] = True
                if fixture.mode == "stale":
                    result["context_revision"] += 1
                if fixture.mode == "secret":
                    result["summary"] = self.headers.get("Authorization", "fixture-credential-never-store").removeprefix("Bearer ")
                if fixture.mode == "tool":
                    result["actions"] = [{"id": "grant", "tool_id": "authority.grant", "arguments": {}, "reason": "bad", "source_refs": []}]
                text = canonical(result)
                response = {
                    "openai": {"object": "response", "status": "completed", "incomplete_details": None, "output": [
                        {"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": text}]}]},
                    "anthropic": {"type": "message", "role": "assistant", "stop_reason": "end_turn", "content": [{"type": "text", "text": text}]},
                    "gemini": {"candidates": [{"finishReason": "STOP", "content": {"role": "model", "parts": [{"text": text}]}}]},
                    "ollama": {"response": text, "done": True, "done_reason": "stop"},
                }[provider]
                if fixture.mode == "incomplete":
                    if provider == "openai":
                        response["status"] = "incomplete"
                    elif provider == "anthropic":
                        response["stop_reason"] = "max_tokens"
                    elif provider == "gemini":
                        response["candidates"][0]["finishReason"] = "MAX_TOKENS"
                    else:
                        response["done"] = False
                if fixture.mode == "slow":
                    threading.Event().wait(2)
                if fixture.mode == "redirect":
                    self.send_response(307)
                    self.send_header("Location", "http://127.0.0.1:1/credential-theft")
                    self.end_headers()
                    return
                raw = canonical(response).encode()
                if fixture.mode == "invalid_json":
                    raw = b'{"error": "fixture-credential-never-store", "error": 1}'
                self.send_response(503 if fixture.mode == "http_error" else 200)
                self.send_header("Content-Type", "text/plain" if fixture.mode == "content_type" else "application/json")
                self.send_header("Content-Length", str(len(raw) + (5000000 if fixture.mode == "oversize" else 1 if fixture.mode == "truncated_body" else 0)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def configuration(self, provider):
        path = {"openai": "/v1/responses", "anthropic": "/v1/messages", "gemini": "/v1beta/models/fixture-model:generateContent",
                "ollama": "/api/generate"}[provider]
        return {"format": FORMAT, "provider": provider, "model": "fixture-model",
                "endpoint": "http://127.0.0.1:" + str(self.server.server_port) + path,
                "key_env": "VERANTYX_FIXTURE_MODEL_KEY" if provider != "ollama" else None,
                "allow_loopback_http": True, "timeout": 2, "max_output_tokens": 4096, "max_response_bytes": 262144}

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class ModelConnectionTests(Fixture):
    def setUp(self):
        super().setUp()
        self.http = HTTPFixture()
        self.environment = mock.patch.dict(os.environ, {"VERANTYX_FIXTURE_MODEL_KEY": "fixture-credential-never-store"})
        self.environment.start()
        self.revision = self.run_task("task")["recorded_revision"]
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            self.input = _input(self.root, store, "task", "ja", [])[0]

    def tearDown(self):
        self.environment.stop()
        self.http.close()
        super().tearDown()

    def adapter(self, provider="openai"):
        path = self.root / (provider + ".json")
        path.write_text(canonical(self.http.configuration(provider)))
        return path

    def test_four_provider_http_payloads_and_completion_contracts(self):
        for provider in ("openai", "anthropic", "gemini", "ollama"):
            with self.subTest(provider=provider):
                result = request(self.http.configuration(provider), self.input)
                self.assertEqual(result, self.input["proposal_template"])
                call = self.http.calls[-1]
                self.assertNotIn("fixture-credential-never-store", canonical(call["body"]))
                self.assertNotIn("fixture-credential-never-store", call["path"])
        self.assertEqual(self.http.calls[0]["headers"]["Authorization"], "Bearer fixture-credential-never-store")
        self.assertFalse(self.http.calls[0]["body"]["store"])
        self.assertEqual(self.http.calls[1]["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(self.http.calls[2]["body"]["generationConfig"]["candidateCount"], 1)
        self.assertFalse(self.http.calls[3]["body"]["stream"])

    def test_each_provider_rejects_incomplete_output_without_retry(self):
        self.http.mode = "incomplete"
        for provider in ("openai", "anthropic", "gemini", "ollama"):
            with self.subTest(provider=provider):
                before = len(self.http.calls)
                with self.assertRaises(LedgerError):
                    request(self.http.configuration(provider), self.input)
                self.assertEqual(len(self.http.calls), before + 1)

    def test_unsafe_tls_endpoints_and_configuration_types_are_rejected(self):
        base = self.http.configuration("openai")
        changes = [{"allow_loopback_http": False}, {"allow_loopback_http": 1}, {"timeout": True},
                   {"key_env": "HOME"}, {"key_env": "PYTHONPATH"}, {"model": "model\nheader"},
                   {"endpoint": "http://localhost:11434/v1/responses"}, {"endpoint": "http://192.0.2.1/v1/responses"},
                   {"endpoint": "https://user:secret@example.test/v1/responses"},
                   {"endpoint": "https://example.test/v1/responses?key=secret"},
                   {"endpoint": "https://example.test/v1/responses#fragment"}, {"api_key": "must not accept"}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(LedgerError):
                validate_config({**base, **change})
        self.assertEqual(self.http.calls, [])

    def test_model_config_check_and_queue_do_not_read_credentials(self):
        path = self.adapter()
        os.environ.pop("VERANTYX_FIXTURE_MODEL_KEY")
        self.assertFalse(check_model(path)["credentials_read"])
        command = load_command(path)
        self.assertNotIn("VERANTYX_FIXTURE_MODEL_KEY", command["env"])
        submit(self.root, self.cfg, "task", adapter_path=path, key="queued-api", expected_revision=self.revision, clock=self.clock)
        os.environ["VERANTYX_FIXTURE_MODEL_KEY"] = "fixture-credential-never-store"
        self.assertEqual(command["identity"], load_command(path)["identity"])
        completed = run_job(self.root, self.cfg, "queued-api", clock=self.clock)
        self.assertEqual(completed["status"], "COMPLETED", completed)
        self.assertEqual(run_job(self.root, self.cfg, "queued-api", clock=self.clock)["status"], "COMPLETED")
        self.assertEqual(len(self.http.calls), 1)
        for file in (self.root / ".verantyx/bridges").glob("*.json"):
            self.assertNotIn("fixture-credential-never-store", file.read_text())

    def test_missing_credential_prevents_network_call(self):
        os.environ.pop("VERANTYX_FIXTURE_MODEL_KEY")
        with self.assertRaises(LedgerError):
            request(self.http.configuration("openai"), self.input)
        self.assertEqual(self.http.calls, [])

    def test_json_escaped_credential_echo_is_also_quarantined(self):
        self.http.mode = "secret"
        for secret in ('synthetic-quote"slash\\secret', 'synthetic-backslash\\secret'):
            with self.subTest(secret_format="escaped"), mock.patch.dict(os.environ, {"VERANTYX_FIXTURE_MODEL_KEY": secret}):
                with self.assertRaises(LedgerError) as error:
                    request(self.http.configuration("openai"), self.input)
                self.assertEqual(error.exception.code, "BRIDGE_PROTOCOL")
                self.assertNotIn(secret, str(error.exception))

    def test_real_propose_stdout_path_for_each_provider(self):
        for provider in ("openai", "anthropic", "gemini", "ollama"):
            with self.subTest(provider=provider):
                task = "task-" + provider
                revision = self.run_task(task)["recorded_revision"]
                result = propose(self.root, self.cfg, task, adapter_path=self.adapter(provider), key=provider,
                                 expected_revision=revision)
                self.assertTrue(result["ok"])
                with EventStore(self.root, self.cfg["project"]["id"]) as store:
                    types = [e["type"] for e in store.events(task)]
                self.assertEqual(types.count("ProposalRecorded"), 2)
                self.assertNotIn("HumanDecisionRecorded", types)
                self.assertNotIn("EffectAuthorized", types)

    def test_network_protocol_and_proposal_failures_are_not_repeated(self):
        for mode in ("redirect", "http_error", "content_type", "oversize", "truncated_body", "invalid_json", "secret", "self_approve", "tool", "stale"):
            with self.subTest(mode=mode):
                self.http.mode = mode
                before = len(self.http.calls)
                for _ in range(2):
                    with self.assertRaises(LedgerError):
                        propose(self.root, self.cfg, "task", adapter_path=self.adapter(), key=mode, expected_revision=self.revision)
                self.assertEqual(len(self.http.calls), before + 1)
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            self.assertNotIn("fixture-credential-never-store", store.export())

    def test_process_wall_timeout_is_not_retried(self):
        self.http.mode = "slow"
        path = self.adapter()
        for _ in range(2):
            with self.assertRaises(LedgerError) as error:
                propose(self.root, self.cfg, "task", adapter_path=path, key="timeout", expected_revision=self.revision, timeout=1)
            self.assertEqual(error.exception.code, "BRIDGE_TIMEOUT")
        self.assertEqual(len(self.http.calls), 1)

    def test_cli_config_propose_and_five_language_displays(self):
        adapter = self.root / "cli-model.json"
        source = str(Path(__file__).resolve().parents[1] / "src")
        env = {**os.environ, "PYTHONPATH": source}
        config = self.http.configuration("ollama")
        base = [sys.executable, "-m", "verantyx", "--project", str(self.root)]
        configured = subprocess.run([*base, "--json", "model-api-config", "--provider", "ollama", "--model", config["model"],
                                     "--endpoint", config["endpoint"], "--output", str(adapter), "--allow-loopback-http"], env=env, capture_output=True, text=True)
        self.assertEqual(configured.returncode, 0, configured.stdout + configured.stderr)
        for locale in ("en", "ja", "zh-Hans", "ko", "es"):
            result = subprocess.run([*base, "--lang", locale, "model-api-check", "--adapter", str(adapter)], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        proposed = subprocess.run([*base, "--json", "propose", "task", "--adapter", str(adapter), "--key", "cli-propose",
                                  "--expected-revision", str(self.revision)], env=env, capture_output=True, text=True)
        self.assertEqual(proposed.returncode, 0, proposed.stdout + proposed.stderr)
        self.assertEqual(len(self.http.calls), 1)

    def test_cli_auto_thinking_is_explicit_and_does_not_call_a_model(self):
        base = [sys.executable, "-m", "verantyx", "--project", str(self.root), "--json", "model-api-config",
                "--provider", "ollama", "--model", "fixture-model", "--endpoint", self.http.configuration("ollama")["endpoint"],
                "--allow-loopback-http", "--max-output-tokens", "32768", "--context-window", "131072", "--timeout", "600"]
        for mode in ("on", "off", "auto"):
            path = self.root / ("cli-" + mode + ".json")
            completed = subprocess.run([*base, "--thinking-mode", mode, "--output", str(path)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            value = json.loads(path.read_text())
            self.assertEqual(value.get("thinking", False), {"on": True, "off": False, "auto": "auto"}[mode])
            self.assertEqual(value["max_output_tokens"], 32768)
            self.assertEqual(value["context_window"], 131072)
            self.assertEqual(value["timeout"], 600)
        path = self.root / "conflicting.json"
        failed = subprocess.run([*base, "--thinking", "--thinking-mode", "auto", "--output", str(path)], capture_output=True, text=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse(path.exists())
        self.assertEqual(self.http.calls, [])


if __name__ == "__main__":
    unittest.main()
