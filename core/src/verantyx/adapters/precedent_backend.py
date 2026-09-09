"""Narrow port to the user's existing Precedent executor; no model/engine calls."""
from pathlib import Path
import hashlib
import os
import subprocess
import types

from .observations import read_document, observe, normalize_path
from ..domain.codec import digest
from ..errors import LedgerError

MAX_FILES = 1024
MAX_TREE_BYTES = 16 * 1024 * 1024


class PrecedentBackend:
    def __init__(self, path, expected_hash=None):
        self.source = Path(path).expanduser().resolve() / "precedent/execution.py"
        try:
            raw = read_document(self.source, 256 * 1024)
        except (OSError, LedgerError):
            raise LedgerError("PRECEDENT_UNAVAILABLE") from None
        self.identity = {"backend": "precedent.execution.v1", "path": str(self.source),
                         "sha256": hashlib.sha256(raw).hexdigest()}
        self.fingerprint = digest(self.identity)
        if expected_hash is not None and self.fingerprint != expected_hash:
            raise LedgerError("PRECEDENT_CHANGED")
        # Explicit local backend selection is a trust boundary, like selecting an executable.
        # Load only the audited execution module, never engine/UI/provider integrations.
        self.module = types.ModuleType("verantyx_precedent_execution")
        try:
            exec(compile(raw, str(self.source), "exec"), self.module.__dict__)
        except (SyntaxError, ImportError):
            raise LedgerError("PRECEDENT_UNAVAILABLE") from None

    def fresh(self):
        if hashlib.sha256(read_document(self.source, 256 * 1024)).hexdigest() != self.identity["sha256"]:
            raise LedgerError("PRECEDENT_CHANGED")

    def git(self, root, *args):
        self.fresh()
        if any(name in os.environ for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
                                                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT")):
            raise LedgerError("GIT_FAILED")
        try:
            # Precedent supplies the subprocess boundary; disable hooks and file monitors.
            return self.module.git(Path(root), "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *args)
        except (RuntimeError, OSError, UnicodeError, subprocess.TimeoutExpired):
            raise LedgerError("GIT_FAILED") from None

    def snapshot(self, root):
        root = Path(root).resolve()
        top = self.git(root, "rev-parse", "--show-toplevel")
        if Path(top).resolve() != root:
            raise LedgerError("GIT_ROOT")
        base = self.git(root, "rev-parse", "HEAD")
        listed = self.git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
        names = sorted(set(filter(None, listed.split("\0"))))
        names = [n for n in names if n != ".verantyx" and not n.startswith(".verantyx/")]
        if len(names) > MAX_FILES:
            raise LedgerError("DOCUMENT_LIMIT")
        values, size = {}, 0
        for name in names:
            name = normalize_path(name)
            record = observe(root, name, "2000-01-01T00:00:00.000000Z", "2000-01-02T00:00:00.000000Z")
            if record["status"] not in ("OBSERVED", "MISSING"):
                raise LedgerError("SOURCE_UNSAFE")
            size += record["size"] or 0
            if size > MAX_TREE_BYTES:
                raise LedgerError("DOCUMENT_LIMIT")
            values[name] = {k: record[k] for k in ("status", "sha256", "size")}
        tree = self.git(root, "ls-tree", "-r", "--full-tree", "-z", base)
        return {"root": str(root), "base_version": base, "files": values,
                "index_hash": digest(self.git(root, "ls-files", "--stage", "-z")), "tree_hash": digest(tree)}

    def prepare(self, root, target, base):
        self.fresh()
        if target.exists() or target.is_symlink():
            raise LedgerError("DESTINATION_EXISTS")
        records = self.git(root, "ls-tree", "-r", "--full-tree", "-z", base).split("\0")
        files, total = [], 0
        for record in filter(None, records):
            meta, name = record.split("\t", 1)
            mode, kind, oid = meta.split()
            if kind != "blob" or mode not in ("100644", "100755"):
                raise LedgerError("SOURCE_UNSAFE")  # No submodules or symlinks in this capability.
            name = normalize_path(name)
            total += int(self.git(root, "cat-file", "-s", oid))
            if total > MAX_TREE_BYTES or len(files) >= MAX_FILES:
                raise LedgerError("DOCUMENT_LIMIT")
            files.append((name, mode, oid))
        # No checkout: this prevents smudge filters or checkout hooks executing project code.
        self.git(root, "worktree", "add", "--detach", "--no-checkout", str(target), base)
        for name, mode, oid in files:
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as handle:
                result = subprocess.run(["git", "-C", str(root), "cat-file", "blob", oid],
                                        stdout=handle, stderr=subprocess.PIPE, timeout=30)
                if result.returncode:
                    raise LedgerError("GIT_FAILED")
            destination.chmod(0o755 if mode == "100755" else 0o644)
        self.git(target, "read-tree", base)
        return {"worktree": str(target), "base_version": base, "files": len(files)}

    def apply_and_test(self, root, files, tests):
        self.fresh()
        try:
            self.module.apply_files(root, files, list(files))
            applied = {name: hashlib.sha256(read_document(root / name, 100000)).hexdigest() for name in files}
            evidence = self.module.run_tests(root, [root / name for name in tests])
            from ..domain.effects import completed_unittest_report
            if evidence["passed"] and not completed_unittest_report(evidence["output"]):
                # A candidate can exit during import before unittest ran at all.
                evidence = {**evidence, "passed": False, "reason": "SUITE_COMPLETION_NOT_OBSERVED"}
        except (RuntimeError, ValueError, OSError, subprocess.SubprocessError):
            raise LedgerError("PRECEDENT_FAILED") from None
        return applied, evidence
