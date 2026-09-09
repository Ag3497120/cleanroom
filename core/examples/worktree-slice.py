#!/usr/bin/env python3
"""Synthetic, disposable two-task demonstration using the actual .cross/Precedent backends."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from verantyx import config
from verantyx.application import record_run
from verantyx.effects import authorize, execute, inspect_workspace
from verantyx.governance import control
from verantyx.storage.sqlite import EventStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--precedent", required=True)
    args = parser.parse_args()
    root = Path(args.output).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=False)
    cfg = config.defaults(root, "ja")
    config.save(root, cfg, None)
    def git(*values):
        subprocess.run(["git", "-C", str(root), "-c", "core.hooksPath=/dev/null", *values], check=True, capture_output=True)
    git("init", "-q")
    (root / "calc.py").write_text("def add(a, b):\n    return 0\n")
    (root / "test_calc.py").write_text("import unittest\nfrom calc import add\nclass Check(unittest.TestCase):\n    def test_cases(self):\n        self.assertEqual(add(2, 3), 5)\n        self.assertEqual(add(-3, 2), -1)\n")
    git("add", "calc.py", "test_calc.py")
    git("-c", "user.name=Verantyx Fixture", "-c", "user.email=fixture@invalid", "commit", "-qm", "Synthetic validation fixture")
    (root / "calc.py").write_text("# Synthetic first writer's unpublished change\ndef add(a, b):\n    return 0\n")
    initial = (root / "calc.py").read_bytes()
    # Proposal documents stay outside the observed repository; later proposals cannot change an earlier lease's premise.
    proposal_dir = root / ".verantyx/fixture-proposals"
    proposal_dir.mkdir()
    def task(name, body="def add(a, b):\n    return a + b\n"):
        document = {"schema_version": 1, "task_id": name, "context_revision": 0, "response_locale": "ja",
                    "summary": "検証用の記録済み提案。実際の人間の判断履歴ではありません。", "claims": [], "unknowns": [],
                    "decision_points": [{"id": "separate", "kind": "VALUE_DECISION", "decision_type": "parallel_writers",
                                         "question": "未完了の変更を残すため、作業場所を分離しますか？",
                                         "options": [{"id": "isolate", "label": "個別worktree"}, {"id": "shared", "label": "共有worktree"}]}],
                    "actions": [{"id": "writer", "tool_id": "writer.apply", "arguments": {
                        "point_id": "separate", "destination": "shared", "files": {"calc.py": body}, "tests": ["test_calc.py"]},
                        "reason": "二つ目のwriterによる候補の適用", "source_refs": []}]}
        path = proposal_dir / (name + ".json")
        path.write_text(json.dumps(document, ensure_ascii=False))
        return record_run(root, cfg, request="検証用: 二つ目のwriterが修正候補を作る", run_id=name, proposal_path=path,
                          context={"component": "writer", "workload": "parallel", "risk": "HIGH"}, key=name)
    def operator(operation, target, **values):
        with EventStore(root, cfg["project"]["id"], create=True) as store:
            return control(store, cfg, operation, target, **values)
    first = task("first")
    inspect_workspace(root, cfg, "first", args.precedent, "inspect-first")
    case = operator("decide", "first", point_id="separate", choice="isolate",
                    reason="検証用の選択: 未コミット変更を共有先への書き込みから保護する")["precedent_id"]
    operator("precedent-accept", case)
    rule = operator("rule-draft", case)["rule_id"]
    operator("rule-shadow", rule)
    operator("rule-confirm", rule)
    active = operator("rule-activate", rule)
    first_lease = authorize(root, cfg, "first", "writer", args.precedent, "first-lease")
    first_receipt = execute(root, cfg, "first", first_lease["lease_id"], args.precedent, "first-exec")
    second = task("second")
    second_lease = authorize(root, cfg, "second", "writer", args.precedent, "second-lease")
    second_receipt = execute(root, cfg, "second", second_lease["lease_id"], args.precedent, "second-exec")
    task("negative-control", "def add(a, b):\n    return 5\n")
    bad_lease = authorize(root, cfg, "negative-control", "writer", args.precedent, "negative-lease")
    bad_receipt = execute(root, cfg, "negative-control", bad_lease["lease_id"], args.precedent, "negative-exec")
    preserved = (root / "calc.py").read_bytes() == initial
    task("stale-authorization")
    stale_lease = authorize(root, cfg, "stale-authorization", "writer", args.precedent, "stale-lease")
    (root / "calc.py").write_text("# Synthetic edit after authorization\n")
    stale = execute(root, cfg, "stale-authorization", stale_lease["lease_id"], args.precedent, "stale-exec")
    report = {
        "fixture": True, "real_user_decisions": False, "live_model_calls": 0, "project": str(root), "rule_id": rule,
        "first_question": first["state"]["assessment"]["question"], "second_question": second["state"]["assessment"]["question"],
        "second_judgment": second["state"]["assessment"]["judgments"][0],
        "first_receipt": first_receipt["execution"], "second_receipt": second_receipt["execution"],
        "negative_control": bad_receipt["execution"], "stale_authorization": stale["execution"],
        "uncommitted_change_preserved_before_deliberate_stale_edit": preserved,
        "human_delta": active["state"]["deltas"]["human_delta"],
    }
    report["passed"] = (preserved and report["second_question"] is None
        and report["second_judgment"]["status"] == "PRECEDENT_MATCHED"
        and second_receipt["execution"]["receipt"]["verification"]["closure"] == "BOUNDED"
        and bad_receipt["execution"]["receipt"]["verification"]["closure"] == "REFUTED"
        and stale["execution"]["status"] == "INVALIDATED"
        and not Path(stale["execution"]["lease"]["resource_scope"]).exists())
    with EventStore(root, cfg["project"]["id"]) as store:
        archive = store.export()
    (root / "events.jsonl").write_text(archive)
    (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "report": str(root / "report.json"),
                      "events": str(root / "events.jsonl")}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
