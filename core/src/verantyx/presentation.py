"""Localized, deterministic explanations of recorded facts; never authority.

Catalogs are frozen at import. narrative_facts/fallback_text/render_reply read
only their arguments: no clock, model call, event write, or file observation.
"""
from copy import deepcopy
import unicodedata

from .domain.codec import digest
from .i18n import LANGUAGES, catalog, normalize

MAX_FACTS = 48
_CATALOGS = {locale: dict(catalog(locale)) for locale in LANGUAGES}


def _locale(locale):
    return locale if locale in _CATALOGS else normalize(locale)


def _text(locale, key, **values):
    return _CATALOGS[_locale(locale)]["presentation." + key].format(**values)


def safe_text(value, *, multiline=False):
    """Keep answer paragraphs, but render terminal and bidi controls visibly."""
    return "".join(c if (multiline and c == "\n") or unicodedata.category(c) not in ("Cc", "Cf")
                   else f"\\u{ord(c):04x}" for c in str(value))


def _clip(value, limit=400):
    value = str(value)
    return value if len(value) <= limit else value[:limit - 1] + "…"


def _refs(*values):
    result = []
    for value in values:
        if type(value) is str and value:
            result.append(value)
        elif type(value) in (list, tuple):
            result.extend(item for item in value if type(item) is str and item)
    return sorted(set(result))


def localized_status(code, locale, *, domain=None):
    """A display label only; preserve the original code in the source object."""
    messages = _CATALOGS[_locale(locale)]
    choices = (["presentation." + domain + "." + str(code)] if domain else [])
    choices += ["presentation.status." + str(code), "state." + str(code), "effect.status." + str(code)]
    return next((messages[key] for key in choices if key in messages), _text(locale, "unclassified"))


def gap_text(gap, locale):
    code = gap.get("code", "UNKNOWN")
    messages = _CATALOGS[_locale(locale)]
    return messages.get("presentation.gap." + code, messages.get("gap." + code, _text(locale, "gap_unknown")))


def _facts_content(value):
    # Rendering edits do not invalidate the recorded meaning of an answer.
    # A response event also advances revision without changing its prior facts.
    result = {key: deepcopy(value.get(key)) for key in ("schema_version", "locale", "run_id", "facts", "next_steps", "omitted_count")}
    for key in ("facts", "next_steps"):
        if type(result[key]) is list:
            for row in result[key]:
                if type(row) is dict:
                    row.pop("text", None)
    return result


def narrative_facts(state, locale):
    """Return at most 48 cited facts with IDs stable across display languages.

    The machine codes and cited evidence remain separate from their prose.
    Negative results and decisions come before ordinary progress details.
    """
    locale = _locale(locale)
    assessment = state.get("assessment") or {}
    gaps = assessment.get("gaps", [])
    claims = assessment.get("claims", [])
    judgments = assessment.get("judgments", [])
    proposal = state.get("proposal") or {}
    anchor = _refs(state.get("proposal_ref"), state.get("request_ref"))
    rows = []

    def add(category, code, message, *, subject=None, refs=(), details=None, priority=5):
        identity = {"category": category, "code": code, "subject": subject,
                    "source_refs": _refs(refs), "details": deepcopy(details or {})}
        row = {"id": "fact-" + digest(identity)[:32], **identity, "text": message}
        rows.append((priority, len(rows), row))
        return row

    gap_codes = {gap.get("code") for gap in gaps}
    properties = [claim.get("property_evidence") or {} for claim in claims]
    property_statuses = {item.get("epistemic_status") for item in properties}
    if "CONTESTED" in property_statuses or any(gap.get("classification") == "CONTESTED" for gap in gaps):
        lead = "contested"
    elif "REFUTED" in property_statuses or gap_codes & {"PROPERTY_REFUTED", "CANDIDATE_TEST_FAILED"}:
        lead = "refuted"
    elif gap_codes & {"EXECUTION_OUTCOME_UNKNOWN", "INTEGRATION_OUTCOME_UNKNOWN", "ADOPTION_OUTCOME_UNKNOWN"}:
        lead = "uncertain_execution"
    elif assessment.get("question") is not None or gap_codes & {"VALUE_DECISION_REQUIRED", "SCOPE_MISMATCH", "RULE_EXCEPTION_APPLIES"}:
        lead = "decision"
    elif gap_codes & {"AUTHORITY_REQUIRED", "READ_SCOPE_NOT_GRANTED"}:
        lead = "permission"
    elif gap_codes & {"STALE_SOURCE", "SOURCE_CHANGED", "AUTHORIZATION_STALE", "RULE_ENGINE_CHANGED", "EDITOR_DECISION_CHANGED", "EDITOR_REFERENCE_CHANGED"}:
        lead = "stale"
    elif not proposal:
        lead = "no_proposal"
    elif assessment.get("strategy") == "EXECUTE":
        lead = "ready"
    else:
        lead = "open"
    summary = _text(locale, "summary." + lead)
    add("strategy", assessment.get("strategy", "UNKNOWN"), summary, refs=anchor,
        details={"situation": lead}, priority=0)
    # A passing predicate does not entail an arbitrary sentence attached to it.
    has_property_result = any(item.get("current_evidence_refs") for item in properties)
    evidence_key = ("evidence_with_checks" if has_property_result else
                    "evidence_without_checks" if proposal else "evidence_no_proposal")
    add("evidence", assessment.get("evidence", "UNKNOWN"), _text(locale, evidence_key), refs=anchor,
        details={"prose_entailment": "NOT_ASSESSED", "has_property_result": has_property_result}, priority=0)
    learning = list(state.get("learning_candidates", {}).values())
    reports = [evidence for item in learning for evidence in item.get("evidence", [])]
    self_reported = bool(reports) or any(item.get("mastery_evidence") == "SELF_REPORTED"
                                      for item in state.get("deltas", {}).get("human_delta", []))
    add("ownership", assessment.get("ownership", "UNASSESSED"),
        _text(locale, "ownership_reported" if self_reported else "ownership_unassessed"),
        refs=_refs(anchor, [item.get("source_ref") for item in reports]),
        details={"mastery_evidence": "SELF_REPORTED" if self_reported else "NONE", "mastery_assessment": "NOT_ASSESSED"}, priority=0)

    # The bounded property evidence is reported independently of prose claims.
    for claim in claims:
        evidence = claim.get("property_evidence")
        if not evidence:
            continue
        status = evidence.get("epistemic_status", "UNKNOWN")
        situation = {"SUPPORTED": "supported", "REFUTED": "refuted", "CONTESTED": "contested"}.get(status, "unknown")
        subject = claim.get("id", "")
        refs = evidence.get("current_evidence_refs", [])
        if not refs:
            refs = [item.get("source_ref") for item in claim.get("evidence", [])]
        add("property_evidence", status, _text(locale, "property." + situation, subject=_clip(subject)),
            subject=subject, refs=_refs(refs, state.get("proposal_ref")),
            details={"closure": evidence.get("closure", "UNKNOWN"), "scope": evidence.get("scope"),
                     "reason": evidence.get("reason"), "prose_entailment": claim.get("prose_entailment", "NOT_ASSESSED")},
            priority=1 if situation in ("refuted", "contested") else 4)

    for gap in gaps:
        code = gap.get("code", "UNKNOWN")
        important = code in {"PROPERTY_REFUTED", "CANDIDATE_TEST_FAILED", "VERIFICATION_CONFLICT", "RULE_CONFLICT", "RULE_CONTESTED"}
        priority = 1 if important else (2 if gap.get("classification") == "UNDECIDED_HUMAN" else 3)
        add("gap", code, gap_text(gap, locale), subject=gap.get("item_id", gap.get("point_id")),
            refs=_refs(gap.get("source_ref"), gap.get("source_refs")),
            details={key: deepcopy(gap[key]) for key in ("classification", "blocker", "epistemic_status") if key in gap}, priority=priority)

    points = {point["id"]: point for point in proposal.get("decision_points", [])}
    for judgment in judgments:
        point_id, status = judgment.get("point_id"), judgment.get("status", "UNKNOWN")
        point = points.get(point_id, {})
        choice = judgment.get("choice")
        label = next((option["label"] for option in point.get("options", []) if option["id"] == choice), choice or "")
        question = judgment.get("question") or point_id or ""
        if status in ("PRECEDENT_MATCHED", "HUMAN_DECIDED"):
            key = "rule_reused" if status == "PRECEDENT_MATCHED" else "decision_recorded"
            add("judgment", status, _text(locale, key, question=_clip(question), choice=_clip(label)),
                subject=point_id, refs=judgment.get("rule_refs", []),
                details={"choice": choice, "choice_label": _clip(label), "question": _clip(question), "scope": deepcopy(judgment.get("scope"))}, priority=4)
        elif judgment.get("kind") == "VALUE_DECISION" and status in ("UNDECIDED_HUMAN", "UNSCOPED_RULE"):
            add("judgment", status, _text(locale, "decision_waiting", question=_clip(question)),
                subject=point_id, refs=anchor, details={"question": _clip(question)}, priority=2)
        for advisory in judgment.get("advisories", []):
            if advisory.get("outcome") == "OUT_OF_SCOPE":
                continue
            mode = advisory.get("enforcement")
            key = "rule_exception" if advisory.get("outcome") == "EXEMPTED" else ("rule_shadow" if mode == "SHADOW" else "rule_warning")
            description = _text(locale, key)
            enforcement = _CATALOGS[locale].get("presentation.enforcement." + str(mode))
            if enforcement:
                description = enforcement + ": " + description
            add("rule_advisory", advisory.get("outcome", "UNKNOWN"), description, subject=point_id,
                refs=_refs(advisory.get("source_ref"), advisory.get("rule_ref")),
                details={"mode": mode, "rule_id": advisory.get("rule_id"), "choice": advisory.get("choice")}, priority=2)

    for action in assessment.get("actions", []):
        gate = action.get("gate", "UNKNOWN")
        if gate in ("AUTHORIZED", "CANDIDATE_TESTED", "CANDIDATE_REFUTED", "CANDIDATE_UNVERIFIED", "PREPARED", "OBSERVATION_AVAILABLE"):
            add("action", gate, _text(locale, "action." + gate), subject=action.get("id"),
                refs=_refs(action.get("receipt_ref"), action.get("observation_ref"), state.get("proposal_ref")),
                details={"tool_id": action.get("tool_id"), "reason": action.get("reason")},
                priority=1 if gate == "CANDIDATE_REFUTED" else 4)
    add("build", assessment.get("build", "IN_PROGRESS"), _text(locale, "build_recorded"), refs=anchor, priority=5)

    unique = {}
    for priority, order, row in rows:
        unique.setdefault(row["id"], (priority, order, row))
    ordered = [row for _, _, row in sorted(unique.values(), key=lambda item: (item[0], item[1]))]
    selected = ordered[:MAX_FACTS]
    steps = []
    step_keys = []
    if lead in ("refuted", "contested"):
        step_keys.append("review_checks")
    if lead in ("decision", "permission"):
        step_keys.append("record_choice" if lead == "decision" else "review_permission")
    if lead == "stale":
        step_keys.append("refresh")
    if lead == "uncertain_execution":
        step_keys.append("inspect_receipt")
    if lead in ("no_proposal", "open"):
        step_keys.append("continue")
    for key in step_keys[:3]:
        steps.append({"id": "step-" + digest({"key": key, "refs": anchor})[:32], "code": key.upper(),
                      "text": _text(locale, "next." + key), "source_refs": anchor})
    return {"schema_version": 1, "locale": locale, "run_id": state.get("run_id"),
            "basis_revision": state.get("revision", 0), "summary": summary, "facts": selected,
            "next_steps": steps, "omitted_count": len(ordered) - len(selected)}


def fallback_text(state, locale):
    value = narrative_facts(state, locale)
    complete = list(dict.fromkeys(item["text"] for item in value["facts"]))
    paragraphs, used = [], 0
    for paragraph in complete:
        if used + len(paragraph) + 2 > 14000:
            break
        paragraphs.append(paragraph)
        used += len(paragraph) + 2
    omitted = value["omitted_count"] + len(complete) - len(paragraphs)
    if omitted:
        paragraphs.append(_text(locale, "omitted", count=omitted))
    paragraphs.extend(item["text"] for item in value["next_steps"])
    return "\n\n".join(paragraphs)


def response_freshness(state, locale, response=None):
    response = response if response is not None else state.get("latest_response")
    if not response:
        return "ABSENT"
    if response.get("locale") != _locale(locale):
        return "OTHER_LOCALE"
    if response.get("context_compatibility") == "V063_HANDOFF_HISTORY":
        return "CONTEXT_CHANGED"
    if (not response.get("command_id") or response.get("command_id") != state.get("last_command_id") or
            type(response.get("basis_revision")) is not int or
            response.get("basis_revision") != state.get("command_start_revision") or
            response.get("proposal_ref") != state.get("proposal_ref") or
            type(response.get("recorded_revision")) is not int or
            not response["basis_revision"] < response["recorded_revision"] <= state.get("revision", 0)):
        return "HISTORICAL"
    facts = response.get("facts")
    if type(facts) is not dict or _facts_content(facts) != _facts_content(narrative_facts(state, locale)):
        return "CONTEXT_CHANGED"
    handoff = (response.get("request_snapshot") or {}).get("editor_handoff")
    if handoff:
        from .shared_context import current_editor_attempt
        attempt = current_editor_attempt(state)
        if attempt is None or handoff.get("source_ref") != attempt["source_ref"]:
            return "CONTEXT_CHANGED"
    return "CURRENT"


def render_reply(state, locale, generated_reply=None, *, include_sources=False, include_codes=False):
    """Render a useful answer and its recorded constraints without changing either."""
    locale = _locale(locale)
    bundle = narrative_facts(state, locale)
    response = generated_reply if generated_reply is not None else state.get("latest_response")
    freshness = response_freshness(state, locale, response)
    paragraphs = []
    proposal = state.get("proposal") or {}
    if state.get("trust") == "ARCHIVE_ONLY":
        paragraphs.append(_text(locale, "archive"))
    if freshness == "CURRENT":
        document = response.get("document") or {}
        if response.get("mode") == "FALLBACK" and response.get("generator_error"):
            paragraphs.append(_text(locale, "generator_failed"))
            reason = _CATALOGS[locale].get("error." + str(response["generator_error"]))
            if reason:
                paragraphs.append(safe_text(reason, multiline=True))
        answer = document.get("answer", "")
        if answer and answer != fallback_text(state, locale):
            title = "generated_answer" if response.get("mode") == "GENERATED" else "proposed_answer"
            paragraphs.extend((_text(locale, title), safe_text(answer, multiline=True)))
        known = {item["id"] for item in bundle["facts"]}
        explanations = [item.get("text", "") for item in document.get("explanations", []) if item.get("fact_id") in known]
        # Identical fallback explanations are already present in the fact block.
        fixed = {item["text"] for item in bundle["facts"]}
        explained = list(dict.fromkeys(text for text in explanations if text and text not in fixed))
        if explained:
            paragraphs.append(_text(locale, "generated_explanations"))
            paragraphs.extend(safe_text(text, multiline=True) for text in explained)
    else:
        if freshness != "ABSENT":
            paragraphs.append(_text(locale, "response_other_locale" if freshness == "OTHER_LOCALE" else "response_historical"))
        if proposal.get("summary"):
            paragraphs.append(_text(locale, "proposed_answer"))
            if proposal.get("response_locale") != locale:
                paragraphs.append(_text(locale, "proposal_other_locale"))
            paragraphs.append(safe_text(proposal["summary"], multiline=True))
    paragraphs.append(_text(locale, "recorded_facts"))
    if state.get("handoff_plan"):
        from .i18n import text
        from .shared_context import current_editor_attempt
        attempt = current_editor_attempt(state)
        from .decision_context import handoff_status
        paragraphs.append(text(locale, "context." + handoff_status(state)))
        if attempt:
            paragraphs.append(text(locale, "context.boundary"))
    seen = set()
    for item in bundle["facts"]:
        sentence = safe_text(item["text"], multiline=True)
        if sentence in seen and not include_sources and not include_codes:
            continue
        seen.add(sentence)
        if include_codes:
            sentence += " [" + safe_text(item["code"]) + "]"
        if include_sources and item["source_refs"]:
            sentence += "\n" + _text(locale, "sources", refs=", ".join(safe_text(ref) for ref in item["source_refs"]))
        paragraphs.append(sentence)
    if bundle["omitted_count"]:
        paragraphs.append(_text(locale, "omitted", count=bundle["omitted_count"]))
    paragraphs.extend(safe_text(item["text"], multiline=True) for item in bundle["next_steps"])
    return "\n\n".join(paragraphs)


def display_reply(state, locale, generated_reply=None, *, include_sources=False, include_codes=False):
    print(render_reply(state, locale, generated_reply, include_sources=include_sources, include_codes=include_codes))


def display_verification(result, locale):
    """Keep review identifiers while explaining success/failure in its real scope."""
    item = result["verification"]
    plan = item["plan"]
    receipt = item.get("receipt") or {}
    checked = receipt.get("result") or {}
    print(_text(locale, "verification_record", identifier=safe_text(plan["id"])))
    print(_text(locale, "verification_target", target=safe_text(plan["target"]["path"])))
    print(_text(locale, "verification_property", property=safe_text(plan["spec"]["property"])))
    print(localized_status(item["status"], locale, domain="verification"))
    if checked:
        print(localized_status(checked.get("closure", "UNKNOWN"), locale, domain="verification"))
    elif receipt.get("reason"):
        print(gap_text({"code": receipt["reason"]}, locale))
    if item.get("receipt_ref") or item.get("source_ref"):
        print(_text(locale, "sources", refs=item.get("receipt_ref", item.get("source_ref"))))
    if result.get("state"):
        display_reply(result["state"], locale)
