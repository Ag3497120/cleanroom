"""Append-only, hash chained operational logs; no proposal authority is imported.

These logs have their own revisions. The project event ledger is unchanged.
Locks coordinate cooperating local commands, not a hostile OS account.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import fcntl
import os
import sqlite3
import stat

from .domain.codec import canonical, decode, digest
from .domain.events import require, timestamp
from .errors import LedgerError

_HELD = ContextVar("verantyx_security_locks", default=())


def directory(root):
    target = Path(root) / ".verantyx"
    require(target.is_dir() and not target.is_symlink(), "STORE_PATH")
    return target


@contextmanager
def exclusive(root, name):
    path = directory(root) / (name + ".lock")
    identity = str(path.resolve())
    if identity in _HELD.get():
        yield
        return
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    token = None
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "STORE_PATH")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LedgerError("STORE_BUSY") from None
        token = _HELD.set((*_HELD.get(), identity))
        yield
    finally:
        if token is not None:
            _HELD.reset(token)
        os.close(fd)


class Journal:
    def __init__(self, root, name, project_id):
        require(name in ("authority", "writers"), "ARGUMENTS")
        self.root, self.name, self.project_id = Path(root), name, project_id
        self.path = directory(root) / (name + ".db")

    def _open(self, create=False):
        for suffix in ("", "-wal", "-shm", "-journal"):
            path = Path(str(self.path) + suffix)
            if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_nlink != 1)):
                raise LedgerError("STORE_PATH")
        if not self.path.exists() and not create:
            return None
        if create:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                os.close(fd)
            except FileExistsError:
                pass
        conn = sqlite3.connect(self.path.resolve().as_uri() + ("?mode=rw" if create else "?mode=ro"),
                               uri=True, isolation_level=None, timeout=5)
        try:
            if create:
                conn.execute("PRAGMA synchronous=FULL")
                conn.execute("BEGIN IMMEDIATE")
                if not conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                    conn.execute("CREATE TABLE entries (seq INTEGER PRIMARY KEY, body TEXT NOT NULL)")
                    conn.execute("CREATE TRIGGER entries_no_update BEFORE UPDATE ON entries BEGIN SELECT RAISE(ABORT,'append only'); END")
                    conn.execute("CREATE TRIGGER entries_no_delete BEFORE DELETE ON entries BEGIN SELECT RAISE(ABORT,'append only'); END")
                    conn.execute("PRAGMA user_version=1")
                conn.execute("COMMIT")
            require(conn.execute("PRAGMA user_version").fetchone()[0] == 1, "STORE_VERSION")
            return conn
        except BaseException:
            conn.close()
            raise

    def read(self):
        conn = self._open()
        if conn is None:
            return []
        try:
            values, previous = [], "0" * 64
            for seq, raw in conn.execute("SELECT seq,body FROM entries ORDER BY seq"):
                value = decode(raw)
                require(type(value) is dict and set(value) == {"format", "project_id", "revision", "previous_hash",
                        "recorded_at", "kind", "payload", "hash"}, "SECURITY_INTEGRITY")
                require(value["format"] == "verantyx." + self.name + ".v1" and value["project_id"] == self.project_id
                        and type(value["revision"]) is int and value["revision"] == seq == len(values) + 1
                        and value["previous_hash"] == previous, "SECURITY_INTEGRITY")
                timestamp(value["recorded_at"])
                require(digest({k: v for k, v in value.items() if k != "hash"}) == value["hash"], "SECURITY_INTEGRITY")
                previous = value["hash"]
                values.append(value)
            return values
        finally:
            conn.close()

    def append(self, kind, payload, at, expected_revision):
        with exclusive(self.root, self.name):
            values = self.read()
            require(len(values) == expected_revision, "REVISION_CONFLICT")
            value = {"format": "verantyx." + self.name + ".v1", "project_id": self.project_id,
                     "revision": len(values) + 1, "previous_hash": values[-1]["hash"] if values else "0" * 64,
                     "recorded_at": at, "kind": kind, "payload": payload}
            timestamp(at)
            value["hash"] = digest(value)
            conn = self._open(create=True)
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("INSERT INTO entries VALUES (?,?)", (value["revision"], canonical(value)))
                conn.execute("COMMIT")
            finally:
                conn.close()
            return value
