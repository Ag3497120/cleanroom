"""Bounded, display-only messages from our built-in adapter's stderr.

Arbitrary executor stderr and provider error bodies never enter this channel.
No observation is an executable document, a receipt, or an authorization.
"""
import json

PREFIX = b"VERANTYX_MODEL_EVENT "
MAX_LINE = 8192
MAX_THINKING = 16000
REASONS = frozenset((
    "MODEL_API_CONFIG", "MODEL_API_PROVIDER", "MODEL_API_MODEL", "MODEL_API_KEY_ENV",
    "MODEL_API_TLS", "MODEL_API_LIMIT", "MODEL_API_ENDPOINT", "MODEL_API_ENDPOINT_PATH",
    "MODEL_API_ENDPOINT_MODEL", "MODEL_API_INPUT_LIMIT", "MODEL_API_RESPONSE",
    "MODEL_API_REQUEST_FORMAT", "MODEL_API_CREDENTIAL", "MODEL_API_HTTP_STATUS",
    "MODEL_API_CONTENT_TYPE", "MODEL_API_RESPONSE_LIMIT", "MODEL_API_TIMEOUT",
    "MODEL_API_TRUNCATED_BODY", "MODEL_API_CREDENTIAL_ECHO", "MODEL_API_TRANSPORT_OR_RESPONSE",
    "MODEL_API_CONFIG_CHANGED", "MODEL_API_STREAM", "MODEL_API_GENERATION_LIMIT", "MODEL_API_EMPTY_ANSWER",
    "SHARED_CONTEXT_BUDGET", "EDITOR_SCHEMA", "ASSET_PLAN_DOCUMENT",
    "CODEX_CLI_ARGUMENTS", "CODEX_PROCESS_EXIT", "CODEX_CONFIG_CHANGED",
    "CODEX_CALL_BUDGET_EXHAUSTED", "CODEX_REQUEST_ALREADY_RESERVED",
))


def diagnostic(error):
    from .i18n import catalog
    code = getattr(error, "code", "BRIDGE_PROCESS_FAILED")
    if "error." + code not in catalog("en"):
        code = "BRIDGE_PROCESS_FAILED"
    details = getattr(error, "details", {})
    safe = {}
    if type(details.get("reason")) is str and details["reason"] in REASONS:
        safe["reason"] = details["reason"]
    for key in ("http_status", "budget", "limit", "thinking_characters", "response_characters", "generated_tokens", "output_token_limit"):
        if type(details.get(key)) is int and 0 <= details[key] <= 64 * 1024 * 1024:
            safe[key] = details[key]
    return {"code": code, "details": safe}


def emit(stream, event):
    # The caller supplies only host fields or already quarantined model text.
    stream.write(PREFIX.decode() + json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n")
    stream.flush()


def parse(raw):
    if not raw.startswith(PREFIX) or len(raw) > MAX_LINE:
        return None
    try:
        event = json.loads(raw[len(PREFIX):])
    except (ValueError, UnicodeError):
        return None
    if type(event) is not dict:
        return None
    kind = event.get("kind")
    if kind in ("thinking",) and set(event) == {"kind", "text"} and type(event["text"]) is str and len(event["text"]) <= 512:
        return event
    if kind in ("thinking_truncated", "validated") and set(event) == {"kind"}:
        return event
    if kind == "output" and set(event) == {"kind", "characters"} and type(event["characters"]) is int and 0 <= event["characters"] <= 4 * 1024 * 1024:
        return event
    if kind == "error" and set(event) == {"kind", "code", "details"} and type(event["code"]) is str and type(event["details"]) is dict:
        from .errors import LedgerError
        return {"kind": kind, **diagnostic(LedgerError(event["code"], event["details"]))}
    return None
