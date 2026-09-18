"""Official CLI discovery and status, without reading credential files."""
from pathlib import Path
import json
import os
import re
import shutil
import subprocess

from .adapters.command_process import BASE_ENV
from .errors import LedgerError

PROVIDERS = ("codex", "claude")
MODEL_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}"


def validate_model(model):
    if type(model) is not str or re.fullmatch(MODEL_PATTERN, model) is None:
        raise LedgerError("MODEL_SETTINGS", {"reason": "MODEL_NAME"})
    return model


def find_executable(provider):
    if provider not in PROVIDERS:
        raise LedgerError("ARGUMENTS")
    found = shutil.which(provider)
    candidates = ([Path(found)] if found else []) + [
        Path.home() / ".local/bin" / provider,
        Path("/opt/homebrew/bin") / provider,
        Path("/usr/local/bin") / provider,
        Path.home() / ".npm-global/bin" / provider,
        Path.home() / ".cargo/bin" / provider,
    ]
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())
    return None


def environment(provider):
    if provider not in PROVIDERS:
        raise LedgerError("ARGUMENTS")
    location = "CODEX_HOME" if provider == "codex" else "CLAUDE_CONFIG_DIR"
    # The native binary owns its account store and keychain access.
    # API keys, extracted OAuth tokens and provider overrides are not imported.
    return {name: os.environ[name] for name in (*BASE_ENV, location) if name in os.environ}


def status(provider, executable=None):
    executable = executable or find_executable(provider)
    result = {"provider": provider, "installed": bool(executable),
              "executable": executable, "signed_in": False, "subscription_login": False,
              "state": "NOT_INSTALLED", "model_access_checked": False}
    if not executable:
        return result
    if provider == "claude":
        try:
            help_result = subprocess.run([executable, "--help"], cwd=Path.home(), env=environment(provider),
                                         stdin=subprocess.DEVNULL, capture_output=True, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            result["state"] = "CLI_START_FAILED"
            return result
        if (help_result.returncode != 0 or len(help_result.stdout) > 131072
                or any(flag not in help_result.stdout for flag in (b"--safe-mode", b"--restricted", b"--system-prompt-snapshot"))):
            # Old versions can interpret unknown subcommands as a paid prompt.
            result["state"] = "UPDATE_REQUIRED"
            return result
    arguments = ["login", "status"] if provider == "codex" else ["auth", "status"]
    try:
        completed = subprocess.run(
            [executable, *arguments], cwd=Path.home(), env=environment(provider),
            stdin=subprocess.DEVNULL, capture_output=True, timeout=10, check=False,
        )
    except subprocess.TimeoutExpired:
        result["state"] = "STATUS_TIMEOUT"
        return result
    except OSError:
        result["state"] = "CLI_START_FAILED"
        return result
    result["signed_in"] = completed.returncode == 0
    if completed.returncode != 0:
        result["state"] = "SIGN_IN_REQUIRED"
        return result
    if len(completed.stdout) + len(completed.stderr) > 32768:
        result["state"] = "STATUS_UNRECOGNIZED"
        return result
    if provider == "codex":
        # Parse an official authentication report, not a user's task semantics.
        report = (completed.stdout + completed.stderr).decode("utf-8", "replace").lower()
        result["subscription_login"] = "chatgpt" in report and "api key" not in report
    else:
        try:
            report = json.loads(completed.stdout)
        except (ValueError, UnicodeDecodeError):
            report = None
        if type(report) is dict:
            method = str(report.get("authMethod", "")).lower().replace(".", "")
            result["subscription_login"] = report.get("loggedIn") is True and method == "claudeai"
    # Do not expose emails, tokens, provider output or claim plan/model eligibility.
    result["state"] = "SIGNED_IN" if result["subscription_login"] else "SUBSCRIPTION_LOGIN_NOT_CONFIRMED"
    return result
