// A single-request, disposable native WebKit reader. No saved browser profile.
import AppKit
import WebKit

final class Reader: NSObject, WKNavigationDelegate {
    let app = NSApplication.shared
    var window: NSWindow!
    var view: WKWebView!
    var allowedHost = ""
    var requestID = ""
    var finished = false

    func finish(_ result: [String: Any]) {
        guard !finished else { return }
        finished = true
        var response = result
        response["id"] = requestID
        if let data = try? JSONSerialization.data(withJSONObject: response, options: [.sortedKeys]) {
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write(Data([10]))
        }
        view?.stopLoading()
        exit(0)
    }

    func start() {
        guard let line = readLine(), let data = line.data(using: .utf8),
              let input = try? JSONSerialization.jsonObject(with: data) as? [String: String],
              let address = input["url"], let url = URL(string: address),
              let host = url.host, ["http", "https"].contains(url.scheme ?? ""),
              url.user == nil, url.password == nil else {
            finish(["ok": false, "error": "INVALID_URL", "message": "A public HTTP URL is required."])
            return
        }
        requestID = input["id"] ?? ""
        allowedHost = host.lowercased()
        app.setActivationPolicy(.accessory)
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        view = WKWebView(frame: NSRect(x: 0, y: 0, width: 1200, height: 850), configuration: configuration)
        view.navigationDelegate = self
        window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.contentView = view
        // Attach to a window without stealing focus, moving the pointer or typing.
        window.orderOut(nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + 22) {
            self.finish(["ok": false, "error": "TIMEOUT", "message": "WebKit did not finish reading the page."])
        }
        view.load(URLRequest(url: url, timeoutInterval: 18))
        app.run()
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url,
              ["https", "http"].contains(url.scheme ?? ""),
              url.host?.lowercased() == allowedHost,
              url.user == nil, url.password == nil,
              url.port == nil || [80, 443].contains(url.port!) else {
            decisionHandler(.cancel)
            if action.targetFrame?.isMainFrame == true {
                finish(["ok": false, "error": "CROSS_HOST_REDIRECT",
                        "message": "Read the redirect with web_fetch, then request its public destination explicitly."])
            }
            return
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        // Wait for a short DOM quiet period, with a hard bound for live pages.
        // Completion is the extraction result, never a PAGE_READY notification.
        let script = #"""
        await new Promise(resolve => {
            let idle;
            const done = () => { clearTimeout(idle); clearTimeout(cap); observer.disconnect(); resolve(); };
            const settle = () => { clearTimeout(idle); idle = setTimeout(done, 350); };
            const observer = new MutationObserver(settle);
            const cap = setTimeout(done, 2500);
            observer.observe(document.documentElement, {childList:true,subtree:true,characterData:true});
            settle();
        });
        const full = (document.querySelector('main, article') || document.body)?.innerText || '';
        const links = Array.from(document.querySelectorAll('a[href]'))
            .filter(a => /^https?:/.test(a.href) && a.innerText.trim()).slice(0, 20)
            .map(a => ({title:a.innerText.trim().slice(0,200),url:a.href.slice(0,2048)}));
        return {ok:true,url:location.href,title:document.title.slice(0,500),
                text:full.slice(0,16000),truncated:full.length>16000,links:links};
        """#
        webView.callAsyncJavaScript(script, arguments: [:], in: nil, in: .defaultClient) { outcome in
            switch outcome {
            case .success(let value):
                if let response = value as? [String: Any] {
                    self.finish(response)
                } else {
                    self.finish(["ok": false, "error": "EMPTY_PAGE", "message": "WebKit returned no page text."])
                }
            case .failure:
                self.finish(["ok": false, "error": "EXTRACTION_FAILED", "message": "WebKit could not read the DOM."])
            }
        }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        finish(["ok": false, "error": "NAVIGATION_FAILED", "message": "The page could not be loaded."])
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        finish(["ok": false, "error": "NAVIGATION_FAILED", "message": "The page could not be loaded."])
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        finish(["ok": false, "error": "BROWSER_EXITED", "message": "The browser content process exited."])
    }
}

let reader = Reader()
reader.start()
