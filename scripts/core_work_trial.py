"""Opt-in live trials. Never invoked by unit-test discovery.

Uses the same Work / Reflection gateway and authority scope as the CLI.
Calls the user's selected subscription sequentially. No model calls on import.
Artifacts, raw results and trial receipts stay outside the source repository.
"""
import argparse
import json
import time
import uuid
from pathlib import Path

from verantyx import config
from verantyx.cli import main as cli_main
from verantyx.development_console import _mutate
from verantyx.agent_runtime import run_work
from verantyx.model_settings import activate_codex
from verantyx.owner_experience import cards


CASES = Path(__file__).resolve().parents[1] / "core/tests/fixtures/core_work_scenarios.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=("mouth", "bicycle", "signal", "irrigation"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--feedback", default="")
    parser.add_argument("--continue-from")
    parser.add_argument("--asset", action="append", default=[])
    args = parser.parse_args()
    case = next(row for row in json.loads(CASES.read_text())["cases"] if row["id"] == args.case)
    root = args.root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    configuration, _ = config.load(root)
    if configuration is None:
        code = cli_main(["--project", str(root), "--lang", "ja", "setup", "--non-interactive",
                         "--name", "Core trial / " + args.case,
                         "--purpose", "Test fixture: retain human purpose, understanding and evidence.",
                         "--learning", "digest", "--max-items", "2"])
        if code:
            raise SystemExit(code)
        configuration, _ = config.load(root)
        _mutate(root, configuration, activate_codex, model="default")
    request = case["request"]
    if args.feedback:
        request += "\nIndependent check feedback (not a human mastery claim):\n" + args.feedback
    key = "live-trial-" + uuid.uuid4().hex
    started = time.monotonic()
    print("LIVE TRIAL / " + args.case + " / " + case["phase"], flush=True)
    result = _mutate(root, configuration, run_work, request=request, key=key,
                     continue_from=args.continue_from, assets=args.asset)
    state = result["state"]
    reflection = result["reflection"]
    items = cards(state)
    report = {
        "format": "cleanroom.core-trial-result.v1", "case": case["id"],
        "phase": case["phase"], "elapsed_seconds": round(time.monotonic() - started, 2),
        "run_id": result["run_id"], "work": result["work"], "reflection": reflection,
        "owner_cards": items, "model_turns": len(state["work_turns"]),
        "source_project_changed": result["source_project_changed"],
        "independent_artifact_validation": "NOT_RUN",
        "human_mastery": "NOT_ASSESSED",
    }
    directory = root / ".verantyx/trial-receipts"
    directory.mkdir(exist_ok=True)
    receipt = directory / (key + ".json")
    with receipt.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({
        "run_id": result["run_id"], "work": result["work"]["status"],
        "reason": result["work"]["reason"], "reflection": reflection["status"],
        "files": result["candidate_files"], "owner_kinds": [item["kind"] for item in items],
        "turns": len(state["work_turns"]), "seconds": report["elapsed_seconds"],
        "receipt": str(receipt),
    }, ensure_ascii=False), flush=True)
    return 0 if result["ok"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
