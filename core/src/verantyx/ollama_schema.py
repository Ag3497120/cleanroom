"""Constrain local generation before applying the unchanged kernel validators."""
from copy import deepcopy


def _object(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _string(maximum=4000):
    return {"type": "string", "minLength": 1, "maxLength": maximum}


def _portable(schema, definitions=None):
    # The local sampler rejects large maxLength bounds. Inline references and
    # omit these bounds only at generation time; the original validators still
    # enforce them, along with the retained nonempty text and identifier rules.
    definitions = definitions if definitions is not None else schema.get("$defs", {})
    if isinstance(schema, list):
        return [_portable(item, definitions) if isinstance(item, (dict, list)) else item for item in schema]
    if not isinstance(schema, dict):
        return schema
    if "$ref" in schema:
        return _portable(definitions[schema["$ref"].removeprefix("#/$defs/")], definitions)
    omitted = {"$id", "$schema", "$defs", "uniqueItems", "maxProperties", "maxLength", "title", "description"}
    result = {}
    for key, item in schema.items():
        if key in omitted:
            continue
        if key in ("const", "enum", "default"):
            # These are application data, not nested schema keywords.
            result[key] = deepcopy(item)
            continue
        if key == "properties":
            result[key] = {name: _portable(value, definitions) for name, value in item.items()}
        else:
            result[key] = _portable(item, definitions) if isinstance(item, (dict, list)) else item
    return result


def output_schema(value):
    from .agent_schema import FORMATS, generation_schema as agent_schema
    if value.get("format") in FORMATS:
        return _portable(agent_schema(value))
    if value.get("format") == "verantyx.asset-workflow-request.v1":
        from .domain.asset_workflow import output_schema as asset_schema
        result = _portable(asset_schema(max_checks=value["max_checks"],
                         context=value["context"] if value.get("planning_contract_version") in (2, 3, 4) else None,
                         source_value_sampling=value.get("planning_contract_version") == 4))
        if value.get("planning_contract_version") == 4:
            step = result["properties"]["steps"]["items"]
            fields = step["properties"]
            # Generate the attributed requirement before its check encoding,
            # so the explanation need not rationalize an already chosen hash.
            order = ("id", "mode", "claim_id", "target_path", "expectation_basis", "source_refs",
                     "property", "method", "asset_id", "checks", "negative_controls")
            step["properties"] = {key: fields[key] for key in order}
            preferred = [binding["source_ref"] for row in value.get("repair_feedback", {}).get("source_value_matches", [])
                         for binding in row["literal_matches_only"]]
            refs = fields["source_refs"]["items"]["enum"]
            # Change presentation order only. The model must still choose its
            # citations; the unchanged host checks source/value correspondence.
            fields["source_refs"]["items"]["enum"] = list(dict.fromkeys([ref for ref in preferred if ref in refs] + refs))
        return result
    if value.get("format") in ("verantyx.handoff-plan-request.v1", "verantyx.editor-request.v1"):
        from .coordination_schema import schema
        return _portable(schema(value, line_blocks=value.get("format") == "verantyx.editor-request.v1"))
    if value.get("format") == "verantyx.proposal-request.v1":
        schema = deepcopy(value["proposal_schema"])
        schema.pop("$id", None)
        for field in ("schema_version", "task_id", "context_revision", "response_locale"):
            schema["properties"][field] = {"const": value["proposal_template"][field]}
        for definition, prefix in (("claim", "claim"), ("action", "action"), ("unknown", "unknown"), ("decision_point", "decision")):
            schema["$defs"][definition]["properties"]["id"] = {
                "type": "string", "pattern": "^" + prefix + "-[A-Za-z0-9_.:-]{1,140}$"}
        schema["properties"]["summary"]["description"] = "Answer the user's actual request fluently; do not just repeat it or describe this schema."
        return _portable(schema)
    if value.get("format") != "verantyx.response-request.v1":
        return "json"
    template = value["response_template"]
    mutable = {"answer", "explanations", "learning_candidates", "reusable_candidates"}
    properties = {key: {"const": item} for key, item in template.items() if key not in mutable}
    ids = [item["fact_id"] for item in template["explanations"]]
    properties["answer"] = _string(16000)
    properties["explanations"] = {"type": "array", "minItems": len(ids), "maxItems": len(ids),
        "items": _object({"fact_id": {"type": "string", "enum": ids} if ids else _string(), "text": _string(2000)})}
    refs = {"type": "array", "minItems": 1, "maxItems": 16, "uniqueItems": True,
            "items": {"type": "string", "enum": value["allowed_source_refs"]}}
    learning = {key: _string() for key in ("why_now", "minimum_model", "counterexample", "check")}
    learning.update(concept_id={"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$"},
                    concept=_string(1000), source_refs=refs)
    reusable = {key: _string() for key in ("title", "situation", "procedure", "counterexample")}
    reusable.update(kind={"enum": ["DECISION_HEURISTIC", "VERIFICATION_IDEA", "FAILURE_PATTERN"]}, source_refs=refs)
    properties["learning_candidates"] = {"type": "array", "maxItems": value["max_learning_items"], "items": _object(learning)}
    properties["reusable_candidates"] = {"type": "array", "maxItems": 8, "items": _object(reusable)}
    return _portable(_object(properties))
