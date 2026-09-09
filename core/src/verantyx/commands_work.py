"""A reviewable candidate, one explicit execution, then three recorded deltas."""
COMMANDS = {"work", "sovereignty"}


def register(sub):
    work = sub.add_parser("work", add_help=False, allow_abbrev=False)
    work.add_argument("run_id")
    work.add_argument("--key", required=True)
    work.add_argument("--expected-revision", type=int, required=True)
    work.add_argument("--action")
    work.add_argument("--execute", action="store_true")
    work.add_argument("--precedent")
    work.add_argument("--adapter")
    work.add_argument("--refresh", action="store_true")
    work.add_argument("--editor-adapter")
    work.add_argument("--include", action="append", default=[])
    work.add_argument("--max-repairs", type=int, choices=(0, 1, 2), default=1)
    work.add_argument("--timeout", type=int, default=60)
    sub.add_parser("sovereignty", add_help=False, allow_abbrev=False)


def dispatch(root, configuration, args, locale):
    if args.command == "sovereignty":
        from .sovereignty import report
        return report(root, configuration)
    from .work_loop import run_candidate
    return run_candidate(root, configuration, args.run_id, key=args.key, expected_revision=args.expected_revision,
                         action_id=args.action, execute=args.execute, precedent_path=args.precedent,
                         adapter_path=args.adapter, timeout=args.timeout, locale=locale, refresh=args.refresh,
                         editor_adapter=args.editor_adapter, include_paths=args.include, max_repairs=args.max_repairs)


def display_work(outcome, locale):
    from .cli import visible
    from .i18n import text
    print(text(locale, "work.status", status=outcome["status"]))
    if outcome.get("worktree"):
        print(text(locale, "effect.path", path=visible(outcome["worktree"])))
    if outcome.get("evidence"):
        print("BUILD: " + outcome["build"] + "  EVIDENCE: " + outcome["evidence"]
              + "  OWNERSHIP: " + outcome["ownership"])
    for row in outcome.get("files", []):
        print("  " + visible(row["path"]))
    if outcome.get("tests"):
        print(text(locale, "work.tests", tests=", ".join(map(visible, outcome["tests"]))))
    if outcome.get("reason"):
        print(text(locale, "error." + outcome["reason"]))


def display(result, locale, command):
    from .i18n import text
    if command == "sovereignty":
        print(text(locale, "sovereignty.title"))
        for name, value in result["metrics"].items():
            print(text(locale, "sovereignty." + name) + ": " + str(value))
        print(text(locale, "sovereignty.boundary"))
        return
    from .commands_response import display as display_response
    display_response(result, locale, command)
    display_work(result["work_loop"], locale)
