"""Small, optional live cards and ID-addressed questions without changing work."""
import asyncio
from collections import deque

from . import work_pulse
from .presentation import safe_text


class LiveLearningUX:
    def _init_live_learning(self):
        self.live_insights = []
        self.live_visible_ids = set()
        self.live_seen_ids = set()
        self.live_question_cards = {}
        self.live_deferred = deque()
        self.live_pulse = {"available": False}
        self.live_explicit = False
        self.live_offset = 0

    def _live_command(self, value, buffer):
        if self.practice or self.readonly or self.settings_active:
            return False
        if value in ("/insights", "/verantyx insights"):
            self.live_explicit = True
            self.live_offset = 0
            self.preview = None
            self.growth_selection = None
            buffer.reset()
            asyncio.create_task(self._refresh())
            return True
        parsed = work_pulse.parse_reference(value)
        if parsed is None:
            return False
        identity, question = parsed
        # Unknown ID-looking input is still normal work, not a semantic refusal.
        note = work_pulse.resolve(self.root, identity)
        if note is None or self.question is not None:
            return False
        self.info_text = None
        self.volatile_answer = None
        if self.busy:
            row = self.run_input.submit_question(note["id"], question) if self.run_input else None
            if row is None:
                self._log(self._st("insight_wait"))
                return True
            self._question_pending(row)
        else:
            import uuid
            row = {"id": uuid.uuid4().hex, "learning_id": note["id"], "question": question}
            self._question_pending(row)
            self.start_action("insight-question", identity=note["id"], question=question, key=row["id"],
                              run_id=self.selected)
        self.recall.record("agent", value)
        buffer.reset()
        self._render()
        return True

    def _question_pending(self, row):
        group = self.conversation.start("insight:" + row["id"], row["learning_id"] + (" " + row["question"] if row["question"] else ""))
        group["side_answer"] = self._st("insight_queued")
        self.live_question_cards[row["id"]] = group["id"]
        if len(self.live_question_cards) > 100:
            self.live_question_cards.pop(next(iter(self.live_question_cards)))

    def _question_finished(self, row):
        group = self.conversation.get(self.live_question_cards.get(row["id"], "insight:" + row["id"]))
        if group is not None:
            group["side_answer"] = (row.get("answer") if row.get("status") == "ANSWERED" else
                                    self._st("insight_failed", code=row.get("reason", "UNKNOWN")))
            group["side_label"] = self._st("insight_answer")
        self._render()

    def _continue_live_questions(self):
        if self.busy or self.exit_after_work or not self.live_deferred:
            return False
        row = self.live_deferred.popleft()
        self.start_action("insight-question", identity=row["learning_id"], question=row["question"],
                          key=row["id"], run_id=self.selected)
        return True

    async def _refresh_live_learning(self):
        if self.practice or self.readonly:
            return
        room = self.console_sessions["room"]["id"]
        root, run_id = self.root, self.selected
        explicit, offset = self.live_explicit, self.live_offset
        visible, seen = set(self.live_visible_ids), set(self.live_seen_ids)
        automatic = (self.busy and self.active_action in ("work", "work-notebook", "new-work")
                     and not ((self.view or {}).get("state") or {}).get("work_result"))
        def read():
            rows = work_pulse.notes(root, room, limit=20 if explicit else 8, offset=offset)
            for row in reversed(rows):
                if not automatic or row["run_id"] != run_id or explicit or row["id"] in visible or row["id"] in seen:
                    continue
                if work_pulse.reserve(root, row):
                    visible.add(row["id"])
                seen.add(row["id"])
            return rows, visible, seen, work_pulse.pulse(root, run_id) if run_id else {"available": False}
        rows, visible, seen, pulse = await self.loop.run_in_executor(self.read_executor, read)
        if room != self.console_sessions["room"]["id"]:
            return
        available = {row["id"] for row in rows}
        self.live_insights = rows
        self.live_visible_ids = visible & available
        self.live_seen_ids = seen & available
        self.live_pulse = pulse
        if self.owner_view is not None:
            self.owner_view["live_insights"] = [row for row in rows if explicit or row["id"] in visible]
            self.owner_view["insights_available"] = bool(rows)
            self.owner_view["insights_explicit"] = explicit
            self.owner_view["work_pulse"] = pulse if self.busy else {"available": False}

    def _live_indicator(self):
        if not self.busy:
            return ""
        if self.active_action == "insight-question":
            return self._st("insight_running")
        pulse = self.live_pulse
        if not pulse.get("available"):
            return self._st("eta_unknown")
        if pulse["overdue"]:
            return self._st("eta_overdue")
        result = self._st("eta", low=pulse["remaining_min"], high=pulse["remaining_max"])
        if pulse.get("question_running"):
            result += " / " + self._st("insight_running")
        elif pulse.get("needs_update"):
            result += " / " + self._st("eta_update")
        return safe_text(result)
