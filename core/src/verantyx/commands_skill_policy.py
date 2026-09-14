"""CLI for explicit human policies and model-free verification-contract reuse."""
COMMANDS = {"skills-policies", "skills-policy-set", "skills-route", "skills-reuse"}


def register(sub):
    parser = sub.add_parser("skills-policies", add_help=False, allow_abbrev=False)
    parser.add_argument("--run")
    parser = sub.add_parser("skills-policy-set", add_help=False, allow_abbrev=False)
    parser.add_argument("run_id")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--ai-mode", choices=("explain", "propose", "check"), required=True)
    parser.add_argument("--reuse-mode", choices=("confirm", "assisted", "auto-check"), required=True)
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--asset", action="append", default=[])
    parser.add_argument("--reason", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--expected-policy-revision", type=int, required=True)
    for command in ("skills-route", "skills-reuse"):
        parser = sub.add_parser(command, add_help=False, allow_abbrev=False)
        parser.add_argument("run_id")
        parser.add_argument("--candidate", required=True)
        parser.add_argument("--asset", required=True)
        parser.add_argument("--claim", required=True)
        parser.add_argument("--target", required=True)
        if command == "skills-reuse":
            parser.add_argument("--scope-id", required=True)
            parser.add_argument("--key", required=True)
            parser.add_argument("--execute", action="store_true")
            parser.add_argument("--confirm-scope")
            parser.add_argument("--judgment-reason")


def dispatch(root, configuration, args, locale):
    from . import skill_policy
    if args.command == "skills-policies":
        current = skill_policy.policy_snapshot(root, configuration)
        return {"ok": True, "command": args.command, "revision": current["revision"],
                "policies": [row for row in current["policies"] if args.run is None or row["run_id"] == args.run],
                "model_calls": 0, "writes": False}
    if args.command == "skills-policy-set":
        return skill_policy.set_policy(root, configuration, args.run_id, candidate_id=args.candidate,
            ai_mode=args.ai_mode, reuse_mode=args.reuse_mode, paths=args.path, asset_ids=args.asset,
            reason=args.reason, key=args.key, expected_policy_revision=args.expected_policy_revision)
    values = {"candidate_id": args.candidate, "asset_id": args.asset,
              "claim_id": args.claim, "target_path": args.target}
    if args.command == "skills-route":
        return skill_policy.route(root, configuration, args.run_id, **values)
    return skill_policy.reuse(root, configuration, args.run_id, **values, scope_id=args.scope_id,
        key=args.key, execute=args.execute, confirm_scope=args.confirm_scope, judgment_reason=args.judgment_reason)


def display(result, locale, command):
    from .cli import visible
    if command == "skills-policies":
        print("Skill policy revision: " + str(result["revision"]))
        for row in result["policies"]:
            print(visible(row["run_id"]) + " / " + visible(row["candidate_id"]))
            print("  " + row["ai_mode"] + " / " + row["reuse_mode"] + " / " + row["policy_id"])
            print("  " + visible(row["reason"]))
        print("Learning ownership and permission to execute are separate.")
    elif command == "skills-policy-set":
        print("Policy recorded: " + result["policy_id"])
        print("revision=" + str(result["recorded_revision"]) + " / execution_authorized=False")
    elif "workflow_id" in result:
        print("Workflow: " + visible(result["workflow_id"]) + " / " + visible(result["workflow"]["status"]))
        print("model_calls=0 / source_method_rewritten=False")
        print(result["boundary"])
    else:
        print(result["status"] + ": " + result["reason"])
        if result.get("scope"):
            print("scope: " + result["scope"]["id"])
            print("asset: " + visible(result["scope"]["asset_id"]))
            print("target: " + visible(result["scope"]["target_path"]))
            print("claim: " + visible(result["scope"]["claim_id"]))
            print("No checks have been executed by this preview.")
