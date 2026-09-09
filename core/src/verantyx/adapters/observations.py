"""Explicit, bounded file observations. Model text never invokes this module."""
from pathlib import Path, PurePosixPath
import hashlib
import os
import stat

from ..domain.codec import MAX_DOCUMENT
from ..errors import LedgerError

MAX_OBSERVATION_BYTES = 16 * 1024 * 1024


def normalize_path(value):
    if type(value) is not str or not value or len(value) > 1024:
        raise LedgerError("PATH_SCOPE")
    path = PurePosixPath(value)
    if path.is_absolute() or "\\" in value or "\x00" in value:
        raise LedgerError("PATH_SCOPE")
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise LedgerError("PATH_SCOPE")
    if path.parts[0] in (".verantyx", ".git"):
        raise LedgerError("PATH_SCOPE")
    return path.as_posix()


def _open_under(root, relative):
    """Walk using directory descriptors; never follow a symlink."""
    parts = normalize_path(relative).split("/")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        return os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)


def read_document(path, limit=MAX_DOCUMENT):
    """An explicitly supplied proposal/archive path may be outside the project."""
    fd = os.open(Path(path).expanduser(), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise LedgerError("DOCUMENT_INVALID")
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise LedgerError("DOCUMENT_LIMIT")
    return raw


def observe(root, relative, observed_at, expires_at):
    relative = normalize_path(relative)
    result = {"observer": "file.sha256.v1", "path": relative, "status": "UNREADABLE",
              "sha256": None, "size": None, "reason": None,
              "observed_at": observed_at, "expires_at": expires_at}
    try:
        fd = _open_under(root, relative)
        with os.fdopen(fd, "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                result["reason"] = "NOT_REGULAR"
                return result
            if before.st_size > MAX_OBSERVATION_BYTES:
                result["reason"] = "BYTE_LIMIT"
                return result
            checksum = hashlib.sha256()
            size = 0
            while chunk := handle.read(min(65536, MAX_OBSERVATION_BYTES + 1 - size)):
                size += len(chunk)
                if size > MAX_OBSERVATION_BYTES:
                    result["reason"] = "BYTE_LIMIT"
                    return result
                checksum.update(chunk)
            after = os.fstat(handle.fileno())
            fingerprint = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            # Detect ordinary concurrent edits and path replacement during reading.
            try:
                current_fd = _open_under(root, relative)
                try:
                    current = os.fstat(current_fd)
                finally:
                    os.close(current_fd)
            except OSError:
                current = None
            if current is None or fingerprint(before) != fingerprint(after) or fingerprint(after) != fingerprint(current):
                result.update(status="CHANGED", reason="CHANGED_DURING_READ")
                return result
        result.update(status="OBSERVED", sha256=checksum.hexdigest(), size=size)
    except FileNotFoundError:
        result.update(status="MISSING", reason="NOT_FOUND")
    except OSError:
        result["reason"] = "READ_FAILED"
    return result
