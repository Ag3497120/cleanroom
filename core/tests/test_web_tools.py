"""Search, public-network boundaries and real stdio MCP without paid models."""
import asyncio
from copy import deepcopy
from email.message import Message
import json
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
from urllib.parse import parse_qs, urlsplit

from verantyx import config, web_tools as web, work_tools
from verantyx.cli import parse
from verantyx.web_mcp import bounded, browser_fetch, preset, setup


HTML = '''<div class="result"><a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fguide&amp;x=1"
 class="result__a extra">A &amp; <b>B</b></a><span class="result__snippet">First <b>summary</b>.</span></div>
<div class="result"><a class="result__a" href="https://example.org">Second</a></div>
<div class="result"><a class="result__a" href="javascript:alert(1)">Invalid</a></div>'''


class WebTools(TestCase):
    def test_search_preserves_query_encoding_and_associates_snippets(self):
        fetcher = mock.Mock(return_value=web.Page("https://html.duckduckgo.com/html/", HTML, "text/html"))
        result = web.search('"C++" & 日本語 #1', fetcher=fetcher)
        self.assertEqual(parse_qs(urlsplit(fetcher.call_args.args[0]).query)["q"], ['"C++" & 日本語 #1'])
        self.assertEqual(result["result_count"], 2)
        self.assertEqual(result["results"][0], {"title": "A & B", "url": "https://example.com/guide", "snippet": "First summary."})
        self.assertEqual(result["results"][1]["snippet"], "")
        self.assertEqual(result["content_kind"], "search_listings")

    def test_one_result_is_a_valid_search(self):
        result = web.search("a", limit=1, fetcher=lambda url: web.Page(url, HTML, "text/html"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["result_count"], 1)

    def test_blocked_changed_html_and_zero_results_are_distinct(self):
        for html, expected in [('<form id="challenge-form">Challenge</form>', "BLOCKED"),
                               ('<html>Unexpected layout</html>', "SEARCH_UNAVAILABLE"),
                               ('<div class="no-results">No results</div>', None)]:
            with self.subTest(expected=expected):
                result = web.search("x", fetcher=lambda url: web.Page(url, html, "text/html"))
                self.assertEqual(result.get("error"), expected)
                self.assertEqual(result["ok"], expected is None)

    def test_article_excludes_scripts_and_prefers_main_and_keeps_links(self):
        html = '<title>Title &amp; more</title><nav>Navigation</nav><main><p>' + 'Useful content. ' * 20
        html += '</p><script>ignore this</script><a href="/source">Source</a></main><footer>Footer</footer>'
        result = web.read_page("https://example.com", 200,
                               fetcher=lambda url: web.Page(url, html, "text/html"))
        self.assertEqual(result["title"], "Title & more")
        self.assertTrue(result["truncated"])
        self.assertNotIn("ignore", result["text"])
        self.assertNotIn("Navigation", result["text"])
        self.assertEqual(result["links"], [{"title": "Source", "url": "https://example.com/source"}])

    def test_private_and_mixed_dns_addresses_are_rejected(self):
        for ips in [["127.0.0.1"], ["169.254.169.254"], ["::1"], ["93.184.216.34", "10.0.0.1"]]:
            addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ips]
            with mock.patch.object(socket, "getaddrinfo", return_value=addresses):
                with self.assertRaisesRegex(web.WebError, "public internet"):
                    web.public_url("https://example.com")

    def test_schemes_credentials_and_ports_are_rejected_without_network(self):
        for url in ["file:///etc/passwd", "https://user:password@example.com", "http://example.com:8080", "http://[bad", "http://example.com/\n"]:
            with self.subTest(url=url), mock.patch.object(socket, "getaddrinfo") as dns:
                with self.assertRaises(web.WebError):
                    web.public_url(url)
                dns.assert_not_called()

    def test_redirect_is_validated_before_connecting(self):
        connection = mock.Mock()
        response = connection.getresponse.return_value
        response.status = 302
        response.getheader.return_value = "http://127.0.0.1/"
        valid = (urlsplit("https://example.com"), "example.com", 443, ["93.184.216.34"])
        with mock.patch.object(web, "public_url", side_effect=[valid, web.WebError("PRIVATE_ADDRESS", "private")]), \
                mock.patch.object(web.http.client, "HTTPSConnection", return_value=connection) as factory:
            with self.assertRaises(web.WebError):
                web.fetch_page("https://example.com")
            factory.assert_called_once()
            connection.close.assert_called_once()

    def test_output_budget_preserves_valid_json(self):
        value = bounded({"ok": True, "text": "日" * 24000, "links": [{"url": "x" * 4096}] * 30})
        self.assertTrue(value["truncated"])
        self.assertLessEqual(len(json.dumps(value, ensure_ascii=False)), 22000)
        self.assertLessEqual(len(json.dumps(value, ensure_ascii=False).encode("utf-8")), 52000)
        self.assertGreater(len(value["text"]), 1000)

    def test_browser_checks_request_identity_and_public_url(self):
        with mock.patch("verantyx.web_mcp.public_url"), mock.patch("os.access", return_value=True), \
                mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout='{"id":"wrong","ok":true}')):
            self.assertEqual(browser_fetch("https://example.com", "/test/helper")["error"], "BROWSER_PROTOCOL")


class WebSetup(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cfg = config.defaults(self.root, "en")
        config.save(self.root, self.cfg, None)

    def test_setup_merges_existing_grants_and_is_repeatable(self):
        settings = deepcopy(work_tools.DEFAULT)
        settings["write_candidates"] = False
        settings["mcp_servers"]["existing"] = {"argv": ["/usr/bin/true"], "tools": ["read"],
                                                "argument_schemas": {}, "env": {}, "timeout": 5}
        work_tools.configure(self.root, settings, confirmed=True)
        first = setup(self.root, self.cfg, confirmed=True)
        second = setup(self.root, self.cfg, confirmed=True)
        current, _ = work_tools.load(self.root)
        self.assertFalse(current["write_candidates"])
        self.assertEqual(current["mcp_servers"]["existing"], settings["mcp_servers"]["existing"])
        self.assertEqual(first, second)
        self.assertNotIn("settings", first)

    def test_setup_does_not_replace_an_unrelated_web_server(self):
        settings = deepcopy(work_tools.DEFAULT)
        settings["mcp_servers"]["web"] = dict(preset(), argv=["/usr/bin/true"])
        work_tools.configure(self.root, settings, confirmed=True)
        with self.assertRaises(web.WebError):
            setup(self.root, self.cfg, confirmed=True)

    def test_cli_commands_and_optional_browser_are_registered(self):
        _, args = parse(["toolbox", "setup-web", "--browser", "--yes"])
        self.assertTrue(args.browser and args.yes)
        self.assertEqual(parse(["web-search", "hello"])[1].query, "hello")
        self.assertTrue(parse(["web-fetch", "https://example.com", "--browser"])[1].browser)

    def test_real_mcp_worker_discovers_and_calls_tools_in_ephemeral_home(self):
        setup(self.root, self.cfg, confirmed=True)
        worker = work_tools.MCPWorker(self.root, {"web": preset()})
        try:
            listing = worker.call("web")
            self.assertEqual({tool["name"] for tool in listing["tools"]}, {"web_search", "web_fetch"})
            response = worker.call("web", "web_fetch", {"url": "file:///etc/passwd"})
            result = json.loads(response["content"][0]["text"])
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "INVALID_URL")
        finally:
            worker.close()
