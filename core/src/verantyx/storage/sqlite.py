"""Append-only event batches, idempotent command receipts, and inert archives."""
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from pathlib import Path
import hashlib
import fcntl
import os
import sqlite3
import stat

from ..domain.codec import canonical, decode, digest, MAX_ARCHIVE
from ..domain.events import require, validate_event
from ..errors import LedgerError
from ..kernel.reducer import replay

DDL = [
    "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE events (
         seq INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, stream_id TEXT NOT NULL,
         revision INTEGER NOT NULL CHECK(revision > 0), event_json TEXT NOT NULL,
         UNIQUE(stream_id, revision))""",
    """CREATE TABLE commands (
         key TEXT PRIMARY KEY, input_hash TEXT NOT NULL, stream_id TEXT NOT NULL,
         first_revision INTEGER NOT NULL, last_revision INTEGER NOT NULL, command_id TEXT NOT NULL UNIQUE)""",
    """CREATE TABLE outbox (
         command_id TEXT PRIMARY KEY REFERENCES commands(command_id),
         topic TEXT NOT NULL CHECK(topic = 'run.updated'), payload TEXT NOT NULL)""",
    """CREATE TABLE archives (
         archive_id TEXT PRIMARY KEY, source_project_id TEXT NOT NULL,
         bundle TEXT NOT NULL, imported_at TEXT NOT NULL)""",
]
for table in ("metadata", "events", "commands", "outbox", "archives"):
    for operation in ("UPDATE", "DELETE"):
        DDL.append(f"""CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} ON {table}
                       BEGIN SELECT RAISE(ABORT, 'append only'); END""")


def store_path(root):
    return Path(root) / ".verantyx" / "state.db"


def _location(root):
    directory = Path(root) / ".verantyx"
    if directory.is_symlink() or not directory.is_dir():
        raise LedgerError("STORE_PATH")
    for name in ("state.db", "state.db-wal", "state.db-shm", "state.db-journal"):
        path = directory / name
        if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_nlink != 1)):
            raise LedgerError("STORE_PATH")
    return directory / "state.db"


class EventStore:
    def __init__(self, root, project_id, create=False):
        self.root, self.project_id = Path(root), project_id
        self.path = _location(root)
        self.connection = None
        self._lock_depth = 0
        self._project_snapshot = None
        self._project_snapshot_token = None
        if not self.path.exists() and not create:
            return
        if create:
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(descriptor)
            except FileExistsError:
                pass
        try:
            uri = self.path.resolve().as_uri() + ("?mode=rw" if create else "?mode=ro")
            self.connection = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5)
            self.connection.execute("PRAGMA foreign_keys=ON")
            self.connection.execute("PRAGMA busy_timeout=5000")
            if create:
                self.connection.execute("PRAGMA synchronous=FULL")
            with self._transaction(write=create):
                version = self.connection.execute("PRAGMA user_version").fetchone()[0]
                tables = self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                if version == 0 and not tables and create:
                    for statement in DDL:
                        self.connection.execute(statement)
                    self.connection.execute("INSERT INTO metadata VALUES ('project_id', ?)", (project_id,))
                    self.connection.execute("PRAGMA user_version=1")
                elif version != 1:
                    raise LedgerError("STORE_VERSION")
                row = self.connection.execute("SELECT value FROM metadata WHERE key='project_id'").fetchone()
                if row is None or row[0] != project_id:
                    raise LedgerError("STORE_PROJECT")
        except BaseException:
            self.close()
            raise

    @contextmanager
    def exclusive(self):
        if self._lock_depth:
            self._lock_depth += 1
            try:
                yield
            finally:
                self._lock_depth -= 1
            return
        lock_path = self.root / ".verantyx/commands.lock"
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
                raise LedgerError("STORE_PATH")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise LedgerError("STORE_BUSY") from None
            self._lock_depth = 1
            try:
                yield
            finally:
                self._lock_depth = 0
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    @contextmanager
    def _transaction(self, write=False):
        try:
            self.connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield
            self.connection.execute("COMMIT")
        except BaseException:
            if self.connection.in_transaction:
                self.connection.execute("ROLLBACK")
            raise

    def close(self):
        self._project_snapshot = None
        self._project_snapshot_token = None
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _read_events(self, stream_id=None, through=None):
        """Read and validate envelopes; callers also validate their stream/project bindings."""
        if self.connection is None:
            return []
        query, arguments = "SELECT event_id, stream_id, revision, event_json FROM events", []
        if stream_id is not None:
            query += " WHERE stream_id=?"
            arguments.append(stream_id)
            if through is not None:
                query += " AND revision<=?"
                arguments.append(through)
            query += " ORDER BY revision"
        else:
            query += " ORDER BY seq"
        values = []
        for event_id, stream, revision, raw in self.connection.execute(query, arguments):
            event = validate_event(decode(raw))
            require(event["project_id"] == self.project_id, "STORE_INTEGRITY")
            require((event["event_id"], event["stream_id"], event["revision"]) == (event_id, stream, revision), "STORE_INTEGRITY")
            values.append(event)
        return values

    def events(self, stream_id=None, through=None):
        values = self._read_events(stream_id, through)
        if stream_id is not None:
            replay(values)
        else:
            from ..kernel.rules import catalog
            catalog(values)
        return values

    def project_snapshot(self):
        """Return a private copy of the current validated project snapshot."""
        return self.project_snapshot_if_changed()[1]

    def project_snapshot_if_changed(self, previous_token=None):
        """Return (opaque token, private snapshot), or (token, None) if unchanged.

        Tokens are connection-local identities for display polling, not revisions,
        evidence, or authority. All database invalidation checks still run. Public
        snapshots remain private copies; the cached snapshot is never exposed.
        """
        empty = {"project_revision": 0, "events": [], "states": [], "rules": {}, "as_of": None}
        if self.connection is None:
            return None, empty
        # A caller-owned transaction might roll back without reducing total_changes.
        # Neither reuse nor retain snapshots of its potentially uncommitted writes.
        cacheable = not self.connection.in_transaction
        with (self._transaction() if cacheable else nullcontext()):
            stamp = (self.project_revision(),
                     self.connection.execute("PRAGMA data_version").fetchone()[0],
                     self.connection.total_changes,
                     self.connection.execute("PRAGMA schema_version").fetchone()[0])
            if not cacheable or self._project_snapshot is None or self._project_snapshot[0] != stamp:
                events = self._read_events()
                from ..kernel.rules import catalog
                rules = catalog(events)
                groups = {}
                for event in events:
                    groups.setdefault(event["stream_id"], []).append(event)
                snapshot = {"project_revision": stamp[0], "events": events,
                            "states": [replay(group) for group in groups.values()], "rules": rules,
                            "as_of": max((event["recorded_at"] for event in events), default=None)}
                if not cacheable:
                    return None, deepcopy(snapshot)
                self._project_snapshot = (stamp, snapshot)
                self._project_snapshot_token = object()
            if previous_token is not None and previous_token is self._project_snapshot_token:
                return previous_token, None
            return self._project_snapshot_token, deepcopy(self._project_snapshot[1])

    def runs(self):
        if self.connection is None:
            return []
        return [row[0] for row in self.connection.execute("SELECT stream_id FROM events GROUP BY stream_id ORDER BY MIN(seq)")]

    def project_revision(self):
        return 0 if self.connection is None else self.connection.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0]

    def receipt(self, key, input_hash):
        if self.connection is None:
            return None
        row = self.connection.execute(
            "SELECT input_hash,stream_id,first_revision,last_revision,command_id FROM commands WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        if row[0] != input_hash:
            raise LedgerError("IDEMPOTENCY_CONFLICT")
        events = self.events(row[1], through=row[3])
        if not events or events[-1]["revision"] != row[3] or events[-1]["command_id"] != row[4]:
            raise LedgerError("STORE_INTEGRITY")
        return {"stream_id": row[1], "first_revision": row[2], "last_revision": row[3],
                "command_id": row[4], "events": events, "duplicate": True}

    def append(self, key, input_hash, stream_id, expected_revision, events, fault=None, project_revision=None):
        if self.connection is None:
            raise LedgerError("STORE_PATH")
        require(events and len(events) <= 66)
        with self.exclusive(), self._transaction(write=True):
            existing_receipt = self.receipt(key, input_hash)
            if existing_receipt:
                return existing_receipt
            if project_revision is not None and self.project_revision() != project_revision:
                raise LedgerError("REVISION_CONFLICT", {"reason": "PROJECT_CONTEXT_CHANGED"})
            existing = self.events(stream_id)
            revision = existing[-1]["revision"] if existing else 0
            if revision != expected_revision:
                raise LedgerError("REVISION_CONFLICT", {"expected": expected_revision, "actual": revision})
            from ..kernel.rules import catalog
            catalog([*self.events(), *events])
            state = replay([*existing, *events])
            command_id = events[0]["command_id"]
            require(all(e["command_id"] == command_id and e["stream_id"] == stream_id
                        and e["project_id"] == self.project_id for e in events))
            require(events[-1]["type"] == "EvaluationRecorded")
            for event in events:
                self.connection.execute("INSERT INTO events(event_id,stream_id,revision,event_json) VALUES(?,?,?,?)",
                                        (event["event_id"], stream_id, event["revision"], canonical(event)))
            if fault:
                fault("after_events")
            self.connection.execute("INSERT INTO commands VALUES(?,?,?,?,?,?)",
                                    (key, input_hash, stream_id, revision + 1, state["revision"], command_id))
            # A durable notification, not an executable effect or a model call.
            self.connection.execute("INSERT INTO outbox VALUES(?,?,?)",
                                    (command_id, "run.updated", canonical({"stream_id": stream_id, "revision": state["revision"]})))
            if fault:
                fault("before_commit")
        if fault:
            fault("after_commit")
        return {"stream_id": stream_id, "first_revision": revision + 1, "last_revision": state["revision"],
                "command_id": command_id, "events": [*existing, *events], "duplicate": False}

    def export(self, archive_id=None):
        if archive_id:
            return self.archive(archive_id)["bundle"]
        events = self.events()
        for stream in dict.fromkeys(e["stream_id"] for e in events):
            replay([e for e in events if e["stream_id"] == stream])
        records = [canonical({"record": "header", "format": "verantyx.events.v1", "project_id": self.project_id})]
        records.extend(canonical({"record": "event", "event": event}) for event in events)
        prefix = "\n".join(records) + "\n"
        footer = {"record": "footer", "events": len(events), "sha256": hashlib.sha256(prefix.encode()).hexdigest()}
        bundle = prefix + canonical(footer) + "\n"
        if len(bundle.encode()) > MAX_ARCHIVE:
            raise LedgerError("DOCUMENT_LIMIT")
        return bundle

    def import_archive(self, raw, imported_at):
        parsed = parse_archive(raw)
        archive_id = hashlib.sha256(raw).hexdigest()
        with self._transaction(write=True):
            row = self.connection.execute("SELECT archive_id FROM archives WHERE archive_id=?", (archive_id,)).fetchone()
            if row is None:
                self.connection.execute("INSERT INTO archives VALUES(?,?,?,?)",
                                        (archive_id, parsed["project_id"], raw.decode("utf-8"), imported_at))
        return {"archive_id": archive_id, "source_project_id": parsed["project_id"], "events": len(parsed["events"]),
                "duplicate": row is not None, "trust": "ARCHIVE_ONLY", "local_runs_changed": False}

    def archives(self):
        if self.connection is None:
            return []
        return [{"archive_id": row[0], "source_project_id": row[1], "imported_at": row[2], "trust": "ARCHIVE_ONLY"}
                for row in self.connection.execute("SELECT archive_id,source_project_id,imported_at FROM archives ORDER BY rowid")]

    def archive(self, archive_id):
        row = None if self.connection is None else self.connection.execute(
            "SELECT bundle FROM archives WHERE archive_id=?", (archive_id,)).fetchone()
        if row is None:
            raise LedgerError("RUN_NOT_FOUND")
        raw = row[0].encode("utf-8")
        require(hashlib.sha256(raw).hexdigest() == archive_id, "STORE_INTEGRITY")
        return {**parse_archive(raw), "bundle": row[0]}


def parse_archive(raw):
    if len(raw) > MAX_ARCHIVE:
        raise LedgerError("DOCUMENT_LIMIT")
    lines = raw.splitlines(keepends=True)
    require(len(lines) >= 2, "ARCHIVE_INVALID")
    header, footer = decode(lines[0]), decode(lines[-1])
    require(type(header) is dict and set(header) == {"record", "format", "project_id"}, "ARCHIVE_INVALID")
    from ..domain.events import uuid_value
    uuid_value(header["project_id"])
    require(header["record"] == "header" and header["format"] == "verantyx.events.v1", "ARCHIVE_INVALID")
    require(type(footer) is dict and set(footer) == {"record", "events", "sha256"}, "ARCHIVE_INVALID")
    require(footer["record"] == "footer" and type(footer["events"]) is int, "ARCHIVE_INVALID")
    require(footer["events"] == len(lines) - 2, "ARCHIVE_INVALID")
    require(hashlib.sha256(b"".join(lines[:-1])).hexdigest() == footer["sha256"], "ARCHIVE_INVALID")
    events, ids, streams = [], set(), {}
    for line in lines[1:-1]:
        record = decode(line)
        require(type(record) is dict and set(record) == {"record", "event"} and record["record"] == "event", "ARCHIVE_INVALID")
        event = validate_event(record["event"])
        require(event["project_id"] == header["project_id"] and event["event_id"] not in ids, "ARCHIVE_INVALID")
        ids.add(event["event_id"])
        events.append(event)
        streams.setdefault(event["stream_id"], []).append(event)
    for stream in streams.values():
        replay(stream)
        require(stream[-1]["type"] == "EvaluationRecorded", "ARCHIVE_INVALID")
    from ..kernel.rules import catalog
    catalog(events)
    return {"project_id": header["project_id"], "events": events}
