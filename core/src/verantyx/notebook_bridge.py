"""Private Markdown/Obsidian projection and passive skill migration.

The SQLite/event ledger remains authoritative. Markdown edits never grant
permissions or mark mastery. No imported script is executed.
"""
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlencode
import hashlib
import json
import os
import stat
import uuid

from . import personal_profile as profile
from .domain.codec import canonical, digest
from .errors import LedgerError

CONFIG_ID = "integration-obsidian"
EXPORT_KINDS = {"statement", "note", "journal", "lesson", "skill_asset", "skill_progress",
                "learning_trace", "learning_guide"}


def _directory(path, create=False):
    path = Path(path).expanduser()
    profile.require(path.is_absolute(), "VAULT_ABSOLUTE_PATH")
    for part in [*reversed(path.parents), path]:
        profile.require(not part.is_symlink(), "VAULT_SYMLINK")
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    profile.require(path.is_dir(), "VAULT_REQUIRED")
    return path.resolve()


def _write(root, relative, body):
    # Walk directories by descriptor; never follow a replaced child symlink.
    parts = relative.split("/")
    profile.require(all(p and p not in (".", "..") and "\\" not in p for p in parts), "VAULT_PATH")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    raw = body.encode("utf-8")
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, 0o700, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        try:
            output = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            previous = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(previous, "rb") as stream:
                info = os.fstat(stream.fileno())
                profile.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                                and stream.read(len(raw) + 1) == raw, "VAULT_EDIT_CONFLICT")
        else:
            with os.fdopen(output, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
    finally:
        os.close(fd)


def settings():
    return profile.get_record(CONFIG_ID) or {"enabled": False, "auto_sync": False}


def connect(path, *, confirmed=False, include_private=False, auto=False):
    profile.require(confirmed and include_private, "VAULT_PRIVATE_EXPORT_APPROVAL")
    root = _directory(path, create=True)
    previous = settings()
    same = previous.get("path") == str(root)
    profile.put_record({"id": CONFIG_ID, "kind": "integration", "enabled": True,
                        "path": str(root), "auto_sync": bool(auto), "private_export_approved": True,
                        "files": previous.get("files", {}) if same else {},
                        "index": previous.get("index", "") if same else "",
                        "authority": "OWNER_SELECTED", "share_with_ai": False})
    return sync()


def _rows():
    with profile.connection() as db:
        if db is None:
            return []
        return [json.loads(row[0]) for row in db.execute("SELECT document FROM records ORDER BY updated,id")
                if json.loads(row[0]).get("kind") in EXPORT_KINDS]


def _tags(row):
    tags = list(row.get("definition", {}).get("technology_tags", []))
    if row.get("technology"):
        tags.append(row["technology"])
    raw = row.get("event", {}).get("payload", {}).get("proposal", {}).get("learning_notes", [])
    if isinstance(raw, list):
        for note in raw:
            if isinstance(note, dict):
                tags += [x for x in note.get("technology_tags", []) if isinstance(x, str)]
    return sorted(set(tags))[:16]


def sync():
    value = settings()
    profile.require(value.get("enabled") and value.get("private_export_approved"), "VAULT_NOT_CONNECTED")
    root = _directory(value["path"])
    files = dict(value.get("files", {}))
    index = ["# Cleanroom notebook", "", "AI procedures, original work and your own experience are separate.", ""]
    technology_links = {}
    for row in _rows():
        record_hash = digest(row)
        filename = "Cleanroom/records/" + digest(row["id"])[:20] + "-" + record_hash[:20] + ".md"
        title = str(row.get("title") or row.get("definition", {}).get("title") or row.get("technology") or row["kind"])
        tags = _tags(row)
        links = []
        for tag in tags:
            techpath = "Cleanroom/technologies/" + digest(tag)[:24] + ".md"
            _write(root, techpath, "# " + tag.replace("\n", " ") + "\n\nA connection in your notebook, not a mastery score.\n")
            links.append("[[" + techpath[:-3] + "|" + tag.replace("|", " ").replace("]", "") + "]]")
            technology_links[tag] = techpath
        data = canonical(row)
        fence = "~" * (max([len(x) for x in data.splitlines() if x and not x.strip("~")] or [2]) + 1)
        body = ("---\ncleanroom_id: " + json.dumps(row["id"]) + "\nkind: " + json.dumps(row["kind"])
                + "\nsource_sha256: " + record_hash + "\n---\n\n# " + title.replace("\n", " ")
                + "\n\n" + " ".join(links) + "\n\nSource record; AI text is not proof of your understanding.\n\n"
                + fence + "json\n" + json.dumps(row, ensure_ascii=False, indent=2) + "\n" + fence + "\n")
        _write(root, filename, body)
        files[row["id"]] = filename
        index.append("- [[" + filename[:-3] + "|" + title.replace("|", " ").replace("]", "").replace("\n", " ") + "]]")
    index_name = "Cleanroom/notebook-" + digest(files)[:24] + ".md"
    _write(root, index_name, "\n".join(index) + "\n")
    updated = {**value, "files": files, "index": index_name}
    with profile.connection(True) as db:
        profile._put(db, updated)
    return {"ok": True, "records": len(files), "vault": str(root),
            "url": "obsidian://open?" + urlencode({"path": str(root / index_name)}),
            "human_progress_changed": False, "scripts_executed": False}


def auto_sync():
    try:
        value = settings()
        return sync() if value.get("enabled") and value.get("auto_sync") else {"status": "OFF"}
    except Exception as error:
        return {"status": "DEFERRED", "reason": getattr(error, "code", type(error).__name__),
                "work_result_unchanged": True}


def link(identity=None):
    value = settings()
    relative = value.get("files", {}).get(identity) if identity else value.get("index")
    if not value.get("enabled") or not relative:
        return None
    return "obsidian://open?" + urlencode({"path": str(Path(value["path"]) / relative)})


def import_text(text, *, origin, title="Imported skill", technologies=(), confirmed=False):
    profile.require(confirmed and type(text) is str and 0 < len(text.encode()) <= 131072,
                    "SKILL_IMPORT_APPROVAL")
    profile.require(type(origin) is str and 0 < len(origin) <= 1000
                    and type(title) is str and 0 < len(title) <= 200
                    and len(technologies) <= 8 and all(type(t) is str and 0 < len(t) <= 100 for t in technologies),
                    "SKILL_IMPORT_METADATA")
    fingerprint = digest({"origin": origin, "text": text})
    identity = "imported-skill-" + fingerprint[:32]
    if profile.get_record(identity):
        return {"ok": True, "id": identity, "replayed": True, "human_progress_changed": False}
    ref = "import:" + fingerprint
    stamp = profile.now()
    definition = {"title": title, "purpose": "Imported procedure; applicability requires review.",
                  "technology_tags": list(technologies), "inputs": [], "outputs": [],
                  "steps": ["Read the preserved source document; it is not executed automatically."],
                  "applicable_when": ["The owner has reviewed the source and its scope."],
                  "stop_when": ["Source instructions conflict with project permissions."],
                  "verification_methods": [], "human_decisions": [], "source_event_ids": [ref],
                  "extends_skill_id": ""}
    asset = {"id": identity, "kind": "skill_asset", "project_id": "external-import",
             "project_name": origin, "run_id": identity, "work_key": "external-import/" + identity,
             "reflection_id": "", "source_ref": ref, "trace_sha256": fingerprint,
             "model": {"provider": "external-import", "model": origin, "adapter_sha256": None},
             "definition": definition, "definition_sha256": digest(definition),
             "source_text": text, "source_origin": origin, "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
             "created_at": stamp, "authority": "UNTRUSTED_IMPORTED_PROCEDURE_NOT_MASTERY", "share_with_ai": False}
    note = {"title": title, "target_kind": "SKILL", "technology_tags": list(technologies),
            "explanation": "An external procedure was imported. Read the preserved source_text.",
            "prerequisites": [], "expanded_steps": [], "alternatives": [], "pitfalls": [],
            "verification": [], "next_small_step": "", "source_event_ids": [], "profile_refs": []}
    payload = {"source_text": text, "origin": origin, "proposal": {"learning_notes": [note]}}
    event = {"source_ref": ref, "revision": 1, "type": "ImportedSkillDocument",
             "actor_kind": "external_import", "recorded_at": stamp, "event_hash": digest(payload), "payload": payload}
    trace = {"id": "learning-trace-" + digest(ref)[:40], "kind": "learning_trace",
             "work_key": asset["work_key"], "project_id": asset["project_id"], "project_name": origin,
             "run_id": identity, "request": title, "event": event, "profile_snapshot": {},
             "profile_snapshot_sha256": None, "profile_refs": [], "share_with_ai": False,
             "authority": "UNTRUSTED_IMPORTED_SOURCE", "created_at": stamp}
    with profile.connection(True) as db:
        profile._put(db, asset)
        profile._put(db, trace)
    auto_sync()
    return {"ok": True, "id": identity, "human_state": "NO_RECORD", "ai_use": "DRAFT",
            "scripts_executed": False, "scope_verified": False}


def import_file(path, **kwargs):
    target = Path(path).expanduser()
    profile.require(target.is_absolute(), "SKILL_IMPORT_ABSOLUTE")
    for part in [*reversed(target.parents), target]:
        profile.require(not part.is_symlink(), "SKILL_IMPORT_SYMLINK")
    fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        profile.require(stat.S_ISREG(info.st_mode) and info.st_size <= 131072, "SKILL_IMPORT_LIMIT")
        raw = stream.read(131073)
    profile.require(len(raw) <= 131072, "SKILL_IMPORT_LIMIT")
    return import_text(raw.decode("utf-8"), **kwargs)


def graph():
    nodes, edges, by_id = [], [], {}
    for row in reversed(_rows()):
        if row["kind"] not in ("skill_asset", "learning_trace", "statement"):
            continue
        if row["kind"] == "learning_trace" and not row.get("event", {}).get("payload", {}).get("proposal", {}).get("learning_notes"):
            continue
        if len(nodes) >= 72:
            break
        key = row["id"]
        label = str(row.get("definition", {}).get("title") or row.get("title")
                    or row.get("technology") or row.get("request") or row["kind"])[:120]
        kind = "owner" if row["kind"] == "statement" else "skill" if row["kind"] == "skill_asset" else "work"
        nodes.append({"id": key, "label": label, "kind": kind, "obsidian_url": link(key)})
        by_id[key] = True
        for tag in _tags(row):
            tid = "technology-" + digest(tag)[:24]
            if tid not in by_id:
                if len(nodes) >= 72:
                    continue
                nodes.append({"id": tid, "label": tag, "kind": "technology", "obsidian_url": None})
                by_id[tid] = True
            edges.append({"source": key, "target": tid, "relation": "recorded_tag_not_mastery"})
    return {"nodes": nodes, "edges": edges, "limit": 72, "mastery_score": None,
            "obsidian_url": link(), "connected": bool(settings().get("enabled")), "read_only": True}
