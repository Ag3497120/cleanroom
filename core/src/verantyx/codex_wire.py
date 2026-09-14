"""Lossless editor transport without JSON nested inside a generated string.

Only file-map and citation representations change. Local validators remain
authoritative; this module never fills meanings, choices or permissions.
"""
from copy import deepcopy
from hashlib import sha256

from .errors import LedgerError

EDITOR = "verantyx.editor-request.v1"
PLAN = "verantyx.handoff-plan-request.v1"
RESPONSE = "verantyx.response-request.v1"


def _object(properties):
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


def _array(items, maximum):
    return {"type": "array", "items": items, "maxItems": maximum}


def _enum(values):
    values = list(dict.fromkeys(values))
    return {"type": "string", "enum": values} if values else {"type": "string"}


def _alternative_slots(plan):
    return [{"interpretation_id": node["id"],
             "ref": node["id"] + ":alternative-" + str(index + 1) + ":" + sha256(body.encode("utf-8")).hexdigest(),
             "text": body}
            for node in plan["interpretations"] for index, body in enumerate(node.get("alternatives", []))]


def editor_contract(value):
    from .shared_context import DISPOSITIONS, STRENGTHS, RELATIONS
    plan = value["interpretation_proposal"]
    ids = [node["id"] for node in plan["interpretations"]]
    cases = plan["cases"]
    text = {"type": "string"}
    document = _object({
        "context_sha256": _enum([value["shared_context"]["sha256"]]),
        "plan_sha256": _enum([value["response_template"]["plan_sha256"]]),
        "acknowledgements": _array(_object({
            "id": _enum(ids), "disposition": _enum(DISPOSITIONS),
            "strength": _enum(STRENGTHS), "interpretation": text,
            "alternatives": _array(text, 8)}), len(ids)),
        "relations": _array(_object({"kind": _enum(RELATIONS),
            "from": _enum(ids), "to": _enum(ids)}), 128),
        "case_choices": _array(_object({"id": _enum([case["id"] for case in cases]),
            "choice": _enum([choice["id"] for case in cases for choice in case["choices"]] + ["UNRESOLVED"]),
            "reason": text}), len(cases)),
        "files": _array(_object({"path": text, "content": text}), 16),
        "tests": _array(text, 16),
        "notes": {"type": "string", "maxLength": 8000},
    })
    request = deepcopy(value)
    template = request["response_template"]
    template["files"] = [{"path": path, "content": content} for path, content in template["files"].items()]
    request["output_contract"] = request.get("output_contract", "") + (
        " Wire representation for this adapter only: document is a JSON OBJECT, not a JSON string. "
        "Replace the files map with an array of {path, content} objects, each path at most once. "
        "Content is the complete file text; preserve its whitespace. All other fields keep the original contract. "
        "Copy fixed_tests into tests when supplied; do not modify fixed tests or claim to have executed them. "
        "The host restores the files map losslessly and validates the original contract.")
    alternatives = _alternative_slots(plan)
    if alternatives:
        variants = []
        for node in plan["interpretations"]:
            refs = [slot["ref"] for slot in alternatives if slot["interpretation_id"] == node["id"]]
            variants.append(_object({
                "id": _enum([node["id"]]), "disposition": _enum(DISPOSITIONS),
                "strength": _enum(STRENGTHS), "interpretation": text,
                "alternative_refs": _array(_enum(refs), len(refs)),
                "alternatives": _array(text, 8)}))
        document["properties"]["acknowledgements"] = _array({"anyOf": variants}, len(ids))
        request["alternative_slots"] = deepcopy(alternatives)
        request["output_contract"] += (
            " Wire override for acknowledgements: alternative_refs names existing alternative_slots "
            "you independently consider plausible for that interpretation; alternatives contains only "
            "NEW plausible meanings not already represented by a selected reference. "
            "Select no reference when you reject those alternatives. Never select merely to agree. "
            "Refer to an existing alternative verbatim by ref rather than paraphrasing it. "
            "If you disagree or remain uncertain, preserve it through different selections, new alternatives "
            "or UNRESOLVED. Obvious violations belong in choice cases, not plausible alternatives. "
            "The host restores selected texts without judging semantic equivalence. References do not "
            "prove agreement with the user or authorize actions. Preserve order, do not repeat refs, "
            "and return at most eight selected plus new alternatives per interpretation.")
    return request, _object({"document": document})


def _citation_slots(value):
    from .coordination_schema import source_units
    return [{**unit, "quote_ref": unit["id"] + ":" + sha256(unit["quote"].encode("utf-8")).hexdigest()}
            for unit in source_units(value)]


def plan_contract(value):
    from .shared_context import DISPOSITIONS, STRENGTHS, RELATIONS
    units = _citation_slots(value)
    ids = [unit["id"] for unit in units]
    text = {"type": "string"}
    # Exact source bytes stay in the request, never in provider enum literals.
    # References bind slots to those bytes; they are not execution capabilities.
    interpretations = _array({"anyOf": [
        _object({**{name: _enum([unit[name]]) for name in ("id", "source_id", "quote_ref")},
                 "meaning": text, "disposition": _enum(DISPOSITIONS),
                 "strength": _enum(STRENGTHS), "alternatives": _array(text, 8)})
        for unit in units]}, len(units))
    interpretations["minItems"] = len(units)
    case_slots = [{"id": "case-" + str(i // 2 + 1), "interpretation_ids": ids[i:i + 2]}
                  for i in range(0, len(ids), 2)]
    case_variants = []
    for slot in case_slots:
        covered = _array(_enum(slot["interpretation_ids"]), len(slot["interpretation_ids"]))
        covered["minItems"] = len(slot["interpretation_ids"])
        choices = _array(_object({"id": _enum(["choice-A", "choice-B"]), "text": text}), 2)
        choices["minItems"] = 2
        case_variants.append(_object({
            "id": _enum([slot["id"]]), "situation": text, "choices": choices,
            "expected": _enum(["choice-A", "choice-B"]), "interpretation_ids": covered}))
    cases = _array({"anyOf": case_variants}, len(case_slots))
    cases["minItems"] = len(case_slots)
    document = _object({
        "context_sha256": _enum([value["shared_context"]["sha256"]]),
        "interpretations": interpretations,
        "relations": _array(_object({"kind": _enum(RELATIONS),
            "from": _enum(ids), "to": _enum(ids)}), 128),
        "cases": cases,
    })
    request = deepcopy(value)
    request["citation_slots"] = deepcopy(units)
    request["case_slots"] = deepcopy(case_slots)
    request["output_contract"] = request.get("output_contract", "") + (
        " Return document as a JSON OBJECT, not an encoded JSON string. "
        "Wire override: replace each interpretation's quote field with quote_ref. "
        "Copy each citation_slots entry's id, source_id and quote_ref exactly once. "
        "Read its quote as source data, but do not output or paraphrase the quote field. "
        "The host restores quote byte-for-byte from the original request after validating all references. "
        "Generate interpretation in meaning only. "
        "For each case_slots entry, generate exactly one case with its fixed id and all its "
        "interpretation_ids, once each, including the last slot. Generate a concrete situation and "
        "two distinct observable choices that exercise ALL assigned interpretations. "
        "Case slots ensure structural coverage only, not correct interpretation or successful execution. "
        "Retain all original source slots and case coverage; do not omit uncertainty or invent agreement. "
        "No execution or permission is implied by this proposal.")
    return request, _object({"document": document})




def is_skill_proposal(value):
    from .personal_skills import REQUEST
    return (value.get("format") == "verantyx.proposal-request.v1"
            and value.get("task", {}).get("request") == REQUEST
            and not value.get("selected_files"))


def skill_proposal_contract(value):
    """A reference-only asset proposal: no action capabilities on this path."""
    from .responses import _references
    if not is_skill_proposal(value):
        raise LedgerError("BRIDGE_PROTOCOL", {"reason": "CODEX_SKILL_PROPOSAL_SCOPE"})
    template = value["proposal_template"]
    identifier = {"type": "string", "minLength": 1, "maxLength": 128,
                  "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]*$"}
    refs = sorted(set(_references(value)))
    document = _object({
        "schema_version": {"type": "integer", "enum": [template["schema_version"]]},
        "task_id": _enum([template["task_id"]]),
        "context_revision": {"type": "integer", "enum": [template["context_revision"]]},
        "response_locale": _enum([template["response_locale"]]),
        "summary": {"type": "string", "minLength": 1, "maxLength": 4000},
        "claims": _array(_object({
            "id": identifier,
            "statement": {"type": "string", "minLength": 1, "maxLength": 4000},
            "source_refs": {"type": "array", "maxItems": 16, "items": _enum(refs)},
        }), 32),
        "actions": _array(_object({}), 0),
        "unknowns": _array(_object({
            "id": identifier,
            "question": {"type": "string", "minLength": 1, "maxLength": 2000},
            "needed_observation": {"type": "string", "minLength": 1, "maxLength": 2000},
        }), 16),
    })
    request = deepcopy(value)
    request["output_contract"] += (
        " This is the reference-only personal-skills import path, not a code-edit request. "
        "Return document as a JSON OBJECT, not an encoded JSON string. Keep actions empty. "
        "Retain attributed judgments, conditions, procedures and counterexamples in the proposal. "
        "Use unknowns for missing observations; never invent a resolution or approval. "
        "Copy exact source_ref identifiers, not body hashes or labels. "
        "The unchanged ModelProposal validator remains authoritative.")
    return request, _object({"document": document})


def response_contract(value):
    """Native response transport; the ordinary response validator still decides."""
    template = value["response_template"]
    text = {"type": "string", "minLength": 1, "maxLength": 4000}
    refs = {"type": "array", "minItems": 1, "maxItems": 16,
            "items": _enum(value["allowed_source_refs"])}
    learning = _object({
        "concept_id": {"type": "string", "minLength": 1, "maxLength": 128,
                       "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]*$"},
        "concept": {"type": "string", "minLength": 1, "maxLength": 1000},
        "why_now": text, "minimum_model": text, "counterexample": text,
        "check": text, "source_refs": refs,
    })
    reusable = _object({
        "kind": _enum(("DECISION_HEURISTIC", "VERIFICATION_IDEA", "FAILURE_PATTERN")),
        "title": text, "situation": text, "procedure": text, "counterexample": text,
        "source_refs": refs,
    })
    explanations = _array(_object({
        "fact_id": _enum(row["fact_id"] for row in template["explanations"]),
        "text": {"type": "string", "minLength": 1, "maxLength": 2000},
    }), len(template["explanations"]))
    explanations["minItems"] = len(template["explanations"])
    document = _object({
        "schema_version": {"type": "integer", "enum": [template["schema_version"]]},
        "task_id": _enum([template["task_id"]]),
        "basis_revision": {"type": "integer", "enum": [template["basis_revision"]]},
        "response_locale": _enum([template["response_locale"]]),
        "norms_sha256": _enum([template["norms_sha256"]]),
        "answer": {"type": "string", "minLength": 1, "maxLength": 16000},
        "explanations": explanations,
        "learning_candidates": _array(learning, value["max_learning_items"]),
        "reusable_candidates": _array(reusable, 8),
    })
    request = deepcopy(value)
    request["output_contract"] += (
        " Return document as a JSON OBJECT, not an encoded JSON string. "
        "Include every supplied fact_id exactly once, without inventing IDs. "
        "Source references are exact members of allowed_source_refs, never content hashes or array indices. "
        "Where the selected work supports concrete lessons or reusable procedures, retain them as attributed "
        "candidates; lack of execution evidence is not a reason to discard an explicitly unverified idea. "
        "Do not manufacture candidates when the source is insufficient. "
        "The host validates the unchanged original response contract.")
    return request, _object({"document": document})


def decode_editor(envelope, source_request=None):
    from jsonschema import Draft202012Validator
    # The request-specific schema is checked by the caller. Guard the map
    # conversion independently so duplicates are never silently overwritten.
    if type(envelope) is not dict or set(envelope) != {"document"} or type(envelope["document"]) is not dict:
        raise LedgerError("BRIDGE_PROTOCOL", {"reason": "CODEX_EDITOR_ENVELOPE"})
    document = deepcopy(envelope["document"])
    entries = document.get("files")
    if type(entries) is not list or len(entries) > 16:
        raise LedgerError("BRIDGE_PROTOCOL", {"reason": "CODEX_EDITOR_FILES"})
    files = {}
    for entry in entries:
        if (type(entry) is not dict or set(entry) != {"path", "content"}
                or type(entry["path"]) is not str or type(entry["content"]) is not str
                or entry["path"] in files):
            raise LedgerError("BRIDGE_PROTOCOL", {"reason": "CODEX_EDITOR_FILE_ENTRY"})
        files[entry["path"]] = entry["content"]
    document["files"] = files
    if any("alternative_refs" in row for row in document.get("acknowledgements", [])):
        if type(source_request) is not dict or source_request.get("format") != EDITOR:
            raise LedgerError("BRIDGE_PROTOCOL", {"reason": "CODEX_EDITOR_SOURCE_REQUIRED"})
        slots = {slot["ref"]: slot for slot in _alternative_slots(source_request["interpretation_proposal"])}
        for row in document["acknowledgements"]:
            refs = row.pop("alternative_refs", [])
            if (len(refs) != len(set(refs)) or any(ref not in slots
                    or slots[ref]["interpretation_id"] != row["id"] for ref in refs)
                    or len(refs) + len(row["alternatives"]) > 8):
                raise LedgerError("BRIDGE_PROTOCOL", {"reason": "CODEX_EDITOR_ALTERNATIVE_BINDING"})
            row["alternatives"] = [slots[ref]["text"] for ref in refs] + row["alternatives"]
    return document


def validate_envelope(envelope, schema, *, editor=True, source_request=None):
    from jsonschema import Draft202012Validator
    if not Draft202012Validator(schema).is_valid(envelope):
        raise LedgerError("BRIDGE_PROTOCOL", {"reason": "CODEX_EDITOR_WIRE_SCHEMA"})
    if editor and schema["properties"]["document"]["properties"]["acknowledgements"]["items"].get("anyOf"):
        if type(source_request) is not dict or source_request.get("format") != EDITOR:
            raise LedgerError("BRIDGE_PROTOCOL", {"reason": "CODEX_EDITOR_SOURCE_REQUIRED"})
        if editor_contract(source_request)[1] != schema:
            raise LedgerError("BRIDGE_PROTOCOL", {"reason": "CODEX_EDITOR_SOURCE_BINDING"})
    if not editor:
        fields = schema.get("properties", {}).get("document", {}).get("properties", {})
        variants = fields.get("interpretations", {}).get("items", {}).get("anyOf")
        if variants:
            if type(source_request) is not dict or source_request.get("format") != PLAN:
                raise LedgerError("BRIDGE_PROTOCOL", {"reason": "CODEX_PLAN_SOURCE_REQUIRED"})
            _, bound_schema = plan_contract(source_request)
            if bound_schema != schema:
                raise LedgerError("BRIDGE_PROTOCOL", {"reason": "CODEX_PLAN_SOURCE_BINDING"})
            expected = {row["properties"]["id"]["enum"][0] for row in variants}
            actual = [row["id"] for row in envelope["document"]["interpretations"]]
            if len(actual) != len(expected) or set(actual) != expected:
                raise LedgerError("BRIDGE_PROTOCOL", {"reason": "CODEX_PLAN_CITATION_COVERAGE"})
            case_variants = fields["cases"]["items"]["anyOf"]
            expected_cases = {
                row["properties"]["id"]["enum"][0]:
                    set(row["properties"]["interpretation_ids"]["items"]["enum"])
                for row in case_variants}
            actual_cases = envelope["document"]["cases"]
            if (len({row["id"] for row in actual_cases}) != len(expected_cases)
                    or any(set(row["interpretation_ids"]) != expected_cases[row["id"]]
                           for row in actual_cases)):
                raise LedgerError("BRIDGE_PROTOCOL", {"reason": "CODEX_PLAN_CASE_COVERAGE"})
            slots = {unit["id"]: unit for unit in _citation_slots(source_request)}
            document = deepcopy(envelope["document"])
            for row in document["interpretations"]:
                row.pop("quote_ref")
                row["quote"] = slots[row["id"]]["quote"]
            return document
    return decode_editor(envelope, source_request) if editor else deepcopy(envelope["document"])
