"""Live conversation, sequential work queue and non-modal change reviews."""
import math
import os
import time
import uuid
from collections import deque
from concurrent.futures import Future
from copy import deepcopy

from .conversation_view import Conversation, LineStyles
from .errors import LedgerError


WORK_ACTIONS = {"work", "new-work", "work-notebook"}


class ConversationUX:
    def _init_conversation(self):
        self.conversation = Conversation()
        self.chat_lexer, self.owner_lexer = LineStyles(), LineStyles()
        self.active_action = None
        self.active_ticket = None
        self.active_attachments = []
        self.run_input = None
        self.scheduled = deque()
        self.queue_paused = False
        self.model_waiting = False
        self._observed_chat = None

    def _locale(self):
        return self.configuration.get("ui", {}).get("locale", "en")

    def _chat_width(self):
        return self._pane_width("agent")

    def _primary_answer(self):
        if self.settings_active or self.info_text is not None or self.volatile_answer is not None or self.practice:
            self.chat_lexer.rows = []
            return super()._primary_answer()
        state = (self.view or {}).get("state") or {}
        marker = (state.get("run_id"), state.get("revision"))
        if marker != self._observed_chat:
            self.conversation.observe(state)
            self._observed_chat = marker
        if not self.conversation.groups and not state.get("work_session"):
            self.chat_lexer.rows = []
            return super()._primary_answer()
        return self.conversation.render(self._chat_width(), self._locale(), self.chat_lexer)

    def _work_indicator(self):
        if self.busy and self.active_action == "insight-question":
            return self._live_indicator()
        if not self.busy or self.active_action not in WORK_ACTIONS:
            return ""
        if self.question is not None:
            return self._ux("owner_question")
        mark = "*" if os.environ.get("VERANTYX_REDUCE_MOTION") == "1" else "|/-\\"[int(time.monotonic() * 4) % 4]
        return mark + " " + self._ux("model_running" if self.model_waiting else "working") + " / " + self._live_indicator()

    def _agent_input_style(self):
        if ("NO_COLOR" in os.environ or not self.busy or self.active_action not in WORK_ACTIONS
                or self.question is not None):
            return ""
        level = 0.35 if os.environ.get("VERANTYX_REDUCE_MOTION") == "1" else (math.sin(time.monotonic() * 2.0) + 1) / 2
        rgb = tuple(int(low + (high - low) * level) for low, high in ((24, 35), (37, 57), (46, 64)))
        return "bg:#%02x%02x%02x fg:#eef4f3" % rgb

    def _picker_active(self):
        if self.picker is None:
            return False
        return (not self.picker.get("inline") or
                self.app.layout.has_focus(self.input) or self.app.layout.has_focus(self.menu_control))

    def _inline_choice(self):
        return self.picker is not None and (self.settings_active or self.picker.get("inline", False))

    def _offer_work_input(self, value, buffer):
        if self.active_action not in WORK_ACTIONS or self.run_input is None:
            self._log(self._tr("Finish the current operation first; the draft is retained.",
                               "現在の操作が終わるまで下書きを保持します。"))
            return
        from .cleanroom_owner import selected_references, expand_request
        references = selected_references(value, self.reference_bindings)
        try:
            expanded = expand_request(value, references)
        except LedgerError:
            self._log(self._ux("queue_full"))
            return
        if len(self.scheduled) >= 12 or len(expanded) > 16000:
            self._log(self._ux("queue_full"))
            return
        identity = uuid.uuid4().hex
        queued = {"request": value, "owner_references": deepcopy(references),
                  "attachments": list(self.attachment_queue), "_chat_ticket": identity}
        def selected(choice):
            if choice is None:
                return
            self.info_text, self.volatile_answer = None, None
            self.volatile_history.clear()
            if choice == "now":
                row = self.run_input.submit(expanded, value, identity) if self.run_input else None
                if row:
                    self.conversation.instruction(self.active_ticket, row)
                else:
                    self.scheduled.append(queued)
                    self.conversation.start(identity, value, "queued")
                    self.queue_paused = True
                    self._log(self._ux("queue_fallback"))
            else:
                self.scheduled.append(queued)
                self.conversation.start(identity, value, "queued")
            self.recall.record("agent", value)
            if buffer.text.strip() == value:
                buffer.reset()
            self._render()
        choices = [("queue", self._ux("queue_later"))]
        # New attachments require the next task's own send-scope approval.
        if list(self.attachment_queue) == self.active_attachments:
            choices.append(("now", self._ux("steer_now")))
        self._show_picker(self._ux("queue_choice"), choices, selected, inline=True,
                          descriptions={"queue": self._ux("queue_detail"), "now": self._ux("steer_detail")})

    def _start_chat_work(self, action, kwargs):
        from .work_input import WorkInput
        self.active_action = action
        self.model_waiting = False
        self.run_input = None
        self.active_ticket = None
        if action not in WORK_ACTIONS:
            return
        self._refresh_model_label()
        ticket = kwargs.pop("_chat_ticket", None) or uuid.uuid4().hex
        self.active_ticket = ticket
        self.active_attachments = list(kwargs.get("attachments", []))
        if kwargs.get("request"):
            self.conversation.start(ticket, kwargs["request"])
        def started(run_id):
            self.loop.call_soon_threadsafe(self._bind_chat_run, ticket, run_id, kwargs.get("request", ""))
        def answered(row):
            self.loop.call_soon_threadsafe(self._question_finished, row)
        self.run_input = WorkInput(started, answered)

    def _bind_chat_run(self, ticket, run_id, request):
        if self.closed:
            return
        if self.conversation.get(ticket) is None and request:
            self.conversation.start(ticket, request)
        self.conversation.bind(ticket, run_id)
        self._begin_run(run_id, request)

    def _finish_chat_work(self, action, result, inbox, ticket):
        if action not in WORK_ACTIONS:
            return
        if isinstance(result, dict):
            if result.get("run_id"):
                self.conversation.bind(ticket, result["run_id"])
            self.conversation.observe(result.get("state") or {})
        unsent = inbox.close() if inbox else []
        if inbox is not None:
            self.live_deferred.extend(inbox.pending_questions())
        for row in unsent:
            self.conversation.remove_pending(ticket, row["id"])
            if self.exit_after_work:
                continue
            # Retain the expanded reference text, not an unstated re-selection.
            queued = {"request": row["text"], "owner_references": [], "attachments": [],
                      "_chat_ticket": row["id"]}
            self.scheduled.append(queued)
            self.conversation.start(row["id"], row["user_text"], "queued")
        succeeded = isinstance(result, dict) and (result.get("work") or {}).get("status") == "SUCCEEDED"
        if self.scheduled and (not succeeded or unsent):
            self.queue_paused = True
        if unsent and not self.exit_after_work:
            self._log(self._ux("queue_fallback"))
        if self.queue_paused and self.scheduled:
            self._log(self._ux("queue_paused"))
        self.run_input = None
        self.model_waiting = False

    def _start_next_queued(self):
        if (self.closed or self.busy or self.question is not None or self.picker is not None
                or self.exit_after_work or self.queue_paused or self.read_error or not self.scheduled
                or self.settings_active or self.practice):
            return
        row = self.scheduled.popleft()
        self.info_text = None
        self.volatile_answer = None
        self.start_action("work", **row)

    def _queue_menu(self):
        if not self.scheduled:
            self._log(self._ux("queue_empty"))
            return
        choices = []
        if not self.busy:
            choices.append(("resume", self._ux("queue_resume")))
        choices += [("clear", self._ux("queue_clear"))]
        descriptions = {"resume": self._ux("queue_detail"), "clear": self._ux("queue_close")}
        for row in self.scheduled:
            key = "remove:" + row["_chat_ticket"]
            choices.append((key, "- " + row["request"].splitlines()[0][:90]))
            descriptions[key] = row["request"]
        def selected(choice):
            if choice == "resume":
                self.queue_paused = False
                self._start_next_queued()
            elif choice == "clear":
                for row in self.scheduled:
                    self.conversation.remove(row["_chat_ticket"])
                self.scheduled.clear()
                self.queue_paused = False
            elif choice and choice.startswith("remove:"):
                identity = choice.split(":", 1)[1]
                self.scheduled = deque(row for row in self.scheduled if row["_chat_ticket"] != identity)
                self.conversation.remove(identity)
            self._render()
        self._show_picker("/queue", choices, selected, descriptions=descriptions, inline=True)

    def _review_status(self):
        if self.question is not None and getattr(self.question, "preview", None) is not None:
            return self._ux("review_wait")
        return ""

    def review_change(self, preview):
        from .cleanroom_tui import Question
        from .session_text import t
        lang = self._locale()
        question = Question(
            self._ux("change_title") + ": " + preview["path"], Future(),
            choices=[("allow", t("allow_once", lang)), ("workspace", t("allow_workspace", lang)),
                     ("permanent", t("allow_permanent", lang)), ("deny", t("deny", lang))],
            descriptions={"allow": t("once_detail", lang), "workspace": t("workspace_detail", lang),
                          "permanent": t("permanent_detail", lang), "deny": t("deny_detail", lang)},
            inline=True, preview=deepcopy(preview))
        self.loop.call_soon_threadsafe(self._present_question, question)
        return question.answer.result()

    def notice_change(self, preview, mode):
        def display():
            self.conversation.change(preview, mode)
            self._render()
        self.loop.call_soon_threadsafe(display)

    def _confirm_queue_exit(self):
        if not self.scheduled and not (self.run_input and self.run_input.peek()):
            return False
        if self.question is not None:
            # Do not overwrite a host confirmation with a second picker.
            self._cancel_question()
        def selected(choice):
            if choice == "discard":
                self.scheduled.clear()
                self.request_exit(discard_queue=True)
        self._show_picker(self._ux("queue_close"), [("discard", self._ux("queue_discard"))],
                          selected, descriptions={"discard": self._ux("queue_detail")}, inline=True)
        return True
