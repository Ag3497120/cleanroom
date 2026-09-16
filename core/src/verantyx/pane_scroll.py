"""Scroll the selected reading pane in physical rows, retaining editor drafts.

Native terminal scrollback remains controlled by the terminal. F7 releases mouse
reporting for native text selection; normal wheel events stay in the active pane.
"""
from functools import wraps

from prompt_toolkit.filters import Condition
from prompt_toolkit.mouse_events import MouseEventType


def install_pane_scroll(session, bindings):
    def available():
        return (not session.native_selection
                and (session.picker is None or session.picker.get("inline", False))
                and session.input.buffer.complete_state is None
                and session.owner_input.buffer.complete_state is None)

    def move(direction, page=False):
        name, area = session._reading_target()
        window = area.window
        if (window.render_info is None or area.buffer.selection_state is not None
                or session.reading_drag is area):
            return
        height = max(1, window.render_info.window_height)
        maximum = max(0, area.buffer.document.line_count - height)
        current = max(0, min(maximum, window.vertical_scroll))
        at_edge = current == (maximum if direction > 0 else 0)
        if name == "owner" and at_edge and session._archive_scroll(direction, window):
            return
        # Reading buffers contain display rows. Do not use prompt_toolkit's
        # private scroll helpers, which count logical lines in wrapped buffers.
        distance = max(1, height - 2) if page else 1
        top = max(0, min(maximum, current + direction * distance))
        state = session.reading_views.get(name)
        if state:
            state.follow = name == "agent" and direction > 0 and top == maximum
            if state.follow:
                state.unseen = False
        document = area.buffer.document
        row = max(top, min(top + height - 1, document.cursor_position_row))
        area.buffer.cursor_position = document.translate_row_col_to_index(row, document.cursor_position_col)
        window.vertical_scroll, window.vertical_scroll_2 = top, 0
        session.app.invalidate()

    @bindings.add("pageup", filter=Condition(available), eager=True)
    def page_up(event):
        move(-1, page=True)

    @bindings.add("pagedown", filter=Condition(available), eager=True)
    def page_down(event):
        move(1, page=True)

    @bindings.add("c-up", filter=Condition(available), eager=True)
    def line_up(event):
        move(-1)

    @bindings.add("c-down", filter=Condition(available), eager=True)
    def line_down(event):
        move(1)

    @bindings.add("c-home", filter=Condition(available), eager=True)
    def first(event):
        session._reading_jump(False)

    @bindings.add("c-end", filter=Condition(available), eager=True)
    def latest(event):
        session._reading_jump(True)

    def route_wheel(app):
        if session.native_selection:
            return
        raster = app.renderer.mouse_handlers.mouse_handlers
        wrappers = {}

        def wrap(handler):
            original = getattr(handler, "_cleanroom_original", handler)
            if original not in wrappers:
                @wraps(original)
                def dispatch(event):
                    if available():
                        if event.event_type == MouseEventType.SCROLL_UP:
                            move(-1)
                            return None
                        if event.event_type == MouseEventType.SCROLL_DOWN:
                            move(1)
                            return None
                    try:
                        return original(event)
                    finally:
                        # A release can land outside the pane where a drag began.
                        if event.event_type == MouseEventType.MOUSE_UP:
                            session.reading_drag = None
                dispatch._cleanroom_original = original
                wrappers[original] = dispatch
            return wrappers[original]

        for row in raster.values():
            for column, handler in list(row.items()):
                row[column] = wrap(handler)

    session.app.after_render += route_wheel
