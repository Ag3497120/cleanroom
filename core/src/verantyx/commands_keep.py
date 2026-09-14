"""Explicit end-of-work capture using existing learning and verification events."""
import hashlib
import shlex

from .errors import LedgerError

COMMANDS = {"keep"}


def register(sub):
    parser = sub.add_parser("keep", add_help=False, allow_abbrev=False)
    parser.add_argument("run_id")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--learn", dest="learn_candidate")
    operation.add_argument("--delegate", dest="delegate_candidate")
    # 'check' is a text argument in the authority layer, not a signed file.
    operation.add_argument("--check", dest="check_spec")
    parser.add_argument("--reason")
    parser.add_argument("--key")
    parser.add_argument("--expected-revision", type=int)


def dispatch(root, configuration, args, locale):
    from .experience_report import report

    learn = getattr(args, "learn_candidate", None)
    delegate = getattr(args, "delegate_candidate", None)
    check = getattr(args, "check_spec", None)
    reason, key = getattr(args, "reason", None), getattr(args, "key", None)
    revision = getattr(args, "expected_revision", None)
    selected = sum(value is not None for value in (learn, delegate, check))
    choosing = learn is not None or delegate is not None
    # Validate the whole operation before invoking any writing API.
    if (selected > 1 or selected and (type(key) is not str or not key.strip())
            or choosing and (type(reason) is not str or not reason.strip())
            or not choosing and reason is not None
            or not selected and (key is not None or revision is not None)):
        raise LedgerError("ARGUMENTS")
    operation = {"kind": "READ_ONLY", "executed": False}
    receipt = None
    if choosing:
        from .learning import control_learning
        candidate, target = (learn, "OWN") if learn is not None else (delegate, "DELEGATE")
        receipt = control_learning(root, configuration, args.run_id, "target",
                                   candidate_id=candidate, target=target, reason=reason,
                                   key=key, expected_revision=revision)
        operation.update(kind="LEARNING_TARGET_SELECTED", candidate_id=candidate, target=target)
    elif check is not None:
        from .adapters.observations import read_document
        from .authority import require_current_input_hash
        from .domain.codec import decode
        from .verification import plan_verification
        raw = read_document(check, 192000)
        require_current_input_hash(check, hashlib.sha256(raw).hexdigest())
        receipt = plan_verification(root, configuration, args.run_id, decode(raw), key,
                                    ttl=300, expected_revision=revision)
        operation.update(kind="VERIFICATION_PLANNED", verification_id=receipt["verification_id"],
                         status=receipt["verification"]["status"])
    if receipt is not None:
        operation.update(duplicate=receipt["duplicate"], recorded_revision=receipt["recorded_revision"])
    result = report(root, configuration, args.run_id, locale)
    result.update(command="keep", operation=operation, write_requested=bool(selected),
                  writes=receipt is not None and not receipt["duplicate"])
    result["boundaries"]["read_only"] = not selected
    result["capture"] = _capture(root, result)
    return result


def _capture(root, result):
    system, human = result["system_delta"], result["human_delta"]
    items = {row["id"]: row for row in [*human["suggestions"], *human["ownership_choices"]]}
    learning = [{key: row[key] for key in (
        "id", "concept", "ownership_target", "target_is_suggestion", "status",
        "source_ref", "source_refs", "recorded",
    ) if key in row} for row in items.values()]
    counts = {"human_judgments": len(human["judgments"]),
              "verification_methods": len(system["verification_assets"]),
              "execution_methods": len(system["execution_assets"]),
              "failure_cases": len(system["failure_assets"]),
              "model_candidates": len(system["model_candidates"])}
    commands = []

    def add(purpose, argv, *, requires=(), writes=False, executes_verifier=False):
        argv = ["verantyx", "--project", str(root), *argv]
        commands.append({"purpose": purpose, "argv": argv, "command": shlex.join(argv),
                         "requires": list(requires), "writes": writes,
                         "executes_verifier": executes_verifier, "authority_granted": False})

    run = result["run_id"]
    add("REPLAY_RECORDED_WORK", ["replay", run])
    add("SHOW_ALL_LEARNING_ITEMS", ["learn", run])
    for asset in [row for row in result["next_actions"] if row["reusable_via_current_cli"]][:3]:
        argv = [asset["cli_command"], asset["asset_id"], "--claim", "CLAIM_ID", "--target", "TARGET_PATH"]
        if "EXPLICIT_REPRODUCES_BINDING" in asset["requires"]:
            argv.extend(["--reproduces", "VERIFICATION_ID"])
        add("PREPARE_SAVED_CONTRACT_TEMPLATE", argv, requires=asset["requires"])
    for candidate in learning[:3]:
        for flag in ("--learn", "--delegate"):
            add("SELECT_OWN" if flag == "--learn" else "SELECT_DELEGATE",
                ["keep", run, flag, candidate["id"], "--reason", "REASON", "--key", "NEW_KEY",
                 "--expected-revision", str(result["revision"])], writes=True,
                requires=("EXPLICIT_HUMAN_CHOICE", "REASON", "NEW_KEY", "NORMAL_AUTHORITY_CHECKS"))
    add("SAVE_FINITE_CONTRACT_PLAN", ["keep", run, "--check", "SPEC_FILE", "--key", "NEW_KEY",
                                     "--expected-revision", str(result["revision"])], writes=True,
        requires=("SPEC_WITH_EXISTING_CLAIM_AND_TARGET", "CURRENT_TARGET_OBSERVATION", "NEW_KEY",
                  "NORMAL_AUTHORITY_CHECKS"))
    operation = result["operation"]
    if operation["kind"] == "VERIFICATION_PLANNED":
        add("EXPLICITLY_RUN_PLANNED_VERIFIER",
            ["verify-run", run, "--verification", operation["verification_id"], "--key", "NEW_KEY"],
            writes=True, executes_verifier=True,
            requires=("EXPLICIT_EXECUTION_REQUEST", "CURRENT_PLAN_AND_TARGET", "NEW_KEY", "NORMAL_AUTHORITY_CHECKS"))
    return {"method_status": "EXECUTABLE_METHODS_SAVED" if counts["verification_methods"] + counts["execution_methods"]
            else "NO_EXECUTABLE_METHOD_YET", "counts": counts,
            "learning_items": learning, "next_commands": commands}


def display(result, locale, command):
    from .cli import visible

    def say(ja, en):
        return ja if locale == "ja" else en

    capture, system, human = result["capture"], result["system_delta"], result["human_delta"]
    print("keep " + visible(result["run_id"]) + " / revision " + str(result["revision"]))
    if capture["method_status"] == "NO_EXECUTABLE_METHOD_YET":
        print(say("再利用できる実行可能な方法は、まだ記録されていません。",
                  "No executable method has been recorded yet."))
    else:
        print(say("実行可能な契約が保存されています。PLANNED は計画の保存であり、検証成功ではありません。",
                  "Executable contracts are saved. PLANNED records a plan, not a passed check."))
    operation = result["operation"]
    if operation["kind"] != "READ_ONLY":
        identity = operation.get("candidate_id", operation.get("verification_id"))
        print(visible(str(identity)) + " -> " + operation.get("target", operation.get("status", ""))
              + (" (duplicate)" if operation["duplicate"] else ""))
    sections = [
        (say("人間が記録した判断", "Recorded human judgments"), human["judgments"],
         lambda row: str(row["point_id"]) + " -> " + str(row["choice"]) + ": " + row["reason"]),
        (say("保存された検証方法", "Saved verification methods"), system["verification_assets"],
         lambda row: row["id"] + " / " + row["family"] + " / " + row["status"] + " / " + str(row.get("name") or row.get("title") or row["family"])),
        (say("保存された実行方法", "Saved execution methods"), system["execution_assets"],
         lambda row: row["id"] + " / " + row["family"] + " / " + row["status"]),
        (say("保持された失敗・未確定結果", "Preserved failures and unknown outcomes"), system["failure_assets"],
         lambda row: row["id"] + " / " + str(row.get("closure") or row.get("outcome"))
         + " / " + str(row.get("reason") or row.get("case_kind", ""))),
        (say("学ぶこと・委ねる判断", "Learning and delegated judgments"), capture["learning_items"],
         lambda row: row["id"] + " / " + row["concept"] + " / " + row["ownership_target"]
         + " / " + row["status"] + (" (suggested)" if row.get("target_is_suggestion", True) else " (selected)")),
    ]
    for title, rows, describe in sections:
        print(title + ": " + str(len(rows)))
        for row in rows[:3]:
            refs = row.get("source_refs") or [row.get("source_ref")]
            print("  " + visible(describe(row)) + (" @ " + visible(str(refs[0])) if refs[0] else ""))
        if len(rows) > 3:
            print(say("  続きは JSON 出力で確認できます。", "  Additional records are available in JSON output."))
    print(say("未検証のモデル候補（実行契約とは別）: ", "Unverified model candidates, separate from contracts: ")
          + str(capture["counts"]["model_candidates"]))
    print(say("次に選べる操作（大文字の引数は明示して置換）:", "Available next steps; replace uppercase placeholders explicitly:"))
    shown = set()
    for action in capture["next_commands"]:
        purpose = action["purpose"]
        if purpose not in {"PREPARE_SAVED_CONTRACT_TEMPLATE", "SELECT_OWN", "SELECT_DELEGATE",
                           "SAVE_FINITE_CONTRACT_PLAN", "EXPLICITLY_RUN_PLANNED_VERIFIER"} or purpose in shown:
            continue
        shown.add(purpose)
        print("  " + purpose + ": " + visible(action["command"]))
    print(say("チェック登録は PLANNED まで。実行・認可・習得認定は行いません。OWN/DELEGATE は本人の選択です。",
              "Check registration only saves a plan. keep does not execute checks, grant authority or certify mastery. OWN/DELEGATE records a choice."))
    print(visible(result["boundaries"]["message"]))
