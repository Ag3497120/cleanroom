"""Opt-in Codex role configurations and a read-only shared call-budget report."""
from pathlib import Path

from . import codex_budget
from .codex_cli import MODEL, ROLES, configuration
from .domain.codec import canonical
from .errors import LedgerError

COMMANDS = {"codex-config", "codex-usage"}
READ_COMMANDS = {"codex-usage"}


def register(sub):
    create = sub.add_parser("codex-config", add_help=False, allow_abbrev=False)
    create.add_argument("--directory", required=True)
    create.add_argument("--max-calls", type=int, default=4)
    usage = sub.add_parser("codex-usage", add_help=False, allow_abbrev=False)
    usage.add_argument("--directory", required=True)


def create_configs(directory, max_calls=4, model=MODEL, executable=None):
    codex_budget.validate_cap(max_calls)
    directory = Path(directory).expanduser()
    if directory.is_symlink():
        raise LedgerError("BRIDGE_CONFIG", {"reason": "CODEX_CONFIG_DIRECTORY"})
    directory = directory.resolve()
    files = {role: directory / (role + ".json") for role in ROLES}
    if any(path.exists() or path.is_symlink() for path in (*files.values(), directory / "budget")):
        raise LedgerError("OUTPUT_EXISTS")
    values = {role: configuration(directory, role, max_calls, model=model, executable=executable)
              for role in ROLES}
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    # No reopen/reset on failure: partial creation remains visible for review.
    codex_budget.initialize(directory / "budget", max_calls)
    for role, path in files.items():
        with path.open("x", encoding="utf-8") as handle:
            handle.write(canonical(values[role]) + "\n")
    return {"schema_version": 1, "ok": True, "command": "codex-config", "directory": str(directory),
            "adapters": {role: str(path) for role, path in files.items()},
            "budget": codex_budget.usage(directory / "budget")}


def dispatch(root, configuration, args, locale):
    if args.command == "codex-config":
        return create_configs(args.directory, args.max_calls)
    if args.command != "codex-usage":
        raise LedgerError("ARGUMENTS")
    return {"schema_version": 1, "ok": True, "command": "codex-usage",
            "budget": codex_budget.usage(Path(args.directory).expanduser() / "budget")}


def display(result, locale, command):
    from .cli import visible
    budget = result["budget"]
    print("ChatGPT Codex / " + MODEL + " / low")
    for role, path in result.get("adapters", {}).items():
        print(role + ": " + visible(path))
    print("Recorded calls: " + str(budget["calls_reserved"]) + " / 独自の生成回数上限なし")
    for row in budget["calls"]:
        print(visible(str(row["id"]) + " " + row["role"] + " " + row["status"]
                      + " request=" + row["request_sha256"]))
    print("Provider-reported tokens: " + visible(canonical(budget["provider_reported_tokens"])))
    print("Calls without token usage: " + str(budget["calls_without_token_usage"]))
    print(budget["boundary"])
