"""CLI entry points for bounded proposal delivery."""
import time

COMMANDS = {"job-submit", "jobs", "job-run", "job-recover", "job-cancel", "worker"}


def register(sub):
    submit = sub.add_parser("job-submit", add_help=False, allow_abbrev=False)
    submit.add_argument("run_id")
    submit.add_argument("--adapter", required=True)
    submit.add_argument("--key", required=True)
    submit.add_argument("--expected-revision", type=int, required=True)
    submit.add_argument("--include", action="append", default=[])
    submit.add_argument("--delay", type=int, default=0)
    submit.add_argument("--ttl", type=int, default=3600)
    submit.add_argument("--timeout", type=int, default=60)
    submit.add_argument("--max-output", type=int, default=262144)
    submit.add_argument("--collect", action="store_true")
    sub.add_parser("jobs", add_help=False, allow_abbrev=False)
    for name in ("job-run", "job-recover", "job-cancel"):
        parser = sub.add_parser(name, add_help=False, allow_abbrev=False)
        parser.add_argument("job_id")
        if name == "job-cancel":
            parser.add_argument("--reason", required=True)
    worker = sub.add_parser("worker", add_help=False, allow_abbrev=False)
    worker.add_argument("--max-jobs", type=int, default=1)
    worker.add_argument("--watch", action="store_true")
    worker.add_argument("--poll", type=int, default=5)
    worker.add_argument("--idle-timeout", type=int, default=60)


def dispatch(root, configuration, args, locale):
    from . import jobs
    from .domain.events import require
    if args.command == "job-submit":
        return jobs.submit(root, configuration, args.run_id, adapter_path=args.adapter, key=args.key,
                           expected_revision=args.expected_revision, include_paths=args.include,
                           delay=args.delay, ttl=args.ttl, timeout=args.timeout, max_output=args.max_output, locale=locale,
                           collect=args.collect)
    if args.command == "jobs":
        return jobs.list_jobs(root, configuration)
    if args.command == "job-cancel":
        return jobs.cancel(root, configuration, args.job_id, reason=args.reason)
    if args.command in ("job-run", "job-recover"):
        return jobs.run_job(root, configuration, args.job_id, recover=args.command == "job-recover")
    require(1 <= args.poll <= 60 and 1 <= args.idle_timeout <= 3600 and 1 <= args.max_jobs <= 100, "ARGUMENTS")
    result = jobs.worker(root, configuration, max_jobs=args.max_jobs)
    if not args.watch:
        return result
    idle_since = time.monotonic()
    while len(result["processed"]) < args.max_jobs and time.monotonic() - idle_since < args.idle_timeout:
        time.sleep(min(args.poll, max(0, args.idle_timeout - (time.monotonic() - idle_since))))
        current = jobs.worker(root, configuration, max_jobs=args.max_jobs - len(result["processed"]))
        if current["processed"]:
            idle_since = time.monotonic()
            result["processed"].extend(current["processed"])
            result["ok"] = result["ok"] and current["ok"]
    return result


LABELS = {
    "ja": ("提案生成ジョブ", "ジョブは提案を記録します。実行・採用の許可は別に扱います。", "処理件数"),
    "en": ("Proposal jobs", "Jobs record proposals. Execution and adoption use separate authorization.", "Processed"),
    "zh-Hans": ("提案生成任务", "任务记录提案。执行和采纳需要单独授权。", "已处理"),
    "ko": ("제안 생성 작업", "작업은 제안을 기록합니다. 실행과 채택 권한은 별도로 처리합니다.", "처리 건수"),
    "es": ("Trabajos de propuestas", "Los trabajos registran propuestas. La ejecución y la adopción requieren autorizaciones separadas.", "Procesados"),
}


def display(result, locale, command):
    from .cli import visible
    title, boundary, processed = LABELS[locale]
    print(title)
    for item in result.get("jobs", result.get("processed", [result] if "job_id" in result else [])):
        print(visible(item["job_id"]) + "  " + visible(item["run_id"]) + "  " + item["status"])
        if (item.get("details") or {}).get("code"):
            print("  " + visible(item["details"]["code"]))
    if "processed" in result:
        print(processed + ": " + str(len(result["processed"])))
    print(boundary)
