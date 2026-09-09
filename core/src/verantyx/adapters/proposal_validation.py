"""The packaged proposal schema is the runtime contract, never an authority."""
from functools import lru_cache
from importlib.resources import files
import re

from jsonschema import Draft202012Validator

from ..domain.codec import canonical, decode, MAX_DOCUMENT
from ..errors import LedgerError


@lru_cache(maxsize=1)
def validator():
    schema = decode(files("verantyx").joinpath("schemas", "model-proposal.v1.json").read_bytes())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_proposal(value):
    if len(canonical(value).encode("utf-8")) > MAX_DOCUMENT:
        raise LedgerError("DOCUMENT_LIMIT")
    errors = list(_VALIDATOR.iter_errors(value))
    if errors:
        # The CLI renders its own localized message. Keep diagnostics structured.
        raise LedgerError("PROPOSAL_INVALID", {"paths": [list(e.absolute_path) for e in errors[:16]]})
    ids = [item["id"] for group in ("claims", "actions", "unknowns", "decision_points") for item in value.get(group, [])]
    if len(ids) != len(set(ids)) or any(not item.strip() for item in ids):
        raise LedgerError("PROPOSAL_INVALID", {"reason": "DUPLICATE_OR_EMPTY_ID"})
    for point in value.get("decision_points", []):
        options = [item["id"] for item in point["options"]]
        if len(options) != len(set(options)):
            raise LedgerError("PROPOSAL_INVALID", {"reason": "DUPLICATE_OPTION"})
    return value


def valid_id(value):
    return type(value) is str and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}", value))

# Contract loading is startup I/O; event replay only uses the frozen validator.
_VALIDATOR = validator()
