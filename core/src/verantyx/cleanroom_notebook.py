"""Human-facing research-notebook views for the Cleanroom CLI.

This module deliberately owns presentation only.  The project ledger, rules,
evidence, and model adapters remain in their existing modules so that the
notebook never becomes a second source of truth.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _model_label(configuration: Any) -> str:
    runtime = _field(configuration, "runtime", {})
    selection = _field(runtime, "model_selection", {})
    return str(_field(selection, "label", "Default project connection"))


def _result_label(result: Any) -> str:
    for key in ("label", "request", "title", "run_id", "id"):
        candidate = _field(result, key)
        if candidate:
            return str(candidate)
    return "This work note"


def _result_status(result: Any) -> str:
    status = _field(result, "status") or _field(result, "state")
    return str(status or "recorded")


def render_first_open(root: str) -> None:
    project = Path(root).name
    print("\n╭─ CLEANROOM ─────────────────────────────────────────────────")
    print("│ AI can prepare work. You keep the project.")
    print("│")
    print("│ " + project + " is ready as a shared research notebook.")
    print("│")
    print("│  Read       Vera studies only this project by default")
    print("│  Propose    AI work stays in an isolated candidate notebook")
    print("│  Adopt      You decide what enters the project")
    print("│  Remember   Decisions, evidence, failures, and learning stay local")
    print("╰─────────────────────────────────────────────────────────────")


def render_workspace_header(root: str, configuration: Any) -> None:
    project = Path(root).name
    print("\n╭─ CLEANROOM NOTEBOOK ────────────────────────────────────────")
    print("│ " + project)
    print("│ " + _model_label(configuration))
    print("│")
    print("│ Write the work in your own words. Vera investigates first;")
    print("│ it returns only the remaining human decision when one matters.")
    print("│")
    print("│ Work is a page. Project is its shared context. Notebook keeps")
    print("│ the history. Review collects only the work that needs you.")
    print("╰─────────────────────────────────────────────────────────────")
    print("例えば: サイトをリニューアルして / 今のプロジェクトを見せて / 確認が必要なことを見る")


def render_task_workspace(
    context_files: Sequence[str],
    preflight: Mapping[str, Any] | None,
    previous: Mapping[str, Any] | None = None,
) -> None:
    question = _field(preflight or {}, "question")
    previous_label = _field(previous or {}, "label")
    print("\n╭─ WORK NOTE ─────────────────────────────────────────────────")
    print("│ Candidate workspace: ready   Project files: sealed")
    print("│")
    print("│ OWNERSHIP RAIL")
    print("│ Human   Purpose, trade-offs, irreversible choices, adoption")
    print("│ AI      Research, alternatives, implementation, routine repair")
    print("│ Vera    Evidence, failure history, retained rules, learning notes")
    print("│")
    print("│ Context selected automatically: " + str(len(context_files)) + " project files")
    print("│ Outside the project, secrets, and old notebooks stay outside.")
    if previous_label:
        print("│ Continuing note: " + str(previous_label))
    if question:
        print("│ HUMAN REVIEW: " + str(question))
    else:
        print("│ HUMAN REVIEW: only if a non-delegated decision remains.")
    print("╰─────────────────────────────────────────────────────────────")


def render_notebook_index() -> None:
    print("\n╭─ NOTEBOOK INDEX ────────────────────────────────────────────")
    print("│ You do not need to memorize commands. Write a sentence.")
    print("│")
    print("│ Work       仕事の続きが見たい / 今の仕事を見せて")
    print("│ Project    今のプロジェクトを見せて / プロジェクトを理解したい")
    print("│ Notebook   ノートを見る / 記録を見せて")
    print("│ Review     確認が必要なことを見る / レビューを開く")
    print("│ Settings   設定を開く / モデル接続を変える")
    print("│")
    print("│ A work page preserves five things: Project, Human, Evidence,")
    print("│ System, and Growth. The full conversation remains secondary.")
    print("╰─────────────────────────────────────────────────────────────")


def render_project_map(root: str, configuration: Any, context_files: Sequence[str]) -> None:
    print("\n╭─ PROJECT MAP ───────────────────────────────────────────────")
    print("│ Project: " + Path(root).name)
    print("│ Current connection: " + _model_label(configuration))
    print("│ Visible local context: " + str(len(context_files)) + " selected project files")
    print("│")
    print("│ What remains with the project")
    print("│  Purpose          Why the project exists")
    print("│  Decisions        What a person chose and why")
    print("│  Evidence         What was checked and within which boundary")
    print("│  Unknowns         What neither a model nor a rule can settle")
    print("│  Experience       Failures, reusable checks, and working rules")
    print("│")
    print("│ The map grows from work notes. It does not pretend a chat log")
    print("│ is understanding, and it does not score your understanding.")
    print("╰─────────────────────────────────────────────────────────────")


def render_review_queue(root: str, configuration: Any) -> None:
    print("\n╭─ REVIEW QUEUE ──────────────────────────────────────────────")
    print("│ " + Path(root).name)
    print("│")
    print("│ This page is for work only a project owner should do.")
    print("│")
    print("│ HUMAN DECISIONS")
    print("│  Purpose, values, public scope, irreversible trade-offs")
    print("│")
    print("│ CANDIDATE ADOPTION")
    print("│  Candidate work can be inspected before it enters the project")
    print("│")
    print("│ UNDERSTANDING RECOVERY")
    print("│  OWN      Principles you need to design or change")
    print("│  REVIEW   Risks you need to recognize")
    print("│  REFERENCE Details you can look up when needed")
    print("│  DELEGATE  Stable routine work that the system can retain")
    print("│")
    print("│ Vera does not stop routine work for missing knowledge. It keeps")
    print("│ ownership debt visible until you choose to learn, reference, or delegate.")
    print("╰─────────────────────────────────────────────────────────────")


def render_work_receipt(root: str, result: Any) -> None:
    print("\n╭─ CLEANROOM RECEIPT ─────────────────────────────────────────")
    print("│ Work: " + _result_label(result))
    print("│ State: " + _result_status(result))
    print("│")
    print("│ PROJECT DELTA  Candidate work and unresolved change are recorded")
    print("│ HUMAN DELTA    Human decisions remain separate from AI assumptions")
    print("│ EVIDENCE       Checks are retained with their boundary, not as a claim of certainty")
    print("│ SYSTEM DELTA   Reusable rules, checks, and failures can be promoted")
    print("│ GROWTH         Learn, review, reference, or delegate without turning work into homework")
    print("│")
    print("│ Open the work note to inspect details before adopting a candidate.")
    print("╰─────────────────────────────────────────────────────────────")
