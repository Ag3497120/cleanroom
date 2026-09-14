"""Owner and Agent are projections of one validated, read-only ledger snapshot.

The session cursor is only a view subscription, never an approval, an execution
receipt or a second task store. A watcher neither creates a DB nor invokes AI.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import uuid

from .domain.codec import digest
from .errors import LedgerError
from .presentation import safe_text
from .storage.sqlite import EventStore


CURSOR = "cleanroom-session.json"
EMPTY = {"project_revision": 0, "events": [], "states": [], "rules": {}, "as_of": None}


def layout_mode(columns, rows):
    if columns >= 140 and rows >= 24:
        return "side"
    if columns >= 90 and rows >= 36:
        return "stack"
    return "tabs"


def _directory(root):
    path = Path(root) / ".verantyx"
    if path.is_symlink() or not path.is_dir():
        raise LedgerError("STORE_PATH")
    return path


@contextmanager
def owner_lock(root):
    """One interactive writer, independently of the existing command locks."""
    path = _directory(root) / "cleanroom-owner.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise LedgerError("STORE_PATH")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LedgerError("STORE_BUSY", {"reason": "OWNER_ALREADY_OPEN", "next": "verantyx watch"}) from None
        yield
    finally:
        os.close(fd)


def publish_cursor(root, session_id, run_id, *, busy, waiting, phase, closed=False):
    directory = _directory(root)
    temporary = directory / (".cleanroom-" + uuid.uuid4().hex)
    value = {"format": "cleanroom.view-cursor.v1", "session_id": session_id,
             "pid": os.getpid(), "run_id": run_id, "updated_at": time.time(),
             "busy": busy, "waiting": waiting, "phase": phase, "closed": closed,
             "authority": "DISPLAY_ONLY_NOT_EVIDENCE"}
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=True)
        os.replace(temporary, directory / CURSOR)
    finally:
        temporary.unlink(missing_ok=True)


def read_cursor(root):
    path = _directory(root) / CURSOR
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 8192:
            raise LedgerError("STORE_PATH")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
            value = json.loads(stream.read(8193))
        if not isinstance(value, dict) or value.get("format") != "cleanroom.view-cursor.v1":
            return None
        updated = value.get("updated_at")
        age = time.time() - updated if type(updated) in (int, float) else float("inf")
        value["live"] = not value.get("closed") and 0 <= age <= 6
        return value
    except (ValueError, UnicodeError):
        return None
    finally:
        os.close(fd)


def _text(value, limit=1200):
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, default=str)
    return safe_text(value[:limit], multiline=True)


def _rows(title, rows, render, empty="まだ記録されていません。", limit=8):
    lines = [title]
    lines.extend("  " + _text(render(row)) for row in rows[:limit])
    if not rows:
        lines.append("  " + empty)
    if len(rows) > limit:
        lines.append(f"  + {len(rows) - limit} more recorded items")
    return lines + [""]


def project_view(snapshot, configuration, selected=None, owner_notes=()):
    """Pure display data. No prose is promoted into authorization or evidence."""
    from .development import work_summaries_from_snapshot
    from .experience_report import from_snapshot
    from .ownership_report import _work_gate, _declared_assumptions
    from .cleanroom_owner import catalogue, render_owner

    works = work_summaries_from_snapshot(snapshot)
    run_id = selected or (works[0]["run_id"] if works else None)
    state = next((row for row in snapshot["states"] if row["run_id"] == run_id), None)
    view = {"format": "cleanroom.split-view.v1", "run_id": run_id,
            "project_revision": snapshot["project_revision"], "revision": 0,
            "as_of": snapshot["as_of"], "writes": False, "model_calls": 0,
            "state": state, "works": works, "receipt": None, "related_receipts": [],
            "events": [], "assumptions": [], "candidates": [], "question": None,
            "recorded": state is not None, "panes": {}, "owner_note_revision": len(owner_notes)}
    if state is None:
        message = "この仕事の台帳イベントを待っています。" if run_id else "まだ仕事の記録はありません。"
        view["panes"] = {
            "owner": "YOUR PROJECT\n\n" + _text(configuration["project"].get("purpose") or "目的は未記録です。最初の依頼から始められます。")
                     + "\n\n" + message + "\n\n一文で仕事を依頼できます。送信前に範囲を確認します。\n判断・理解・採用は人間側に残します。",
            "agent": "AGENT WORKBENCH\n\n" + message + "\nこの画面の閲覧ではAIを呼び出しません。",
            "evidence": "EVIDENCE\n\n検査記録はまだありません。未検証を成功とは表示しません。",
            "notebook": "NOTEBOOK\n\n仕事から、判断・失敗・学びの記録が生まれます。",
            "review": "REVIEW\n\n" + message,
        }
        view["owner_items"] = catalogue(view, owner_notes)
        view["panes"]["owner"] = render_owner(view, view["owner_items"])
        return view
    receipt = from_snapshot(snapshot, configuration, run_id, "ja")
    events = [row for row in snapshot["events"] if row["stream_id"] == run_id]
    work = next((row for row in works if row["run_id"] == run_id), None)
    related = [from_snapshot(snapshot, configuration, identity, "ja")
               for identity in (work or {}).get("related_runs", []) if identity != run_id]
    assessment = state.get("assessment") or {}
    attempt = state.get("editor_attempt") or {}
    document = attempt.get("document") or {}
    files = document.get("files") or {}
    candidates = [{"path": path, "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                   "bytes": len(body.encode("utf-8")), "source_ref": attempt.get("source_ref")}
                  for path, body in sorted(files.items()) if isinstance(body, str)]
    gate = _work_gate(state) or {}
    assumptions = _declared_assumptions(document.get("notes"))
    human = list(receipt["human_delta"]["judgments"])
    if gate.get("human_assumption"):
        human.append({"reason": gate["human_assumption"], "kind": "TASK_LOCAL_ASSUMPTION"})
    # The live command owns transient progress. The ledger owns these statuses.
    view.update(revision=state["revision"], receipt=receipt, events=events,
                related_receipts=related, candidates=candidates, assumptions=assumptions,
                question=assessment.get("question"), human_decisions=human)
    from .cleanroom_growth import project as growth_project, summary as growth_summary
    view["growth"] = growth_project(snapshot, configuration, [run_id, *(row["run_id"] for row in related)])
    status_line = " | ".join(name.upper() + ": " + receipt[name]["status"]
                             for name in ("build", "evidence", "ownership"))
    canonical = receipt["project_delta"]["canonical_changes"]
    adoption_line = (f"採用・統合の記録: {len(canonical)}件。現在の作業木は再検査していません。"
                     if canonical else "この仕事に採用・統合の実行記録はありません。")
    owner = ["PURPOSE / YOUR CONTRIBUTION", _text(state.get("request") or run_id), "", status_line, adoption_line, ""]
    owner += _rows("HUMAN DECISIONS", human, lambda row: row.get("reason") or row.get("choice") or row,
                   "人間判断は未記録です。AIの候補とは区別します。")
    question = view["question"]
    if question:
        owner += ["ONE DECISION FOR YOU", _text(question.get("question") or question), "Menu > Review で回答できます。", ""]
    owner += _rows("AI ASSUMPTIONS / UNVERIFIED", assumptions, lambda row: row["statement"],
                   "AIの前提は明示的に記録されていません。前提がないという意味ではありません。")
    owner += _rows("CANDIDATE / NOT AUTOMATICALLY APPLIED", candidates,
                   lambda row: f"{row['path']}  {row['bytes']} B  sha256:{row['sha256'][:12]}")
    unknowns = receipt["project_delta"]["unresolved"]
    owner += _rows("STILL UNKNOWN", unknowns, lambda row: row.get("question") or row.get("code") or row,
                   "記録された未解決項目は0件です。一般的な正しさの保証ではありません。")
    learning = receipt["human_delta"]
    if view["growth"]["automatic_card"] and view["growth"]["focus"]:
        owner += ["UNDERSTANDING TO KEEP / OPTIONAL", view["growth"]["focus"]["concept"],
                  "F4またはMenu > Learn together。後回しや委譲も本人が選べます。", ""]
    evidence = ["EVIDENCE / RECORDED TARGETS ONLY", status_line,
                "記録時点の対象・有限条件に対する結果です。現在のファイルの再検査ではありません。",
                "別モデルの合意だけを独立した検証とは扱いません。", ""]
    for record in [receipt, *related]:
        evidence += ["Run " + record["run_id"] + " / revision " + str(record["revision"])]
        evidence += _rows("CLAIMS", record["evidence"]["claims"],
                          lambda row: _text({key: row[key] for key in ("id", "status", "closure", "evidence_scope", "recorded_evidence") if key in row}, 2200))
        evidence += _rows("CHECKS / CONTRACTS", record["system_delta"]["verification_assets"],
                          lambda row: {key: row[key] for key in ("id", "status", "target", "contract_summary", "source_refs", "latest_outcome") if key in row})
        evidence += _rows("FAILURES / NOT SUCCESS", record["system_delta"]["failure_assets"], lambda row: row)
    agent = ["AGENT WORKBENCH / READ ONLY", "以下は観測・実行・検査の記録です。内部の思考過程は表示しません。", ""]
    agent += _rows("OBSERVED FILES", receipt["project_delta"]["observations"],
                   lambda row: {key: row[key] for key in ("path", "status", "sha256", "source_ref") if key in row})
    agent += _rows("CANDIDATE FINGERPRINTS", candidates, lambda row: row, limit=16)
    agent += _rows("EXECUTION RECEIPTS", receipt["project_delta"]["execution_records"], lambda row: row,
                   "コマンド実行の記録はありません。候補の保存だけでは実行済みと扱いません。")
    agent += ["EVENT TRAIL / MOST RECENT 80"]
    allowed = ("path", "status", "outcome", "reason", "plan_id", "verification_id", "lease_id", "returncode", "exit_code", "stage", "action_id")
    for event in events[-80:]:
        details = {key: event["payload"][key] for key in allowed if key in event["payload"]}
        agent += [f"r{event['revision']}  {event['recorded_at']}  {event['type']}",
                  "  " + _text(details) if details else "  event:" + event["event_id"]]
    notebook = ["CLEANROOM RECEIPT", _text(state.get("request") or run_id), "", status_line, "", "PROJECT",
                f"候補ファイル {len(candidates)} / 採用・統合の記録 {len(canonical)}", adoption_line, ""]
    notebook += _rows("HUMAN / YOUR CONTRIBUTION", human, lambda row: row.get("reason") or row)
    notebook += _rows("UNDERSTANDING / YOUR CHOICES", learning["ownership_choices"],
                      lambda row: row["ownership_target"] + ": " + row["concept"])
    notebook += _rows("GROWTH / SUGGESTIONS, NOT MASTERY", learning["suggestions"],
                      lambda row: {key: row[key] for key in ("concept", "why_now", "minimum_model", "counterexample", "check") if key in row})
    system = receipt["system_delta"]
    notebook += ["SYSTEM / RETAINED EXPERIENCE",
                 f"検査資産 {len(system['verification_assets'])} / 失敗事例 {len(system['failure_assets'])}",
                 f"参照した規則 {len(system['reused_rules'])} / モデル由来の再利用候補 {len(system['model_candidates'])}",
                 "候補を自動で正式規則へ昇格させません。委譲と人間の理解は別の状態です。", ""]
    notebook += _rows("LINKED CHECK NOTES", related,
                      lambda row: row["run_id"] + " / EVIDENCE: " + row["evidence"]["status"])
    notebook += [growth_summary(view["growth"]), ""]
    review = ["REVIEW / ONLY HUMAN WORK", _text(question.get("question") if question else "台帳上の判断待ちはありません。"), ""]
    review += _rows("ASSUMPTIONS TO REVIEW", assumptions, lambda row: row["statement"])
    review += _rows("UNDERSTANDING TO RECOVER", learning["suggestions"], lambda row: row["concept"])
    review += ["Menu > Review で、判断・有限検査・学習方針・準備済み採用を選べます。",
               "作業の閲覧やノートを開くこと自体には、承認・実行の効力はありません。"]
    view["panes"] = dict(zip(("owner", "agent", "evidence", "notebook", "review"),
                             ("\n".join(lines) for lines in (owner, agent, evidence, notebook, review))))
    view["owner_items"] = catalogue(view, owner_notes)
    view["panes"]["owner"] = render_owner(view, view["owner_items"])
    return view


class Reader:
    """Use on one dedicated thread; all visible panes share its snapshot."""
    def __init__(self, root, configuration):
        self.root, self.configuration = Path(root), configuration
        self.store = None
        self.previous = None
        self.previous_key = None
        self.view = None

    def read(self, selected=None, follow=False):
        cursor = read_cursor(self.root) if follow else None
        if cursor and cursor.get("run_id") and selected is None:
            selected = cursor["run_id"]
        if self.store is None or self.store.connection is None:
            self.close()
            self.store = EventStore(self.root, self.configuration["project"]["id"])
        snapshot = self.store.project_snapshot()
        from .cleanroom_owner import read_notes
        owner_notes = read_notes(self.root)
        key = (selected, digest(self.configuration), digest(owner_notes))
        if snapshot != self.previous or key != self.previous_key:
            self.view = project_view(snapshot, self.configuration, selected, owner_notes)
            self.previous, self.previous_key = snapshot, key
        return {**self.view, "cursor": cursor,
                "read_at": datetime.now(timezone.utc).isoformat()}

    def close(self):
        if self.store is not None:
            self.store.close()
            self.store = None


def public_view(view):
    """Export the display, not raw prompts, response bodies or local inputs."""
    fields = ("format", "run_id", "project_revision", "revision", "as_of", "read_at",
              "writes", "model_calls", "recorded", "owner_note_revision", "panes")
    return {key: view[key] for key in fields if key in view}
