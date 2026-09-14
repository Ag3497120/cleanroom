"""A deliberately small language for explicit conditions, not prose guessing."""
import base64
import re

from .adapters.observations import normalize_path
from .domain.codec import canonical, decode, digest
from .domain.verification import AXES, validate_spec
from .errors import LedgerError


def compile_conditions(target, expressions, rejected_json=()):
    normalize_path(target)
    if not 1 <= len(expressions) <= 16 or len(rejected_json) > 8:
        raise LedgerError("ARGUMENTS", {"reason": "EXPECTATION_COUNT"})
    checks, seen = [], {}
    for index, expression in enumerate(expressions, 1):
        if not isinstance(expression, str) or len(expression) > 32768:
            raise LedgerError("ARGUMENTS", {"reason": "EXPECTATION_SIZE"})
        typed = re.fullmatch(r"JSON\s+(\S+)\s+type\s+(null|boolean|integer|number|string|array|object)", expression.strip())
        equal = re.fullmatch(r"JSON\s+(\S+?)\s*(?:==|=|は)\s*(.+)", expression.strip())
        if typed:
            pointer, expected = typed.groups()
            kind = "json.type"
        elif equal:
            pointer, raw = equal.groups()
            expected = decode(raw, 32768)
            kind = "json.equals"
        else:
            raise LedgerError("ARGUMENTS", {"reason": "UNSUPPORTED_EXPECTATION",
                                          "example": "JSON /retry_limit = 3"})
        pointer = "" if pointer == "$" else pointer
        identity = (kind, pointer)
        if identity in seen:
            if seen[identity] != digest(expected):
                raise LedgerError("ARGUMENTS", {"reason": "CONFLICTING_EXPECTATIONS"})
            continue
        seen[identity] = digest(expected)
        checks.append({"id": "expected-" + str(index), "kind": kind,
                       "pointer": pointer, "expected": expected})
    controls = [{"id": "negative-" + str(i + 1),
                 "input_base64": base64.b64encode(canonical(decode(raw, 65536)).encode("utf-8")).decode("ascii")}
                for i, raw in enumerate(rejected_json)]
    spec = {
        "claim_id": "explicit-contract", "target_path": target,
        "property": "Only the explicit JSON predicates; not arbitrary program semantics.",
        "method": "NEGATIVE_CONTROL" if controls else "TEST",
        "checks": checks, "negative_controls": controls, "reproduces": None,
        "oracle": {"description": "Conditions explicitly supplied before checking, not inferred from the result.",
                   "source_refs": []},
        "provenance": {axis: "" for axis in AXES},
    }
    spec["provenance"].update(model="none", implementation="verantyx explicit-conditions.v1",
                              oracle="explicit CLI expressions", data="operator supplied conditions")
    validate_spec(spec)
    return {"format": "verantyx.explicit-conditions.v1", "target": target,
            "expressions": list(expressions), "spec": spec,
            "authority": "EXPLICIT_PREDICATES_ONLY", "model_calls": 0}
