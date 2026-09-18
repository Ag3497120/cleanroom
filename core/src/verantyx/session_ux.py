"""Independent Owner rooms and Agent conversations, plus a non-recording tour."""
import asyncio
from concurrent.futures import Future
from copy import deepcopy
import shlex

from prompt_toolkit.completion import Completer, Completion

from . import session_store
from .session_text import t
from .errors import LedgerError
from .presentation import safe_text


class SessionCompleter(Completer):
    def __init__(self, session, inner=None):
        self.session, self.inner = session, inner

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/") and not text.startswith("//"):
            commands = ["/verantyx new", "/verantyx cleanroom", "/verantyx compact",
                        "/verantyx models", "/verantyx setup context", "/verantyx setup permissions",
                        "/help", "/tutorial", "/queue", "/approvals", "/insights",
                        "/web", "/browse", "/tools", "/usage", "/context", "/timeout 1800", "/copy", "/latest", "/fullscreen", "/split"]
            names = [row["name"] for row in self.session.room_catalog]
            commands += ["/" + name for name in names]
            commands += ["/verantyx cleanroom " + shlex.quote(name) for name in names]
            for command in commands:
                if command.casefold().startswith(text.casefold()):
                    yield Completion(command, start_position=-len(text), display=safe_text(command))
            return
        if self.inner is not None:
            yield from self.inner.get_completions(document, complete_event)


class SessionUX:
    def _st(self, key, **values):
        return t(key, self._locale(), **values)

    def _init_sessions(self):
        self.console_sessions = (session_store.current(self.root) if not self.practice and not self.readonly else {
            "agent": {"id": "demo", "name": "Agent"}, "room": {"id": "demo", "name": "Cleanroom"}})
        self.room_catalog = session_store.rooms(self.root) if not self.practice and not self.readonly else []
        self.room_drafts = {}
        self.owner_view = None
        self.session_bootstrapped = False
        self.tour_step = 0
        self.tour_launch_real = False
        self._init_live_learning()
        self.memo_offset = 0
        self.memo_query = ""
        self.archive_loading = False

    def _session_caption(self, plane):
        current = self.console_sessions["agent" if plane == "agent" else "room"]
        return safe_text(current["name"])

    def _session_busy(self):
        return (self.busy or bool(self.scheduled) or
                (self.note_task is not None and not self.note_task.done()))

    def _session_control(self, value, buffer, plane):
        if self.practice:
            if plane == "agent" and value.strip() == "verantyx":
                self.tour_launch_real = True
                self._handle_control("/done", buffer)
                return True
            return False
        if not value.startswith("/") or value.startswith("//") or self.settings_active:
            return False
        head, _, rest = value.partition(" ")
        head, rest = head.casefold(), rest.strip()
        command, name = None, ""
        if head in ("/verantyx", "/vernatyx"):
            token, _, tail = rest.partition(" ")
            if token.casefold() in ("new", "compact", "cleanroom"):
                command, name = token.casefold(), tail.strip()
        elif head in ("/new", "/compact", "/cleanroom", "/timeout"):
            command, name = head[1:], rest
        else:
            name = value[1:].strip()
            if any(row["name"].casefold() == name.casefold() for row in self.room_catalog):
                command = "cleanroom"
        if command is None:
            return False
        if self._session_busy():
            self._log(self._st("busy_session"))
            return True
        if command == "cleanroom" and name[:1] in ("'", '"'):
            try:
                parsed = shlex.split(name)
                name = parsed[0] if len(parsed) == 1 else name
            except ValueError:
                self._log(self._st("name_invalid"))
                return True
        buffer.reset()
        self.info_text = None
        self.start_action("session-control", command=command, name=name, plane=plane)
        return True

    def _session_choice(self, title, choices, descriptions=None):
        from .cleanroom_tui import Question
        question = Question(title, Future(), choices=choices, descriptions=descriptions or {}, inline=True)
        self.loop.call_soon_threadsafe(self._present_question, question)
        return question.answer.result()

    def _session_operation(self, command, name="", plane="agent"):
        if command == "timeout":
            from .model_preferences import set_timeout
            from .development_console import _mutate
            if name and not name.isdecimal():
                raise LedgerError("ARGUMENTS")
            result = _mutate(self.root, self.configuration, set_timeout, int(name) if name else None)
            self.loop.call_soon_threadsafe(self._session_message,
                self._tr("Model timeout: ", "モデルの待ち時間: ") + str(result["timeout"]) + "s"
                + " / " + self._tr("Maximum: ", "設定上限: ") + str(result["maximum"]) + "s\n/timeout 1800")
            return result
        if command == "compact":
            from .session_context import compact_session
            from .development_console import _mutate
            choice = self._session_choice(self._st("compact_confirm"),
                    [("yes", self._st("confirm")), ("no", self._st("cancel"))],
                    {"yes": self._st("compact_detail"), "no": self._st("cancel")})
            if choice != "yes":
                return None
            result = _mutate(self.root, self.configuration, compact_session,
                             agent=self.console_sessions["agent"]["id"])
            message = self._st("compact_empty" if result["status"] == "EMPTY" else
                               "compact_failed" if not result.get("ok") else
                               "compact_partial" if result["status"] == "PARTIAL" else "compact_saved")
            if result.get("remaining_events"):
                message += "\n" + self._st("remaining_sources", count=result["remaining_events"])
            self.loop.call_soon_threadsafe(self._session_message, message)
            return result
        if command == "new":
            owner = plane == "owner"
            choice = self._session_choice(self._st("new_room" if owner else "new_agent"),
                    [("yes", self._st("confirm")), ("no", self._st("cancel"))],
                    {"yes": self._st("new_room" if owner else "new_agent"), "no": self._st("cancel")})
            if choice != "yes":
                return None
            if owner and not name:
                name = self.ask(self._st("name_prompt"))
                if not name.strip():
                    return None
            try:
                value = session_store.new_room(self.root, name) if owner else session_store.new_agent(self.root, name or None)
            except LedgerError:
                self.loop.call_soon_threadsafe(self._session_message, self._st("name_invalid"))
                return None
            self.loop.call_soon_threadsafe(self._adopt_sessions, value)
            return None
        self.room_catalog = session_store.rooms(self.root)
        if not name:
            lines = [self._st("room_list"), ""]
            lines.extend(("* " if row["active"] else "  ") + "/" + row["name"] + "  " + row["created_at"]
                         for row in self.room_catalog)
            self.loop.call_soon_threadsafe(self._session_message, "\n".join(lines))
            return None
        row = next((row for row in self.room_catalog if row["name"].casefold() == name.casefold()), None)
        if row is None:
            self.loop.call_soon_threadsafe(self._session_message, self._st("name_invalid"))
            return None
        while True:
            choice = self._session_choice(self._st("switch_room", name=row["name"]),
                      [("switch", self._st("switch")), ("cancel", self._st("cancel")),
                       ("rename", self._st("rename"))],
                      {"switch": self._st("switch_room", name=row["name"]), "cancel": self._st("cancel"),
                       "rename": self._st("name_prompt")})
            if choice == "switch":
                self.loop.call_soon_threadsafe(self._adopt_sessions, session_store.switch_room(self.root, row["id"]))
                return None
            if choice != "rename":
                return None
            new_name = self.ask(self._st("name_prompt"))
            if not new_name.strip():
                continue
            try:
                session_store.rename_room(self.root, row["id"], new_name)
                row = next(item for item in session_store.rooms(self.root) if item["id"] == row["id"])
                self.loop.call_soon_threadsafe(self._adopt_sessions, session_store.current(self.root))
            except LedgerError:
                self.notice(self._st("name_invalid"))

    def _session_message(self, text):
        self.info_text = text
        self._render()

    def _adopt_sessions(self, value):
        previous = self.console_sessions
        if previous["agent"]["id"] != value["agent"]["id"]:
            from .conversation_view import Conversation
            self.conversation = Conversation()
            self.selected = None
            self.view = None
            self.pending_request = None
            self.reference_bindings.clear()
            self.volatile_history.clear()
            self.volatile_answer = None
            self.input.buffer.reset()
            self.recall.entries["agent"].clear()
            self.recall.positions.pop("agent", None)
            self.recall.drafts.pop("agent", None)
        if previous["room"]["id"] != value["room"]["id"]:
            self.owner_drafts[self.owner_mode] = self.owner_input.text
            self.room_drafts[previous["room"]["id"]] = (deepcopy(self.owner_drafts), self.owner_mode)
            self.owner_drafts, self.owner_mode = self.room_drafts.get(
                value["room"]["id"], ({"memo": "", "search": ""}, "memo"))
            self.owner_input.text = self.owner_drafts[self.owner_mode]
            self.owner_view = None
            self.growth_selection = None
            self.preview = None
            self.live_explicit = False
            self.live_offset = 0
            self.live_insights = []
            self.memo_offset = 0
            self.memo_query = ""
        self.console_sessions = value
        self.room_catalog = session_store.rooms(self.root)
        self.info_text = None
        self.session_bootstrapped = False
        self._render()

    async def _read_session_views(self):
        """Agent selection and Owner room are independent subscriptions."""
        if self.readonly:
            return await self.loop.run_in_executor(self.read_executor, self.reader.read, self.selected, True)
        if not self.session_bootstrapped:
            # Import legacy records before choosing the active conversation.
            await self.loop.run_in_executor(self.read_executor, self.reader.read)
            self.console_sessions = session_store.current(self.root)
            self.room_catalog = session_store.rooms(self.root)
            ids = session_store.runs(self.root, agent=self.console_sessions["agent"]["id"])
            if self.selected is None and ids:
                self.selected = ids[-1]
            from .agent_runtime import _state
            for run_id in ids[-80:]:
                state = await self.loop.run_in_executor(self.read_executor, _state, self.root, self.configuration, run_id)
                self.conversation.observe(state)
            from .work_pulse import question_history
            questions = await self.loop.run_in_executor(self.read_executor, question_history, self.root, ids)
            for row in questions:
                self._question_pending(row)
                if row["status"] == "RUNNING":
                    row["reason"] = "PREVIOUS_RESULT_UNKNOWN"
                self._question_finished(row)
            self.session_bootstrapped = True
        room = self.console_sessions["room"]["id"]
        query = self.owner_input.text.strip() if self.owner_mode == "search" else ""
        if query != self.memo_query:
            self.memo_offset, self.memo_query = 0, query
        offset = self.memo_offset
        view = await self.loop.run_in_executor(self.read_executor,
            lambda: self.reader.read(self.selected, room_id=room, empty=self.selected is None, note_offset=offset, note_query=query))
        ids = session_store.runs(self.root, room=room)
        owner_run = self.selected if self.selected in ids else ids[-1] if ids else None
        self.owner_view = await self.loop.run_in_executor(self.read_executor,
            lambda: self.reader.read(owner_run, room_id=room, empty=owner_run is None, note_offset=offset, note_query=query))
        return view

    def _tour_hint(self, plane):
        if not self.practice:
            return ""
        target = "owner" if self.tour_step in (1, 2) else "agent"
        if plane != target:
            return ""
        key = ("tour_chat", "tour_memo", "tour_search", "tour_private", "tour_settings", "tour_complete")[min(self.tour_step, 5)]
        return self._st(key)

    def _tour_event(self, event):
        expected = ("chat", "memo", "search", "private", "settings")
        if self.practice and self.tour_step < len(expected) and event == expected[self.tour_step]:
            self.tour_step += 1

    def _archive_scroll(self, direction, window):
        if self.archive_loading or self.preview is not None or self.growth_selection is not None:
            return False
        page = (self.owner_view or self.view or {}).get("memo_page", {})
        info = window.render_info
        if info is None:
            return False
        at_end = info.last_visible_line() >= info.ui_content.line_count - 1
        at_start = info.first_visible_line() == 0
        offset, size = page.get("offset", 0), page.get("limit", 200)
        if direction > 0 and at_end and offset + size < page.get("total", 0):
            next_offset = offset + size
        elif direction < 0 and at_start and offset > 0:
            next_offset = max(0, offset - size)
        else:
            return False
        self.memo_offset = next_offset
        self.archive_loading = True
        async def move():
            try:
                await self._refresh()
                area = self.areas["owner"]
                area.buffer.cursor_position = 0 if direction > 0 else len(area.text)
                area.window.vertical_scroll = 0 if direction > 0 else max(0, area.buffer.document.line_count - 3)
                self.app.invalidate()
            finally:
                self.archive_loading = False
        asyncio.create_task(move())
        return True
