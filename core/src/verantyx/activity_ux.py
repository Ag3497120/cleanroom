"""A quiet composer status strip driven by observed host activity."""
import asyncio
import os
import time

from .presentation import safe_text
from .reading_ux import fit_text


class ActivityUX:
    def _activity(self):
        state = (self.view or {}).get("state") or {}
        result = state.get("work_result") or {}
        waiting = (self.question is not None or (result.get("status") == "WAITING_OWNER"
                   and not state.get("work_owner_reply") and not self.busy))
        if waiting:
            return "waiting", self._tr("Your reply is needed", "あなたの返答を待っています"), self._tr("Type your answer below", "下の入力欄から返答できます")
        if self.readonly:
            return "idle", self._tr("Viewing saved work", "保存された作業を閲覧中"), ""
        if not self.busy:
            if self.phase in ("needs attention", "paused"):
                return "waiting", self._tr("Work paused", "作業を一時停止しています"), self._tr("/details opens the activity log", "/details で操作ログを確認")
            return "idle", self._tr("Ready", "入力待ち"), ""
        phase = self.phase
        if phase.startswith("tool:"):
            _, tool, path = phase.split(":", 2)
            label = {"read_file": ("Reading a file", "ファイルを読んでいます"),
                     "list_files": ("Checking files", "ファイルを確認しています"),
                     "write_candidate": ("Saving changes", "変更を保存しています"),
                     "run_project_check": ("Running checks", "検査を実行しています"),
                     "call_mcp": ("Using a connected tool", "接続ツールを実行しています"),
                     "list_mcp_tools": ("Checking available tools", "利用できるツールを確認しています")}.get(tool, ("Running a tool", "ツールを実行しています"))
            return "tool", self._tr(*label), safe_text(path or tool)
        if phase == "reflection":
            return "model", self._tr("Organizing the work", "作業内容を整理しています"), self._tr("Additional AI call", "追加のAI呼び出し")
        if phase == "compact":
            return "model", self._tr("Summarizing the conversation", "会話を要約しています"), self._tr("Reducing context for the next turn", "次の処理に向けて文脈を圧縮中")
        if self.active_action == "web-read":
            return "tool", self._tr("Reading the web", "Webを検索・取得しています"), self._tr("No model call", "この取得処理はAIを呼びません")
        if self.active_action == "web-setup":
            return "tool", self._tr("Setting up Web tools", "Webツールを設定しています"), ""
        if self.model_waiting:
            return "model", self._tr("Waiting for the AI response", "AIの回答を待っています"), self._tr("You can add a follow-up while waiting", "待機中も次の依頼を入力できます")
        if phase == "validating":
            return "saving", self._tr("Checking the response", "回答を確認しています"), self._tr("Checking format and saving the result", "形式を検査して結果を保存中")
        return "working", self._tr("Preparing the next step", "次の処理を準備しています"), ""

    def _activity_mark(self, kind):
        if kind == "idle":
            return "○"
        if kind == "waiting":
            return "●"
        if os.environ.get("VERANTYX_REDUCE_MOTION") == "1":
            return "•"
        return "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[int(time.monotonic() * 8) % 10]

    def _activity_line(self):
        if self.native_selection:
            return getattr(self, "_frozen_activity", [])
        kind, label, detail = self._activity()
        elapsed = ""
        if self.busy and self.started is not None:
            seconds = max(0, int(time.monotonic() - self.started))
            elapsed = f"  {seconds // 60:02d}:{seconds % 60:02d}"
        width = self._pane_width("agent")
        fragments = [("class:activity." + kind, " " + self._activity_mark(kind) + " " + fit_text(label, max(1, width - len(elapsed) - 4))),
                     ("class:activity.meta", elapsed)]
        self._frozen_activity = fragments
        return fragments

    def _activity_detail(self):
        if self.native_selection:
            return getattr(self, "_frozen_activity_detail", "")
        kind, _, detail = self._activity()
        usage = getattr(self, "last_model_usage", None)
        if usage and not detail:
            tokens = usage["tokens"]
            if usage["source"] == "local_cache":
                detail = self._tr("Reused saved result · no model call", "保存済みの結果を再利用 · AI呼び出しなし")
            else:
                input_count, cached = tokens.get("input_tokens"), tokens.get("cached_input_tokens")
                if input_count is not None:
                    detail = self._tr("Last call: ", "前回: ") + f"{input_count:,} " + self._tr("input", "入力")
                    if cached is not None:
                        detail += f" · {cached / input_count:.0%} " + self._tr("cached", "キャッシュ") if input_count else ""
                    if "output_tokens" in tokens:
                        detail += f" · {tokens['output_tokens']:,} " + self._tr("output", "出力")
                else:
                    detail = self._tr("Usage not reported", "利用量は未報告")
                detail += "  /usage"
        value = " " + fit_text(detail or self._tr("Enter send · /help commands", "Enter 送信 · /help 操作一覧"), self._pane_width("agent") - 1)
        self._frozen_activity_detail = value
        return value

    def _composer_height(self):
        from prompt_toolkit.utils import get_cwidth
        # Grow with the draft, keeping conversation space when the input is empty.
        width = max(1, self._pane_width("agent") - 4)
        limit = 3 if self._compact_ui() else 5
        rows = 0
        for line in self.input.text.split("\n"):
            rows += max(1, (get_cwidth(line.expandtabs(4)) + width - 1) // width)
            if rows >= limit:
                return limit
        return rows

    def _work_indicator(self):
        if self.native_selection:
            return self.native_indicator
        return self._activity()[1] if self.busy or self._activity()[0] == "waiting" else ""

    def _agent_input_style(self):
        # Motion belongs to the status glyph, not the text the user is typing.
        return "" if "NO_COLOR" in os.environ else "class:composer"

    async def _animate_activity(self):
        while True:
            animated = self.busy and self.question is None and not self.native_selection
            delay = .125 if animated and os.environ.get("VERANTYX_REDUCE_MOTION") != "1" else 1
            await asyncio.sleep(delay)
            if animated:
                self.app.invalidate()

    def _handle_control(self, value, buffer):
        if value.strip() == "/context" and self.question is None:
            from .context_meter import read, describe
            self.context_composition = read(self.root)
            self.info_text = describe(self.context_composition, self._locale() == "ja")
            buffer.reset()
            self._render()
            return True
        if value.strip() != "/usage" or self.question is not None:
            return super()._handle_control(value, buffer)
        from .model_usage import summary
        data = summary(self.root)
        tokens = data["tokens"]
        ratio = data["cached_input_ratio"]
        lines = [self._tr("Model usage", "モデル利用量"),
                 self._tr("Reported calls: ", "結果を受信した呼び出し: ") + str(data["calls"]),
                 self._tr("Local reuses: ", "保存済み結果の再利用: ") + str(data["local_reuses"]),
                 self._tr("Input: ", "入力: ") + (f"{tokens['input_tokens']:,}" if "input_tokens" in tokens else "—"),
                 self._tr("Cached input: ", "キャッシュ済み入力: ") + (f"{tokens['cached_input_tokens']:,}" if "cached_input_tokens" in tokens else "—"),
                 self._tr("Cache read rate: ", "キャッシュ再利用率: ") + (f"{ratio:.1%}" if ratio is not None else "—"),
                 self._tr("Output: ", "出力: ") + (f"{tokens['output_tokens']:,}" if "output_tokens" in tokens else "—"),
                 "", self._tr("Measured since this update. Missing usage is unknown, not zero.",
                               "この更新以降の記録です。未報告の利用量は0として扱いません。")]
        for purpose, count in data["calls_by_purpose"].items():
            lines.append(purpose.removeprefix("verantyx.").removesuffix("-request.v1") + ": " + str(count))
        self.info_text = "\n".join(lines)
        buffer.reset()
        self._render()
        return True

    def _context_line(self):
        if self.native_selection:
            return getattr(self, "native_context_line", "")
        from .context_meter import LABELS
        value = getattr(self, "context_composition", None)
        if not value:
            return self._tr("Request breakdown: — · /context · /usage", "依頼の内訳: — · /context · /usage")
        pieces = []
        for key, count in sorted(value["categories"].items(), key=lambda row: -row[1])[:2]:
            pieces.append(self._tr(*LABELS.get(key, (key, key))) + f" {count / max(1, value['bytes']):.0%}")
        line = self._tr("Last request / bytes: ", "直近の依頼・バイト比率: ") + " · ".join(pieces) + " · /context"
        return fit_text(line, max(1, self._pane_width("agent") - 4))
