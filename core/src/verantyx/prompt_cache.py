"""Stable transport ordering; canonical ledger bytes and validation stay unchanged."""
from copy import deepcopy
import re

from .domain.codec import canonical, digest

# Put reusable material before counters, candidate state and current schemas.
PREFIX_KEYS = ("format", "output_contract", "response_locale", "tool_capabilities",
               "model_roles", "personal_context", "approved_files", "approved_assets",
               "project_context", "request")
FRAGMENT_INSTRUCTION = (
    " Text content blocks are consecutive fragments of one REQUEST_JSON object; "
    "concatenate them in order. For REQUEST_PATCH in a continued conversation, "
    "replace the listed top-level fields, then append the listed array entries "
    "to the previous request. The resulting request is authoritative for this turn. "
    "Prior model output is not evidence that proposed tools ran."
)


def fragments(value):
    """Return lossless JSON fragments and reusable prefix boundary indices.

    Receipts are normally the largest growing field. A completed tool batch
    retains its own boundary when later batches are appended.
    """
    remaining = dict(value)
    fixed = {key: remaining.pop(key) for key in PREFIX_KEYS if key in remaining}
    # Protocol and tool definitions survive a new task or changed file scope.
    # Do not alphabetically sort the entire prefix: approved_files would then
    # precede the shared contract and invalidate it on every scope change.
    base_keys = PREFIX_KEYS[:5]
    base = [canonical(key) + ":" + canonical(fixed.pop(key)) for key in base_keys if key in fixed]
    parts = ["{" + ",".join(base)]
    boundaries = [0] if base else []
    separator = "," if base else ""
    if fixed:
        parts.append(separator + ",".join(canonical(key) + ":" + canonical(value) for key, value in fixed.items()))
        boundaries.append(len(parts) - 1)
        separator = ","
    receipts = remaining.pop("tool_receipts", None)
    if isinstance(receipts, list) and receipts:
        batch, previous = [], object()
        prefix = separator + '"tool_receipts":['
        for index, receipt in enumerate(receipts):
            turn = receipt.get("turn_index") if isinstance(receipt, dict) else index
            if batch and turn != previous:
                parts.append(prefix + ",".join(canonical(row) for row in batch))
                boundaries.append(len(parts) - 1)
                prefix, batch = ",", []
            batch.append(receipt)
            previous = turn
        parts.append(prefix + ",".join(canonical(row) for row in batch))
        boundaries.append(len(parts) - 1)
        tail, separator = "]", ","
    else:
        if "tool_receipts" in value:
            remaining["tool_receipts"] = receipts
        tail = ""
    for key in sorted(remaining):
        tail += separator + canonical(key) + ":" + canonical(remaining[key])
        separator = ","
    parts.append(tail + "}")
    # At most four explicit boundaries, supported by both direct API adapters.
    selected = list(dict.fromkeys(boundaries[:2] + boundaries[-2:]))
    return parts, selected


def text(value):
    return "".join(fragments(value)[0])


def cache_key(value):
    # No prompt, file path, account credential or personally identifying text.
    # A routing hint, not an authorization boundary. A fresh run ID must not
    # prevent reuse of the same protocol prefix across tasks.
    return "cleanroom-" + digest({key: value.get(key) for key in PREFIX_KEYS[:5]})[:48]


def explicit_openai(model):
    match = re.match(r"^gpt-(\d+)(?:\.(\d+))?(?:-|$)", model)
    return bool(match and (int(match[1]), int(match[2] or 0)) >= (5, 6))


def native_contract(request):
    """Avoid changing the provider's schema whenever provenance IDs grow.

    Exact provenance remains in the request and in host validation. All shape,
    type and status restrictions remain in the native output schema.
    """
    from .agent_schema import native_contract as original, WORK_REQUEST
    value, envelope = original(request)
    if request.get("format") != WORK_REQUEST:
        return value, envelope
    value = deepcopy(value)
    value.pop("output_schema", None)  # Already supplied as native structured output.
    note = envelope["properties"]["document"]["properties"].get("learning_notes", {})
    for name in ("source_event_ids", "profile_refs"):
        field = note.get("items", {}).get("properties", {}).get(name, {})
        field.get("items", {}).pop("enum", None)
    return value, envelope
