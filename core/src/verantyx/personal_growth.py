"""AI-proposed personal growth, independent of WorkResult and execution rights."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import time
import uuid

from . import personal_profile as profile
from .domain.codec import canonical, digest
from .errors import LedgerError

REQUEST = "verantyx.personal-growth-request.v1"
OWNER_INPUT = ContextVar("personal_owner_input", default=None)
CONTRACT = """You help a person remain the author of an AI-assisted project.
Use the actual recorded work, explicit self-reports and this person's chosen pace.
Never infer inability, low confidence or lack of understanding from delegation,
repeated requests, asking AI to push to GitHub, skipped suggestions or silence.
No profile entry means EXPERIENCE NOT RECORDED, not beginner.
Experience, understanding, confidence, desired support and delegation are independent.
The person may know a topic and still prefer that AI does it.
A concern is not a diagnosis. Do not solicit trauma or create a permanent sensitive
memory without an explicit owner choice. Offer practical support without a compulsory lesson.
All output is revisable AI interpretation. No scores, mastery certification, rights,
rule activation, employment claims or forced tests. Do not convert assisted work into
independent human achievement. Different models may propose different useful interpretations.

For reflect mode: suggest at most the requested per-work number of OWN/REVIEW
items, often zero or one. Ground them in actual changes, choices, errors or limits.
Use the chosen weight: brief = one small principle, snippet = one short situated
example, practice = an OPTIONAL small exercise. The lesson must not gate work.
REFERENCE and DELEGATE are valid outcomes, not deficient learning.
Assume there will be another related project. NEXT_TIME means a contextual bookmark,
not overdue homework. Relate a returning topic to the exact previous_id and explain
what is new, rather than repeating the same lesson. Honor REFERENCE, DELEGATE and
DISMISS. Do not reopen them without an explicit owner request.
Cross-language concepts may connect; knowing Python never proves Swift competence.
Do not invent human contributions: distinguish an instruction, a value choice,
a self-report, AI implementation, and a receipt.

For conversation mode: answer the person's question supportively and concretely,
without diagnosing or grading them. They may update preferences in ordinary language.
Return optional profile_updates only for something the person actually said, with an
exact human_quote and source_event_ids. Saving these always needs a later owner action.
For temporary preferences suggest SESSION or TODAY, not GLOBAL by default.
Every work claim and learning item cites provided source_event_ids. profile_refs and
previous_id must come from the provided personal context. Empty arrays are valid.
The actual checks, artifacts and work status are supplied by the host, not your wording.
Return only the personal-growth proposal schema, in response_locale."""


def output_schema():
    from .agent_schema import TEXT, SOURCE, obj, array
    refs = {"type": "array", "items": SOURCE, "minItems": 1, "maxItems": 12, "uniqueItems": True}
    optional_refs = {"type": "array", "items": SOURCE, "maxItems": 16, "uniqueItems": True}
    name = {"type": "string", "minLength": 1, "maxLength": 160}
    return obj({
        "format": {"type": "string", "const": "verantyx.personal-growth-proposal.v1"},
        "reply": TEXT,
        "technologies": array(obj({
            "name": name, "role": {"type": "string", "enum": ["PRIMARY", "SUPPORTING"]},
            "reason": TEXT, "source_event_ids": refs,
        }), 12),
        "interpretations": array(obj({
            "kind": {"type": "string", "enum": ["HUMAN_CONTRIBUTION", "AI_CONTRIBUTION",
                "ASSUMPTION", "FAILURE", "UNKNOWN", "PROJECT_MEANING", "REUSABLE_CANDIDATE"]},
            "text": TEXT, "source_event_ids": refs,
        }), 18),
        "lessons": array(obj({
            "title": TEXT, "technology": name, "topic": TEXT,
            "goal": {"type": "string", "enum": ["OWN", "REVIEW", "REFERENCE", "DELEGATE"]},
            "why_now": TEXT, "minimum_step": TEXT, "optional_practice": TEXT,
            "return_context": TEXT, "connection_to_prior": TEXT, "previous_id": TEXT,
            "source_event_ids": refs, "profile_refs": optional_refs,
        }), 3),
        "profile_updates": array(obj({
            "category": {"type": "string", "enum": [*profile.KINDS, "pace"]},
            "technology": TEXT, "text": TEXT, "human_quote": TEXT, "target_id": TEXT,
            "scope": {"type": "string", "enum": ["GLOBAL", "SESSION", "TODAY"]},
            "source_event_ids": refs,
            "preference_changes": array(obj({
                "name": {"type": "string", "enum": ["mode", "weight", "timing", "daily_limit", "per_work"]},
                "value": TEXT,
            }), 5),
        }), 3),
    })


def _human_text(event):
    if event.get("actor_kind") not in ("HUMAN", "human", "owner") and event.get("type") not in (
            "WorkOwnerReplyRecorded", "OwnerDesignDecisionRecorded", "PersonalOwnerMessage"):
        return ""
    payload = event.get("payload", {})
    return "\n".join(value for key, value in payload.items()
                     if key in ("text", "request", "reason", "choice") and isinstance(value, str))


def validate(request, document):
    sources = {row["source_ref"]: row for row in request.get("trace", {}).get("events", [])}
    context = request.get("personal_context", {})
    statements = {row["id"]: row for row in context.get("records", [])}
    lessons = {row["id"]: row for row in context.get("learning", [])}
    notes = {row["id"]: row for row in context.get("notes", [])}
    for item in [*document["technologies"], *document["interpretations"],
                 *document["lessons"], *document["profile_updates"]]:
        if any(ref not in sources for ref in item["source_event_ids"]):
            raise LedgerError("REFLECTION_SOURCE_UNKNOWN")
    for item in document["lessons"]:
        if any(ref not in statements and ref not in lessons and ref not in notes for ref in item["profile_refs"]):
            raise LedgerError("REFLECTION_SOURCE_UNKNOWN")
        previous = item["previous_id"]
        if previous and previous not in lessons:
            raise LedgerError("REFLECTION_SOURCE_UNKNOWN")
        if previous and lessons[previous].get("choice") in ("DELEGATE", "REFERENCE", "DISMISS"):
            raise LedgerError("BRIDGE_PROTOCOL", {"reason": "OWNER_LEARNING_CHOICE"})
    for item in document["profile_updates"]:
        quote = item["human_quote"].strip()
        if not quote or not any(quote in _human_text(sources[ref]) for ref in item["source_event_ids"]):
            raise LedgerError("REFLECTION_HUMAN_SOURCE_REQUIRED")
        if item["target_id"] and item["target_id"] not in statements:
            raise LedgerError("REFLECTION_SOURCE_UNKNOWN")
        if item["category"] == "pace":
            changes = _pace_changes(item["preference_changes"])
            if not changes:
                raise LedgerError("BRIDGE_PROTOCOL", {"reason": "EMPTY_PREFERENCE_UPDATE"})
        elif item["preference_changes"] or not item["text"].strip() or len(item["technology"]) > 160:
            raise LedgerError("BRIDGE_PROTOCOL", {"reason": "PERSONAL_UPDATE_SCHEMA"})
    return deepcopy(document)


def _pace_changes(rows):
    changes = {}
    for row in rows:
        key, value = row["name"], row["value"]
        profile.require(key not in changes, "DUPLICATE_PERSONAL_PREFERENCE")
        if key in ("daily_limit", "per_work"):
            try:
                value = int(value)
            except (ValueError, TypeError):
                raise LedgerError("ARGUMENTS", {"reason": "PERSONAL_SETTINGS_LIMIT"}) from None
        changes[key] = value
    return profile.settings_valid(changes)


def context():
    """Only explicit excerpts; a broken personal store never blocks a work call."""
    try:
        return profile.shared_context()
    except Exception:
        return {"sharing": "UNAVAILABLE", "records": [], "learning": [],
                "authority": "NO_ABILITY_INFERENCE"}


@contextmanager
def owner_input(callback):
    token = OWNER_INPUT.set(callback)
    try:
        yield
    finally:
        OWNER_INPUT.reset(token)


def work_key(configuration, run_id):
    return configuration["project"]["id"] + "/" + run_id


def owner_tool(name, text, *, human_request, work_identity):
    """Optional UI capability. Never grants project access or changes skill silently."""
    try:
        if not profile.preferences()["enabled"]:
            return {"status": "OFF", "continue_work": True}
        value = json.loads(text)
        profile.require(type(value) is dict, "PERSONAL_TOOL_OBJECT")
        if name == "ask_stack_experience":
            profile.require(set(value) == {"technology", "reason", "primary_chosen"}
                            and value["primary_chosen"] is True
                            and type(value["technology"]) is str and 0 < len(value["technology"]) <= 160
                            and type(value["reason"]) is str and len(value["reason"]) <= 2000,
                            "PERSONAL_STACK_INVITATION")
            callback = OWNER_INPUT.get()
            invited = profile.claim_prompt(value["technology"], work_identity, can_ask=callback is not None)
            if invited and callback:
                callback(value["technology"], value["reason"])
                return {"status": "OWNER_INVITED", "continue_work": True,
                        "note": "The response is private unless explicitly shared. No ability score."}
            return {"status": "OPTIONAL_PROFILE_LATER", "continue_work": True}
        if name == "suggest_owner_update":
            from jsonschema import Draft202012Validator
            schema = output_schema()["properties"]["profile_updates"]["items"]
            profile.require(Draft202012Validator(schema).is_valid(value), "PERSONAL_UPDATE_SCHEMA")
            quote = value["human_quote"].strip()
            profile.require(quote and quote in human_request, "PERSONAL_HUMAN_QUOTE_REQUIRED")
            profile.require(not value["target_id"], "USE_PERSONAL_CONVERSATION_TO_EDIT")
            if value["category"] == "pace":
                _pace_changes(value["preference_changes"])
            else:
                profile.require(not value["preference_changes"] and value["text"].strip()
                                and len(value["technology"]) <= 160, "PERSONAL_UPDATE_SCHEMA")
            identity = "proposal-" + digest({"work": work_identity, "proposal": value})[:32]
            if not profile.get_record(identity):
                profile.put_record({"id": identity, "kind": "proposal", "work_key": work_identity,
                                    "proposal": value, "status": "PENDING_OWNER",
                                    "source": {"kind": "WORK_AI_PROPOSAL", "human_quote": quote,
                                               "work_key": work_identity},
                                    "authority": "AI_PROPOSAL_NOT_OWNER_PROFILE", "created_at": profile.now()})
            return {"status": "PROPOSED_NOT_SAVED_AS_PROFILE", "id": identity, "continue_work": True}
        return {"status": "UNSUPPORTED_PERSONAL_TOOL", "continue_work": True}
    except Exception as error:
        return {"status": "PERSONAL_UNAVAILABLE", "reason": getattr(error, "code", type(error).__name__),
                "continue_work": True, "ability_inference": False}


def private_call(adapter, request, *, key, timeout=None):
    from .agent_models import invoke, identity
    from .agent_schema import schema, validate_output
    request = deepcopy(request)
    request["output_schema"] = schema(request)
    profile.require(len(canonical(request).encode()) <= 450000, "PERSONAL_CONTEXT_LIMIT")
    intent = digest({"request": request, "model": identity(adapter)})
    prior = profile.begin_call(key, intent)
    if prior is not None:
        validate_output(request, prior["document"])
        return prior
    # Keep private interpretation requests out of the project's invocation journal.
    # The outcome tombstone survives a crash; a new explicit generation is needed.
    try:
        with tempfile.TemporaryDirectory(prefix="model-", dir=profile.home()) as directory:
            Path(directory, ".verantyx").mkdir(mode=0o700)
            result = invoke(directory, adapter, request, key=key, timeout=timeout)
    except Exception as error:
        profile.fail_call(key, getattr(error, "code", type(error).__name__))
        raise
    profile.complete_call(key, result)
    return result


def _journal(root, configuration, state, trace):
    key = work_key(configuration, state["run_id"])
    identity = "journal-" + digest(key)[:32]
    old = profile.get_record(identity)
    work = state["work_result"]
    facts = {
        "work_status": work["status"], "result_source_ref": work.get("source_ref"),
        "result_sha256": digest(work), "artifacts": deepcopy(work.get("artifacts", [])),
        "tool_counts": deepcopy(work.get("tool_counts", {})),
        "checks": [{"source_ref": row["source_ref"], "type": row["type"],
                    "event_hash": row["event_hash"], "payload": deepcopy(row["payload"])}
                   for row in trace["events"] if row["type"] in ("WorkCheckStarted", "WorkCheckRecorded")],
        "human_events": [{"source_ref": row["source_ref"], "type": row["type"],
                          "event_hash": row["event_hash"], "payload": deepcopy(row["payload"])}
                         for row in trace["events"] if row["type"] in (
                             "WorkOwnerReplyRecorded", "OwnerDesignDecisionRecorded")],
        "evidence_status": work.get("evidence_status", "NOT_VERIFIED"),
    }
    record = {**(old or {}), "id": identity, "kind": "journal", "work_key": key,
              "project": {"id": configuration["project"]["id"], "name": configuration["project"]["name"],
                          "path": str(root), "purpose": configuration["project"]["purpose"]},
              "run_id": state["run_id"], "request": state["request"],
              "facts": facts, "trace_sha256": trace["sha256"],
              "authority": "RECORDED_WORK_NOT_HUMAN_MASTERY",
              "share_with_ai": False, "created_at": (old or {}).get("created_at", profile.now())}
    if old != record:
        profile.put_record(record)
    return record


def _save_report(journal, request, call, identity):
    document = call["document"]
    report = {"id": identity, "kind": "report", "journal_id": journal["id"] if journal else "",
              "work_key": journal["work_key"] if journal else "",
              "model": call["model"], "schema_version": 1, "request_sha256": digest(request),
              "trace_sha256": request["trace"]["sha256"],
              "sources": [{"source_ref": row["source_ref"], "event_hash": row.get("event_hash"),
                           "type": row["type"]} for row in request["trace"]["events"]],
              "profile_refs": [row["id"] for row in request["personal_context"].get("records", [])]
                              + [row["id"] for row in request["personal_context"].get("learning", [])]
                              + [row["id"] for row in request["personal_context"].get("notes", [])],
              "proposal": document, "status": "PROPOSED", "authority": "AI_INTERPRETATION",
              "created_at": profile.now()}
    profile.put_record(report)
    visible = []
    pref = profile.preferences()
    for index, item in enumerate(document["lessons"]):
        value = {**deepcopy(item), "id": identity + "-lesson-" + str(index), "kind": "lesson",
                 "journal_id": report["journal_id"], "work_key": report["work_key"],
                 "report_id": identity, "model": call["model"], "choice": "OPEN",
                 "share_with_ai": pref["share_with_ai"], "authority": "AI_LEARNING_CANDIDATE",
                 "created_at": profile.now(), "feedback": []}
        if profile.get_record(value["id"]):
            continue
        profile.put_record(value)
        if item["goal"] in ("OWN", "REVIEW") and journal and profile.reserve_lesson(value["id"], journal["work_key"]):
            visible.append(value["id"])
    for index, item in enumerate(document["profile_updates"]):
        value = {"id": identity + "-update-" + str(index), "kind": "proposal",
                 "work_key": report["work_key"], "journal_id": report["journal_id"],
                 "report_id": identity, "proposal": deepcopy(item), "status": "PENDING_OWNER",
                 "profile_refs": report["profile_refs"], "authority": "AI_PROPOSAL_NOT_OWNER_PROFILE",
                 "model": call["model"], "created_at": profile.now()}
        if not profile.get_record(value["id"]):
            profile.put_record(value)
    return {"status": "PROPOSED", "report_id": identity, "journal_id": report["journal_id"],
            "visible_lessons": visible, "model": call["model"], "profile_updates_applied": 0}


def capture_work(root, configuration, state, *, adapter=None, key=None, timeout=None, explicit=False):
    if not profile.preferences()["enabled"]:
        return {"status": "OFF"}
    from .agent_schema import trace_from_events, reflection_events
    from .storage.sqlite import EventStore
    with EventStore(root, configuration["project"]["id"]) as store:
        events = store.events(state["run_id"])
    trace = trace_from_events(reflection_events(events, state["work_result"]["revision"], state["revision"]))
    journal = _journal(root, configuration, state, trace)
    pref = profile.preferences()
    if adapter is None or not pref["share_with_ai"] or (pref["mode"] == "on_demand" and not explicit):
        return {"status": "FACTS_SAVED", "journal_id": journal["id"],
                "meaning": "UNORGANIZED", "visible_lessons": []}
    identity = "growth-" + digest({"journal": journal["id"], "generation": key or uuid.uuid4().hex})[:32]
    prior = profile.get_record(identity)
    if prior:
        return {"status": prior["status"], "report_id": identity, "journal_id": journal["id"],
                "visible_lessons": [], "replayed": True}
    request = {"format": REQUEST, "mode": "reflect", "generation_id": identity, "trace": trace,
               "response_locale": configuration["ui"]["locale"],
               "personal_context": context(), "work_facts": journal["facts"],
               "project_purpose": configuration["project"]["purpose"],
               "output_contract": CONTRACT}
    call = private_call(adapter, request, key=identity, timeout=timeout)
    return _save_report(journal, request, call, identity)


def capture_safe(root, configuration, state, **kwargs):
    try:
        return capture_work(root, configuration, state, **kwargs)
    except Exception as error:
        return {"status": "UNORGANIZED", "reason": getattr(error, "code", type(error).__name__),
                "work_result_unchanged": True, "visible_lessons": []}


def converse(root, configuration, text, *, key=None):
    from .agent_models import selected_work, selected_reflection
    profile.require(type(text) is str and 0 < len(text.strip()) <= 8000, "PERSONAL_MESSAGE")
    profile.require(configuration is not None, "PROJECT_MODEL_CONFIGURATION_REQUIRED")
    adapter = selected_reflection(root, configuration, selected_work(root, configuration))
    profile.require(adapter is not None, "REFLECTION_IS_OFF")
    identity = "conversation-" + (key or uuid.uuid4().hex)
    source = {"source_ref": identity + ":owner", "actor_kind": "HUMAN",
              "type": "PersonalOwnerMessage", "payload": {"text": text},
              "event_hash": digest(text)}
    request = {"format": REQUEST, "mode": "conversation", "generation_id": identity,
               "trace": {"events": [source], "sha256": digest(source)},
               "response_locale": configuration["ui"]["locale"],
               "personal_context": context(), "work_facts": {},
               "project_purpose": "", "output_contract": CONTRACT}
    call = private_call(adapter, request, key=identity)
    result = _save_report(None, request, call, identity)
    return {**result, "reply": call["document"]["reply"],
            "updates": [identity + "-update-" + str(i)
                        for i in range(len(call["document"]["profile_updates"]))]}


def accept_update(identity, *, share=False, scope=None):
    row = profile.get_record(identity)
    profile.require(row and row["kind"] == "proposal" and row["status"] == "PENDING_OWNER",
                    "PERSONAL_PROPOSAL_REQUIRED")
    value = row["proposal"]
    scope = scope or value["scope"]
    if value["category"] == "pace":
        result = profile.configure(_pace_changes(value["preference_changes"]), scope=scope)
    else:
        result = profile.statement(value["text"], technology=value["technology"], kind=value["category"],
                                   share=share, scope=scope, record_id=value["target_id"] or None,
                                   source={"kind": "OWNER_ACCEPTED_AI_DRAFT", "proposal_id": identity,
                                           "human_quote": value["human_quote"]})
    row.update(status="ACCEPTED_BY_OWNER", owner_scope=scope, owner_share=share,
               accepted_at=profile.now())
    profile.put_record(row)
    return result


def reject_update(identity):
    row = profile.get_record(identity)
    profile.require(row and row["kind"] == "proposal", "PERSONAL_PROPOSAL_REQUIRED")
    row["status"] = "DISMISSED_BY_OWNER"
    return profile.put_record(row)


def portfolio(journal_ids, *, personal_summary="", experience_ids=()):
    profile.require(len(journal_ids) <= 100 and len(set(journal_ids)) == len(journal_ids), "PORTFOLIO_SELECTION")
    profile.require(type(personal_summary) is str and len(personal_summary) <= 16000, "PORTFOLIO_SUMMARY")
    rows = []
    for identity in journal_ids:
        row = profile.get_record(identity)
        profile.require(row and row["kind"] == "journal", "PERSONAL_JOURNAL_REQUIRED")
        # No private notes, full request, paths, hashes or AI learning diagnosis leak into the public selection.
        rows.append({"journal_id": identity, "project_name": row["project"]["name"],
                     "date": row["created_at"][:10], "work_status": row["facts"]["work_status"],
                     "candidate_file_count": len(row["facts"]["artifacts"]),
                     "collaboration": "AI-assisted development; not a claim of independent implementation",
                     "human_contribution": "Use the owner's explicit description below; not inferred from generated code."})
    profile.require(len(experience_ids) <= 100 and len(set(experience_ids)) == len(experience_ids),
                    "PORTFOLIO_EXPERIENCE_SELECTION")
    learning = []
    for identity in experience_ids:
        row = profile.get_record(identity)
        profile.require(row and row["kind"] in ("statement", "lesson", "skill_progress"), "PORTFOLIO_EXPERIENCE_REQUIRED")
        if row["kind"] == "statement":
            profile.require(row["category"] in ("experience", "understanding", "goal"),
                            "PORTFOLIO_PRIVATE_CATEGORY")
            learning.append({"technology": row["technology"], "category": row["category"],
                             "owner_words": row["text"], "recorded_at": row["created_at"],
                             "authority": "OWNER_SELF_REPORT_NOT_CERTIFICATION"})
        elif row["kind"] == "skill_progress":
            profile.require(row["human"] != "NO_RECORD", "PORTFOLIO_OWNER_EXAMPLE_REQUIRED")
            learning.append({"technology_tags": row["technology_tags"], "category": "skill_history",
                             "title": row["title"], "owner_words": row["note"],
                             "claim": row["human"], "recorded_at": row["updated_at"],
                             "AI_assisted": True, "authority": "OWNER_SELF_REPORT_NOT_CERTIFICATION"})
        else:
            feedback = [item for item in row.get("feedback", []) if
                        item["choice"].startswith("SELF_REPORTED") and item["text"].strip()]
            profile.require(feedback, "PORTFOLIO_OWNER_EXAMPLE_REQUIRED")
            learning.append({"technology": row["technology"], "category": "learning_history",
                             "owner_examples": [{"text": item["text"], "recorded_at": item["recorded_at"],
                                                 "claim": item["choice"]} for item in feedback],
                             "authority": "OWNER_SELF_REPORT_NOT_CERTIFICATION"})
    return {"format": "verantyx.personal-portfolio.v1", "selected_work": rows,
            "selected_experience": learning,
            "owner_description": personal_summary, "authority": "OWNER_SELECTED_SELF_REPORT",
            "mastery_certification": False, "published": False}


def panel(snapshot):
    pref, rows = snapshot["settings"], snapshot["records"]
    if not pref["enabled"]:
        return ["MY NOTEBOOK / 自分の経験", "F2 > My profile で任意に始められます。未登録は未経験ではありません。"]
    pending = sum(row.get("status") == "PENDING_OWNER" for row in rows["proposal"])
    next_time = sum(row.get("choice") == "NEXT_TIME" for row in rows["lesson"])
    lines = ["MY NOTEBOOK / プロジェクトを越えて残るもの",
            "自分の記録 " + str(snapshot["counts"].get("statement", 0))
            + " / 日記 " + str(snapshot["counts"].get("journal", 0))
            + " / 次の機会 " + str(next_time) + " / 更新候補 " + str(pending),
            "提案: " + pref["mode"] + " / " + pref["weight"] + " / 1日最大 " + str(pref["daily_limit"]),
            "F2 > My profile / My journal / Next time / My pace",
            "自己申告・AI提案・実行記録は別物です。能力の点数は付けません。"]
    from .skill_assets import MARKS, ON_BOARD
    chosen = [row for row in rows.get("skill_progress", []) if row["plan"] in ON_BOARD]
    lines += ["", "MY SKILLS / 自分が選んだ穴だけ育てる",
              "個人カタログのAI手順 " + str(snapshot["counts"].get("skill_asset", 0)) + "件 / F2 > My skills"]
    lines += [MARKS[row["human"]] + " " + row["title"] + " / " + row["plan"] for row in chosen[:3]]
    if len(chosen) > 3 or snapshot.get("omitted", {}).get("skill_progress", 0):
        lines.append("ほかの選択・過去の記録はMy skillsから。全項目を埋める必要はありません。")
    return lines


_PACE_CACHE = (0.0, False)


def uses_personal_pace():
    """UI-only cache. Never used for sharing consent or operation permission."""
    global _PACE_CACHE
    at, enabled = _PACE_CACHE
    if time.monotonic() - at > 0.5:
        try:
            enabled = profile.preferences()["onboarded"]
        except Exception:
            enabled = True  # A display failure must not create extra homework.
        _PACE_CACHE = (time.monotonic(), enabled)
    return enabled


def ui_state(previous=None):
    """Refresh only after the private store changes; no model call on repaint."""
    if previous is not None and previous.get("revision") == profile.revision():
        return previous
    return profile.snapshot()


def reference_items(snapshot):
    """Local completion/search index. Only an explicit selection sends these."""
    from .cleanroom_owner import make_item
    if not snapshot or not snapshot["settings"]["enabled"]:
        return []
    items = []
    for row in snapshot["records"]["statement"]:
        if not profile.active(row):
            continue
        label = (row.get("technology", "") + " " + row["text"]).strip()[:110]
        items.append(make_item("note", label,
            {key: row.get(key) for key in ("text", "technology", "category", "scope", "authority")},
            source_ref="personal:" + row["id"]))
    for row in snapshot["records"]["lesson"]:
        if row.get("choice") == "DISMISS":
            continue
        items.append(make_item("learning", row["title"],
            {key: row.get(key) for key in ("title", "minimum_step", "choice", "authority", "source_event_ids")},
            source_ref="personal:" + row["id"]))
    return items
