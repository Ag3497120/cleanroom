"""Signed operator commands and actual writer process observations."""
from .domain.codec import decode

COMMANDS = {"authority-request", "authority-execute", "authority-enable", "authority-rotate", "authority-status",
            "authority-history", "writer-register", "writer-observe", "writer-renew", "writer-release", "writers"}


def accepts(command):
    return command in COMMANDS


def register(sub):
    for command in sorted(COMMANDS):
        parser = sub.add_parser(command, add_help=False, allow_abbrev=False)
        if command in ("authority-enable", "authority-rotate"):
            parser.add_argument("--public-key", required=True)
        elif command == "authority-request":
            parser.add_argument("--invocation", required=True)
            parser.add_argument("--ttl", type=int, default=300)
            parser.add_argument("--bind-input", action="append", default=[])
            parser.add_argument("--output")
        elif command == "authority-execute":
            parser.add_argument("--approval", required=True)
            parser.add_argument("--signature", required=True)
        elif command == "writer-register":
            parser.add_argument("run_id")
            parser.add_argument("--lease", required=True)
            parser.add_argument("--pid", type=int, required=True)
            parser.add_argument("--owner", required=True)
            parser.add_argument("--ttl", type=int, default=300)
        elif command in ("writer-observe", "writer-renew", "writer-release"):
            parser.add_argument("writer_id", **({"nargs": "?"} if command == "writer-observe" else {}))
            if command == "writer-renew":
                parser.add_argument("--ttl", type=int, default=300)


def dispatch(root, configuration, args, locale=None):
    from . import authority, writers
    from .adapters.observations import read_document
    from .domain.events import fields
    from .errors import LedgerError
    command = args.command
    if command == "authority-request":
        invocation = decode(read_document(args.invocation, 128 * 1024))
        fields(invocation, ("argv",))
        request = authority.request(root, configuration, invocation["argv"], ttl=args.ttl, bind_inputs=args.bind_input)
        if args.output:
            from .application import write_new_output
            write_new_output(root, args.output, authority.signing_bytes(request))
        return {"schema_version": 1, "ok": True, "command": command, "approval": request,
                "output": args.output, "signing_format": "canonical UTF-8 JSON; sign the exact output-file bytes",
                "private_key_generated": False}
    if command == "authority-execute":
        return authority.execute(root, configuration, decode(read_document(args.approval, 1024 * 1024)),
                                 read_document(args.signature, 64))
    if command in ("authority-enable", "authority-rotate"):
        raise LedgerError("AUTHORITY_REQUIRED")
    if command in ("authority-status", "authority-history"):
        return authority.inspect(root, configuration, history=command == "authority-history")
    if command == "writer-register":
        return writers.register(root, configuration, args.run_id, args.lease, pid=args.pid, responsible=args.owner, ttl=args.ttl)
    if command == "writer-observe":
        return writers.observe(root, configuration, args.writer_id)
    if command == "writer-renew":
        return writers.renew(root, configuration, args.writer_id, ttl=args.ttl)
    if command == "writer-release":
        return writers.release(root, configuration, args.writer_id)
    return writers.inspect(root, configuration)


LABELS = {
    "ja": ("操作の署名とwriter観測", "署名は外部鍵の保持を確認します。本人の実在確認やOS隔離は行いません。", "状態", "記録版"),
    "en": ("Command signatures and writer observations", "Signatures verify possession of an external key. They do not establish a person's identity or OS isolation.", "Status", "Revision"),
    "zh-Hans": ("操作签名与writer观察", "签名验证外部密钥的持有，不证明自然人身份或操作系统隔离。", "状态", "版本"),
    "ko": ("명령 서명과 writer 관찰", "서명은 외부 키 보유를 확인합니다. 실제 개인의 신원이나 OS 격리를 증명하지 않습니다.", "상태", "기록 버전"),
    "es": ("Firmas de operaciones y observaciones de writers", "La firma verifica la posesión de una clave externa. No acredita la identidad de una persona ni el aislamiento del sistema operativo.", "Estado", "Revisión"),
}


def display(result, locale, command):
    from .cli import visible
    title, boundary, status, revision = LABELS[locale]
    print(title)
    if "enabled" in result:
        print(status + ": " + ("ENABLED" if result["enabled"] else "LEGACY_LOCAL_OPERATOR"))
    if "revision" in result:
        print(revision + ": " + str(result["revision"]))
    if "approval" in result:
        print(visible(result["output"] or result["approval"]["nonce"]))
        print(visible(result["approval"]["operation"]["arguments"]["command"]))
    if "operation_status" in result:
        print(status + ": " + result["operation_status"])
        from .cli import kernel_output
        kernel_output(result["result"], locale, False, result["result"].get("command", "record"))
    for item in result.get("writers", [result["writer"]] if "writer" in result else []):
        print(visible(item["id"]) + "  " + visible(item["workspace"]) + "  PID " + str(item["process"]["pid"]))
        print(status + ": " + item.get("status", "REGISTERED"))
    for item in result.get("observations", result.get("commands", [])):
        print(visible(item.get("writer_id", item.get("nonce"))) + "  " + status + ": " + item["status"])
    print(boundary)
