"""Explicit integration commands; provider text never becomes authorization."""
import json
from .errors import LedgerError

COMMANDS = ("connections", "skill-import", "model-roles", "handoff", "mcp")


def register(sub):
    notebook = sub.add_parser("connections", help="Local notebook or Obsidian-first workflow")
    notebook.add_argument("action", nargs="?", default="menu", choices=("menu", "status", "connect", "sync"))
    notebook.add_argument("--vault")
    notebook.add_argument("--auto", action="store_true")
    notebook.add_argument("--yes", action="store_true")
    notebook.add_argument("--include-private", action="store_true")
    importer = sub.add_parser("skill-import", help="Import passive skill text without inferring mastery")
    importer.add_argument("path")
    importer.add_argument("--origin", required=True)
    importer.add_argument("--title", default="Imported skill")
    importer.add_argument("--technology", action="append", default=[])
    importer.add_argument("--yes", action="store_true")
    roles = sub.add_parser("model-roles", help="Owner-selected parent and advisory child models")
    roles.add_argument("action", nargs="?", default="show", choices=("show", "register", "set", "menu"))
    roles.add_argument("--alias")
    roles.add_argument("--adapter")
    roles.add_argument("--role", choices=("parent", "child"))
    roles.add_argument("--yes", action="store_true")
    handoff = sub.add_parser("handoff", help="Loss-aware model handoff from recorded work")
    handoff.add_argument("run_id")
    handoff.add_argument("--budget", type=int, default=60000)
    mcp = sub.add_parser("mcp", help="Optional stdio MCP notebook server")
    mcp.add_argument("--allow-personal", action="store_true")
    mcp.add_argument("--allow-import", action="store_true")


def dispatch(root, configuration, args):
    from . import notebook_bridge as bridge
    from . import model_roles as roles
    if args.command == "connections":
        if args.action == "menu":
            from .bridge_console import menu
            menu(root, configuration)
            return {"status": "CLOSED"}
        if args.action == "status":
            value = bridge.settings()
            return {"enabled": value.get("enabled", False), "auto_sync": value.get("auto_sync", False),
                    "vault": value.get("path"), "obsidian_url": bridge.link(), "read_only": True}
        if args.action == "connect":
            if not args.vault:
                raise LedgerError("ARGUMENTS")
            return bridge.connect(args.vault, confirmed=args.yes, include_private=args.include_private, auto=args.auto)
        if not args.yes:
            raise LedgerError("VAULT_EXPORT_APPROVAL_REQUIRED")
        return bridge.sync()
    if args.command == "skill-import":
        return bridge.import_file(args.path, origin=args.origin, title=args.title,
                                  technologies=args.technology, confirmed=args.yes)
    if args.command == "model-roles":
        if configuration is None:
            raise LedgerError("PROJECT_REQUIRED")
        if args.action == "show":
            return roles.load(root)
        if args.action == "menu":
            roles.menu(root, configuration)
            return {"status": "CLOSED"}
        if args.action == "register":
            if not args.alias or not args.adapter:
                raise LedgerError("ARGUMENTS")
            return roles.register(root, configuration, args.alias, args.adapter, confirmed=args.yes)
        return roles.choose(root, configuration, args.role, args.alias, confirmed=args.yes)
    if args.command == "handoff":
        if configuration is None:
            raise LedgerError("PROJECT_REQUIRED")
        from .context_handoff import build
        return build(root, configuration, args.run_id, budget=args.budget)
    raise LedgerError("ARGUMENTS")
