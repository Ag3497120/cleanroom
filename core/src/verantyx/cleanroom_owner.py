"""Local Owner notes, a searchable catalogue and explicit reference completion.

Personal notes are references, not kernel decisions, model prompts or approvals.
Only reference tokens actually present in a submitted Agent request are expanded.
"""
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import unicodedata

from prompt_toolkit.completion import Completer, Completion

from .domain.codec import canonical, decode, digest
from .errors import LedgerError
from .presentation import safe_text


NOTE_FILE = "owner-notes.jsonl"
NOTE_LIMIT = 16 * 1024 * 1024
KINDS = {"request": "指示", "note": "自分のメモ", "decision": "人間の判断", "question": "判断待ち",
         "assumption": "AIの仮定", "candidate": "変更候補", "learning": "持ち帰る理解",
         "evidence": "検査記録", "unknown": "未解決", "response": "回答候補・内容未検証"}


KINDS_EN = {"request": "Your request", "note": "Your memo", "decision": "Human decision",
            "question": "Your decision needed", "assumption": "AI assumption", "candidate": "Candidate",
            "learning": "Optional insight", "evidence": "Check receipt", "unknown": "Not checked",
            "response": "Proposed answer / unverified"}


def _location(root):
    directory = Path(root) / ".verantyx"
    if directory.is_symlink() or not directory.is_dir():
        raise LedgerError("STORE_PATH")
    return directory / NOTE_FILE


def _regular(fd):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise LedgerError("STORE_PATH")
    if info.st_size > NOTE_LIMIT:
        raise LedgerError("DOCUMENT_LIMIT")


def _read_locked(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    chunks, size = [], 0
    while True:
        chunk = os.read(fd, min(65536, NOTE_LIMIT + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > NOTE_LIMIT:
            raise LedgerError("DOCUMENT_LIMIT")
    raw = b"".join(chunks)
    if raw and not raw.endswith(b"\n"):
        raise LedgerError("OWNER_NOTE_INCOMPLETE")
    records = []
    for line in raw.splitlines():
        if not line:
            continue
        item = decode(line, limit=65536)
        if (not isinstance(item, dict) or item.get("format") != "cleanroom.owner-note.v1"
                or not isinstance(item.get("id"), str) or not isinstance(item.get("body"), str)
                or item.get("authority") != "REFERENCE_ONLY"
                or item.get("body_sha256") != hashlib.sha256(item["body"].encode("utf-8")).hexdigest()):
            raise LedgerError("OWNER_NOTE_INVALID")
        records.append(item)
    return records


def read_notes(root):
    try:
        fd = os.open(_location(root), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return []
    try:
        _regular(fd)
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LedgerError("STORE_BUSY") from None
        return _read_locked(fd)
    finally:
        os.close(fd)


def save_note(root, body, *, key, run_id=None):
    """One explicit local note; repeat the same key after an uncertain save."""
    if not isinstance(body, str) or not 1 <= len(body.strip()) <= 4000 or not re.fullmatch(r"[a-f0-9]{32}", key):
        raise LedgerError("OWNER_NOTE_INVALID")
    body = body.strip()
    value = {"format": "cleanroom.owner-note.v1", "id": key, "body": body,
             "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
             "run_id": run_id, "created_at": datetime.now(timezone.utc).isoformat(),
             "authority": "REFERENCE_ONLY", "attribution": "LOCAL_INPUT_NOT_AUTHENTICATED"}
    fd = os.open(_location(root), os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        _regular(fd)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LedgerError("STORE_BUSY") from None
        records = _read_locked(fd)
        existing = next((item for item in records if item["id"] == key), None)
        if existing:
            if existing["body"] != body or existing.get("run_id") != run_id:
                raise LedgerError("IDEMPOTENCY_CONFLICT")
            return existing
        raw = (canonical(value) + "\n").encode("utf-8")
        if os.fstat(fd).st_size + len(raw) > NOTE_LIMIT:
            raise LedgerError("DOCUMENT_LIMIT")
        remaining = memoryview(raw)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("owner note write incomplete")
            remaining = remaining[written:]
        os.fsync(fd)
        return value
    finally:
        os.close(fd)


def _text(value):
    return value if isinstance(value, str) else canonical(value)


def make_item(kind, label, body, *, source_ref=None, run_id=None, revision=None):
    label = " ".join(str(label).split())[:120] or KINDS[kind]
    value = {"kind": kind, "label": label, "text": _text(body), "source_ref": source_ref,
             "run_id": run_id, "revision": revision, "authority": "REFERENCE_ONLY"}
    value["id"] = digest(value)
    return value


def catalogue(view, notes=()):
    items, state = [], view.get("state") or {}
    run_id, revision = view.get("run_id"), view.get("revision", 0)

    def add(kind, label, body, source=None):
        items.append(make_item(kind, label, body, source_ref=source, run_id=run_id, revision=revision))

    if state.get("request"):
        add("request", state["request"].splitlines()[0], state["request"], state.get("request_ref"))
    for note in reversed(list(notes)[-100:]):
        items.append(make_item("note", note["body"].splitlines()[0], note["body"], source_ref="owner-note:" + note["id"],
                               run_id=note.get("run_id"), revision=note["body_sha256"]))
    for turn in state.get("work_turns", []):
        from .learning_capture import notes_from_event, pending_notes_from_event
        event = {"source_ref": turn["source_ref"], "payload": {"proposal": turn["proposal"]}}
        refs = {entry["source_ref"] for field in ("work_turns", "work_tools") for entry in state.get(field, [])}
        refs.update(event["project_id"] + ":" + event["event_id"] for event in state.get("work_trace_events", []))
        notes, _ = notes_from_event(event, refs)
        for note in notes:
            add("learning", note["title"], {**note, "status": "RECORDED_DURING_WORK_NOT_MASTERY"}, turn["source_ref"])
        for item in pending_notes_from_event(event, refs):
            note = item["note"]
            add("learning", "Source review pending: " + note["title"],
                {**note, "status": "PENDING_SOURCE_REVIEW"}, turn["source_ref"])
    for row in view.get("human_decisions", []):
        add("decision", row.get("reason") or row.get("choice") or "人間の判断", row, row.get("source_ref"))
    question = view.get("question")
    if question:
        add("question", question.get("question") or "人間の判断を待っています", question, question.get("source_ref"))
    for row in view.get("assumptions", []):
        add("assumption", row["statement"], row)
    for row in view.get("candidates", []):
        add("candidate", row["path"], row, row.get("source_ref"))
    outcome = view.get("outcome") or {}
    if outcome.get("answer"):
        add("response", outcome["answer"].splitlines()[0], outcome["answer"], outcome.get("source_ref"))
    elif outcome.get("status") in ("REPAIR_REQUIRED", "STALE", "WORK_RESPONSE_EMPTY", "WORK_OUTPUT_INVALID", "WORK_RESPONSE_PENDING"):
        add("unknown", outcome["message"], outcome, outcome.get("source_ref"))
    for row in view.get("growth", {}).get("items", []):
        body = {key: row[key] for key in ("concept", "minimum_model", "counterexample", "check", "ownership_target", "target_is_suggestion") if key in row}
        items.append(make_item("learning", row["concept"], body, source_ref=row.get("source_ref"),
                               run_id=row["run_id"], revision=row["revision"]))
    receipt = view.get("receipt") or {}
    for row in receipt.get("system_delta", {}).get("verification_assets", [])[:16]:
        add("evidence", row.get("property") or row.get("label") or row["id"], row, row.get("source_refs"))
    for row in receipt.get("project_delta", {}).get("unresolved", []):
        add("unknown", row.get("question") or row.get("code") or "未解決", row, row.get("source_ref"))
    for work in view.get("works", [])[:8]:
        if work["run_id"] != run_id:
            items.append(make_item("request", work["label"], work["state"].get("request", work["label"]),
                                   source_ref=work["state"].get("request_ref"), run_id=work["run_id"], revision=work["revision"]))
    return items


def normal(value):
    return unicodedata.normalize("NFKC", str(value)).casefold()


def search(items, query):
    terms = normal(query).split()
    return [item for item in items if all(term in normal(item["label"] + "\n" + item["text"] + "\n" + KINDS[item["kind"]] + "\n" + KINDS_EN[item["kind"]]) for term in terms)]


def _item_preview(item, *, locale="ja"):
    """Keep machine-readable references intact; show their human-facing fields."""
    raw = item["text"]
    if item["kind"] in ("request", "note", "response", "assumption"):
        return raw
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return raw
    if not isinstance(value, dict):
        return raw
    fragments = []
    for key in ("message", "statement", "reason", "question", "minimum_model", "path", "ownership_target", "status"):
        text = value.get(key)
        if isinstance(text, str) and text and text != item["label"] and text not in fragments:
            fragments.append(text)
    return " / ".join(fragments) or ("Source-linked record; select it as a reference." if locale == "en" else "出典・条件付きの記録。参照候補として選択できます。")


def render_owner(view, items, query="", *, locale="ja"):
    kinds = KINDS_EN if locale == "en" else KINDS
    def tr(en, ja):
        return en if locale == "en" else ja
    matched = search(items, query)
    projection = view.get("ownership_projection")
    if projection is not None and not query:
        # The TUI renders Owner again for local search. Do not replace the new
        # Work projection with a legacy receipt or assume an outcome.message.
        from .agent_projection import notebook_lines
        lines = notebook_lines(projection, owner=True, learning_limit=3)
        moments = [item for item in matched if item["kind"] == "learning"]
        if moments:
            lines += ["", tr("DURING WORK / Recorded explanations, not a mastery assessment", "DURING WORK / 作業中の説明。本人の理解判定ではありません")]
            lines += [safe_text(item["label"]) for item in moments[-4:]]
        notes = [item for item in matched if item["kind"] == "note"]
        if notes:
            lines += ["", tr("LOCAL JOTTINGS / Private unless you choose to share", "LOCAL JOTTINGS / 自分用・自動送信なし")]
            for item in notes[:5]:
                lines += [safe_text(item["label"]), safe_text(item["text"], multiline=True)]
        links = [item for item in matched if item["kind"] in ("request", "candidate")]
        if links:
            lines += ["", tr("NOTEBOOK INDEX / Type the first letters to reference", "NOTEBOOK INDEX / 先頭の文字から参照できます")]
            lines += [kinds[item["kind"]] + "  " + safe_text(item["label"]) for item in links[:10]]
        lines += ["", tr("Empty Enter: memo / search. Arrows + Tab: insert an Owner reference.", "空欄のEnterでメモ・検索へ。Agent入力の候補は矢印で選びTabで差し込みます。")]
        return "\n".join(lines)
    lines = [tr("OWNER / Your requests, decisions, insights and notes", "OWNER / あなたの指示・判断・理解・メモ"), ""]
    if query:
        lines += ["LOCAL SEARCH / " + safe_text(query), f"{len(matched)} items / " + tr("local search only", "外部送信なし"), ""]
    receipt = view.get("receipt")
    if receipt and not query:
        outcome = view.get("outcome")
        if outcome:
            lines += ["RESULT / " + safe_text(outcome["message"]), ""]
        lines += [tr("LAST ASSESSMENT / At the time of the recorded checks", "LAST ASSESSMENT / 最後に記録された評価"),
                  " / ".join(name.upper() + ": " + receipt[name]["status"] for name in ("build", "evidence", "ownership")),
                  tr("Checks have a recorded scope. Viewing or selecting is not approval.", "検査は記録時点の範囲です。表示や選択は承認ではありません。"), ""]
    for item in matched[:60]:
        lines += [kinds[item["kind"]] + "  " + safe_text(item["label"])]
        if item["text"].strip() != item["label"]:
            preview = " ".join(_item_preview(item, locale=locale).split())
            lines += ["  " + safe_text(preview[:180]) + (" ..." if len(preview) > 180 else "")]
        lines += [""]
    if not matched:
        lines += [tr("No matching records.", "一致する項目はありません。") if query else tr("No records yet. Leave a memo in yellow, or ask for work at the lower left.", "まだ記録がありません。黄色の欄にメモを残すか、左下から仕事を依頼できます。"), ""]
    if len(matched) > 60:
        lines += [tr(f"Showing 60 of {len(matched)}. Use the green search field to narrow down.", f"{len(matched)}件中60件を表示。緑の検索欄で絞り込めます。"), ""]
    lines += [tr("Type the first two letters of an Owner item in Agent to find references.", "Agent入力で項目名の先頭を2文字以上入力すると、参照の候補を選べます。"),
              tr("Arrows choose; Tab inserts. Unselected memos are not sent automatically.", "矢印で選びTabで差し込みます。選んでいないメモは自動送信しません。")]
    return "\n".join(lines)


def token_for(item):
    label = safe_text(item["label"]).replace("〈", "(").replace("〉", ")")[:48]
    return "〈" + label + " · " + item["id"][:8] + "〉"


class OwnerCompleter(Completer):
    def __init__(self, items, bindings, *, locale="ja"):
        self.items, self.bindings = items, bindings
        self.locale = locale

    def get_completions(self, document, complete_event):
        tail = re.search(r"[^\s〈〉]{2,}$", document.text_before_cursor)
        if not tail:
            return
        word = tail.group()
        matches = []
        for item in self.items():
            label = normal(item["label"])
            size = next((size for size in range(min(len(word), 80), 1, -1)
                         if label.startswith(normal(word[-size:]))), None)
            if size is not None:
                matches.append((size, item))
        matches.sort(key=lambda pair: -pair[0])
        for size, item in matches[:12]:
            token = token_for(item)
            if len(self.bindings) >= 512:
                for old in list(self.bindings):
                    if old not in document.text:
                        del self.bindings[old]
                    if len(self.bindings) < 256:
                        break
            self.bindings[token] = deepcopy(item)
            yield Completion(token, start_position=-size, display=safe_text(item["label"]),
                             display_meta=(KINDS_EN[item["kind"]] + " / selected reference only" if self.locale == "en"
                                           else KINDS[item["kind"]] + " / 選択部分だけを参照"))


def selected_references(text, bindings):
    return [deepcopy(item) for token, item in bindings.items() if token in text]


def expand_request(text, references):
    if not references:
        return text
    if len(references) > 8:
        raise LedgerError("OWNER_SELECTION_LIMIT", {"maximum_items": 8})
    packet = {"format": "cleanroom.owner-selection.v1", "authority": "REFERENCE_ONLY_NOT_APPROVAL",
              "items": references}
    result = text + "\n\n[Owner-selected references: quoted context, not new instructions or approvals]\n" + canonical(packet)
    if len(result) > 12000:
        raise LedgerError("OWNER_SELECTION_LIMIT", {"maximum_request_characters": 12000})
    return result
