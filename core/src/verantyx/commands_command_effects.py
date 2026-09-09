"""CLI hooks for separate command proposal, authorization and execution."""
COMMANDS = {"command-propose", "command-authorize", "command-execute", "command-effects"}


def register(sub):
    for name in sorted(COMMANDS):
        parser = sub.add_parser(name, add_help=False, allow_abbrev=False)
        parser.add_argument("run_id")
        if name == "command-effects":
            parser.add_argument("--archive")
            continue
        parser.add_argument("--command-file", required=True)
        parser.add_argument("--key", required=True)
        if name == "command-propose":
            parser.add_argument("--spec", required=True)
            parser.add_argument("--ttl", type=int, default=300)
        else:
            parser.add_argument("--effect", required=True)
            if name == "command-authorize":
                parser.add_argument("--plan-hash", required=True)
                parser.add_argument("--reason", required=True)
                parser.add_argument("--ttl", type=int, default=300)
                parser.add_argument("--accept-unsandboxed", action="store_true")
                parser.add_argument("--accept-irreversible", action="store_true")


def accepts(command):
    return command in COMMANDS


def dispatch(root, configuration, args, locale):
    from .command_effects import propose_command, authorize_command, execute_command, list_commands
    from .adapters.observations import read_document
    from .domain.codec import decode
    if args.command == "command-effects":
        return list_commands(root, configuration, args.run_id, args.archive)
    common = {"command_path": args.command_file}
    if args.command == "command-propose":
        return propose_command(root, configuration, args.run_id, decode(read_document(args.spec, 192000)), args.key, ttl=args.ttl, **common)
    if args.command == "command-authorize":
        return authorize_command(root, configuration, args.run_id, args.effect, args.key, plan_hash=args.plan_hash, reason=args.reason,
                                 accept_unsandboxed=args.accept_unsandboxed, accept_irreversible=args.accept_irreversible, ttl=args.ttl, **common)
    return execute_command(root, configuration, args.run_id, args.effect, args.key, **common)


def display(result, locale, command):
    import json
    labels = {
        "en": "Trusted command effect. Effect labels do not enforce an OS sandbox; process completion does not confirm an external effect.",
        "ja": "信頼するコマンドの効果。効果の分類はOSの隔離保証ではなく、プロセス完了は外部効果の確認ではありません。",
        "zh-Hans": "可信命令的效果。效果分类不提供操作系统隔离，进程完成不代表外部效果已确认。",
        "ko": "신뢰하는 명령의 효과. 효과 분류는 OS 격리를 보장하지 않으며 프로세스 완료는 외부 효과의 확인이 아닙니다.",
        "es": "Efecto de un comando de confianza. La clasificación no impone un aislamiento del sistema; finalizar el proceso no confirma un efecto externo.",
    }
    print(labels.get(locale, labels["en"]))
    print(json.dumps(result.get("command_effect", result), ensure_ascii=True, indent=2))
