"""A loopback-only, read-only browser view of the personal notebook.

No model calls, writes, filesystem browsing, telemetry, or external web assets.
The capability URL is private. This is not a public or multi-user web service.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, urlsplit
import hmac
import json
import secrets
import webbrowser

from . import atlas_data
from . import personal_profile as profile
from .errors import LedgerError

STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/assets/atlas.css": ("atlas.css", "text/css; charset=utf-8"),
          "/assets/atlas.js": ("atlas.js", "text/javascript; charset=utf-8")}


class AtlasServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, port, locale, project_root=None):
        super().__init__(("127.0.0.1", port), AtlasHandler)
        self.origin = "http://127.0.0.1:" + str(self.server_address[1])
        self.token = secrets.token_urlsafe(32)
        self.locale = "en" if locale == "en" else "ja"
        self.project_root = project_root
        package = resources.files("verantyx").joinpath("web", "atlas")
        self.assets = {path: (package.joinpath(filename).read_bytes(), mime)
                       for path, (filename, mime) in STATIC.items()}
        for path in ("/", "/index.html"):
            if path in self.assets:
                body, mime = self.assets[path]
                self.assets[path] = (body.replace(b'lang="ja"', ('lang="' + self.locale + '"').encode()), mime)


class AtlasHandler(BaseHTTPRequestHandler):
    server_version = "CleanroomLocal"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *args):
        # Do not write private searches, record identifiers, or tokens to logs.
        pass

    def _send(self, status, body, mime="application/json; charset=utf-8"):
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                         "img-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _local(self):
        hosts = self.headers.get_all("Host", [])
        origin = self.headers.get("Origin")
        return (len(hosts) == 1 and hosts[0] == self.server.origin.removeprefix("http://")
                and (origin is None or origin == self.server.origin)
                and self.headers.get("Sec-Fetch-Site") != "cross-site")

    def _authorized(self):
        value = self.headers.get("Authorization", "")
        return value.isascii() and hmac.compare_digest(value, "Bearer " + self.server.token)

    def do_GET(self):
        try:
            if len(self.path) > 8192 or not self._local():
                self._send(403, {"error": "LOCAL_ORIGIN_REQUIRED"})
                return
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc:
                self._send(400, {"error": "LOCAL_PATH_REQUIRED"})
                return
            if parsed.path in self.server.assets:
                data, mime = self.server.assets[parsed.path]
                self._send(200, data, mime)
                return
            if not parsed.path.startswith("/api/"):
                self._send(404, {"error": "NOT_FOUND"})
                return
            if not self._authorized():
                self._send(401, {"error": "OPEN_PRIVATE_URL_FROM_TERMINAL"})
                return
            args = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=12)
            if any(len(value) != 1 for value in args.values()):
                raise ValueError("Duplicate query")
            args = {key: values[0] for key, values in args.items()}
            if parsed.path == "/api/atlas":
                if set(args) - {"search", "technology", "kind", "project", "month", "offset", "limit"}:
                    raise ValueError("Unknown query")
                for name in ("offset", "limit"):
                    if name in args:
                        args[name] = int(args[name])
                # Bound a single page window, not the lifetime notebook size.
                if args.get("offset", 0) > 100000:
                    raise ValueError("Narrow the filter before paging further")
                result = atlas_data.snapshot(**args)
                if self.server.project_root is not None:
                    from . import config
                    current, _ = config.load(self.server.project_root)
                    if current:
                        self.server.locale = "en" if current["ui"]["locale"] == "en" else "ja"
                result["locale"] = self.server.locale
                result["language_flag"] = {"requested": self.server.locale, "source": "PROJECT_OR_EXPLICIT_CLI"}
                from .notebook_bridge import graph as notebook_graph
                result["connections"] = notebook_graph()
                from .learning_guides import catalogue as guide_catalogue
                result["learning_guides"] = guide_catalogue()
                self._send(200, result)
            elif parsed.path == "/api/guides":
                if set(args) - {"offset"}:
                    raise ValueError("Guide query")
                from .learning_guides import catalogue as guide_catalogue
                self._send(200, guide_catalogue(offset=int(args.get("offset", "0"))))
            elif parsed.path == "/api/guide":
                if set(args) - {"id", "detail"} or "id" not in args:
                    raise ValueError("Guide query")
                from .learning_guides import read as read_guide
                self._send(200, read_guide(args["id"], detail=args.get("detail", "summary")))
            elif parsed.path == "/api/entry":
                if set(args) - {"id", "observation"} or "id" not in args:
                    raise ValueError("Entry query")
                observation = int(args["observation"]) if "observation" in args else None
                self._send(200, atlas_data.detail(args["id"], observation))
            else:
                self._send(404, {"error": "NOT_FOUND"})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return
        except (ValueError, LedgerError):
            self._send(400, {"error": "RECORD_OR_FILTER_UNAVAILABLE", "writes": False})
        except Exception:
            # Private record bodies, database paths and stack traces stay off the HTTP response.
            self._send(503, {"error": "LOCAL_NOTEBOOK_UNAVAILABLE", "writes": False})

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        self._send(405, {"error": "READ_ONLY_VIEW", "writes": False})

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST
    do_OPTIONS = do_POST


def serve(*, port=0, open_browser=True, locale="ja", as_json=False, project_root=None):
    profile.require(type(port) is int and 0 <= port <= 65535, "ATLAS_PORT")
    try:
        server = AtlasServer(port, locale, project_root)
    except OSError as error:
        raise LedgerError("ATLAS_START_FAILED", {"reason": type(error).__name__}) from None
    url = server.origin + "/#token=" + server.token
    opened = False
    try:
        if as_json:
            print(json.dumps({"event": "atlas_started", "url": url, "read_only": True,
                              "scope": "LOOPBACK_ONLY", "model_calls": 0, "url_is_private": True}))
        else:
            print("\nCleanroom / My Atlas")
            print("Local, read-only. No AI calls. Keep this terminal open; Ctrl+C stops the view.")
            print("Private access link / このURLは共有しないでください:")
            print(url)
        if open_browser and not as_json:
            try:
                opened = bool(webbrowser.open(url, new=2))
            except Exception:
                opened = False
            if not opened:
                print("Open the private URL above in a browser. The server is running.")
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return {"ok": True, "status": "CLOSED", "browser_open_requested": open_browser,
            "browser_opened": opened, "writes": False, "model_calls": 0}
