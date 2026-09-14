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


class OwnerCancelled(Exception):
    pass


@dataclass
class Question:
    title: str
    answer: Future
    choices: list | None = None
    default: str = ""


class Cleanroom:
    def __init__(self, root, configuration, *, readonly=False, run_id=None, initial_request=None):
        self.root, self.configuration = Path(root), configuration
        self.readonly, self.selected, self.initial_request = readonly, run_id, initial_request
        self.session_id = uuid.uuid4().hex
        self.reader = Reader(root, configuration)
        self.read_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cleanroom-ledger")
        self.work_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cleanroom-owner")
        self.note_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cleanroom-local-note")
        self.view = None
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
        self._build()

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
        from prompt_toolkit.styles import Style
        from prompt_toolkit.widgets import Frame, Label, TextArea

        from .cleanroom_owner import OwnerCompleter
        completer = ConditionalCompleter(OwnerCompleter(self._visible_owner_items, self.reference_bindings),
                                         filter=Condition(lambda: self.question is None and not self.readonly))
        self.input = TextArea(multiline=True, height=Dimension(min=1, max=5),
                              prompt="  > ", accept_handler=self._submit, wrap_lines=True,
                              completer=completer, complete_while_typing=True)
        self.owner_input = TextArea(multiline=True, height=Dimension(min=1, max=4),
                                    prompt="  > ", accept_handler=self._submit_owner, wrap_lines=True)
        self.owner_input.window.style = self._owner_style
        self.areas = {name: TextArea(read_only=True, scrollbar=True, wrap_lines=True)
                      for name in ("owner", "agent", "evidence", "notebook", "review")}
        frames = {name: Frame(area, title=title, width=Dimension(weight=3 if name == "owner" else 2))
                  for (name, area), title in zip(self.areas.items(), (
                      "Owner Console / 判断と理解", "Agent Workbench / 閲覧専用",
                      "Evidence / 記録した検査", "Notebook / 仕事から残るもの", "Review / 人間に必要なこと"))}
        self.frames = frames
        self.menu_control = FormattedTextControl(self._menu_text, focusable=True,
                                                 get_cursor_position=lambda: Point(0, self.choice_index))
        self.menu_window = Window(self.menu_control, wrap_lines=True, height=Dimension(min=2, max=13))
        self.dialog = Frame(HSplit([
            Window(FormattedTextControl(self._question_title), wrap_lines=True, height=Dimension(min=1, max=7)),
            self.menu_window,
            Window(FormattedTextControl(" Up/Down: choose   Enter: select   Esc: keep unchanged"), height=1, style="class:muted"),
        ]), title="One choice / あなたの選択", width=Dimension(preferred=76, max=96))
        growth_margin = ConditionalContainer(Frame(HSplit([
            Window(FormattedTextControl(self._growth_card), wrap_lines=True, height=Dimension(min=2, max=4)),
            Window(FormattedTextControl(self._growth_actions), wrap_lines=True, height=Dimension(min=1, max=2)),
        ]), title="Keep one insight / 今回持ち帰る理解"), filter=Condition(self._growth_visible))
        owner_field = ConditionalContainer(Frame(HSplit([
            Window(FormattedTextControl(self._owner_title), height=1, style=self._owner_style),
            self.owner_input,
        ]), title="Owner / local only"), filter=Condition(lambda: not self.readonly))
        self.agent_column = HSplit([
            frames["agent"],
            ConditionalContainer(Window(FormattedTextControl(self._input_title),
                                        height=Dimension(min=1, max=4), wrap_lines=True),
                                 filter=Condition(lambda: not self.readonly)),
            ConditionalContainer(Frame(self.input, title="Agent / あなたからの依頼"),
                                 filter=Condition(lambda: not self.readonly)),
        ], width=Dimension(weight=2))
        self.owner_column = HSplit([
            owner_field,
            ConditionalContainer(Window(FormattedTextControl(self._handoff_text),
                                        height=Dimension(min=1, max=3), wrap_lines=True, style="class:handoff"),
                                 filter=Condition(lambda: self.handoff is not None)),
            DynamicContainer(lambda: self.frames[self._owner_page()]),
            growth_margin,
        ], width=Dimension(weight=3))
        self.split_side = VSplit([self.agent_column,
                                 Window(FormattedTextControl(self._vertical_boundary), width=3, style="class:boundary"),
                                 self.owner_column])
        self.split_stack = HSplit([self.agent_column,
                                  Window(FormattedTextControl(self._horizontal_boundary), height=1, style="class:boundary"),
                                  self.owner_column])
        content = HSplit([
            Window(FormattedTextControl(self._header), height=3, style="class:header"),
            Window(FormattedTextControl(self._tabs), height=1),
            DynamicContainer(self._body),
            Window(FormattedTextControl(self._footer), height=2, wrap_lines=True, style="class:muted"),
        ])
        root = FloatContainer(content=content, floats=[Float(content=ConditionalContainer(
            self.dialog, filter=Condition(lambda: self.picker is not None))),
            Float(xcursor=True, ycursor=True, content=ConditionalContainer(CompletionsMenu(max_height=8, scroll_offset=1),
                filter=Condition(lambda: self.picker is None and not self.readonly
                                 and self.app.layout.has_focus(self.input))))])
        bindings = KeyBindings()
        picking = Condition(lambda: self.picker is not None)

        @bindings.add("up", filter=picking, eager=True)
        def up(event):
            self.choice_index = max(0, self.choice_index - 1)

        @bindings.add("down", filter=picking, eager=True)
        def down(event):
            self.choice_index = min(len(self.picker["choices"]) - 1, self.choice_index + 1)

        @bindings.add("enter", filter=picking, eager=True)
        def choose(event):
            picker = self.picker
            value = picker["choices"][self.choice_index][0]
            self.picker = None
            self._focus_input()
            picker["callback"](value)

        @bindings.add("enter", filter=Condition(lambda: self.picker is None and not self.readonly and self.app.layout.has_focus(self.input)))
        def submit(event):
            if self.input.buffer.complete_state is not None:
                self._accept_owner_completion()
                return
            self.input.buffer.validate_and_handle()

        @bindings.add("enter", filter=Condition(lambda: self.picker is None and not self.readonly and self.app.layout.has_focus(self.owner_input)))
        def submit_owner(event):
            self.owner_input.buffer.validate_and_handle()

        completing = Condition(lambda: self.picker is None and self.question is None and not self.readonly
                               and self.app.layout.has_focus(self.input) and self.input.buffer.complete_state is not None)

        @bindings.add("down", filter=completing, eager=True)
        def next_reference(event):
            self.input.buffer.complete_next()

        @bindings.add("up", filter=completing, eager=True)
        def previous_reference(event):
            self.input.buffer.complete_previous()

        @bindings.add("escape", "enter", filter=Condition(lambda: not self.readonly))
        @bindings.add("c-j", filter=Condition(lambda: not self.readonly))
        def newline(event):
            if self.picker is None:
                field = self.owner_input if self.app.layout.has_focus(self.owner_input) else self.input
                field.buffer.insert_text("\n")

        @bindings.add("f2", eager=True)
        def menu(event):
            if self.picker is None:
                self.open_menu()

        @bindings.add("tab", eager=True)
        def complete_reference(event):
            if self.picker is not None:
                self.choice_index = (self.choice_index + 1) % len(self.picker["choices"])
            elif not self.readonly and self.app.layout.has_focus(self.input) and self.question is None:
                if self.input.buffer.complete_state is not None:
                    self._accept_owner_completion()
                else:
                    self.input.buffer.start_completion(select_first=False)

        @bindings.add("escape", eager=False)
        def back(event):
            if self.input.buffer.complete_state is not None and self.picker is None:
                self.input.buffer.cancel_completion()
            elif self.picker is not None:
                picker, self.picker = self.picker, None
                self._focus_input()
                picker["callback"](None)
            elif self.question is not None:
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

        @bindings.add("c-c", eager=True)
        def interrupt(event):
            if self.question is not None:
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
            "owner.memo": "bg:#483619 fg:#ffe6a1", "owner.search": "bg:#153d2b fg:#bceccc",
            "boundary": "#698b7a", "handoff": "#c7ba80",
            "completion-menu": "bg:#23372e fg:#e3e6d8",
            "completion-menu.completion.current": "bg:#60795c fg:#ffffff bold",
        })
        self.app = Application(layout=Layout(root, focused_element=self.areas["agent"] if self.readonly else self.input),
                               full_screen=True, key_bindings=bindings, mouse_support=True, style=style,
                               color_depth=ColorDepth.DEPTH_1_BIT if "NO_COLOR" in os.environ else None,
                               refresh_interval=1 if os.environ.get("VERANTYX_REDUCE_MOTION") == "1" else .3)
        self.owner_input.buffer.on_text_changed += self._owner_text_changed

    def _owner_page(self):
        return self.focus_name if self.focus_name in ("owner", "evidence", "notebook", "review") else "owner"

    def _body(self):
        if self.focus_name == "agent":
            return self.agent_column
        if self.focus_name in ("owner", "evidence", "notebook", "review"):
            return self.owner_column
        size = self.app.output.get_size()
        mode = layout_mode(size.columns, size.rows)
        return (self.split_side if mode == "side" else self.split_stack if mode == "stack"
                else self.owner_column if self.active_input == "owner" else self.agent_column)

    def _header(self):
        view = self.view or {}
        run_id = view.get("run_id") or self.selected or "no run yet"
        freshness = "Ledger read pending" if self.view is None else "Ledger synced"
        if self.read_error:
            freshness = "STALE / 前回の表示を保持: " + self.read_error
        cursor = view.get("cursor") or {}
        if self.readonly:
            owner = "Owner live" if cursor.get("live") else "Owner offline / historical ledger"
            phase = cursor.get("phase", "idle") if cursor.get("live") else "recorded"
        else:
            owner, phase = "Owner Console", self.phase
        elapsed = f" / {int(time.monotonic() - self.started)}s" if self.busy and self.started else ""
        name = safe_text(self.configuration["project"]["name"])
        return (f" CLEANROOM  /  {name}  /  {'READ ONLY' if self.readonly else 'One project, one notebook'}\n"
                f" {safe_text(run_id)}  r{view.get('revision', 0)} / ledger {view.get('project_revision', 0)} / notes {view.get('owner_note_revision', 0)}\n"
                f" {freshness}  |  {owner}  |  {safe_text(phase)}{elapsed}")

    def _tabs(self):
        fragments = []
        for name in ("split", "owner", "agent", "evidence", "notebook", "review"):
            def click(event, name=name):
                from prompt_toolkit.mouse_events import MouseEventType
                if event.event_type == MouseEventType.MOUSE_UP and self.picker is None:
                    self.focus_name = name
                    self._focus_input()
            fragments.append(("class:tab.active" if name == self.focus_name else "class:tab", "  " + name.title() + "  ", click))
        return fragments

    def _footer(self):
        message = self.cursor_error or "台帳の表示は承認ではありません。検査は記録時点の対象に限定されます。"
        if self.read_error:
            message = "DBの読み取りを再接続待ち。前回の正常な表示: " + str((self.view or {}).get("read_at") or "まだありません。")
        if self.readonly:
            return " F2 Menu | Alt+1..4 Views | F3 Scroll | F4 Learn | Ctrl+D Close\n " + message
        return " Empty Enter: Agent > Memo > Search | Tab: reference | F2 Menu | F3 Scroll | F4 Learn\n " + message

    def _input_title(self):
        if self.question is not None:
            return " OWNER / " + safe_text(self.question.title, multiline=True) + (
                " [" + safe_text(self.question.default) + "]" if self.question.default else "")
        if self.busy:
            return " AGENT / 次の依頼を下書きできます。空欄のEnterでOwnerのメモ・検索へ。"
        count = sum(token in self.input.text for token in self.reference_bindings)
        return (" AGENT / 依頼を書く。Owner項目の先頭2文字から候補、矢印 + Tabで参照。"
                + (f" 選択中 {count}件。" if count else ""))

    def _owner_style(self):
        return "class:owner.memo" if self.owner_mode == "memo" else "class:owner.search"

    def _owner_title(self):
        if self.owner_mode == "memo":
            saving = self.note_task is not None and not self.note_task.done()
            return " MEMO / 黄色 / " + ("保存中" if saving else "Enterでローカル保存。空欄のEnterで検索へ")
        return " SEARCH / 緑 / Owner内だけを検索。空欄のEnterでAgentへ"

    def _owner_text_changed(self, buffer):
        self.owner_drafts[self.owner_mode] = buffer.text
        if self.owner_mode == "search":
            self.growth_selection = None
            self.preview = None
            self.areas["owner"].buffer.cursor_position = 0
        self._render()

    def _owner_items(self):
        from .cleanroom_owner import make_item
        items = list((self.view or {}).get("owner_items", []))
        recorded_request = ((self.view or {}).get("state") or {}).get("request", "")
        if self.pending_request and recorded_request.split("\n\n[Owner-selected references:", 1)[0] != self.pending_request:
            item = make_item("request", self.pending_request.splitlines()[0],
                             {"request": self.pending_request, "status": "SESSION_ONLY_NOT_EXECUTION"},
                             run_id=self.selected, source_ref="session:" + self.session_id)
            items.insert(0, item)
        if self.question is not None:
            items.insert(0, make_item("question", self.question.title, self.question.title,
                                     run_id=self.selected, source_ref="session-question:" + self.session_id))
        return items

    def _visible_owner_items(self):
        from .cleanroom_owner import search
        query = self.owner_input.text if self.owner_mode == "search" else ""
        return search(self._owner_items(), query)[:60]

    def _cycle_inputs(self):
        self.input.buffer.cancel_completion()
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
        self.focus_name = "split"
        self._focus_input()
        self._render()

    def _submit_owner(self, buffer):
        if self.readonly:
            return True
        self.active_input = "owner"
        body = buffer.text.strip()
        if not body:
            self._cycle_inputs()
            return True
        if self.owner_mode == "search":
            self.focus_name = "split"
            self._render()
            return True
        if self.note_task is not None and not self.note_task.done():
            return True
        if len(body) > 4000:
            self._log("メモは4000文字以内に分けてください。入力内容は残しています。", owner=True)
            return True
        if self.note_intent is None or self.note_intent[1:] != (body, self.selected):
            self.note_intent = (uuid.uuid4().hex, body, self.selected)
        self.note_task = asyncio.create_task(self._save_owner_note(self.note_intent))
        return True

    async def _save_owner_note(self, intent):
        from .cleanroom_owner import save_note
        key, body, run_id = intent
        try:
            await self.loop.run_in_executor(self.note_executor, lambda: save_note(self.root, body, key=key, run_id=run_id))
            if self.owner_drafts["memo"].strip() == body:
                self.owner_drafts["memo"] = ""
            if self.owner_mode == "memo" and self.owner_input.text.strip() == body:
                self.owner_input.buffer.reset()
            self.note_intent = None
            self._log("Ownerメモをローカル保存しました。Agentには送信していません。", owner=True)
            await self._refresh()
        except (LedgerError, OSError, ValueError) as error:
            self._log("メモの保存結果を確認できません: " + getattr(error, "code", type(error).__name__)
                      + "。入力を保持しています。同じ内容の再保存は同じ操作キーを使います。", owner=True)
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
            self._transfer("owner_to_agent", item["id"], item["label"], "選択した参照")

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
        for index, (_, label) in enumerate(self.picker["choices"]):
            style = "class:menu.selected" if index == self.choice_index else ""
            fragments.append((style, (" > " if index == self.choice_index else "   ") + safe_text(label) + "\n"))
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

    def _show_picker(self, title, choices, callback):
        self.choice_index = 0
        self.picker = {"title": title, "choices": [(None, "Back / 変更せず戻る"), *choices], "callback": callback}
        self.app.layout.focus(self.menu_control)
        self.app.invalidate()

    def _log(self, value, *, owner=False):
        value = safe_text(str(value).strip(), multiline=True)
        if value:
            self.logs.append(value[:8000])
            if owner:
                self.notes.append(value[:8000])
        self._render()

    def notice(self, value):
        self.loop.call_soon_threadsafe(lambda: self._log(value, owner=True))

    def _present_question(self, question):
        if self.closed:
            question.answer.set_exception(OwnerCancelled())
            return
        self.question = question
        self._transfer("agent_to_owner", "question-" + uuid.uuid4().hex, question.title, "人間への確認")
        self.saved_draft = self.input.buffer.document
        self.input.buffer.reset()
        self.phase = "waiting for your choice"
        if question.choices is not None:
            self._show_picker(question.title, question.choices, self._answer)
        else:
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
            return self.choose(title, [("y", "Confirm / 確認した操作だけを進める")]) or "n"
        question = Question(title, Future(), default=default)
        self.loop.call_soon_threadsafe(self._present_question, question)
        value = question.answer.result()
        return str(value or default).strip()

    def choose(self, title, choices):
        question = Question(title, Future(), choices=list(choices))
        self.loop.call_soon_threadsafe(self._present_question, question)
        return question.answer.result()

    def _submit(self, buffer):
        value = buffer.text.strip()
        if self.readonly:
            return True
        self.active_input = "agent"
        if not value:
            self._cycle_inputs()
            return True
        if self.question is not None:
            self._answer(value)
            return True
        if self.busy:
            self._log("現在の操作を実行中です。入力は下書きとして残しています。", owner=True)
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
                self._log("選択する参照は8件以内、依頼と参照の合計は12000文字以内にしてください。内容は省略せず入力を保持しました。", owner=True)
                return True
            self._transfer("agent_to_owner", "request-" + uuid.uuid4().hex, value.splitlines()[0], "あなたの依頼")
            self.start_action("work", request=value, owner_references=references)
        return True

    def open_menu(self):
        if self.question is not None:
            self._log("先に表示中の選択へ回答するか、Escでその操作を中止してください。", owner=True)
            return
        choices = [(name, label) for name, label in (
            ("split", "Work / 人間とAIを一緒に見る"), ("owner", "Owner / 目的・判断・理解"),
            ("agent", "Agent / 作業記録を読む"), ("evidence", "Evidence / 検査と限界を見る"),
            ("notebook", "Notebook / 仕事から残ったもの"), ("review", "Review / 判断・採用・学習方針"))]
        if not self.busy:
            choices += [("history", "History / 別の仕事を開く")]
            choices += [("growth", "Learn together / 今回持ち帰る理解を開く")]
            if self.readonly:
                choices += [("follow", "Follow Owner / 人間側と同じ仕事を追う")]
            else:
                choices += [("review-action", "Review actions / 今必要な操作を選ぶ"),
                            ("models", "Models & Providers / AI接続を設定"), ("scope", "Workspace / 送信候補の範囲"),
                            ("learn", "Learning library / 保存した学習・検査を詳しく見る")]
        choices += [("help", "About / 使い方と境界"), ("quit", "Close / この画面を閉じる")]

        def selected(value):
            if value in ("split", *self.areas):
                self.focus_name = value
            elif value == "history":
                self.open_history()
            elif value == "growth":
                self.open_growth()
            elif value == "follow":
                self.selected = None
            elif value == "quit":
                self.request_exit()
            elif value == "help":
                self.growth_selection = None
                self.preview = ("CLEANROOM / TWO VIEWS, ONE PROJECT\n\n"
                                "一文で依頼し、送信範囲を確認してから作業を始めます。\n"
                                "左下のAgent入力は人間からの依頼、右上のOwner入力はローカルのメモ・検索です。\n"
                                "空欄のEnterで、Agent → 黄色のメモ → 緑の検索 → Agentへ巡回します。\n"
                                "Owner項目名の先頭2文字で候補が出ます。矢印で選びTabで参照を差し込みます。\n"
                                "F2でメニュー、矢印とEnterで選択できます。\n"
                                "F3で本文へ移り、矢印やPageUp/Downで読み、Escで入力に戻ります。\n"
                                "Alt+0で分割、Alt+1..4で各ページへ移動できます。\n"
                                "F4で今回の理解を開き、読む・自分の言葉・後で・参照・委譲を選べます。\n"
                                "読むだけでは理解済みにしません。学習しなくても開発は続けられます。\n"
                                "verantyx watch は別端末から同じ記録を読むだけです。\n"
                                "閲覧による追加のモデル呼出しや承認はありません。\n\n"
                                "記録された検査は現在のファイルの再検査ではありません。\n"
                                "画面分割はOSの隔離機能ではありません。\n"
                                "処理中に閉じる場合は、現在の処理の区切りを待ちます。\n"
                                "強制終了時の外部処理結果はUNKNOWNになり得ます。自動再送しません。\n"
                                "Escでこの説明を閉じます。")
                self.focus_name = "owner"
            elif value:
                self.start_action(value)
            self._render()
            if self.picker is None:
                self._focus_input()
        self._show_picker("Cleanroom / 何を見ますか？", choices, selected)

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
        from prompt_toolkit.document import Document
        panes = (self.view or {}).get("panes", {})
        for name, area in self.areas.items():
            body = panes.get(name, "読み取り専用で台帳を開いています。")
            if name == "owner":
                from .cleanroom_owner import render_owner
                query = self.owner_input.text if self.owner_mode == "search" else ""
                body = render_owner(self.view or {}, self._owner_items(), query)
                growth_item = self._growth_item(selected_only=True)
                if growth_item is not None and not query:
                    from .cleanroom_growth import lesson
                    body = lesson(growth_item)
                elif self.preview is not None and not query:
                    body = self.preview
                if self.notes and not query:
                    body += "\n\nSESSION NOTES / 台帳とは別の操作案内\n" + "\n".join(self.notes)
            if name == "agent":
                body = "SESSION OBSERVATION / 証拠ではありません\n" + safe_text(self.phase) + "\n\n" + body
                if self.logs:
                    body += "\n\nLOCAL OPERATION MESSAGES / 未永続化\n" + "\n".join(self.logs)
            body = safe_text(body, multiline=True)
            if body != area.text:
                position = min(area.buffer.cursor_position, len(body))
                area.buffer.set_document(Document(body, cursor_position=position), bypass_readonly=True)
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
        self._log("Phase: " + self.phase)

    def _model_progress(self, event):
        # Never expose hidden reasoning or treat a provider's self-check as proof.
        if event.get("kind") == "start":
            self._log("Model request: " + safe_text(event.get("model", "configured model")))
        elif event.get("kind") == "output":
            self._log("Response received: " + str(event.get("characters", 0)) + " characters / not evidence")
        elif event.get("kind") == "validated":
            self._log("Model response format checked / not an independent correctness check")

    def start_action(self, action, **kwargs):
        if self.readonly or self.busy:
            return
        self.busy, self.phase, self.started = True, "preparing", time.monotonic()
        self.preview = None
        if action == "work":
            self.pending_request = kwargs["request"]
        basis = deepcopy(self.view)
        self.work_task = asyncio.create_task(self._run_operation(action, basis, kwargs))

    async def _run_operation(self, action, basis, kwargs):
        follow_up_ui = None
        def invoke():
            from .progress import observe
            with bind(self), observe(lambda stage: self.loop.call_soon_threadsafe(self._progress, stage),
                                     lambda event: self.loop.call_soon_threadsafe(self._model_progress, dict(event))):
                return self._operation(action, basis, **kwargs)
        try:
            result = await self.loop.run_in_executor(self.work_executor, invoke)
            if isinstance(result, dict):
                follow_up_ui = result.get("ui_action")
                self.last_result = result
                if result.get("run_id"):
                    self.selected = result["run_id"]
                self._log("操作結果: " + str(result.get("status", "RECORDED")) + " / 証拠と理解の状態は台帳で別々に表示します。", owner=True)
                if result.get("reason"):
                    self._log(str(result["reason"]), owner=True)
            self.phase = "idle"
        except OwnerCancelled:
            self.phase = "paused"
            self._log("今回の未実行操作を中止しました。既に記録された結果は取り消しません。", owner=True)
        except (LedgerError, config.ConfigError, sqlite3.Error, OSError, ValueError) as error:
            self.phase = "needs attention"
            self._log("操作を完了できませんでした: " + getattr(error, "code", type(error).__name__)
                      + "\n自動で再試行しません。失敗・結果不明・記録済みを台帳で区別してください。", owner=True)
        except Exception as error:
            self.phase = "needs attention"
            self._log("操作を中断しました: " + type(error).__name__ + " / 成功として扱わず、自動再送もしません。", owner=True)
        finally:
            self.busy = False
            self.started = None
            self._render()
            if self.exit_after_work:
                self.app.exit(result=0)
            elif follow_up_ui == "open_growth":
                self.open_growth()

    def _operation(self, action, basis, **kwargs):
        from . import development_console as console
        from .development import run_work
        from .constitution import prepare
        from .model_settings import activate_codex, clear, describe
        if action == "work":
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

    def request_exit(self):
        if self.busy:
            self.exit_after_work = True
            if self.question is not None:
                self._cancel_question()
            self._log("現在の操作の区切りで閉じます。外部処理を強制終了して再送することはしません。", owner=True)
        else:
            self.app.exit(result=0)

    async def _refresh(self):
        try:
            if not self.readonly:
                try:
                    publish_cursor(self.root, self.session_id, self.selected, busy=self.busy,
                                   waiting=self.question is not None, phase=self.phase)
                    self.cursor_error = None
                except OSError:
                    self.cursor_error = "別端末向けの状態通知が停止しています。台帳の保存状態とは別です。"
            view = await self.loop.run_in_executor(self.read_executor, self.reader.read, self.selected, self.readonly)
            self.view, self.read_error = view, None
            growth = view.get("growth") or {}
            focus = growth.get("focus")
            identity = (focus["run_id"], focus["id"]) if focus else None
            if not self.view_primed:
                self.announced_growth = identity
                self.view_primed = True
            elif not self.busy and growth.get("automatic_card") and identity != self.announced_growth:
                self.announced_growth = identity
                if focus:
                    self._transfer("agent_to_owner", "learning:" + focus["id"], focus["concept"], "持ち帰る理解")
            if not self.readonly and self.selected is None:
                self.selected = view["run_id"]
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
            await asyncio.sleep(1)

    async def run(self):
        self.loop = asyncio.get_running_loop()
        await self._refresh()
        poller = asyncio.create_task(self._poll())
        try:
            def start():
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
