"""Terminal entry, real adapter calls, and unchanged authorization boundaries."""
import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import unittest
from unittest import mock

import jsonschema
import test_responses_v06 as fixtures
from verantyx import config
from verantyx.cli import main
from verantyx.console import adapter_info, contextual_request, remember_adapter, saved_adapter, select_adapter
from verantyx.errors import LedgerError
from verantyx.i18n import LANGUAGES, catalog
from verantyx.ollama_schema import output_schema
from verantyx.storage.sqlite import EventStore


class Terminal(io.StringIO):
    def isatty(self):
        return True


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ResponseTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        self.adapter = self.fixture.adapter()

    def terminal(self, lines, arguments=(), locale="ja"):
        output = Terminal()
        with mock.patch("sys.stdin", Terminal(lines)), contextlib.redirect_stdout(output):
            code = main(["--project", str(self.root), "--lang", locale, *arguments])
        return code, output.getvalue()

    def test_bare_configured_command_starts_console_in_every_language(self):
        remember_adapter(self.root, adapter_info(self.adapter))
        for locale in LANGUAGES:
            with mock.patch("verantyx.session_commands.authorize_workspace", return_value=True), \
                    mock.patch("verantyx.terminal_ui.capable_terminal", return_value=False), \
                    mock.patch("verantyx.development_console.interact", return_value={"ok": True}) as interact:
                code, output = self.terminal("/quit\n", locale=locale)
            self.assertEqual(code, 0)
            interact.assert_called_once()
            self.assertFalse(interact.call_args.kwargs["onboarding"])
            self.assertEqual(self.fixture.invocations(), [])

    def test_json_start_never_waits_calls_network_or_writes(self):
        before = {str(p): p.read_bytes() for p in (self.root / ".verantyx").rglob('*') if p.is_file()}
        with mock.patch("sys.stdin", io.StringIO()), contextlib.redirect_stdout(io.StringIO()) as out, \
                mock.patch("verantyx.console.ollama_models", side_effect=AssertionError("network")):
            self.assertEqual(main(["--project", str(self.root), "start", "--json"]), 0)
        value = json.loads(out.getvalue())
        self.assertFalse(value["interactive"])
        self.assertFalse(value["network_called"])
        self.assertFalse(value["writes"])
        after = {str(p): p.read_bytes() for p in (self.root / ".verantyx").rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_two_real_rounds_receive_only_this_conversation_context(self):
        code, out = self.terminal("最初の依頼\nその続き\n/learn\n/dictionary\n/quit\n", ["start", "--adapter", str(self.adapter)])
        self.assertEqual(code, 0)
        calls = self.fixture.invocations()
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[0]["task"]["request"], "最初の依頼")
        continued = json.loads(calls[2]["task"]["request"])
        self.assertEqual(continued["current_request"], "その続き")
        self.assertEqual(continued["previous_turns"][0]["request"], "最初の依頼")
        self.assertIn(fixtures.ANSWERS["ja"], out)
        with EventStore(self.root, self.fixture.cfg["project"]["id"]) as store:
            kinds = [event["type"] for event in store.events()]
        self.assertEqual(kinds.count("ResponseComposed"), 2)
        self.assertNotIn("HumanDecisionRecorded", kinds)
        self.assertNotIn("ActionAuthorized", kinds)

    def test_new_clears_conversation_without_erasing_records(self):
        self.terminal("first\n/new\nsecond\n/quit\n", ["start", "--adapter", str(self.adapter)])
        calls = self.fixture.invocations()
        self.assertEqual(calls[2]["task"]["request"], "second")
        with EventStore(self.root, self.fixture.cfg["project"]["id"]) as store:
            self.assertEqual(sum(event["type"] == "TaskRequested" for event in store.events()), 2)

    def test_source_spaces_are_preserved_while_commands_allow_surrounding_spaces(self):
        self.terminal("  retain my spaces  \n  /quit  \n", ["start", "--adapter", str(self.adapter)])
        calls = self.fixture.invocations()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["shared_context"]["sources"][0]["text"], "  retain my spaces  ")

    def test_plain_explicit_paste_sends_one_request_and_keeps_commands_as_data(self):
        original = "  最初の行\n\n/quit\n最後の行  \n"
        code, output = self.terminal("/paste\n" + original + "/send\n/quit\n", ["start", "--adapter", str(self.adapter), "--plain"])
        self.assertEqual(code, 0)
        calls = self.fixture.invocations()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["task"]["request"], original)
        self.assertEqual(calls[0]["shared_context"]["sources"][0]["text"], original)
        self.assertIn("5行", output)

    def test_cancelled_paste_creates_no_task(self):
        self.terminal("/paste\n依頼ではない\n/cancel\n/quit\n", ["start", "--adapter", str(self.adapter)])
        self.assertEqual(self.fixture.invocations(), [])

    def test_model_failure_displays_code_and_closed_diagnostic_without_provider_body(self):
        error = LedgerError("BRIDGE_OUTCOME_UNKNOWN", {"reason": "MODEL_API_HTTP_STATUS", "http_status": 503,
                                                     "provider_body": "must-not-display"})
        with mock.patch("verantyx.responses.ask", side_effect=error) as call:
            code, output = self.terminal("依頼\n/quit\n", ["start", "--adapter", str(self.adapter)])
        self.assertEqual(code, 0)
        self.assertEqual(call.call_count, 1)
        self.assertIn("BRIDGE_OUTCOME_UNKNOWN / MODEL_API_HTTP_STATUS / HTTP 503", output)
        self.assertNotIn("must-not-display", output)

    def test_authority_mode_cannot_be_bypassed_by_console(self):
        with mock.patch("verantyx.authority.state", return_value={"enabled": True}):
            code, out = self.terminal("do work\n/quit\n", ["start", "--adapter", str(self.adapter)])
        self.assertEqual(code, 0)
        self.assertIn(catalog("ja")["error.AUTHORITY_REQUIRED"], out)
        self.assertEqual(self.fixture.invocations(), [])

    def test_console_cannot_be_signed_as_an_open_ended_operation(self):
        from verantyx.authority import _parse_operation
        with self.assertRaises(LedgerError) as error:
            _parse_operation(["start", "--adapter", str(self.adapter)], "ja")
        self.assertEqual(error.exception.code, "AUTHORITY_REQUEST_INVALID")

    def test_unknown_slash_commands_never_execute_or_call_model(self):
        self.terminal("/execute rm file\n/learn\n/quit\n", ["start", "--adapter", str(self.adapter)])
        self.assertEqual(self.fixture.invocations(), [])

    def test_flow_and_details_are_read_only_and_plain_has_no_ansi(self):
        code, out = self.terminal("/flow\n/details\n/quit\n", ["start", "--adapter", str(self.adapter), "--plain"])
        self.assertEqual(code, 0)
        self.assertIn(catalog("ja")["console.flow"], out)
        self.assertNotIn("\x1b", out)
        self.assertEqual(self.fixture.invocations(), [])

    def test_missing_model_selection_can_be_cancelled_without_writes(self):
        with mock.patch("verantyx.console.ollama_models", return_value=[]):
            code, _ = self.terminal(":q\n", ["start"])
        self.assertEqual(code, 0)
        self.assertFalse((self.root / ".verantyx/console.json").exists())

    def test_selected_local_model_persists_without_generation(self):
        with mock.patch("verantyx.console.ollama_models", return_value=["existing:small"]), \
                mock.patch("sys.stdin", Terminal("1\n")), contextlib.redirect_stdout(Terminal()):
            chosen = select_adapter(self.root, "ja", 300)
        self.assertEqual(saved_adapter(self.root), chosen)
        value = json.loads(Path(chosen["path"]).read_text())
        self.assertEqual(value["model"], "existing:small")
        self.assertIsNone(value["key_env"])
        self.assertEqual(self.fixture.invocations(), [])

    def test_changed_adapter_requires_reselection(self):
        remember_adapter(self.root, adapter_info(self.adapter))
        self.adapter.write_text(self.adapter.read_text() + " ")
        with self.assertRaises(LedgerError) as error:
            saved_adapter(self.root)
        self.assertEqual(error.exception.code, "CONSOLE_ADAPTER_CHANGED")

    def test_symlink_selection_does_not_write_target(self):
        target = self.root / "untouched.json"
        target.write_text("untouched")
        (self.root / ".verantyx/console.json").symlink_to(target)
        with self.assertRaises(LedgerError):
            remember_adapter(self.root, adapter_info(self.adapter))
        self.assertEqual(target.read_text(), "untouched")

    def test_failed_call_is_not_automatically_retried(self):
        with mock.patch("verantyx.responses.ask", side_effect=LedgerError("BRIDGE_OUTCOME_UNKNOWN")) as call:
            code, out = self.terminal("one request\n/help\n/quit\n", ["start", "--adapter", str(self.adapter)])
        self.assertEqual(code, 0)
        self.assertEqual(call.call_count, 1)
        self.assertIn(catalog("ja")["console.failed"], out)

    def test_context_bound_never_truncates_current_request(self):
        current = "x" * 15999
        self.assertEqual(contextual_request(current, [{"request": "old", "assistant_candidate": "y" * 16000}]), current)
        with self.assertRaises(LedgerError):
            contextual_request("x" * 16001, [])

    def test_ollama_schema_preserves_required_fields_and_rejects_extra_authority(self):
        from verantyx.bridges import _input
        self.fixture.start("schema")
        with EventStore(self.root, self.fixture.cfg["project"]["id"]) as store:
            value, _ = _input(self.root, store, "schema", "ja", [])
        schema = output_schema(value)
        jsonschema.Draft202012Validator.check_schema(schema)
        proposal = deepcopy(value["proposal_template"])
        jsonschema.validate(proposal, schema)
        proposal["approved"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(proposal, schema)
        del proposal["approved"]
        proposal["task_id"] = "other"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(proposal, schema)

    def test_response_schema_keeps_title_property_and_exact_norm_hash(self):
        self.terminal("hello\n/quit\n", ["start", "--adapter", str(self.adapter)])
        value = self.fixture.invocations()[1]
        schema = output_schema(value)
        jsonschema.Draft202012Validator.check_schema(schema)
        fields = schema["properties"]["reusable_candidates"]["items"]
        self.assertIn("title", fields["properties"])
        response = deepcopy(value["response_template"])
        jsonschema.validate(response, schema)
        response["norms_sha256"] = "0" * 64
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(response, schema)
