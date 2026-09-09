"""One bounded NDJSON response. Partial content never becomes a proposal."""
import time

from .domain.codec import decode
from .model_observation import MAX_THINKING


def notify(observer, event):
    if observer:
        try:
            observer(event)
        except Exception:
            pass


def read(response, config, deadline, connection, secret, observer):
    from .model_api import _contains_secret, _require
    pending = bytearray()
    answer, thoughts = [], []
    total = generated = characters = displayed = 0
    final = None
    shown_limit = False
    thought_buffer = ""
    last_update = 0

    def show_thinking(value, flush=False):
        nonlocal thought_buffer, displayed, shown_limit, last_update
        if secret or observer is None:
            return  # Credential-bearing connections do not stream provider text.
        thought_buffer += value[:max(0, MAX_THINKING - displayed - len(thought_buffer))]
        now = time.monotonic()
        if flush or now - last_update >= .2 or len(thought_buffer) >= 512:
            while thought_buffer:
                part, thought_buffer = thought_buffer[:512], thought_buffer[512:]
                notify(observer, {"kind": "thinking", "text": part})
                displayed += len(part)
            last_update = now
        if displayed + len(thought_buffer) >= MAX_THINKING and not shown_limit:
            notify(observer, {"kind": "thinking_truncated"})
            shown_limit = True

    def consume(raw):
        nonlocal final, generated, characters
        if not raw.strip():
            return
        _require(final is None, "MODEL_API_STREAM", "BRIDGE_PROTOCOL")
        item = decode(raw, config["max_response_bytes"] * 16)
        _require(type(item) is dict and not item.get("error") and type(item.get("done")) is bool,
                 "MODEL_API_STREAM", "BRIDGE_PROTOCOL")
        _require(not secret or not _contains_secret(item, secret), "MODEL_API_CREDENTIAL_ECHO", "BRIDGE_PROTOCOL")
        if config["endpoint"].endswith("/api/chat"):
            message = item.get("message")
            _require(type(message) is dict and message.get("role") == "assistant"
                     and not message.get("tool_calls") and not message.get("images"), "MODEL_API_STREAM", "BRIDGE_PROTOCOL")
            item = {**item, "response": message.get("content", ""), "thinking": message.get("thinking", "")}
        for field, destination in (("response", answer), ("thinking", thoughts)):
            part = item.get(field, "")
            _require(type(part) is str, "MODEL_API_STREAM", "BRIDGE_PROTOCOL")
            generated += len(part.encode("utf-8"))
            _require(generated <= config["max_response_bytes"], "MODEL_API_RESPONSE_LIMIT", "BRIDGE_OUTPUT_LIMIT")
            destination.append(part)
            if field == "thinking":
                show_thinking(part)
            elif part:
                characters += len(part)
        if item["done"]:
            final = item

    last_output = 0
    while True:
        remaining = deadline - time.monotonic()
        _require(remaining > 0, "MODEL_API_TIMEOUT", "BRIDGE_TIMEOUT")
        if connection.sock is not None:
            connection.sock.settimeout(remaining)
        chunk = response.read1(min(65536, config["max_response_bytes"] * 16 + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        _require(total <= config["max_response_bytes"] * 16, "MODEL_API_RESPONSE_LIMIT", "BRIDGE_OUTPUT_LIMIT")
        pending.extend(chunk)
        while b"\n" in pending:
            row, _, rest = pending.partition(b"\n")
            pending = bytearray(rest)
            consume(row)
        if characters and time.monotonic() - last_output >= .5:
            notify(observer, {"kind": "output", "characters": characters})
            last_output = time.monotonic()
    if pending:
        consume(pending)
    show_thinking("", flush=True)
    length = response.getheader("Content-Length")
    _require(length is None or total == int(length), "MODEL_API_TRUNCATED_BODY", "BRIDGE_PROTOCOL")
    _require(final is not None, "MODEL_API_TRUNCATED_BODY", "BRIDGE_PROTOCOL")
    result = {"response": "".join(answer), "thinking": "".join(thoughts),
              "done": True, "done_reason": final.get("done_reason")}
    if type(final.get("eval_count")) is int and 0 <= final["eval_count"] <= 65536:
        result["eval_count"] = final["eval_count"]
    _require(not secret or not _contains_secret(result, secret), "MODEL_API_CREDENTIAL_ECHO", "BRIDGE_PROTOCOL")
    notify(observer, {"kind": "output", "characters": characters})
    return result
