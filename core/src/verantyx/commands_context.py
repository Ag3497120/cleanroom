"""Shared source inspection and explicit editor handoff/candidate commands."""
COMMANDS = {"shared-context", "handoff-editor", "editor-candidate"}


def register(sub):
    show = sub.add_parser("shared-context", add_help=False, allow_abbrev=False)
    show.add_argument("run_id")
    handoff = sub.add_parser("handoff-editor", add_help=False, allow_abbrev=False)
    handoff.add_argument("run_id")
    handoff.add_argument("--adapter", required=True)
    handoff.add_argument("--editor-adapter", required=True)
    handoff.add_argument("--include", action="append", default=[])
    handoff.add_argument("--key", required=True)
    handoff.add_argument("--expected-revision", type=int, required=True)
    handoff.add_argument("--max-repairs", type=int, choices=(0, 1, 2), default=1)
    handoff.add_argument("--timeout", type=int, default=60)
    candidate = sub.add_parser("editor-candidate", add_help=False, allow_abbrev=False)
    candidate.add_argument("run_id")
    candidate.add_argument("--key", required=True)
    candidate.add_argument("--expected-revision", type=int, required=True)


def dispatch(root, configuration, args, locale):
    if args.command == "handoff-editor":
        from .coordination import coordinate
        return coordinate(root, configuration, args.run_id, proposer_adapter=args.adapter, editor_adapter=args.editor_adapter,
                          key=args.key, expected_revision=args.expected_revision, include_paths=args.include,
                          timeout=args.timeout, max_repairs=args.max_repairs)
    if args.command == "editor-candidate":
        from .coordination import stage_candidate
        return stage_candidate(root, configuration, args.run_id, key=args.key, expected_revision=args.expected_revision)
    from .application import get_projection
    from .shared_context import current_editor_attempt
    from .decision_context import snapshot, handoff_status
    from .storage.sqlite import EventStore
    with EventStore(root, configuration["project"]["id"]) as store:
        state = get_projection(store, args.run_id)["state"]
    return {"schema_version": 1, "ok": True, "command": args.command, "run_id": args.run_id,
            "shared_context": state.get("shared_context"), "interpretations": state.get("handoff_plans", []),
            "editor_attempts": state.get("editor_attempts", []), "current_plan": state.get("handoff_plan"),
            "current_editor_attempt": current_editor_attempt(state), "reference_only": True,
            "decision_context": snapshot(state), "handoff_status": handoff_status(state)}


def display(result, locale, command):
    from .cli import visible
    from .i18n import text
    if "state" in result:
        from .commands_response import display as reply
        reply(result, locale, command)
        return
    packet = result.get("shared_context")
    if packet is None:
        print(text(locale, "error.SHARED_CONTEXT_MISSING"))
        return
    print(text(locale, "context.sources", count=len(packet["sources"]), version=packet["sha256"][:12]))
    for source in packet["sources"]:
        print(visible(source["text"]))
    if result.get("current_plan"):
        plan = result["current_plan"]["plan"]
        print(text(locale, "context.interpretations"))
        nodes = {n["id"]: n for n in plan["interpretations"]}
        for node in nodes.values():
            print("- " + text(locale, "context." + node["disposition"]) + " · " + visible(node["meaning"]) +
                  " · " + text(locale, "context." + node["strength"]))
        for relation in plan["relations"]:
            print(text(locale, "context." + relation["kind"],
                       source=visible(nodes[relation["from"]]["meaning"]),
                       target=visible(nodes[relation["to"]]["meaning"])))
        for case in plan["cases"]:
            expected = next(c["text"] for c in case["choices"] if c["id"] == case["expected"])
            print(text(locale, "context.case", situation=visible(case["situation"]), choice=visible(expected)))
    for row in (result.get("decision_context") or {}).get("items", []):
        choice = row["selected_option"]
        if choice:
            print(text(locale, "context.decision", question=visible(row["point"]["question"]), choice=visible(choice["label"])))
        else:
            print(text(locale, "context.decision_pending", question=visible(row["point"]["question"])))
    attempt = result.get("current_editor_attempt")
    if attempt:
        validation = attempt["validation"]
        print(text(locale, "context." + result.get("handoff_status", validation["status"])))
        print(text(locale, "context.boundary"))
    elif result.get("current_plan"):
        print(text(locale, "context.AWAITING_EDITOR"))
    history_count = len(result["editor_attempts"]) - int(attempt is not None)
    if history_count:
        print(text(locale, "context.attempt_history", count=history_count))
