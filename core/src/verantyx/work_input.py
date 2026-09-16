"""Session-local steering inbox. Only the work gateway records human speech.

No extra writer, process interruption, new file scope, or execution authority.
"""
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from threading import Lock
import uuid

CURRENT = ContextVar("cleanroom_work_input", default=None)


@contextmanager
def bind(inbox):
    token = CURRENT.set(inbox)
    try:
        yield
    finally:
        CURRENT.reset(token)


class WorkInput:
    def __init__(self, on_started=None, on_question=None):
        self._lock = Lock()
        self._pending = deque()
        self._questions = deque()
        self._question_count = 0
        self.on_question = on_question
        self._closed = False
        self._count = 0
        self._characters = 0
        self.on_started = on_started
        self._edit_grant = ""

    def started(self, run_id):
        if self.on_started is not None:
            self.on_started(run_id)

    def edit_grant(self):
        with self._lock:
            return self._edit_grant

    def set_edit_grant(self, identity):
        with self._lock:
            self._edit_grant = identity

    def submit(self, text, user_text, identity=None):
        if not text.strip() or len(text) > 16000 or not user_text.strip():
            return None
        with self._lock:
            if self._closed or self._count >= 16 or self._characters + len(text) > 120000:
                return None
            row = {"id": identity or uuid.uuid4().hex, "text": text, "user_text": user_text}
            self._pending.append(row)
            self._count += 1
            self._characters += len(text)
            return deepcopy(row)

    def peek(self):
        with self._lock:
            return deepcopy(self._pending[0]) if self._pending else None

    def recorded(self, identity):
        with self._lock:
            if self._pending and self._pending[0]["id"] == identity:
                self._pending.popleft()

    def seal_if_empty(self):
        """Atomically end acceptance; a racing submission gets another boundary."""
        with self._lock:
            if self._pending or self._questions:
                return False
            self._closed = True
            return True

    def close(self):
        """Return unsent inputs, never silently resend recorded/uncertain ones."""
        with self._lock:
            self._closed = True
            rows = list(self._pending)
            self._pending.clear()
            return rows

    def submit_question(self, learning_id, question=""):
        with self._lock:
            if self._closed or self._question_count >= 4:
                return None
            row = {"id": uuid.uuid4().hex, "learning_id": learning_id, "question": question}
            self._questions.append(row)
            self._question_count += 1
            return deepcopy(row)

    def next_question(self):
        with self._lock:
            return deepcopy(self._questions.popleft()) if self._questions else None

    def question_answered(self, row):
        if self.on_question is not None:
            self.on_question(deepcopy(row))

    def pending_questions(self):
        with self._lock:
            rows = list(self._questions)
            self._questions.clear()
            return rows
