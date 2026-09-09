"""Exercise input events, display isolation and progress over real workflows."""
import contextlib
from copy import deepcopy
import io
import os
import time
import unittest
from unittest import mock

from prompt_toolkit import PromptSession
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

import test_responses_v06 as fixtures
from verantyx.errors import LedgerError
from verantyx.i18n import text
from verantyx.progress import observe, report
from verantyx.responses import ask
from verantyx.terminal_ui import ConsoleUI, STAGES, capable_terminal, command_completer, input_bindings


class InputTests(unittest.TestCase):
    def prompt(self, keys):
        with create_pipe_input() as stream:
            session = PromptSession(input=stream, output=DummyOutput(), multiline=True,
                                    key_bindings=input_bindings())
            stream.send_text(keys)
            return session.prompt()

    def test_paste_preserves_newlines_and_does_not_submit_each_line(self):
        self.assertEqual(self.prompt("\x1b[200~日本語の依頼\nsecond line\x1b[201~\r"), "日本語の依頼\nsecond line")

    def test_large_paste_waits_for_explicit_submit_and_retains_indent_blank_lines(self):
        from concurrent.futures import ThreadPoolExecutor
        pasted = "\n".join("  日本語の条件 " + str(i) if i % 3 else "" for i in range(457)) + "\n"
        with create_pipe_input() as stream, ThreadPoolExecutor(1) as pool:
            session = PromptSession(input=stream, output=DummyOutput(), multiline=True, key_bindings=input_bindings())
            future = pool.submit(session.prompt)
            stream.send_text("\x1b[200~" + pasted.replace("\n", "\r\n") + "\x1b[201~")
            # Repaint waits until this input batch is applied, without an Enter.
            deadline = time.monotonic() + 2
            while session.default_buffer.text != pasted and time.monotonic() < deadline:
                time.sleep(.01)
            try:
                self.assertEqual(session.default_buffer.text, pasted)
                self.assertFalse(future.done())
            finally:
                stream.send_text("\r")
            self.assertEqual(future.result(timeout=2), pasted)

    def test_portable_newline_and_ctrl_j(self):
        self.assertEqual(self.prompt("one\\\rtwo\nthree\r"), "one\ntwo\nthree")

    def test_ctrl_c_clears_draft_without_sending_it(self):
        self.assertEqual(self.prompt("do not submit\x03new request\r"), "new request")

    def test_empty_ctrl_c_exits(self):
        with self.assertRaises(KeyboardInterrupt):
            self.prompt("\x03")

    def test_command_completion_does_not_rewrite_natural_language(self):
        complete = command_completer()
        self.assertEqual([c.text for c in complete.get_completions(Document("/fl"), None)], ["/flow"])
        self.assertEqual(list(complete.get_completions(Document("Explain /fl"), None)), [])


class TerminalTests(unittest.TestCase):
    def setUp(self):
        environment = mock.patch.dict(os.environ, {"TERM": "xterm-256color"})
        environment.start()
        self.addCleanup(environment.stop)
        self.fixture = fixtures.ResponseTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.adapter = self.fixture.adapter()

    def run_ask(self, key="visual"):
        return ask(self.fixture.root, self.fixture.cfg, request="Retry design", adapter_path=self.adapter, key=key)

    def ui(self, animated=True):
        with mock.patch("verantyx.terminal_ui.capable_terminal", return_value=True):
            ui = ConsoleUI(self.fixture.root, self.fixture.cfg, "ja")
        output = io.StringIO()
        ui.console = Console(file=output, force_terminal=True, width=80, no_color=True)
        ui.animated = animated
        return ui, output

    def test_real_stages_and_cached_calls_do_not_invent_generation(self):
        stages = []
        with observe(stages.append):
            first = self.run_ask()
        self.assertEqual(stages, ["request", "context", "proposal", "assessment", "structure", "answer", "capture"])
        self.assertNotIn("editor", stages)
        stages.clear()
        with observe(stages.append):
            duplicate = self.run_ask()
        self.assertNotIn("proposal", stages)
        self.assertNotIn("answer", stages)
        self.assertEqual(first["projection_hash"], duplicate["projection_hash"])
        self.assertEqual(len(self.fixture.invocations()), 2)

    def test_failed_proposal_never_reports_answer_or_capture(self):
        self.adapter = self.fixture.adapter("raise SystemExit(7)")
        stages = []
        with observe(stages.append), self.assertRaises(LedgerError):
            self.run_ask()
        self.assertIn("proposal", stages)
        self.assertNotIn("answer", stages)
        self.assertNotIn("capture", stages)

    def test_broken_observer_does_not_change_workflow_or_grant_authority(self):
        def broken(stage):
            raise ValueError("display failed")
        with observe(broken):
            result = self.run_ask()
        self.assertEqual(result["state"]["latest_response"]["mode"], "GENERATED")
        self.assertFalse(result["state"]["can_execute_effects"])
        self.assertEqual(len(self.fixture.invocations()), 2)

    def test_animation_restores_cursor_and_observer_after_interrupt(self):
        ui, output = self.ui()
        outer = []
        with observe(outer.append):
            with self.assertRaises(KeyboardInterrupt):
                with ui.activity():
                    report("proposal")
                    time.sleep(.27)
                    raise KeyboardInterrupt()
            report("answer")
        raw = output.getvalue()
        self.assertIn("\x1b[?25l", raw)
        self.assertIn("\x1b[?25h", raw)
        self.assertIn(text("ja", "console.stage.proposal"), raw)
        self.assertGreater(raw.count("\r"), 1)
        self.assertEqual(outer, ["answer"])

    def test_nonterminal_and_dumb_use_plain_output(self):
        with mock.patch("sys.stdin", io.StringIO()), mock.patch("sys.stdout", io.StringIO()):
            self.assertFalse(capable_terminal())
        with mock.patch.dict(os.environ, {"TERM": "dumb"}):
            self.assertFalse(capable_terminal())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ui = ConsoleUI(self.fixture.root, self.fixture.cfg, "ja", plain=True)
            with ui.activity():
                report("proposal")
        self.assertNotIn("\x1b", out.getvalue())
        self.assertIn(text("ja", "console.stage.proposal"), out.getvalue())

    def test_model_controls_and_markdown_do_not_hide_fact_panel(self):
        result = self.run_ask()
        state = deepcopy(result["state"])
        state["latest_response"]["document"]["answer"] = "```\n\x1b[2J[link](https://example.com)"
        ui, output = self.ui(False)
        ui.console = Console(file=output, width=120, color_system=None)
        ui.response({"state": state}, 1.2)
        rendered = output.getvalue()
        self.assertNotIn("\x1b", rendered)
        self.assertIn("\\u001b", rendered)
        self.assertIn(text("ja", "presentation.recorded_facts"), rendered)
        self.assertIn("1.2", rendered)

    def test_reduce_motion_keeps_stages_without_repainting(self):
        with mock.patch.dict(os.environ, {"VERANTYX_REDUCE_MOTION": "1"}), \
                mock.patch("verantyx.terminal_ui.capable_terminal", return_value=True):
            ui = ConsoleUI(self.fixture.root, self.fixture.cfg, "ja")
        output = io.StringIO()
        ui.console = Console(file=output, width=120, color_system=None)
        with ui.activity():
            report("proposal")
            report("proposal")
            report("answer")
        self.assertNotIn("\r", output.getvalue())
        self.assertEqual(output.getvalue().count(text("ja", "console.stage.proposal")), 1)
