"""Route terminal wheel/page events to the active pane without moving input focus.

The terminal's native scrollback scrollbar is outside this application's control.
This module changes only the full-screen application's content viewport.
"""
from functools import wraps
from types import SimpleNamespace

from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding.bindings.scroll import scroll_forward, scroll_backward
from prompt_toolkit.mouse_events import MouseEventType


def install_pane_scroll(session, bindings):
    def available():
        return ((session.picker is None or session.picker.get("inline", False))
                and session.input.buffer.complete_state is None)

    def target():
        if session.focus_name in session.areas:
            return session.areas[session.focus_name]
        return session.areas["agent" if session.active_input == "agent" else session._owner_page()]

    def move(direction, page=False):
        area = target()
        window = area.window
        if window.render_info is None:
            return
        if area is session.areas.get("owner") and session._archive_scroll(direction, window):
            return
        if page:
            # Use prompt_toolkit's wrapped-line-aware paging, temporarily focusing
            # only this body. Restore the editor without touching its draft.
            previous = session.app.layout.current_window
            try:
                session.app.layout.focus(area)
                event = SimpleNamespace(app=session.app)
                (scroll_forward if direction > 0 else scroll_backward)(event)
            finally:
                session.app.layout.focus(previous)
        else:
            (window._scroll_down if direction > 0 else window._scroll_up)()
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

    def route_wheel(app):
        if not available():
            return
        raster = app.renderer.mouse_handlers.mouse_handlers
        wrappers = {}

        def wrap(handler):
            # Some repaints reuse the previous screen's mouse map.
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
                    return original(event)
                dispatch._cleanroom_original = original
                wrappers[original] = dispatch
            return wrappers[original]

        for row in raster.values():
            for column, handler in list(row.items()):
                row[column] = wrap(handler)

    session.app.after_render += route_wheel
