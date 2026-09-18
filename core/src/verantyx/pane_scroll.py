"""Reading-pane scrolling and mouse capture across pane boundaries."""
import asyncio
from functools import wraps

from prompt_toolkit.filters import Condition
from prompt_toolkit.mouse_events import MouseButton, MouseEventType
from prompt_toolkit.selection import SelectionType
from prompt_toolkit.utils import get_cwidth


class ReadingScroll:
    def __init__(self, session):
        self.session = session
        self.point = None
        self.task = None
        self.moved = False

    def available(self):
        s = self.session
        return (not s.native_selection
                and (s.picker is None or s.picker.get("inline", False))
                and s.input.buffer.complete_state is None
                and s.owner_input.buffer.complete_state is None)

    def target(self):
        s = self.session
        if s.reading_drag is not None:
            return next((n, a) for n, a in s._reading_areas().items() if a is s.reading_drag)
        return s._reading_target()

    def move(self, direction, page=False):
        s = self.session
        name, area = self.target()
        window = area.window
        if window.render_info is None:
            return
        height = max(1, window.render_info.window_height)
        maximum = max(0, area.buffer.document.line_count - height)
        current = max(0, min(maximum, window.vertical_scroll))
        selecting = area.buffer.selection_state is not None or s.reading_drag is area
        if (name == "owner" and not selecting and current == (maximum if direction > 0 else 0)
                and s._archive_scroll(direction, window)):
            return
        distance = max(1, height - 2) if page else 1
        top = max(0, min(maximum, current + direction * distance))
        state = s.reading_views.get(name)
        if state:
            state.follow = not selecting and name == "agent" and direction > 0 and top == maximum
            if state.follow:
                state.unseen = False
        window.vertical_scroll, window.vertical_scroll_2 = top, 0
        if s.reading_drag is area and self.point is not None:
            self.extend(self.point)
        else:
            document = area.buffer.document
            row = max(top, min(top + height - 1, document.cursor_position_row))
            # Moving the endpoint retains the original selection anchor.
            area.buffer.cursor_position = document.translate_row_col_to_index(row, document.cursor_position_col)
        s.app.invalidate()

    def extend(self, point):
        area = self.session.reading_drag
        if area is None or area.window.render_info is None:
            return
        self.point = point
        info = area.window.render_info
        document = area.buffer.document
        row = area.window.vertical_scroll + max(0, min(info.window_height - 1, point.y - info._y_offset))
        row = min(row, document.line_count - 1)
        cells = max(0, point.x - info._x_offset)
        used = column = 0
        for character in document.lines[row]:
            width = max(0, get_cwidth(character))
            if used + width > cells:
                break
            used += width
            column += 1
        position = document.translate_row_col_to_index(row, column)
        if position != area.buffer.cursor_position and area.buffer.selection_state is None:
            area.buffer.start_selection(selection_type=SelectionType.CHARACTERS)
        area.buffer.cursor_position = position
        self.session.app.invalidate()

    def direction(self):
        area = self.session.reading_drag
        if area is None or self.point is None or area.window.render_info is None:
            return 0
        info = area.window.render_info
        if self.point.y <= info._y_offset:
            return -1
        if self.point.y >= info._y_offset + info.window_height - 1:
            return 1
        return 0

    async def auto_scroll(self):
        try:
            while self.session.reading_drag is not None and self.available():
                await asyncio.sleep(.08)
                direction = self.direction()
                if direction:
                    self.move(direction)
        finally:
            self.task = None

    def stop(self):
        if self.task is not None:
            self.task.cancel()
        self.point = None
        self.moved = False

    def route(self, app):
        if self.session.native_selection:
            return
        wrappers = {}

        def wrap(handler):
            original = getattr(handler, "_cleanroom_original", handler)
            if original not in wrappers:
                @wraps(original)
                def dispatch(event):
                    s = self.session
                    if self.available():
                        if event.event_type in (MouseEventType.SCROLL_UP, MouseEventType.SCROLL_DOWN):
                            self.move(-1 if event.event_type == MouseEventType.SCROLL_UP else 1)
                            return None
                        if s.reading_drag is not None:
                            if event.event_type == MouseEventType.MOUSE_MOVE and event.button == MouseButton.LEFT:
                                self.moved = True
                                self.extend(event.position)
                                if self.task is None and app.is_running:
                                    self.task = app.create_background_task(self.auto_scroll())
                                return None
                            if event.event_type == MouseEventType.MOUSE_UP and self.moved:
                                self.extend(event.position)
                                s._finish_reading_drag()
                                return None
                    try:
                        result = original(event)
                        if event.event_type == MouseEventType.MOUSE_DOWN and s.reading_drag is not None:
                            self.point = event.position
                        return result
                    finally:
                        if event.event_type == MouseEventType.MOUSE_UP and s.reading_drag is not None:
                            s._finish_reading_drag()
                dispatch._cleanroom_original = original
                wrappers[original] = dispatch
            return wrappers[original]

        raster = app.renderer.mouse_handlers.mouse_handlers
        # Capture releases and drags over frames, margins and the other pane.
        for row in raster.values():
            for column, handler in list(row.items()):
                row[column] = wrap(handler)


def install_pane_scroll(session, bindings):
    scroll = session.reading_scroll = ReadingScroll(session)
    available = Condition(scroll.available)
    for key, direction, page in (("pageup", -1, True), ("pagedown", 1, True),
                                  ("c-up", -1, False), ("c-down", 1, False)):
        bindings.add(key, filter=available, eager=True)(
            lambda event, direction=direction, page=page: scroll.move(direction, page))
    bindings.add("c-home", filter=available, eager=True)(lambda event: session._reading_jump(False))
    bindings.add("c-end", filter=available, eager=True)(lambda event: session._reading_jump(True))
    session.app.after_render += scroll.route
