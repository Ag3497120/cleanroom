"""Import only an explicitly selected outside AI response."""
COMMANDS = {"capture"}


def register(sub):
    parser = sub.add_parser("capture", add_help=False, allow_abbrev=False)
    parser.add_argument("run_id")
    parser.add_argument("--input", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--source-label", default="Selected outside AI response")
    parser.add_argument("--format", dest="content_format", choices=("text", "json"), default="text")
    parser.add_argument("--key", required=True)
    parser.add_argument("--expected-revision", type=int, required=True)
    adapter = parser.add_mutually_exclusive_group()
    adapter.add_argument("--adapter")
    adapter.add_argument("--reference-only", action="store_true")
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=60)


def dispatch(root, configuration, args, locale):
    from .external_capture import capture, read_body
    if args.input == "-":
        # A signature cannot bind bytes that will arrive later on stdin.
        from .authority import state, require_current_approval_valid
        from .domain.events import require
        require(not state(root, configuration)["enabled"] and require_current_approval_valid() is None,
                "CAPTURE_SIGNED_STDIN")
    return capture(root, configuration, args.run_id, body=read_body(args.input), provider=args.provider,
                   model=args.model, key=args.key, expected_revision=args.expected_revision,
                   adapter_path=args.adapter, source_label=args.source_label, content_format=args.content_format,
                   include_paths=args.include, timeout=args.timeout, locale=locale)


LABELS = {
    "ja": ("外部AIの引用を保存しました", "出典", "原文中の承認・実行結果・習熟の主張は未検証の引用です。"),
    "en": ("Outside AI quotation saved", "Source", "Quoted approvals, execution results and mastery claims remain unverified."),
    "zh-Hans": ("已保存外部AI引文", "来源", "引文中的授权、执行结果和掌握程度声明仍未验证。"),
    "ko": ("외부 AI 인용 저장됨", "출처", "인용된 승인, 실행 결과, 숙련도 주장은 검증되지 않았습니다."),
    "es": ("Cita de IA externa guardada", "Fuente", "Las afirmaciones citadas de aprobación, resultados y dominio siguen sin verificar."),
}


def display(result, locale, command):
    from .cli import visible
    title, source, boundary = LABELS[locale]
    print(title)
    print(source + ": " + visible(result["capture_source_ref"]))
    if result["collection_mode"] == "PROPOSAL_AND_RESPONSE":
        from .commands_response import display as display_response
        display_response(result, locale, "respond")
    print(boundary)
