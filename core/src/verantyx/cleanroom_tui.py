from .session_ux import SessionUX
from .live_learning_ux import LiveLearningUX
"""An Agent request field and local Owner memo/search field, not two agents.

Domain mutations stay inside existing authority gates. Model work uses one
worker; another thread only reads the ledger. Terminal repainting calls no AI.
"""
import asyncio
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

from . import config
from .cleanroom_io import bind
from .cleanroom_view import Reader, layout_mode, owner_lock, public_view, publish_cursor
from .domain.codec import digest
from .errors import LedgerError
from .presentation import safe_text
from .terminal_ui import capable_terminal
from .interaction_ux import InteractionUX, SETTINGS_ACTIONS
from .interaction_text import tr
from .input_recall import InputRecall
from .conversation_ux import ConversationUX
from .reading_ux import ReadingUX, fit_text
from .web_ux import WebUX
from .activity_ux import ActivityUX
from .console_copy import ui_text


class OwnerCancelled(Exception):
    pass


@dataclass
class Question:
    title: str
    answer: Future
    choices: list | None = None
    default: str = ""
    descriptions: dict | None = None
    aliases: dict | None = None
    inline: bool = False
    preview: dict | None = None


class Cleanroom(ActivityUX, WebUX, ReadingUX, LiveLearningUX, SessionUX, ConversationUX, InteractionUX):
    def __init__(self, root, configuration, *, readonly=False, run_id=None, initial_request=None, practice=False):
        self.root, self.configuration = Path(root), configuration
        self.readonly, self.selected, self.initial_request = readonly, run_id, initial_request
        self.session_id = uuid.uuid4().hex
        self.reader = None if practice else Reader(root, configuration)
        self._init_interaction(practice)
        self._init_conversation()
        self.recall = InputRecall()
        self.read_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cleanroom-ledger")
        self.work_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cleanroom-owner")
        self.note_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cleanroom-local-note")
        self.view = None
        self.personal_view = None
        self.personal_visible = []
        self.personal_error = None
        self.busy = False
        self.phase = "idle"
        self.started = None
        self.question = None
        self.picker = None
        self.choice_index = 0
        self.saved_draft = None
        self.focus_name = "split"
        self.preview = None
        self.growth_selection = None
        self.active_input = "agent"
        self.owner_mode = "memo"
        self.owner_drafts = {"memo": "", "search": ""}
        self.reference_bindings = {}
        self.pending_request = None
        self.note_task = None
        self.note_intent = None
        self.handoff = None
        self.motion_task = None
        self.announced_growth = None
        self.view_primed = False
        self.logs = deque(maxlen=160)
        self.notes = deque(maxlen=24)
        self.read_error = None
        self.cursor_error = None
        self.exit_after_work = False
        self.closed = False
        self.last_result = None
        self.loop = None
        self.work_task = None
        self._init_sessions()
        self._init_reading()
        self._init_web()
        self._build()

    def _tr(self, en, ja):
        lang = self.configuration.get("ui", {}).get("locale", "en")
        return ja if lang == "ja" else ui_text(en, lang)

    def _build(self):
        from prompt_toolkit.application import Application
        from prompt_toolkit.completion import ConditionalCompleter
        from prompt_toolkit.data_structures import Point
        from prompt_toolkit.filters import Condition
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.layout import Layout, HSplit, VSplit, Window, DynamicContainer, ConditionalContainer, FloatContainer, Float
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.layout.dimension import Dimension
        from prompt_toolkit.layout.menus import CompletionsMenu
        from prompt_toolkit.output import ColorDepth
        from prompt_toolkit.output.defaults import create_output
        from prompt_toolkit.styles import Style
        from prompt_toolkit.widgets import Frame, Label, TextArea

        from .cleanroom_owner import OwnerCompleter
        self.output = create_output()
        self.owner_completer = OwnerCompleter(self._visible_owner_items, self.reference_bindings,
                                              locale=self.configuration.get("ui", {}).get("locale", "en"))
        from .session_ux import SessionCompleter
        completer = ConditionalCompleter(SessionCompleter(self, self.owner_completer),
                                         filter=Condition(lambda: self.question is None and not self.readonly
                                                          and not self.settings_active))
        self.input = TextArea(multiline=True, height=self._composer_height,
                              prompt="  > ", accept_handler=self._submit, wrap_lines=True,
                              completer=completer, complete_while_typing=True, focus_on_click=True)
        self.owner_input = TextArea(multiline=True, height=lambda: Dimension(min=1, max=2 if self._compact_ui() else 4),
                                    prompt="  > ", accept_handler=self._submit_owner, wrap_lines=True,
                                    completer=ConditionalCompleter(SessionCompleter(self),
                                        filter=Condition(lambda: not self.settings_active and not self.readonly)),
                                    complete_while_typing=True, focus_on_click=True)
        self.input.window.style = self._agent_input_style
        self.owner_input.window.style = self._owner_style
        self.areas = {name: TextArea(read_only=True, scrollbar=True, wrap_lines=False, focus_on_click=True)
                      for name in ("owner", "agent", "evidence", "notebook", "review")}
        self.areas["agent"].lexer = self.chat_lexer
        self.areas["owner"].lexer = self.owner_lexer
        titles = {
            "owner": lambda: self._ux("owner_title") + " / " + self._session_caption("owner"),
            "agent": lambda: self._ux("settings") if self.settings_active else self._ux("conversation") + " / " + self._session_caption("agent"),
            "evidence": lambda: self._tr("Evidence / Recorded checks", "Evidence / 記録した検査"),
            "notebook": lambda: self._tr("Notebook / What stays with you", "Notebook / 仕事から残るもの"),
            "review": lambda: self._tr("Review / Your choices", "Review / 人間に必要なこと"),
        }
        frames = {name: Frame(area, title=titles[name], width=Dimension(weight=1))
                  for name, area in self.areas.items()}
        self.frames = frames
        self.system_area = TextArea(read_only=True, scrollbar=True, wrap_lines=False,
                                    focus_on_click=True, style="class:muted",
                                    height=lambda: Dimension(min=1, max=(6 if self._compact_ui() else 8)
                                                             if self.details_visible else 2))
        self.menu_control = FormattedTextControl(self._menu_text, focusable=True,
                                                 get_cursor_position=lambda: Point(0, self.choice_index))
        self.menu_window = Window(self.menu_control, wrap_lines=False,
                                  height=lambda: Dimension(min=2, max=4 if self._compact_ui() else 8))
        self.choice_body = HSplit([
            Window(FormattedTextControl(self._question_title), wrap_lines=True,
                   height=lambda: Dimension(min=1, max=2 if self._compact_ui() else 3)),
            self.menu_window,
            Window(FormattedTextControl(self._menu_detail),
                   height=lambda: Dimension(min=1, max=3 if self._compact_ui() else 4),
                   wrap_lines=True, style="class:detail"),
            Window(FormattedTextControl(lambda: self._ux("keys")),
                   height=lambda: 1 if self._compact_ui() else 2, wrap_lines=True, style="class:muted"),
        ])
        self.dialog = Frame(self.choice_body, title=self._tr("One choice / Yours to make", "One choice / あなたの選択"), width=Dimension(preferred=76, max=96))
        growth_margin = ConditionalContainer(Frame(HSplit([
            Window(FormattedTextControl(self._growth_card), wrap_lines=True, height=Dimension(min=2, max=4)),
            Window(FormattedTextControl(self._growth_actions), wrap_lines=True, height=Dimension(min=1, max=2)),
        ]), title=self._tr("Keep one insight / Only when you want to", "Keep one insight / 今回持ち帰る理解")), filter=Condition(lambda: self._growth_visible() and not self._compact_ui()))
        owner_field = ConditionalContainer(Frame(HSplit([
            ConditionalContainer(Window(FormattedTextControl(self._owner_title), height=1, style=self._owner_style),
                                 filter=Condition(lambda: not self._compact_ui())),
            self.owner_input,
        ]), title=lambda: self._rt("memo" if self.owner_mode == "memo" else "search")
            if self._compact_ui() else "Owner / local only"), filter=Condition(lambda: not self.readonly))
        self.agent_column = HSplit([
            DynamicContainer(lambda: self.areas["agent"] if self._compact_ui() else frames["agent"]),
            ConditionalContainer(Frame(self.system_area, title=lambda: self._ux("activity")),
                                 filter=Condition(lambda: self.details_visible)),
            ConditionalContainer(Frame(HSplit([
                Window(FormattedTextControl(self._activity_line), height=1),
                ConditionalContainer(Window(FormattedTextControl(self._activity_detail), height=1,
                                            style="class:activity.meta"),
                                     filter=Condition(lambda: not self._compact_ui())),
                ConditionalContainer(Window(FormattedTextControl(self._input_title),
                                            height=Dimension(min=1, max=3), wrap_lines=True,
                                            style="class:activity.waiting"),
                                     filter=Condition(lambda: self.question is not None and not self._inline_choice())),
                ConditionalContainer(self.choice_body, filter=Condition(self._inline_choice)),
                self.input,
                Window(FormattedTextControl(self._context_line), height=1, style="class:activity.meta"),
            ]), title=self._tr("Message", "メッセージ")),
                                 filter=Condition(lambda: not self.readonly)),
            ConditionalContainer(Window(FormattedTextControl(lambda: self._tour_hint("agent")), height=3,
                                        wrap_lines=True, style="class:warning"),
                                 filter=Condition(lambda: bool(self._tour_hint("agent")))),
            ConditionalContainer(Window(FormattedTextControl(lambda: self._st("tour_start")), height=2,
                                        wrap_lines=True, style="class:muted"),
                                 filter=Condition(lambda: self.practice)),
        ], width=Dimension(weight=1))
        self.owner_column = HSplit([
            ConditionalContainer(Window(FormattedTextControl(lambda: self._tour_hint("owner")), height=3, wrap_lines=True, style="class:warning"), filter=Condition(lambda: bool(self._tour_hint("owner")))),
            owner_field,
            ConditionalContainer(Window(FormattedTextControl(self._review_status), wrap_lines=True,
                                        height=lambda: Dimension(min=1, max=1 if self._compact_ui() else 3), style="class:warning"),
                                 filter=Condition(lambda: bool(self._review_status()))),
            ConditionalContainer(Window(FormattedTextControl(self._handoff_text),
                                        height=Dimension(min=1, max=3), wrap_lines=True, style="class:handoff"),
                                 filter=Condition(lambda: self.handoff is not None and not self._compact_ui())),
            DynamicContainer(lambda: self.areas[self._owner_page()] if self._compact_ui()
                             else self.frames[self._owner_page()]),
            growth_margin,
        ], width=Dimension(weight=1))
        def outlined(body, name):
            style = lambda: self._pane_border_style(name)
            return HSplit([
                VSplit([Window(char="━", width=2, height=1, style=style),
                        Window(FormattedTextControl(lambda: " " + self._pane_caption(name) + " "),
                               height=1, style=style),
                        Window(char="━", width=2, height=1, style=style)]),
                VSplit([Window(char="┃", width=1, style=style), body,
                        Window(char="┃", width=1, style=style)]),
                Window(char="━", height=1, style=style),
            ], width=lambda: Dimension.exact(self._column_width(name)))
        self.agent_column = outlined(self.agent_column, "agent")
        self.owner_column = outlined(self.owner_column, "owner")
        self.split_side = VSplit([self.agent_column,
                                 Window(FormattedTextControl(self._vertical_boundary), width=3, style="class:boundary"),
                                 self.owner_column])
        self.split_stack = HSplit([self.agent_column,
                                  Window(FormattedTextControl(self._horizontal_boundary), height=1, style="class:boundary"),
                                  self.owner_column])
        content = HSplit([
            Window(FormattedTextControl(self._header), height=lambda: 2 if self._compact_ui() else 4, style="class:header"),
            ConditionalContainer(Window(FormattedTextControl(self._tabs), height=1),
                                 filter=Condition(lambda: not self._compact_ui())),
            DynamicContainer(self._body),
            Window(FormattedTextControl(self._footer), height=2,
                   wrap_lines=False, style="class:muted"),
        ])
        root = FloatContainer(content=content, floats=[Float(content=ConditionalContainer(
            self.dialog, filter=Condition(lambda: self.picker is not None and not self._inline_choice()))),
            Float(xcursor=True, ycursor=True, content=ConditionalContainer(CompletionsMenu(max_height=8, scroll_offset=1),
                filter=Condition(lambda: self.picker is None and not self.readonly
                                 and self.app.layout.has_focus(self.input))))])
        bindings = KeyBindings()
        picking = Condition(self._picker_active)

        @bindings.add("up", filter=picking, eager=True)
        def up(event):
            self.choice_index = max(0, self.choice_index - 1)

        @bindings.add("down", filter=picking, eager=True)
        def down(event):
            self.choice_index = min(len(self.picker["choices"]) - 1, self.choice_index + 1)

        @bindings.add("enter", filter=picking, eager=True)
        def choose(event):
            if self.settings_active and self.input.text.strip():
                self.input.buffer.validate_and_handle()
                return
            picker = self.picker
            value = picker["choices"][self.choice_index][0]
            self.picker = None
            self._focus_input()
            picker["callback"](value)

        @bindings.add("enter", filter=Condition(lambda: not self._picker_active() and not self.readonly and self.app.layout.has_focus(self.input)))
        def submit(event):
            if self.input.buffer.complete_state is not None:
                self._accept_owner_completion()
                return
            self.input.buffer.validate_and_handle()

        @bindings.add("enter", filter=Condition(lambda: not self._picker_active() and not self.readonly and self.app.layout.has_focus(self.owner_input)))
        def submit_owner(event):
            if self.owner_input.buffer.complete_state is not None:
                state = self.owner_input.buffer.complete_state
                if state.completions:
                    self.owner_input.buffer.apply_completion(state.current_completion or state.completions[0])
                return
            self.owner_input.buffer.validate_and_handle()

        def eventless_field(session):
            return session.owner_input if session.app.layout.has_focus(session.owner_input) else session.input

        completing = Condition(lambda: self.picker is None and self.question is None and not self.readonly
                               and eventless_field(self).buffer.complete_state is not None)

        @bindings.add("down", filter=completing, eager=True)
        def next_reference(event):
            eventless_field(self).buffer.complete_next()

        @bindings.add("up", filter=completing, eager=True)
        def previous_reference(event):
            eventless_field(self).buffer.complete_previous()

        recalling = Condition(lambda: not self._picker_active()
                              and (self.question is None or (self.active_input == "owner" and self._inline_choice()))
                              and not self.readonly
                              and not self.settings_active and not self.practice
                              and (self.app.layout.has_focus(self.input) or self.app.layout.has_focus(self.owner_input))
                              and eventless_field(self).buffer.complete_state is None)

        @bindings.add("up", filter=recalling)
        def recall_previous(event):
            field = self.owner_input if self.app.layout.has_focus(self.owner_input) else self.input
            key = self.owner_mode if field is self.owner_input else "agent"
            if field.buffer.document.cursor_position_row != 0 or not self.recall.move(field, key, -1):
                field.buffer.cursor_up()

        @bindings.add("down", filter=recalling)
        def recall_next(event):
            field = self.owner_input if self.app.layout.has_focus(self.owner_input) else self.input
            key = self.owner_mode if field is self.owner_input else "agent"
            document = field.buffer.document
            if document.cursor_position_row != document.line_count - 1 or not self.recall.move(field, key, 1):
                field.buffer.cursor_down()

        @bindings.add("escape", "enter", filter=Condition(lambda: not self.readonly))
        @bindings.add("c-j", filter=Condition(lambda: not self.readonly))
        def newline(event):
            if not self._picker_active():
                field = self.owner_input if self.app.layout.has_focus(self.owner_input) else self.input
                field.buffer.insert_text("\n")

        @bindings.add("f2", eager=True)
        def menu(event):
            if self.picker is None:
                self.open_menu()

        @bindings.add("tab", eager=True)
        def complete_reference(event):
            if self._picker_active():
                self.choice_index = (self.choice_index + 1) % len(self.picker["choices"])
            elif not self.readonly and self.app.layout.has_focus(self.owner_input):
                field = self.owner_input.buffer
                if field.complete_state is not None and field.complete_state.completions:
                    field.apply_completion(field.complete_state.current_completion or field.complete_state.completions[0])
                else:
                    field.start_completion(select_first=False)
            elif not self.readonly and self.app.layout.has_focus(self.input) and self.question is None:
                if self.input.buffer.complete_state is not None:
                    self._accept_owner_completion()
                else:
                    self.input.buffer.start_completion(select_first=False)

        @bindings.add("escape", eager=False)
        def back(event):
            if self._clear_reading_selection():
                self._focus_input()
                return
            if self.owner_input.buffer.complete_state is not None and self.picker is None:
                self.owner_input.buffer.cancel_completion()
            elif self.input.buffer.complete_state is not None and self.picker is None:
                self.input.buffer.cancel_completion()
            elif self._picker_active():
                picker, self.picker = self.picker, None
                self._focus_input()
                picker["callback"](None)
            elif self.question is not None and (not self.question.inline or self.active_input == "agent"):
                self._cancel_question()
            elif self.growth_selection is not None:
                self.growth_selection = None
                self._render()
            elif self.preview is not None:
                self.preview = None
                self._render()
            else:
                self._focus_input()

        for key, name in (("0", "split"), ("1", "owner"), ("2", "agent"), ("3", "evidence"), ("4", "notebook")):
            def focus(event, name=name):
                if self.picker is None:
                    self.focus_name = name
                    self.reading_fullscreen = name != "split"
                    self._focus_input()
            bindings.add("escape", key)(focus)

        @bindings.add("f3", eager=True)
        def inspect(event):
            if self.picker is None:
                name = self.focus_name if self.focus_name in self.areas else self.active_input
                self.app.layout.focus(self.areas[name])

        @bindings.add("f4", eager=True)
        def grow(event):
            if self.picker is None and self.question is None and not self.busy:
                if self.growth_selection is not None and not self.readonly:
                    self.open_growth_actions()
                else:
                    self.open_growth()

        @bindings.add("f8", eager=True)
        def next_owner_match(event):
            self._jump_owner_match(1)

        @bindings.add("escape", "f8", eager=True)
        def previous_owner_match(event):
            self._jump_owner_match(-1)

        @bindings.add("c-c", eager=True)
        def interrupt(event):
            if self.native_selection or self._copy_reading(only_selection=True):
                return
            if self.question is not None and (not self.question.inline or self.active_input == "agent"):
                self._cancel_question()
            elif not self.readonly and (self.owner_input if self.active_input == "owner" else self.input).text:
                (self.owner_input if self.active_input == "owner" else self.input).buffer.reset()
            else:
                self.request_exit()

        @bindings.add("c-d", eager=True)
        def exit_requested(event):
            self.request_exit()

        style = Style.from_dict({
            "header": "bold", "frame.border": "#698b7a", "frame.label": "bold #94ae8b",
            "muted": "#8b9289", "tab.active": "bold underline #94ae8b", "tab": "#8b9289",
            "menu.selected": "reverse bold", "warning": "bold #d3a66e", "text-area": "",
            "selected-text": "bg:#527976 fg:#ffffff",
            "owner.memo": "bg:#483619 fg:#ffe6a1", "owner.search": "bg:#153d2b fg:#bceccc",
            "pane.inactive": "#536770", "pane.agent": "bold #92c7c2",
            "pane.memo": "bold #dec383", "pane.search": "bold #91c6a5",
            "detail": "#b5cbd0", "answer": "",
            "chat.user": "bg:#2d3e4c fg:#f0f4f4", "chat.answer": "",
            "chat.speaker": "bold #a1d5cf", "chat.meta": "#a7b6bf",
            "chat.review": "bold #e2c990",
            "diff.add": "#a8d8af", "diff.remove": "#e5aa9d", "diff.hunk": "bold #9cc9dd",
            "owner.heading": "bold #afd3d2", "owner.label": "#d6e5e2",
            "owner.fact": "#b9d9d0", "owner.attention": "#e2c990", "owner.query": "#b5dfbd",
            "owner.match": "bold bg:#304c43 fg:#e5f4b6",
            "boundary": "#698b7a", "handoff": "#c7ba80",
            "composer": "bg:#24313d fg:#edf3f5",
            "activity.idle": "#a9b8c3", "activity.waiting": "bold #e3c581",
            "activity.model": "bold #a7d4e5", "activity.tool": "bold #b4d4b0",
            "activity.working": "bold #a7d4e5", "activity.saving": "bold #b4d4b0",
            "activity.meta": "#a5b3bf",
            "completion-menu": "bg:#23372e fg:#e3e6d8",
            "completion-menu.completion.current": "bg:#60795c fg:#ffffff bold",
        })
        self.app = Application(layout=Layout(root, focused_element=self.areas["agent"] if self.readonly else self.input),
                               full_screen=True, key_bindings=bindings,
                               mouse_support=Condition(lambda: not self.native_selection), style=style, output=self.output,
                               color_depth=ColorDepth.DEPTH_1_BIT if "NO_COLOR" in os.environ else None,
                               refresh_interval=None)
        self.app.pre_run_callables.append(lambda: self.app.create_background_task(self._animate_activity()))
        self._install_reading(bindings)
        self._rendered_size = None
        def track_focus(_):
            if self.app.layout.has_focus(self.owner_input):
                self.active_input = "owner"
            elif self.app.layout.has_focus(self.input):
                self.active_input = "agent"
            else:
                for name, area in self.areas.items():
                    if self.app.layout.has_focus(area):
                        self.active_input = "agent" if name == "agent" else "owner"
                        break
            size = self.output.get_size()
            dimensions = (size.columns, size.rows, self.focus_name)
            if dimensions != self._rendered_size:
                self._rendered_size = dimensions
                self._render()
        self.app.before_render += track_focus
        self.owner_input.buffer.on_text_changed += self._owner_text_changed
        self.owner_input.buffer.on_text_changed += lambda buffer: self.recall.edited(self.owner_mode)
        self.input.buffer.on_text_changed += lambda buffer: self.recall.edited("agent")
        from .pane_scroll import install_pane_scroll
        install_pane_scroll(self, bindings)

    def _owner_page(self):
        return self.focus_name if self.focus_name in ("owner", "evidence", "notebook", "review") else "owner"

    def _pane_width(self, name):
        return max(1, self._column_width(name) - (3 if self._compact_ui() else 6))

    def _column_width(self, name):
        size = self.output.get_size()
        split = self.focus_name == "split" and layout_mode(size.columns, size.rows) == "side"
        if not split:
            return size.columns
        available = size.columns - 3
        agent = available * 7 // 10
        return agent if name in ("agent", "system") else available - agent

    def _body(self):
        if self.focus_name == "agent":
            return self.agent_column
        if self.focus_name in ("owner", "evidence", "notebook", "review"):
            return self.owner_column
        size = self.output.get_size()
        mode = layout_mode(size.columns, size.rows)
        return (self.split_side if mode == "side" else self.split_stack if mode == "stack"
                else self.owner_column if self.active_input == "owner" else self.agent_column)

    def _header(self):
        if self.native_selection:
            return self.native_header
        if self._compact_ui():
            return self._short_header()
        view = self.view or {}
        run_id = view.get("run_id") or self.selected or "no run yet"
        freshness = "Ledger read pending" if self.view is None else "Ledger synced"
        if self.read_error:
            freshness = self._tr("STALE / Showing the last available view: ", "STALE / 前回の表示を保持: ") + self.read_error
        cursor = view.get("cursor") or {}
        if self.readonly:
            owner = "Owner live" if cursor.get("live") else "Owner offline / historical ledger"
            phase = cursor.get("phase", "idle") if cursor.get("live") else "recorded"
        else:
            owner, phase = "Owner Console", self._activity()[1]
        elapsed = f" / {int(time.monotonic() - self.started)}s" if self.busy and self.started else ""
        name = safe_text(self.configuration.get("project", {}).get("name", self.root.name))
        return (f" CLEANROOM  /  {name}  /  {'READ ONLY' if self.readonly else 'One project, one notebook'}\n"
                f" {safe_text(run_id)}  r{view.get('revision', 0)} / ledger {view.get('project_revision', 0)} / notes {view.get('owner_note_revision', 0)}\n"
                f" {freshness}  |  {owner}  |  {safe_text(phase)}{elapsed}\n"
                f" Web: {'ON' if self.web_enabled else 'OFF'} /tools  |  {self._reflection_hint()}  |  {self._ux('model')}: {self.model_label}")

    def _tabs(self):
        fragments = []
        for name in ("split", "owner", "agent", "evidence", "notebook", "review"):
            def click(event, name=name):
                from prompt_toolkit.mouse_events import MouseEventType
                if event.event_type == MouseEventType.MOUSE_UP and self.picker is None:
                    self.focus_name = name
                    self.reading_fullscreen = name != "split"
                    self._focus_input()
            fragments.append(("class:tab.active" if name == self.focus_name else "class:tab", "  " + name.title() + "  ", click))
        def tools(event):
            from prompt_toolkit.mouse_events import MouseEventType
            if event.event_type == MouseEventType.MOUSE_UP and self.picker is None and not self.busy:
                self._web_menu()
        fragments.append(("class:tab", "  Web / MCP  ", tools))
        return fragments

    def _footer(self):
        footer = self._reading_footer()
        message = self.cursor_error
        if self.read_error:
            message = self._tr("Waiting to reconnect. Last readable view: ", "DBの読み取りを再接続待ち。前回の正常な表示: ") + str((self.view or {}).get("read_at") or self._tr("none yet.", "まだありません。"))
        return (footer.split("\n")[0] + "\n " + fit_text(message, self.output.get_size().columns - 2)) if message else footer

    def _input_title(self):
        if self.question is not None:
            return safe_text(self.question.title, multiline=True) + (
                " [" + safe_text(self.question.default) + "]" if self.question.default else "")
        return self._ux("busy_input" if self.busy else "agent_input")

    def _owner_style(self):
        return "class:owner.memo" if self.owner_mode == "memo" else "class:owner.search"

    def _owner_title(self):
        return self._ux("memo_input" if self.owner_mode == "memo" else "search_input")

    def _owner_text_changed(self, buffer):
        if self.practice:
            self._render()
            return
        self.owner_drafts[self.owner_mode] = buffer.text
        if self.owner_mode == "search":
            self.growth_selection = None
            self.preview = None
            self.areas["owner"].buffer.cursor_position = 0
        self._render()

    def _owner_items(self, include_personal=False):
        from .cleanroom_owner import make_item
        owner_view = self.owner_view or self.view or {}
        archived = owner_view.get("owner_archive", False)
        items = list(owner_view.get("owner_items", []))
        if not archived and (self.live_explicit or self.owner_mode == "search" and self.owner_input.text.strip()):
            for row in self.live_insights:
                items.append(make_item("learning", row["id"] + " " + row["note"]["title"], row["note"],
                                       run_id=row["run_id"], source_ref=row["source_ref"]))
        if self.personal_view and not self.readonly and (not archived or include_personal):
            from .personal_growth import reference_items
            items.extend(reference_items(self.personal_view))
        recorded_request = ((self.owner_view or self.view or {}).get("state") or {}).get("request", "")
        if (self.pending_request and (not archived or self.selected == owner_view.get("run_id"))
                and recorded_request.split("\n\n[Owner-selected references:", 1)[0] != self.pending_request):
            item = make_item("request", self.pending_request.splitlines()[0],
                             {"request": self.pending_request, "status": "SESSION_ONLY_NOT_EXECUTION"},
                             run_id=self.selected, source_ref="session:" + self.session_id)
            items.insert(0, item)
        if self.question is not None and not self.settings_active:
            items.insert(0, make_item("question", self.question.title, self.question.title,
                                     run_id=self.selected, source_ref="session-question:" + self.session_id))
        return items

    def _visible_owner_items(self):
        if self.practice:
            from .cleanroom_owner import make_item
            return [make_item("note", text, text, run_id=None, source_ref="tutorial")
                    for text in [self._ux("demo_owner").splitlines()[1], *self.practice_notes]]
        from .cleanroom_owner import search
        query = self.owner_input.text if self.owner_mode == "search" else ""
        return search(self._owner_items(include_personal=True), query)

    def _cycle_inputs(self):
        self.input.buffer.cancel_completion()
        self.owner_input.buffer.cancel_completion()
        if self.active_input == "agent":
            self.owner_mode = "memo"
            self.active_input = "owner"
            self.owner_input.text = self.owner_drafts["memo"]
        elif self.owner_mode == "memo":
            self.owner_drafts["memo"] = self.owner_input.text
            self.owner_mode = "search"
            self.owner_input.text = self.owner_drafts["search"]
            self.growth_selection = None
            self.preview = None
        else:
            self.owner_drafts["search"] = self.owner_input.text
            self.active_input = "agent"
        self.focus_name = self.active_input if self.reading_fullscreen else "split"
        self._focus_input()
        self._render()

    def _jump_owner_match(self, direction):
        if self.owner_mode != "search" or not self.owner_input.text.strip() or self.picker is not None:
            return
        area = self.areas["owner"]
        lines = area.buffer.document.lines
        matches = [index for index, line in enumerate(lines) if line.startswith("▶ ")]
        if not matches:
            return
        current = area.buffer.document.cursor_position_row
        candidates = [row for row in matches if row > current] if direction > 0 else [row for row in matches if row < current]
        target = (candidates[0] if direction > 0 else candidates[-1]) if candidates else (matches[0] if direction > 0 else matches[-1])
        area.buffer.cursor_position = area.buffer.document.translate_row_col_to_index(target, 0)
        area.window.vertical_scroll = max(0, target - 2)
        self.app.invalidate()

    def _submit_owner(self, buffer):
        if self._session_control(buffer.text.strip(), buffer, "owner"):
            return True
        if self.practice:
            return self._practice_submit_owner(buffer)
        self.recall.record(self.owner_mode, buffer.text)
        if self.readonly:
            return True
        self.active_input = "owner"
        body = buffer.text.strip()
        if not body:
            self._cycle_inputs()
            return True
        if self.owner_mode == "search":
            self.focus_name = "owner" if self.reading_fullscreen else "split"
            self._render()
            self._jump_owner_match(1)
            return True
        if self.note_task is not None and not self.note_task.done():
            return True
        if len(body) > 4000:
            self._log(self._tr("Please keep each memo within 4,000 characters. Your draft is retained.", "メモは4000文字以内に分けてください。入力内容は残しています。"), owner=True)
            return True
        if self.note_intent is None or self.note_intent[1:] != (body, self.selected, self.console_sessions["room"]["id"]):
            self.note_intent = (uuid.uuid4().hex, body, self.selected, self.console_sessions["room"]["id"])
        self.note_task = asyncio.create_task(self._save_owner_note(self.note_intent))
        return True

    async def _save_owner_note(self, intent):
        from .cleanroom_owner import save_note
        key, body, run_id, room_id = intent
        try:
            await self.loop.run_in_executor(self.note_executor, lambda: save_note(self.root, body, key=key, run_id=run_id, room_id=room_id))
            if self.owner_drafts["memo"].strip() == body:
                self.owner_drafts["memo"] = ""
            if self.owner_mode == "memo" and self.owner_input.text.strip() == body:
                self.owner_input.buffer.reset()
            self.note_intent = None
            self.memo_offset = 0
            self._log(self._tr("Memo saved locally. It has not been sent to Agent.", "Ownerメモをローカル保存しました。Agentには送信していません。"), owner=True)
            await self._refresh()
        except (LedgerError, OSError, ValueError) as error:
            self._log(self._tr("Memo save could not be confirmed: ", "メモの保存結果を確認できません: ") + getattr(error, "code", type(error).__name__)
                      + self._tr(". Draft retained. Retrying the same memo uses the same operation key.", "。入力を保持しています。同じ内容の再保存は同じ操作キーを使います。"), owner=True)
        finally:
            self.app.invalidate()

    def _accept_owner_completion(self):
        state = self.input.buffer.complete_state
        if state is None or not state.completions:
            return
        completion = state.current_completion or state.completions[0]
        self.input.buffer.apply_completion(completion)
        item = self.reference_bindings.get(completion.text)
        if item:
            self._transfer("owner_to_agent", item["id"], item["label"], self._tr("Selected reference", "選択した参照"))

    def _transfer(self, direction, identity, label, kind):
        self.handoff = {"direction": direction, "id": identity, "label": safe_text(str(label))[:220],
                        "kind": kind, "started": time.monotonic()}
        if self.motion_task is not None and not self.motion_task.done():
            self.motion_task.cancel()
        if os.environ.get("VERANTYX_REDUCE_MOTION") != "1" and not self.closed:
            self.motion_task = asyncio.create_task(self._animate_transfer(identity))
        self._render()

    async def _animate_transfer(self, identity):
        for _ in range(14):
            if self.closed or self.handoff is None or self.handoff["id"] != identity:
                return
            self.app.invalidate()
            await asyncio.sleep(.06)

    def _transfer_progress(self):
        if self.handoff is None or os.environ.get("VERANTYX_REDUCE_MOTION") == "1":
            return 1.0
        return min(1.0, (time.monotonic() - self.handoff["started"]) / .72)

    def _vertical_boundary(self):
        rows = max(1, self.app.output.get_size().rows)
        progress = self._transfer_progress()
        if self.handoff is None or progress >= 1:
            return "\n".join(" │ " for _ in range(rows))
        center = max(2, rows // 3)
        radius = 1 + int(progress * 4)
        arrow = "›" if self.handoff["direction"] == "agent_to_owner" else "‹"
        return "\n".join((" " + arrow + " ") if row == center else
                         (" · " if progress < .6 else " ┆ ") if abs(row - center) <= radius else " │ "
                         for row in range(rows))

    def _horizontal_boundary(self):
        columns = max(4, self.app.output.get_size().columns)
        progress = self._transfer_progress()
        if self.handoff is None or progress >= 1:
            return "─" * columns
        center = columns // 2
        return "─" * max(0, center - 3) + (" · ↓ · " if self.handoff["direction"] == "agent_to_owner" else " · ↑ · ") + "─" * max(0, columns - center - 4)

    def _handoff_text(self):
        if self.handoff is None:
            return ""
        direction = "Agent → Owner" if self.handoff["direction"] == "agent_to_owner" else "Owner → Agent"
        label = self.handoff["label"]
        count = max(1, int(len(label) * self._transfer_progress()))
        return " " + direction + " / " + self.handoff["kind"] + "\n " + label[:count]

    def _question_title(self):
        return safe_text(self.picker["title"], multiline=True) if self.picker else ""

    def _menu_text(self):
        if not self.picker:
            return []
        fragments = []
        width = (self._pane_width("agent") - 6 if self._inline_choice()
                 else min(96, self.output.get_size().columns) - 10)
        for index, (_, label) in enumerate(self.picker["choices"]):
            style = "class:menu.selected" if index == self.choice_index else ""
            fragments.append((style, (" (o) " if index == self.choice_index else " ( ) ")
                              + fit_text(label, width) + "\n"))
        return fragments

    def _focus_input(self):
        if self.closed:
            return
        if self.focus_name == "agent":
            self.active_input = "agent"
        elif self.focus_name in ("owner", "evidence", "notebook", "review"):
            self.active_input = "owner"
        target = (self.areas[self.focus_name if self.focus_name in self.areas else self.active_input]
                  if self.readonly else self.owner_input if self.active_input == "owner" else self.input)
        self.app.layout.focus(target)
        self.app.invalidate()

    def _show_picker(self, title, choices, callback, descriptions=None, aliases=None, *, inline=False):
        self.choice_index = 1 if (self.settings_active or inline) and choices else 0
        self.picker = {"title": title, "choices": [(None, self._ux("back")), *choices], "callback": callback,
                       "descriptions": descriptions or {}, "aliases": aliases or {}, "inline": inline}
        if not (inline and self.active_input == "owner"):
            if self.settings_active or inline:
                self.active_input = "agent"
                self.focus_name = "split"
                self.app.layout.focus(self.input)
            else:
                self.app.layout.focus(self.menu_control)
        self.app.invalidate()

    def _log(self, value, *, owner=False):
        value = safe_text(str(value).strip(), multiline=True)
        if value:
            self.logs.append(value[:8000])
            # Activity is not a second copy of the Owner notebook.
        self._render()

    def notice(self, value):
        def display():
            if self.settings_active:
                self.settings_lines.append(safe_text(str(value).strip(), multiline=True)[:8000])
                self._render()
            else:
                self._log(value)
        self.loop.call_soon_threadsafe(display)

    def _present_question(self, question):
        if self.closed:
            question.answer.set_exception(OwnerCancelled())
            return
        self.question = question
        if question.preview is not None:
            self.info_text = None
            self.volatile_answer = None
            self.conversation.change(question.preview, "WAITING")
        elif not self.settings_active:
            self._transfer("agent_to_owner", "question-" + uuid.uuid4().hex, question.title, self._ux("owner_question"))
        self.saved_draft = self.input.buffer.document
        self.input.buffer.reset()
        self.phase = self._ux("owner_question")
        if question.choices is not None:
            self._show_picker(question.title, question.choices, self._answer,
                              descriptions=question.descriptions, aliases=question.aliases, inline=question.inline)
        elif not (question.inline and self.active_input == "owner"):
            self.active_input = "agent"
            self.focus_name = "split"
            self._focus_input()
        self._render()

    def _answer(self, value):
        question, self.question = self.question, None
        self.picker = None
        if self.saved_draft is not None:
            self.input.buffer.set_document(self.saved_draft)
            self.saved_draft = None
        self.phase = "working"
        if question is not None and not question.answer.done():
            question.answer.set_result(value)
        self._focus_input()

    def _cancel_question(self):
        question = self.question
        if question is not None and not question.answer.done():
            question.answer.set_exception(OwnerCancelled())
        self.question = None
        self.picker = None
        if self.saved_draft is not None:
            self.input.buffer.set_document(self.saved_draft)
            self.saved_draft = None
        self._focus_input()

    def ask(self, title, default=""):
        if title.endswith(("[y/N]", "[Y/n]")):
            return self.choose(title, [("y", ui_text("Confirm the displayed operation only", self._locale()))]) or "n"
        question = Question(title, Future(), default=default)
        self.loop.call_soon_threadsafe(self._present_question, question)
        value = question.answer.result()
        return str(value or default).strip()

    def choose(self, title, choices, descriptions=None, aliases=None):
        question = Question(title, Future(), choices=list(choices), descriptions=descriptions, aliases=aliases)
        self.loop.call_soon_threadsafe(self._present_question, question)
        return question.answer.result()

    def _submit(self, buffer):
        value = buffer.text.strip()
        if self._live_command(value, buffer):
            return True
        if self._session_control(value, buffer, "agent"):
            return True
        if self.readonly:
            return True
        self.active_input = "agent"
        if self._handle_control(value, buffer):
            return True
        if self.practice and value:
            self._tour_event("chat")
            buffer.reset()
            self.info_text = self._ux("demo_answer") + "\n\n" + self._ux("demo_steps") + "\n\n" + self._ux("workflow_guide")
            self._render()
            return True
        if self.question is not None:
            # A displayed question owns Enter, including its explicit default.
            # Input-pane cycling applies only when no question is pending.
            self._answer(value)
            return True
        if not value:
            self._cycle_inputs()
            return True
        if self.busy:
            self._offer_work_input(value, buffer)
            return True
        buffer.reset()
        from .development_console import _notebook_intent
        intent = _notebook_intent(value)
        destinations = {"project": "owner", "notebook": "notebook", "decisions": "evidence", "review": "review"}
        if intent in destinations:
            self.focus_name = destinations[intent]
        elif intent == "quit":
            self.request_exit()
        elif intent == "history":
            self.open_history()
        elif intent == "learn":
            self.open_growth()
        elif intent in ("index", "settings", "mode", "export") or value.startswith("/") and intent is None:
            self.open_menu()
        elif intent in ("assets", "models", "scope"):
            self.start_action(intent)
        else:
            from .cleanroom_owner import selected_references, expand_request
            references = selected_references(value, self.reference_bindings)
            try:
                expand_request(value, references)
            except LedgerError:
                buffer.text = value
                self._log(self._tr("Choose up to 8 references and 12,000 characters total. Your full draft is retained.", "選択する参照は8件以内、依頼と参照の合計は12000文字以内にしてください。内容は省略せず入力を保持しました。"), owner=True)
                return True
            self._transfer("agent_to_owner", "request-" + uuid.uuid4().hex, value.splitlines()[0], self._tr("Your request", "あなたの依頼"))
            self.recall.record("agent", value)
            self.info_text = None
            self.volatile_answer = None
            self.volatile_history.clear()
            self.start_action("work", request=value, owner_references=references,
                              attachments=list(self.attachment_queue))
        return True

    def open_menu(self):
        if self.question is not None:
            self._log(self._tr("Answer the current choice, or press Esc to cancel that operation.", "先に表示中の選択へ回答するか、Escでその操作を中止してください。"), owner=True)
            return
        choices = [(name, label) for name, label in (
            ("split", "Work / 人間とAIを一緒に見る"), ("owner", "Owner / 目的・判断・理解"),
            ("agent", "Agent / 作業記録を読む"), ("evidence", "Evidence / 検査と限界を見る"),
            ("notebook", "Notebook / 仕事から残ったもの"), ("review", "Review / 判断・採用・学習方針"))]
        if not self.busy:
            if not self.readonly:
                choices += [("new-work", "New page / 別の仕事を始める")]
            choices += [("history", "History / 別の仕事を開く")]
            choices += [("growth", "Learn together / 今回持ち帰る理解を開く")]
            if self.readonly:
                choices += [("follow", "Follow Owner / 人間側と同じ仕事を追う")]
            else:
                choices += [("review-action", "Review actions / 今必要な操作を選ぶ"),
                            ("web-tools", "Web & MCP / 無料検索・本文取得の設定"),
                            ("perspectives", "Perspectives / 新しい見方と、これまでの来歴"),
                            ("models", "Models & Providers / AI接続を設定"), ("scope", "Workspace / 送信候補の範囲"),
                            ("learn", "Learning library / 保存した学習・検査を詳しく見る"),
                            ("personal-profile", "My profile / 経験と希望。点数は付けません"),
                            ("personal-journal", "My journal / プロジェクトを越えた日記"),
                            ("personal-skills", "My skills / AIの手順と、自分が育てる盤面"),
                            ("work-harness", "Work harness / 内蔵・信頼する外部アダプター"),
                            ("learning-guides", "Unpack / スキル・技術の学び方と元の記録"),
                            ("notebook-connections", "Connections / Obsidian・スキル移植・MCP"),
                            ("learning-moments", "During work / 作業中の説明と自分の記録"),
                            ("model-roles", "Parent / child models / 親子モデル"),
                            ("sandbox-backend", "Sandbox backend / 外部OSSランチャー"),
                            ("personal-next", "Next time / 少しずつ続ける理解・参照・委譲"),
                            ("personal-pace", "My pace / 提案の量・共有・今日だけ静かに"),
                            ("personal-talk", "Talk / 相談する・自分の言葉で更新"),
                            ("personal-portfolio", "Portfolio / 実績として残すものを選ぶ")]
        choices += [("help", "About / 使い方と境界"), ("quit", "Close / この画面を閉じる")]

        english_labels = {
          "split": "Work / Agent and Owner together",
          "owner": "Owner / Purpose, decisions and understanding",
          "agent": "Agent / Work records",
          "evidence": "Evidence / Checks and their limits",
          "notebook": "Notebook / What the work leaves behind",
          "review": "Review / Your choices",
          "new-work": "New page / Start another task",
          "history": "History / Open an earlier task",
          "growth": "Learn together / One optional insight",
          "follow": "Follow Owner / Read the same task",
          "review-action": "Review actions / Choose what is needed",
          "web-tools": "Web & MCP / Free search and page reading",
          "perspectives": "Perspectives / Versioned interpretations",
          "models": "Models & Providers / AI connections",
          "scope": "Workspace / Send scope",
          "learn": "Learning library / Sources and checks",
          "personal-profile": "My profile / Experience and preferences, not scores",
          "personal-journal": "My journal / Across projects",
          "personal-skills": "My skills / AI procedures and the skills you choose",
          "work-harness": "Work harness / Trusted runtime",
          "learning-guides": "Unpack / Explore original work and explanations",
          "notebook-connections": "Connections / Obsidian, skills, MCP",
          "learning-moments": "During work / Explanations and your own words",
          "model-roles": "Parent / child models",
          "sandbox-backend": "Sandbox backend / External OSS launcher",
          "personal-next": "Next time / Learn, reference or delegate",
          "personal-pace": "My pace / Amount, weight, timing and privacy",
          "personal-talk": "Talk / Ask or update in your own words",
          "personal-portfolio": "Portfolio / Select experiences to keep",
          "help": "About / Controls and boundaries",
          "quit": "Close / Leave this view"
}
        choices = [(name, self._tr(english_labels.get(name, label), label)) for name, label in choices]
        choices[6:6] = [("reading-fullscreen", self._rt("split" if self.reading_fullscreen else "fullscreen")),
                        ("reading-copy", self._rt("copy")), ("reading-latest", self._rt("latest"))]

        def selected(value):
            if value in ("split", *self.areas):
                self.focus_name = value
                self.reading_fullscreen = value != "split"
            elif value == "reading-fullscreen":
                self._set_fullscreen()
            elif value == "reading-copy":
                self._copy_reading()
            elif value == "web-tools":
                self._web_menu()
            elif value == "reading-latest":
                self._reading_jump(True)
            elif value == "history":
                self.open_history()
            elif value == "growth":
                self.open_growth()
            elif value == "follow":
                self.selected = None
            elif value == "quit":
                self.request_exit()
            elif value == "help":
                self._show_help()
                self.focus_name = "agent"
            elif value:
                self.start_action(value)
            self._render()
            if self.picker is None:
                self._focus_input()
        self._show_picker(self._tr("Cleanroom / What would you like to open?", "Cleanroom / 何を見ますか？"), choices, selected)

    def open_history(self):
        works = (self.view or {}).get("works", [])
        self._show_picker("Notebook / 保存された仕事", [(row["run_id"], row["label"] + " / " + row["status"])
                         for row in works], lambda value: self._select_run(value))

    def _select_run(self, value):
        if value:
            self.selected = value
            self.preview = None
            self.growth_selection = None
            self.pending_request = None
            self.notes.clear()
            self.logs.clear()
            self.focus_name = "split"

    def _render(self):
        if self.native_selection:
            self.app.invalidate()
            return
        from .conversation_view import owner_page
        self.owner_completer.locale = self._locale()
        panes = (self.view or {}).get("panes", {})
        for name, area in self.areas.items():
            body = panes.get(name, self._tr("Opening the local records in read-only mode.", "読み取り専用で台帳を開いています。"))
            if name == "owner":
                query = self.owner_input.text if self.owner_mode == "search" else ""
                items = self._owner_items()
                if not query:
                    items = [item for item in items if not str(item.get("source_ref", "")).startswith("personal:")]
                body = owner_page(self.owner_view or self.view or {}, items, query,
                                  self.personal_view if not self.readonly else None, self.personal_visible,
                                  self._pane_width("owner"),
                                  self._locale(), self.owner_lexer)
                growth_item = self._growth_item(selected_only=True)
                if growth_item is not None and not query:
                    from .cleanroom_growth import lesson
                    body = lesson(growth_item)
                    self.owner_lexer.rows = []
                elif self.preview is not None and not query:
                    body = self.preview
                    self.owner_lexer.rows = []
                if self.practice:
                    body = self._practice_owner()
                    self.owner_lexer.rows = []
            if name == "agent":
                body = self._primary_answer()
            self._set_pane_text(name, body)
        self._set_pane_text("system", self._system_text())
        self.app.invalidate()

    def _growth_item(self, *, selected_only=False):
        growth = (self.view or {}).get("growth") or {}
        if self.growth_selection is not None:
            return next((item for item in growth.get("items", [])
                         if (item["run_id"], item["id"]) == self.growth_selection), None)
        return None if selected_only else growth.get("focus")

    def _growth_visible(self):
        growth = (self.view or {}).get("growth") or {}
        return (not self.readonly and not self.busy and self.picker is None and self.question is None
                and self.preview is None and self.focus_name in ("split", "owner", "notebook")
                and self.app.output.get_size().rows >= 24 and self._growth_item() is not None
                and (self.growth_selection is not None or growth.get("automatic_card", False)))

    def _growth_card(self):
        from .cleanroom_growth import card
        item = self._growth_item()
        return card(item) if item is not None else ""

    def _growth_actions(self):
        fragments = []
        for action, label in (("read", "Read / 読む"), ("explain", "My words / 自分の言葉"),
                              ("defer", "Later / 後で"), ("reference", "Reference / 参照"),
                              ("delegate", "Delegate / 委譲")):
            def click(event, action=action):
                from prompt_toolkit.mouse_events import MouseEventType
                if event.event_type == MouseEventType.MOUSE_UP and not self.busy and not self.readonly:
                    self._choose_growth_action(action)
            fragments.append(("class:tab.active", "  " + label + "  ", click))
        return fragments

    def open_growth(self):
        if self.busy or self.question is not None:
            return
        if ((self.view or {}).get("state") or {}).get("work_session"):
            self.start_action("learn", run_id=self.view["run_id"])
            return
        growth = (self.view or {}).get("growth") or {}
        focus = self._growth_item()
        if focus is not None:
            self._open_growth_item(focus)
            return
        items = growth.get("items", [])
        if not items:
            self._log("この仕事では、表示できる学習候補はまだ保存されていません。\n"
                      "教材を推測で埋めません。学習をオフにしている場合は未選択の候補を表示しません。", owner=True)
            return
        self._show_growth_list(items)

    def _show_growth_list(self, items):
        self._show_picker("Learning notes / この仕事に結び付いた項目", [
            (index, item["concept"] + " / " + item.get("ownership_target", "REVIEW")
             + (" / 後で確認" if item.get("status") == "DEFERRED" else ""))
            for index, item in enumerate(items)],
            lambda index: self._open_growth_item(items[index]) if index is not None else None)

    def _open_growth_item(self, item):
        self.growth_selection = (item["run_id"], item["id"])
        self.preview = None
        self.active_input = "owner"
        self.owner_mode = "memo"
        self.owner_input.text = self.owner_drafts["memo"]
        self.focus_name = "split"
        self._render()

    def open_growth_actions(self):
        item = self._growth_item()
        if item is None or self.readonly or self.busy:
            return
        choices = [("read", "Read / 保存された原理・反例・出典を読む"),
                   ("explain", "My words / 自分の言葉で説明を残す"),
                   ("counterexample", "Boundary / 使えない条件を自分の言葉で残す"),
                   ("apply", "Apply / 今回どう適用したかを記録"),
                   ("own", "Own / 自分で設計・応用できることを目標にする"),
                   ("review", "Review / 危険や誤りを判断できることを目標にする"),
                   ("reference", "Reference / 参照できれば十分"),
                   ("delegate", "Delegate / 人間側の学習目標を委譲へ変更"),
                   ("resume" if item.get("status") == "DEFERRED" else "defer",
                    "Resume / 後回しの項目を再開" if item.get("status") == "DEFERRED" else "Later / 今は作業を進め、後で確認"),
                   ("all", "Other notes / この仕事のほかの学習項目")]
        self._show_picker("Learn together / 読むだけで理解済みにはしません", choices,
                          lambda action: self._choose_growth_action(action) if action else None)

    def _choose_growth_action(self, action):
        item = self._growth_item()
        if item is None or self.busy:
            return
        if action == "read":
            self._open_growth_item(item)
        elif action == "all":
            self._show_growth_list((self.view or {}).get("growth", {}).get("items", []))
        elif not self.readonly:
            self._open_growth_item(item)
            self.start_action("growth-record", learning_identity=(item["run_id"], item["id"]), learning_action=action)

    def _progress(self, stage):
        self.phase = safe_text(str(stage)[:100])
        if str(stage).startswith("tool:"):
            self.model_waiting = False
        self._log("Phase: " + self.phase)

    def _model_progress(self, event):
        # Never expose hidden reasoning or treat a provider's self-check as proof.
        if event.get("kind") == "start":
            self.model_waiting = True
            self._log("Model request: " + safe_text(event.get("model", "configured model")))
        elif event.get("kind") == "output":
            self.model_waiting = False
            self._log("Response received: " + str(event.get("characters", 0)) + " characters / not evidence")
        elif event.get("kind") == "validated":
            self.model_waiting = False
            self.phase = "validating"
            self._log("Model response format checked / not an independent correctness check")
        elif event.get("kind") == "usage":
            self.last_model_usage = event
            self.model_waiting = False
            self.phase = "validating"
            self.app.invalidate()

    def start_action(self, action, **kwargs):
        if self.readonly or self.busy:
            return
        if self.practice:
            self._log(self._ux("demo"))
            return
        self._start_chat_work(action, kwargs)
        self.settings_active = action in SETTINGS_ACTIONS
        if self.settings_active:
            self.settings_lines.clear()
            self.info_text = None
            self.active_input = "agent"
            self.focus_name = "split"
        self.busy, self.phase, self.started = True, "preparing", time.monotonic()
        self.preview = None
        if action in ("work", "work-notebook", "legacy-work"):
            self.personal_visible = []
            self.pending_request = kwargs["request"]
        basis = deepcopy(self.view)
        self.work_task = asyncio.create_task(self._run_operation(action, basis, kwargs))
        self._render()

    async def _run_operation(self, action, basis, kwargs):
        from .cleanroom_view import operation_message
        follow_up_ui, result = None, None
        inbox, ticket = self.run_input, self.active_ticket
        def invoke():
            from .progress import observe
            from .work_input import bind as bind_work_input
            from .interaction_text import language
            with bind(self), bind_work_input(inbox), language(self.configuration), observe(lambda stage: self.loop.call_soon_threadsafe(self._progress, stage),
                                     lambda event: self.loop.call_soon_threadsafe(self._model_progress, dict(event))):
                return self._operation(action, basis, **kwargs)
        try:
            result = await self.loop.run_in_executor(self.work_executor, invoke)
            self.phase = "idle"
            if isinstance(result, dict) and result.get("transient"):
                self.volatile_answer = result["answer"]
                self.volatile_history.extend([{"role": "user", "text": kwargs["request"]},
                                              {"role": "assistant", "text": result["answer"]}])
                self.volatile_history = self.volatile_history[-8:]
                return
            if isinstance(result, dict):
                follow_up_ui = result.get("ui_action")
                self.last_result = result
                personal = result.get("personal_growth") or {}
                if personal.get("visible_lessons"):
                    self.personal_visible = personal["visible_lessons"]
                    self._transfer("agent_to_owner", "personal:" + self.personal_visible[0],
                                   "今回の小さな一歩", "自分のペースで持ち帰る")
                if result.get("run_id"):
                    self.selected = result["run_id"]
                    if action in ("work", "work-notebook"):
                        self.attachment_queue.clear()
                status = result.get("status", "RECORDED")
                self._log("操作結果: " + operation_message(status) + " / 証拠と理解の状態は台帳で別々に表示します。", owner=True)
                if status in ("BLOCKED", "DECISION_REQUIRED", "UNKNOWN_CONTEXT", "MODEL_CALL_FAILED", "MODEL_OUTCOME_UNKNOWN", "WORK_OUTPUT_INVALID"):
                    self.phase = "needs attention / 保留・確認が必要"
                elif status in ("RESPONSE_SAVED", "CANDIDATE_SAVED"):
                    self.phase = operation_message(status)
                if result.get("reason"):
                    self._log(operation_message(result["reason"]), owner=True)
                await self._refresh()
        except OwnerCancelled:
            self.phase = "paused"
            self._log("今回の未実行操作を中止しました。既に記録された結果は取り消しません。", owner=True)
        except (LedgerError, config.ConfigError, sqlite3.Error, OSError, ValueError) as error:
            self.phase = "needs attention"
            if getattr(error, "code", "") == "ATTACHMENT_INPUT":
                self._log(self._ux("attachment_help") + "\n" + str(getattr(error, "details", {}).get("reason", "")))
            self._log("操作を完了できませんでした: " + operation_message(getattr(error, "code", type(error).__name__))
                      + "\n自動で再試行しません。失敗・結果不明・記録済みを台帳で区別してください。", owner=True)
        except Exception as error:
            self.phase = "needs attention"
            self._log("操作を中断しました: " + type(error).__name__ + " / 成功として扱わず、自動再送もしません。", owner=True)
        finally:
            self._finish_chat_work(action, result, inbox, ticket)
            self.busy = False
            self.started = None
            if action in SETTINGS_ACTIONS:
                self.settings_active = False
                self._refresh_model_label()
            self._render()
            if self.after_settings is not None and not self.exit_after_work:
                pending, self.after_settings = self.after_settings, None
                if pending:
                    self.input.buffer.text = pending
                    self._submit(self.input.buffer)
            if self.exit_after_work:
                self.app.exit(result=0)
            elif follow_up_ui == "open_growth":
                self.open_growth()
            elif not self._continue_live_questions():
                self._start_next_queued()

    def _operation(self, action, basis, **kwargs):
        if action in ("web-setup", "web-read"):
            return self._web_operation(action, **kwargs)
        from . import development_console as console
        from .development import run_work
        from .constitution import prepare
        from .model_settings import activate_codex, clear, describe
        from .work_pulse import answer as work_pulse_answer
        if action == "insight-question":
            from .development_console import _mutate
            result = _mutate(self.root, self.configuration, work_pulse_answer, **kwargs)
            self.loop.call_soon_threadsafe(self._question_finished, result)
            return None
        if action == "session-control":
            return self._session_operation(**kwargs)
        if action == "inline-settings":
            from .settings_console import configure, display
            if kwargs.get("section") == "show":
                return display(self.root, self.configuration)
            return configure(self.root, self.configuration, kwargs.get("section", "menu"))
        if action == "temporary-chat":
            from .volatile_chat import chat
            from .interaction_text import tr
            print_message = tr("private", self.configuration["ui"]["locale"])
            self.notice(print_message)
            if self.choose(tr("send_private", self.configuration["ui"]["locale"]),
                           [("send", tr("send", self.configuration["ui"]["locale"]))]) != "send":
                return None
            return chat(self.root, self.configuration, kwargs["request"], kwargs.get("history", []))
        if action == "notebook-connections":
            from .bridge_console import menu as bridge_menu
            return bridge_menu(self.root, self.configuration)
        if action == "learning-moments":
            from .learning_moments import menu as moments_menu
            return moments_menu(self.root, self.configuration)
        if action == "model-roles":
            from .model_roles import menu as roles_menu
            return roles_menu(self.root, self.configuration)
        if action == "learning-guides":
            from .learning_console import menu as learning_menu
            return learning_menu(self.root, self.configuration)
        if action == "sandbox-backend":
            from .sandbox_backends import menu as sandbox_menu
            return sandbox_menu(self.root, self.configuration)
        if action == "work-harness":
            from .work_harness import menu as harness_menu
            return harness_menu(self.root, self.configuration)
        if action.startswith("personal-"):
            from .personal_console import menu
            return menu(self.root, self.configuration, action.removeprefix("personal-"))
        if action == "new-work":
            return console._new_work(self.root, self.configuration, "assisted")
        if action in ("work", "work-notebook"):
            from .cleanroom_owner import expand_request
            request = expand_request(kwargs["request"], kwargs.get("owner_references", []))
            state = (basis or {}).get("state") or {}
            previous = ({"run_id": basis["run_id"]} if state.get("work_session") and basis.get("run_id") else None)
            return console._new_work(self.root, self.configuration, "assisted", previous=previous, request=request,
                                     attachments=kwargs.get("attachments", []))
        if action == "perspectives":
            from .provenance_console import perspectives_menu
            return perspectives_menu(self.root, self.configuration, (basis or {}).get("run_id"))
        if action in ("project", "review", "learn", "assets", "decisions", "notebook", "history"):
            from .owner_notebook import show_project, open_notebook
            if action == "project":
                return show_project(self.root, self.configuration)
            return open_notebook(self.root, self.configuration, run_id=kwargs.get("run_id"),
                                 section="learn" if action == "learn" else action)
        if action == "legacy-work":
            from .cleanroom_owner import expand_request
            references = kwargs.get("owner_references", [])
            request = expand_request(kwargs["request"], references)
            gate = console._mutate(self.root, self.configuration, prepare, request)
            assumption = None
            if gate.get("question"):
                assumption = self.ask(gate["question"] + " / 今回だけの前提。空欄は保留")
                if not assumption and gate["status"] in ("ASK_ONE_DECISION", "UNKNOWN"):
                    return {"status": "DECISION_REQUIRED", "task_gate": gate, "model_calls": 0}
            paths = self._context_paths()
            details = "\n".join(f"{path}  {(self.root / path).stat().st_size} B" for path in paths)
            self.notice("EXTERNAL CONTEXT / 今回の送信候補\n" + (details or "該当する小さなテキストファイルなし")
                        + "\n既存のプロジェクト文脈・過去の判断も実行系が注入します。\n"
                        "自動選択は最大8件です。除外名の検査だけで、秘密情報がないことを保証しません。")
            if references:
                self.notice("OWNER REFERENCES / 選択した項目だけを送ります\n"
                            + "\n\n".join(item["label"] + "\n" + item["text"] for item in references)
                            + "\n参照は保存時点のものです。承認や実行権限にはなりません。")
            self.choose_or_stop("依頼・プロジェクト文脈と、表示したファイルを設定済みAIへ送りますか？", "Send & start / この範囲で開始")
            key = uuid.uuid4().hex
            run_id = "partner-" + digest({"project": self.configuration["project"]["id"], "key": key})[:32]
            self.loop.call_soon_threadsafe(self._begin_run, run_id, kwargs["request"])
            return console._mutate(self.root, self.configuration, run_work, request=request, key=key,
                                   include=paths, target=None, expectations=[], mode="assisted",
                                   allow_contested=False, assumption=assumption or None)
        if action == "scope":
            self.notice("WORKSPACE / " + str(self.root) + "\n" + "\n".join(self._context_paths())
                        + "\nここを開くだけでは送信しません。最大8件の候補であり、全ソースの理解ではありません。")
            return
        if action == "models":
            return console._model_settings(self.root, self.configuration)
        if action == "legacy-models":
            provider = self.choose("Models & Providers / " + describe(self.configuration)["label"], [
                ("codex", "ChatGPT Codex subscription"), ("ollama", "Ollama local models"),
                ("openai", "OpenAI API"), ("anthropic", "Anthropic API"), ("gemini", "Gemini API"),
                ("openai_compatible", "OpenAI-compatible local server"), ("default", "Restore default Codex connection")])
            if provider == "codex":
                console._mutate(self.root, self.configuration, activate_codex)
            elif provider == "default":
                console._mutate(self.root, self.configuration, clear)
            elif provider:
                console._configure_model_api(self.root, self.configuration, provider)
            return
        if basis is None or basis.get("state") is None:
            self.notice("保存された仕事をHistoryから選ぶか、最初の仕事を依頼してください。")
            return
        run_id = basis["run_id"]
        if action == "growth-record":
            return self._record_growth(basis, **kwargs)
        if action in ("learn", "assets"):
            related = [run_id, *(row["run_id"] for row in basis["related_receipts"])]
            return console._dictionary(self.root, self.configuration, run_ids=related)
        if action == "review-action":
            if basis["state"].get("work_session"):
                from .owner_notebook import open_notebook
                return open_notebook(self.root, self.configuration, run_id=run_id)
            chosen = self.choose("Review / この仕事に必要なこと", [
                ("decision", "Human decision / 判断待ちに回答"), ("preview", "Candidate / 保存された候補内容を見る"),
                ("verify", "Evidence / 明示した有限条件で検査"), ("learn", "Growth / 学ぶ・参照・委譲"),
                ("adoption", "Adoption / 準備済みの採用計画を確認")])
            if chosen == "decision":
                return self._decision(basis)
            if chosen == "preview":
                files = ((basis["state"].get("editor_attempt") or {}).get("document") or {}).get("files") or {}
                path = self.choose("Candidate / 実行・採用はしません", [(path, path) for path in sorted(files)])
                if path:
                    body = "CANDIDATE / NOT APPLIED\n" + path + "\n\n" + files[path] + "\n\nEscで戻る"
                    self.loop.call_soon_threadsafe(self._preview, body)
            elif chosen == "verify":
                return console._verify_work(self.root, self.configuration, {"run_id": run_id, "state": basis["state"]})
            elif chosen == "learn":
                return {"status": "LEARNING_VIEW_REQUESTED", "run_id": run_id, "ui_action": "open_growth"}
            elif chosen == "adoption":
                return self._adoption(basis)

    def _context_paths(self):
        from .development_console import _context_files
        paths = []
        for name in _context_files(self.root):
            path = self.root / name
            if not path.is_symlink() and path.resolve().is_relative_to(self.root) and path.is_file():
                paths.append(name)
        return paths

    def choose_or_stop(self, title, affirmative):
        if self.choose(title, [(True, affirmative)]) is not True:
            raise OwnerCancelled()

    def _begin_run(self, run_id, request):
        self.selected = run_id
        self.growth_selection = None
        self.notes.clear()
        self.logs.clear()
        self.phase = "starting / waiting for ledger"
        self.focus_name = "split"
        self._log("依頼: " + request, owner=True)

    def _preview(self, body):
        self.preview = safe_text(body, multiline=True)
        self.growth_selection = None
        self.focus_name = "owner"
        self._render()

    def _record_growth(self, basis, *, learning_identity, learning_action):
        from .learning import control_learning
        from .development_console import _mutate
        item = next((row for row in basis.get("growth", {}).get("items", [])
                     if (row["run_id"], row["id"]) == learning_identity), None)
        if item is None:
            raise LedgerError("LEARNING_NOT_FOUND")
        fields = {"candidate_id": item["id"], "key": uuid.uuid4().hex, "expected_revision": item["revision"]}
        targets = {"own": "OWN", "review": "REVIEW", "reference": "REFERENCE", "delegate": "DELEGATE"}
        if learning_action in targets:
            operation = "target"
            fields.update(target=targets[learning_action],
                          reason={"own": "Owner selected a goal of understanding the principle well enough to design and adapt it.",
                                  "review": "Owner selected a goal of recognizing risks and judging incorrect applications.",
                                  "reference": "Owner chose to retain this as a reference instead of memorizing it.",
                                  "delegate": "Owner chose delegation as the learning target; no execution authority is granted."}[learning_action])
        elif learning_action in ("defer", "resume"):
            operation = learning_action
            fields["reason"] = ("Owner chose to continue project work and revisit this understanding later."
                                if operation == "defer" else "Owner explicitly reopened this deferred learning item.")
        elif learning_action in ("explain", "counterexample", "apply"):
            operation = learning_action
            prompts = {
                "explain": "自分の言葉で説明すると？ 使える条件も一つ添えられます。ローカルに自己申告として保存します。空欄は中止。",
                "counterexample": "この原理がそのまま使えない条件は？ ローカルに自己申告として保存します。空欄は中止。",
                "apply": "今回どこに、どう適用しましたか？ 実行済みの証明ではなく本人のメモとして保存します。空欄は中止。",
            }
            statement = self.ask(prompts[operation])
            if not statement:
                raise OwnerCancelled()
            self.notice("YOUR NOTE / 保存前の下書き\n" + statement)
            fields["statement"] = statement
        else:
            raise LedgerError("ARGUMENTS")
        receipt = _mutate(self.root, self.configuration, control_learning, item["run_id"], operation, **fields)
        self.notice("理解についての選択・メモを既存の学習台帳へ保存しました。\n"
                    "習熟を自動認定せず、AIの実行許可も変更していません。")
        if operation in ("defer", "target"):
            self.loop.call_soon_threadsafe(self._leave_growth)
        return {"ok": True, "status": "LEARNING_RECORDED", "run_id": basis["run_id"],
                "learning_run_id": item["run_id"], "receipt": receipt, "model_calls": 0}

    def _leave_growth(self):
        self.growth_selection = None
        self.preview = None
        self._render()

    def _decision(self, basis):
        from argparse import Namespace
        from .application import dispatch
        question = basis.get("question") or {}
        points = (basis["state"].get("proposal") or {}).get("decision_points", [])
        point = next((row for row in points if row["id"] == question.get("point_id")), None)
        if point is None:
            self.notice("この仕事に、選択肢付きの未解決判断は記録されていません。")
            return
        options = point.get("options", [])
        choice = self.choose(point["question"], [(row["id"], row.get("label") or row.get("description") or row["id"]) for row in options])
        if choice is None:
            return
        reason = self.ask("この選択をする理由 / 空欄は保留")
        if not reason:
            return
        self.choose_or_stop("選択と理由を人間の判断として記録します。自動実行の許可とは別です。", "Record decision / 判断を残す")
        args = Namespace(command="decide", target=basis["run_id"], point=point["id"], choice=choice, reason=reason,
                         key=uuid.uuid4().hex, expected_revision=basis["revision"])
        return dispatch(self.root, self.configuration, args, "ja")

    def _adoption(self, basis):
        from . import adoption
        from .development_console import _mutate
        plans = [row for row in basis["receipt"]["system_delta"]["execution_assets"] if row["family"] == "ADOPTION"]
        if not plans:
            self.notice("この仕事には準備済みの採用計画がありません。\n候補保存だけから本体へコピーしません。既存のworktree・検査・採用計画の準備が必要です。")
            return
        identity = self.choose("Adoption / 記録された計画", [(row["plan_id"], row["plan_id"] + " / " + row["status"]) for row in plans])
        if identity is None:
            return
        precedent = self.ask("既存の実行許可を表すprecedent設定ファイル / 空欄は戻る")
        if not precedent:
            return
        reviewed = adoption.review_adoption(self.root, self.configuration, basis["run_id"], identity, precedent)
        self.notice("ADOPTION REVIEW\n" + json.dumps(reviewed, ensure_ascii=False, default=str)[:12000])
        selected = self.choose("Review first / 許可と採用実行は別操作です", [
            ("authorize", "Authorize this plan / この計画だけを許可"),
            ("apply", "Apply an authorized plan / 既に許可された計画を実行")])
        if selected == "authorize":
            reason = self.ask("この採用を許可する理由 / 空欄は戻る")
            if reason:
                self.choose_or_stop("表示した計画だけを300秒間許可します。まだ採用は実行しません。", "Authorize / 許可を記録")
                return _mutate(self.root, self.configuration, adoption.authorize_adoption, basis["run_id"], identity,
                               precedent, uuid.uuid4().hex, reason=reason, ttl=300)
        elif selected == "apply":
            self.choose_or_stop("表示した許可済み計画を実行します。対象ブランチと候補を確認してください。", "Apply plan / 採用を実行")
            return _mutate(self.root, self.configuration, adoption.adopt, basis["run_id"], identity, precedent, uuid.uuid4().hex)

    def request_exit(self, *, discard_queue=False):
        if not discard_queue and self._confirm_queue_exit():
            return
        if self.busy:
            self.exit_after_work = True
            if self.question is not None:
                self._cancel_question()
            self._log("現在の操作の区切りで閉じます。外部処理を強制終了して再送することはしません。", owner=True)
        else:
            self.app.exit(result=0)

    async def _refresh(self):
        if self.practice:
            return
        try:
            if not self.readonly:
                try:
                    publish_cursor(self.root, self.session_id, self.selected, busy=self.busy,
                                   waiting=self.question is not None, phase=self.phase)
                    self.cursor_error = None
                except OSError:
                    self.cursor_error = self._tr("Status sharing with other terminals is unavailable. Ledger storage is separate.", "別端末向けの状態通知が停止しています。台帳の保存状態とは別です。")
            view = await self._read_session_views()
            self.view, self.read_error = view, None
            from .context_meter import read as read_context
            self.context_composition = await self.loop.run_in_executor(self.read_executor, read_context, self.root)
            await self._refresh_live_learning()
            if not self.readonly:
                from .personal_growth import ui_state
                try:
                    self.personal_view = await self.loop.run_in_executor(
                        self.read_executor, ui_state, self.personal_view)
                    self.personal_error = None
                except Exception as error:
                    self.personal_error = type(error).__name__
            growth = view.get("growth") or {}
            focus = growth.get("focus")
            identity = (focus["run_id"], focus["id"]) if focus else None
            if not self.view_primed:
                self.announced_growth = identity
                self.view_primed = True
            elif (not self.busy and growth.get("automatic_card") and identity != self.announced_growth
                  and not (self.personal_view or {}).get("settings", {}).get("onboarded")):
                self.announced_growth = identity
                if focus:
                    self._transfer("agent_to_owner", "learning:" + focus["id"], focus["concept"], self._tr("An optional insight", "持ち帰る理解"))
            if self.readonly:
                cursor = view.get("cursor") or {}
                self.phase = cursor.get("phase", "recorded") if cursor.get("live") else "Owner offline / historical ledger"
        except (LedgerError, config.ConfigError, sqlite3.Error, OSError, ValueError) as error:
            self.read_error = getattr(error, "code", type(error).__name__)
            # Keep the last valid projection. Reopen on the next poll rather
            # than leaving a failed SQLite connection or a dead polling task.
            try:
                await self.loop.run_in_executor(self.read_executor, self.reader.close)
            except (sqlite3.Error, OSError):
                pass
        self._render()

    async def _poll(self):
        while not self.closed:
            await self._refresh()
            self._start_next_queued()
            await asyncio.sleep(1)

    async def run(self):
        from .keyboard_protocol import enhanced_enter
        with enhanced_enter(self.output) as enable:
            self.enable_keys = enable
            if self.reader is None:
                self.loop = asyncio.get_running_loop()
                self._render()
                try:
                    return await self.app.run_async(pre_run=enable)
                finally:
                    self.closed = True
                    if self.motion_task is not None:
                        self.motion_task.cancel()
                    self.read_executor.shutdown(wait=True)
                    self.work_executor.shutdown(wait=True)
                    self.note_executor.shutdown(wait=True)
            return await self._run_session()

    async def _run_session(self):
        self.loop = asyncio.get_running_loop()
        await self._refresh()
        poller = asyncio.create_task(self._poll())
        try:
            def start():
                self.enable_keys()
                if self.initial_request and not self.readonly:
                    self.start_action("work", request=self.initial_request)
            return await self.app.run_async(pre_run=start)
        finally:
            self.closed = True
            self._cancel_question()
            if self.work_task is not None and not self.work_task.done():
                # No fire-and-forget retry; let the existing bounded invocation finish.
                await self.work_task
            if self.note_task is not None and not self.note_task.done():
                await self.note_task
            if self.motion_task is not None:
                self.motion_task.cancel()
                try:
                    await self.motion_task
                except asyncio.CancelledError:
                    pass
            poller.cancel()
            try:
                await poller
            except asyncio.CancelledError:
                pass
            await self.loop.run_in_executor(self.read_executor, self.reader.close)
            self.read_executor.shutdown(wait=True)
            self.work_executor.shutdown(wait=True)
            self.note_executor.shutdown(wait=True)
            if not self.readonly:
                try:
                    publish_cursor(self.root, self.session_id, self.selected, busy=False, waiting=False, phase=self.phase, closed=True)
                except OSError:
                    pass


def interact(root, configuration, onboarding=False, initial_request=None):
    with owner_lock(root):
        from .personal_console import first_open
        from .interaction_text import language
        with language(configuration):
            first_open(root, configuration)
        from .onboarding_walkthrough import offer
        offer(root, configuration)
        session = Cleanroom(root, configuration, initial_request=initial_request)
        asyncio.run(session.run())
    print("Cleanroomを閉じました。保存された判断・候補・証拠・理解はローカル台帳に残ります。")
    return {"ok": True, "status": "CLOSED", "run_id": session.selected}


def watch(root, configuration, *, run_id=None, once=False, as_json=False, plain=False):
    if once or as_json or plain or not capable_terminal():
        reader = Reader(root, configuration)
        try:
            view = reader.read(run_id, follow=True)
        finally:
            reader.close()
        if as_json:
            print(json.dumps(public_view(view), ensure_ascii=False, indent=2))
        else:
            print("CLEANROOM WATCH / READ ONLY / model calls: 0")
            print(str(view["run_id"] or "no run") + " / revision " + str(view["revision"]))
            print(view["panes"]["agent"])
        return 0
    return asyncio.run(Cleanroom(root, configuration, readonly=True, run_id=run_id).run()) or 0
