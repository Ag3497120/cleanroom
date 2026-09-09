"""Pure contracts for bounded model-assisted asset planning.

The model selects data contracts. It cannot introduce effects, authorities,
executable code, or an independent oracle. All source and result bindings are
checked again during replay.
"""
from copy import deepcopy
import hashlib
import json
import re

from .codec import canonical, decode, digest
from .verification import AXES, CHECKS, validate_spec
from ..adapters.observations import normalize_path
from ..adapters.proposal_validation import valid_id
from ..errors import LedgerError

REQUEST_FORMAT = "verantyx.asset-workflow-request.v1"
PLAN_FORMAT = "verantyx.asset-workflow-plan.v1"
EVENT_ACTORS = {"AssetWorkflowPlanned": "asset_planner", "AssetWorkflowFinished": "kernel"}
MAX_CONTEXT = 512 * 1024


def predicate_contracts():
    """Descriptions of the existing verifier primitives, not inferred goals."""
    return [
        {"kind": "bytes.sha256", "meaning": "Exact SHA-256 of the whole raw file.",
         "pointer": "", "expected_format": "64 lowercase hexadecimal characters"},
        {"kind": "bytes.size", "meaning": "Exact UTF-8/raw byte length of the whole file, not character count.",
         "pointer": "", "expected_format": "integer from 0 to 65536"},
        {"kind": "text.equals", "meaning": "Exact UTF-8 text equality including spaces and newlines.",
         "pointer": "", "expected_format": "literal string, possibly empty"},
        {"kind": "text.contains", "meaning": "The decoded UTF-8 file contains this literal substring.",
         "pointer": "", "expected_format": "nonempty literal string, not regex"},
        {"kind": "json.equals", "meaning": "Compare the JSON value at a JSON Pointer with the literal expected JSON value. "
          "To require a particular value use this predicate, not json.type. Types and numeric representation are exact; "
          "a number and a string are different. Do not wrap expected in a type/value object.",
         "pointer": "JSON Pointer: /answer selects the answer key; empty string selects the document; ~0 means ~ and ~1 means /.",
         "expected_format": "the expected JSON value itself",
         "example": {"id": "expected-value", "kind": "json.equals", "pointer": "/count", "expected": 3}},
        {"kind": "json.type", "meaning": "Check only the JSON runtime type, not a particular value. "
          "integer means an int; number means a floating-point value, excluding an integer.",
         "pointer": "JSON Pointer, not a quoted key name. /answer is valid; a string containing quote-answer-quote is not.",
         "expected_format": "one literal string: null, boolean, integer, number, string, array, object",
         "example": {"id": "expected-type", "kind": "json.type", "pointer": "/count", "expected": "integer"}},
    ]



def _literal_values(text):
    """Locate JSON literals in source text, without interpreting surrounding prose.

    A parsed container retains its span and JSON Pointer for each contained
    value. Keys and the contents of a JSON string are never scanned as numbers.
    These are candidate value bindings, not statements that a requirement holds.
    """
    decoder = json.JSONDecoder()
    token = re.compile(r'["{\[]|(?<![A-Za-z0-9_.+\-])(?:-?[0-9]|true|false|null)')
    offset = 0
    while match := token.search(text, offset):
        start = match.start()
        try:
            _, end = decoder.raw_decode(text, start)
        except (ValueError, RecursionError):
            offset = start + 1
            continue
        offset = end
        # Do not treat a fragment of an identifier, decimal or exponent as a
        # literal. Japanese prose may adjoin a number without ASCII whitespace.
        if end < len(text) and (re.match(r'[A-Za-z0-9_]', text[end]) or
                                text[end] == '.' and end + 1 < len(text) and text[end + 1].isdigit()):
            continue
        try:
            value = decode(text[start:end])
        except LedgerError:
            continue
        pending = [(value, "")]
        while pending:
            item, pointer = pending.pop()
            yield {"value": item, "start": start, "end": end, "source_pointer": pointer}
            if type(item) is dict:
                pending.extend((v, pointer + "/" + k.replace("~", "~0").replace("/", "~1"))
                               for k, v in reversed(list(item.items())))
            elif type(item) is list:
                pending.extend((item[i], pointer + "/" + str(i)) for i in reversed(range(len(item))))


def _expectation_sources(context):
    # No model-generated expectation_basis, proposal, candidate summary or
    # available-method prose can certify another model-generated value.
    return [{"source_ref": context["request_ref"], "text": context["request"], "path": None},
            *[{"source_ref": row["source_ref"], "text": row["body"], "path": None}
              for row in context.get("external_captures", [])],
            *[{"source_ref": row["source_ref"], "text": row["text"], "path": row["path"]}
              for row in context["selected_files"]]]


def _json_type(value):
    return {type(None): "null", bool: "boolean", int: "integer", float: "number",
            str: "string", list: "array", dict: "object"}[type(value)]


def _expectation_bindings_v1(context, checks, refs, target_path):
    """Bind literal equality expectations to cited material other than the target.

    Literal presence proves neither prose entailment nor that the model chose
    the relevant part of the source. The caller retains MODEL_PROPOSED status.
    """
    sources = [row for row in _expectation_sources(context)
               if row["source_ref"] in refs and row["path"] != target_path]
    result = []
    for check in checks:
        if check["kind"] != "json.equals":
            continue
        require(bool(sources), "EXPECTATION_SOURCE_REQUIRED")
        expected = canonical(check["expected"])
        binding = None
        for source in sources:
            for literal in _literal_values(source["text"]):
                if canonical(literal["value"]) == expected:
                    binding = {"check_id": check["id"], "source_ref": source["source_ref"],
                               "source_sha256": hashlib.sha256(source["text"].encode("utf-8")).hexdigest(),
                               "start": literal["start"], "end": literal["end"], "offset_unit": "UNICODE_CODEPOINT",
                               "source_pointer": literal["source_pointer"],
                               "literal_type": _json_type(literal["value"]),
                               "literal_sha256": digest(literal["value"]),
                               "relationship": "LITERAL_MATCH_ONLY"}
                    break
            if binding is not None:
                break
        require(binding is not None, "EXPECTATION_LITERAL_MISMATCH")
        result.append(binding)
    return result


def _source_text_span(text, expected, token=False):
    if not expected:
        return (0, 0) if text == "" else None
    offset = 0
    while (start := text.find(expected, offset)) >= 0:
        end = start + len(expected)
        if not token or ((start == 0 or not re.match(r"[A-Za-z0-9_]", text[start - 1])) and
                         (end == len(text) or not re.match(r"[A-Za-z0-9_]", text[end]))):
            return start, end
        offset = end
    return None


def expectation_bindings(context, checks, refs, target_path):
    """Check finite source/value correspondence for each existing predicate.

    v1 is preserved verbatim for recorded equality-only plans. v2 also binds
    hash/type tokens and text literals; it still does not prove that the model
    chose the property required by surrounding prose.
    """
    if context.get("expectation_binding_version") == 1:
        return _expectation_bindings_v1(context, checks, refs, target_path)
    sources = [row for row in _expectation_sources(context)
               if row["source_ref"] in refs and row["path"] != target_path]
    result = []
    for check in checks:
        require(bool(sources), "EXPECTATION_SOURCE_REQUIRED")
        expected = canonical(check["expected"])
        binding = None
        for source in sources:
            literal = next((row for row in _literal_values(source["text"])
                            if canonical(row["value"]) == expected), None)
            encoding = "JSON_LITERAL"
            if literal is None and check["kind"] in ("bytes.sha256", "json.type", "text.equals", "text.contains"):
                span = _source_text_span(source["text"], check["expected"],
                                         token=check["kind"] in ("bytes.sha256", "json.type"))
                if span is not None:
                    literal = {"value": check["expected"], "start": span[0], "end": span[1], "source_pointer": ""}
                    encoding = ("SHA256_TOKEN" if check["kind"] == "bytes.sha256" else
                                "TYPE_NAME" if check["kind"] == "json.type" else "TEXT_SUBSTRING")
            if literal is not None:
                binding = {"check_id": check["id"], "source_ref": source["source_ref"],
                           "source_sha256": hashlib.sha256(source["text"].encode("utf-8")).hexdigest(),
                           "start": literal["start"], "end": literal["end"], "offset_unit": "UNICODE_CODEPOINT",
                           "source_pointer": literal["source_pointer"], "source_encoding": encoding,
                           "literal_type": _json_type(literal["value"]), "literal_sha256": digest(literal["value"]),
                           "relationship": "LITERAL_MATCH_ONLY"}
                break
        require(binding is not None, "EXPECTATION_LITERAL_MISMATCH")
        result.append(binding)
    return result

def _typed_check_schema(context=None, *, source_value_sampling=False):
    expected = {"bytes.sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "bytes.size": {"type": "integer", "minimum": 0, "maximum": 65536},
                "text.equals": {"type": "string"}, "text.contains": {"type": "string", "minLength": 1},
                "json.equals": {}, "json.type": {"type": "string", "enum":
                 ["null", "boolean", "integer", "number", "string", "array", "object"]}}
    if source_value_sampling and context and context.get("expectation_binding_version") == 2:
        # Give the sampler actual source values, not a type/value wrapper it
        # must invent. This is a choice set, never an inferred requirement.
        # With several selected files the host still checks that the chosen
        # value came from a cited source other than this step's target.
        sources = _expectation_sources(context)
        if len(context["selected_files"]) == 1:
            sources = [row for row in sources if row["path"] is None]
        literals, size, bounded = {}, 0, True
        for source in sources:
            for row in _literal_values(source["text"]):
                encoded = canonical(row["value"])
                if encoded in literals:
                    continue
                size += len(encoded.encode("utf-8"))
                if len(literals) >= 256 or size > 16384:
                    bounded = False
                    break
                literals[encoded] = row["value"]
            if not bounded:
                break
        if bounded and literals:
            expected["json.equals"] = {"enum": list(literals.values())}
        # Large sources keep the generic sampler and the same acceptance
        # checks. No source or value is silently discarded from validation.
    return {"oneOf": [{"type": "object", "additionalProperties": False,
        "properties": {"id": {"type": "string"}, "kind": {"const": kind},
                       "pointer": {"type": "string", "pattern": "^(/.*)?$"} if kind.startswith("json.") else {"const": ""},
                       "expected": expected[kind]}, "required": ["id", "kind", "pointer", "expected"]} for kind in CHECKS]}


def require(value, reason="CONTRACT_INVALID"):
    if not value:
        raise LedgerError("ASSET_WORKFLOW_INVALID", {"reason": reason})


def _fields(value, names):
    require(type(value) is dict and set(value) == set(names))


def _text(value, limit=2000, empty=False):
    require(type(value) is str and (empty or bool(value.strip())) and len(value) <= limit)


def output_schema(max_checks=4, context=None, *, source_value_sampling=False):
    """One closed response shape, also usable by constrained model decoding."""
    check = {"type": "object", "additionalProperties": False,
             "properties": {"id": {"type": "string"}, "kind": {"type": "string", "enum": list(CHECKS)},
                            "pointer": {"type": "string"}, "expected": {}},
             "required": ["id", "kind", "pointer", "expected"]}
    control = {"type": "object", "additionalProperties": False,
               "properties": {"id": {"type": "string"}, "input_base64": {"type": "string"}},
               "required": ["id", "input_base64"]}
    properties = {"id": {"type": "string"}, "mode": {"type": "string", "enum": ["REUSE", "COMPILE"]},
                  "claim_id": {"type": "string"}, "target_path": {"type": "string"},
                  "asset_id": {"type": ["string", "null"]}, "property": {"type": ["string", "null"]},
                  "method": {"enum": ["TEST", "NEGATIVE_CONTROL", None]},
                  "checks": {"type": "array", "items": check, "maxItems": max_checks},
                  "negative_controls": {"type": "array", "items": control, "maxItems": 8},
                  "expectation_basis": {"type": "string"},
                  "source_refs": {"type": "array", "items": {"type": "string"}, "maxItems": 16}}
    result = {"type": "object", "additionalProperties": False,
            "properties": {"format": {"const": PLAN_FORMAT}, "context_sha256": {"type": "string"},
                           "steps": {"type": "array", "maxItems": max_checks,
                                     "items": {"type": "object", "additionalProperties": False,
                                               "properties": properties, "required": list(properties)}},
                           "unresolved": {"type": "array", "maxItems": 16, "items": {"type": "string"}}},
            "required": ["format", "context_sha256", "steps", "unresolved"]}
    if context is not None:
        # Sampling may select only references that the host can actually bind.
        # This narrows the existing contract; compile_document remains the
        # authority and still rejects invalid combinations and changed values.
        methods = context["available_methods"]
        candidates = context["candidates"]
        properties["checks"]["items"] = _typed_check_schema(context, source_value_sampling=source_value_sampling)
        properties["mode"]["enum"] = ["REUSE", "COMPILE"] if methods else ["COMPILE"]
        properties["asset_id"]["enum"] = [None, *dict.fromkeys(row["id"] for row in [*methods, *candidates])]
        properties["claim_id"]["enum"] = [row["id"] for row in context["claims"]]
        properties["target_path"]["enum"] = [row["path"] for row in context["selected_files"]]
        properties["source_refs"]["items"]["enum"] = sorted(source_refs(context))
        if source_value_sampling:
            sources = _expectation_sources(context)
            if len(context["selected_files"]) == 1:
                sources = [row for row in sources if row["path"] is None]
            # A generated expectation must cite its requirement, rather than
            # its own candidate or the observed output. Original context and
            # all source records remain intact; REUSE can cite its method.
            properties["source_refs"]["items"]["enum"] = sorted(
                {row["source_ref"] for row in [*sources, *methods]})
        properties["source_refs"]["minItems"] = 1
        result["properties"]["context_sha256"] = {"const": digest(context)}
        if not methods:
            properties["method"]["enum"] = ["TEST", "NEGATIVE_CONTROL"]
            properties["property"]["type"] = "string"
    return result


def source_refs(context):
    """One citation allowlist for generation and pure acceptance checks."""
    refs = {context["request_ref"], context["proposal_ref"]}
    refs |= {row["source_ref"] for row in context["selected_files"]}
    refs |= {row["source_ref"] for row in context["available_methods"]}
    refs |= {ref for row in context["candidates"] for ref in row["source_refs"]}
    refs |= {row["source_ref"] for row in context.get("external_captures", [])}
    return refs


def method_snapshot(event):
    """Exact stored method; new claims/targets never replace its predicates."""
    from .events import citation
    require(event["type"] == "VerificationPlanned")
    spec = event["payload"]["plan"]["spec"]
    return {"id": digest({"project_id": event["project_id"], "run_id": event["stream_id"],
                          "family": "VERIFICATION", "source_ref": citation(event)}),
            "owner_run": event["stream_id"], "source_ref": citation(event),
            "source_event_hash": event["event_hash"], "contract_hash": digest(spec), "spec": deepcopy(spec)}


def candidate_snapshots(event):
    from .events import citation
    if event["type"] != "ResponseComposed":
        return []
    ref = citation(event)
    return [{"id": digest({"response_ref": ref, "candidate_index": index}),
             "owner_run": event["stream_id"], "source_event_hash": event["event_hash"],
             "source_refs": list(dict.fromkeys([ref, *row["source_refs"]])),
             **{key: deepcopy(row[key]) for key in ("kind", "title", "situation", "procedure", "counterexample")}}
            for index, row in enumerate(event["payload"]["document"].get("reusable_candidates", []))]


def validate_project_bindings(events):
    """Single pass, no replay/I/O: compare snapshots with preceding real events."""
    if not any(e["type"] == "AssetWorkflowPlanned" for e in events):
        return
    methods, candidates = {}, {}
    for event in events:
        if event["type"] == "AssetWorkflowPlanned":
            context = event["payload"]["context"]
            for row in context["available_methods"]:
                require(row["id"] in methods and canonical(row) == canonical(methods[row["id"]]), "SOURCE_CONTRACT_CHANGED")
            for row in context["candidates"]:
                require(row["id"] in candidates and canonical(row) == canonical(candidates[row["id"]]), "CANDIDATE_SOURCE_CHANGED")
        elif event["type"] == "VerificationPlanned":
            row = method_snapshot(event)
            methods[row["id"]] = row
        elif event["type"] == "ResponseComposed":
            for row in candidate_snapshots(event):
                candidates[row["id"]] = row


def compile_document(context, document, max_checks):
    """Deterministically bind an untrusted response to host-selected inputs."""
    _fields(document, ("format", "context_sha256", "steps", "unresolved"))
    require(document["format"] == PLAN_FORMAT and document["context_sha256"] == digest(context), "CONTEXT_CHANGED")
    require(type(document["steps"]) is list and len(document["steps"]) <= max_checks, "CHECK_LIMIT")
    require(type(document["unresolved"]) is list and len(document["unresolved"]) <= 16)
    for value in document["unresolved"]:
        _text(value, 2000)
    claims = {row["id"] for row in context["claims"]}
    files = {row["path"]: row for row in context["selected_files"]}
    methods = {row["id"]: row for row in context["available_methods"]}
    candidates = {row["id"]: row for row in context["candidates"]}
    allowed = source_refs(context)
    seen, result, count = set(), [], 0
    for step in document["steps"]:
        _fields(step, ("id", "mode", "claim_id", "target_path", "asset_id", "property", "method", "checks",
                       "negative_controls", "expectation_basis", "source_refs"))
        require(valid_id(step["id"]) and step["id"] not in seen)
        seen.add(step["id"])
        require(valid_id(step["claim_id"]) and step["claim_id"] in claims, "CLAIM_UNKNOWN")
        require(type(step["target_path"]) is str and step["target_path"] in files, "TARGET_NOT_SELECTED")
        refs = step["source_refs"]
        require(type(refs) is list and 1 <= len(refs) <= 16 and all(type(ref) is str for ref in refs)
                and len(set(refs)) == len(refs) and set(refs) <= allowed, "SOURCE_UNKNOWN")
        _text(step["expectation_basis"], 1500)
        if step["mode"] == "REUSE":
            require(type(step["asset_id"]) is str and step["asset_id"] in methods, "ASSET_NOT_REUSABLE")
            source = methods[step["asset_id"]]
            require(step["property"] is None and step["method"] is None and step["checks"] == []
                    and step["negative_controls"] == [], "FROZEN_CONTRACT_CHANGED")
            require(source["source_ref"] in refs, "SOURCE_UNKNOWN")
            spec = deepcopy(source["spec"])
            require(spec["method"] in ("TEST", "NEGATIVE_CONTROL"), "ASSET_NOT_REUSABLE")
            spec.update(claim_id=step["claim_id"], target_path=step["target_path"])
            # Old task observation references cannot be asserted as fresh oracles.
            # Exact predicate/expected values/controls and oracle prose survive.
            spec["oracle"]["source_refs"] = [row["source_ref"] for row in files.values()]
            origin = "RECORDED_CONTRACT_NEW_BINDING"
        elif step["mode"] == "COMPILE":
            require(step["asset_id"] is None or (type(step["asset_id"]) is str and step["asset_id"] in candidates), "CANDIDATE_UNKNOWN")
            if step["asset_id"] is not None:
                require(bool(set(refs) & set(candidates[step["asset_id"]]["source_refs"])), "SOURCE_UNKNOWN")
            require(step["method"] in ("TEST", "NEGATIVE_CONTROL"), "METHOD_UNSUPPORTED")
            spec = {"claim_id": step["claim_id"], "target_path": step["target_path"], "property": step["property"],
                    "method": step["method"], "checks": deepcopy(step["checks"]),
                    "negative_controls": deepcopy(step["negative_controls"]), "reproduces": None,
                    "oracle": {"description": "MODEL_PROPOSED; independence NOT_ESTABLISHED. " + step["expectation_basis"],
                               "source_refs": [row["source_ref"] for row in files.values()]},
                    "provenance": {axis: "" for axis in AXES}}
            spec["provenance"].update(model=context["adapter_identity"], oracle="MODEL_PROPOSED_NOT_INDEPENDENT",
                                      implementation="bounded.predicates.v1")
            origin = "MODEL_PROPOSED"
        else:
            raise LedgerError("ASSET_WORKFLOW_INVALID", {"reason": "MODE_UNSUPPORTED"})
        validate_spec(spec)
        bindings = None
        if context.get("expectation_binding_version") in (1, 2):
            if step["mode"] == "COMPILE":
                bindings = expectation_bindings(context, spec["checks"], refs, step["target_path"])
                if bindings:
                    spec["provenance"]["oracle"] = ("MODEL_PROPOSED_ALL_LITERAL_BOUND_NOT_INDEPENDENT"
                                                    if context["expectation_binding_version"] == 2 else
                                                    "MODEL_PROPOSED_LITERAL_BOUND_NOT_INDEPENDENT")
            elif spec["provenance"]["oracle"] == "MODEL_PROPOSED_NOT_INDEPENDENT":
                # Old unbound model proposals remain historical contracts, not
                # approved goals. Automatic selection must cite a current
                # literal basis; explicit operator selection stays available.
                bindings = expectation_bindings(context, spec["checks"], refs, step["target_path"])
            elif (context["expectation_binding_version"] == 2 and
                  spec["provenance"]["oracle"] == "MODEL_PROPOSED_LITERAL_BOUND_NOT_INDEPENDENT"):
                # v1 only bound equality values; do not silently extend that
                # historical evidence to other primitive expectations.
                unbound = [check for check in spec["checks"] if check["kind"] != "json.equals"]
                bindings = expectation_bindings(context, unbound, refs, step["target_path"])
        count += len(spec["checks"])
        require(count <= max_checks, "CHECK_LIMIT")
        result.append({"id": step["id"], "mode": step["mode"], "asset_id": step["asset_id"],
                       "spec": spec, "spec_sha256": digest(spec), "source_refs": list(refs),
                       "expectation_basis": step["expectation_basis"], "expectation_origin": origin,
                       "independence": "NOT_ESTABLISHED", "prose_entailment": "NOT_ASSESSED"})
        if bindings is not None:
            result[-1]["expectation_bindings"] = bindings
    return result


def validate_payload(kind, payload):
    from .events import hash_value, uuid_value, timestamp
    if kind == "AssetWorkflowPlanned":
        _fields(payload, ("id", "basis_revision", "context", "context_sha256", "document", "steps", "max_checks",
                          "max_rounds", "rejected", "execute", "created_at", "expires_at"))
        uuid_value(payload["id"])
        require(type(payload["basis_revision"]) is int and payload["basis_revision"] > 0)
        require(type(payload["execute"]) is bool)
        require(type(payload["max_checks"]) is int and 1 <= payload["max_checks"] <= 8)
        require(type(payload["max_rounds"]) is int and 1 <= payload["max_rounds"] <= 3)
        timestamp(payload["created_at"])
        timestamp(payload["expires_at"])
        require(payload["created_at"] < payload["expires_at"])
        hash_value(payload["context_sha256"])
        context = payload["context"]
        names = {"project_id", "run_id", "basis_revision", "request", "request_ref", "proposal_ref", "proposal_hash",
                 "claims", "decision_context", "selected_files", "available_methods", "candidates", "adapter_identity"}
        optional = {key for key in ("external_captures", "expectation_binding_version") if key in context}
        _fields(context, names | optional)
        if "expectation_binding_version" in context:
            require(type(context["expectation_binding_version"]) is int and context["expectation_binding_version"] in (1, 2))
        if "external_captures" in context:
            from ..external_capture import MAX_CAPTURES, validate_payload as validate_capture
            require(type(context["external_captures"]) is list and len(context["external_captures"]) <= MAX_CAPTURES)
            for row in context["external_captures"]:
                _fields(row, {"id", "basis_revision", "body", "body_sha256", "content_format", "provenance",
                              "authority", "claims_status", "source_ref", "recorded_at", "owner_run"})
                require(valid_id(row["source_ref"]) and row["owner_run"] == context["run_id"], "REFERENCE_CHANGED")
                timestamp(row["recorded_at"])
                validate_capture("ExternalResponseCaptured", {k: v for k, v in row.items()
                                  if k not in ("source_ref", "recorded_at", "owner_run")})
        require(payload["context_sha256"] == digest(context) and context["basis_revision"] == payload["basis_revision"])
        require(len(canonical(context).encode("utf-8")) <= MAX_CONTEXT)
        hash_value(context["adapter_identity"])
        require(type(context["selected_files"]) is list and len(context["selected_files"]) <= 16)
        require(type(context["available_methods"]) is list and len(context["available_methods"]) <= 24)
        require(type(context["candidates"]) is list and len(context["candidates"]) <= 24)
        for row in context["selected_files"]:
            _fields(row, ("path", "sha256", "text", "source_ref"))
            normalize_path(row["path"])
            _text(row["text"], 65536, empty=True)
            require(hashlib.sha256(row["text"].encode("utf-8")).hexdigest() == row["sha256"], "SELECTED_FILE_CHANGED")
        require(len({row["path"] for row in context["selected_files"]}) == len(context["selected_files"]))
        for row in context["available_methods"]:
            _fields(row, ("id", "owner_run", "source_ref", "source_event_hash", "contract_hash", "spec"))
            validate_spec(row["spec"])
            require(digest(row["spec"]) == row["contract_hash"], "SOURCE_CONTRACT_CHANGED")
            hash_value(row["source_event_hash"])
        require(canonical(compile_document(context, payload["document"], payload["max_checks"])) == canonical(payload["steps"]), "COMPILED_SPEC_CHANGED")
        require(type(payload["rejected"]) is list and len(payload["rejected"]) <= payload["max_rounds"])
        for index, row in enumerate(payload["rejected"], 1):
            _fields(row, ("round", "code", "reason", "response_sha256"))
            require(row["round"] == index and valid_id(row["code"]))
            _text(row["reason"], 160)
            hash_value(row["response_sha256"])
    elif kind == "AssetWorkflowFinished":
        _fields(payload, ("workflow_id", "plan_sha256", "bindings", "status", "results"))
        uuid_value(payload["workflow_id"])
        hash_value(payload["plan_sha256"])
        require(type(payload["bindings"]) is list and len(payload["bindings"]) <= 16)
        for row in payload["bindings"]:
            _fields(row, ("step_id", "verification_id"))
            require(valid_id(row["step_id"]))
            uuid_value(row["verification_id"])


def results_for(state, plan, bindings):
    require(len(bindings) == len(plan["steps"]) if plan["execute"] else not bindings, "RESULT_BINDING_CHANGED")
    results = []
    seen = set()
    for step, binding in zip(plan["steps"], bindings):
        require(binding["step_id"] == step["id"] and binding["verification_id"] not in seen, "RESULT_BINDING_CHANGED")
        seen.add(binding["verification_id"])
        item = state.get("verifications", {}).get(binding["verification_id"])
        require(item and canonical(item["plan"]["spec"]) == canonical(step["spec"]), "RESULT_CONTRACT_CHANGED")
        require(item["plan"]["proposal_hash"] == plan["context"]["proposal_hash"], "CONTEXT_CHANGED")
        target = next(row for row in plan["context"]["selected_files"] if row["path"] == step["spec"]["target_path"])
        require(item["plan"]["target"]["sha256"] == target["sha256"]
                and item["plan"]["created_at"] >= plan["created_at"]
                and state.get("asset_workflow_verification_revisions", {}).get(item["source_ref"], 0) > plan["basis_revision"] + 1,
                "RESULT_BINDING_CHANGED")
        receipt = item.get("receipt")
        require(receipt is not None, "RESULT_MISSING")
        evidence = receipt.get("result") or {}
        results.append({"step_id": step["id"], "verification_id": binding["verification_id"], "status": item["status"],
                        "closure": evidence.get("closure"), "reason": receipt.get("reason") or evidence.get("reason"),
                        "source_ref": item["receipt_ref"], "expectation_origin": step["expectation_origin"],
                        "prose_entailment": "NOT_ASSESSED", "independence": "NOT_ESTABLISHED"})
    if not plan["steps"]:
        status = "NO_PLAN"
    elif not plan["execute"]:
        status = "PLANNED"
    elif any(row["status"] != "COMPLETED" for row in results):
        status = "OUTCOME_UNKNOWN" if any(row["status"] == "OUTCOME_UNKNOWN" for row in results) else "INVALIDATED"
    elif any(row["closure"] == "CONTESTED" for row in results):
        status = "CONTESTED"
    elif any(row["closure"] == "REFUTED" for row in results):
        status = "REFUTED"
    else:
        status = "COMPLETED"
    return status, results


def apply_event(state, event):
    if event["type"] == "VerificationPlanned" and state.get("asset_workflows"):
        from .events import citation
        state.setdefault("asset_workflow_verification_revisions", {})[citation(event)] = event["revision"]
    if event["type"] not in EVENT_ACTORS:
        return
    from .events import citation
    from ..decision_context import snapshot
    p = event["payload"]
    validate_payload(event["type"], p)
    items = state.setdefault("asset_workflows", {})
    if event["type"] == "AssetWorkflowPlanned":
        context = p["context"]
        require(p["id"] not in items and state["revision"] == p["basis_revision"], "CONTEXT_CHANGED")
        require(context["project_id"] == state["project_id"] and context["run_id"] == state["run_id"])
        require(context["request"] == state["request"] and context["request_ref"] == state["request_ref"])
        require(context["proposal_ref"] == state["proposal_ref"] and context["proposal_hash"] == digest(state["proposal"]), "CONTEXT_CHANGED")
        require(canonical(context["claims"]) == canonical((state["proposal"] or {}).get("claims", [])), "CLAIM_CHANGED")
        require(canonical(context["decision_context"]) == canonical(snapshot(state)), "DECISION_CHANGED")
        if "external_captures" in context:
            require(context["external_captures"] == state.get("external_captures", []), "REFERENCE_CHANGED")
        require(p["created_at"] == event["recorded_at"])
        for row in context["selected_files"]:
            ref = state["latest_observations"].get(row["path"])
            observation = state["observations"].get(ref)
            require(row["path"] in state["read_scope"] and ref == row["source_ref"] and observation
                    and observation["status"] == "OBSERVED" and observation["sha256"] == row["sha256"]
                    and observation["size"] == len(row["text"].encode("utf-8")), "SELECTED_FILE_CHANGED")
            require(observation["observed_at"] <= p["created_at"] < observation["expires_at"], "OBSERVATION_EXPIRED")
        items[p["id"]] = {"plan": deepcopy(p), "status": "PLANNED", "source_ref": citation(event)}
    else:
        item = items.get(p["workflow_id"])
        require(item is not None and item["status"] == "PLANNED" and "finished_ref" not in item)
        require(digest(item["plan"]) == p["plan_sha256"], "PLAN_CHANGED")
        status, results = results_for(state, item["plan"], p["bindings"])
        require(status == p["status"] and canonical(results) == canonical(p["results"]), "RESULT_CHANGED")
        item.update(status=status, results=results, finished_ref=citation(event), finished_at=event["recorded_at"])
        state["latest_asset_workflow"] = p["workflow_id"]
