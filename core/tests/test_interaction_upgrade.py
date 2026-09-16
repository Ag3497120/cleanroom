"""Focused offline checks for the split-input upgrade. No real model calls."""
import asyncio
from contextlib import ExitStack
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from prompt_toolkit.application.current import create_app_session
from prompt_toolkit.data_structures import Size
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.input.vt100_parser import Vt100Parser
from prompt_toolkit.keys import Keys
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.widgets import TextArea

from verantyx import config
from verantyx.cleanroom_tui import Cleanroom
from verantyx.input_recall import InputRecall
from verantyx.keyboard_protocol import enhanced_enter, SHIFT_ENTER_SEQUENCES
from verantyx.errors import LedgerError


class WideOutput(DummyOutput):
    def get_size(self):
        return Size(rows=44, columns=180)


class KeyboardProtocolTests(unittest.TestCase):
    def test_shift_sequences_are_newlines_and_plain_enter_stays_enter(self):
        from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
        before = {key: ANSI_SEQUENCES.get(key) for key in SHIFT_ENTER_SEQUENCES}
        with enhanced_enter(DummyOutput()):
            for sequence in SHIFT_ENTER_SEQUENCES:
                events = []
                parser = Vt100Parser(events.append)
                parser.feed(sequence)
                parser.flush()
                self.assertEqual([event.key for event in events], [Keys.ControlJ])
            events = []
            parser = Vt100Parser(events.append)
            parser.feed("\r")
            parser.flush()
            self.assertEqual(events[0].key, Keys.ControlM)
        self.assertEqual({key: ANSI_SEQUENCES.get(key) for key in SHIFT_ENTER_SEQUENCES}, before)

    def test_recall_preserves_draft_and_excludes_commands(self):
        recall = InputRecall()
        for value in ("first", "second", "//private", "/model", ""):
            recall.record("agent", value)
        field = TextArea(text="unsent draft")
        self.assertTrue(recall.move(field, "agent", -1))
        self.assertEqual(field.text, "second")
        recall.move(field, "agent", -1)
        self.assertEqual(field.text, "first")
        recall.move(field, "agent", 1)
        recall.move(field, "agent", 1)
        self.assertEqual(field.text, "unsent draft")
        recall.record("memo", "my note")
        self.assertEqual(recall.entries["agent"], ["first", "second"])
        self.assertEqual(recall.entries["memo"], ["my note"])


class LiveInputTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stack = ExitStack()
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.pipe = self.stack.enter_context(create_pipe_input())
        self.output = WideOutput()
        self.stack.enter_context(create_app_session(input=self.pipe, output=self.output))
        self.stack.enter_context(patch("prompt_toolkit.output.defaults.create_output", return_value=self.output))
        self.session = Cleanroom(self.root, config.defaults(self.root, "ja"))
        self.session.loop = asyncio.get_running_loop()
        self.session.view = {"panes": {}, "owner_items": []}
        self.actions = []
        self.session.start_action = lambda action, **kwargs: self.actions.append((action, kwargs))
        self.stack.enter_context(enhanced_enter(self.output))
        self.task = asyncio.create_task(self.session.app.run_async())
        await asyncio.sleep(.08)

    async def asyncTearDown(self):
        if not self.task.done():
            self.session.app.exit()
        await self.task
        self.session.closed = True
        if self.session.motion_task:
            self.session.motion_task.cancel()
            try:
                await self.session.motion_task
            except asyncio.CancelledError:
                pass
        self.session.reader.close()
        for executor in (self.session.read_executor, self.session.work_executor, self.session.note_executor):
            executor.shutdown(wait=True)
        self.stack.close()

    async def keys(self, text):
        self.pipe.send_text(text)
        await asyncio.sleep(.09)

    async def test_shift_enter_inserts_line_without_sending(self):
        for sequence in SHIFT_ENTER_SEQUENCES:
            self.session.input.buffer.reset()
            await self.keys("first" + sequence + "second")
            self.assertEqual(self.session.input.text, "first\nsecond")
            self.assertEqual(self.actions, [])
        await self.keys("\r")
        self.assertEqual(self.actions[-1][0], "work")
        self.assertEqual(self.actions[-1][1]["request"], "first\nsecond")

    async def test_empty_enter_keeps_three_field_cycle(self):
        await self.keys("\r")
        self.assertEqual((self.session.active_input, self.session.owner_mode), ("owner", "memo"))
        await self.keys("\r")
        self.assertEqual((self.session.active_input, self.session.owner_mode), ("owner", "search"))
        await self.keys("\r")
        self.assertEqual(self.session.active_input, "agent")
        self.assertEqual(self.actions, [])

    async def test_up_down_recalls_submissions_and_unsent_draft(self):
        await self.keys("first task\r")
        await self.keys("second task\r")
        await self.keys("draft")
        await self.keys("\x1b[A")
        self.assertEqual(self.session.input.text, "second task")
        await self.keys("\x1b[A")
        self.assertEqual(self.session.input.text, "first task")
        await self.keys("\x1b[B\x1b[B")
        self.assertEqual(self.session.input.text, "draft")

    async def test_settings_slash_is_not_work_or_recall(self):
        await self.keys("/model\r")
        self.assertEqual(self.actions, [("inline-settings", {"section": "models"})])
        self.assertEqual(self.session.recall.entries["agent"], [])

    async def test_temporary_chat_is_not_work_or_recall(self):
        await self.keys("//private question\r")
        self.assertEqual(self.actions[0][0], "temporary-chat")
        self.assertEqual(self.session.recall.entries["agent"], [])
        self.assertIsNone(self.session.pending_request)

    async def test_inline_picker_uses_arrows_with_localized_detail(self):
        from verantyx.choice_navigation import description
        selected = []
        self.session.settings_active = True
        self.session._show_picker("Choose a connection", [("codex", "Codex"), ("ollama", "Ollama")],
                                  selected.append, descriptions={
                                      name: description("", name, name, "ja") for name in ("codex", "ollama")})
        await self.keys("\x1b[B")
        self.assertIn("Ollama", self.session._menu_detail())
        self.assertIn("接続先", self.session._menu_detail())
        await self.keys("\r")
        self.assertEqual(selected, ["ollama"])

    async def test_system_messages_do_not_duplicate_answer_or_owner(self):
        self.session.view["ownership_projection"] = {"work_answer": "The actual answer."}
        # Inspect the answer formatter without needing a full owner projection fixture.
        self.session.logs.append("internal phase")
        self.assertEqual(self.session._primary_answer(), "The actual answer.")
        self.assertNotIn("internal phase", self.session._primary_answer())
        self.session.view.pop("ownership_projection")
        self.session._log("system-only", owner=True)
        self.assertEqual(list(self.session.notes), [])

    async def test_practice_memo_does_not_start_note_writer(self):
        self.session.practice = True
        self.session.owner_mode = "memo"
        self.session.owner_input.text = "practice note"
        self.session._submit_owner(self.session.owner_input.buffer)
        self.assertEqual(self.session.practice_notes, ["practice note"])
        self.assertIsNone(self.session.note_task)
        self.assertFalse((self.root / ".verantyx").exists())


def pdf_fixture():
    content = b"BT /F1 14 Tf 20 50 Td (Attachment fixture.) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 240 100] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    raw, offsets = bytearray(b"%PDF-1.4\n"), [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(raw))
        raw.extend(str(index).encode() + b" 0 obj\n" + body + b"\nendobj\n")
    xref = len(raw)
    raw.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        raw.extend(("%010d 00000 n \n" % offset).encode())
    raw.extend(b"trailer\n<< /Root 1 0 R /Size 6 >>\nstartxref\n" + str(xref).encode() + b"\n%%EOF")
    return raw


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.pdf = self.root / "assignment space.pdf"
        self.pdf.write_bytes(pdf_fixture())

    def tearDown(self):
        self.temporary.cleanup()

    def test_paths_and_options(self):
        from verantyx.attachment_inputs import paths_in_text, parse_argument
        self.assertEqual(paths_in_text("これを解いて/Users/example/課題.pdf")[0]["path"], "/Users/example/課題.pdf")
        self.assertEqual(paths_in_text('read "/tmp/a b.pdf"')[0]["path"], "/tmp/a b.pdf")
        self.assertEqual(paths_in_text("https://example.org/a.pdf"), [])
        self.assertEqual(parse_argument('--pages 1-3 --text "/tmp/a b.pdf"')["pages"], [1, 2, 3])

    def test_pdf_has_text_and_native_page_image(self):
        from verantyx.attachment_inputs import prepare, image_inputs, public_request
        records = prepare(self.root, [{"path": str(self.pdf)}])
        self.assertIn("Attachment fixture.", records[0]["pages"][0]["text"])
        images = image_inputs({"attachments": records})
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["mime_type"], "image/jpeg")
        public = json.dumps(public_request({"attachments": records}))
        self.assertNotIn("staged_path", public)
        self.assertNotIn("original_path", public)

    def test_text_only_and_scope(self):
        from verantyx.attachment_inputs import prepare, image_inputs
        records = prepare(self.root, [{"path": str(self.pdf), "text_only": True}])
        self.assertEqual(image_inputs({"attachments": records}), [])
        alias = self.root / "alias.pdf"
        alias.symlink_to(self.pdf)
        with self.assertRaises(LedgerError):
            prepare(self.root, [{"path": str(alias)}])

    def test_native_api_payloads(self):
        from verantyx.attachment_inputs import prepare
        from verantyx.model_api import payload
        from verantyx.agent_schema import WORK_REQUEST
        records = prepare(self.root, [{"path": str(self.pdf)}])
        value = {"format": WORK_REQUEST, "request": "Read attached page.", "attachments": records}
        common = {"model": "fixture-vision", "max_output_tokens": 2048}
        openai = payload({**common, "provider": "openai"}, value)
        self.assertEqual(openai["input"][0]["content"][1]["type"], "input_image")
        anthropic = payload({**common, "provider": "anthropic"}, value)
        self.assertEqual(anthropic["messages"][0]["content"][1]["type"], "image")
        gemini = payload({**common, "provider": "gemini"}, value)
        self.assertIn("inlineData", gemini["contents"][0]["parts"][1])
        compatible = payload({**common, "provider": "openai_compatible",
                              "endpoint": "http://127.0.0.1:1234/v1/chat/completions"}, value)
        self.assertEqual(compatible["messages"][1]["content"][1]["type"], "image_url")

    def test_changed_image_is_rejected(self):
        from verantyx.attachment_inputs import prepare, image_inputs
        records = prepare(self.root, [{"path": str(self.pdf)}])
        Path(records[0]["pages"][0]["image"]["staged_path"]).write_bytes(b"changed")
        with self.assertRaises(LedgerError):
            image_inputs({"attachments": records})


class TemporaryChatTests(unittest.TestCase):
    def test_native_cache_and_journal_use_temporary_directory(self):
        from verantyx.volatile_chat import chat
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter = root / "source.json"
            value = {"format": "verantyx.codex-cli.v1", "provider": "chatgpt_codex",
                     "model": "default", "role": "implementation", "reasoning_effort": "low",
                     "executable": "/usr/bin/false", "budget_directory": str(root / "persistent-budget"),
                     "max_calls": 4, "timeout": 30, "max_input_bytes": 524288, "max_response_bytes": 262144}
            adapter.write_text(json.dumps(value))
            temporary_paths = []

            def invoke(temporary, copied, request, **kwargs):
                temporary_paths.append(Path(temporary))
                copied_value = json.loads(Path(copied).read_text())
                self.assertNotEqual(copied_value["budget_directory"], value["budget_directory"])
                self.assertTrue(Path(copied_value["budget_directory"]).is_relative_to(temporary))
                self.assertEqual(request["approved_files"], [])
                self.assertEqual(request["personal_context"], {})
                return {"document": {"status": "COMPLETE", "answer": "Private answer.", "tool_requests": []},
                        "model": {"provider": "fixture", "model": "fixture"}}

            with patch("verantyx.agent_models.selected_work", return_value=str(adapter)), \
                    patch("verantyx.agent_models.invoke", side_effect=invoke), \
                    patch("verantyx.volatile_chat.command_scope") as scope:
                scope.return_value.__enter__.return_value = None
                result = chat(root, config.defaults(root, "en"), "private question")
            self.assertTrue(result["transient"])
            self.assertFalse((root / "persistent-budget").exists())
            self.assertTrue(all(not path.exists() for path in temporary_paths))


if __name__ == "__main__":
    unittest.main()
