"""Structured terminal presentation; never infer meaning from message keywords."""
from copy import deepcopy

from prompt_toolkit.lexers import Lexer
from prompt_toolkit.utils import get_cwidth

from .interaction_text import tr
from .presentation import safe_text


class LineStyles(Lexer):
    def __init__(self):
        self.rows = []

    def lex_document(self, document):
        styles = tuple(self.rows)
        def line(number):
            return [(styles[number] if number < len(styles) else "", document.lines[number])]
        return line


def _wrapped(text, width):
    for line in text.split("\n"):
        current, used = "", 0
        for character in line:
            size = max(0, get_cwidth(character))
            if used + size > width and current:
                yield current
                current, used = "", 0
            current += character
            used += size
        yield current


class Page:
    def __init__(self, width):
        self.width = max(12, width)
        self.lines, self.styles = [], []

    def add(self, text="", style="", *, fill=False):
        text = safe_text(str(text), multiline=True).replace("\t", "    ")
        for line in _wrapped(text, self.width) if fill else text.split("\n"):
            self.lines.append(line + " " * max(0, self.width - get_cwidth(line)) if fill else line)
            self.styles.append(style)

    def section(self, title):
        self.add()
        self.add(title, "class:owner.heading")
        self.add()

    def finish(self, lexer):
        lexer.rows = self.styles
        return "\n".join(self.lines)


class Conversation:
    def __init__(self):
        self.groups = []
        self.omitted = False

    def start(self, identity, request, status=""):
        group = next((row for row in self.groups if row["id"] == identity), None)
        if group is None:
            group = {"id": identity, "request": request, "run_id": None,
                     "status": status, "state": {}, "changes": {}, "pending": {}, "revision": -1}
            self.groups.append(group)
        else:
            group["status"] = status
        while len(self.groups) > 80:
            self.groups.pop(0)
            self.omitted = True
        return group

    def get(self, identity):
        return next((row for row in self.groups if row["id"] == identity), None)

    def bind(self, identity, run_id):
        group = self.get(identity)
        if group is None:
            return
        prior = next((row for row in self.groups if row["run_id"] == run_id and row is not group), None)
        if prior:
            group["state"] = prior["state"]
            group["revision"] = prior["revision"]
            group["changes"].update(prior["changes"])
            self.groups.remove(prior)
        group["run_id"], group["status"] = run_id, ""

    def observe(self, state):
        if not state or not state.get("work_session"):
            return
        run_id = state["run_id"]
        group = next((row for row in self.groups if row["run_id"] == run_id), None)
        if group is None:
            group = self.start("run:" + run_id, state.get("request", "").split("\n\n[Owner-selected references:", 1)[0])
            group["run_id"] = run_id
        if state.get("revision", 0) < group["revision"]:
            return
        group["revision"] = state.get("revision", 0)
        if not group["request"]:
            group["request"] = state.get("request", "").split("\n\n[Owner-selected references:", 1)[0]
        group["state"] = deepcopy({key: state.get(key) for key in (
            "work_turns", "work_tools", "work_instructions", "work_result")})
        for row in state.get("work_instructions", []):
            group["pending"].pop(row["id"], None)

    def instruction(self, identity, row):
        group = self.get(identity)
        if group is not None:
            group["pending"][row["id"]] = deepcopy(row)

    def remove_pending(self, identity, instruction_id):
        group = self.get(identity)
        if group is not None:
            group["pending"].pop(instruction_id, None)

    def change(self, preview, mode):
        group = next((row for row in self.groups if row["run_id"] == preview["run_id"]), None)
        if group is None:
            group = self.start("run:" + preview["run_id"], "")
            group["run_id"] = preview["run_id"]
        group["changes"][preview["review_id"]] = (deepcopy(preview), mode)

    def remove(self, identity):
        self.groups = [row for row in self.groups if row["id"] != identity]

    def render(self, width, lang, lexer):
        from .change_review import describe
        page = Page(width)
        if self.omitted:
            page.add(tr("chat_limit", lang), "class:chat.meta")
        if not self.groups:
            page.add(tr("empty", lang), "class:chat.meta")
        for group in self.groups:
            page.add()
            page.add("  " + tr("you", lang), "class:chat.user", fill=True)
            page.add("  " + group["request"], "class:chat.user", fill=True)
            if group["status"]:
                page.add("  " + tr(group["status"], lang), "class:chat.user", fill=True)
            page.add()
            state = group["state"]
            turns = state.get("work_turns") or []
            receipts = {row.get("change_review", {}).get("review_id"): row
                        for row in state.get("work_tools") or [] if row.get("change_review")}
            events = []
            for row in state.get("work_instructions") or []:
                events.append((row["revision"], "user", row["user_text"]))
            for row in turns:
                proposal = row["proposal"]
                if proposal.get("answer"):
                    events.append((row["revision"], "assistant", proposal["answer"]))
            for preview, mode in group["changes"].values():
                receipt = receipts.get(preview["review_id"])
                if receipt is not None:
                    mode = receipt["change_review"]["mode"] + " / " + receipt["status"]
                    rank = receipt["revision"]
                else:
                    turn = next((row for row in turns if row["index"] == preview["turn"]), None)
                    rank = turn["revision"] + .5 if turn else 10**9 - 1
                events.append((rank, "change", (preview, mode)))
            for review_id, receipt in receipts.items():
                if review_id not in group["changes"]:
                    events.append((receipt["revision"], "receipt", receipt))
            for _, role, body in sorted(events, key=lambda row: row[0]):
                if role == "user":
                    page.add("  " + tr("you", lang) + " / " + tr("recorded_instruction", lang),
                             "class:chat.user", fill=True)
                    page.add("  " + body, "class:chat.user", fill=True)
                elif role == "assistant":
                    page.add(tr("assistant", lang), "class:chat.speaker")
                    page.add(body, "class:chat.answer")
                elif role == "receipt":
                    review = body["change_review"]
                    page.add(tr("saved_review", lang), "class:chat.review")
                    page.add(review["path"] + " / " + review["mode"] + " / " + body["status"], "class:chat.meta")
                    page.add("SHA-256: " + review["after_sha256"], "class:chat.meta")
                else:
                    preview, mode = body
                    page.add(tr("change_title", lang) + " / " + mode, "class:chat.review")
                    for line in describe(preview, lang).splitlines():
                        style = ("class:diff.add" if line.startswith("+") and not line.startswith("+++") else
                                 "class:diff.remove" if line.startswith("-") and not line.startswith("---") else
                                 "class:diff.hunk" if line.startswith(("@@", "---", "+++")) else "class:chat.meta")
                        page.add(line, style)
                page.add()
            if group.get("side_answer"):
                page.add(group.get("side_label", tr("assistant", lang)), "class:chat.speaker")
                page.add(group["side_answer"], "class:chat.answer")
                page.add()
            work = state.get("work_result") or {}
            answer = work.get("answer", "")
            last_answer = next((row["proposal"]["answer"] for row in reversed(turns) if row["proposal"].get("answer")), "")
            if answer and answer != last_answer:
                page.add(tr("assistant", lang), "class:chat.speaker")
                page.add(answer, "class:chat.answer")
                page.add()
            question = work.get("question") or (turns[-1]["proposal"].get("owner_question") if turns else "")
            if question:
                page.add(tr("owner_question", lang), "class:chat.review")
                page.add(question)
                page.add()
            for row in group["pending"].values():
                page.add("  " + tr("you", lang) + " / " + tr("pending_instruction", lang),
                         "class:chat.user", fill=True)
                page.add("  " + row["user_text"], "class:chat.user", fill=True)
                page.add()
        return page.finish(lexer)


def owner_page(view, items, query, personal, visible_lessons, width, lang, lexer):
    """Facts and proposals use separate, labelled sections, not a success score."""
    from .cleanroom_owner import search
    page = Page(width)
    projection = view.get("ownership_projection") or {}
    matched = search(items, query)
    page.add(tr("owner_title", lang), "class:owner.heading")
    from .session_text import t as session_text
    memo_page = view.get("memo_page", {})
    if memo_page.get("total", 0) > memo_page.get("limit", 200):
        page.add(session_text("memo_paging", lang, first=memo_page["offset"] + 1,
                              last=min(memo_page["offset"] + memo_page["limit"], memo_page["total"]),
                              total=memo_page["total"]), "class:chat.meta")
    if query:
        page.section(tr("owner_index", lang))
        page.add(query, "class:owner.query")
        for item in matched:
            page.add(item["label"], "class:owner.label")
            if item.get("text", "").strip() != item["label"]:
                page.add(item.get("text", ""))
            page.add()
        return page.finish(lexer)
    from .session_text import t as session_text
    live = view.get("live_insights", [])
    if live:
        page.section(session_text("insight_heading", lang))
        for item in live:
            page.add(item["id"] + "  " + item["note"]["title"], "class:owner.label")
            page.add(item["note"].get("next_small_step") or item["note"]["explanation"].split("\n", 1)[0], "class:chat.meta")
        page.add(session_text("insight_hint", lang), "class:chat.meta")
    elif view.get("insights_available"):
        page.add(session_text("insight_available", lang), "class:chat.meta")
    estimate = view.get("work_pulse", {})
    if estimate.get("available"):
        proposal = estimate["proposal"]
        impl, checks = proposal["implementation_minutes"], proposal["testing_minutes"]
        page.add(session_text("eta_parts", lang, il=impl["minimum"], ih=impl["maximum"], tl=checks["minimum"], th=checks["maximum"]), "class:chat.meta")
        page.add(proposal["basis"], "class:chat.meta")
    if projection:
        if projection.get("owner_question"):
            page.section(tr("owner_question", lang))
            page.add(projection["owner_question"], "class:owner.attention")
        page.section(tr("owner_purpose", lang))
        page.add(projection.get("human_request", {}).get("text", "").split("\n\n[Owner-selected references:", 1)[0])
        if projection.get("purpose"):
            page.add(projection["purpose"], "class:owner.label")
        instructions = projection.get("human_instructions", [])
        for row in instructions[-3:]:
            page.add("+ " + row["user_text"], "class:owner.label")
        decisions = projection.get("human_decisions", [])
        if decisions:
            page.section(tr("owner_decisions", lang))
            for row in decisions[-4:]:
                page.add(row.get("statement") or row.get("reason") or "")
                if row.get("source_ref"):
                    page.add(row["source_ref"], "class:chat.meta")
        facts = projection.get("recorded_facts", {})
        page.section(tr("owner_facts", lang))
        page.add(tr("owner_counts", lang, reads=facts.get("file_reads", 0),
                    writes=facts.get("candidate_writes", 0), checks=facts.get("tests_run", 0),
                    refused=facts.get("refused_tools", 0)), "class:owner.fact")
        evidence = projection.get("evidence_and_unknowns", {})
        page.add("Evidence: " + evidence.get("evidence", "NOT_VERIFIED"), "class:owner.fact")
        page.add(tr("owner_no_audit", lang), "class:chat.meta")
        proposals = [row for row in projection.get("owner_items", [])
                     if row.get("status") not in ("DEFERRED", "DISMISSED")
                     and row.get("target") in ("OWN", "REVIEW")
                     and row.get("human_understanding") == "NOT_ASSESSED"]
        # Respect the person's suggestion pace, rather than inventing a new feed.
        from .personal_growth import uses_personal_pace
        if uses_personal_pace():
            proposals = []
        if proposals:
            page.section(tr("owner_proposals", lang))
            for row in proposals[:2]:
                page.add(row["text"], "class:owner.label")
                page.add(row.get("reason", ""))
                page.add(row.get("target", "") + " / " + ("AI" if row.get("target_is_suggestion") else tr("you", lang)), "class:chat.meta")
        chosen = [row for row in projection.get("owner_items", []) if not row.get("target_is_suggestion", True)]
        if chosen:
            page.section(tr("chosen_role", lang))
            for row in chosen[-3:]:
                page.add(row["text"], "class:owner.label")
                page.add(str(row.get("target") or ""), "class:chat.meta")
        reusable = projection.get("system_delta", {}).get("candidates", [])
        if reusable:
            page.section(tr("system_candidates", lang))
            for row in reusable[:3]:
                page.add(row.get("kind", "") + " / " + row.get("text", ""))
        words = projection.get("human_notes", [])
        if words:
            page.section(tr("human_words", lang))
            for row in words[-2:]:
                page.add(row["text"], "class:owner.label")
        unknown = [*projection.get("declared_ai_assumptions", [])[-2:],
                   *evidence.get("unknown_proposals", [])[:2]]
        if unknown:
            page.section(tr("owner_unknown", lang))
            for row in unknown:
                page.add(row.get("text", ""), "class:owner.attention")
    else:
        page.section(tr("owner_purpose", lang))
        requests = [row for row in matched if row["kind"] in ("request", "question")]
        for item in requests[:5]:
            page.add(item.get("text") or item["label"])
        if not requests:
            page.add(tr("owner_empty", lang), "class:chat.meta")
    notes = [row for row in matched if row["kind"] == "note"]
    if notes:
        page.section(tr("owner_notes", lang))
        for item in notes:
            page.add(item.get("created_at", ""), "class:chat.meta")
            page.add(item["label"], "class:owner.label")
            if item.get("text") != item["label"]:
                page.add(item.get("text", ""))
    links = [row for row in matched if row["kind"] in ("candidate", "request", "learning")]
    if links:
        page.section(tr("owner_index", lang))
        for item in links[:8]:
            page.add(item["label"], "class:owner.label")
    if personal:
        records = personal.get("records", {})
        page.section(tr("owner_personal", lang))
        page.add(tr("personal_counts", lang, journal=personal.get("counts", {}).get("journal", len(records.get("journal", []))),
                    later=len([row for row in records.get("lesson", []) if row.get("choice") == "NEXT_TIME"]),
                    skills=personal.get("counts", {}).get("skill_asset", 0)), "class:chat.meta")
        from .skill_assets import ON_BOARD, MARKS
        for skill in [row for row in records.get("skill_progress", []) if row["plan"] in ON_BOARD][:3]:
            page.add(MARKS[skill["human"]] + " " + skill["title"], "class:owner.label")
            page.add(skill["plan"], "class:chat.meta")
        lessons = {row["id"]: row for row in records.get("lesson", [])}
        for identity in visible_lessons:
            row = lessons.get(identity)
            if row and row.get("choice") == "OPEN":
                page.add(row["title"], "class:owner.label")
                page.add(row["minimum_step"])
    page.add()
    page.add(tr("owner_guard", lang), "class:chat.meta")
    return page.finish(lexer)
