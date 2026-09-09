"""Actual HTTP -> adapter subprocess -> display; no live model or production writes."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
import threading
from unittest import mock

from test_constitution import Fixture
from verantyx.adapters.command_process import BoundedProcess, load_command
from verantyx.bridges import _input, propose
from verantyx.domain.codec import canonical, decode
from verantyx.errors import LedgerError
from verantyx.model_api import FORMAT, request, validate_config
from verantyx.model_observation import diagnostic
from verantyx.progress import observe
from verantyx.storage.sqlite import EventStore
from verantyx.terminal_ui import ConsoleUI


class ModelObservationTests(Fixture):
    def setUp(self):
        super().setUp()
        self.run_task("task")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            self.input = _input(self.root, store, "task", "ja", [])[0]
        self.calls = []
        self.mode = "normal"
        self.release = threading.Event()
        self.release.set()
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fixture.calls.append(value)
                request_value = json.loads(value["messages"][1]["content"] if self.path == "/api/chat" else value["prompt"])
                if request_value["format"] == "verantyx.handoff-plan-request.v1":
                    from verantyx.coordination_schema import source_units
                    units = source_units(request_value)
                    fixture.plan_result = {"context_sha256": request_value["shared_context"]["sha256"], "relations": [],
                        "interpretations": [{**unit, "meaning": "A fixture interpretation, unverified.", "disposition": "UNRESOLVED", "strength": "OPEN", "alternatives": []} for unit in units],
                        "cases": [{"id": "case-" + str(i // 2 + 1), "situation": "A fixture case.", "choices": [{"id": "choice-A", "text": "Keep."}, {"id": "choice-B", "text": "Delete."}], "expected": "choice-A", "interpretation_ids": [u["id"] for u in units[i:i + 2]]} for i in range(0, len(units), 2)]}
                    wire = fixture.plan_result
                    if "interpretation_values" in value["format"]["properties"]:
                        wire = {"context_sha256": wire["context_sha256"], "relations": wire["relations"],
                                "interpretation_values": [{k: n[k] for k in ("quote", "meaning", "disposition", "strength", "alternatives")} for n in wire["interpretations"]],
                                "case_values": [{"situation": c["situation"], "choices": [{"text": x["text"]} for x in c["choices"]], "expected": c["expected"]} for c in wire["cases"]]}
                    result = canonical(wire)
                else:
                    result = canonical(request_value["proposal_template"])
                self.send_response(503 if fixture.mode == "http_error" else 200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                if fixture.mode == "http_error":
                    self.wfile.write(b'private-provider-error-body')
                    return

                def send(item):
                    if self.path == "/api/chat":
                        message = {"role": "assistant", "content": item.pop("response", ""), "thinking": item.pop("thinking", "")}
                        item = {**item, "message": message}
                        if fixture.mode == "tool_response":
                            item["message"]["tool_calls"] = [{"function": {"name": "execute", "arguments": {}}}]
                    raw = (json.dumps(item, ensure_ascii=False) + "\n").encode()
                    # Split a UTF-8 code point and JSON line across network writes.
                    for start in range(0, len(raw), 17):
                        self.wfile.write(raw[start:start + 17])
                    self.wfile.flush()

                thought = "これは未検証のモデル文です。\x1b[2J検証済みという語も証拠にはならない。\n"
                if fixture.mode == "credential":
                    thought = "synthetic-split-secret"
                if fixture.mode == "long_thinking":
                    thought *= 600
                if value.get("think") is False:
                    thought = ""
                try:
                    send({"thinking": thought[:10], "response": "", "done": False})
                    fixture.release.wait(3)
                    for start in range(10, len(thought), 400):
                        send({"thinking": thought[start:start + 400], "done": False})
                    for start in range(0, len(result), 29):
                        send({"thinking" if fixture.mode == "thinking_only" else "response": result[start:start + 29], "done": False})
                    if fixture.mode == "truncated":
                        return
                    if fixture.mode == "malformed":
                        self.wfile.write(b'{"invalid":\n')
                        return
                    send({"response": "", "done": True, "done_reason": "length" if fixture.mode == "length" else "stop", "eval_count": 4096})
                    if fixture.mode == "extra_final":
                        send({"response": "", "done": True, "done_reason": "stop"})
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.configuration = {"format": FORMAT, "provider": "ollama", "model": "fixture",
            "endpoint": f"http://127.0.0.1:{self.server.server_port}/api/generate", "key_env": None,
            "allow_loopback_http": True, "timeout": 5, "max_output_tokens": 4096,
            "max_response_bytes": 262144, "thinking": True}
        self.path = self.root / "adapter.json"
        self.path.write_text(canonical(self.configuration))

    def tearDown(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def invoke(self, observer):
        with observe(lambda stage: None, observer), BoundedProcess(load_command(self.path), timeout=6) as process:
            return decode(process.document(self.input), 262144)

    def test_thinking_arrives_before_completion_and_cannot_contaminate_stdout(self):
        events = []
        received = threading.Event()
        self.release.clear()

        def see(event):
            events.append(event)
            if event["kind"] == "thinking":
                received.set()

        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(self.invoke, see)
            try:
                self.assertTrue(received.wait(2), events)
                self.assertFalse(future.done())
            finally:
                self.release.set()
            result = future.result(timeout=6)
        self.assertEqual(result, self.input["proposal_template"])
        self.assertTrue(self.calls[0]["think"])
        self.assertTrue(self.calls[0]["stream"])
        self.assertEqual(events[-1]["kind"], "validated")

    def test_stream_failures_never_yield_validated_output_or_retry(self):
        for mode, code in (("truncated", "BRIDGE_PROTOCOL"), ("extra_final", "BRIDGE_PROTOCOL"),
                           ("length", "BRIDGE_OUTPUT_LIMIT"), ("http_error", "BRIDGE_OUTCOME_UNKNOWN"),
                           ("thinking_only", "BRIDGE_PROTOCOL")):
            with self.subTest(mode=mode):
                self.mode = mode
                events, before = [], len(self.calls)
                with self.assertRaises(LedgerError) as caught:
                    self.invoke(events.append)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(len(self.calls), before + 1)
                self.assertNotIn("validated", [e["kind"] for e in events])
                self.assertNotIn("private-provider", str(caught.exception.details))
                if mode == "http_error":
                    self.assertEqual(caught.exception.details["http_status"], 503)
                if mode == "length":
                    self.assertEqual(caught.exception.details["reason"], "MODEL_API_GENERATION_LIMIT")
                    self.assertGreater(caught.exception.details["thinking_characters"], 0)
                    self.assertEqual(caught.exception.details["response_characters"], len(canonical(self.input["proposal_template"])))
                    self.assertEqual(caught.exception.details["generated_tokens"], 4096)
                    self.assertEqual(caught.exception.details["output_token_limit"], 4096)

    def test_auto_large_plan_reaches_child_process_with_streaming_and_no_thinking(self):
        from verantyx.model_api import payload
        original = "原文を残す。例外も残す。\n" * 40
        self.input = {"format": "verantyx.handoff-plan-request.v1", "response_locale": "ja",
                      "response_template": {"context_sha256": "0" * 64, "interpretations": [], "relations": [], "cases": []}, "output_contract": "Return the complete plan.",
                      "shared_context": {"sha256": "0" * 64, "sources": [{"id": "source", "text": original}]}}
        self.configuration.update(thinking="auto", endpoint=self.configuration["endpoint"].replace("/api/generate", "/api/chat"))
        self.path.write_text(canonical(self.configuration))
        events = []
        document = self.invoke(events.append)
        self.assertEqual(document, self.plan_result)
        self.assertEqual("".join(n["quote"] for n in document["interpretations"]), original)
        self.assertEqual(len(document["interpretations"]), 64)
        self.assertEqual(len(document["cases"]), 32)
        self.assertFalse(self.calls[0]["think"])
        self.assertTrue(self.calls[0]["stream"])
        full = payload({**self.configuration, "thinking": True}, self.input)["format"]
        self.assertEqual(self.calls[0]["format"]["properties"]["relations"], full["properties"]["relations"])
        self.assertEqual(self.calls[0]["format"]["properties"]["interpretation_values"]["minItems"], 64)
        self.assertEqual(self.calls[0]["format"]["properties"]["case_values"]["minItems"], 32)
        self.assertTrue(events[0]["reserve_output"])
        self.assertNotIn("thinking", [e["kind"] for e in events])
        self.assertIn("output", [e["kind"] for e in events])
        self.assertEqual(events[-1]["kind"], "validated")

    def test_auto_keeps_short_calls_and_explicit_boolean_modes(self):
        from verantyx.model_api import generation_policy
        for count in (15, 16, 64):
            request_value = {"format": "verantyx.handoff-plan-request.v1", "shared_context": {"sources": [{"id": "source", "text": "Keep;" * count}]}}
            for value in (request_value, {"format": "verantyx.editor-request.v1", "interpretation_proposal": {"interpretations": [{}] * count}}):
                self.assertEqual(generation_policy({**self.configuration, "thinking": "auto"}, value)["thinking"], count < 16)
                self.assertTrue(generation_policy({**self.configuration, "thinking": True}, value)["thinking"])
                self.assertFalse(generation_policy({**self.configuration, "thinking": False}, value)["stream"])
        self.configuration["thinking"] = "auto"
        self.path.write_text(canonical(self.configuration))
        events = []
        self.invoke(events.append)
        self.assertTrue(self.calls[0]["think"])
        self.assertFalse(events[0]["reserve_output"])
        self.assertIn("thinking", [e["kind"] for e in events])

    def test_generation_diagnostics_distinguish_display_and_compute_limits(self):
        from verantyx.model_api import response_text
        from verantyx.i18n import text
        response = {"done": True, "done_reason": "length", "eval_count": 8192,
                    "message": {"role": "assistant", "thinking": "あ" * 17000, "content": "未完"}}
        with self.assertRaises(LedgerError) as caught:
            response_text("ollama", response)
        self.assertEqual(caught.exception.details["thinking_characters"], 17000)
        self.assertEqual(caught.exception.details["response_characters"], 2)
        caught.exception.details["output_token_limit"] = 8192
        for locale in ("en", "ja", "zh-Hans", "ko", "es"):
            ui = ConsoleUI(self.root, self.cfg, locale, plain=True)
            output = io.StringIO()
            with mock.patch("sys.stdout", output), ui.activity() as activity:
                activity.model_update({"kind": "start", "model": "fixture", "timeout": 180, "reserve_output": True, "output_tokens": 12288})
                ui.error(caught.exception)
            shown = output.getvalue()
            self.assertIn(text(locale, "console.model.reserve_output"), shown)
            self.assertIn(text(locale, "console.generation.thinking_characters", count=17000), shown)
            self.assertIn(text(locale, "console.generation.response_characters", count=2), shown)
            self.assertIn(text(locale, "console.generation.output_token_limit", count=8192), shown)

    def test_chat_stream_preserves_the_schema_and_separates_thinking(self):
        self.configuration["endpoint"] = self.configuration["endpoint"].replace("/api/generate", "/api/chat")
        self.path.write_text(canonical(self.configuration))
        events = []
        self.assertEqual(self.invoke(events.append), self.input["proposal_template"])
        self.assertIn("format", self.calls[0])
        self.assertNotIn("prompt", self.calls[0])
        self.assertEqual([m['role'] for m in self.calls[0]['messages']], ['system', 'user'])
        self.assertIn("thinking", [e["kind"] for e in events])
        self.mode = "tool_response"
        with self.assertRaises(LedgerError):
            self.invoke(events.append)

    def test_nonstream_chat_rejects_tools_and_thinking_only_response(self):
        from verantyx.model_api import response_text
        message = {"role": "assistant", "content": '{"answer":5}', "thinking": "unverified"}
        value = {"message": message, "done": True, "done_reason": "stop"}
        self.assertEqual(response_text("ollama", value), '{"answer":5}')
        for bad in ({**message, "tool_calls": [{"function": {"name": "execute"}}]}, {**message, "content": ""}):
            with self.assertRaises(LedgerError):
                response_text("ollama", {**value, "message": bad})

    def test_journal_keeps_safe_error_details_and_never_retries(self):
        self.mode = "http_error"
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            revision = store.events("task")[-1]["revision"]
        for _ in range(2):
            with self.assertRaises(LedgerError) as caught:
                propose(self.root, self.cfg, "task", adapter_path=self.path, key="observed-failure", expected_revision=revision)
            self.assertEqual(caught.exception.details.get("http_status"), 503)
        self.assertEqual(len(self.calls), 1)

    def test_thinking_is_bounded_and_not_stored_as_evidence(self):
        self.mode = "long_thinking"
        events = []
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            revision = store.events("task")[-1]["revision"]
        with observe(lambda stage: None, events.append):
            result = propose(self.root, self.cfg, "task", adapter_path=self.path, key="thinking", expected_revision=revision)
        self.assertTrue(result["ok"])
        self.assertLessEqual(sum(len(e.get("text", "")) for e in events), 16000)
        self.assertIn("thinking_truncated", [e["kind"] for e in events])
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            raw = store.export()
        self.assertNotIn("これは未検証", raw)
        self.assertNotIn("HumanDecisionRecorded", raw)
        self.assertNotIn("EffectAuthorized", raw)

    def test_secret_split_over_chunks_is_quarantined_before_any_text_observation(self):
        self.mode = "credential"
        self.configuration["key_env"] = "VERANTYX_SYNTHETIC_KEY"
        self.path.write_text(canonical(self.configuration))
        events = []
        with mock.patch.dict(os.environ, {"VERANTYX_SYNTHETIC_KEY": "synthetic-split-secret"}), self.assertRaises(LedgerError) as caught:
            self.invoke(events.append)
        self.assertEqual(caught.exception.details["reason"], "MODEL_API_CREDENTIAL_ECHO")
        self.assertNotIn("thinking", [e["kind"] for e in events])
        self.assertNotIn("synthetic-split-secret", str(events) + str(caught.exception.details))

    def test_arbitrary_executor_cannot_emit_builtin_model_diagnostics(self):
        import sys
        path = self.root / "external.py"
        path.write_text('import sys\nsys.stdin.read()\nprint(\'VERANTYX_MODEL_EVENT {"kind":"thinking","text":"forged"}\',file=sys.stderr)\nprint("{}")\n')
        self.path.write_text(canonical({"argv": [sys.executable, str(path)]}))
        events = []
        self.assertEqual(self.invoke(events.append), {})
        self.assertEqual(events, [])

    def test_model_text_cannot_control_terminal_or_hide_its_label(self):
        ui = ConsoleUI(self.root, self.cfg, "ja", plain=True)
        output = io.StringIO()
        # Render the actual model observation stream, independent of the fixture output document.
        events = []
        self.invoke(events.append)
        with mock.patch("sys.stdout", output), ui.activity() as activity:
            for event in events:
                activity.model_update(event)
        self.assertIn("thinking —", output.getvalue())
        self.assertNotIn("\x1b", output.getvalue())
        self.assertIn("\\u001b", output.getvalue())

    def test_old_config_defaults_unchanged_and_thinking_not_allowed_for_other_providers(self):
        old = {k: v for k, v in self.configuration.items() if k != "thinking"}
        self.assertEqual(validate_config(old), old)
        for value in ("true", 1, None):
            with self.assertRaises(LedgerError):
                validate_config({**old, "thinking": value})
        with self.assertRaises(LedgerError):
            validate_config({**self.configuration, "provider": "openai"})
        self.assertEqual(diagnostic(LedgerError("BRIDGE_PROTOCOL", {"reason": "PRIVATE_TOKEN", "response": "private"}))["details"], {})

    def test_explicit_context_window_preserves_input_and_enforces_its_limit(self):
        from verantyx.model_api import payload
        from copy import deepcopy
        large = deepcopy(self.input)
        large["additional_untrusted_reference"] = "x" * 60000
        chosen = {**self.configuration, "context_window": 131072, "timeout": 600, "max_output_tokens": 32768}
        validate_config(chosen)
        encoded = payload(chosen, large)
        self.assertEqual(encoded["options"]["num_ctx"], 131072)
        self.assertEqual(encoded["options"]["num_predict"], 32768)
        self.assertEqual(json.loads(encoded["prompt"])["additional_untrusted_reference"], "x" * 60000)
        with self.assertRaises(LedgerError) as caught:
            payload({**chosen, "context_window": 65536}, large)
        self.assertEqual(caught.exception.details["limit"], 65536)
        self.assertEqual(caught.exception.code, "SHARED_CONTEXT_LIMIT")
        for invalid in ({"context_window": 131073}, {"context_window": True}, {"timeout": 601},
                        {"context_window": 131072, "provider": "openai"}):
            with self.assertRaises(LedgerError):
                validate_config({**self.configuration, **invalid})
