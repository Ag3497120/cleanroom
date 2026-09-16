"""Discoverable command catalogue and explicitly trusted external tool connections."""
from .errors import LedgerError

COMMANDS = ("commands", "toolbox")


def catalogue(sub):
    return [{"command": name, "usage": parser.format_usage().strip(),
             "arguments": [{"name": action.dest, "flags": action.option_strings,
                            "required": action.required,
                            "choices": list(action.choices) if action.choices is not None else None}
                           for action in parser._actions if action.dest != "help"]}
            for name, parser in sorted(sub.choices.items())]


def register(sub):
    command = sub.add_parser("commands", help="List real commands and their arguments")
    command.add_argument("name", nargs="?")
    toolbox = sub.add_parser("toolbox", help="Owner-approved MCP and sandboxed check tools")
    toolbox.add_argument("action", choices=("status", "configure", "list", "call"))
    toolbox.add_argument("--file")
    toolbox.add_argument("--server")
    toolbox.add_argument("--tool")
    toolbox.add_argument("--arguments", default="{}")
    toolbox.add_argument("--yes", action="store_true")


def dispatch(root, configuration, args):
    from . import work_tools as tools
    from .adapters.observations import read_document
    from .domain.codec import decode
    if args.action == "status":
        return {"ok": True, **tools.ToolSession(root).describe()}
    if configuration is None:
        raise LedgerError("NOT_CONFIGURED")
    if args.action == "configure":
        if not args.file:
            raise LedgerError("ARGUMENTS")
        return tools.configure(root, decode(read_document(args.file, 131072), 131072), confirmed=args.yes)
    if not args.yes:
        raise LedgerError("TOOLBOX_APPROVAL_REQUIRED")
    request = {"id": "owner-call", "tool": "list_mcp_tools" if args.action == "list" else "call_mcp",
               "path": (args.server or "") + ("/" + (args.tool or "") if args.action == "call" else ""),
               "text": args.arguments if args.action == "call" else ""}
    import uuid
    with tools.session(root) as runtime:
        return {"ok": True, "receipt": runtime.execute(request, run_id="owner-" + uuid.uuid4().hex,
                                                       turn=0, scope=[], artifacts={})}
