"""One human-readable ownership view over a recorded AI work item.

This module does not reinterpret AI prose as fact.  It joins existing,
source-linked work recaps with the project constitution and explicitly marks
anything an AI did not declare or the ledger did not verify as unresolved.
"""

from __future__ import annotations

import json
import re
import hashlib
from copy import deepcopy

from .constitution import gaps, snapshot
from .domain.codec import canonical
from .experience_report import report as historical_report
from .personal_skills import read_state


_ASSUMPTION = re.compile(r"^\s*(?:assumption|assumptions|仮定)\s*[:：-]\s*(.+?)\s*$", re.IGNORECASE)


def _work_gate(state):
    """Read only the preflight record captured by the connected work loop."""
    for capture in reversed(state.get("external_captures", [])):
        body = capture.get("body")
        if not isinstance(body, str):
            continue
        try:
            value = json.loads(body)
        except (TypeError, ValueError):
            continue
        if value.get("format") == "verantyx.work-recovery.v1" and isinstance(value.get("task_gate"), dict):
            return deepcopy(value["task_gate"])
    return None


def _declared_assumptions(notes):
    if not isinstance(notes, str):
        return []
    values = []
    for line in notes.splitlines():
        matched = _ASSUMPTION.match(line)
        if matched:
            values.append({"statement": matched.group(1)[:1000], "status": "AI_DECLARED_UNVERIFIED"})
    return values[:8]


def _candidate_changes(files, observations, source_ref=None):
    """Expose saved candidate content as a delta without treating it as applied.

    The experience recap only knows staged ``writer.apply`` actions.  Connected
    work deliberately stores an editor document before it is authorized, so the
    ownership screen must also show that earlier, safer candidate state.
    """
    observed = {row.get("path"): row for row in observations if isinstance(row, dict)}
    changes = []
    for path in sorted(files):
        body = files[path]
        if not isinstance(path, str) or not isinstance(body, str):
            continue
        baseline = observed.get(path) or {}
        changes.append({
            "path": path,
            "status": "CANDIDATE_NOT_APPLIED",
            "candidate_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "candidate_bytes": len(body.encode("utf-8")),
            "baseline_observation_ref": baseline.get("source_ref"),
            "baseline_sha256": baseline.get("sha256"),
            "source_ref": source_ref,
        })
    return changes


def report(root, configuration, run_id, locale="ja"):
    """Return a six-delta ownership report without a model call or mutation."""
    historical = historical_report(root, configuration, run_id, locale)
    state = read_state(root, configuration, run_id)
    gate = _work_gate(state)
    document = (state.get("editor_attempt") or {}).get("document") or {}
    files = document.get("files") or {}
    notes = document.get("notes")
    assumptions = _declared_assumptions(notes)
    attempt = state.get("editor_attempt") or {}
    project_delta = deepcopy(historical["project_delta"])
    recorded_candidates = _candidate_changes(files, project_delta.get("observations", []), attempt.get("source_ref"))
    existing_candidates = project_delta.get("candidate_changes", [])
    existing_paths = {row.get("path") for row in existing_candidates if isinstance(row, dict)}
    project_delta["candidate_changes"] = [*existing_candidates,
                                          *(row for row in recorded_candidates if row["path"] not in existing_paths)]
    model_provenance = deepcopy(attempt.get("provenance")) if isinstance(attempt.get("provenance"), dict) else None
    human_decisions = deepcopy(historical["human_delta"]["judgments"])
    if gate and gate.get("human_assumption"):
        human_decisions.append({
            "kind": "TASK_LOCAL_ASSUMPTION",
            "statement": gate["human_assumption"],
            "status": "RECORDED_NOT_GENERAL_RULE",
            "gap_id": gate.get("gap_id"),
        })
    unresolved = [row for row in gaps(root) if row["status"] == "OPEN" and row.get("request") == state.get("request")]
    ownership_debt = []
    if files and not human_decisions:
        ownership_debt.append({"code": "AI_CHANGE_WITHOUT_RECORDED_HUMAN_DECISION",
                               "meaning": "候補変更はあるが、この仕事に紐づく人間判断は記録されていません。"})
    if files and not assumptions:
        ownership_debt.append({"code": "AI_ASSUMPTIONS_NOT_EXPLICITLY_CAPTURED",
                               "meaning": "AI候補はありますが、AIが置いた前提は構造化して記録されていません。"})
    if historical["evidence"]["status"] in ("UNKNOWN", "CONTESTED"):
        ownership_debt.append({"code": "EVIDENCE_NOT_CLOSED",
                               "meaning": "候補の実装状態と、正しさの確認状態はまだ一致していません。"})
    return {
        "schema_version": 1,
        "ok": True,
        "command": "ownership",
        "run_id": run_id,
        "revision": historical["revision"],
        "project_constitution": snapshot(root, configuration),
        "project_delta": project_delta,
        "human_decisions": human_decisions,
        "ai_decisions_and_assumptions": {
            "candidate_files": sorted(files),
            "candidate_status": (state.get("editor_attempt") or {}).get("validation", {}).get("status", "NOT_RECORDED"),
            "recorded_model_provenance": model_provenance,
            "implementation_notes": notes[:4000] if isinstance(notes, str) else None,
            "declared_assumptions": assumptions,
            "assumption_capture": "DECLARED_UNVERIFIED" if assumptions else "NOT_EXPLICITLY_CAPTURED",
            "boundary": "Candidate files and model notes are proposals, not accepted decisions or verified evidence.",
        },
        "evidence_and_unknowns": {
            "build": deepcopy(historical["build"]),
            "evidence": deepcopy(historical["evidence"]),
            "ownership": deepcopy(historical["ownership"]),
            "recorded_unknowns": deepcopy(historical["evidence"].get("gaps", [])),
            "open_human_judgment_gaps": unresolved,
        },
        "human_learning_delta": deepcopy(historical["human_delta"]),
        "system_delta": deepcopy(historical["system_delta"]),
        "task_gate": gate or {"status": "NOT_CAPTURED", "boundary": "This run was not created through the connected develop flow."},
        "ownership_debt": ownership_debt,
        "model_calls": 0,
        "model_calls_during_report": 0,
        "writes": False,
        "authority": "REFERENCE_ONLY",
        "boundary": (
            "This is a historical, source-linked ownership view. It does not recheck current files, grant execution, "
            "prove human mastery, or convert undeclared AI reasoning into a human decision."
        ),
        "fingerprint": canonical({"run_id": run_id, "revision": historical["revision"],
                                    "constitution_revision": snapshot(root, configuration)["revision"]}),
    }


def display(result, locale="ja", command="ownership"):
    from .cli import visible
    print("\nVera / PROJECT OWNERSHIP")
    print("AIが作業しても、目的・判断・証拠・理解を人間側へ残す記録です。")
    constitution = result["project_constitution"]
    print("\nPROJECT CONSTITUTION")
    print("目的: " + visible(constitution.get("purpose") or "未記録"))
    print("版: " + str(constitution["revision"]) + " / " + constitution["source"])
    print("\n1. PROJECT DELTA")
    project = result["project_delta"]
    for key in ("candidate_changes", "canonical_changes", "execution_records", "workflows"):
        print("  " + key + ": " + str(len(project.get(key, []))))
    print("\n2. HUMAN DECISIONS")
    for row in result["human_decisions"][:8]:
        print("  " + visible(row.get("statement") or row.get("reason") or row.get("id") or "記録済み判断"))
    if not result["human_decisions"]:
        print("  未記録。AI候補を人間の決定として扱いません。")
    print("\n3. AI DECISIONS AND ASSUMPTIONS")
    ai = result["ai_decisions_and_assumptions"]
    print("  候補ファイル: " + ", ".join(ai["candidate_files"]) if ai["candidate_files"] else "  候補ファイル: 未記録")
    print("  前提の記録: " + ai["assumption_capture"])
    for row in ai["declared_assumptions"]:
        print("  仮定: " + visible(row["statement"]) + " / " + row["status"])
    print("\n4. EVIDENCE AND UNKNOWNS")
    evidence = result["evidence_and_unknowns"]
    print("  BUILD=" + str(evidence["build"]["status"]) + " / EVIDENCE=" + str(evidence["evidence"]["status"])
          + " / OWNERSHIP=" + str(evidence["ownership"]["status"]))
    print("  OPEN HUMAN GAPS: " + str(len(evidence["open_human_judgment_gaps"])))
    print("\n5. HUMAN LEARNING DELTA")
    learning = result["human_learning_delta"]
    print("  OWNERSHIP CHOICES: " + str(len(learning.get("ownership_choices", [])))
          + " / SUGGESTIONS: " + str(len(learning.get("suggestions", []))))
    print("\n6. SYSTEM DELTA")
    system = result["system_delta"]
    print("  検証資産: " + str(len(system.get("verification_assets", [])))
          + " / 失敗資産: " + str(len(system.get("failure_assets", [])))
          + " / 再利用候補: " + str(len(system.get("model_candidates", []))))
    print("\nOWNERSHIP DEBT: " + str(len(result["ownership_debt"])))
    for debt in result["ownership_debt"]:
        print("  " + debt["code"] + ": " + debt["meaning"])
    print("モデル呼出し: 0 / 現在のファイルは再検査していません。")
