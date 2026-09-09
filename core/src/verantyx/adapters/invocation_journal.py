"""Local append-only markers for external calls, separate from authority events."""
from pathlib import Path
import fcntl
import os
import stat
import uuid

from .observations import read_document
from ..domain.codec import canonical, decode, digest
from ..errors import LedgerError


class InvocationJournal:
    def __init__(self, root, operation, key):
        self.directory = Path(root) / ".verantyx" / "bridges"
        self.prefix = digest({"operation": operation, "key": key})
        self.fd = None

    def __enter__(self):
        if self.directory.parent.is_symlink() or not self.directory.parent.is_dir():
            raise LedgerError("STORE_PATH")
        self.directory.mkdir(mode=0o700, exist_ok=True)
        if self.directory.is_symlink() or not self.directory.is_dir():
            raise LedgerError("STORE_PATH")
        self.fd = os.open(self.path("lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise LedgerError("STORE_PATH")
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            self.fd = None
            raise LedgerError("STORE_BUSY") from None
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise
        return self

    def __exit__(self, *args):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)

    def path(self, stage):
        return self.directory / (self.prefix + "." + stage + ".json")

    def read(self, stage):
        path = self.path(stage)
        try:
            info = path.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise LedgerError("STORE_PATH")
        return decode(read_document(path, 4 * 1024 * 1024), 4 * 1024 * 1024)

    def write(self, stage, value):
        raw = canonical(value).encode("utf-8")
        if len(raw) > 4 * 1024 * 1024:
            raise LedgerError("DOCUMENT_LIMIT")
        temporary = self.directory / (".pending-" + uuid.uuid4().hex)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, self.path(stage))
            except FileExistsError:
                raise LedgerError("STORE_INTEGRITY") from None
            temporary.unlink()
            directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)
