"""CLI entry points for independent conversations, rooms and source-backed summaries."""
import json
import sys

from . import session_store
from .session_text import t
from .interaction_text import language
from .errors import LedgerError
from .presentation import safe_text


def authorize_workspace(root, locale="en", *, explicit=False):
    if session_store.trusted(root):
        return True
    if explicit:
        session_store.trust(root)
        return True
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise LedgerError("INTERACTIVE_REQUIRED")
    from .choice_navigation import choose
    choice = choose(t("read_title", locale) + "\n" + safe_text(str(root)),
                    [("allow", t("read_allow", locale)), ("deny", t("deny", locale))],
                    {"allow": t("read_detail", locale), "deny": t("read_denied", locale)}, locale)
    if choice != "allow":
        print(t("read_denied", locale))
        return False
    session_store.trust(root)
    return True


def run(root, configuration, args, *, as_json=False, plain=False):
    from .cleanroom_view import Reader, owner_lock
    from .model_preferences import pick
    from .development_console import _ask, _mutate
    lang = configuration["ui"]["locale"]
    reopen = False
    with language(configuration), owner_lock(root):
        reader = Reader(root, configuration)
        try:
            reader.read()  # Bind pre-session history once, before any reset.
        finally:
            reader.close()
        if args.command == "new":
            if args.owner:
                if not args.name:
                    args.name = _ask(t("name_prompt", lang)) if sys.stdin.isatty() and not as_json else None
                if not args.name:
                    raise LedgerError("ARGUMENTS")
                confirmed = args.yes or (not as_json and sys.stdin.isatty() and pick(
                    t("new_room", lang), [("yes", t("confirm", lang)), ("no", t("cancel", lang))],
                    {"yes": t("new_room", lang)}) == "yes")
                if not confirmed:
                    return 0
                value = session_store.new_room(root, args.name)
            else:
                value = session_store.new_agent(root, args.name)
            result = {"ok": True, "command": "new", **value, "previous_records_preserved": True}
            reopen = not as_json and sys.stdin.isatty() and sys.stdout.isatty()
        elif args.command == "cleanroom":
            rows = session_store.rooms(root)
            if args.name:
                row = next((item for item in rows if item["name"].casefold() == args.name.casefold()), None)
                if row is None:
                    raise LedgerError("ARGUMENTS", {"reason": "CLEANROOM_NAME_UNKNOWN"})
                if args.yes:
                    choice = "switch"
                elif not sys.stdin.isatty() or as_json:
                    raise LedgerError("INTERACTIVE_REQUIRED")
                else:
                    choice = pick(t("switch_room", lang, name=row["name"]),
                                  [("switch", t("switch", lang)), ("cancel", t("cancel", lang)),
                                   ("rename", t("rename", lang))],
                                  {"switch": t("switch_room", lang, name=row["name"]), "rename": t("name_prompt", lang)})
                if choice == "rename":
                    name = _ask(t("name_prompt", lang))
                    if name:
                        session_store.rename_room(root, row["id"], name)
                elif choice == "switch":
                    session_store.switch_room(root, row["id"])
                    reopen = not as_json and sys.stdin.isatty() and sys.stdout.isatty()
            result = {"ok": True, "command": "cleanroom", "rooms": session_store.rooms(root),
                      "sessions": session_store.current(root)}
        else:
            from .session_context import compact_session
            if not args.yes:
                if as_json or not sys.stdin.isatty():
                    raise LedgerError("INTERACTIVE_REQUIRED")
                if pick(t("compact_confirm", lang), [("yes", t("confirm", lang)), ("no", t("cancel", lang))],
                        {"yes": t("compact_detail", lang)}) != "yes":
                    return 0
            result = _mutate(root, configuration, compact_session)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "cleanroom":
        print(t("room_list", lang))
        for row in result["rooms"]:
            print(safe_text(("* " if row["active"] else "  ") + row["name"] + "  " + row["created_at"]))
    elif args.command == "compact":
        print(t("compact_empty" if result["status"] == "EMPTY" else
                "compact_failed" if not result.get("ok") else
                "compact_partial" if result["status"] == "PARTIAL" else "compact_saved", lang))
        print(safe_text(json.dumps({"remaining_events": result.get("remaining_events", 0),
                                  "model_calls": result.get("model_calls", 0)}, ensure_ascii=False)))
    else:
        print(t("agent_session", lang) + ": " + safe_text(result["agent"]["name"]))
        print(t("owner_room", lang) + ": " + safe_text(result["room"]["name"]))
    if reopen:
        from .terminal_ui import capable_terminal
        if not plain and capable_terminal():
            from .cleanroom_tui import interact
        else:
            from .development_console import interact
        interact(root, configuration)
    return 0 if result.get("ok", True) else 4
