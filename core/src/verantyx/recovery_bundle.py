"""Materialize existing judgments and skills; never invent a verifier or authority."""
from copy import deepcopy
import os
from pathlib import Path

from .domain.codec import canonical, digest
from .errors import LedgerError

FORMAT = "verantyx.recovery-bundle.v1"
MAX_BUNDLE = 4 * 1024 * 1024


def project_bundle(state, policy_state):
    from .assets import project_assets
    from .learning import project_learning
    from .skill_report import summarize_state
    assets = project_assets(state, "ja")
    methods = []
    for method in assets["verification_methods"] + assets["execution_methods"]:
        item = {**deepcopy(method), "portable_execution": False,
                "remaining": "REQUIRES_ORIGINAL_EXECUTOR_AND_NEW_AUTHORIZATION"}
        if method["family"] == "VERIFICATION":
            spec = deepcopy(state["verifications"][method["plan_id"]]["plan"]["spec"])
            from .domain.verification import validate_spec
            validate_spec(spec)
            item["spec"] = spec
            item["portable_execution"] = spec["method"] in ("TEST", "NEGATIVE_CONTROL")
            item["remaining"] = None if item["portable_execution"] else "NOT_A_STANDALONE_PREDICATE_TEST"
        elif method["family"] == "ORACLE":
            # Keep the fixed cases as private reference data. The existing
            # portable replay family gate must never execute this Python spec.
            spec = deepcopy(state["oracles"][method["plan_id"]]["plan"]["spec"])
            from .domain.oracles import validate_spec
            validate_spec(spec)
            item.update(spec=spec, portable_execution=False,
                        remaining="REQUIRES_FRESH_ORACLE_PLAN_AND_SANDBOX")
        methods.append(item)
    learning = project_learning(state)
    dictionary = {"learn": [], "reference": [], "delegate": []}
    for candidate in learning:
        item = deepcopy(candidate)
        explicit = not item.get("target_is_suggestion", True)
        # A suggestion to delegate is not the person's actual choice.
        destination = ("delegate" if explicit and item["ownership_target"] == "DELEGATE"
                       else "reference" if item["ownership_target"] == "REFERENCE" else "learn")
        dictionary[destination].append(item)
    policies = [deepcopy(row) for row in policy_state["policies"]
                if row["run_id"] == state["run_id"]]
    executable_count = sum(row["family"] == "VERIFICATION" and row["portable_execution"] for row in methods)
    oracle_count = sum(row["family"] == "ORACLE" for row in methods)
    remaining = [] if executable_count else ["NO_PORTABLE_EXECUTABLE_CONTRACT"]
    if oracle_count:
        remaining.append("REQUIRES_FRESH_ORACLE_PLAN_AND_SANDBOX")
    payload = {
        "format": FORMAT, "project_id": state["project_id"], "run_id": state["run_id"],
        "revision": state["revision"], "policy_revision": policy_state["revision"],
        "request_ref": state["request_ref"], "completion": summarize_state(state),
        "human_judgments": deepcopy(list(state.get("human_decisions", {}).values())),
        "methods": methods, "failures": assets["failure_cases"],
        "uncompiled_candidates": assets["reuse_candidates"],
        "dictionary": dictionary, "policies": policies,
        "executable_count": executable_count,
        "oracle_method_count": oracle_count,
        "executor_required_count": sum(not row["portable_execution"] for row in methods),
        "model_calls": 0, "authority": "REFERENCE_ONLY",
        "capture_coverage": "KERNEL_COMMANDS_AND_EXPLICIT_IMPORTS",
        "privacy": "LOCAL_PRIVATE_EXPORT_REVIEW_BEFORE_SHARING",
        "remaining": remaining,
        "boundaries": [
            "Historical evidence does not certify the current target or arbitrary prose.",
            "Classification and self-explanation do not certify human mastery.",
            "A bundle is not permission to run commands, write files, or activate policies.",
            "The content hash detects changes, not authorship or authenticity.",
            "Portable replay uses the installed Verantyx predicate engine, not an AI model.",
            "Oracle history requires an explicit target, current observations, the original engine, a fresh oracle plan, sandbox and new authorization.",
            "Oracle inputs and expectations are reference data; portable replay never executes candidate Python.",
        ],
    }
    if len(canonical(payload).encode("utf-8")) > MAX_BUNDLE:
        raise LedgerError("DOCUMENT_LIMIT")
    return {"bundle_id": digest(payload), "payload": payload}


def render(bundle):
    data = bundle["payload"]
    lines = [
        "# 仕事から回収した判断と学習",
        "",
        "この記録は既存台帳のスナップショットです。原文や失敗履歴を上書きしません。",
        "",
        "仕事: " + data["run_id"],
        "記録版: " + str(data["revision"]),
        "ID: " + bundle["bundle_id"],
        "",
        "## システムに残ったもの",
        "",
        "- 人間の判断: " + str(len(data["human_judgments"])),
        "- 記録済みの方法: " + str(len(data["methods"])),
        "- 単独で再検査できる有限契約: " + str(data["executable_count"]),
        "- 新規oracle計画と隔離実行が必要な方法: " + str(data.get("oracle_method_count", 0)),
        "- 失敗事例: " + str(len(data["failures"])),
        "- 実行条件へ変換されていない候補: " + str(len(data["uncompiled_candidates"])),
        "",
    ]
    oracle_methods = [method for method in data["methods"] if method["family"] == "ORACLE"]
    if oracle_methods:
        lines.extend([
            "## 別プロセスoracleの履歴",
            "",
            "以下は固定入出力の過去の観測です。replay.pyから任意Pythonを実行する契約ではありません。",
            "再利用には明示対象・現在の観測・元エンジン・新規oracle-plan/oracle-run・隔離条件・新規許可が必要です。",
            "",
        ])
        for method in oracle_methods:
            target = method.get("target_binding", {})
            lines.extend([
                "### " + method["name"],
                "",
                "- 方法ID: " + method["id"],
                "- 有限範囲: " + method.get("scope", "UNKNOWN"),
                "- 元の対象: " + str(method["target"]),
                "- 対象SHA-256: " + target.get("sha256", "UNKNOWN"),
                "- 元エンジンhash: " + method.get("engine_hash", "UNKNOWN"),
                "- 再利用条件: " + method["remaining"],
                "- 出典: " + ", ".join(method["source_refs"]),
            ])
            for outcome in method.get("outcome_history", []):
                lines.append("- 履歴: " + outcome["outcome"] + " / " + str(outcome["closure"])
                             + " / " + outcome["source_ref"])
                checks, controls = outcome["checks"], outcome["negative_controls"]
                if checks:
                    lines.append("  有限入力の一致: " + str(sum(row.get("passed") is True for row in checks))
                                 + "/" + str(len(checks)))
                if controls:
                    lines.append("  比較器の反例値拒否: " + str(sum(row.get("rejected") is True for row in controls))
                                 + "/" + str(len(controls)))
                if outcome.get("reason"):
                    lines.append("  未確定・失敗理由: " + outcome["reason"])
            lines.append("")
    lines.extend(["## 自分に残す理解", ""])
    for group, heading in (("learn", "学ぶ候補"), ("reference", "参照でよいもの"),
                           ("delegate", "明示的に委譲したもの")):
        lines.extend(["### " + heading, ""])
        for item in data["dictionary"][group]:
            selected = "候補" if item.get("target_is_suggestion", True) else "明示的な選択"
            lines.extend([
                "- " + item["concept"] + " / " + item["ownership_target"] + " / " + selected,
                "",
                "最小限の理解: " + str(item.get("minimum_model", "")),
                "",
                "反例: " + str(item.get("counterexample", "")),
                "",
                "自分で確かめる問い: " + str(item.get("check", "")),
                "",
            ])
        if not data["dictionary"][group]:
            lines.extend(["未記録。本人の理解や委譲を推測しません。", ""])
    lines.extend([
        "## 元のモデルを使わずに再検査する",
        "",
        "VerantyxをインストールしたPythonで、同じフォルダの replay.py を実行します。",
        "元の会話・プロジェクトDB・AIの認証情報は使いません。",
        "",
        "    python replay.py --list",
        "    python replay.py --asset ASSET_ID --root TARGET_DIRECTORY --target RELATIVE_FILE",
        "",
        "対象は毎回明示します。ファイルを読む有限検証だけを実行し、コマンド実行や修復はしません。",
        "終了コード: 0=有限条件内で成立、1=反証、2=不明または実行不可。",
        "OBSERVATION、REPRODUCTION、コマンド、任意Pythonオラクルは、この入口では実行しません。",
        "",
        "## 意味の限界",
        "",
        "有限検査が通っても、自然言語の主張全体・実装全体・人間の習熟は証明しません。",
        "保存した方針は履歴です。このフォルダを渡しても実行権限は移転しません。",
        "ハッシュは改変検知用で、作成者の署名ではありません。",
        "判断理由や教材には個人情報が含まれ得ます。公開前に内容を確認してください。",
        "",
    ])
    if data["remaining"]:
        lines.extend(["未完了: " + ", ".join(data["remaining"]), ""])
    return "\n".join(lines)


LAUNCHER = """#!/usr/bin/env python3
from pathlib import Path
from verantyx.recovery_replay import main

if __name__ == "__main__":
    raise SystemExit(main(bundle_path=Path(__file__).with_name("manifest.json")))
"""


def _write_files(root, parts, files):
    """Descriptor-relative creation; no overwrites and no symlink traversal."""
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts:
            try:
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        for name, body in files.items():
            try:
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=descriptor)
            except FileExistsError:
                from .adapters.observations import read_document
                # Read through the held directory descriptor, not a replaced ancestor.
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=descriptor)
                import stat
                with os.fdopen(fd, "rb") as existing:
                    if not stat.S_ISREG(os.fstat(existing.fileno()).st_mode):
                        raise LedgerError("RECOVERY_OUTPUT_CHANGED")
                    if existing.read(len(body) + 1) != body:
                        raise LedgerError("RECOVERY_OUTPUT_CHANGED")
            else:
                with os.fdopen(fd, "wb") as output:
                    output.write(body)
                    output.flush()
                    os.fsync(output.fileno())
    finally:
        os.close(descriptor)


def save_recovery(root, configuration, run_id):
    from .adapters.proposal_validation import valid_id
    from .personal_skills import read_state
    from .skill_policy import policy_snapshot
    if not valid_id(run_id):
        raise LedgerError("ARGUMENTS")
    state = read_state(root, configuration, run_id)
    bundle = project_bundle(state, policy_snapshot(root, configuration))
    parts = ("vera-recovery", run_id, bundle["bundle_id"])
    directory = Path(root).joinpath(*parts)
    document = render(bundle)
    files = {
        "manifest.json": (canonical(bundle) + "\n").encode("utf-8"),
        "README.md": document.encode("utf-8"),
        "replay.py": LAUNCHER.encode("utf-8"),
    }
    receipt = {"bundle_id": bundle["bundle_id"],
               "files": {name: __import__("hashlib").sha256(body).hexdigest()
                         for name, body in files.items()}}
    # Written last: a partial export cannot look like a completed receipt.
    files["receipt.json"] = (canonical(receipt) + "\n").encode("utf-8")
    _write_files(root, parts, files)
    return {
        "status": "SAVED", "bundle_id": bundle["bundle_id"], "run_id": run_id,
        "revision": state["revision"], "directory": str(directory),
        "readme": str(directory / "README.md"), "manifest": str(directory / "manifest.json"),
        "replay": str(directory / "replay.py"),
        "executable_count": bundle["payload"]["executable_count"],
        "method_count": len(bundle["payload"]["methods"]),
        "oracle_method_count": bundle["payload"]["oracle_method_count"],
        "executor_required_count": bundle["payload"]["executor_required_count"],
        "remaining": bundle["payload"]["remaining"], "model_calls": 0,
        "published": False, "authority": "REFERENCE_ONLY",
    }


def attach_recovery(root, configuration, result):
    """Export failure must not hide a successful job or trigger another AI call."""
    try:
        recovery = save_recovery(root, configuration, result["run_id"])
    except (LedgerError, OSError) as error:
        recovery = {"status": "INCOMPLETE", "reason": getattr(error, "code", "OUTPUT_UNAVAILABLE"),
                    "model_calls": 0, "automatic_retry": False}
    return {**result, "recovery_bundle": recovery}
