"""Explicit TUI commands and presentation-only state, independent of work memory."""
from collections import deque
from pathlib import Path
import shlex

from .errors import LedgerError
from .interaction_text import tr, help_text
from .presentation import safe_text

SETTINGS_ACTIONS = {
    "inline-settings", "models", "model-roles", "notebook-connections",
    "sandbox-backend", "work-harness", "personal-profile", "personal-pace",
}


class InteractionUX:
    def _init_interaction(self, practice=False):
        self.practice = practice
        self.practice_notes = []
        self.practice_backup = None
        self.settings_active = False
        self.settings_lines = deque(maxlen=80)
        self.after_settings = None
        self.info_text = None
        self.volatile_answer = None
        self.volatile_history = []
        self.attachment_queue = []
        self.details_visible = False
        self.model_label = "DEMO / no model call" if practice else ""
        if not practice:
            self._refresh_model_label()

    def _ux(self, key, **values):
        return tr(key, self.configuration.get("ui", {}).get("locale", "en"), **values)

    def _refresh_model_label(self):
        try:
            from .model_settings import current_label
            self.model_label = safe_text(current_label(self.root, self.configuration))
        except (LedgerError, OSError, ValueError):
            self.model_label = self._ux("unconfigured")

    def _primary_answer(self):
        if self.settings_active:
            return self._ux("settings") + "\n\n" + "\n".join(self.settings_lines) + "\n\n" + self._ux("setting_input")
        if self.info_text is not None:
            return self.info_text
        if self.volatile_answer is not None:
            return self._ux("private") + "\n\n" + self.volatile_answer
        if self.practice:
            return self._ux("demo_answer") + "\n\n" + self._ux("demo_steps") + "\n\n" + self._ux("workflow_guide")
        projection = (self.view or {}).get("ownership_projection") or {}
        answer = projection.get("work_answer")
        if answer:
            question = projection.get("owner_question")
            return answer + ("\n\n" + question if question else "")
        return (self.view or {}).get("panes", {}).get("agent") or self._ux("empty")

    def _system_text(self):
        if self.practice:
            return self._ux("demo")
        lines = list(self.logs)
        if not self.details_visible:
            lines = [line.splitlines()[0] for line in lines[-2:]]
        status = safe_text(self.phase)
        return status + ("\n" + "\n".join(lines) if lines else "")

    def _pane_border_style(self, name):
        if self.active_input != name:
            return "class:pane.inactive"
        if name == "owner":
            return "class:pane.memo" if self.owner_mode == "memo" else "class:pane.search"
        return "class:pane.agent"

    def _pane_caption(self, name):
        return name.upper() + " / " + self._session_caption(name) + (" / " + self._ux("active") if self.active_input == name else "")

    def _menu_detail(self):
        if not self.picker:
            return ""
        value = self.picker["choices"][self.choice_index][0]
        return safe_text(self.picker.get("descriptions", {}).get(value, self._ux("back")), multiline=True)

    def _show_help(self):
        self.info_text = help_text(self.configuration["ui"]["locale"])
        self._render()

    def _settings_value(self, value):
        """Only explicit /text, inside settings, can answer the active setting."""
        if value.casefold() in ("back", "cancel", "close"):
            self._cancel_question()
            self.settings_active = False
            self._render()
            return
        if self.question is None and self.picker is None:
            self._log(self._ux("setting_input"))
            return
        if self.picker is not None:
            key = value.strip().casefold()
            aliases = self.picker.get("aliases", {})
            selected = aliases.get(key)
            if selected is None:
                found = [choice for choice, label in self.picker["choices"]
                         if label.casefold() == key or label.casefold().startswith(key + " /")]
                if len(found) == 1:
                    selected = found[0]
            if selected is None:
                self._log(self._ux("keys"))
                return
            if self.practice:
                picker, self.picker = self.picker, None
                picker["callback"](selected)
                self._focus_input()
            else:
                self._answer(selected)
        else:
            self._answer(value)

    def _stop_settings_for(self, value):
        self.after_settings = value
        self._cancel_question()
        self.settings_active = False
        self.settings_lines.clear()
        self.info_text = None
        if not self.busy:
            self.after_settings = None
            if value:
                self.input.buffer.text = value
                self._submit(self.input.buffer)

    def _handle_control(self, value, buffer):
        """True means consumed. Nothing here turns task words into classifications."""
        if not value:
            return False
        if self.settings_active and not value.startswith("/"):
            buffer.reset()
            self._stop_settings_for(value)
            return True
        # Existing host questions outside settings retain their explicit answer path.
        if self.question is not None and not self.settings_active:
            return False
        if not value.startswith("/"):
            return False
        if self.settings_active and (value.startswith("//") or value.split()[0] in (
                "/verantyx", "/model", "/models", "/settings", "/tutorial")):
            buffer.reset()
            self._stop_settings_for(value)
            return True
        if value.startswith("//"):
            if self.busy:
                self._log(self._tr("Finish the current operation first; the draft is retained.",
                                   "現在の操作が終わるまで下書きを保持します。"))
                return True
            buffer.reset()
            message = value[2:].strip()
            if not message:
                self.info_text = self._ux("private")
                self._render()
                return True
            if self.practice:
                self._tour_event("private")
                self.info_text = self._ux("private") + "\n\n" + self._ux("demo_answer")
                self._render()
            else:
                self.info_text = None
                self.start_action("temporary-chat", request=message, history=list(self.volatile_history))
            return True
        head, _, rest = value.partition(" ")
        head, rest = head.casefold(), rest.strip()
        known = {"/verantyx", "/model", "/models", "/settings", "/help", "/commands",
                 "/attach", "/detach", "/tutorial", "/done", "/close", "/details"}
        known.update(("/queue", "/approvals"))
        if head in ("/queue", "/approvals") and not self.settings_active:
            buffer.reset()
            if head == "/queue":
                self._queue_menu()
            else:
                if self.busy:
                    buffer.text = value
                    return True
                self.start_action("inline-settings", section="permissions")
            return True
        if head not in known:
            if not self.settings_active:
                from .attachment_inputs import paths_in_text
                paths = paths_in_text(value)
                if paths and paths[0]["path"] == value.strip("\'\""):
                    return self._handle_control("/attach " + shlex.quote(paths[0]["path"]), buffer)
            if self.settings_active:
                buffer.reset()
                self._settings_value(value[1:].strip())
                return True
            return False  # Existing explicit navigation commands continue below.
        buffer.reset()
        if head in ("/help", "/commands"):
            self._show_help()
        elif head == "/details":
            self.details_visible = not self.details_visible
            self._render()
        elif head == "/close":
            if self.settings_active:
                self._stop_settings_for("")
            self.info_text = None
            self.volatile_answer = None
            self.volatile_history.clear()
            self._render()
        elif head == "/done" and self.practice:
            if self.reader is None:
                self.app.exit(result=0)
            else:
                self.practice = False
                self.practice_notes.clear()
                self.info_text = None
                self.input.buffer.reset()
                if self.practice_backup is not None:
                    self.owner_drafts, self.owner_mode, document = self.practice_backup
                    self.owner_input.buffer.set_document(document)
                    self.practice_backup = None
                else:
                    self.owner_input.buffer.reset()
                self._refresh_model_label()
                self._render()
        elif head == "/tutorial":
            if not self.busy:
                if not self.practice:
                    self.practice_backup = (dict(self.owner_drafts), self.owner_mode, self.owner_input.buffer.document)
                    self.owner_drafts = {"memo": "", "search": ""}
                    self.owner_input.buffer.reset()
                self.practice = True
                self.tour_step = 0
                self.info_text = None
                self.practice_notes = []
                self.active_input = "agent"
                self.focus_name = "split"
                self._render()
        elif head == "/attach":
            try:
                from .attachment_inputs import parse_argument
                entry = parse_argument(rest)
                if len(self.attachment_queue) >= 4:
                    raise LedgerError("ATTACHMENT_INPUT")
                if not self.practice:
                    self.attachment_queue.append(entry)
                self.info_text = self._ux("attachments") + "\n" + safe_text(entry["path"]) + "\n\n" + self._ux("attachment_help")
            except LedgerError:
                self.info_text = self._ux("attachment_help")
            self._render()
        elif head == "/detach":
            self.attachment_queue.clear()
            self.info_text = self._ux("attachment_help")
            self._render()
        elif head in ("/verantyx", "/settings", "/models", "/model"):
            if self.busy:
                buffer.text = value
                return True
            section = "models" if head in ("/model", "/models") else "menu"
            try:
                tokens = shlex.split(rest)
                if head == "/verantyx" and tokens:
                    command = tokens.pop(0)
                    if command in ("model", "models"):
                        section = "models"
                    elif command in ("setup", "settings"):
                        section = tokens.pop(0) if tokens else "menu"
                    elif command in ("help", "commands", "--help"):
                        self._show_help()
                        return True
                    elif command in ("status", "config"):
                        section = "show"
                    elif command == "tutorial":
                        return self._handle_control("/tutorial", buffer)
                    else:
                        self._show_help()
                        return True
                elif tokens:
                    section = tokens.pop(0)
                from .settings_console import SECTIONS
                if tokens or section not in (*SECTIONS, "menu", "show"):
                    self._show_help()
                    return True
            except ValueError:
                self._show_help()
                return True
            if self.practice:
                self.settings_active = True
                from .choice_navigation import description
                choices = [("codex", "ChatGPT / Codex"), ("ollama", "Ollama / local"),
                           ("openai_compatible", "OpenAI-compatible server")]
                self._show_picker("Models / DEMO", choices,
                    lambda _: self._end_practice_setting(),
                    descriptions={k: description("", k, label, self.configuration["ui"]["locale"]) for k, label in choices},
                    aliases={k: k for k, _ in choices})
            else:
                self.start_action("inline-settings", section=section)
        return True

    def _end_practice_setting(self):
        self._tour_event("settings")
        self.settings_active = False
        self.info_text = self._ux("demo") + "\n\n" + self._ux("demo_steps")
        self._render()

    def _practice_owner(self):
        text = self._ux("demo_owner")
        notes = self.practice_notes
        if self.owner_mode == "search":
            query = self.owner_input.text.casefold()
            if query:
                return "\n".join(line for line in (text + "\n" + "\n".join(notes)).splitlines() if query in line.casefold())
        return text + "\n\n" + "\n".join(notes)

    def _practice_submit_owner(self, buffer):
        if not buffer.text.strip():
            self._cycle_inputs()
        elif self.owner_mode == "memo":
            self._tour_event("memo")
            self.practice_notes.append(buffer.text)
            buffer.reset()
            self._render()
        else:
            self._tour_event("search")
            self._render()
        return True
