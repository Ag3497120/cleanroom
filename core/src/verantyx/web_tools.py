"""Key-free search and bounded public-page reads, independent of UI and models.

Search/listing separation follows Verantyx bdcd218. See browser/NOTICE.txt.
Pages and snippets are untrusted data, never permissions or instructions.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import http.client
import ipaddress
import re
import socket
import ssl
import time
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit, urlunsplit

import certifi


class WebError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def public_url(url):
    """Validate every destination, including redirects; resolve before connecting."""
    if not isinstance(url, str) or len(url) > 4096 or any(ord(c) < 33 for c in url):
        raise WebError("INVALID_URL", "Provide a complete http:// or https:// URL.")
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").encode("idna").decode("ascii")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        if (parts.scheme not in ("http", "https") or not host or parts.username is not None
                or parts.password is not None or port not in (80, 443) or "\\" in url):
            raise ValueError()
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        ips = list(dict.fromkeys(row[4][0] for row in addresses))
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise WebError("PRIVATE_ADDRESS", "Only public internet addresses are allowed.")
    except WebError:
        raise
    except (ValueError, UnicodeError, OSError):
        raise WebError("INVALID_URL", "The public URL could not be resolved.") from None
    return parts, host, port, ips


@dataclass
class Page:
    url: str
    text: str
    content_type: str
    status: int = 200


def fetch_page(url, timeout=12, max_bytes=2_000_000):
    """Pin the validated IP while retaining the hostname for TLS/SNI and Host.

No ambient proxy, cookies, login profiles, or credentials are inherited.
"""
    deadline = time.monotonic() + timeout
    for _ in range(6):
        parts, host, port, ips = public_url(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WebError("TIMEOUT", "The page took too long to respond.")
        if parts.scheme == "https":
            connection = http.client.HTTPSConnection(host, port, timeout=remaining,
                context=ssl.create_default_context(cafile=certifi.where()))
        else:
            connection = http.client.HTTPConnection(host, port, timeout=remaining)
        # HTTPConnection uses this hook before HTTPS wraps the socket with SNI.
        connection._create_connection = lambda address, timeout, source_address=None: socket.create_connection(
            (ips[0], port), timeout, source_address)
        try:
            path = urlunsplit(("", "", quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~"),
                               quote(parts.query, safe="%&=+/:?@!$'()*,-._~"), ""))
            connection.request("GET", path, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Version/17.0 Safari/605.1.15",
                "Accept": "text/html,application/xhtml+xml,text/plain,application/json;q=0.5",
                "Accept-Encoding": "identity"})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise WebError("REDIRECT", "The redirect has no destination.")
                url = urljoin(url, location)
                continue
            if response.status >= 400 or response.status == 202:
                code = "RATE_LIMITED" if response.status == 429 else "BLOCKED" if response.status in (202, 403) else "HTTP_ERROR"
                raise WebError(code, f"The site returned HTTP {response.status}.")
            content_type = response.headers.get_content_type()
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise WebError("UNSUPPORTED_ENCODING", "The site ignored the uncompressed-content request.")
            if content_type not in ("text/html", "application/xhtml+xml", "text/plain", "application/json"):
                raise WebError("UNSUPPORTED_CONTENT", f"Cannot extract {content_type}; use an HTML or text page.")
            data = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise WebError("TIMEOUT", "The page took too long to download.")
                if connection.sock:
                    connection.sock.settimeout(remaining)
                chunk = response.read1(min(65536, max_bytes + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise WebError("PAGE_TOO_LARGE", "The page exceeds the 2 MB download limit.")
            encoding = response.headers.get_content_charset() or "utf-8"
            try:
                text = data.decode(encoding, errors="replace")
            except LookupError:
                text = data.decode("utf-8", errors="replace")
            return Page(url, text, content_type, response.status)
        except (TimeoutError, socket.timeout):
            raise WebError("TIMEOUT", "The site did not respond in time.") from None
        except (OSError, http.client.HTTPException, UnicodeError):
            raise WebError("NETWORK_ERROR", "The page could not be downloaded.") from None
        finally:
            connection.close()
    raise WebError("REDIRECT_LIMIT", "The page redirected too many times.")


def compact(text):
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def result_url(href, base):
    try:
        target = urljoin(base, href)
        parts = urlsplit(target)
        host = parts.hostname or ""
        if host == "duckduckgo.com" or host.endswith(".duckduckgo.com"):
            target = parse_qs(parts.query).get("uddg", [target])[0]
        parts = urlsplit(target)
        return target if (len(target) <= 4096 and parts.scheme in ("https", "http")
                          and parts.hostname and not parts.username and not any(ord(c) < 33 for c in target)) else ""
    except ValueError:
        return ""


class SearchHTML(HTMLParser):
    """Parse each listing with its own snippet, without attribute-order assumptions."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self.capture = None
        self.depth = 0
        self.zero = False
        self.blocked = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if "no-results" in classes:
            self.zero = True
        if "anomaly" in attrs.get("class", "") or attrs.get("id") == "challenge-form":
            self.blocked = True
        if tag == "a" and "result__a" in classes:
            self.results.append({"title": "", "url": attrs.get("href", ""), "snippet": ""})
            self.capture, self.depth = "title", 1
        elif "result__snippet" in classes and self.results:
            self.capture, self.depth = "snippet", 1
        elif self.capture and tag not in ("br", "img", "meta", "input", "hr", "link", "wbr"):
            self.depth += 1

    def handle_endtag(self, tag):
        if self.capture and tag not in ("br", "img", "meta", "input", "hr", "link", "wbr"):
            self.depth -= 1
            if self.depth <= 0:
                self.capture = None

    def handle_data(self, text):
        if self.capture:
            self.results[-1][self.capture] += text


class ArticleHTML(HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "template", "noscript", "svg", "canvas"}
    BREAKS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "section", "article", "main", "tr", "pre"}

    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.stack = base, []
        self.body, self.main, self.title, self.links = [], [], [], []
        self.link = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.BREAKS:
            self.handle_data("\n")
        if tag not in ("br", "hr", "img", "meta", "link", "input", "source", "wbr", "area", "embed", "param", "col"):
            self.stack.append(tag)
        if tag == "a" and attrs.get("href") and not any(t in self.SKIP for t in self.stack):
            self.link = {"title": "", "url": result_url(attrs["href"], self.base)}

    def handle_endtag(self, tag):
        if tag in self.BREAKS:
            self.handle_data("\n")
        if tag == "a" and self.link is not None:
            if self.link["url"] and self.link["title"].strip() and len(self.links) < 40:
                self.link["title"] = compact(self.link["title"])[:200]
                self.links.append(self.link)
            self.link = None
        if tag in self.stack:
            index = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[index:]

    def handle_data(self, text):
        if any(t in self.SKIP for t in self.stack):
            return
        if "title" in self.stack:
            self.title.append(text)
            return
        self.body.append(text)
        if "article" in self.stack or "main" in self.stack:
            self.main.append(text)
        if self.link is not None:
            self.link["title"] += text

    def text(self):
        body = "".join(self.main if len("".join(self.main)) >= 80 else self.body)
        return "\n".join(line for raw in body.splitlines() if (line := compact(raw)))


def failure(error, **extra):
    return {"ok": False, "error": error.code, "message": str(error), **extra}


def search(query, limit=5, fetcher=fetch_page):
    if not isinstance(query, str) or not query.strip() or len(query) > 500 or not 1 <= limit <= 10:
        raise WebError("ARGUMENTS", "Use a query of 1–500 characters and a limit of 1–10.")
    # Retain explicit quotes: exact-phrase searches are a user's choice.
    query = query.strip()
    url = "https://html.duckduckgo.com/html/?" + urlencode({"q": query})
    try:
        page = fetcher(url)
        parser = SearchHTML()
        parser.feed(page.text)
        if parser.blocked:
            raise WebError("BLOCKED", "DuckDuckGo requested a browser challenge. Try later; this is not zero results.")
        results, seen = [], set()
        for row in parser.results:
            target = result_url(row["url"], page.url)
            if not target or target in seen or not row["title"].strip():
                continue
            results.append({"title": compact(row["title"]), "url": target, "snippet": compact(row["snippet"])})
            seen.add(target)
            if len(results) >= limit:
                break
        if not results and not parser.zero:
            raise WebError("SEARCH_UNAVAILABLE", "No listings could be extracted. The response may be a challenge or changed HTML.")
        return {"ok": True, "query": query, "provider": "duckduckgo_html", "source_url": page.url,
                "results": results, "result_count": len(results), "fetched_at": datetime.now(timezone.utc).isoformat(),
                "content_kind": "search_listings", "untrusted": True,
                "guidance": "These are titles and snippets. Read a result with web_fetch before making specific claims."}
    except WebError as error:
        return failure(error, query=query, provider="duckduckgo_html")


def read_page(url, max_chars=16000, fetcher=fetch_page):
    if not 200 <= max_chars <= 24000:
        raise WebError("ARGUMENTS", "max_chars must be between 200 and 24000.")
    try:
        page = fetcher(url)
        parser = ArticleHTML(page.url)
        if page.content_type in ("text/html", "application/xhtml+xml"):
            parser.feed(page.text)
            text, title, links = parser.text(), compact("".join(parser.title)), parser.links
        else:
            text, title, links = page.text, "", []
        return {"ok": True, "url": page.url, "title": title, "text": text[:max_chars], "links": links,
                "truncated": len(text) > max_chars, "http_status": page.status, "content_type": page.content_type,
                "fetched_at": datetime.now(timezone.utc).isoformat(), "untrusted": True,
                "needs_browser": len(text.strip()) < 160, "content_kind": "page_text"}
    except WebError as error:
        return failure(error, url=url)
