"""Opt-in-size-advice, real key controls, and entirely simulated notebook content."""
import asyncio
import os
from pathlib import Path
import sys

from .interaction_text import tr, help_text


def offer(root, configuration, *, force=False):
    marker = Path(root) / ".verantyx" / "interaction-tour-v3"
    if not force and marker.is_file():
        return
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return
    lang = configuration["ui"]["locale"]
    from .terminal_ui import capable_terminal
    if not capable_terminal():
        print(help_text(lang))
        return
    from prompt_toolkit.shortcuts import prompt
    from prompt_toolkit.key_binding import KeyBindings
    bindings = KeyBindings()

    @bindings.add("escape")
    def skip(event):
        event.app.exit(result="skip")

    print("\n" + tr("size", lang))
    print(tr("demo", lang))
    launch_real = False
    try:
        selected = prompt("Enter / Esc > ", key_bindings=bindings)
        if selected != "skip":
            from .cleanroom_tui import Cleanroom
            demo = Cleanroom(root, configuration, practice=True)
            asyncio.run(demo.run())
            launch_real = demo.tour_launch_real
    except (EOFError, KeyboardInterrupt):
        pass
    if not force and not marker.parent.is_symlink():
        marker.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as stream:
                stream.write("offered\n")
        except FileExistsError:
            pass
    return launch_real
