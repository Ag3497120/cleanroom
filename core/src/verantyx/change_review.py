"""Pre-write candidate review. This does not authorize source adoption or tools."""
import difflib
import hashlib
from pathlib import PurePosixPath

from .cleanroom_io import current
from .domain.codec import digest
from .errors import LedgerError
from .interaction_text import tr


def _sha(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def prepare(root, run_id, turn, request, scope, artifacts, raw):
    from .agent_candidate_files import read_bytes, MAX_ASSET_BYTES
    from .agent_runtime import _read_text
    path = request["path"]
    prior = artifacts.get(path)
    before, baseline = None, "NOT_READ"
    if prior is not None:
        before = read_bytes(root, prior["storage_path"], expected=prior,
                            limit=MAX_ASSET_BYTES, internal=True)
        baseline = "CANDIDATE"
    elif path in scope:
        try:
            before = _read_text(root, path).encode("utf-8")
            baseline = "APPROVED_SOURCE"
        except LedgerError as error:
            if error.code != "WORK_TEXT_ONLY":
                raise
            # A text-only approved scope is not permission to infer binary data.
    try:
        left = before.decode("utf-8") if before is not None else ""
        right = raw.decode("utf-8")
        binary = False
        diff = "\n".join(difflib.unified_diff(
            left.splitlines(), right.splitlines(),
            fromfile=("a/" + path) if before is not None else "(base not read)",
            tofile="candidate/" + path, lineterm=""))
        endings = {"before_final_newline": before.endswith(b"\n") if before is not None else None,
                   "after_final_newline": raw.endswith(b"\n")}
    except UnicodeDecodeError:
        binary, diff, endings = True, "", {}
    directories = [str(parent) for parent in reversed(PurePosixPath(path).parents)
                   if str(parent) != "."]
    preview = {"run_id": run_id, "turn": turn, "request_id": request["id"], "path": path,
               "before_sha256": _sha(before), "after_sha256": _sha(raw),
               "before_bytes": len(before) if before is not None else None,
               "after_bytes": len(raw), "baseline": baseline, "binary": binary,
               "diff": diff, "diff_sha256": digest({"diff": diff, **endings}),
               "directories": directories, **endings}
    preview["review_id"] = digest(preview)
    return preview


def describe(preview, lang):
    lines = [preview["path"], tr("candidate_only", lang)]
    if preview["baseline"] == "NOT_READ":
        lines += [tr("base_unknown", lang)]
    lines += ["Base: " + preview["baseline"],
              "Before: " + str(preview["before_bytes"]) + " bytes / " + str(preview["before_sha256"]),
              "After: " + str(preview["after_bytes"]) + " bytes / " + preview["after_sha256"]]
    if preview["directories"]:
        lines += [tr("candidate_folders", lang), "  " + " / ".join(preview["directories"])]
    if not preview["binary"]:
        lines += ["Final newline: " + str(preview.get("before_final_newline"))
                  + " -> " + str(preview.get("after_final_newline"))]
    lines += ["", tr("binary_diff", lang) if preview["binary"] else
              preview["diff"] or tr("no_changes", lang)]
    return "\n".join(lines)


def review(preview):
    from . import session_store
    ui = current.get()
    mode, grant_id = "PREAUTHORIZED", ""
    if ui is not None and hasattr(ui, "review_change"):
        saved = session_store.edit_grant(ui.root)
        if saved:
            mode = "WORKSPACE" if saved["scope"] == "workspace" else "PERMANENT"
            grant_id = saved["id"]
        else:
            choice = ui.review_change(preview)
            mode = {"allow": "ALLOW_ONCE", "workspace": "WORKSPACE",
                    "permanent": "PERMANENT"}.get(choice, "DENIED")
            if choice in ("workspace", "permanent"):
                grant_id = session_store.grant(ui.root, choice)
        ui.notice_change(preview, mode)
    return {key: preview[key] for key in (
        "review_id", "path", "request_id", "before_sha256", "after_sha256",
        "diff_sha256", "baseline")} | {
        "scope": "ISOLATED_CANDIDATE_ONLY", "mode": mode, "grant_id": grant_id}


def unchanged(root, preview, artifacts):
    from .agent_candidate_files import read_bytes, MAX_ASSET_BYTES
    from .agent_runtime import _read_text
    if preview["baseline"] == "CANDIDATE":
        prior = artifacts[preview["path"]]
        raw = read_bytes(root, prior["storage_path"], expected=prior,
                         limit=MAX_ASSET_BYTES, internal=True)
    elif preview["baseline"] == "APPROVED_SOURCE":
        raw = _read_text(root, preview["path"]).encode("utf-8")
    else:
        return
    if _sha(raw) != preview["before_sha256"]:
        raise LedgerError("WORK_INPUT_CHANGED")
