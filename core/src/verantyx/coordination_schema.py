"""Generation-time schemas; the event validators remain authoritative."""
import re
from pathlib import PurePosixPath

from .ollama_schema import _object, _string
from .shared_context import DISPOSITIONS, STRENGTHS, RELATIONS


def array(item, minimum=0, maximum=64):
    return {"type": "array", "items": item, "minItems": minimum, "maxItems": maximum}


def identifier(prefix=""):
    return {"type": "string", "pattern": "^" + prefix + "[A-Za-z0-9][A-Za-z0-9_.:-]{0,140}$"}


def source_units(request):
    """Lossless citation scaffolding; punctuation does not determine semantics.

    The finite contract has 64 slots, not a 64-sentence input limit. Adjacent
    spans from one source share a slot when necessary. Sources never merge and
    concatenating their quotes reconstructs each original byte for byte.
    """
    from .shared_context import require
    groups = []
    for source in request["shared_context"]["sources"]:
        parts = []
        for quote in re.split(r"(?<=[。！？!?；;\n])", source["text"]):
            if quote.strip():
                parts.append(quote)
            elif quote and parts:
                parts[-1] += quote
            elif quote:
                # A leading blank line belongs to the first nonblank span.
                parts.append(quote)
        if len(parts) > 1 and not parts[0].strip():
            prefix = parts.pop(0)
            parts[0] = prefix + parts[0]
        require(parts and all(p.strip() for p in parts), "SHARED_CONTEXT_INVALID")
        groups.append((source["id"], parts))
    require(1 <= len(groups) <= 64, "SHARED_CONTEXT_LIMIT")
    budgets = [1] * len(groups)
    for _ in range(min(64, sum(len(parts) for _, parts in groups)) - len(groups)):
        available = [i for i, (_, parts) in enumerate(groups) if budgets[i] < len(parts)]
        i = max(available, key=lambda i: (len(groups[i][1]) / budgets[i], -i))
        budgets[i] += 1
    units = []
    for (source_id, parts), count in zip(groups, budgets):
        for i in range(count):
            quote = "".join(parts[len(parts) * i // count:len(parts) * (i + 1) // count])
            units.append({"id": "intent-" + str(len(units) + 1), "source_id": source_id, "quote": quote})
    require(1 <= len(units) <= 64, "SHARED_CONTEXT_LIMIT")
    return units


def fixed_array(items):
    # The local grammar supports prefixItems. Do not add items:false: some
    # samplers prefer items over prefixItems. Equal min/max still closes it.
    return {"type": "array", "prefixItems": items, "minItems": len(items), "maxItems": len(items)}


def fixed_test_paths(selected):
    """The selected source snapshot, not a model's test list, fixes the suite."""
    return [source["path"] for source in selected
            if PurePosixPath(source["path"]).name.startswith("test_") and source["path"].endswith(".py")]


def validate_editor_test_contract(document, selected):
    """Enforce the same frozen suite at every adapter ingress and on replay.

    Existing explicit Python test paths still work when no test_*.py was
    selected. A nonempty fixed suite retains its exact execution order.
    """
    from .shared_context import require
    chosen = {source["path"] for source in selected}
    fixed = fixed_test_paths(selected)
    require(set(document["tests"]) <= chosen, "TEST_SCOPE")
    if fixed:
        require(document["tests"] == fixed, "TEST_SCOPE")
    from .domain.paths import portable_path_key
    protected = {portable_path_key(path) for path in document["tests"]}
    require(not protected.intersection(portable_path_key(path) for path in document["files"]), "TEST_SCOPE")


def relation_schema(ids):
    # Relations connect existing, distinct interpretation nodes only.
    if len(ids) < 2:
        return {"const": []}
    return array({"anyOf": [_object({"kind": {"enum": list(RELATIONS)}, "from": {"const": source},
                 "to": {"enum": [target for target in ids if target != source]}}) for source in ids]}, maximum=128)


def schema(request, *, line_blocks=False):
    properties = {"context_sha256": {"const": request["shared_context"]["sha256"]}}
    if request["format"] == "verantyx.handoff-plan-request.v1":
        units = source_units(request)
        ids = [unit["id"] for unit in units]
        nodes = [_object({**{key: {"const": value} for key, value in unit.items()},
                          "meaning": _string(), "disposition": {"enum": list(DISPOSITIONS)},
                          "strength": {"enum": list(STRENGTHS)}, "alternatives": array(_string(), maximum=8)}) for unit in units]
        relations = relation_schema(ids)
        choices = fixed_array([_object({"id": {"const": "choice-" + letter}, "text": _string()}) for letter in 'AB'])
        # At most 32 paired cases cover all 64 citation slots. The meanings and
        # selected outcome remain generated; coverage alone is not correctness.
        cases = [_object({"id": {"const": "case-" + str(i // 2 + 1)}, "situation": _string(),
                          "choices": choices, "expected": {"enum": ["choice-A", "choice-B"]},
                          "interpretation_ids": {"const": ids[i:i + 2]}}) for i in range(0, len(ids), 2)]
        properties.update(interpretations=fixed_array(nodes), relations=relations, cases=fixed_array(cases))
    else:
        plan = request["interpretation_proposal"]
        fixed_tests = fixed_test_paths(request["selected_files"])
        nodes = [_object({"id": {"const": n["id"]}, "disposition": {"enum": list(DISPOSITIONS)},
                          "strength": {"enum": list(STRENGTHS)}, "interpretation": _string(),
                          "alternatives": array(_string(), maximum=8)}) for n in plan["interpretations"]]
        cases = [_object({"id": {"const": c["id"]},
                          "choice": {"enum": [x["id"] for x in c["choices"]] + ["UNRESOLVED"]},
                          "reason": _string()}) for c in plan["cases"]]
        properties.update(plan_sha256={"const": request["response_template"]["plan_sha256"]},
                          acknowledgements=fixed_array(nodes), relations=relation_schema([n["id"] for n in plan["interpretations"]]),
                          case_choices=fixed_array(cases),
                          files={"type": "object", "additionalProperties": {"type": "string"}, "maxProperties": 16},
                          tests={"const": fixed_tests} if fixed_tests else (
                              array({"enum": [s["path"] for s in request["selected_files"] if s["path"].endswith(".py")]}, maximum=16)
                              if any(s["path"].endswith(".py") for s in request["selected_files"]) else {"const": []}),
                          notes=_string(8000))
        if "response" in request["response_template"]:
            from .work_output import response_schema
            contract = request.get("work_output_contract")
            properties["response"] = response_schema(contract)
            if contract and contract["read_only"]:
                properties["files"] = {"const": {}}
        if line_blocks:
            properties.pop("files")
            properties["file_line_blocks"] = {"type": "object", "maxProperties": 16,
                "additionalProperties": _object({"lines": array({"type": "string"}, maximum=10000),
                                                  "newline": {"enum": ["LF", "CRLF"]},
                                                  "final_newline": {"type": "boolean"}})}
            if request.get("work_output_contract", {}).get("read_only"):
                properties["file_line_blocks"] = {"const": {}}
    return _object(properties)


def encode_editor_document(document):
    """Generation transport: physical lines avoid ambiguous double escaping."""
    from copy import deepcopy
    value = deepcopy(document)
    value["file_line_blocks"] = {}
    for path, body in value.pop("files").items():
        newline = "\r\n" if "\r\n" in body else "\n"
        final = body.endswith(newline)
        lines = body.split(newline) if body else []
        if final:
            lines.pop()
        value["file_line_blocks"][path] = {"lines": lines, "newline": "CRLF" if newline == "\r\n" else "LF",
                                           "final_newline": final}
    return value


def plan_compact_schema(request):
    """Retain semantic field names and quotes; encode fixed IDs by position."""
    full = schema(request)["properties"]
    nodes = full["interpretations"]
    for node in nodes["prefixItems"]:
        for key in ("id", "source_id"):
            node["properties"].pop(key)
            node["required"].remove(key)
    cases = full["cases"]
    for case in cases["prefixItems"]:
        for key in ("id", "interpretation_ids"):
            case["properties"].pop(key)
            case["required"].remove(key)
        for choice in case["properties"]["choices"]["prefixItems"]:
            # schema() shares the same fixed choice schema across cases.
            choice["properties"].pop("id", None)
            choice["required"] = [key for key in choice["required"] if key != "id"]
    return _object({"context_sha256": full["context_sha256"], "interpretation_values": nodes,
                    "relations": full["relations"], "case_values": cases})


def decode_plan_compact(document, request):
    from copy import deepcopy
    from jsonschema import Draft202012Validator
    from .shared_context import require
    require(Draft202012Validator(plan_compact_schema(request)).is_valid(document))
    units = source_units(request)
    nodes = [{**unit, **node} for unit, node in zip(units, document["interpretation_values"])]
    cases = [{**case, "id": "case-" + str(i + 1),
              "choices": [{**choice, "id": "choice-" + letter} for choice, letter in zip(case["choices"], "AB")],
              "interpretation_ids": [u["id"] for u in units[i * 2:i * 2 + 2]]}
             for i, case in enumerate(document["case_values"])]
    return deepcopy({"context_sha256": document["context_sha256"], "interpretations": nodes,
                     "relations": document["relations"], "cases": cases})


def decode_editor_document(document, request):
    from copy import deepcopy
    from jsonschema import Draft202012Validator
    from .shared_context import require
    require(Draft202012Validator(schema(request, line_blocks=True)).is_valid(document))
    value = deepcopy(document)
    value["files"] = {}
    for path, block in value.pop("file_line_blocks").items():
        require(all("\n" not in line and "\r" not in line for line in block["lines"]))
        newline = "\r\n" if block["newline"] == "CRLF" else "\n"
        value["files"][path] = newline.join(block["lines"]) + (newline if block["final_newline"] else "")
    return value
