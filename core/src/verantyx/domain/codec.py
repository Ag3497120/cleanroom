"""Bounded, unambiguous JSON. No clocks, random numbers, or external effects."""
import hashlib
import json
import math

from ..errors import LedgerError

MAX_DOCUMENT = 1024 * 1024
MAX_ARCHIVE = 16 * 1024 * 1024


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("non-finite number")


def _check(value, depth=0):
    if depth > 40:
        raise ValueError("nesting limit")
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("object key")
            key.encode("utf-8")
            _check(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _check(item, depth + 1)
    elif type(value) is str:
        value.encode("utf-8")
    elif type(value) is float:
        if not math.isfinite(value):
            raise ValueError("non-finite number")
    elif value is not None and type(value) not in (int, bool):
        raise ValueError("not JSON")


def canonical(value):
    try:
        _check(value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise LedgerError("DOCUMENT_INVALID") from None


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def decode(raw, limit=MAX_DOCUMENT):
    try:
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        if len(raw) > limit:
            raise LedgerError("DOCUMENT_LIMIT")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        _check(value)
        return value
    except LedgerError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise LedgerError("DOCUMENT_INVALID") from None
