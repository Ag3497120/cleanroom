"""One explicit bounded webhook POST. No response body or credential is retained."""
from datetime import datetime, timezone
from pathlib import Path
import http.client
import ipaddress
import os
import re
import ssl
import sys
import time
from urllib.parse import urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verantyx.domain.codec import canonical, decode
from verantyx.errors import LedgerError


def _require(condition):
    if not condition:
        raise LedgerError("BRIDGE_CONFIG", {"reason": "NOTIFICATION_CONNECTION"})


def validate_connection(value):
    _require(type(value) is dict and set(value) == {"endpoint", "key_env", "allow_loopback_http"})
    endpoint, key = value["endpoint"], value["key_env"]
    _require(type(endpoint) is str and 1 <= len(endpoint) <= 2048 and endpoint.isascii()
             and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in endpoint) and "\\" not in endpoint)
    _require(type(value["allow_loopback_http"]) is bool)
    reserved = {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "WINDIR"}
    _require(key is None or (type(key) is str and bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", key))
             and key not in reserved and not key.startswith(("PYTHON", "LD_", "DYLD_"))))
    try:
        url = urlsplit(endpoint)
        _require(url.hostname is not None and url.username is None and url.password is None
                 and not url.query and not url.fragment and url.path.startswith("/") and (url.port is None or 1 <= url.port <= 65535))
        loopback = False
        try:
            loopback = ipaddress.ip_address(url.hostname).is_loopback
        except ValueError:
            pass
        _require(url.scheme == "https" or (url.scheme == "http" and loopback and value["allow_loopback_http"]))
    except ValueError:
        raise LedgerError("BRIDGE_CONFIG") from None
    return value


def deliver(value):
    _require(type(value) is dict and set(value) == {"connection", "packet", "delivery_id", "expires_at", "timeout"})
    configuration = validate_connection(value["connection"])
    _require(type(value["timeout"]) is int and 1 <= value["timeout"] <= 60)
    _require(type(value["delivery_id"]) is str and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}", value["delivery_id"])))
    from verantyx.domain.events import timestamp
    timestamp(value["expires_at"])
    expires = datetime.strptime(value["expires_at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    raw = canonical({"format": "verantyx.notification.v1", "delivery_id": value["delivery_id"], "packet": value["packet"]}).encode()
    _require(len(raw) <= 65536)
    headers = {"Content-Type": "application/json", "Accept-Encoding": "identity", "Idempotency-Key": value["delivery_id"]}
    if configuration["key_env"]:
        secret = os.environ.get(configuration["key_env"])
        _require(type(secret) is str and 1 <= len(secret) <= 8192 and secret.isascii() and all(32 < ord(c) < 127 for c in secret))
        headers["Authorization"] = "Bearer " + secret
    url = urlsplit(configuration["endpoint"])
    connection = None
    try:
        remaining = (expires - datetime.now(timezone.utc)).total_seconds()
        _require(remaining > 0)
        timeout = min(value["timeout"], remaining)
        deadline = time.monotonic() + timeout
        if url.scheme == "https":
            connection = http.client.HTTPSConnection(url.hostname, url.port, timeout=timeout, context=ssl.create_default_context())
        else:
            connection = http.client.HTTPConnection(url.hostname, url.port, timeout=timeout)
        remaining = min(deadline - time.monotonic(), (expires - datetime.now(timezone.utc)).total_seconds())
        _require(remaining > 0)
        connection.timeout = remaining
        # Connect and complete TLS before checking the final dispatch deadline.
        # Refuse http.client's implicit reconnect after this checked connection.
        connection.connect()
        connection.auto_open = False
        remaining = min(deadline - time.monotonic(), (expires - datetime.now(timezone.utc)).total_seconds())
        _require(remaining > 0 and connection.sock is not None)
        connection.sock.settimeout(remaining)
        # No redirects, proxy lookup, retries, or authenticated URL parameters.
        connection.request("POST", url.path, raw, headers)
        remaining = min(deadline - time.monotonic(), (expires - datetime.now(timezone.utc)).total_seconds())
        _require(remaining > 0)
        connection.sock.settimeout(remaining)
        response = connection.getresponse()
        _require(200 <= response.status < 300)
        _require(response.getheader("Content-Encoding", "identity").lower() == "identity")
        length = response.getheader("Content-Length")
        _require(length is None or (length.isdigit() and int(length) <= 65536))
        count = 0
        while True:
            remaining = deadline - time.monotonic()
            _require(remaining > 0)
            if connection.sock is not None:
                connection.sock.settimeout(remaining)
            chunk = response.read1(min(65536 - count + 1, 8192))
            if not chunk:
                break
            count += len(chunk)
            _require(count <= 65536)
        _require(length is None or count == int(length))
        return {"status": "HTTP_ACCEPTED", "http_status": response.status, "response_bytes": count,
                "delivery_confirmed": False, "response_body_retained": False}
    except (OSError, ValueError, TypeError, KeyError, http.client.HTTPException):
        raise LedgerError("BRIDGE_OUTCOME_UNKNOWN") from None
    finally:
        if connection is not None:
            connection.close()


def main():
    try:
        value = decode(sys.stdin.buffer.read(131073), 131072)
        sys.stdout.write(canonical(deliver(value)) + "\n")
        return 0
    except (OSError, LedgerError):
        sys.stderr.write("NOTIFICATION_OUTCOME_UNKNOWN_NO_RETRY\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
