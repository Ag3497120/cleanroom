"""Ephemeral UI observations, outside command inputs, receipts and authority."""
from contextlib import contextmanager
from contextvars import ContextVar


_observer = ContextVar("verantyx_progress_observer", default=None)
_model_observer = ContextVar("verantyx_model_observer", default=None)


@contextmanager
def observe(callback, model_callback=None):
    token = _observer.set(callback)
    model_token = _model_observer.set(model_callback)
    try:
        yield
    finally:
        _observer.reset(token)
        _model_observer.reset(model_token)


def report(stage):
    callback = _observer.get()
    if callback is not None:
        try:
            callback(stage)
        except Exception:
            # A broken display must not retry, authorize or fail a command.
            pass


def model_event(event):
    callback = _model_observer.get()
    if callback is not None:
        try:
            callback(event)
        except Exception:
            pass
