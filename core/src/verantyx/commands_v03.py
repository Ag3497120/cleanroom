"""Public operations that connect proposal, adoption, learning and handoff."""
LEARNING = {"learn-" + name for name in ("collect", "raise", "target", "defer", "resume", "explain", "counterexample", "apply", "transfer")}
ADOPTION = {"adoption-propose", "adoption-review", "adoption-authorize", "adopt"}
MEMORY = {"memory-start", "memory-read", "memory-search", "memory-lookup", "memory-digest-lookup"}
COMMANDS = LEARNING | ADOPTION | MEMORY | {"propose", "handoff-packet", "memory-save"}


def register(sub):
    for command in sorted(LEARNING):
        parser = sub.add_parser(command, add_help=False, allow_abbrev=False)
        parser.add_argument("run_id")
        parser.add_argument("--key", required=True)
        parser.add_argument("--expected-revision", type=int)
        parser.add_argument("--candidate", required=command not in ("learn-collect", "learn-raise"))
        if command == "learn-raise":
            for field in ("concept", "concept-id", "minimum-model", "counterexample", "check"):
                parser.add_argument("--" + field, required=True)
            parser.add_argument("--why-now", action="append", required=True)
        if command == "learn-target":
            parser.add_argument("--target", choices=("OWN", "REVIEW", "REFERENCE", "DELEGATE"), required=True)
        if command in ("learn-target", "learn-defer", "learn-resume"):
            parser.add_argument("--reason", required=True)
        if command in ("learn-explain", "learn-counterexample", "learn-apply", "learn-transfer"):
            parser.add_argument("--statement", required=True)
        if command in ("learn-raise", "learn-explain", "learn-counterexample", "learn-apply", "learn-transfer"):
            parser.add_argument("--source-ref", action="append", default=[], required=command == "learn-raise")
    for command in sorted(ADOPTION):
        parser = sub.add_parser(command, add_help=False, allow_abbrev=False)
        parser.add_argument("run_id")
        parser.add_argument("--precedent", required=True)
        if command != "adoption-review":
            parser.add_argument("--key", required=True)
        if command == "adoption-propose":
            parser.add_argument("--lease", required=True)
            parser.add_argument("--branch", default="verantyx/canonical")
            parser.add_argument("--message", default="Adopt verified Vera candidate")
        else:
            parser.add_argument("--adoption", required=True)
        if command == "adoption-authorize":
            parser.add_argument("--reason", required=True)
            parser.add_argument("--ttl", type=int, default=300)
    parser = sub.add_parser("propose", add_help=False, allow_abbrev=False)
    parser.add_argument("run_id")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--expected-revision", required=True, type=int)
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--max-output", type=int, default=262144)
    parser.add_argument("--reuse-assets", action="store_true")
    parser.add_argument("--collect", action="store_true")
    for command in sorted(MEMORY):
        parser = sub.add_parser(command, add_help=False, allow_abbrev=False)
        parser.add_argument("--server", required=True)
        parser.add_argument("--name", required=True)
        parser.add_argument("--timeout", type=int, default=30)
        if command == "memory-read":
            parser.add_argument("--after-n", type=int, default=0)
            parser.add_argument("--limit", type=int, default=20)
        if command in ("memory-start", "memory-read"):
            parser.add_argument("--max-chars", type=int, default=12000)
        if command == "memory-search":
            parser.add_argument("query")
            parser.add_argument("--k", type=int, default=10)
        if command == "memory-lookup":
            parser.add_argument("n", type=int)
        if command == "memory-digest-lookup":
            parser.add_argument("digest_id")
    parser = sub.add_parser("handoff-packet", add_help=False, allow_abbrev=False)
    parser.add_argument("run_ids", nargs="+")
    parser.add_argument("--output")
    parser = sub.add_parser("memory-save", add_help=False, allow_abbrev=False)
    parser.add_argument("packet")
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--timeout", type=int, default=30)


def dispatch(root, configuration, args, locale):
    command = args.command
    if command in LEARNING:
        from .learning import control_learning
        keywords = {name: getattr(args, name, None) for name in ("key", "expected_revision", "target", "reason", "concept",
                     "concept_id", "why_now", "minimum_model", "counterexample", "check", "statement")}
        return control_learning(root, configuration, args.run_id, command.removeprefix("learn-"),
                                candidate_id=args.candidate, source_refs=getattr(args, "source_ref", []), **keywords)
    if command in ADOPTION:
        from .adoption import propose_adoption, review_adoption, authorize_adoption, adopt
        if command == "adoption-propose":
            return propose_adoption(root, configuration, args.run_id, args.lease, args.precedent, args.key,
                                    branch=args.branch, message=args.message)
        if command == "adoption-review":
            return review_adoption(root, configuration, args.run_id, args.adoption, args.precedent)
        if command == "adoption-authorize":
            return authorize_adoption(root, configuration, args.run_id, args.adoption, args.precedent, args.key,
                                      reason=args.reason, ttl=args.ttl)
        return adopt(root, configuration, args.run_id, args.adoption, args.precedent, args.key)
    from .bridges import propose, memory_read, handoff_packet, memory_save
    if command == "propose":
        if args.collect:
            from .external_capture import collect_proposal
            return collect_proposal(root, configuration, args.run_id, adapter_path=args.adapter, key=args.key,
                                    expected_revision=args.expected_revision, include_paths=args.include, timeout=args.timeout,
                                    max_output=args.max_output, locale=locale)
        return propose(root, configuration, args.run_id, adapter_path=args.adapter, key=args.key,
                       expected_revision=args.expected_revision, include_paths=args.include, timeout=args.timeout,
                       max_output=args.max_output, locale=locale, reuse_assets=args.reuse_assets)
    if command in MEMORY:
        allowed = ("after_n", "limit", "max_chars", "query", "k", "n", "digest_id")
        kwargs = {name: getattr(args, name) for name in allowed if hasattr(args, name)}
        if command == "memory-start":
            kwargs["lang"] = locale
        return memory_read(server_path=args.server, name=args.name, operation=command.removeprefix("memory-"), timeout=args.timeout, **kwargs)
    if command == "handoff-packet":
        return handoff_packet(root, configuration, run_ids=args.run_ids, output=args.output)
    return memory_save(root, configuration, packet_path=args.packet, expected_sha256=args.expected_sha256,
                       server_path=args.server, name=args.name, key=args.key, timeout=args.timeout)


def display(result, locale, command):
    from .cli import visible
    from .i18n import text
    import json
    print(text(locale, "flow.title"))
    if result.get("duplicate"):
        print(text(locale, "ledger.duplicate"))
    if "adoption" in result:
        item = result["adoption"]
        print(text(locale, "flow.adoption", identifier=result["adoption_id"], status=item["status"]))
        print(text(locale, "flow.branch", branch=visible(item["plan"]["target_ref"])))
        for name in item["plan"]["files"]:
            print("  " + visible(name))
        if item.get("receipt"):
            print(text(locale, "flow.commit", commit=item["receipt"]["commit"]))
        if item.get("reason"):
            print(visible(item["reason"]))
        for change in result.get("changes", []):
            print("\n".join(visible(line) for line in change["diff"].splitlines()))
            if change["diff_truncated"]:
                print(text(locale, "flow.truncated"))
        print(text(locale, "flow.branch_boundary"))
    elif "candidates" in result:
        for item in result["candidates"]:
            print(visible(item["concept"]) + " [" + item["status"] + "; " + item["ownership_target"] + "]")
            print("  " + item["id"])
            print("  " + visible(item["minimum_model"]))
            print("  " + visible(item["check"]))
            if item.get("evidence"):
                print("  " + item["submission_state"])
                for evidence in item["evidence"]:
                    print("  " + visible(evidence["statement"]))
        print(text(locale, "flow.learning_boundary"))
    elif command == "handoff-packet":
        print(text(locale, "flow.packet"))
        value = {k: v for k, v in result.items() if k != "packet"} if result.get("output") else result
        print(json.dumps(value, ensure_ascii=True, indent=2))
    elif command.startswith("memory-"):
        if type(result.get("result")) is str:
            print("\n".join(visible(line) for line in result["result"].splitlines()))
        else:
            print(json.dumps(result, ensure_ascii=True, indent=2))
