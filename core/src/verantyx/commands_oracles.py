"""CLI registration for explicitly fixed, isolated candidate I/O contracts."""
COMMANDS = {"oracle-plan", "oracle-run", "oracles"}


def register(sub):
    for name in sorted(COMMANDS):
        parser = sub.add_parser(name, add_help=False, allow_abbrev=False)
        parser.add_argument("run_id")
        if name == "oracles":
            parser.add_argument("--archive")
        else:
            parser.add_argument("--precedent", required=True)
            parser.add_argument("--key", required=True)
            if name == "oracle-plan":
                parser.add_argument("--spec", required=True)
                parser.add_argument("--ttl", type=int, default=300)
                parser.add_argument("--expected-revision", type=int)
            else:
                parser.add_argument("--oracle", required=True)


def accepts(command):
    return command in COMMANDS


def dispatch(root, configuration, args, locale):
    from .oracles import plan_oracle, run_oracle, list_oracles
    from .adapters.observations import read_document
    from .domain.codec import decode
    if args.command == "oracle-plan":
        return plan_oracle(root, configuration, args.run_id, decode(read_document(args.spec, 192000)), args.key,
                           precedent=args.precedent, ttl=args.ttl, expected_revision=args.expected_revision)
    if args.command == "oracle-run":
        return run_oracle(root, configuration, args.run_id, args.oracle, args.key, precedent=args.precedent)
    return list_oracles(root, configuration, args.run_id, args.archive)


def display(result, locale, command):
    import json
    labels = {
        "en": "Separate-process candidate checks: evidence covers only the fixed inputs and expected outputs.",
        "ja": "別プロセスで候補を検査：証拠の範囲は固定した入力と期待する出力です。",
        "zh-Hans": "在独立进程中检查候选：证据仅涵盖固定输入和预期输出。",
        "ko": "별도 프로세스에서 후보 검사: 증거는 고정된 입력과 예상 출력에만 적용됩니다.",
        "es": "Comprobación del candidato en otro proceso: la evidencia solo cubre entradas y salidas esperadas fijadas.",
    }
    print(labels.get(locale, labels["en"]))
    print(json.dumps(result.get("oracle", result), ensure_ascii=True, indent=2))
