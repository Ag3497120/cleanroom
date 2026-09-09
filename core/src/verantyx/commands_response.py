"""An ordinary question-to-answer workflow and project experience dictionary."""
COMMANDS = {"ask", "respond", "dictionary", "asset-template"}


def register(sub):
    ask = sub.add_parser("ask", add_help=False, allow_abbrev=False)
    ask.add_argument("request")
    ask.add_argument("--task-id", dest="run_id")
    ask.add_argument("--adapter", required=True)
    ask.add_argument("--key", required=True)
    ask.add_argument("--include", action="append", default=[])
    ask.add_argument("--component", default="UNSPECIFIED")
    ask.add_argument("--workload", default="UNSPECIFIED")
    ask.add_argument("--risk", choices=("LOW", "MEDIUM", "HIGH", "UNSPECIFIED"), default="UNSPECIFIED")
    ask.add_argument("--timeout", type=int, default=60)
    ask.add_argument("--without-assets", action="store_true")
    ask.add_argument("--continue-from")
    ask.add_argument("--original-request")
    ask.add_argument("--editor-adapter")
    ask.add_argument("--proposal-only", action="store_true")
    ask.add_argument("--max-repairs", type=int, choices=(0, 1, 2), default=1)
    ask.add_argument("--auto-check", action="store_true")
    ask.add_argument("--execute-candidate", action="store_true")
    ask.add_argument("--precedent")
    ask.add_argument("--check-rounds", type=int, choices=(1, 2, 3), default=2)
    ask.add_argument("--max-checks", type=int, choices=range(1, 9), default=4)
    respond = sub.add_parser("respond", add_help=False, allow_abbrev=False)
    respond.add_argument("run_id")
    respond.add_argument("--adapter")
    respond.add_argument("--key", required=True)
    respond.add_argument("--expected-revision", type=int, required=True)
    respond.add_argument("--timeout", type=int, default=60)
    respond.add_argument("--without-assets", action="store_true")
    dictionary = sub.add_parser("dictionary", add_help=False, allow_abbrev=False)
    dictionary.add_argument("query", nargs="?")
    dictionary.add_argument("--run", dest="run_id")
    dictionary.add_argument("--limit", type=int, default=24)
    template = sub.add_parser("asset-template", add_help=False, allow_abbrev=False)
    template.add_argument("asset_id")
    template.add_argument("--claim", required=True)
    template.add_argument("--target", required=True)
    template.add_argument("--oracle-source-ref", action="append", default=[])
    template.add_argument("--reproduces")
    template.add_argument("--output")


def dispatch(root, configuration, args, locale):
    from .responses import ask, compose
    if args.command == "ask":
        return ask(root, configuration, request=args.request, adapter_path=args.adapter, key=args.key, run_id=args.run_id,
                   include_paths=args.include, locale=locale,
                   context={key: getattr(args, key) for key in ("component", "workload", "risk")},
                   reuse_assets=not args.without_assets, timeout=args.timeout, continue_from=args.continue_from,
                   original_request=args.original_request, editor_adapter=args.editor_adapter, max_repairs=args.max_repairs,
                   auto_check=args.auto_check, check_rounds=args.check_rounds, max_checks=args.max_checks,
                   execute_candidate=args.execute_candidate, precedent_path=args.precedent, proposal_only=args.proposal_only)
    if args.command == "respond":
        return compose(root, configuration, args.run_id, adapter_path=args.adapter, key=args.key,
                       expected_revision=args.expected_revision, locale=locale, timeout=args.timeout,
                       reuse_assets=not args.without_assets)
    from .application import get_projection, write_new_output
    from .assets import project_catalog, verification_template_from_asset
    from .domain.codec import canonical
    from .storage.sqlite import EventStore
    with EventStore(root, configuration["project"]["id"]) as store:
        if args.command == "dictionary":
            state = get_projection(store, args.run_id)["state"] if args.run_id else None
            return {"schema_version": 1, "ok": True, "command": args.command,
                    "catalog": project_catalog(store, state, locale, query=args.query, limit=args.limit)}
        value = verification_template_from_asset(store, args.asset_id, claim_id=args.claim, target_path=args.target,
                                                oracle_source_refs=args.oracle_source_ref, reproduces=args.reproduces)
    if args.output:
        write_new_output(root, args.output, (canonical(value["spec"]) + "\n").encode())
    return {"schema_version": 1, "ok": True, "command": args.command, "output": args.output, "template": value}


def display(result, locale, command):
    from .cli import visible
    from .i18n import text
    if "state" in result:
        from .presentation import display_reply
        state = result["state"]
        print(text(locale, "ledger.run", run=visible(state["run_id"]), revision=state["revision"]))
        display_reply(state, locale)
        from .workflow_presentation import lines
        for line in lines(state, locale):
            print(line)
        if result.get("work_loop") and command == "ask":
            from .commands_work import display_work
            display_work(result["work_loop"], locale)
        human = state.get("deltas", {}).get("human_delta", [])
        if human:
            print(text(locale, "response.learning"))
            for item in human:
                print("  " + visible(item["concept"]) + "  (" + item["id"] + ")")
        print(text(locale, "response.next", run=visible(state["run_id"])))
    elif command == "dictionary":
        print(text(locale, "response.dictionary"))
        catalog = result["catalog"]
        # The catalog remains structured JSON for automation; show only the
        # compact, human-readable fields in the ordinary dictionary view.
        for section in ("rules", "verification_methods", "execution_methods", "failure_cases", "reuse_candidates", "learning"):
            if catalog.get(section):
                print(text(locale, "response.section." + section))
            for item in catalog.get(section, []):
                print(visible(str(item.get("title") or item.get("concept") or item.get("name") or item.get("decision_type") or item.get("id"))))
                for key in ("description", "why_now", "summary"):
                    if item.get(key):
                        print("  " + visible(str(item[key])))
                print("  " + str(item.get("id", "")))
                if item.get("owner_run"):
                    print("  " + text(locale, "response.owner_run", run=visible(item["owner_run"])))
        if any(catalog.get("truncated", {}).values()):
            print(text(locale, "response.more"))
    else:
        if result.get("output"):
            print(visible(result["output"]))
        else:
            from .cli import emit
            emit(result["template"])
