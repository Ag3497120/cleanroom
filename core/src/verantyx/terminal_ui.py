"""Scrollback-friendly terminal presentation; no model or execution authority."""
from contextlib import contextmanager
import os
import sys
from time import monotonic

from . import __version__
from .i18n import text
from .presentation import safe_text
from .progress import observe


COMMANDS = ("/help", "/paste", "/model", "/editor", "/context", "/new", "/dictionary", "/learn", "/status", "/details", "/flow", "/checks", "/work", "/decide", "/target", "/sovereignty", "/quit")
STAGES = ("request", "context", "proposal", "assessment", "interpretation", "editor", "handoff_check", "candidate_execute", "asset_plan", "asset_check", "structure", "answer", "capture")


def capable_terminal():
    if os.environ.get("TERM") == "dumb":
        return False
    try:
        return all(stream.isatty() and os.isatty(stream.fileno()) for stream in (sys.stdin, sys.stdout))
    except (AttributeError, OSError, ValueError):
        return False


def input_bindings():
    from prompt_toolkit.key_binding import KeyBindings
    keys = KeyBindings()

    @keys.add("enter")
    def submit(event):
        buffer = event.current_buffer
        if buffer.complete_state and buffer.complete_state.current_completion:
            buffer.complete_state = None
        elif buffer.document.char_before_cursor == "\\":
            buffer.delete_before_cursor()
            buffer.insert_text("\n")
        else:
            buffer.validate_and_handle()

    @keys.add("c-j")
    @keys.add("escape", "enter")
    def newline(event):
        event.current_buffer.insert_text("\n")

    @keys.add("c-c")
    def interrupt(event):
        if event.current_buffer.text:
            event.current_buffer.reset()
        else:
            event.app.exit(exception=KeyboardInterrupt())

    return keys


def command_completer():
    from prompt_toolkit.completion import Completer, Completion

    class Commands(Completer):
        def get_completions(self, document, complete_event):
            value = document.text_before_cursor
            if value.startswith("/") and not any(char.isspace() for char in value):
                for command in COMMANDS:
                    if command.startswith(value):
                        yield Completion(command, start_position=-len(value))

    return Commands()


class Activity:
    def __init__(self, ui):
        self.ui = ui
        self.started = monotonic()
        self.stage = None
        self.seen = []
        self.live = None
        self.thinking = ""
        self.thinking_shown = False
        self.model_status = ""

    @property
    def elapsed(self):
        return monotonic() - self.started

    def update(self, stage):
        if stage not in STAGES or stage == self.stage:
            return
        self.stage = stage
        self.seen.append(stage)
        self.flush_thinking()
        self.model_status = ""
        self.ui.notice(f"[{self.elapsed:6.1f}s] " + text(self.ui.locale, "console.stage." + stage), "dim")

    def flush_thinking(self):
        if self.thinking:
            self.ui.notice("  │ " + self.thinking, "dim")
            self.thinking = ""

    def model_update(self, event):
        kind = event["kind"]
        if kind == "start":
            self.flush_thinking()
            self.thinking_shown = False
            self.model_status = text(self.ui.locale, "console.model.waiting")
            self.ui.notice(text(self.ui.locale, "console.model.start", model=event["model"], seconds=event["timeout"]), "cyan")
            if event.get("output_tokens"):
                self.ui.notice(text(self.ui.locale, "console.model.budget", count=event["output_tokens"]), "dim")
            if event.get("reserve_output"):
                self.ui.notice(text(self.ui.locale, "console.model.reserve_output"), "dim")
        elif kind == "thinking" and event["text"]:
            if not self.thinking_shown:
                self.ui.notice(text(self.ui.locale, "console.model.thinking"), "dim")
                self.thinking_shown = True
            self.model_status = "thinking"
            self.thinking += safe_text(event["text"], multiline=True)
            while "\n" in self.thinking or len(self.thinking) >= 160:
                cut = self.thinking.find("\n")
                size = cut if 0 <= cut < 160 else 160
                self.ui.notice("  │ " + self.thinking[:size], "dim")
                self.thinking = self.thinking[size + (1 if size == cut else 0):]
        elif kind == "thinking_truncated":
            self.flush_thinking()
            self.ui.notice(text(self.ui.locale, "console.model.thinking_limit"), "dim")
        elif kind == "output":
            self.flush_thinking()
            self.model_status = text(self.ui.locale, "console.model.output", count=event["characters"])
        elif kind == "validated":
            self.flush_thinking()
            self.ui.notice(text(self.ui.locale, "console.model.validated"), "dim")
            self.model_status = ""

    def render(self):
        from rich.console import Group
        from rich.spinner import Spinner
        from rich.text import Text
        label = text(self.ui.locale, "console.stage." + self.stage) if self.stage else text(self.ui.locale, "console.working")
        line = Text(label + f"  {self.elapsed:.1f}s" + (" · " + self.model_status if self.model_status else ""), style="cyan")
        # Keep the spinner instance: its clock must not reset on each repaint.
        self.spinner.update(text=line)
        done = " · ".join(text(self.ui.locale, "console.phase." + stage) for stage in self.seen[:-1])
        footer = text(self.ui.locale, "console.stop_hint")
        return Group(self.spinner, Text((done + "  ·  " if done else "") + footer, style="dim"))

    def start(self):
        if self.ui.animated:
            from rich.live import Live
            from rich.spinner import Spinner
            self.spinner = Spinner("dots", style="cyan")
            self.live = Live(console=self.ui.console, get_renderable=self.render, refresh_per_second=8,
                             transient=True, redirect_stdout=False, redirect_stderr=False)
            self.live.start(refresh=True)

    def stop(self):
        self.flush_thinking()
        if self.live:
            self.live.stop()


class ConsoleUI:
    def __init__(self, root, configuration, locale, *, plain=False):
        self.root, self.configuration, self.locale = root, configuration, locale
        self.enhanced = not plain and capable_terminal()
        self.animated = self.enhanced and os.environ.get("VERANTYX_REDUCE_MOTION") != "1"
        self.console = None
        self.session = None
        self.model = ""
        if self.enhanced:
            from rich.console import Console
            self.console = Console(file=sys.stdout, markup=False, highlight=False)

    def notice(self, value, style=None):
        value = safe_text(value, multiline=True)
        if self.console:
            from rich.text import Text
            self.console.print(Text(value, style=style or ""))
        else:
            print(value, flush=True)

    def welcome(self):
        if not self.enhanced:
            self.notice(text(self.locale, "console.welcome", name=self.configuration["project"]["name"]))
            self.notice(text(self.locale, "console.help"))
            return
        from rich.panel import Panel
        from rich.text import Text
        content = Text("✣  VERANTYX", style="bold cyan")
        content.append("  " + __version__ + "\n", style="dim")
        content.append(safe_text(self.configuration["project"]["name"]), style="bold")
        purpose = self.configuration["project"].get("purpose")
        if purpose:
            content.append("  ·  " + safe_text(purpose))
        content.append("\n" + safe_text(str(self.root)), style="dim")
        content.append("\n\n" + text(self.locale, "console.tagline"))
        self.console.print(Panel(content, border_style="cyan", padding=(1, 2)))
        self.notice(text(self.locale, "console.shortcuts"), "dim")

    def connected(self, model):
        self.model = safe_text(model)
        self.notice(text(self.locale, "console.connected", model=self.model), "cyan")

    def read(self):
        if not self.enhanced:
            value = input("\n" + text(self.locale, "console.prompt") + " ")
            return self.read_paste() if value.strip() == "/paste" else value
        from prompt_toolkit import PromptSession
        from prompt_toolkit.output import ColorDepth
        from prompt_toolkit.styles import Style
        if self.session is None:
            # Memory-only editing history. The domain ledger owns saved work.
            self.session = PromptSession(multiline=True, key_bindings=input_bindings(),
                                         completer=command_completer(), complete_while_typing=True,
                                         prompt_continuation=[("class:prompt", "  · ")],
                                         reserve_space_for_menu=4)

        def prompt():
            width = max(12, self.session.app.output.get_size().columns - 1)
            return [("class:line", "─" * width + "\n"), ("class:prompt", "❯ ")]

        def toolbar():
            value = self.session.default_buffer.text
            count = text(self.locale, "console.input_count", lines=value.count("\n") + 1, count=len(value))
            return [("class:hint", " " + text(self.locale, "console.input_hint") + "\n " + self.model + " · " + count)]

        value = self.session.prompt(prompt, bottom_toolbar=toolbar,
                                   style=Style.from_dict({"prompt": "ansicyan bold", "line": "ansibrightblack",
                                                          "hint": "ansibrightblack", "bottom-toolbar": "noreverse"}),
                                   color_depth=ColorDepth.DEPTH_1_BIT if "NO_COLOR" in os.environ else None)
        return self.read_paste() if value.strip() == "/paste" else value

    def read_paste(self):
        self.notice(text(self.locale, "console.paste_hint"))
        lines = []
        while True:
            line = input("  · ")
            if line == "/cancel":
                return ""
            if line == "/send":
                return "".join(lines)
            lines.append(line + "\n")

    def received(self, value):
        self.notice(text(self.locale, "console.input_received", lines=value.count("\n") + 1, count=len(value)), "dim")

    def error(self, error):
        from .model_observation import diagnostic
        value = diagnostic(error)
        code, details = value["code"], value["details"]
        label = code + (" / " + details["reason"] if details.get("reason") else "")
        if "http_status" in details:
            label += " / HTTP " + str(details["http_status"])
        self.notice("[" + label + "] " + text(self.locale, "error." + code), "red")
        if code == "SHARED_CONTEXT_LIMIT":
            self.notice(text(self.locale, "console.context_limit"))
        if details.get("reason") == "MODEL_API_GENERATION_LIMIT":
            self.notice(text(self.locale, "console.generation_limit"))
            for key in ("thinking_characters", "response_characters", "generated_tokens", "output_token_limit"):
                if key in details:
                    self.notice(text(self.locale, "console.generation." + key, count=details[key]), "dim")

    @contextmanager
    def activity(self):
        activity = Activity(self)
        try:
            activity.start()
            with observe(activity.update, activity.model_update):
                yield activity
        finally:
            activity.stop()

    def response(self, result, elapsed):
        if not self.enhanced:
            from .cli import kernel_output
            kernel_output(result, self.locale, False, "ask")
            return
        from rich.markdown import Markdown
        from rich.panel import Panel
        from rich.rule import Rule
        from rich.text import Text
        from .presentation import narrative_facts, render_reply, response_freshness
        state = result["state"]
        self.console.print(Rule(Text(text(self.locale, "console.response_title"), style="bold cyan"), align="left", style="cyan"))
        response = state.get("latest_response") or {}
        if (response_freshness(state, self.locale) == "CURRENT" and response.get("mode") == "GENERATED"
                and state.get("trust") != "ARCHIVE_ONLY"):
            self.notice(text(self.locale, "presentation.generated_answer"), "dim")
            self.console.print(Markdown(safe_text(response["document"]["answer"], multiline=True), hyperlinks=False))
            bundle = narrative_facts(state, self.locale)
            known = {item["id"] for item in bundle["facts"]}
            fixed = {item["text"] for item in bundle["facts"]}
            explanations = list(dict.fromkeys(item["text"] for item in response["document"]["explanations"]
                                             if item["fact_id"] in known and item["text"] not in fixed))
            if explanations:
                self.console.print()
                self.notice(text(self.locale, "presentation.generated_explanations"), "dim")
                self.notice("\n\n".join(explanations))
            lines = list(dict.fromkeys(item["text"] for item in bundle["facts"]))
            from .workflow_presentation import lines as workflow_lines
            lines.extend(workflow_lines(state, self.locale))
            if state.get("handoff_plan"):
                from .shared_context import current_editor_attempt
                attempt = current_editor_attempt(state)
                from .decision_context import handoff_status
                lines.append(text(self.locale, "context." + handoff_status(state)))
                if attempt:
                    lines.append(text(self.locale, "context.boundary"))
            if bundle["omitted_count"]:
                lines.append(text(self.locale, "presentation.omitted", count=bundle["omitted_count"]))
            lines.extend(item["text"] for item in bundle["next_steps"])
            self.console.print()
            # Model Markdown cannot consume, restyle or close the fact panel.
            self.console.print(Panel(Text(safe_text("\n\n".join(lines), multiline=True)),
                                     title=Text(text(self.locale, "presentation.recorded_facts")),
                                     border_style="yellow", padding=(0, 1)))
        else:
            # Preserve all fallback, stale, other-language and archive notices.
            self.notice(render_reply(state, self.locale))
        human = state.get("deltas", {}).get("human_delta", [])
        if result.get("work_loop"):
            from .commands_work import display_work
            display_work(result["work_loop"], self.locale)
        if state["learning_preferences"]["mode"] == "digest" and human:
            self.console.print()
            self.notice(text(self.locale, "response.learning"), "cyan")
            for item in human[:state["learning_preferences"]["max_items"]]:
                self.notice("  · " + safe_text(item["concept"]))
        self.console.print()
        self.notice(text(self.locale, "console.completed", seconds=f"{elapsed:.1f}"), "dim")

    def details(self, result):
        if result is None:
            self.notice(text(self.locale, "console.no_task"))
            return
        from .presentation import render_reply
        state = result["state"]
        self.notice(text(self.locale, "ledger.run", run=state["run_id"], revision=state["revision"]), "cyan")
        self.notice(render_reply(state, self.locale, include_sources=True, include_codes=True))
