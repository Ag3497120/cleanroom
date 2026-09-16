"""Explicit official-CLI onboarding; no credential collection or silent install."""
from pathlib import Path
import json
import os
import shlex
import subprocess
import sys
import webbrowser

from .cleanroom_io import current, console_print as print
from .agent_console import terminal_text
from .authority import require_current_approval_valid
from .errors import LedgerError
from .subscription_cli import environment, find_executable, status, validate_model

LABELS = {"codex": "ChatGPT / official Codex CLI", "claude": "Claude / official Claude Code"}
DOCS = {"codex": "https://learn.chatgpt.com/docs/codex/cli",
        "claude": "https://code.claude.com/docs/en/setup"}
INSTALLERS = {
    "codex": "curl -fsSL https://chatgpt.com/codex/install.sh | sh",
    "claude": "curl -fsSL https://claude.ai/install.sh | bash",
}


def _native_operation(root, configuration, provider, arguments, action):
    require_current_approval_valid()
    env = environment(provider)
    if current.get() is not None:
        if sys.platform != "darwin":
            print("Run in a separate terminal: " + shlex.join(arguments))
            print("Then return here and choose Check again.")
            return False
        # Never put auth tokens or account output into our TUI or event log.
        # Only the safe native environment and this explicit command cross over.
        command = shlex.join(["/usr/bin/env", "-i",
                              *[name + "=" + value for name, value in env.items()], *arguments])
        command = "cd " + shlex.quote(str(Path.home())) + " && " + command
        script = 'tell application "Terminal"\nactivate\ndo script ' + json.dumps(command, ensure_ascii=False) + "\nend tell"
        try:
            result = subprocess.run(["/usr/bin/osascript", "-e", script],
                                    capture_output=True, timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired):
            result = None
        if result is None or result.returncode != 0:
            print("Could not open Terminal. Run this command in another terminal:")
            print(shlex.join(arguments))
            return False
        print("Continue in the Terminal window. Come back here when the official CLI has finished.")
        from . import development_console as ui
        ui._pick("Return after " + action, ["continue"], lambda _: "Continue / check the official CLI")
        return True
    try:
        result = subprocess.run(arguments, cwd=Path.home(), env=env, check=False, timeout=600)
    except subprocess.TimeoutExpired:
        print("The official CLI timed out. No Cleanroom connection was saved.")
        return False
    if result.returncode != 0:
        print("The official CLI did not complete (exit " + str(result.returncode) + ").")
        return False
    return True


def _confirm_native(root, configuration, provider, arguments, action):
    from . import development_console as ui
    print("\nOfficial CLI command: " + shlex.join(arguments))
    if action == "installation":
        print("This downloads and runs the vendor's installer and changes this Mac.")
        print("Review the official instructions: " + DOCS[provider])
    else:
        print("Sign in as yourself in the vendor's own flow; never paste tokens into Cleanroom.")
        print("Changing this login can affect other projects using the same official CLI account.")
    choice = ui._pick("Continue with official " + action + "?", ["continue"],
                      lambda _: "Continue / " + action)
    if choice is None:
        return False
    return ui._mutate(root, configuration, _native_operation, provider, arguments, action)


def _save_connection(root, configuration, provider, executable, model, role):
    require_current_approval_valid()
    from .model_settings import _profile, _selection, _save_selection
    from .agent_models import select_reflection
    from .domain.codec import canonical
    validate_model(model)
    if provider == "codex":
        from .commands_codex import create_configs
        directory = _profile(root, "codex")
        created = create_configs(directory, model=model, executable=executable)
        creator = Path(created["adapters"]["implementation"])
        reviewer = Path(created["adapters"]["verification"])
        kind = "codex_subscription"
    else:
        from .claude_cli import configuration as native_config
        directory = _profile(root, "claude")
        value = native_config(executable, model)
        creator, reviewer = directory / "implementation.json", directory / "verification.json"
        for path in (creator, reviewer):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(canonical(value) + "\n")
        kind = "claude_subscription"
    label = LABELS[provider] + " / " + ("CLI default" if model == "default" else model)
    if role == "reflection":
        return select_reflection(root, configuration, "custom", adapter=str(creator), label=label)
    return _save_selection(root, configuration,
                           _selection(kind, label, creator, reviewer, root))


def configure(root, configuration, provider=None, role="work"):
    from . import development_console as ui
    if role not in ("work", "reflection"):
        raise LedgerError("ARGUMENTS")
    if provider is None:
        provider = ui._pick("Connect your own subscription", list(LABELS), LABELS.get)
    if provider is None:
        return
    if provider not in LABELS:
        raise LedgerError("ARGUMENTS")
    model = "default"
    while True:
        print("\nACCOUNTS / " + LABELS[provider])
        print("No API key or token is stored in this project. The official CLI owns authentication.")
        print("This connection uses native account login, not API-key environment variables.")
        print("Account limits and extra-usage billing remain controlled by the provider.")
        executable = find_executable(provider)
        if executable is None:
            print("The official CLI was not found on this Mac.")
            choice = ui._pick("Install or use an existing CLI",
                              ["install", "docs", "retry"],
                              lambda key: {"install": "Install the official CLI (confirmation next)",
                                           "docs": "Open official installation instructions",
                                           "retry": "Check again after installation"}[key])
            if choice is None:
                return
            if choice == "docs":
                webbrowser.open(DOCS[provider])
            elif choice == "install":
                _confirm_native(root, configuration, provider,
                                ["/bin/bash", "-o", "pipefail", "-c", INSTALLERS[provider]], "installation")
            continue
        print("Executable: " + terminal_text(executable))
        login = status(provider, executable)
        print("Account: " + login["state"])
        print("Selected model: " + model + " / access is not tested during setup")
        actions = (["use", "model"] if login["subscription_login"] else []) + ["login"]
        if provider == "codex":
            actions.append("device")
        actions += ["retry", "docs"]
        labels = {
            "use": "Use this account / save as " + ("Reflection AI" if role == "reflection" else "Work AI"),
            "model": "Choose a model ID or alias (optional)",
            "login": "Sign in with your subscription / browser",
            "device": "Sign in with a device code (Codex)",
            "retry": "Check account again",
            "docs": "Open official setup instructions",
        }
        action = ui._pick("Choose the next step", actions, labels.get)
        if action is None:
            return
        if action == "use":
            ui._mutate(root, configuration, _save_connection,
                       provider, executable, model, role)
            print("Connection saved. No work prompt or test generation was sent.")
            print("The official CLI reports account login; plan capacity and model response are not verified.")
            print("Reflection keeps its existing setting; Same as Work AI follows this choice.")
            return
        if action == "model":
            candidate = ui._ask("Model ID / alias; default uses the CLI default", model)
            try:
                validate_model(candidate)
                model = candidate
            except LedgerError:
                print("Use a model ID or alias without spaces, not a command or API key.")
        elif action in ("login", "device"):
            arguments = [executable, "login"] if provider == "codex" else [executable, "auth", "login"]
            if action == "device":
                arguments.append("--device-auth")
                print("Device-code login must be enabled for your OpenAI account or workspace.")
            _confirm_native(root, configuration, provider, arguments, "sign-in")
        elif action == "docs":
            webbrowser.open(DOCS[provider])
