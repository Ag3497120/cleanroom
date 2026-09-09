"""CLI operations for reviewed finite policies and actual task shadow history."""
COMMANDS = {"rule-policy-template", "rule-policy-propose", "rule-policy-accept", "rule-policy-confirm",
            "rule-enforce", "rule-shadow-report"}


def register(sub):
    for command in sorted(COMMANDS):
        parser = sub.add_parser(command, add_help=False, allow_abbrev=False)
        parser.add_argument("rule_id")
        if command not in ("rule-policy-template", "rule-shadow-report"):
            parser.add_argument("--key", required=True)
            parser.add_argument("--reason", required=True)
            parser.add_argument("--expected-revision", type=int)
        if command == "rule-policy-propose":
            parser.add_argument("--policy", required=True)
        if command in ("rule-policy-accept", "rule-policy-confirm", "rule-enforce"):
            parser.add_argument("--expected-policy-sha256", required=command != "rule-enforce")
        if command == "rule-enforce":
            parser.add_argument("--enforcement", choices=("WARN", "BLOCK"), required=True)
        if command == "rule-policy-template":
            parser.add_argument("--minimum-shadow-tasks", type=int, default=2)


def dispatch(root, configuration, args, locale):
    from .storage.sqlite import EventStore
    from .governance import control, policy_report
    from .domain.rule_extensions import exact_policy, validate_policy
    from .domain.codec import decode
    from .adapters.observations import read_document
    with EventStore(root, configuration["project"]["id"], create=True) as store:
        if args.command in ("rule-shadow-report", "rule-policy-template"):
            result = policy_report(store, args.rule_id)
            if args.command == "rule-policy-template":
                return validate_policy(exact_policy(result["rule"]["scope"], args.minimum_shadow_tasks), result["rule"]["scope"])
            return result
        keywords = {key: getattr(args, key, None) for key in ("key", "reason", "expected_revision", "expected_policy_sha256", "enforcement")}
        if args.command == "rule-policy-propose":
            keywords["policy"] = decode(read_document(args.policy, 128 * 1024))
        return control(store, configuration, args.command, args.rule_id, **keywords)


def display(result, locale, command):
    from .i18n import text
    from .cli import visible
    import json
    if command == "rule-policy-template":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(text(locale, "governance.title"))
    print(result["rule_id"])
    if result.get("duplicate"):
        print(text(locale, "ledger.duplicate"))
    rule = result["rule"]
    print(text(locale, "governance.enforcement." + rule["enforcement"]))
    if result.get("policy_sha256"):
        print(text(locale, "governance.hash", sha256=result["policy_sha256"]))
    if command == "rule-policy-propose":
        print(text(locale, "governance.proposal"))
        print(json.dumps(rule["policy_proposal"]["policy"], ensure_ascii=False, indent=2))
    elif command == "rule-policy-accept":
        print(text(locale, "governance.accepted"))
    elif command == "rule-shadow-report":
        print(text(locale, "governance.samples", observations=len(result["observations"]), tasks=result["distinct_tasks"]))
        for outcome, count in sorted(result["outcomes"].items()):
            print(text(locale, "governance.outcome." + outcome) + ": " + str(count))
        for row in result["observations"][-20:]:
            print(visible(row["run_id"]) + ": " + text(locale, "governance.outcome." + row["outcome"]) + " [" + row["source_ref"] + "]")
        if len(result["observations"]) > 20:
            print(text(locale, "governance.recent"))
    print(text(locale, "governance.boundary"))


def display_advisories(judgments, locale):
    from .i18n import text
    from .cli import visible
    for judgment in judgments:
        for row in judgment.get("advisories", []):
            if row["outcome"] == "OUT_OF_SCOPE":
                continue
            print(text(locale, "governance.advisory", mode=text(locale, "governance.enforcement." + row["enforcement"]),
                       choice=visible(row["choice"]), outcome=text(locale, "governance.outcome." + row["outcome"])))
