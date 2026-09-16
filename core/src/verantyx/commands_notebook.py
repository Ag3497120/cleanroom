"""Discoverable CLI access to provenance and explicitly approved checks."""
COMMANDS = {"notebook", "perspectives", "check"}


def register(sub):
    notebook = sub.add_parser("notebook", add_help=False, allow_abbrev=False)
    notebook.add_argument("run_id", nargs="?")
    perspective = sub.add_parser("perspectives", add_help=False, allow_abbrev=False)
    perspective.add_argument("run_id")
    check = sub.add_parser("check", add_help=False, allow_abbrev=False)
    check.add_argument("run_id")
    check.add_argument("--label", default="Candidate check")
    check.add_argument("--timeout", type=int, default=120)
    check.add_argument("--key")
    check.add_argument("--confirm", action="store_true")
    # Pass a JSON argv array so global CLI options cannot consume child flags.
    check.add_argument("--argv", required=True)


def dispatch(root, configuration, args, locale):
    if args.command == "check":
        import json
        from .errors import LedgerError
        from .work_checks import run_check
        try:
            argv = json.loads(args.argv)
        except (ValueError, TypeError):
            raise LedgerError("ARGUMENTS") from None
        return run_check(root, configuration, args.run_id, argv=argv, label=args.label,
                         timeout=args.timeout, key=args.key, confirmed=args.confirm)
    from .provenance import notebook, perspectives
    if args.command == "notebook":
        return notebook(root, configuration, args.run_id)
    from .agent_runtime import _state
    state = _state(root, configuration, args.run_id)
    return {"schema_version": 1, "ok": True, "command": "perspectives", "run_id": args.run_id,
            "perspectives": perspectives(state), "model_calls": 0, "writes": False,
            "agreement_required": False}


def display(result, locale, command):
    from .agent_console import terminal_text
    if command == "check":
        row = result["check"]
        print("CHECK / " + row["status"])
        print("Saved candidate copy only. Not proof of overall correctness or adoption.")
        print("Exit: " + str(row["exit_code"]) + " / " + str(row["elapsed_ms"]) + " ms")
        if row["reason"]:
            print("Reason: " + terminal_text(row["reason"]))
        for key in ("stdout", "stderr"):
            if row[key]:
                print(key + ":\n" + terminal_text(row[key]))
        if row["output_truncated"]:
            print("Output was truncated; the command status is recorded separately.")
        print("Source: " + row["source_ref"])
    elif command == "perspectives":
        print("PERSPECTIVES / Different answers may coexist")
        for row in result["perspectives"]:
            print(terminal_text(row["id"] + " / " + row["model"]["model"] + " / " + row["status"]))
            print(terminal_text(row["perspective"] or "Open perspective"))
            for item in row["owner_items"]:
                print("  " + terminal_text(item["kind"] + ": " + item["text"]))
    else:
        print("NOTEBOOK / " + terminal_text(result["project"]["name"]))
        print("Purpose: " + terminal_text(result["project"]["purpose"]))
        for row in result["active_decisions"]:
            print("Human decision: " + terminal_text(row["statement"]))
        for row in result["works"]:
            print(terminal_text(row["run_id"] + " / " + row["request"][:160]))
        print("Perspectives: " + str(sum(len(row["revisions"]) for row in result["perspectives"])))
        print("Recorded checks: " + str(len(result["check_receipts"])))
        print("No understanding score. These are records, not a mastery assessment.")
