"""Session-only, per-field input recall. Settings and // chats never enter it."""
from collections import defaultdict


class InputRecall:
    def __init__(self):
        self.entries = defaultdict(list)
        self.positions = {}
        self.drafts = {}
        self.navigating = False

    def record(self, key, text):
        text = text.strip()
        if not text or key == "agent" and text.startswith("/"):
            return
        rows = self.entries[key]
        if not rows or rows[-1] != text:
            rows.append(text)
            del rows[:-100]
        self.positions.pop(key, None)

    def edited(self, key):
        if not self.navigating:
            self.positions.pop(key, None)

    def move(self, field, key, direction):
        rows = self.entries[key]
        if not rows:
            return False
        position = self.positions.get(key)
        if position is None:
            if direction > 0:
                return False
            self.drafts[key] = field.text
            position = len(rows)
        position = max(0, min(len(rows), position + direction))
        self.positions[key] = position
        text = self.drafts.get(key, "") if position == len(rows) else rows[position]
        from prompt_toolkit.document import Document
        self.navigating = True
        try:
            field.buffer.set_document(Document(text, len(text)))
        finally:
            self.navigating = False
        return True
