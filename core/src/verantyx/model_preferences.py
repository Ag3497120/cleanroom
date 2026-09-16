"""Explicit model tuning and bounded metadata discovery; no project content sent."""
from copy import deepcopy
import ipaddress
import json
import os
from pathlib import Path
import urllib.request
from urllib.parse import urlsplit, urlunsplit

from .cleanroom_io import current, console_print as print
from .domain.codec import canonical, decode, digest
from .errors import LedgerError
from .session_text import t
from .interaction_text import locale


def pick(title, choices, details=None):
    lang, owner = locale(), current.get()
    if owner is not None:
        return owner.choose(title, choices, descriptions=details or {},
                            aliases={str(key).casefold(): key for key, _ in choices})
    from .choice_navigation import choose
    return choose(title, choices, details or {}, lang)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch(native, path, body=None):
    parsed = urlsplit(native["endpoint"])
    try:
        local = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        local = False
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local and native.get("allow_loopback_http")):
        raise LedgerError("ARGUMENTS", {"reason": "METADATA_ENDPOINT"})
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise LedgerError("ARGUMENTS")
    url = urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
    headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
    key = native.get("key_env")
    if key:
        token = os.environ.get(key, "")
        if not token or len(token) > 8192 or not token.isascii() or any(ord(c) <= 32 for c in token):
            raise LedgerError("ARGUMENTS", {"reason": "METADATA_CREDENTIAL"})
        headers["Authorization"] = "Bearer " + token
    data = None if body is None else canonical(body).encode()
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.build_opener(NoRedirect).open(request, timeout=4) as response:
        raw = response.read(262145)
    return decode(raw, 262144)


def metadata(native):
    model, provider = native.get("model"), native.get("provider")
    result = {"model": model, "maximum": None, "loaded": None, "efforts": [], "source": "UNAVAILABLE"}
    try:
        if native.get("format") == "verantyx.codex-cli.v1":
            # Read model metadata only, never account tokens or auth.json.
            path = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "models_cache.json"
            if path.is_symlink():
                return result
            with path.open("rb") as stream:
                value = decode(stream.read(524289), 524288)
            rows = value.get("models", []) if isinstance(value, dict) else []
            row = next((item for item in rows if isinstance(item, dict) and item.get("slug") == model), {})
            result.update(maximum=row.get("context_window"), source="LOCAL_CODEX_MODEL_CACHE")
            result["efforts"] = [item.get("effort") for item in row.get("supported_reasoning_levels", [])
                                 if isinstance(item, dict)]
        elif provider == "ollama":
            value = _fetch(native, "/api/show", {"model": model, "verbose": False})
            info = value.get("model_info", {}) if isinstance(value, dict) else {}
            sizes = [size for key, size in info.items() if key.endswith(".context_length") and type(size) is int]
            result.update(maximum=max(sizes) if sizes else None, source="OLLAMA_API_SHOW")
            if "thinking" in value.get("capabilities", []):
                result["efforts"] = ["off", "on", "low", "medium", "high"]
        elif provider == "openai_compatible":
            value = _fetch(native, "/api/v1/models")
            rows = value.get("models", []) if isinstance(value, dict) else []
            row = next((item for item in rows if isinstance(item, dict) and (
                item.get("key") == model or any(instance.get("id") == model for instance in item.get("loaded_instances", [])))), {})
            instances = row.get("loaded_instances", [])
            sizes = [item.get("config", {}).get("context_length") for item in instances if isinstance(item, dict)]
            result.update(maximum=row.get("max_context_length"),
                          loaded=min([x for x in sizes if type(x) is int], default=None),
                          source="LM_STUDIO_API_V1")
            reason = row.get("capabilities", {}).get("reasoning", {})
            result["efforts"] = reason.get("allowed_options", []) if isinstance(reason, dict) else []
    except (OSError, ValueError, KeyError, TypeError, LedgerError):
        return result
    for key in ("maximum", "loaded"):
        if type(result[key]) is not int or result[key] < 1:
            result[key] = None
    result["efforts"] = [x for x in result["efforts"] if x in ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra", "off", "on")]
    return result


def local_models(endpoint, *, lmstudio=False):
    native = {"endpoint": endpoint, "allow_loopback_http": True}
    try:
        value = _fetch(native, "/api/v1/models" if lmstudio else "/api/tags")
        rows = value.get("models", []) if isinstance(value, dict) else []
        field = "key" if lmstudio else "name"
        return [item[field] for item in rows if isinstance(item, dict) and isinstance(item.get(field), str)
                and item.get("type") != "embedding"][:128]
    except (OSError, ValueError, LedgerError):
        return []


def window_choice(native):
    lang = locale()
    choices = [("default", t("provider_default", lang)), ("discover", t("discover", lang)),
               (8192, "8,192"), (16384, "16,384"), (32768, "32,768"),
               (65536, "65,536"), (131072, "131,072"), ("manual", t("manual", lang))]
    report = None
    while True:
        value = pick(t("context_window", lang), choices,
                     {key: t("window_detail", lang) for key, _ in choices})
        if value is None:
            return False, None
        if value == "discover":
            report = metadata(native)
            print(canonical(report))
            capacity = report["loaded"] or report["maximum"]
            if capacity and 4096 <= capacity <= 2000000:
                choices = [("default", t("provider_default", lang)), (capacity, str(capacity) + " / " + report["source"]),
                           ("manual", t("manual", lang))]
            else:
                print(t("metadata_unknown", lang))
            continue
        if value == "default":
            return True, None
        if value == "manual":
            from .development_console import _ask
            raw = _ask(t("manual", lang) + " [4096..2000000]")
            if not raw:
                return False, None
            try:
                value = int(raw.replace(",", ""))
            except ValueError:
                continue
        if type(value) is int and 4096 <= value <= 2000000:
            if report and report["maximum"] and value > report["maximum"]:
                print(t("window_detail", lang))
                continue
            return True, value


def _efforts(native):
    provider = native.get("provider")
    if provider == "ollama":
        return ["default", "off", "on", "low", "medium", "high"]
    if provider in ("claude_code", "anthropic"):
        return ["default", "low", "medium", "high", "xhigh", "max"]
    if provider == "gemini":
        return ["default", "minimal", "low", "medium", "high"]
    return ["default", "none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"]


def apply_tuning(root, configuration, adapter, original_hash, effort, window):
    from .authority import require_current_approval_valid
    from .adapters.observations import read_document
    from .model_settings import _profile, _selection, _save_selection
    from .model_roles import load, register
    from .agent_models import selected_work
    require_current_approval_valid()
    # Refuse a stale menu rather than overwriting a newly selected connection.
    if str(selected_work(root, configuration)) != str(adapter):
        raise LedgerError("CONFIG_CHANGED")
    native = decode(read_document(adapter, 65536), 65536)
    if digest(native) != original_hash:
        raise LedgerError("CONFIG_CHANGED")
    value = deepcopy(native)
    value.pop("context_window", None)
    if window is not None:
        value["context_window"] = window
    kind = value.get("format")
    if kind == "verantyx.codex-cli.v1":
        value["reasoning_effort"] = "auto" if effort == "default" else effort
        directory = _profile(root, "codex")
        from .codex_budget import initialize
        value["budget_directory"] = str(directory / "budget")
        initialize(directory / "budget", value["max_calls"])
        from .codex_cli import validate_config
        selection_kind = "codex_subscription"
    elif kind == "verantyx.claude-cli.v1":
        value.pop("reasoning_effort", None)
        if effort != "default":
            value["reasoning_effort"] = effort
        directory = _profile(root, "claude")
        from .claude_cli import validate_config
        selection_kind = "claude_subscription"
    elif kind == "verantyx.model-api.v1":
        value.pop("reasoning_effort", None)
        value.pop("thinking", None)
        if value["provider"] == "ollama" and effort != "default":
            value["thinking"] = {"on": True, "off": False}.get(effort, effort)
        elif effort != "default":
            value["reasoning_effort"] = effort
        directory = _profile(root, "connection")
        from .model_api import validate_config
        selection_kind = "model_api"
    else:
        raise LedgerError("ARGUMENTS", {"reason": "TUNE_NATIVE_ADAPTER_ONLY"})
    validate_config(value)
    paths = [directory / name for name in ("implementation.json", "verification.json")]
    for index, path in enumerate(paths):
        row = deepcopy(value)
        if kind == "verantyx.codex-cli.v1":
            row["role"] = ("implementation", "verification")[index]
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(canonical(row) + "\n")
    roles = load(root)
    if roles.get("parent"):
        register(root, configuration, roles["parent"], str(paths[0]), confirmed=True)
    else:
        label = value.get("provider", selection_kind) + " / " + value["model"] + " / " + effort
        _save_selection(root, configuration, _selection(selection_kind, label, *paths, root))
    return {"ok": True, "status": "MODEL_SETTINGS_SAVED", "model_calls": 0}


def tune(root, configuration):
    from .agent_models import selected_work
    from .adapters.observations import read_document
    from .development_console import _mutate
    native_path = selected_work(root, configuration)
    value = decode(read_document(native_path, 65536), 65536)
    lang = locale()
    efforts = _efforts(value)
    choices = [(name, t("provider_default", lang) if name == "default" else name) for name in efforts]
    effort = pick(t("effort", lang) + " / " + value.get("model", ""),
                  choices, {name: t("effort_detail", lang) for name in efforts})
    if effort is None:
        return
    chosen, window = window_choice(value)
    if not chosen:
        return
    _mutate(root, configuration, apply_tuning, str(native_path), digest(value), effort, window)
    print(t("saved", lang))


def context_menu(root, configuration):
    from .session_store import preferences, set_preferences
    lang = locale()
    while True:
        value = preferences(root)
        print(t("context", lang) + " / " + canonical(value))
        action = pick(t("context", lang),
                      [("on", t("auto_on", lang)), ("off", t("auto_off", lang)),
                       ("model", t("tune_model", lang))],
                      {"on": t("auto_detail", lang), "off": t("compact_detail", lang),
                       "model": t("window_detail", lang)})
        if action is None:
            return
        if action == "model":
            tune(root, configuration)
        else:
            set_preferences(root, auto_compact=action == "on")


def permission_menu(root, configuration):
    from .session_store import edit_grant, revoke
    lang = locale()
    print(t("permissions", lang) + " / " + canonical(edit_grant(root)))
    action = pick(t("permissions", lang),
                  [("workspace", t("revoke_workspace", lang)), ("permanent", t("revoke_permanent", lang))],
                  {"workspace": t("workspace_detail", lang), "permanent": t("permanent_detail", lang)})
    if action:
        revoke(root, permanent=action == "permanent")
        print(t("permission_revoked", lang))
