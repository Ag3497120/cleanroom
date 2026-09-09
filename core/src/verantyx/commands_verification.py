"""CLI hooks for explicit bounded verification (no model-provided authority)."""
COMMANDS = {"verify-template", "verify-plan", "verify-run", "verifications"}


def register(sub):
    for command in sorted(COMMANDS):
        parser = sub.add_parser(command, add_help=False, allow_abbrev=False)
        parser.add_argument("run_id")
        if command == "verify-template":
            parser.add_argument("--claim", required=True)
            parser.add_argument("--target", required=True)
            parser.add_argument("--output")
        elif command == "verify-plan":
            parser.add_argument("--spec", required=True)
            parser.add_argument("--key", required=True)
            parser.add_argument("--ttl", type=int, default=300)
            parser.add_argument("--expected-revision", type=int)
        elif command == "verify-run":
            parser.add_argument("--verification", required=True)
            parser.add_argument("--key", required=True)
        else:
            parser.add_argument("--archive")


def dispatch(root, configuration, args, locale):
    from .verification import verification_template, plan_verification, run_verification, list_verifications
    from .adapters.observations import read_document
    from .domain.codec import canonical, decode
    from .application import write_new_output
    if args.command == "verify-template":
        value = verification_template(root, configuration, args.run_id, args.claim, args.target, locale=locale)
        if args.output:
            write_new_output(root, args.output, (canonical(value) + "\n").encode("utf-8"))
            return {"schema_version": 1, "ok": True, "command": args.command, "output": args.output, "template": value}
        return value
    if args.command == "verify-plan":
        return plan_verification(root, configuration, args.run_id, decode(read_document(args.spec, 192000)), args.key,
                                 ttl=args.ttl, expected_revision=args.expected_revision)
    if args.command == "verify-run":
        return run_verification(root, configuration, args.run_id, args.verification, args.key)
    return list_verifications(root, configuration, args.run_id, args.archive)


def display(result, locale, command):
    from .cli import visible
    import json
    labels = {
        "en": ("Bounded verification", "Evidence covers only the fixed target and predicates. Independence is not established."),
        "ja": ("範囲を固定した検証", "証拠の範囲は固定した対象と検査項目です。独立性は未確認です。"),
        "zh-Hans": ("限定范围的验证", "证据仅涵盖固定的对象和检查项。独立性尚未确认。"),
        "ko": ("범위를 고정한 검증", "증거는 고정된 대상과 검사 항목에만 적용됩니다. 독립성은 확인되지 않았습니다."),
        "es": ("Verificación de alcance limitado", "La evidencia solo cubre el objeto y las comprobaciones fijados. La independencia no está establecida."),
    }
    title, boundary = labels.get(locale, labels["en"])
    print(title)
    if "verification" in result:
        item = result["verification"]
        print(item["plan"]["id"] + " — " + item["status"])
        print(visible(item["plan"]["spec"]["property"]))
        print(visible(item["plan"]["target"]["path"]) + " · " + item["plan"]["target"]["sha256"])
        if item.get("receipt"):
            receipt = item["receipt"]
            if receipt["result"]:
                print(receipt["result"]["method"] + " / " + receipt["result"]["closure"])
            elif receipt["reason"]:
                print(receipt["reason"])
    else:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    print(boundary)
