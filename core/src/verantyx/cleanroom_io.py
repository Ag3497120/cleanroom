"""Thread-local presentation hooks; these never authorize a domain operation."""
import builtins
from contextlib import contextmanager
from contextvars import ContextVar


current = ContextVar("cleanroom_owner_io", default=None)


@contextmanager
def bind(session):
    token = current.set(session)
    try:
        yield
    finally:
        current.reset(token)


def console_print(*values, sep=" ", end="\n", file=None, flush=False):
    session = current.get()
    if session is None or file is not None:
        return builtins.print(*values, sep=sep, end=end, file=file, flush=flush)
    session.notice(sep.join(str(value) for value in values) + end)
