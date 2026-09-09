"""Compile and reuse finite file checks through the existing verifier."""

COMMANDS = {"asset-loop"}


def register(sub):
    parser = sub.add_parser("asset-loop", add_help=False, allow_abbrev=False)
    parser.add_argument("run_id")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--adapter")
    source.add_argument("--asset", dest="reuse_asset")
    parser.add_argument("--claim", dest="claim_id")
    parser.add_argument("--target", dest="target_path")
    parser.add_argument("--key", required=True)
    parser.add_argument("--expected-revision", type=int)
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--max-rounds", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--max-checks", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--preview", action="store_true")


def dispatch(root, configuration, args, locale):
    from .asset_workflow import run_asset_workflow
    return run_asset_workflow(root, configuration, args.run_id, adapter_path=args.adapter, key=args.key,
                              expected_revision=args.expected_revision, include_paths=args.include,
                              timeout=args.timeout, max_rounds=args.max_rounds, max_checks=args.max_checks,
                              execute=not args.preview, reuse_asset=args.reuse_asset,
                              claim_id=args.claim_id, target_path=args.target_path)


def display(result, locale, command):
    from .cli import visible
    from .i18n import text
    from .presentation import display_reply
    from .workflow_presentation import lines
    state = result["state"]
    print(text(locale, "ledger.run", run=visible(state["run_id"]), revision=state["revision"]))
    print(text(locale, "workflow.title"))
    for line in lines(state, locale):
        print(line)
    display_reply(state, locale)
