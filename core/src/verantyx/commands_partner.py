"""One front door into the existing kernel; no parallel agent framework."""
COMMANDS = {"partner", "skills-report", "recover", "judge", "deliver", "develop"}


def register(sub):
    work = sub.add_parser("develop", add_help=False, allow_abbrev=False)
    work.add_argument("request", nargs="?")
    work.add_argument("--input")
    work.add_argument("--origin-project")
    work.add_argument("--capture-mode", choices=("auto", "assisted", "manual"), default="assisted")
    work.add_argument("--key")
    work.add_argument("--include", action="append", default=[])
    work.add_argument("--target")
    work.add_argument("--expect", action="append", default=[])
    work.add_argument("--reject-json", action="append", default=[])
    work.add_argument("--continue-from")
    work.add_argument("--assumption", help="one task-local human assumption recorded before an external AI call")
    work.add_argument("--allow-contested-handoff", action="store_true")
    delivery = sub.add_parser("deliver", add_help=False, allow_abbrev=False)
    delivery.add_argument("run_id")
    delivery.add_argument("--target", required=True)
    delivery.add_argument("--expect", action="append", required=True)
    delivery.add_argument("--reject-json", action="append", default=[])
    delivery.add_argument("--reason", required=True)
    delivery.add_argument("--key", required=True)
    delivery.add_argument("--execute", action="store_true")
    delivery.add_argument("--allow-contested-handoff", action="store_true")
    judge = sub.add_parser("judge", add_help=False, allow_abbrev=False)
    judge.add_argument("run_id")
    judge.add_argument("--target", required=True)
    judge.add_argument("--expect", action="append", required=True)
    judge.add_argument("--reject-json", action="append", default=[])
    judge.add_argument("--reason", required=True)
    judge.add_argument("--key", required=True)
    judge.add_argument("--execute", action="store_true")
    judge.add_argument("--ownership", choices=("OWN", "REVIEW", "REFERENCE", "DELEGATE"))
    judge.add_argument("--ownership-reason")
    recovery = sub.add_parser("recover", add_help=False, allow_abbrev=False)
    recovery.add_argument("run_id")
    parser = sub.add_parser("skills-report", add_help=False, allow_abbrev=False)
    parser.add_argument("--run", dest="run_ids", action="append", default=[])
    parser.add_argument("--query")
    parser.add_argument("--limit", type=int, default=24)
    parser = sub.add_parser("partner", add_help=False, allow_abbrev=False)
    parser.add_argument("request")
    parser.add_argument("--creator-adapter", required=True)
    parser.add_argument("--reviewer-adapter", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--mode", choices=("discuss", "implement"), default="discuss")
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--continue-from")
    parser.add_argument("--constitution", help="canonical project constitution injected as model context only")
    parser.add_argument("--assumption", help="one task-local human assumption for a decision-gated request")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--precedent")
    parser.add_argument("--deliver", action="store_true")
    parser.add_argument("--allow-contested-handoff", action="store_true")
    parser.add_argument("--target")
    parser.add_argument("--expect", action="append", default=[])
    parser.add_argument("--reject-json", action="append", default=[])


def dispatch(root, configuration, args, locale):
    if args.command == "develop":
        from .development import dispatch as develop
        return develop(root, configuration, args)
    from .judgment_compiler import compile_conditions
    if args.command == "deliver":
        from .personal_skills import read_state
        from .partner_delivery import deliver_artifact, delivery_authorization
        contract = compile_conditions(args.target, args.expect, args.reject_json)
        state = read_state(root, configuration, args.run_id)
        if not args.execute:
            return {"ok": True, "command": "deliver", "status": "PREVIEW", "contract": contract,
                    "handoff": delivery_authorization(state, allow_contested_handoff=args.allow_contested_handoff),
                    "model_calls": 0, "execution_performed": False}
        delivered = deliver_artifact(root, configuration, {"state": state, "run_id": args.run_id},
                                     contract, key=args.key, reason=args.reason,
                                     allow_contested_handoff=args.allow_contested_handoff)
        return {**delivered, "ok": delivered["status"] == "COMPLETE_BOUNDED", "command": "deliver"}
    if args.command == "judge":
        contract = compile_conditions(args.target, args.expect, args.reject_json)
        if not args.execute:
            return {"ok": True, "command": "judge", "status": "PREVIEW", "contract": contract,
                    "model_calls": 0, "execution_performed": False}
        from .partner_delivery import judge_target
        judged = judge_target(root, configuration, args.run_id, contract, key=args.key,
                              reason=args.reason, ownership=args.ownership,
                              ownership_reason=args.ownership_reason)
        return {**judged, "ok": judged["status"] == "COMPLETE_BOUNDED", "command": "judge"}
    from .recovery_bundle import attach_recovery, save_recovery
    if args.command == "recover":
        return {"ok": True, "command": "recover", "run_id": args.run_id,
                "recovery_bundle": save_recovery(root, configuration, args.run_id)}
    from .skill_report import make_report
    if args.command == "skills-report":
        return make_report(root, configuration, run_ids=args.run_ids, query=args.query,
                           limit=args.limit, locale=locale)
    from copy import deepcopy
    from .domain.codec import digest
    from .personal_skills import require, roles
    from .responses import ask
    require(not args.deliver or (args.mode == "implement" and not args.execute
                                and args.target and args.expect), "DELIVERY_REQUIRES_EXPLICIT_CONDITIONS")
    require(args.deliver or not (args.target or args.expect or args.reject_json), "UNUSED_DELIVERY_CONDITIONS")
    require(args.deliver or not args.allow_contested_handoff, "UNUSED_SCOPED_HANDOFF_PERMISSION")
    contract = compile_conditions(args.target, args.expect, args.reject_json) if args.deliver else None
    from .constitution import prepare, validate_packet
    from .domain.codec import canonical, decode
    task_gate = prepare(root, configuration, args.request, assumption=args.assumption)
    if task_gate["status"] in ("ASK_ONE_DECISION", "UNKNOWN"):
        return {"ok": False, "command": "partner",
                "status": "DECISION_REQUIRED" if task_gate["status"] == "ASK_ONE_DECISION" else "UNKNOWN_CONTEXT",
                "request": args.request, "task_gate": task_gate, "model_calls": 0,
                "next_action": task_gate.get("question")}
    if args.constitution:
        supplied = validate_packet(decode(args.constitution), allow_empty_purpose=True)
        expected = validate_packet(task_gate["constitution"], allow_empty_purpose=True)
        if canonical(supplied) != canonical(expected):
            from .errors import LedgerError
            raise LedgerError("CONSTITUTION_STALE_OR_FOREIGN")
    request = args.request + "\n\nHost-provided project constitution (context only; not permission or proof):\n" + canonical(task_gate["constitution"])
    if contract:
        from .domain.codec import canonical
        request += "\nExplicit acceptance conditions supplied with the request: " + canonical({
            "target": args.target, "expressions": args.expect, "negative_inputs": args.reject_json})
        request += "\nReturn only the file at the exact project-relative target path. Preserve unrelated fields. Do not use absolute file paths."
    require(not args.execute or (args.mode == "implement" and args.precedent),
            "PARTNER_EXECUTION_REQUIRES_PRECEDENT")
    require(args.execute or args.precedent is None, "PARTNER_UNUSED_PRECEDENT")
    # Different roles are not evidence of statistically independent models.
    roles(args.creator_adapter, args.reviewer_adapter)
    run_id = "partner-" + digest({"project": configuration["project"]["id"], "key": args.key})[:32]
    result = ask(
        root, configuration, request=request,
        adapter_path=args.reviewer_adapter if args.mode == "implement" else args.creator_adapter,
        response_adapter=args.reviewer_adapter, key=args.key, run_id=run_id,
        include_paths=args.include, locale=locale, timeout=args.timeout,
        continue_from=args.continue_from, original_request=request,
        editor_adapter=args.creator_adapter if args.mode == "implement" else None,
        max_repairs=0, execute_candidate=args.execute, precedent_path=args.precedent,
        economy=args.mode == "implement",
        proposal_only=args.deliver,
    )
    response = result["state"].get("latest_response") or {}
    attempt = result["state"].get("editor_attempt") or {}
    generated = (attempt.get("validation", {}).get("status") == "MATCHED"
                 if args.mode == "implement" else response.get("mode") == "GENERATED")
    delivery = None
    if contract:
        from .partner_delivery import deliver_artifact
        delivery = deliver_artifact(root, configuration, result, contract, key=args.key, reason=args.request,
                                    allow_contested_handoff=args.allow_contested_handoff)
    report_runs = [run_id]
    if delivery and delivery.get("run_id"):
        report_runs.append(delivery["run_id"])
    report = make_report(root, configuration, run_ids=report_runs, locale=locale)
    result = attach_recovery(root, configuration, result)
    return {
        **result, "command": "partner", "ok": (
            delivery["status"] == "COMPLETE_BOUNDED" if delivery is not None
            else generated and result.get("execution_ok", True)),
        "delivery": delivery,
        "response_mode": response.get("mode", "NOT_RECORDED"),
        "answer": (response.get("document") or {}).get("answer", ""),
        "recovery": report, "automatic_repairs": 0, "growth_model_calls": 0,
        "role_call_ceiling_before_cache": 2,
        "implementation_validation": deepcopy(attempt.get("validation")),
        "implementation_paths": sorted((attempt.get("document") or {}).get("files", {})),
        "execution_requested": args.execute,
        "independence": "NOT_ESTABLISHED",
        "boundary": "Response and recovery are not proof of completed implementation or human mastery.",
        "task_gate": task_gate,
    }


def display(result, locale, command):
    if command == "develop":
        if result.get("status") != "CLOSED":
            from .development_console import show_result
            from pathlib import Path
            # Artifacts are absolute in recovery; the runtime passes the project
            # root through the returned work receipt for this display.
            show_result(Path(result.get("project_root", ".")), result)
        return
    from .cli import visible
    if command in {"judge", "deliver"}:
        print("判断の実行契約: " + result["status"])
        if result.get("asset_id"):
            print("再利用する資産: " + result["asset_id"])
            print("学習項目: " + result["learning_candidate"] + " / " + result["ownership"])
        if result.get("contract"):
            from .domain.codec import canonical
            print(visible(canonical(result["contract"])))
        if result.get("artifact"):
            print("成果物: " + visible(result["artifact"]))
            print("元ファイルは変更せず、生成コードは実行していません。")
        if result.get("handoff"):
            print("解釈の照合: " + result["handoff"]["status"])
            print("判定範囲: 明示した有限条件のみ。解釈全体の合意とは別です。")
        if result.get("handoff_record"):
            print("不一致の原記録: " + visible(result["handoff_record"]))
        if result.get("recovery_bundle", {}).get("readme"):
            print(visible(result["recovery_bundle"]["readme"]))
        print("model_calls=0 / 人間の習熟や包括的な実行権限は認定しません。")
        return
    if result.get("delivery"):
        delivery = result["delivery"]
        print("成果物と資産の閉ループ: " + delivery["status"])
        if delivery.get("handoff"):
            print("解釈の照合: " + delivery["handoff"]["status"] + " / 不一致は原記録に保持")
        if delivery.get("artifact"):
            print("成果物: " + visible(delivery["artifact"]))
            print("資産と学習: " + visible(delivery["recovery_bundle"]["readme"]))
            print("元ファイルは変更していません。検証は事前に明示した条件の範囲です。")
    bundle = result.get("recovery_bundle")
    if bundle:
        print("判断・学習の回収: " + bundle["status"])
        if bundle.get("readme"):
            print(visible(bundle["readme"]))
            print("モデルなしで再検査できる契約: " + str(bundle["executable_count"]))
        elif bundle.get("reason"):
            print(visible(bundle["reason"]))
    if command == "recover":
        return
    from .skill_report import display_report
    if command == "skills-report":
        display_report(result, locale)
        return
    print(visible(result["answer"]))
    if result.get("implementation_paths"):
        print("実装候補: " + visible(", ".join(result["implementation_paths"])))
        print("候補と実ファイルへの適用は別です。実行には既存の許可と検証の経路が必要です。")
    if not result["ok"]:
        print("INCOMPLETE: 失敗または保留が記録されました。自動で呼び直しません。")
    display_report(result["recovery"], locale)
    print("\n仕事ID: " + visible(result["run_id"]))
    print("次の操作: verantyx skills --interactive")
    print("学習候補と再利用候補は回答と同時に保存。資産回収だけの追加モデル呼出し: 0。")
