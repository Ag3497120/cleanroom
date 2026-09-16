"""Preserve empty Enter; decode enhanced Shift+Enter as an explicit newline."""
from contextlib import contextmanager
import os

SHIFT_ENTER_SEQUENCES = ("\x1b[13;2u", "\x1b[27;2;13~")
ENTER_SEQUENCES = ("\x1b[13u", "\x1b[13;1u")


@contextmanager
def enhanced_enter(output):
    from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
    from prompt_toolkit.input.vt100_parser import _IS_PREFIX_OF_LONGER_MATCH_CACHE
    from prompt_toolkit.keys import Keys
    missing = object()
    mappings = {**dict.fromkeys(SHIFT_ENTER_SEQUENCES, Keys.ControlJ),
                **dict.fromkeys(ENTER_SEQUENCES, Keys.ControlM)}
    previous = {key: ANSI_SEQUENCES.get(key, missing) for key in mappings}
    ANSI_SEQUENCES.update(mappings)
    _IS_PREFIX_OF_LONGER_MATCH_CACHE.clear()
    enabled = False

    def enable():
        nonlocal enabled
        if not enabled and os.environ.get("VERANTYX_ENHANCED_KEYS", "1") != "0":
            # Unsupported terminals ignore these. Never guess Shift from timing.
            output.write_raw("\x1b[>1u\x1b[>4;2m")
            output.flush()
            enabled = True

    try:
        yield enable
    finally:
        if enabled:
            output.write_raw("\x1b[<u\x1b[>4;0m")
            output.flush()
        for key, old in previous.items():
            if old is missing:
                ANSI_SEQUENCES.pop(key, None)
            else:
                ANSI_SEQUENCES[key] = old
        _IS_PREFIX_OF_LONGER_MATCH_CACHE.clear()
