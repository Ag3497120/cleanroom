"""Explicit, bounded web search for optional learning resources.

Only owner-supplied queries leave the project. Results are search observations,
not proof of a book's quality, edition, availability, or a person's learning.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .domain.codec import digest
from .errors import LedgerError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LedgerError("SEARCH_REDIRECT_REFUSED")


def public_link(url):
    if type(url) is not str or len(url) > 4096 or any(ord(c) < 33 for c in url):
        return False
    parsed = urlsplit(url)
    return (parsed.scheme == "https" and bool(parsed.hostname) and parsed.username is None
            and parsed.password is None and parsed.hostname not in ("localhost", "127.0.0.1", "::1"))


class BraveSearch:
    """No optional SDK. API credentials are read only at an approved invocation."""
    label = "Brave Search"

    def search(self, query):
        secret = os.environ.get("BRAVE_SEARCH_API_KEY", "")
        if not secret or not secret.isascii() or not all(32 < ord(c) < 127 for c in secret):
            raise LedgerError("SEARCH_KEY_REQUIRED")
        url = "https://api.search.brave.com/res/v1/web/search?" + urlencode({"q": query, "count": 5})
        request = Request(url, headers={"X-Subscription-Token": secret, "Accept": "application/json",
                                        "Accept-Encoding": "identity", "User-Agent": "Cleanroom-Learning/1"})
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            raw = response.read(524289)
        if len(raw) > 524288:
            raise LedgerError("SEARCH_RESPONSE_LIMIT")
        value = json.loads(raw)
        return value.get("web", {}).get("results", [])


class CommandSearch:
    """Optional trusted JSON search/MCP wrapper, not an automatically installed skill."""
    label = "Trusted search adapter"

    def __init__(self, root, adapter, *, trusted=False):
        from .adapters.command_process import load_command
        from .work_harness import _read
        if not trusted or root is None:
            raise LedgerError("SEARCH_ADAPTER_TRUST_REQUIRED")
        root = Path(root).resolve()
        path = Path(adapter)
        if path.is_absolute():
            try:
                path = path.relative_to(root)
            except ValueError:
                raise LedgerError("PATH_SCOPE") from None
        if path.parts[:2] != (".verantyx", "search-adapters") or ".." in path.parts or path.suffix != ".json":
            raise LedgerError("PATH_SCOPE")
        raw = _read(root, path.as_posix())
        document = json.loads(raw)
        if type(document) is not dict or "argv" not in document:
            raise LedgerError("SEARCH_ADAPTER_PROTOCOL")
        self.command = load_command(root / path)
        if _read(root, path.as_posix()) != raw:
            raise LedgerError("SEARCH_ADAPTER_CHANGED")
        self.fingerprint = hashlib.sha256(raw).hexdigest()

    def search(self, query):
        from .adapters.command_process import BoundedProcess
        with BoundedProcess(self.command, timeout=20, max_output=524288) as process:
            raw = process.document({"format": "verantyx.web-search.v1", "query": query, "limit": 5})
        return json.loads(raw).get("results", [])


def search(queries, *, approved=False, root=None, adapter=None, trusted=False):
    if not approved:
        raise LedgerError("SEARCH_APPROVAL_REQUIRED")
    if (type(queries) is not list or not 1 <= len(queries) <= 3
            or any(type(q) is not str or not q.strip() or len(q) > 300 or
                   any(ord(c) < 32 for c in q) for q in queries)):
        raise LedgerError("SEARCH_QUERY")
    backend = CommandSearch(root, adapter, trusted=trusted) if adapter else BraveSearch()
    results, failures = [], []
    for query in queries:
        try:
            raw = backend.search(query)
            if type(raw) is not list:
                raise LedgerError("SEARCH_RESPONSE")
            for item in raw[:5]:
                if type(item) is not dict or not public_link(item.get("url")) or not isinstance(item.get("title"), str):
                    continue
                result = {
                    "id": "resource-" + digest({"query": query, "url": item["url"], "title": item["title"]})[:32],
                    "title": item["title"][:500], "url": item["url"],
                    "snippet": str(item.get("description", ""))[:1500],
                    "query": query, "provider": backend.label,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "verification": "SEARCH_RESULT_ONLY_NOT_BOOK_OR_EDITION_VERIFIED",
                }
                results.append(result)
        except Exception as error:
            failures.append({"query": query, "code": getattr(error, "code", "SEARCH_UNAVAILABLE")})
    return {"status": "RESULTS" if results else "UNAVAILABLE", "results": results, "failures": failures,
            "queries": queries, "project_text_sent": False, "pages_fetched": False,
            "adapter_sha256": getattr(backend, "fingerprint", None)}
