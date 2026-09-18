"""Compact, selectable reading surfaces. These controls never invoke a model."""
from bisect import bisect_right
from dataclasses import dataclass
import os
import shutil
import subprocess
import sys
import time

from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.layout import ScrollOffsets
from prompt_toolkit.mouse_events import MouseButton, MouseEventType
from prompt_toolkit.selection import SelectionState, SelectionType
from prompt_toolkit.utils import get_cwidth

from .presentation import safe_text


COPY = {
    "en": {
        "keys": "Empty Enter: Agent > Memo > Search | F2 Menu | F5 Full width | F6 Copy",
        "hint": "Small window: F5 expands this pane; enlarge/maximize your terminal for both.",
        "scroll": "PgUp/PgDn Scroll | Ctrl+Home Top | Ctrl+End Latest | F7 Terminal selection",
        "reading": "Drag + wheel / edge to extend | Ctrl+C / F6 Copy | Esc Input",
        "copied": "Copied to the system clipboard.",
        "local_copy": "Copied inside Cleanroom only. F7 enables terminal selection for OS copy.",
        "empty": "No text selected.",
        "native": "Terminal selection ON: drag and use your terminal's Copy. F7 resumes.",
        "resumed": "Application mouse controls restored.",
        "fullscreen": "Full-width pane / Toggle with F5",
        "split": "Two-pane layout / Return with F5",
        "copy": "Copy selected text, or the current pane / F6",
        "latest": "Latest text / Ctrl+End",
        "top": "Start of this view / Ctrl+Home",
        "new": "New text / Ctrl+End",
        "details": "System activity is collapsed. /details opens it.",
        "memo": "MEMO / local only",
        "search": "SEARCH / Owner notes",
        "help": "Reading controls\nF5 or /fullscreen: expand the current pane. F5 or /split: return.\nDrag in any reading pane to select text. Ctrl+C copies a selection; F6 or /copy copies the selection, or the entire current pane when nothing is selected.\nPgUp/PgDn scroll the active pane with overlap. Ctrl+Home goes to the top; Ctrl+End or /latest returns to live output. Reading older text does not stop the model.\nF3 focuses the text. Arrow keys move; Shift+arrows select. Enter or Esc returns to input.\nF7 or /mouse temporarily releases mouse reporting for your terminal's native selection and Copy. Press F7 again to restore in-app wheel controls. Full-width mode avoids selecting both columns.\nOn small windows, repeated labels and system activity are collapsed, not deleted. Use /details and /help, or enlarge/maximize the terminal. Terminal font size belongs to the terminal application.",
    },
    "ja": {
        "keys": "空Enter: Agent > メモ > 検索 | F2 メニュー | F5 全幅 | F6 コピー",
        "hint": "小さい画面: F5で今の欄を全幅表示。両欄を見るには端末を拡大・全画面に。",
        "scroll": "PgUp/PgDn 読む | Ctrl+Home 先頭 | Ctrl+End 最新 | F7 端末の文字選択",
        "reading": "ドラッグ＋スクロールで選択拡大 | Ctrl+C / F6 コピー | Esc 入力へ",
        "copied": "システムのクリップボードへコピーしました。",
        "local_copy": "Cleanroom内にコピーしました。OSへのコピーはF7で端末の文字選択へ。",
        "empty": "コピーする文字が選択されていません。",
        "native": "端末の文字選択ON: ドラッグして端末のコピー操作。F7で通常操作へ。",
        "resumed": "アプリ内のマウス操作へ戻りました。",
        "fullscreen": "今の欄を全幅表示 / F5で切り替え",
        "split": "二分割へ戻る / F5で切り替え",
        "copy": "選択した文章、または今の欄をコピー / F6",
        "latest": "最新の文章へ / Ctrl+End",
        "top": "表示の先頭へ / Ctrl+Home",
        "new": "新着あり / Ctrl+End",
        "details": "システム通知は省略中です。/detailsで開けます。",
        "memo": "メモ / 自分だけ",
        "search": "検索 / Ownerの記録",
        "help": "読みやすさとコピー\nF5または/fullscreenで今の欄を全幅表示。F5または/splitで元の配置へ戻ります。\nAgent・Owner・検査・ノート・Review・システム通知の文章をドラッグで選択できます。選択中のCtrl+Cはコピーです。F6または/copyは選択部分、未選択なら今の欄の全文をコピーします。\nPgUp/PgDnは少し重ねながらスクロール。Ctrl+Homeで先頭、Ctrl+Endまたは/latestで最新へ。過去を読んでいてもAIの作業は続きます。\nF3で本文へ。矢印で移動、Shift+矢印で選択、EnterまたはEscで入力へ戻ります。\nF7または/mouseで端末自身のドラッグ選択とコピー操作を使えます。もう一度F7でアプリ内のホイール操作へ戻ります。左右を一緒に選ばないためには先にF5で全幅にしてください。\n小さい画面では重複した説明とシステム通知を省略しますが、記録は消しません。/detailsや/helpで確認でき、端末を拡大・全画面にしても使えます。文字サイズは端末アプリ側で変更してください。",
    },
    "zh-Hans": {
        "keys": "空Enter: Agent > 备忘 > 搜索 | F2 菜单 | F5 全宽 | F6 复制",
        "hint": "窗口较小：F5展开当前面板；放大或最大化终端可同时阅读两栏。",
        "scroll": "PgUp/PgDn 滚动 | Ctrl+Home 开头 | Ctrl+End 最新 | F7 终端选择",
        "reading": "拖动选择，Ctrl+C / F6复制。Enter / Esc返回输入。",
        "copied": "已复制到系统剪贴板。",
        "local_copy": "仅复制到Cleanroom内部。F7可使用终端的系统复制。",
        "empty": "没有选中文字。",
        "native": "终端选择已开启：拖动并使用终端的复制。F7恢复。",
        "resumed": "已恢复应用内鼠标操作。",
        "fullscreen": "当前面板全宽 / F5切换",
        "split": "返回双栏 / F5切换",
        "copy": "复制所选文字或当前面板 / F6",
        "latest": "最新文字 / Ctrl+End",
        "top": "本页开头 / Ctrl+Home",
        "new": "有新内容 / Ctrl+End",
        "details": "系统通知已折叠。/details展开。",
        "memo": "备忘 / 仅本地",
        "search": "搜索 / Owner记录",
        "help": "阅读与复制\nF5或/fullscreen展开当前面板，F5或/split返回。\n拖动选择正文，Ctrl+C复制所选内容；F6或/copy在没有选择时复制当前面板全文。\nPgUp/PgDn重叠翻页，Ctrl+Home到开头，Ctrl+End或/latest回到最新内容。阅读旧内容不会停止AI。\nF3进入正文，方向键移动，Shift+方向键选择，Enter或Esc返回输入。\nF7或/mouse切换终端原生选择，再按F7恢复应用鼠标滚动。建议先F5全宽，避免同时选择两栏。\n小窗口只折叠说明和系统通知，不删除记录。/details和/help仍可查看；也可以放大或最大化终端。",
    },
    "ko": {
        "keys": "빈 Enter: Agent > 메모 > 검색 | F2 메뉴 | F5 전체 폭 | F6 복사",
        "hint": "작은 창: F5로 현재 패널 확대. 두 패널은 터미널 확대/전체 화면에서.",
        "scroll": "PgUp/PgDn 스크롤 | Ctrl+Home 처음 | Ctrl+End 최신 | F7 터미널 선택",
        "reading": "드래그로 선택, Ctrl+C / F6 복사. Enter / Esc로 입력 복귀.",
        "copied": "시스템 클립보드에 복사했습니다.",
        "local_copy": "Cleanroom 내부에만 복사했습니다. F7로 터미널 복사를 사용하세요.",
        "empty": "선택한 글자가 없습니다.",
        "native": "터미널 선택 ON: 드래그 후 터미널 복사. F7로 복귀.",
        "resumed": "앱 마우스 조작으로 돌아왔습니다.",
        "fullscreen": "현재 패널 전체 폭 / F5 전환",
        "split": "두 패널로 복귀 / F5 전환",
        "copy": "선택한 글 또는 현재 패널 복사 / F6",
        "latest": "최신 글 / Ctrl+End",
        "top": "화면 처음 / Ctrl+Home",
        "new": "새 글 / Ctrl+End",
        "details": "시스템 알림은 접혀 있습니다. /details로 열기.",
        "memo": "메모 / 로컬 전용",
        "search": "검색 / Owner 기록",
        "help": "읽기와 복사\nF5 또는 /fullscreen으로 현재 패널을 확대하고 F5 또는 /split으로 돌아갑니다.\n본문을 드래그해 선택하고 Ctrl+C로 복사합니다. F6 또는 /copy는 선택이 없으면 현재 패널 전체를 복사합니다.\nPgUp/PgDn은 일부를 겹쳐 넘기며 Ctrl+Home은 처음, Ctrl+End 또는 /latest는 최신으로 갑니다. 과거 내용을 읽어도 AI 작업은 계속됩니다.\nF3으로 본문에 들어가 화살표로 이동하고 Shift+화살표로 선택합니다. Enter 또는 Esc로 입력으로 돌아갑니다.\nF7 또는 /mouse로 터미널의 기본 선택/복사를 사용하고 F7로 앱 스크롤을 복원합니다. 두 열이 함께 선택되지 않도록 먼저 F5를 사용하세요.\n작은 창에서는 설명과 시스템 알림만 접고 기록은 삭제하지 않습니다. /details와 /help, 터미널 확대/전체 화면을 이용할 수 있습니다.",
    },
    "es": {
        "keys": "Enter vacío: Agent > Nota > Buscar | F2 Menú | F5 Ampliar | F6 Copiar",
        "hint": "Ventana pequeña: F5 amplía el panel; maximiza el terminal para ver ambos.",
        "scroll": "PgUp/PgDn Leer | Ctrl+Home Inicio | Ctrl+End Último | F7 Selección nativa",
        "reading": "Arrastra para seleccionar; Ctrl+C / F6 copia. Enter / Esc vuelve a escribir.",
        "copied": "Copiado al portapapeles del sistema.",
        "local_copy": "Copiado solo dentro de Cleanroom. F7 permite copiar desde el terminal.",
        "empty": "No hay texto seleccionado.",
        "native": "Selección nativa ON: arrastra y usa Copiar del terminal. F7 vuelve.",
        "resumed": "Se restauró el ratón de la aplicación.",
        "fullscreen": "Ampliar panel / Alternar con F5",
        "split": "Volver a dos paneles / F5",
        "copy": "Copiar selección o panel actual / F6",
        "latest": "Texto más reciente / Ctrl+End",
        "top": "Inicio de la vista / Ctrl+Home",
        "new": "Texto nuevo / Ctrl+End",
        "details": "Actividad del sistema contraída. /details la abre.",
        "memo": "NOTA / solo local",
        "search": "BUSCAR / notas Owner",
        "help": "Lectura y copia\nF5 o /fullscreen amplía el panel actual; F5 o /split vuelve.\nArrastra para seleccionar y usa Ctrl+C. F6 o /copy copia la selección o, si no hay selección, todo el panel.\nPgUp/PgDn desplaza con solapamiento; Ctrl+Home va al inicio y Ctrl+End o /latest vuelve al texto más reciente. Leer mensajes anteriores no detiene el trabajo.\nF3 enfoca el texto; flechas mueven y Shift+flechas seleccionan. Enter o Esc vuelve a la entrada.\nF7 o /mouse activa la selección y copia nativa del terminal; F7 restaura la rueda de la aplicación. Amplía con F5 para no seleccionar las dos columnas.\nLas ventanas pequeñas contraen explicaciones y actividad, sin borrar registros. Usa /details, /help o maximiza el terminal.",
    },
}


def fit_text(text, width):
    text = safe_text(str(text)).replace("\n", " ")
    width = max(1, width)
    if get_cwidth(text) <= width:
        return text
    result, used = "", 0
    for character in text:
        cells = max(0, get_cwidth(character))
        if used + cells > max(0, width - 3):
            break
        result += character
        used += cells
    return result + "." * min(3, width)


@dataclass
class Row:
    source_start: int
    source_end: int
    display_start: int


class Viewport:
    """Soft wrapping with reversible text offsets, independent of input focus."""
    def __init__(self, context, follow=False):
        self.context, self.follow = context, follow
        self.raw = self.display = ""
        self.width = 0
        self.rows, self.styles = [], []
        self.source_starts, self.display_starts = [], []
        self.unseen = False

    def source_position(self, position):
        if not self.rows or position >= len(self.display):
            return len(self.raw)
        index = max(0, bisect_right(self.display_starts, position) - 1)
        row = self.rows[index]
        return min(row.source_end, row.source_start + max(0, position - row.display_start))

    def display_position(self, position):
        if not self.rows or position >= len(self.raw):
            return len(self.display)
        index = max(0, bisect_right(self.source_starts, position) - 1)
        row = self.rows[index]
        return row.display_start + min(max(0, position - row.source_start), row.source_end - row.source_start)

    def compose(self, raw, width, styles):
        self.raw, self.width = raw, max(1, width)
        self.rows, self.styles = [], []
        parts, offset, display_offset = [], 0, 0
        for number, line in enumerate(raw.split("\n")):
            start, cells = 0, 0
            spans = []
            for column, character in enumerate(line):
                size = max(0, get_cwidth(character))
                if cells + size > self.width and column > start:
                    spans.append((start, column))
                    start, cells = column, 0
                cells += size
            spans.append((start, len(line)))
            style = styles[number] if number < len(styles) else ""
            for first, last in spans:
                text = line[first:last]
                if "class:chat.user" in style.split():
                    text += " " * max(0, self.width - get_cwidth(text))
                self.rows.append(Row(offset + first, offset + last, display_offset))
                self.styles.append(style)
                parts.append(text)
                display_offset += len(text) + 1
            offset += len(line) + 1
        self.display = "\n".join(parts)
        self.source_starts = [row.source_start for row in self.rows]
        self.display_starts = [row.display_start for row in self.rows]


def _anchor(old, new, position):
    position = min(position, len(old))
    sample = old[position:position + 120]
    if sample and new[position:position + len(sample)] != sample:
        found = new.find(sample, max(0, position - 8192), min(len(new), position + 8192 + len(sample)))
        if found >= 0:
            return found
    return min(position, len(new))


def system_copy(text):
    """Explicit copy only; no shell, clipboard reads, network or OSC52 writes."""
    if sys.platform == "darwin":
        choices = [("pbcopy", [], "utf-8")]
    elif os.name == "nt" or os.environ.get("WSL_DISTRO_NAME"):
        choices = [("clip.exe", [], "utf-16")]
    else:
        choices = [("wl-copy", [], "utf-8"), ("xclip", ["-selection", "clipboard"], "utf-8"),
                   ("xsel", ["--clipboard", "--input"], "utf-8")]
    for command, args, encoding in choices:
        executable = shutil.which(command)
        if executable:
            try:
                result = subprocess.run([executable, *args], input=text.encode(encoding),
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
                if result.returncode == 0:
                    return True
            except (OSError, subprocess.TimeoutExpired):
                continue
    return False


class ReadingUX:
    def _init_reading(self):
        self.reading_views = {}
        self.reading_fullscreen = False
        self.native_selection = False
        self.reading_drag = None
        self.reading_notice = ("", 0)
        self.native_header = ""
        self.native_indicator = ""

    def _rt(self, key):
        return COPY.get(self._locale(), COPY["en"]).get(key, COPY["en"][key])

    def _compact_ui(self):
        size = self.output.get_size()
        return size.rows < 40 or size.columns < 120

    def _reading_areas(self):
        return {**self.areas, "system": self.system_area}

    def _reading_target(self):
        for name, area in self._reading_areas().items():
            if self.app.layout.has_focus(area):
                return name, area
        name = self.focus_name if self.focus_name in self.areas else (
            "agent" if self.active_input == "agent" else self._owner_page())
        return name, self.areas[name]

    def _reading_context(self, name):
        if name == "agent":
            surface = ("settings" if self.settings_active else
                       "info" if self.info_text is not None else
                       "private" if self.volatile_answer is not None else
                       "practice" if self.practice else "chat")
            return (self.console_sessions["agent"]["id"], surface)
        if name == "system":
            return ("system",)
        return (self.console_sessions["room"]["id"], self.memo_offset,
                self.owner_input.text if self.owner_mode == "search" else "",
                self.growth_selection, self.preview, self.practice)

    def _set_pane_text(self, name, raw):
        area = self._reading_areas()[name]
        raw = safe_text(raw, multiline=True).replace("\t", "    ")
        lexer = self.chat_lexer if name == "agent" else self.owner_lexer if name == "owner" else None
        source_styles = list(lexer.rows) if lexer else []
        context = self._reading_context(name)
        state = self.reading_views.get(name)
        if state is not None and state.context == context and (
                area.buffer.selection_state is not None or self.reading_drag is area or self.native_selection):
            state.unseen = state.unseen or raw != state.raw
            # Freeze the source while selecting, but still reflow after a resize.
            raw, source_styles = state.raw, list(getattr(state, "source_styles", source_styles))
        fresh = state is None or state.context != context
        if fresh:
            area.buffer.exit_selection()
            if self.reading_drag is area:
                self.reading_drag = None
            state = Viewport(context, follow=name == "agent" and context[-1] == "chat")
            self.reading_views[name] = state
        width = self._pane_width("agent" if name == "system" else name)
        if name == "system" and self._compact_ui():
            width = max(1, width - 2)  # Activity keeps its own inner frame.
        if not fresh and raw == state.raw and width == state.width:
            if lexer:
                lexer.rows = state.styles
            return
        old_document = area.buffer.document
        selection = area.buffer.selection_state
        anchor = state.source_position(selection.original_cursor_position) if selection else None
        top_row = min(area.window.vertical_scroll, max(0, old_document.line_count - 1))
        top = state.source_position(old_document.translate_row_col_to_index(top_row, 0))
        cursor = state.source_position(old_document.cursor_position)
        if not fresh and not state.follow:
            top, cursor = _anchor(state.raw, raw, top), _anchor(state.raw, raw, cursor)
            state.unseen = state.unseen or raw != state.raw
        state.compose(raw, width, source_styles)
        state.source_styles = source_styles
        position = len(state.display) if state.follow else state.display_position(cursor)
        document = Document(state.display, cursor_position=position)
        area.buffer.set_document(document, bypass_readonly=True)
        if selection is not None:
            area.buffer.selection_state = SelectionState(state.display_position(anchor), selection.type)
        if state.follow:
            state.unseen = False
        else:
            area.window.vertical_scroll = document.translate_index_to_position(state.display_position(top))[0]
        area.window.vertical_scroll_2 = 0
        if lexer:
            lexer.rows = state.styles

    def _reading_footer(self):
        size = self.output.get_size()
        notice, until = self.reading_notice
        if self.native_selection:
            lines = [self._rt("native"), "F7"]
        else:
            reading = any(self.app.layout.has_focus(area) for area in self._reading_areas().values())
            first = self._rt("reading") if reading else self._rt("keys")
            name, _ = self._reading_target()
            unseen = self.reading_views.get(name)
            second = (notice if time.monotonic() < until else
                      self._rt("new") if unseen and unseen.unseen else
                      self._rt("hint") if self._compact_ui() else self._rt("scroll"))
            name, area = self._reading_target()
            info = area.window.render_info
            if info and area.buffer.document.line_count > info.window_height:
                first_row = area.window.vertical_scroll + 1
                last_row = min(area.buffer.document.line_count, first_row + info.window_height - 1)
                second = f"{first_row}–{last_row}/{area.buffer.document.line_count} | " + second
            lines = [first, second]
        return "\n".join(" " + fit_text(line, max(1, size.columns - 2)) for line in lines)

    def _short_header(self):
        size = self.output.get_size()
        project = self.configuration.get("project", {}).get("name", self.root.name)
        state = self._work_indicator()
        if not state and self.phase not in ("idle", "recorded"):
            state = safe_text(self.phase)
        if self.read_error or self.cursor_error:
            state = "STALE / " + str(self.read_error or self.cursor_error)
        elif self.question is not None:
            state = self._ux("owner_question")
        caption = "CLEANROOM / " + str(project) + (" / " + state if state else "")
        web = "Web: ON" if getattr(self, "web_enabled", False) else "Web: OFF"
        return " " + fit_text(caption, size.columns - 2) + "\n " + fit_text(
            web + " /tools | " + self._reflection_hint() + " | " + self.model_label, size.columns - 2)

    def _reflection_hint(self):
        mode = self.configuration.get("runtime", {}).get("reflection", {}).get("mode", "same")
        return {"same": self._tr("Reflection: same AI", "整理: 同じAI"),
                "custom": self._tr("Reflection: separate AI", "整理: 別のAI"),
                "off": self._tr("Reflection: manual", "整理: 手動")}.get(mode, "Reflection: ?")

    def _work_indicator(self):
        return self.native_indicator if self.native_selection else super()._work_indicator()

    def _agent_input_style(self):
        return "" if self.native_selection else super()._agent_input_style()

    def _set_fullscreen(self, enabled=None):
        self.reading_fullscreen = not self.reading_fullscreen if enabled is None else enabled
        self.focus_name = self._reading_target()[0] if self.reading_fullscreen else "split"
        if self.focus_name == "system":
            self.focus_name = "agent"
        self._render()

    def _reading_jump(self, bottom):
        name, area = self._reading_target()
        area.buffer.exit_selection()
        state = self.reading_views.get(name)
        if state:
            state.follow, state.unseen = bottom, False
        self._render()
        area.buffer.cursor_position = len(area.text) if bottom else 0
        height = area.window.render_info.window_height if area.window.render_info else 1
        area.window.vertical_scroll = max(0, area.buffer.document.line_count - height) if bottom else 0
        area.window.vertical_scroll_2 = 0
        self.app.invalidate()

    def _copy_reading(self, only_selection=False, keep_selection=True):
        buffer = self.app.current_buffer
        selected = buffer.selection_state is not None
        if only_selection and not selected:
            return False
        if selected:
            name, area = next(((name, area) for name, area in self._reading_areas().items()
                               if area.buffer is buffer), (None, None))
            state = self.reading_views.get(name)
            if state:
                text = "\n".join(state.raw[state.source_position(first):state.source_position(last)]
                                 for first, last in buffer.document.selection_ranges())
            else:
                text = buffer.copy_selection().text
        elif self._picker_active():
            label = self.picker["choices"][self.choice_index][1]
            text = label + "\n" + self._menu_detail()
        else:
            name, area = self._reading_target()
            state = self.reading_views.get(name)
            text = state.raw if state else area.text
        if text:
            self.app.clipboard.set_text(text)
            copied = system_copy(text)
            self.reading_notice = (self._rt("copied" if copied else "local_copy"), time.monotonic() + 8)
        else:
            self.reading_notice = (self._rt("empty"), time.monotonic() + 5)
        if selected and not keep_selection:
            buffer.exit_selection()
        self._render()
        return True

    def _finish_reading_drag(self):
        area, self.reading_drag = self.reading_drag, None
        if hasattr(self, "reading_scroll"):
            self.reading_scroll.stop()
        # Terminal.app consumes Cmd+C instead of sending it over the PTY.
        # Copy the explicit mouse selection on release, retaining its highlight.
        if sys.platform == "darwin" and area is not None and area.buffer.selection_state is not None:
            self.app.layout.focus(area)
            self._copy_reading(only_selection=True)
        self.app.invalidate()

    def _clear_reading_selection(self):
        for area in self._reading_areas().values():
            if self.app.layout.has_focus(area) and area.buffer.selection_state is not None:
                area.buffer.exit_selection()
                self._render()
                return True
        return False

    def _toggle_native_selection(self):
        self.reading_drag = None
        if hasattr(self, "reading_scroll"):
            self.reading_scroll.stop()
        if not self.native_selection:
            self.native_header, self.native_indicator = self._header(), self._work_indicator()
            self.native_context_line = self._context_line() if hasattr(self, "_context_line") else ""
        self.native_selection = not self.native_selection
        if not self.native_selection:
            self.reading_notice = (self._rt("resumed"), time.monotonic() + 5)
            self._render()
        self.app.invalidate()

    def _show_help(self):
        super()._show_help()
        self.info_text += "\n\n" + self._rt("help")
        self.info_text += "\n\n" + self._tr(
            "Hold the mouse at the top/bottom edge to extend a selection automatically. Wheel and PgUp/PgDn preserve the anchor. On Mac, releasing a mouse selection copies it to the system clipboard; Cmd+C is handled by the terminal. F6 copies again.\n/web QUERY searches the web. /browse URL reads a page. /tools sets up the built-in Web MCP connection.",
            "マウスを欄の上端・下端へドラッグすると自動スクロールします。ホイール・PgUp/PgDnでも選択の始点を保持します。Macでは選択を離すとクリップボードへコピーします（Command+Cは端末側の操作）。F6でも再コピーできます。\n/web 検索語 でWeb検索、/browse URL で本文取得、/tools で内蔵Web MCPを設定できます。")
        self.info_text += "\n\n" + self._tr(
            "Owner search covers this notebook's complete saved history. Enter/F8: next matching line; Esc then F8: previous.\n/context: prepared request byte shares. /usage: reported tokens and cache. /timeout 1800: set the selected API model deadline to 30 minutes.",
            "Owner検索はこのノートの保存済み全履歴が対象です。Enter/F8で次の該当行、Esc→F8で前へ。\n/context: 依頼のバイト内訳。/usage: 報告されたトークンとキャッシュ。/timeout 1800: 選択中のAPIモデルの待ち時間を30分へ。")
        self._render()

    def _handle_control(self, value, buffer):
        command = value.strip()
        if command not in ("/fullscreen", "/split", "/copy", "/latest", "/top", "/mouse"):
            return super()._handle_control(value, buffer)
        buffer.reset()
        if command in ("/fullscreen", "/split"):
            self._set_fullscreen(command == "/fullscreen")
        elif command == "/copy":
            self._copy_reading()
        elif command in ("/latest", "/top"):
            self._reading_jump(command == "/latest")
        else:
            self._toggle_native_selection()
        return True

    def _install_reading(self, bindings):
        def reading_focused():
            return not self._picker_active() and any(
                self.app.layout.has_focus(area) for area in self._reading_areas().values())

        for name, area in self._reading_areas().items():
            area.window.scroll_offsets = ScrollOffsets(top=0, bottom=0, left=0, right=0)

        for name, area in {**self._reading_areas(), "agent-input": self.input,
                           "owner-input": self.owner_input}.items():
            original = area.control.mouse_handler
            def mouse(event, name=name, area=area, original=original):
                if self.picker is not None and not self._inline_choice():
                    return NotImplemented
                if event.event_type == MouseEventType.MOUSE_DOWN and event.button == MouseButton.LEFT:
                    self.app.layout.focus(area)
                    if name in self.areas:
                        self.active_input = "agent" if name == "agent" else "owner"
                    elif name in ("agent-input", "owner-input"):
                        self.active_input = name.split("-")[0]
                    if name in self._reading_areas():
                        self.reading_drag = area
                        state = self.reading_views.get(name)
                        if state:
                            state.follow = False
                result = original(event)
                if event.event_type == MouseEventType.MOUSE_UP and self.reading_drag is area:
                    self._finish_reading_drag()
                return result
            area.control.mouse_handler = mouse

        @bindings.add("f5", eager=True)
        def fullscreen(event):
            if self.picker is None or self._inline_choice():
                self._set_fullscreen()

        @bindings.add("f6", eager=True)
        def copy(event):
            self._copy_reading()

        @bindings.add("f7", eager=True)
        def terminal_selection(event):
            self._toggle_native_selection()

        @bindings.add("enter", filter=Condition(reading_focused), eager=True)
        def return_to_input(event):
            self._clear_reading_selection()
            self._focus_input()

        def move(event, direction, select=False):
            buffer = event.current_buffer
            name, _ = self._reading_target()
            state = self.reading_views.get(name)
            if state:
                state.follow = False
            if select and buffer.selection_state is None:
                buffer.start_selection(selection_type=SelectionType.CHARACTERS)
            if not select:
                buffer.exit_selection()
            if direction == "up":
                buffer.cursor_up()
            elif direction == "down":
                buffer.cursor_down()
            else:
                buffer.cursor_position = max(0, min(len(buffer.text),
                    buffer.cursor_position + (-1 if direction == "left" else 1)))

        for key in ("up", "down", "left", "right"):
            bindings.add(key, filter=Condition(reading_focused))(
                lambda event, key=key: move(event, key))
            bindings.add("s-" + key, filter=Condition(reading_focused))(
                lambda event, key=key: move(event, key, True))
