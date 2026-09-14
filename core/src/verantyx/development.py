"""A connected work entry over the existing kernel, not another agent runtime."""
from copy import deepcopy
from pathlib import Path
import argparse
import json
import uuid

from .adapters.invocation_journal import InvocationJournal
from .domain.codec import canonical, digest
from .errors import LedgerError
from .personal_skills import read_state, SOURCE_FORMAT, require
from .recovery_bundle import _write_files, save_recovery
from . import constitution

MODES = ("auto", "assisted", "manual")
CATALOG = (
    ("json", ("json", "JSON"), "JSONの値の型と、読み書き時の境界",
     "文字列の3、整数の3、真偽値は別の値です。保存形式の一致とアプリ全体の動作は分けて確認します。",
     "数値を文字列で保存しても同じだと扱う。",
     "今回のファイルで型を変えた場合に、どの検査が失敗するか説明してください。",
     "https://docs.python.org/3/library/json.html"),
    ("arguments", ("argparse", "sys.argv", "ArgumentParser"), "CLIの引数とエラー時の契約",
     "引数の解析、処理、表示を分け、通常入力と不正入力の両方を確認します。",
     "正常入力だけで確認し、引数不足でも成功終了してしまう。",
     "使い方の間違いと処理中の失敗を、終了コードと表示でどう区別しますか。",
     "https://docs.python.org/3/library/argparse.html"),
    ("paths", ("pathlib", "Path(", "worktree"), "ファイルの所有範囲と、元データを壊さない変更",
     "パスの解決と書き込み許可は別です。元ファイル、候補、検証対象を区別します。",
     "相対パスなら必ずプロジェクト内だと決めて書き込む。",
     "今回の処理で、他の作業や元データに影響する書き込みはどこですか。",
     "https://docs.python.org/3/library/pathlib.html"),
    ("retries", ("retry", "再試行", "idempot"), "再試行と二重実行の防止",
     "失敗と結果不明を区別し、同じ依頼の再送で副作用を重ねないようにします。",
     "返答が来ないだけで、最初の処理は実行されていないと決めて再実行する。",
     "同じ依頼を二回送ったとき、何が再利用され、何が再実行されるべきですか。",
     None),
    ("evidence", ("検証", "evidence", "失敗", "テスト"), "この仕事の判断と、反証できる条件",
     "採用理由、適用範囲、失敗する例を分けます。モデルの提案と本人の採用も別に残します。",
     "AIの説明を、実際に通した検査や人間の承認と同一視する。",
     "今回の判断が使えない例を一つ挙げ、どの条件で停止すべきか説明してください。",
     None),
)


def _models(root, configuration):
    from .model_settings import active_adapters
    from .commands_codex import create_configs
    from .personal_skills import roles
    selected = active_adapters(root, configuration)
    if selected is not None:
        return roles(*selected)
    directory = Path(root) / "adapters"
    creator, reviewer = directory / "implementation.json", directory / "verification.json"
    if not creator.exists() and not reviewer.exists() and not (directory / "budget").exists():
        create_configs(directory)
    roles(creator, reviewer)
    return str(creator), str(reviewer)


def _partner(root, configuration, request, *, key, include, target, expectations,
             negative_inputs, allow_contested, continue_from, timeout, constitution_packet=None, assumption=None):
    from .commands_partner import register, dispatch
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers(dest="command", required=True))
    creator, reviewer = _models(root, configuration)
    argv = ["partner", request, "--mode", "implement", "--creator-adapter", creator,
            "--reviewer-adapter", reviewer, "--key", key, "--timeout", str(timeout)]
    for path in include:
        argv.extend(["--include", path])
    if continue_from:
        argv.extend(["--continue-from", continue_from])
    if constitution_packet:
        argv.extend(["--constitution", canonical(dict(constitution_packet))])
    if assumption:
        argv.extend(["--assumption", assumption])
    if expectations:
        argv.extend(["--deliver", "--target", target])
        for condition in expectations:
            argv.extend(["--expect", condition])
        for negative in negative_inputs:
            argv.extend(["--reject-json", negative])
        if allow_contested:
            argv.append("--allow-contested-handoff")
    return dispatch(root, configuration, parser.parse_args(argv), "ja")


def learning_proposals(text, request, files=()):
    """Text signals nominate topics; they do not prove use, correctness or mastery."""
    proposals = []
    for identity, needles, title, model, negative, check, reference in CATALOG:
        if not any(word.casefold() in text.casefold() for word in needles):
            continue
        proposals.append({"concept_id": "work." + identity, "concept": title,
                          "minimum_model": model, "counterexample": negative, "check": check,
                          "why_now": ["今回の依頼・成果物に関連する語が現れたための学習候補です。",
                                      "依頼: " + request[:160],
                                      "関連ファイル: " + ", ".join(list(files)[:8]) if files else "原文との接続を出典で確認できます。"],
                          "reference": reference})
        if len(proposals) == 3:
            break
    if not proposals:
        proposals = [{"concept_id": "work.context-" + digest(request)[:12],
                      "concept": "今回の判断を自分の資産として残す: " + request[:70],
                      "minimum_model": "原文から判断理由、適用条件、未確認の点を区別します。依頼: " + request[:500],
                      "counterexample": "一度の成功を別の条件や別のプロジェクトにも無条件で適用する。",
                      "check": "この仕事を次に任せるとき、繰り返す判断と省ける判断を一つずつ説明してください。",
                      "why_now": ["今回の仕事を、履歴だけでなく再利用する判断へ結び付ける候補です。"],
                      "reference": None}]
    return proposals


def _collect(root, configuration, run_id, source_ref, proposals, key):
    from .learning import control_learning
    candidates = []
    for item in proposals:
        candidate = "work-" + digest({"source": source_ref, "concept": item["concept_id"]})[:32]
        minimum = item["minimum_model"]
        if item.get("reference"):
            minimum += " 関連資料の候補（この実行では取得・確認していません）: " + item["reference"]
        payload = {"id": candidate, "concept": item["concept"], "concept_id": item["concept_id"],
                   "why_now": item["why_now"], "project_anchor": source_ref, "source_refs": [source_ref],
                   "suggested_target": "REVIEW", "minimum_model": minimum,
                   "counterexample": item["counterexample"], "check": item["check"],
                   "system_capture": ["REFERENCE"], "origin": "LOCAL"}
        state = read_state(root, configuration, run_id)
        existing = state.get("learning_candidates", {}).get(candidate)
        if existing:
            require(existing["candidate_hash"] == digest(payload), "WORK_LEARNING_CONFLICT")
        else:
            # Raising a reference is append-only, not a revision-sensitive human decision.
            # A stable intent also survives a crash after the event was committed.
            control_learning(root, configuration, run_id, "raise", candidate_id=candidate,
                             key="work-learning-v2-" + digest({"key": key, "candidate": candidate})[:32],
                             expected_revision=None, concept=item["concept"], concept_id=item["concept_id"],
                             why_now=item["why_now"], minimum_model=minimum,
                             counterexample=item["counterexample"], check=item["check"],
                             source_refs=[source_ref])
        candidates.append(candidate)
    return candidates


def _annotate(root, configuration, run_id, *, request, origin, summary, text, mode, key, task_gate=None):
    from .external_capture import capture
    proposals = learning_proposals(text, request, summary.get("files", []))
    if summary.get("status") in ("MODEL_CALL_FAILED", "MODEL_OUTCOME_UNKNOWN"):
        proposals = [{
            "concept_id": "work.model-failure", "concept": "AIの失敗と結果不明を区別し、二重実行を防ぐ",
            "minimum_model": "失敗した依頼も履歴と出典を保持します。今回の停止理由: "
                             + summary["error"]["code"]
                             + "。応答を採用できないことと、外部で処理されなかったことは別です。",
            "counterexample": "タイムアウトや検証不一致を成功扱いする、または同じ仕事を無条件で再送する。",
            "check": "この記録から確定できることと、不明なことを一つずつ挙げてください。",
            "why_now": ["今回のモデル処理が停止したため。成功例ではなく失敗・未確定事例に接続します。",
                        "依頼: " + request[:160]], "reference": None,
        }, *proposals[:2]]
    label = {"format": SOURCE_FORMAT, "origin_project": origin[:100], "label": request[:100],
             "development": {k: summary[k] for k in ("status", "artifact_directory", "judgment_run")
                             if summary.get(k)}}
    label_text = canonical(label)
    require(len(label_text) <= 1000, "WORK_LABEL_LIMIT")
    body = canonical({"format": "verantyx.work-recovery.v1", "request": request,
                      "summary": summary, "learning_candidates": proposals, "task_gate": task_gate or {},
                      "authority": "REFERENCE_NOT_APPROVAL", "capture_mode": mode})
    capture_key = "work-source-" + digest(key)[:32]
    capture_id = digest({"capture_key": capture_key, "run_id": run_id})
    intent_hash = digest({"run_id": run_id, "body": body, "label": label_text})
    with InvocationJournal(root, "connected-work-recovery", key) as journal:
        started = journal.read("started")
        if started:
            require(started["intent_hash"] == intent_hash, "WORK_RECOVERY_CONFLICT")
        finished = journal.read("finished")
        if finished:
            return finished
        if not started:
            state = read_state(root, configuration, run_id)
            started = {"intent_hash": intent_hash, "basis_revision": state["revision"]}
            journal.write("started", started)
        captured = journal.read("captured")
        if captured is None:
            state = read_state(root, configuration, run_id)
            existing = next((item for item in state.get("external_captures", [])
                             if item["id"] == capture_id), None)
            if existing:
                require(existing["body"] == body
                        and existing["provenance"]["source_label"] == label_text
                        and existing["provenance"]["provider"] == "verantyx"
                        and existing["provenance"]["model"] == "none", "WORK_RECOVERY_CONFLICT")
                captured = {"source_ref": existing["source_ref"]}
            else:
                value = capture(root, configuration, run_id, body=body, provider="verantyx", model="none",
                                key=capture_key, expected_revision=started["basis_revision"],
                                adapter_path=None, source_label=label_text, content_format="json", locale="ja")
                captured = {"source_ref": value["capture_source_ref"]}
            journal.write("captured", captured)
        candidates = [] if mode == "manual" else _collect(
            root, configuration, run_id, captured["source_ref"], proposals, key)
        value = {"learning_candidates": candidates, "learning_proposals": proposals,
                 "source_ref": captured["source_ref"],
                 "recovery_bundle": save_recovery(root, configuration, run_id)}
        journal.write("finished", value)
        return value


def _failed_model_summary(error):
    """Record a call/hand-off failure, never turn storage or scope errors into success."""
    code = error.code
    recoverable = code in {
        "BRIDGE_PROCESS_FAILED", "BRIDGE_TIMEOUT", "BRIDGE_OUTPUT_INVALID",
        "BRIDGE_OUTCOME_UNKNOWN", "BRIDGE_IN_FLIGHT", "BRIDGE_ALREADY_INVOKED",
        "BRIDGE_PREVIOUSLY_FAILED", "JOB_OUTCOME_UNKNOWN",
        "SHARED_CONTEXT_SOURCE", "SHARED_CONTEXT_STALE",
    } or (code.startswith("CODEX_") and any(
        marker in code for marker in ("CALL_FAILED", "OUTCOME_UNKNOWN", "IN_FLIGHT")))
    if not recoverable:
        raise error
    uncertain = any(word in code for word in ("TIMEOUT", "UNKNOWN", "IN_FLIGHT", "ALREADY_INVOKED"))
    detail = {"code": code}
    if type(error.details.get("returncode")) is int:
        detail["returncode"] = error.details["returncode"]
    return {"status": "MODEL_OUTCOME_UNKNOWN" if uncertain else "MODEL_CALL_FAILED",
            "files": [], "error": detail, "reason": code, "evidence": "UNKNOWN",
            "automatic_retry": False, "canonical_adopted": False,
            "next_action": "保存した出典と失敗理由を確認し、再依頼は本人が明示的に選びます。"}


def _save_candidate(root, result, allow_contested):
    from .partner_delivery import delivery_authorization
    from .adapters.observations import normalize_path
    state = result["state"]
    handoff = delivery_authorization(state, allow_contested_handoff=allow_contested)
    if not handoff["allowed"]:
        return {"status": "BLOCKED", "reason": handoff["reason"], "handoff": handoff, "files": []}
    document = (state.get("editor_attempt") or {}).get("document") or {}
    files = document.get("files") or {}
    require(0 < len(files) <= 16, "WORK_FILE_COUNT")
    parts = ("vera-work", result["run_id"], digest(document))
    for path, body in files.items():
        normalize_path(path)
        require(isinstance(body, str) and len(body.encode("utf-8")) <= 65536, "WORK_FILE_SIZE")
    _write_files(root, parts, {"receipt.json": (canonical({
        "format": "verantyx.work-candidate.v1", "parent_run": result["run_id"],
        "handoff": handoff, "original_editor": document, "canonical_adopted": False,
        "generated_code_executed": False}) + "\n").encode("utf-8")})
    for path, body in files.items():
        bits = path.split("/")
        _write_files(root, (*parts, "files", *bits[:-1]), {bits[-1]: body.encode("utf-8")})
    return {"status": "CANDIDATE_SAVED", "files": sorted(files),
            "artifact_directory": "/".join((*parts, "files")), "handoff": handoff,
            "evidence": "UNVERIFIED", "canonical_adopted": False}


def run_work(root, configuration, *, request, key, include=(), target=None, expectations=(),
             negative_inputs=(), mode="assisted", allow_contested=False, continue_from=None,
             timeout=120, origin=None, assumption=None):
    root = Path(root).resolve()
    require(mode in MODES and isinstance(request, str) and bool(request.strip()), "WORK_REQUEST")
    require(not expectations or target, "WORK_TARGET_REQUIRED")
    require(expectations or not (target or negative_inputs), "WORK_UNUSED_CONDITIONS")
    if expectations:
        from .judgment_compiler import compile_conditions
        compile_conditions(target, expectations, negative_inputs)
    task_gate = constitution.prepare(root, configuration, request, assumption=assumption)
    if task_gate["status"] in ("ASK_ONE_DECISION", "UNKNOWN"):
        return {"ok": False, "command": "develop",
                "status": "DECISION_REQUIRED" if task_gate["status"] == "ASK_ONE_DECISION" else "UNKNOWN_CONTEXT",
                "request": request, "task_gate": task_gate, "model_calls": 0,
                "next_action": task_gate.get("question")}
    intent = {"request": request, "include": list(include), "target": target,
              "expectations": list(expectations), "negative_inputs": list(negative_inputs),
              "mode": mode, "allow_contested": allow_contested, "continue_from": continue_from,
              "timeout": timeout, "origin": origin, "task_gate": task_gate}
    with InvocationJournal(root, "connected-work", key) as journal:
        started = journal.read("started")
        if started:
            require(started["intent_hash"] == digest(intent), "WORK_IDEMPOTENCY_CONFLICT")
        finished = journal.read("finished")
        if finished:
            return {**finished, "project_root": str(root), "duplicate": True,
                    "historical_receipt": True, "new_model_calls": 0}
        if not started:
            journal.write("started", {"intent_hash": digest(intent)})
        outcome = journal.read("outcome")
        if outcome is None:
            try:
                result = _partner(root, configuration, request, key=key, include=include, target=target,
                                  expectations=expectations, negative_inputs=negative_inputs,
                                  allow_contested=allow_contested, continue_from=continue_from, timeout=timeout,
                                  constitution_packet=task_gate["constitution"],
                                  assumption=task_gate.get("human_assumption"))
            except LedgerError as error:
                summary = _failed_model_summary(error)
                run_id = "partner-" + digest({"project": configuration["project"]["id"], "key": key})[:32]
                # Model processing has an existing request. Do not invent an AI run
                # for configuration failures that occurred before that request existed.
                read_state(root, configuration, run_id)
                outcome = {"run_id": run_id, "summary": summary, "delivery": None, "text": request}
            else:
                run_id = result["run_id"]
                delivery = result.get("delivery")
                if delivery:
                    summary = {"status": delivery["status"], "files": [target],
                               "handoff": delivery.get("handoff"), "reason": delivery.get("reason"),
                               "judgment_run": delivery.get("run_id"),
                               "artifact_directory": str(Path(delivery["artifact"]).parent.relative_to(root))
                                   if delivery.get("artifact") else None,
                               "asset_id": delivery.get("asset_id"),
                               "evidence": delivery.get("closure", "UNKNOWN")}
                else:
                    summary = _save_candidate(root, result, allow_contested)
                document = (result["state"].get("editor_attempt") or {}).get("document") or {}
                body = request + "\n" + document.get("notes", "") + "\n" + "\n".join(
                    (document.get("files") or {}).values())
                outcome = {"run_id": run_id, "summary": summary, "delivery": delivery, "text": body}
            # An interrupted local export resumes here without another model attempt.
            journal.write("outcome", outcome)
        run_id, summary = outcome["run_id"], outcome["summary"]
        recovered = _annotate(root, configuration, run_id, request=request, origin=origin or root.name,
                              summary=summary, text=outcome["text"], mode=mode, key=key, task_gate=task_gate)
        value = {"ok": summary["status"] in ("COMPLETE_BOUNDED", "CANDIDATE_SAVED"),
                 "command": "develop", "project_root": str(root), "run_id": run_id, "request": request,
                 **summary, **recovered, "delivery": outcome["delivery"], "duplicate": False,
                 "automatic_rule_promotion": False, "human_mastery": "NOT_ASSESSED",
                 "canonical_adopted": False, "capture_mode": mode, "task_gate": task_gate}
        journal.write("finished", value)
        return value


def import_job(root, configuration, *, path, origin, label, mode, key,
               target=None, expectations=(), negative_inputs=()):
    from .external_capture import read_body
    from .personal_skills import import_work
    root = Path(root).resolve()
    require(mode in MODES, "WORK_CAPTURE_MODE")
    require(not expectations or target, "WORK_TARGET_REQUIRED")
    require(expectations or not (target or negative_inputs), "WORK_UNUSED_CONDITIONS")
    contract = None
    if expectations:
        from .judgment_compiler import compile_conditions
        contract = compile_conditions(target, expectations, negative_inputs)
    # Auto import invokes the local two-role model builder.  Do not let that
    # alternate entrance bypass the same human-decision boundary as develop.
    task_gate = constitution.prepare(root, configuration, "外部AI仕事の自動資産化: " + label)
    if mode == "auto" and task_gate["status"] in ("ASK_ONE_DECISION", "UNKNOWN"):
        return {"ok": False, "command": "develop",
                "status": "DECISION_REQUIRED" if task_gate["status"] == "ASK_ONE_DECISION" else "UNKNOWN_CONTEXT",
                "request": label, "task_gate": task_gate, "model_calls": 0,
                "next_action": task_gate.get("question")}
    body = read_body(path)
    intent = {"source_path": str(Path(path).expanduser().resolve()), "body_hash": digest(body),
              "origin": origin, "label": label, "mode": mode, "contract": contract, "task_gate": task_gate}
    with InvocationJournal(root, "connected-import", key) as journal:
        started = journal.read("started")
        if started:
            require(started["intent_hash"] == digest(intent), "WORK_IDEMPOTENCY_CONFLICT")
        finished = journal.read("finished")
        if finished:
            return {**finished, "project_root": str(root), "duplicate": True,
                    "historical_receipt": True, "new_model_calls": 0}
        if not started:
            journal.write("started", {"intent_hash": digest(intent)})
        adapters = {}
        if mode == "auto":
            creator, reviewer = _models(root, configuration)
            adapters = {"creator_adapter": creator, "reviewer_adapter": reviewer}
        try:
            imported = import_work(root, configuration, body=body, origin_project=origin,
                                   label=label, provider="explicit-import", model="unspecified",
                                   key=key, mode=mode, **adapters)
        except LedgerError as error:
            summary = _failed_model_summary(error)
            run_id = "skill-" + digest({"project": configuration["project"]["id"], "key": key})[:32]
            read_state(root, configuration, run_id)
            summary["source_project"] = origin
        else:
            run_id = imported["run_id"]
            summary = {"status": "SOURCE_RECORDED", "files": [], "source_project": origin}
            if contract:
                from .partner_delivery import judge_target
                checked = judge_target(root, configuration, run_id, contract,
                                       key="import-check-" + digest(key)[:32],
                                       reason="Explicit conditions supplied while importing " + label)
                summary.update(status=checked["status"], judgment_run=checked["run_id"],
                               evidence=checked["closure"], asset_id=checked["asset_id"], files=[target])
        recovered = _annotate(root, configuration, run_id, request=label, origin=origin, summary=summary,
                              text=body, mode=mode, key="import-" + key, task_gate=task_gate)
        value = {"ok": summary["status"] in ("SOURCE_RECORDED", "COMPLETE_BOUNDED"),
                 "command": "develop", "project_root": str(root), "run_id": run_id, "request": label,
                 **summary, **recovered, "model_calls_for_recovery": 0, "duplicate": False,
                 "capture_mode": mode, "canonical_adopted": False, "human_mastery": "NOT_ASSESSED",
                 "task_gate": task_gate}
        journal.write("finished", value)
        return value


def work_summaries(root, configuration):
    """Read work and its explicit check references, never confer permissions.

    Activity follows ledger order, not the random/hash-based run identifier.
    Legacy checks without a recorded parent remain visible as standalone work.
    A child's finite result does not replace its parent's build assessment.
    """
    from .storage.sqlite import EventStore
    from .assets import project_assets
    with EventStore(root, configuration["project"]["id"]) as store:
        snapshot = store.project_snapshot()
    activity, recorded_at = {}, {}
    for sequence, event in enumerate(snapshot["events"], 1):
        activity[event["stream_id"]] = sequence
        recorded_at[event["stream_id"]] = event["recorded_at"]
    rows, parent_links = {}, {}
    for state in snapshot["states"]:
        run_id = state["run_id"]
        label, metadata = state.get("request", run_id)[:100], {}
        for source in state.get("external_captures", []):
            try:
                item = json.loads(source["provenance"]["source_label"])
            except (ValueError, TypeError):
                continue
            if isinstance(item, dict) and item.get("format") == SOURCE_FORMAT:
                if isinstance(item.get("label"), str):
                    label = item["label"]
                if isinstance(item.get("development"), dict):
                    metadata = item["development"]
        assets = project_assets(state, "ja")
        retained = {key: metadata[key] for key in ("status", "artifact_directory", "judgment_run")
                    if isinstance(metadata.get(key), str)}
        row = {"run_id": run_id, "label": label, "revision": state["revision"],
               "status": retained.get("status", "RECORDED"), **retained,
               "failures": len(assets["failure_cases"]),
               "methods": len(assets["verification_methods"]) + len(assets["execution_methods"]),
               "last_recorded_at": recorded_at.get(run_id), "activity_order": activity.get(run_id, 0),
               "state": state, "related_runs": [run_id], "checks": [],
               "relationship_scope": "NAVIGATION_ONLY_NOT_AUTHORIZATION"}
        if run_id.startswith("judgment-"):
            # Read the result from the actual verifier, not from imported prose.
            verifications = state.get("verifications", {})
            verification = (verifications.get(metadata.get("verification_id"))
                            if isinstance(metadata.get("verification_id"), str) else None)
            if verification is None and len(verifications) == 1:
                verification = next(iter(verifications.values()))
            if verification:
                closure = ((verification.get("receipt") or {}).get("result") or {}).get("closure", "UNKNOWN")
                row["status"] = ("COMPLETE_BOUNDED" if closure == "BOUNDED" else
                                 "REFUTED" if closure == "REFUTED" else "INCOMPLETE")
                row["target"] = verification["plan"]["spec"]["target_path"]
                if metadata.get("kind") == "FINITE_JUDGMENT" and isinstance(metadata.get("parent_run"), str):
                    parent_links[run_id] = metadata["parent_run"]
        rows[run_id] = row

    # Older one-shot deliveries already carried this explicit child run ID.
    for row in rows.values():
        child = row.get("judgment_run")
        if child in rows and child.startswith("judgment-"):
            if child not in parent_links:
                parent_links[child] = row["run_id"]
            elif parent_links[child] != row["run_id"]:
                parent_links[child] = None  # Conflicting references never hide a record.
    linked = set()
    for child, parent in parent_links.items():
        if parent not in rows or parent.startswith("judgment-") or child == parent:
            continue
        check, work = rows[child], rows[parent]
        work["checks"].append({key: check[key] for key in (
            "run_id", "label", "revision", "status", "target", "methods", "failures",
            "last_recorded_at", "activity_order") if key in check})
        work["methods"] += check["methods"]
        work["failures"] += check["failures"]
        if check["activity_order"] > work["activity_order"]:
            work["activity_order"] = check["activity_order"]
            work["last_recorded_at"] = check["last_recorded_at"]
        linked.add(child)
    for row in rows.values():
        row["checks"].sort(key=lambda check: check["activity_order"], reverse=True)
        row["related_runs"] += [check["run_id"] for check in row["checks"]]
    return sorted((row for run_id, row in rows.items() if run_id not in linked),
                  key=lambda row: row["activity_order"], reverse=True)


def dispatch(root, configuration, args):
    if args.input:
        return import_job(root, configuration, path=args.input,
                          origin=args.origin_project or Path(args.input).parent.name,
                          label=args.request or Path(args.input).name, mode=args.capture_mode, key=args.key or uuid.uuid4().hex,
                          target=args.target, expectations=args.expect, negative_inputs=args.reject_json)
    if args.request:
        return run_work(root, configuration, request=args.request, key=args.key or uuid.uuid4().hex,
                        include=args.include, target=args.target, expectations=args.expect,
                        negative_inputs=args.reject_json, mode=args.capture_mode,
                        allow_contested=args.allow_contested_handoff,
                        continue_from=args.continue_from, origin=args.origin_project, assumption=args.assumption)
    return {"ok": False, "command": "develop", "status": "INTERACTIVE_REQUIRED",
            "project_root": str(Path(root).resolve()),
            "reason": "対話メニューは端末から引数なしの develop で開始してください。"}
