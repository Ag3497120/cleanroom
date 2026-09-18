"""Project-local configuration with conflict detection and recoverable writes.

The lock coordinates Verantyx processes; it is not an OS security boundary.
No agent permission or human approval is created by this bootstrap config.
"""
from pathlib import Path
import json
import os
import re
import uuid


class ConfigError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def config_path(root: Path) -> Path:
    return root / ".verantyx" / "config.json"


def check_location(root: Path) -> Path:
    if not root.is_dir():
        raise ConfigError("PROJECT_MISSING")
    path = config_path(root)
    if path.parent.is_symlink() or path.is_symlink():
        raise ConfigError("CONFIG_SYMLINK")
    return path


def validate(value: dict) -> None:
    try:
        if type(value) is not dict:
            raise ValueError()
        if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
            raise ConfigError("CONFIG_VERSION")
        if set(value) != {"schema_version", "project", "ui", "learning", "runtime", "telemetry"}:
            raise ValueError()
        project, ui, learning, runtime = value["project"], value["ui"], value["learning"], value["runtime"]
        if set(project) != {"id", "name", "purpose"} or set(ui) != {"locale"}:
            raise ValueError()
        uuid.UUID(project["id"])
        if not isinstance(project["name"], str) or not 1 <= len(project["name"].strip()) <= 120:
            raise ValueError()
        if not isinstance(project["purpose"], str) or len(project["purpose"]) > 4000:
            raise ValueError()
        if ui["locale"] not in ("en", "ja", "zh-Hans", "ko", "es"):
            raise ValueError()
        if set(learning) != {"mode", "max_items"} or learning["mode"] not in ("manual", "digest", "off"):
            raise ValueError()
        if type(learning["max_items"]) is not int or not 1 <= learning["max_items"] <= 3:
            raise ValueError()
        if (type(runtime) is not dict or runtime.get("backend") != "none"
                or not {"backend"} <= set(runtime) <= {"backend", "model_selection", "reflection"}):
            raise ValueError()
        if "reflection" in runtime:
            from .agent_models import validate_setting
            validate_setting(runtime["reflection"])
        selection = runtime.get("model_selection")
        if selection is not None:
            if type(selection) is not dict or set(selection) != {
                "format", "kind", "label", "creator_adapter", "reviewer_adapter"
            }:
                raise ValueError()
            if selection["format"] != "verantyx.model-selection.v1" or selection["kind"] not in (
                "codex_subscription", "claude_subscription", "model_api"
            ):
                raise ValueError()
            if (not isinstance(selection["label"], str) or not 1 <= len(selection["label"].strip()) <= 240
                    or any(ord(character) < 32 for character in selection["label"])):
                raise ValueError()
            paths = (selection["creator_adapter"], selection["reviewer_adapter"])
            if any(not isinstance(path, str) or not re.fullmatch(
                r"\.verantyx/model-adapters/[a-z0-9][a-z0-9-]{0,79}/(?:implementation|verification)\.json", path
            ) for path in paths):
                raise ValueError()
            if not selection["creator_adapter"].endswith("/implementation.json") or not selection["reviewer_adapter"].endswith("/verification.json"):
                raise ValueError()
        if set(value["telemetry"]) != {"enabled"} or value["telemetry"]["enabled"] is not False:
            raise ValueError()
    except ConfigError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ConfigError("CONFIG_INVALID") from None


def load(root: Path) -> tuple[dict | None, bytes | None]:
    path = check_location(root)
    if not path.exists():
        return None, None
    with path.open("rb") as handle:
        raw = handle.read(65537)
    if len(raw) > 65536:
        raise ConfigError("CONFIG_INVALID")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ConfigError("CONFIG_INVALID") from None
    validate(value)
    return value, raw


def defaults(root: Path, locale: str) -> dict:
    return {
        "schema_version": 1,
        "project": {"id": str(uuid.uuid4()), "name": root.name or "verantyx", "purpose": ""},
        "ui": {"locale": locale},
        "learning": {"mode": "digest", "max_items": 1},
        "runtime": {"backend": "none", "reflection": {"mode": "off", "adapter": None, "label": "Manual"}},
        "telemetry": {"enabled": False},
    }


def exclusive_write(path: Path, raw: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def save(root: Path, value: dict, expected: bytes | None) -> bool:
    validate(value)
    path = check_location(root)
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(mode=0o700, exist_ok=True)
    lock = path.parent / ".config.lock"
    try:
        lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ConfigError("CONFIG_LOCKED") from None
    temporary = path.parent / f".config.{uuid.uuid4().hex}.tmp"
    try:
        _, current = load(root)
        if current != expected:
            raise ConfigError("CONFIG_CHANGED")
        if current == raw:
            return False
        exclusive_write(temporary, raw)
        if current is not None:
            # Keep the exact previous bytes before replacing a valid config.
            exclusive_write(path.parent / f"config.backup.{uuid.uuid4().hex}.json", current)
            os.replace(temporary, path)
        else:
            # Creation must not overwrite a file created by another writer.
            try:
                os.link(temporary, path)
            except FileExistsError:
                raise ConfigError("CONFIG_CHANGED") from None
        return True
    finally:
        temporary.unlink(missing_ok=True)
        os.close(lock_fd)
        lock.unlink(missing_ok=True)
