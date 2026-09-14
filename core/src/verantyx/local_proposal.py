"""Deterministic observation proposal for the two-role economy workflow.

This script is a trusted local adapter, not a language model. Interpretation
belongs to the subsequent handoff planner; no permission is synthesized here.
"""
import json
import sys


def main():
    raw = sys.stdin.buffer.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        return 2
    request = json.loads(raw)
    if request.get("format") != "verantyx.proposal-request.v1":
        return 2
    source = request["proposal_template"]
    document = {key: source[key] for key in (
        "schema_version", "task_id", "context_revision", "response_locale",
    )}
    document.update(
        summary="Local observation proposal only; request interpretation and code changes are not yet verified.",
        claims=[], unknowns=[],
        actions=[row for row in source["actions"] if row["tool_id"] == "file.observe"],
    )
    print(json.dumps(document, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
