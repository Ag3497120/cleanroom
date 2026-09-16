"""Empty Enter answers a displayed question, not a different pane."""
from unittest import TestCase, mock

from verantyx.cleanroom_tui import Cleanroom


class EnterRoutingContract(TestCase):
    def subject(self):
        instance = mock.Mock()
        instance.readonly = False
        instance.busy = True
        instance.question = object()
        return instance

    def test_pending_question_receives_empty_default(self):
        instance = self.subject()
        Cleanroom._submit(instance, mock.Mock(text=""))
        instance._answer.assert_called_once_with("")
        instance._cycle_inputs.assert_not_called()

    def test_idle_empty_enter_still_cycles_to_owner(self):
        instance = self.subject()
        instance.question = None
        instance.busy = False
        Cleanroom._submit(instance, mock.Mock(text=""))
        instance._cycle_inputs.assert_called_once_with()
        instance._answer.assert_not_called()

    def test_question_receives_explicit_response(self):
        instance = self.subject()
        Cleanroom._submit(instance, mock.Mock(text="n"))
        instance._answer.assert_called_once_with("n")
        instance._cycle_inputs.assert_not_called()

    def test_readonly_view_cannot_answer(self):
        instance = self.subject()
        instance.readonly = True
        Cleanroom._submit(instance, mock.Mock(text=""))
        instance._answer.assert_not_called()
        instance._cycle_inputs.assert_not_called()
