"""Discoverable command catalogue and explicitly trusted external tool connections."""
from .errors import LedgerError

COMMANDS = ("commands", "toolbox", "web-search", "web-fetch", "model-usage", "context-usage")


def catalogue(sub):
    return [{"command": name, "usage": parser.format_usage().strip(),
             "arguments": [{"name": action.dest, "flags": action.option_strings,
                            "required": action.required,
                            "choices": list(action.choices) if action.choices is not None else None}
                           for action in parser._actions if action.dest != "help"]}
            for name, parser in sorted(sub.choices.items())]


def register(sub):
    sub.add_parser("context-usage", help="Read prepared request composition without a model call")
    sub.add_parser("model-usage", help="Read reported model/cache usage without making a model call")
    command = sub.add_parser("commands", help="List real commands and their arguments")
    command.add_argument("name", nargs="?")
    toolbox = sub.add_parser("toolbox", help="Owner-approved MCP and sandboxed check tools")
    toolbox.add_argument("action", choices=("status", "configure", "setup-web", "list", "call"))
    toolbox.add_argument("--browser", action="store_true", help="Build the optional macOS WebKit reader")
    toolbox.add_argument("--file")
    toolbox.add_argument("--server")
    toolbox.add_argument("--tool")
    toolbox.add_argument("--arguments", default="{}")
    toolbox.add_argument("--yes", action="store_true")
    search = sub.add_parser("web-search", help="Search the web using the built-in, key-free Web MCP")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5, choices=range(1, 11))
    fetch = sub.add_parser("web-fetch", help="Read a public web page")
    fetch.add_argument("url")
    fetch.add_argument("--browser", action="store_true", help="Use the optional macOS WebKit reader")


def dispatch(root, configuration, args):
    from . import work_tools as tools
    from .adapters.observations import read_document
    from .domain.codec import decode
    if args.command == "context-usage":
        from .context_meter import read
        return {"ok": True, "composition": read(root), "model_calls": 0}
    if args.command == "model-usage":
        from .model_usage import summary
        return summary(root)
    if args.command in ("web-search", "web-fetch"):
        return call_web(root, configuration, "web_search" if args.command == "web-search" else
                        "browser_read" if args.browser else "web_fetch",
                        {"query": args.query, "limit": args.limit} if args.command == "web-search" else {"url": args.url})
    if args.action == "status":
        return {"ok": True, **tools.ToolSession(root).describe()}
    if configuration is None:
        raise LedgerError("NOT_CONFIGURED")
    if args.action == "setup-web":
        from .web_mcp import setup
        from .web_tools import WebError
        try:
            return setup(root, configuration, browser=args.browser, confirmed=args.yes)
        except WebError as error:
            raise LedgerError(error.code, {"message": str(error)}) from None
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


def call_web(root, configuration, tool, arguments):
    import json
    import uuid
    from . import work_tools
    with work_tools.session(root) as runtime:
        if tool not in runtime.settings["mcp_servers"].get("web", {}).get("tools", []):
            raise LedgerError("WEB_TOOLS_NOT_CONFIGURED", {
                "setup": "verantyx toolbox setup-web " + ("--browser " if tool == "browser_read" else "") + "--yes"})
        receipt = runtime.execute({"id": "owner-web", "tool": "call_mcp", "path": "web/" + tool,
                                   "text": json.dumps(arguments, ensure_ascii=False)},
                                  run_id="owner-" + uuid.uuid4().hex, turn=0, scope=[], artifacts={})
    blocks = receipt.get("content", [])
    text = next((row["text"] for row in blocks if row.get("type") == "text"), "")
    try:
        result = json.loads(text)
    except ValueError:
        result = {"ok": False, "error": "WEB_TOOL_ERROR", "message": text or "No response"}
    return {"ok": bool(result.get("ok")), "result": result, "receipt": receipt}
