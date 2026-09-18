"""Selection anchors survive scrolling, reflow, streaming and clipboard copies."""
import asyncio
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase, mock

from prompt_toolkit.application import Application
from prompt_toolkit.clipboard import InMemoryClipboard
from prompt_toolkit.data_structures import Point
from prompt_toolkit.document import Document
from prompt_toolkit.layout import Layout
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.selection import SelectionState
from prompt_toolkit.widgets import TextArea

from verantyx.pane_scroll import ReadingScroll
from verantyx.reading_ux import ReadingUX


class ReadingHarness(ReadingUX):
    def __init__(self):
        self._init_reading()
        self.width = 16
        self.context = ("test",)
        self.chat_lexer = self.owner_lexer = None
        self.areas = {"agent": TextArea(read_only=True, wrap_lines=False)}
        self.system_area = TextArea(read_only=True)
        self.input = TextArea()
        self.owner_input = TextArea()
        self.focus_name = "agent"
        self.active_input = "agent"
        self.picker = None
        self.app = Application(layout=Layout(self.areas["agent"]), output=DummyOutput(),
                               clipboard=InMemoryClipboard())
        self.reading_scroll = ReadingScroll(self)
        self._archive_scroll = mock.Mock(return_value=False)

    def _reading_context(self, name):
        return self.context

    def _pane_width(self, name):
        return self.width

    def _compact_ui(self):
        return False

    def _locale(self):
        return "en"

    def _render(self):
        pass

    def _picker_active(self):
        return False

    def fill(self, text):
        self._set_pane_text("agent", text)
        self.area.window.render_info = SimpleNamespace(window_height=5, window_width=self.width,
                                                       _x_offset=2, _y_offset=3)

    @property
    def area(self):
        return self.areas["agent"]

    def select(self, start, end):
        state = self.reading_views["agent"]
        self.area.buffer.cursor_position = state.display_position(end)
        self.area.buffer.selection_state = SelectionState(state.display_position(start))


class ReadingSelection(TestCase):
    def setUp(self):
        self.subject = ReadingHarness()

    def test_page_down_extends_selection_instead_of_refusing_to_scroll(self):
        s = self.subject
        s.fill("\n".join(f"line {i:02d}" for i in range(30)))
        s.select(0, 2)
        anchor = s.area.buffer.selection_state.original_cursor_position
        s.reading_scroll.move(1, page=True)
        self.assertEqual(s.area.window.vertical_scroll, 3)
        self.assertEqual(s.area.buffer.selection_state.original_cursor_position, anchor)
        self.assertGreater(s.area.buffer.cursor_position, 2)

    def test_wheel_during_drag_extends_at_pointer_and_keeps_anchor(self):
        s = self.subject
        s.fill("\n".join(f"line {i:02d}" for i in range(30)))
        s.area.buffer.cursor_position = 1
        s.reading_drag = s.area
        s.reading_scroll.extend(Point(6, 7))
        anchor = s.area.buffer.selection_state.original_cursor_position
        previous = s.area.buffer.cursor_position
        s.reading_scroll.move(1)
        self.assertEqual(s.area.buffer.selection_state.original_cursor_position, anchor)
        self.assertGreater(s.area.buffer.cursor_position, previous)

    def test_wide_characters_use_screen_cells(self):
        s = self.subject
        s.fill("日本語abc")
        s.reading_drag = s.area
        s.reading_scroll.extend(Point(6, 3))
        self.assertEqual(s.area.buffer.cursor_position, 2)

    def test_copy_is_exact_without_extra_character_or_soft_wrap_newline(self):
        s = self.subject
        s.width = 5
        s.fill("0123456789日本語abcdefgh")
        s.select(2, 15)
        with mock.patch("verantyx.reading_ux.system_copy", return_value=True) as clipboard:
            s._copy_reading(only_selection=True)
        clipboard.assert_called_once_with("23456789日本語ab")
        self.assertIsNotNone(s.area.buffer.selection_state)

    def test_selection_reflows_on_resize_and_defers_new_streamed_text(self):
        s = self.subject
        original = "0123456789日本語abcdefgh"
        s.fill(original)
        s.select(2, 15)
        s.width = 5
        s._set_pane_text("agent", original + "new output")
        self.assertEqual(s.reading_views["agent"].width, 5)
        self.assertTrue(s.reading_views["agent"].unseen)
        with mock.patch("verantyx.reading_ux.system_copy", return_value=True) as clipboard:
            s._copy_reading(only_selection=True)
        clipboard.assert_called_once_with(original[2:15])
        s.area.buffer.exit_selection()
        s._set_pane_text("agent", original + "new output")
        self.assertEqual(s.reading_views["agent"].raw, original + "new output")

    def test_macos_mouse_release_copies_and_retains_highlight(self):
        s = self.subject
        s.fill("copy this text")
        s.select(0, 4)
        s.reading_drag = s.area
        with mock.patch("verantyx.reading_ux.sys.platform", "darwin"), \
                mock.patch("verantyx.reading_ux.system_copy", return_value=True) as clipboard:
            s._finish_reading_drag()
        clipboard.assert_called_once_with("copy")
        self.assertIsNone(s.reading_drag)
        self.assertIsNotNone(s.area.buffer.selection_state)

    def test_release_over_another_pane_finishes_original_drag(self):
        s = self.subject
        s.fill("\n".join("selectable line" for _ in range(20)))
        original = mock.Mock()
        s.app.renderer.mouse_handlers.mouse_handlers[20][50] = original
        s.reading_drag = s.area
        s.reading_scroll.moved = True
        s.reading_scroll.route(s.app)
        event = MouseEvent(Point(50, 20), MouseEventType.MOUSE_UP, MouseButton.LEFT, frozenset())
        with mock.patch("verantyx.reading_ux.system_copy", return_value=True):
            s.app.renderer.mouse_handlers.mouse_handlers[20][50](event)
        original.assert_not_called()
        self.assertIsNone(s.reading_drag)

    def test_new_context_discards_old_selection(self):
        s = self.subject
        s.fill("old text")
        s.select(0, 3)
        s.context = ("new",)
        s._set_pane_text("agent", "new text")
        self.assertIsNone(s.area.buffer.selection_state)
        self.assertEqual(s.reading_views["agent"].raw, "new text")


class AutoScroll(IsolatedAsyncioTestCase):
    async def test_holding_at_edge_scrolls_without_more_mouse_events(self):
        s = ReadingHarness()
        s.fill("\n".join("a long line" for _ in range(60)))
        s.reading_drag = s.area
        s.reading_scroll.extend(Point(8, 8))
        task = asyncio.create_task(s.reading_scroll.auto_scroll())
        try:
            await asyncio.sleep(.28)
            self.assertGreaterEqual(s.area.window.vertical_scroll, 2)
            self.assertIsNotNone(s.area.buffer.selection_state)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
