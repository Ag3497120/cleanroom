"""Discoverable Web tools without a model call or an editor round trip."""
from .errors import LedgerError
from .presentation import safe_text


class WebUX:
    def _init_web(self):
        self.web_enabled = False
        self.browser_enabled = False
        self._refresh_web_status()

    def _refresh_web_status(self):
        from .work_tools import load
        try:
            settings, _ = load(self.root)
            granted = settings["mcp_servers"].get("web", {}).get("tools", [])
            self.web_enabled = "web_search" in granted and "web_fetch" in granted
            self.browser_enabled = "browser_read" in granted
        except (OSError, LedgerError):
            self.web_enabled = self.browser_enabled = False

    def _web_menu(self):
        self._refresh_web_status()
        choices = [("help", self._tr("Search /web QUERY · Read /browse URL", "検索 /web 検索語 · 本文 /browse URL")),
                   ("setup", self._tr("Enable free Web search and page reading", "無料Web検索・本文取得を有効にする"))]
        import sys
        if sys.platform == "darwin":
            choices.append(("browser", self._tr("Enable native WebKit page reading too", "MacのWebKit本文取得も有効にする")))
        def selected(value):
            if value is None:
                return
            if value in ("setup", "browser"):
                self.start_action("web-setup", browser=value == "browser")
            else:
                self.info_text = self._tr(
                    "Web tools\n/web QUERY: search public pages without an API key.\n/browse URL: read a page.\n/browse --browser URL: render JavaScript with disposable WebKit.\n/tools: enable or inspect the built-in MCP. These commands do not call a language model.\nCLI: verantyx toolbox status | verantyx commands toolbox",
                    "Webツール\n/web 検索語: APIキーなしで公開ページを検索\n/browse URL: ページの本文を取得\n/browse --browser URL: JavaScriptをWebKitで描画して取得\n/tools: 内蔵MCPの設定。これらのコマンド自体はAIを呼びません。\nCLI: verantyx toolbox status | verantyx commands toolbox")
                self._render()
        label = "Web: ON" if self.web_enabled else "Web: OFF"
        self._show_picker(label + " / " + self._tr("Web & MCP", "Web検索・MCP"), choices, selected)

    def _handle_control(self, value, buffer):
        head, _, rest = value.strip().partition(" ")
        if head not in ("/web", "/browse", "/tools") or self.question is not None:
            return super()._handle_control(value, buffer)
        if self.busy or self.readonly:
            self._log(self._tr("Finish the current operation first. Your draft is retained.", "現在の操作が終わるまで下書きを保持します。"))
            return True
        buffer.reset()
        if head == "/tools" or not rest.strip():
            self._web_menu()
            return True
        if head == "/web":
            tool, arguments = "web_search", {"query": rest.strip()}
        else:
            browser = rest.startswith("--browser ")
            tool = "browser_read" if browser else "web_fetch"
            arguments = {"url": rest.removeprefix("--browser ").strip()}
        if not self.web_enabled or (tool == "browser_read" and not self.browser_enabled):
            # Keep the request available after setup instead of silently discarding it.
            buffer.text = value
            self._web_menu()
            return True
        self.start_action("web-read", tool=tool, arguments=arguments)
        return True

    def _show_web_result(self, result):
        if not result.get("ok"):
            body = result.get("error", "WEB_ERROR") + "\n" + result.get("message", "")
        elif "results" in result:
            lines = [self._tr("Web search: ", "Web検索: ") + result.get("query", "")]
            for index, row in enumerate(result["results"], 1):
                lines.append(f"\n{index}. {row['title']}\n{row['url']}\n{row['snippet']}")
            if not result["results"]:
                lines.append(self._tr("No results found.", "検索結果はありません。"))
            lines.append(self._tr("\nRead a source with /browse URL.", "\n/browse URL で出典の本文を確認できます。"))
            body = "\n".join(lines)
        else:
            body = result.get("title", "") + "\n" + result.get("url", "") + "\n\n" + result.get("text", "")
            if result.get("needs_browser"):
                body += self._tr("\n\nLittle text found. Try /browse --browser URL.", "\n\n本文が少ないため /browse --browser URL でも取得できます。")
        self.info_text = safe_text(body, multiline=True)
        self._render()

    def _web_operation(self, action, **kwargs):
        from .development_console import _mutate
        from .web_tools import WebError
        try:
            if action == "web-setup":
                from .web_mcp import setup
                result = _mutate(self.root, self.configuration, setup, browser=kwargs.get("browser", False), confirmed=True)
                self.loop.call_soon_threadsafe(self._refresh_web_status)
                self.loop.call_soon_threadsafe(self._show_web_result, {
                    "ok": True, "title": "Web: ON", "text": self._tr(
                        "/web QUERY searches the web. /browse URL reads a page. The AI can also use these tools.",
                        "/web 検索語 で検索、/browse URL で本文取得ができます。AIからも利用できます。")})
            else:
                from .commands_toolbox import call_web
                result = _mutate(self.root, self.configuration, call_web, kwargs["tool"], kwargs["arguments"])
                self.loop.call_soon_threadsafe(self._show_web_result, result["result"])
        except WebError as error:
            raise LedgerError(error.code, {"message": str(error)}) from None
        return None
