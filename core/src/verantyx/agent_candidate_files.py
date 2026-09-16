"""Bounded artifact reads and a coherent isolated workspace, not source adoption."""
from pathlib import Path
import hashlib
import os
import stat

from .adapters.observations import _open_under, normalize_path
from .authority import require_current_approval_valid
from .errors import LedgerError

MAX_ASSET_BYTES = 8 * 1024 * 1024
MAX_BUNDLE_BYTES = 16 * 1024 * 1024


def _open_candidate(root, relative):
    parts = relative.split("/")
    if (parts[:2] != [".verantyx", "work-candidates"] or len(parts) < 5
            or any(part in ("", ".", "..") or "\\" in part or "\x00" in part for part in parts)):
        raise LedgerError("PATH_SCOPE")
    parent = os.open(Path(root).resolve(), os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        return os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)


def read_bytes(root, relative, *, limit=MAX_ASSET_BYTES, expected=None, internal=False):
    fd = _open_candidate(root, relative) if internal else _open_under(root, relative)
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise LedgerError("DOCUMENT_LIMIT")
        raw = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
    if len(raw) > limit or (before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_ino, after.st_size, after.st_mtime_ns):
        raise LedgerError("WORK_INPUT_CHANGED")
    if expected and (len(raw) != expected["size"] or
                     hashlib.sha256(raw).hexdigest() != expected["sha256"]):
        raise LedgerError("WORK_CANDIDATE_CHANGED")
    return raw


def asset_manifest(root, paths):
    rows = []
    for path in paths:
        raw = read_bytes(root, path)
        rows.append({"path": path, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    if len(rows) > 32 or sum(row["size"] for row in rows) > MAX_BUNDLE_BYTES:
        raise LedgerError("DOCUMENT_LIMIT")
    return rows


def materialize(root, run_id, artifacts):
    """Copy exact registered versions, including inherited files, into one tree.

    Never execute code, download dependencies, overwrite the source project or
    turn this packaging receipt into test evidence. Existing differing copies
    fail closed; immutable originals remain under work-candidates.
    """
    from .agent_runtime import _relative
    if not artifacts:
        return ""
    if not run_id.startswith("work-") or normalize_path(run_id) != run_id or "/" in run_id:
        raise LedgerError("PATH_SCOPE")
    if len(artifacts) > 32 or sum(row["size"] for row in artifacts) > MAX_BUNDLE_BYTES:
        raise LedgerError("DOCUMENT_LIMIT")
    files = []
    for row in artifacts:
        path = _relative(root, row["path"])
        if path != row["path"] or not row["storage_path"].startswith(".verantyx/work-candidates/"):
            raise LedgerError("PATH_SCOPE")
        files.append((path, read_bytes(root, row["storage_path"], expected=row, internal=True)))
    require_current_approval_valid()
    base = ".verantyx/workspaces/" + run_id
    for path, raw in files:
        parts = [*base.split("/"), *Path(path).parts]
        parent = os.open(Path(root).resolve(), os.O_RDONLY | os.O_DIRECTORY)
        try:
            for component in parts[:-1]:
                try:
                    os.mkdir(component, 0o700, dir_fd=parent)
                except FileExistsError:
                    pass
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                os.close(parent)
                parent = child
            try:
                fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=parent)
            except FileExistsError:
                fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
                with os.fdopen(fd, "rb") as handle:
                    info = os.fstat(handle.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or handle.read(len(raw) + 1) != raw:
                        raise LedgerError("WORK_CANDIDATE_CHANGED")
            else:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
        finally:
            os.close(parent)
    return base
