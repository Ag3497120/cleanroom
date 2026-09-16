"""Conversation follows the selected work; a new page is an explicit UI action."""
from unittest import TestCase, mock

from verantyx.cleanroom_tui import Cleanroom


class ContinuationRoutingContract(TestCase):
    def subject(self):
        value = mock.Mock()
        value.root = "/synthetic/project"
        value.configuration = {}
        return value

    def test_normal_input_continues_selected_work_without_keyword_inference(self):
        basis = {"run_id": "work-existing", "state": {"work_session": {"context": {}}}}
        with mock.patch("verantyx.development_console._new_work") as work:
            Cleanroom._operation(self.subject(), "work", basis, request="今度はこちらを変更して")
        self.assertEqual(work.call_args.kwargs["previous"], {"run_id": "work-existing"})
        self.assertEqual(work.call_args.kwargs["request"], "今度はこちらを変更して")

    def test_no_recorded_work_starts_without_inherited_candidate(self):
        bases = (None, {}, {"state": None, "run_id": None}, {"state": {}, "run_id": None},
                 {"state": {"work_session": {"context": {}}}, "run_id": None})
        for action in ("work", "work-notebook"):
            for basis in bases:
                with self.subTest(action=action, basis=basis):
                    with mock.patch("verantyx.development_console._new_work") as work:
                        Cleanroom._operation(self.subject(), action, basis, request="Make something useful")
                    work.assert_called_once()
                    self.assertIsNone(work.call_args.kwargs["previous"])

    def test_new_page_never_implicitly_continues_selected_work(self):
        basis = {"run_id": "work-existing", "state": {"work_session": {"context": {}}}}
        with mock.patch("verantyx.development_console._new_work") as work:
            Cleanroom._operation(self.subject(), "new-work", basis)
        self.assertNotIn("previous", work.call_args.kwargs)
