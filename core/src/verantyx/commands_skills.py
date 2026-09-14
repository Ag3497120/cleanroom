"""Personal skill library CLI; ordinary project-ledger and authority paths."""
COMMANDS = {"skills-import", "skills-build", "skills-stack", "skills-newsletter", "skills-explain"}


def register(sub):
    import_parser = sub.add_parser("skills-import", add_help=False, allow_abbrev=False)
    import_parser.add_argument("--input", required=True)
    import_parser.add_argument("--origin-project", required=True)
    import_parser.add_argument("--label", required=True)
    import_parser.add_argument("--provider", required=True)
    import_parser.add_argument("--model", required=True)
    import_parser.add_argument("--format", dest="content_format", choices=("text", "json"), default="text")
    import_parser.add_argument("--mode", choices=("auto", "assisted", "manual"), default="assisted")
    import_parser.add_argument("--key", required=True)
    build_parser = sub.add_parser("skills-build", add_help=False, allow_abbrev=False)
    build_parser.add_argument("run_id")
    build_parser.add_argument("--key", required=True)
    build_parser.add_argument("--expected-revision", type=int)
    for parser in (import_parser, build_parser):
        parser.add_argument("--creator-adapter", required=parser is build_parser)
        parser.add_argument("--reviewer-adapter", required=parser is build_parser)
        parser.add_argument("--timeout", type=int, default=120)
    for name in ("skills-stack", "skills-newsletter"):
        parser = sub.add_parser(name, add_help=False, allow_abbrev=False)
        parser.add_argument("--run", dest="run_ids", action="append", default=[], required=name == "skills-newsletter")
        parser.add_argument("--limit", type=int, default=24)
        if name == "skills-stack":
            parser.add_argument("--query")
            parser.add_argument("--target", choices=("OWN", "REVIEW", "REFERENCE", "DELEGATE"))
        else:
            parser.add_argument("--title", default="Verantyx skills newsletter")
            parser.add_argument("--format", dest="output_format", choices=("markdown", "html"), default="markdown")
            parser.add_argument("--output")
            parser.add_argument("--scope-id", required=True)
    parser = sub.add_parser("skills-explain", add_help=False, allow_abbrev=False)
    parser.add_argument("run_id")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--statement", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--expected-revision", type=int)


def dispatch(root, configuration, args, locale):
    from . import personal_skills
    from .recovery_bundle import attach_recovery
    if args.command == "skills-import":
        from .external_capture import read_body
        result = personal_skills.import_work(root, configuration, body=read_body(args.input),
            origin_project=args.origin_project, label=args.label, provider=args.provider, model=args.model,
            key=args.key, mode=args.mode, content_format=args.content_format,
            creator_adapter=args.creator_adapter, reviewer_adapter=args.reviewer_adapter,
            timeout=args.timeout, locale=locale)
        return attach_recovery(root, configuration, result)
    if args.command == "skills-build":
        result = personal_skills.build(root, configuration, args.run_id,
            creator_adapter=args.creator_adapter, reviewer_adapter=args.reviewer_adapter,
            key=args.key, expected_revision=args.expected_revision, timeout=args.timeout, locale=locale)
        return attach_recovery(root, configuration, result)
    if args.command == "skills-explain":
        result = personal_skills.explain(root, configuration, args.run_id, candidate_id=args.candidate,
            statement=args.statement, key=args.key, expected_revision=args.expected_revision)
        return {**result, "command": args.command, "run_id": args.run_id,
                "model_called": False, "mastery": "SELF_REPORT_NOT_CERTIFICATION"}
    result = personal_skills.stack(root, configuration, run_ids=args.run_ids, limit=args.limit,
        query=getattr(args, "query", None), target=getattr(args, "target", None), locale=locale)
    if args.command == "skills-stack":
        return result
    personal_skills.require(personal_skills.valid_text(args.title, 300), "SKILLS_NEWSLETTER_TITLE")
    personal_skills.require(result["omitted_runs"] == 0, "SKILLS_NEWSLETTER_INCOMPLETE_SCOPE")
    personal_skills.require(args.scope_id == result["scope"]["id"], "SKILLS_NEWSLETTER_SCOPE_CHANGED")
    from .skill_newsletter import render
    body = render(result, title=args.title, format=args.output_format)
    if args.output:
        from .application import write_new_output
        write_new_output(root, args.output, body.encode("utf-8"))
    return {"schema_version": 1, "ok": True, "command": args.command, "scope": result["scope"],
            "output": args.output, "format": args.output_format,
            "draft": None if args.output else body, "published": False,
            "model_called": False, "writes": bool(args.output)}


def display(result, locale, command):
    from .cli import visible
    bundle = result.get("recovery_bundle")
    if bundle:
        print("判断・学習の回収: " + bundle["status"])
        if bundle.get("readme"):
            print(visible(bundle["readme"]))
        elif bundle.get("reason"):
            print(visible(bundle["reason"]))
    if command == "skills-newsletter":
        if result.get("output"):
            print("Local draft: " + visible(result["output"]))
        else:
            print(visible(result["draft"]))
        print("scope: " + result["scope"]["id"] + " / published=False")
        return
    if command == "skills-stack":
        print("Personal skills / scope: " + result["scope"]["id"])
        for work in result["works"]:
            print(visible(work["label"]) + " / " + visible(work["run_id"]))
            for item in work["skills"]:
                tag = "suggested" if item.get("target_is_suggestion", True) else "selected"
                print("  " + visible(item["concept"]) + " / " + item["ownership_target"] + " / " + tag)
                print("  " + visible(item["id"]))
                if item.get("ai_policy"):
                    policy = item["ai_policy"]
                    print("  AI scope: " + policy["ai_mode"] + " / " + policy["reuse_mode"])
                    print("  policy: " + policy["policy_id"])
                for key in ("minimum_model", "counterexample", "check"):
                    if item.get(key):
                        print("  " + key + ": " + visible(item[key]))
                for note in item["explanations"]:
                    print("  self-explanation: " + visible(note["statement"]))
            print("  methods=" + str(len(work["methods"])) + " failures=" + str(len(work["failures"]))
                  + " candidates=" + str(len(work["candidates"])))
            if not work["skills"]:
                print("  No generated learning items. History alone is not a learned executable skill.")
        if result["omitted_runs"]:
            print("Omitted runs: " + str(result["omitted_runs"]) + "; narrow --run or increase --limit.")
        print(result["boundary"])
        print("verantyx skills-policies : recorded AI scope is separate from learning ownership")
        return
    print(command + ": " + visible(result["run_id"]))
    if command == "skills-import":
        print("mode=" + result["mode"] + " / " + result["candidate_generation"])
        print("source: " + visible(result["source_ref"]))
        print("verantyx skills-build " + visible(result["run_id"])
              + " --creator-adapter IMPLEMENTATION_JSON --reviewer-adapter VERIFICATION_JSON --key NEW_KEY")
    elif command == "skills-build":
        if result.get("ok") and result.get("response_mode") == "GENERATED":
            print("Two-role candidates recorded; adopted=False, executed=False, independence=NOT_ESTABLISHED")
            print("verantyx keep " + visible(result["run_id"]))
        else:
            print("INCOMPLETE: reviewer output was not accepted; source and failed attempt remain recorded.")
            print("No automatic retry, rule adoption or mastery certification was performed.")
    else:
        print("Explanation recorded as self-report, not a certification of mastery.")
