"""Closed connection CLI: explicit model endpoints, voluntary feedback, inert transport."""

COMMANDS = {"model-api-config", "model-api-check", "service-definition", "archive-send", "archive-fetch",
            "learn-model-material", "learn-model-assess", "service-register", "service-stop", "service-worker",
            "notification-packet", "notification-authorize", "notification-send"}


def accepts(command):
    return command in COMMANDS


def register(sub):
    model = sub.add_parser("model-api-config", add_help=False, allow_abbrev=False)
    model.add_argument("--provider", required=True, choices=("openai", "anthropic", "gemini", "ollama", "openai_compatible"))
    for name in ("model", "endpoint", "output"):
        model.add_argument("--" + name, required=True)
    model.add_argument("--key-env")
    model.add_argument("--allow-loopback-http", action="store_true")
    model.add_argument("--timeout", type=int, default=30)
    model.add_argument("--max-output-tokens", type=int, default=4096)
    model.add_argument("--max-response-bytes", type=int, default=262144)
    model.add_argument("--context-window", type=int)
    thinking = model.add_mutually_exclusive_group()
    thinking.add_argument("--thinking", action="store_true")
    thinking.add_argument("--thinking-mode", choices=("on", "off", "auto"))
    check = sub.add_parser("model-api-check", add_help=False, allow_abbrev=False)
    check.add_argument("--adapter", required=True)
    service = sub.add_parser("service-definition", add_help=False, allow_abbrev=False)
    service.add_argument("--kind", required=True, choices=("launchd", "systemd"))
    service.add_argument("--executable", required=True)
    service.add_argument("--output", required=True)
    service.add_argument("--interval", type=int, default=60)
    service.add_argument("--max-jobs", type=int, default=1)
    worker = sub.add_parser("service-worker", add_help=False, allow_abbrev=False)
    worker.add_argument("--max-jobs", type=int, default=1)
    for name in ("service-register", "service-stop"):
        control = sub.add_parser(name, add_help=False, allow_abbrev=False)
        for argument in ("definition", "sha256", "manager", "key", "worker-sha256"):
            control.add_argument("--" + argument, required=True)
        control.add_argument("--timer-sha256")
        control.add_argument("--timeout", type=int, default=30)
    packet = sub.add_parser("notification-packet", add_help=False, allow_abbrev=False)
    packet.add_argument("run_id")
    for argument in ("candidate", "exercise", "output"):
        packet.add_argument("--" + argument, required=True)
    permit = sub.add_parser("notification-authorize", add_help=False, allow_abbrev=False)
    for argument in ("packet", "sha256", "endpoint", "key"):
        permit.add_argument("--" + argument, required=True)
    permit.add_argument("--key-env")
    permit.add_argument("--allow-loopback-http", action="store_true")
    permit.add_argument("--ttl", type=int, default=300)
    permit.add_argument("--timeout", type=int, default=30)
    sender = sub.add_parser("notification-send", add_help=False, allow_abbrev=False)
    sender.add_argument("delivery_id")
    for name in ("archive-send", "archive-fetch"):
        archive = sub.add_parser(name, add_help=False, allow_abbrev=False)
        archive.add_argument("--archive" if name == "archive-send" else "--sha256", required=True)
        archive.add_argument("--directory", required=True)
    for name in ("learn-model-material", "learn-model-assess"):
        learn = sub.add_parser(name, add_help=False, allow_abbrev=False)
        learn.add_argument("run_id")
        learn.add_argument("candidate_id")
        learn.add_argument("--adapter", required=True)
        learn.add_argument("--key", required=True)
        learn.add_argument("--expected-revision", type=int, required=True)
        learn.add_argument("--timeout", type=int, default=60)
        if name == "learn-model-assess":
            learn.add_argument("--submission-ref", required=True)
            learn.add_argument("--rubric", required=True)


def dispatch(root, configuration, args, locale):
    from . import connections_v05 as connect
    if args.command == "model-api-config":
        return connect.configure_model(root, provider=args.provider, model=args.model, endpoint=args.endpoint,
                                       key_env=args.key_env, output=args.output, allow_loopback_http=args.allow_loopback_http,
                                       timeout=args.timeout, max_output_tokens=args.max_output_tokens,
                                       max_response_bytes=args.max_response_bytes,
                                       context_window=args.context_window,
                                       thinking={"on": True, "off": False, "auto": "auto"}.get(args.thinking_mode, args.thinking))
    if args.command == "model-api-check":
        return connect.check_model(args.adapter)
    if args.command == "service-definition":
        return connect.service_definition(root, executable=args.executable, kind=args.kind, output=args.output,
                                          interval=args.interval, max_jobs=args.max_jobs)
    if args.command in ("service-register", "service-stop", "service-worker"):
        from . import service_runtime
        if args.command == "service-worker":
            return service_runtime.worker(root, configuration, max_jobs=args.max_jobs)
        return service_runtime.control(root, configuration, operation=args.command.removeprefix("service-"),
                                       definition=args.definition, expected_sha256=args.sha256, manager=args.manager,
                                       worker_sha256=args.worker_sha256, timer_sha256=args.timer_sha256, timeout=args.timeout, key=args.key)
    if args.command.startswith("notification-"):
        from . import notifications
        if args.command == "notification-packet":
            return notifications.prepare(root, configuration, args.run_id, candidate_id=args.candidate,
                                         exercise_id=args.exercise, output=args.output)
        if args.command == "notification-authorize":
            return notifications.authorize(root, configuration, packet_path=args.packet, expected_sha256=args.sha256,
                                           endpoint=args.endpoint, key=args.key, key_env=args.key_env,
                                           allow_loopback_http=args.allow_loopback_http, ttl=args.ttl, timeout=args.timeout)
        return notifications.send(root, configuration, args.delivery_id)
    if args.command == "archive-send":
        return connect.archive_send(root, configuration, archive_id=args.archive, directory=args.directory)
    if args.command == "archive-fetch":
        return connect.archive_fetch(root, configuration, expected_sha256=args.sha256, directory=args.directory)
    from .learning_external import generate
    return generate(root, configuration, args.run_id, candidate_id=args.candidate_id,
                    operation="material" if args.command == "learn-model-material" else "assess",
                    adapter_path=args.adapter, key=args.key, expected_revision=args.expected_revision,
                    submission_ref=getattr(args, "submission_ref", None), rubric=getattr(args, "rubric", None),
                    timeout=args.timeout)


LABELS = {
    "ja": ("明示接続", "外部応答から人間の判断・許可・本人の習熟を確定しません。"),
    "en": ("Explicit connections", "External responses do not establish human decisions, authority, or mastery."),
    "zh-Hans": ("显式连接", "不根据外部响应确定人的判断、授权或掌握程度。"),
    "ko": ("명시적 연결", "외부 응답으로 사람의 판단, 권한, 숙련도를 확정하지 않습니다."),
    "es": ("Conexiones explícitas", "Las respuestas externas no establecen decisiones humanas, permisos ni dominio personal."),
}


def display(result, locale, command):
    from .cli import visible
    if command == "service-worker":
        from .commands_jobs import display as show_jobs
        from .i18n import text
        show_jobs(result, locale, command)
        for item in result.get("refused", []):
            print(visible(item["job_id"]) + "  " + text(locale, "error." + item["code"]))
        return
    title, boundary = LABELS[locale]
    print(title)
    for key in ("provider", "model", "output", "archive_id", "candidate_id", "delivery_id", "status"):
        if result.get(key):
            print(visible(str(result[key])))
    for item in result.get("files", []):
        print(visible(item["path"]) + "  SHA256 " + item["sha256"])
    for key in ("file_sha256", "worker_sha256"):
        if result.get(key):
            print(key + ": " + result[key])
    if result.get("receipt"):
        print(result["receipt"]["status"] + "  HTTP " + str(result["receipt"]["http_status"]))
    print(boundary)
