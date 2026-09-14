"""CLI access to local project constitutions and judgment gaps."""

from . import constitution


COMMANDS = {"constitution", "constitution-set", "constitution-gaps", "constitution-resolve"}


def register(sub):
    sub.add_parser("constitution", add_help=False, allow_abbrev=False)
    parser = sub.add_parser("constitution-set", add_help=False, allow_abbrev=False)
    parser.add_argument("--purpose", required=True)
    parser.add_argument("--non-negotiable", action="append", default=[])
    parser.add_argument("--human-decision", action="append", default=[])
    sub.add_parser("constitution-gaps", add_help=False, allow_abbrev=False)
    parser = sub.add_parser("constitution-resolve", add_help=False, allow_abbrev=False)
    parser.add_argument("gap_id")
    parser.add_argument("--reason", required=True)


def dispatch(root, configuration, args, locale=None):
    if args.command == "constitution":
        return {"ok": True, "command": args.command, "constitution": constitution.snapshot(root, configuration)}
    if args.command == "constitution-set":
        return {"ok": True, "command": args.command, "constitution": constitution.set_constitution(
            root, configuration, purpose=args.purpose, non_negotiables=args.non_negotiable,
            human_owned_decisions=args.human_decision)}
    if args.command == "constitution-gaps":
        return {"ok": True, "command": args.command, "gaps": constitution.gaps(root)}
    if args.command == "constitution-resolve":
        return {"ok": True, "command": args.command,
                "result": constitution.resolve_gap(root, args.gap_id, args.reason)}
    raise ValueError("unsupported constitution command")


def display(result, locale, command):
    from .cli import visible
    if command == "constitution":
        value = result["constitution"]
        print("PROJECT CONSTITUTION")
        print("目的: " + visible(value.get("purpose") or "未記録"))
        print("版: " + str(value["revision"]) + " / " + value["source"])
        for item in value.get("non_negotiables", []):
            print("守る条件: " + visible(item))
        for item in value.get("human_owned_decisions", []):
            print("人間が決めること: " + visible(item))
    elif command == "constitution-set":
        value = result["constitution"]
        print("PROJECT CONSTITUTION SAVED: revision " + str(value["revision"]))
    elif command == "constitution-gaps":
        print("JUDGMENT GAPS: " + str(len(result["gaps"])))
        for gap in result["gaps"]:
            print(gap["status"] + " " + visible(gap["gap_id"]) + " / " + visible(gap.get("question") or ""))
    elif command == "constitution-resolve":
        print("JUDGMENT GAP: " + result["result"]["status"])
