"""Observed activity, quiet input and recorded owner questions drive the UI."""
from types import SimpleNamespace
from unittest import TestCase, mock

from verantyx.activity_ux import ActivityUX


class Harness(ActivityUX):
    def __init__(self):
        self.view = None
        self.question = None
        self.readonly = self.busy = self.model_waiting = self.native_selection = False
        self.phase = "idle"
        self.started = None
        self.active_action = "work"
        self.root = None
        self._render = mock.Mock()

    def _tr(self, en, ja):
        return ja

    def _pane_width(self, name):
        return 70


class ActivityTests(TestCase):
    def setUp(self):
        self.ui = Harness()

    def test_recorded_owner_question_is_waiting_even_when_worker_is_idle(self):
        self.ui.view = {"state": {"work_result": {"status": "WAITING_OWNER"}}}
        kind, label, _ = self.ui._activity()
        self.assertEqual(kind, "waiting")
        self.assertIn("返答", label)
        self.assertNotIn("idle", label)

    def test_reply_clears_old_waiting_indicator(self):
        self.ui.view = {"state": {"work_result": {"status": "WAITING_OWNER"}, "work_owner_reply": {"text": "yes"}}}
        self.assertEqual(self.ui._activity()[0], "idle")

    def test_tool_activity_shows_actual_path_and_model_wait_is_distinct(self):
        self.ui.busy = True
        self.ui.phase = "tool:read_file:src/main.py"
        kind, label, detail = self.ui._activity()
        self.assertEqual((kind, detail), ("tool", "src/main.py"))
        self.assertIn("読んで", label)
        self.ui.phase = "model"
        self.ui.model_waiting = True
        self.assertEqual(self.ui._activity()[0], "model")

    def test_input_background_does_not_pulse_and_reduced_motion_is_static(self):
        self.ui.busy = True
        with mock.patch.dict("os.environ", {"VERANTYX_REDUCE_MOTION": "1"}):
            with mock.patch("time.monotonic", return_value=1):
                before = self.ui._activity_mark("model"), self.ui._agent_input_style()
            with mock.patch("time.monotonic", return_value=20):
                after = self.ui._activity_mark("model"), self.ui._agent_input_style()
        self.assertEqual(before, after)
        self.assertEqual(self.ui._activity_mark("waiting"), "●")

    def test_usage_does_not_claim_unknown_cache_is_zero(self):
        self.ui.last_model_usage = {"source": "provider", "tokens": {"input_tokens": 100}}
        self.assertNotIn("0%", self.ui._activity_detail())
        self.ui.last_model_usage["tokens"]["cached_input_tokens"] = 80
        self.assertIn("80%", self.ui._activity_detail())

    def test_elapsed_time_is_observed_not_fake_percentage_progress(self):
        self.ui.busy = self.ui.model_waiting = True
        self.ui.started = 100
        with mock.patch("time.monotonic", return_value=175):
            text = "".join(value for _, value in self.ui._activity_line())
        self.assertIn("01:15", text)
        self.assertNotIn("%", text)

    def test_native_selection_freezes_activity_text(self):
        self.ui._activity_line()
        self.ui._activity_detail()
        self.ui.native_selection = True
        before = self.ui._activity_line()
        detail = self.ui._activity_detail()
        self.ui.busy = self.ui.model_waiting = True
        self.assertEqual(self.ui._activity_line(), before)
        self.assertEqual(self.ui._activity_detail(), detail)

    def test_composer_grows_for_multiline_and_wide_characters_then_shrinks(self):
        self.ui.input = SimpleNamespace(text="")
        self.ui._compact_ui = lambda: False
        self.assertEqual(self.ui._composer_height(), 1)
        self.ui.input.text = "あ" * 34
        self.assertEqual(self.ui._composer_height(), 2)
        self.ui.input.text = "line\n" * 20
        self.assertEqual(self.ui._composer_height(), 5)
        self.ui._compact_ui = lambda: True
        self.assertEqual(self.ui._composer_height(), 3)
        self.ui.input.text = ""
        self.assertEqual(self.ui._composer_height(), 1)
