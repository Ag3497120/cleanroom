"""Project-local model choices for the Cleanroom notebook.

Secrets stay outside the project.  The selected connection records adapter
paths and environment-variable names only; model output remains a proposal.
"""
from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
import uuid

from . import config as project_config
from .connections_v05 import configure_model
from .errors import LedgerError


FORMAT = "verantyx.model-selection.v1"
PROFILE_ROOT = (".verantyx", "model-adapters")


def _require(condition, reason):
    if not condition:
        raise LedgerError("MODEL_SETTINGS", {"reason": reason})


def _root(value):
    return Path(value).resolve()


def _profile(root, prefix):
    directory = _root(root).joinpath(*PROFILE_ROOT, prefix + "-" + uuid.uuid4().hex[:16])
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    return directory


def _relative(root, path):
    return Path(path).resolve().relative_to(_root(root)).as_posix()


def _selection(kind, label, creator, reviewer, root):
    return {
        "format": FORMAT,
        "kind": kind,
        "label": label,
        "creator_adapter": _relative(root, creator),
        "reviewer_adapter": _relative(root, reviewer),
    }


def _save_selection(root, configuration, selection):
    root = _root(root)
    current, expected = project_config.load(root)
    _require(current is not None and current["project"]["id"] == configuration["project"]["id"], "CONFIG_CHANGED")
    updated = deepcopy(current)
    updated["runtime"] = {**updated["runtime"], "model_selection": selection}
    project_config.save(root, updated, expected)
    configuration.clear()
    configuration.update(updated)
    return {"ok": True, "selection": selection}


def activate_codex(root, configuration):
    """Use the existing ChatGPT-authenticated Codex adapter in a fresh profile."""
    from .commands_codex import create_configs
    directory = _profile(root, "codex")
    created = create_configs(directory)
    adapters = created["adapters"]
    selection = _selection(
        "codex_subscription",
        "ChatGPT Codexサブスクリプション / gpt-5.3-codex-spark",
        adapters["implementation"],
        adapters["verification"],
        root,
    )
    return _save_selection(root, configuration, selection)


def activate_api(root, configuration, *, provider, label, creator_model, reviewer_model,
                 creator_endpoint, reviewer_endpoint, key_env=None, allow_loopback_http=False):
    """Create two explicit adapters without storing an API credential."""
    _require(type(creator_model) is str and bool(creator_model.strip()), "CREATOR_MODEL")
    _require(type(reviewer_model) is str and bool(reviewer_model.strip()), "REVIEWER_MODEL")
    _require((provider, creator_model, creator_endpoint) != (provider, reviewer_model, reviewer_endpoint),
             "ROLE_COLLISION")
    directory = _profile(root, "api")
    creator, reviewer = directory / "implementation.json", directory / "verification.json"
    configure_model(root, provider=provider, model=creator_model.strip(), endpoint=creator_endpoint,
                    key_env=key_env, output=creator, allow_loopback_http=allow_loopback_http)
    configure_model(root, provider=provider, model=reviewer_model.strip(), endpoint=reviewer_endpoint,
                    key_env=key_env, output=reviewer, allow_loopback_http=allow_loopback_http)
    selection = _selection("model_api", label, creator, reviewer, root)
    return _save_selection(root, configuration, selection)


def clear(root, configuration):
    root = _root(root)
    current, expected = project_config.load(root)
    _require(current is not None and current["project"]["id"] == configuration["project"]["id"], "CONFIG_CHANGED")
    updated = deepcopy(current)
    updated["runtime"] = {"backend": "none"}
    project_config.save(root, updated, expected)
    configuration.clear()
    configuration.update(updated)
    return {"ok": True, "selection": None}


def active_adapters(root, configuration):
    selection = configuration.get("runtime", {}).get("model_selection")
    if selection is None:
        return None
    _require(selection.get("format") == FORMAT, "SELECTION_FORMAT")
    project = _root(root)
    profile_root = project.joinpath(*PROFILE_ROOT).resolve()
    paths = []
    for field in ("creator_adapter", "reviewer_adapter"):
        relative = Path(selection[field])
        _require(not relative.is_absolute() and ".." not in relative.parts, "SELECTION_SCOPE")
        path = (project / relative).resolve()
        _require(path.is_relative_to(profile_root) and path.is_file() and not path.is_symlink(), "SELECTION_FILE")
        paths.append(str(path))
    return tuple(paths)


def describe(configuration):
    selection = configuration.get("runtime", {}).get("model_selection")
    if selection is None:
        return {
            "configured": False,
            "label": "既定のCodex接続（初回の仕事で候補設定を作成）",
        }
    return {
        "configured": True,
        "label": selection["label"],
        "kind": selection["kind"],
        "creator_adapter": selection["creator_adapter"],
        "reviewer_adapter": selection["reviewer_adapter"],
    }


def ollama_models():
    """List locally installed Ollama names without sending project content."""
    executable = shutil.which("ollama")
    if not executable:
        return []
    try:
        completed = subprocess.run(
            [executable, "list"], capture_output=True, text=True, timeout=3, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    names = []
    for line in completed.stdout.splitlines()[1:]:
        columns = line.split()
        if columns and columns[0] not in names:
            names.append(columns[0])
    return names[:32]
