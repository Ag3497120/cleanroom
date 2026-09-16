"""Record the real Cleanroom TUI using public, scripted fixture work.

No model calls, user profile reads or project files are used. This is a UI
demonstration, not an evaluation receipt. Output is GIF, MP4 and a poster.
Run with the optional capture dependencies documented in docs/DEMO_RECORDING.md.
"""
import argparse
import asyncio
import codecs
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import sys
import tempfile
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
COLS, ROWS = 140, 38
DURATION = 34
SCENES = [
    [
        0,
        "01  Ask normally.",
        "Your request has a background. The answer stays separate from system activity.",
        "TYPE A REQUEST  /  ENTER"
    ],
    [
        4,
        "02  Understanding does not wait for the finish.",
        "A small optional note arrives during work, with a stable L-number.",
        "OPTIONAL NOTE  /  NOT A MASTERY SCORE"
    ],
    [
        8,
        "03  Ask about one insight without replacing the work.",
        "Send L-000001. This recorded explanation is scripted; no model is called.",
        "L-000001  /  ENTER"
    ],
    [
        12,
        "04  Keep a private memo.",
        "Empty Enter moves to the yellow Owner field. Your note is not sent to AI.",
        "EMPTY ENTER  /  MEMO  /  ENTER"
    ],
    [
        17,
        "05  Review a candidate, without losing your place.",
        "A choice appears in Agent. Owner keeps focus until you switch back.",
        "EMPTY ENTER TWICE  /  ARROWS  /  ENTER"
    ],
    [
        21,
        "06  Find and reuse only what matters.",
        "Green searches Owner. A title prefix and Tab insert a chosen reference.",
        "EMPTY ENTER  /  SEARCH  /  PREFIX + TAB"
    ],
    [
        26,
        "07  A conversation, not a screen that resets.",
        "The next question joins the same conversation. Your notebook stays beside it.",
        "ANOTHER QUESTION  /  ENTER"
    ],
    [
        30,
        "08  Your pace. Your own notebook.",
        "Scroll the active side while the other keeps its place. No homework list.",
        "PAGE DOWN  /  PAGE UP"
    ]
]



def demo_session():
    sys.path.insert(0, str(ROOT / "core" / "src"))
    from concurrent.futures import Future
    from hashlib import sha256

    # Isolate before importing or constructing anything that could open a profile.
    with tempfile.TemporaryDirectory(prefix="cleanroom-public-demo-",
                                     dir=os.environ.get("CLEANROOM_DEMO_HOME")) as tmp:
        root = Path(tmp).resolve()
        os.environ["VERANTYX_PERSONAL_HOME"] = str(root / "private-profile")
        os.environ["VERANTYX_LANG"] = "en"
        from verantyx.cleanroom_tui import Cleanroom, Question
        from verantyx.cleanroom_owner import make_item, read_notes
        from verantyx.interaction_text import language

        class FixtureCleanroom(Cleanroom):
            def _refresh_model_label(self):
                self.model_label = "SCRIPTED FIXTURE / NO MODEL CALLS"

            async def _refresh(self):
                notes = read_notes(self.root)
                items = list(getattr(self, "fixture_items", []))
                for note in notes:
                    stamp = note.get("created_at", note.get("created", ""))
                    items.append(make_item("note", note["body"], note["body"] + "\n" + stamp,
                                           source_ref="demo-note:" + note["id"]))
                self.view = {
                    "run_id": "DEMO-001", "revision": getattr(self, "fixture_revision", 0),
                    "project_revision": 0, "owner_note_revision": len(notes), "state": {},
                    "owner_items": items, "growth": {}, "live_insights": getattr(self, "fixture_insights", []),
                    "work_pulse": self.live_pulse,
                    "panes": {"agent": "Public interaction fixture. No model, tool, or project execution.",
                              "evidence": "No checks have run. This recording is not an execution receipt.",
                              "notebook": "An isolated, temporary notebook.", "review": "AI proposals are not mastery."},
                }
                self.owner_view = self.view
                self._render()

            def start_action(self, action, **kwargs):
                if action != "work":
                    self.notice("Only recorded interaction fixtures are enabled.")
                    return
                count = getattr(self, "fixture_count", 0) + 1
                self.fixture_count = count
                identity = "fixture-request-" + str(count)
                self.conversation.start(identity, kwargs["request"])
                self.conversation.bind(identity, "DEMO-001" if count == 1 else "DEMO-" + str(count))
                self.pending_request = kwargs["request"]
                if count > 1:
                    group = self.conversation.get(identity)
                    group["side_label"] = "SCRIPTED RESPONSE / NO MODEL CALL"
                    group["side_answer"] = (
                        "Multi-device conflicts remain unverified.\n"
                        "No build, browser check or deployment was run.\n\n"
                        "Your private memo is still in Owner.\n"
                        "The learning note is optional, not an assignment."
                    )
                    self._render()
                    return
                self.selected = "DEMO-001"
                self.busy, self.active_action, self.model_waiting = True, "work", True
                self.started = time.monotonic()
                self.phase = "SCRIPTED WORK / NOT EXECUTION"
                self.fixture_items = [make_item("request", kwargs["request"], kwargs["request"],
                                                source_ref="fixture:request")]
                self.work_task = asyncio.create_task(self.finish_fixture(identity))

            def _live_command(self, value, buffer):
                if value != "L-000001":
                    return super()._live_command(value, buffer)
                group = self.conversation.start("fixture-question", value)
                group["side_label"] = "READ-ONLY EXPLANATION / SCRIPTED"
                group["side_answer"] = (
                    "Keep the original before adding synchronization.\n\n"
                    "If two devices edit one note, an automatic overwrite can lose an edit.\n"
                    "Keep a recoverable local copy; ask the owner which conflict policy fits.\n\n"
                    "Your original task stays in place. You do not have to learn this now.\n"
                    "This explanation is fixture data, not a model result."
                )
                self.live_pulse["remaining_min"] = 4
                self.live_pulse["remaining_max"] = 7
                self.live_pulse["needs_update"] = True
                self.recall.record("agent", value)
                buffer.reset()
                self._render()
                return True

            async def finish_fixture(self, identity):
                await self._refresh()
                await asyncio.sleep(.9)
                group = self.conversation.get(identity)
                group["side_label"] = "SCRIPTED RESPONSE / NO MODEL CALL"
                group["side_answer"] = (
                    "I will separate local storage from synchronization.\n\n"
                    "First, keep a recoverable copy. The owner can choose a conflict policy later.\n\n"
                    "This is a public fixture. No project files have been read or changed."
                )
                await asyncio.sleep(.7)
                self.fixture_items.append(make_item(
                    "learning", "Keep a recoverable copy before sync",
                    "Optional insight. Preserve the original; choose a conflict policy explicitly.",
                    source_ref="fixture:learning"))
                self.fixture_insights = [{"id": "L-000001", "note": {
                    "title": "Keep a recoverable copy before sync",
                    "explanation": "A second device may overwrite an edit.",
                    "next_small_step": "Send L-000001 to ask. Or leave it for next time.",
                }}]
                self.live_pulse = {"available": True, "remaining_min": 3, "remaining_max": 6,
                    "overdue": False, "needs_update": False, "question_running": False,
                    "proposal": {"implementation_minutes": {"minimum": 2, "maximum": 4},
                                 "testing_minutes": {"minimum": 1, "maximum": 2},
                                 "basis": "SCRIPTED ESTIMATE DISPLAY / NOT A LIVE PREDICTION"}}
                self._transfer("agent_to_owner", "fixture-learning", "L-000001", "Optional / not mastery")
                await self._refresh()
                await asyncio.sleep(14.1)
                before, after = "await sync(note)\n", "await saveLocalCopy(note)\nawait sync(note)\n"
                preview = {"run_id": "DEMO-001", "review_id": "fixture-review", "turn": 1,
                    "path": "notes/storage.ts", "baseline": "SCRIPTED_FIXTURE", "directories": [],
                    "before_bytes": len(before), "after_bytes": len(after),
                    "before_sha256": sha256(before.encode()).hexdigest(),
                    "after_sha256": sha256(after.encode()).hexdigest(),
                    "before_final_newline": True, "after_final_newline": True, "binary": False,
                    "diff": "--- a/notes/storage.ts\n+++ b/notes/storage.ts\n@@ candidate only @@\n"
                            "-await sync(note)\n+await saveLocalCopy(note)\n+await sync(note)\n"}
                answer = Future()
                self.model_waiting = False
                self._present_question(Question(
                    "Review the candidate / fixture only",
                    answer,
                    choices=[("once", "Allow once"), ("workspace", "Allow in this workspace"),
                             ("permanent", "Allow permanently"), ("deny", "Deny")],
                    descriptions={key: "Practice only: no file or permission changes. Adoption is a separate action."
                                  for key in ("once", "workspace", "permanent", "deny")},
                    inline=True, preview=preview))
                choice = await asyncio.wrap_future(answer)
                self.conversation.change(preview, "DEMO / " + str(choice))
                self.busy, self.model_waiting = False, False
                self.phase = "FIXTURE READY / NO TESTS EXECUTED"
                self.fixture_items.append(make_item("unknown", "Multi-device conflicts",
                    "Not tested. No evidence or understanding is certified.", source_ref="fixture:unknown"))
                await self._refresh()

        (root / ".verantyx").mkdir(mode=0o700)
        conf = {"project": {"name": "offline-notes / PUBLIC DEMO", "id": "public-demo"},
                "ui": {"locale": "en"}}

        async def run_fixture():
            ui = FixtureCleanroom(root, conf)
            # The real rendering and key handlers remain. Replace only external work
            # and ledger polling with the disclosed fixture, never a real project.
            if ui.reader is not None:
                ui.reader.close()
            ui.reader = None
            await ui._refresh()
            await ui.run()

        with language(conf):
            asyncio.run(run_fixture())


def record(output):
    import pyte
    from PIL import Image, ImageDraw, ImageFont

    output.mkdir(parents=True, exist_ok=True)
    master, slave = pty.openpty()
    fcntl.ioctl(slave, __import__("termios").TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
    isolated = tempfile.TemporaryDirectory(prefix="cleanroom-recording-")
    child_python = Path(sys.executable)
    env = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor",
               PROMPT_TOOLKIT_NO_CPR="1", PYTHONPATH=str(ROOT / "core" / "src"),
               CLEANROOM_DEMO_HOME=str(Path(isolated.name).resolve()), VERANTYX_LANG="en")
    env.pop("NO_COLOR", None)
    env.pop("VERANTYX_REDUCE_MOTION", None)
    process = subprocess.Popen([str(child_python), str(Path(__file__).resolve()), "--session"],
                               stdin=slave, stdout=slave, stderr=slave, cwd=ROOT, env=env, close_fds=True)
    os.close(slave)
    screen = pyte.Screen(COLS, ROWS)
    stream = pyte.Stream(screen)
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    mono_paths = [os.environ.get("CLEANROOM_DEMO_FONT", ""), "/System/Library/Fonts/Menlo.ttc",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]
    font = next((ImageFont.truetype(p, 14) for p in mono_paths if p and Path(p).is_file()), ImageFont.load_default())
    cjk_path = Path("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc")
    cjk = ImageFont.truetype(str(cjk_path), 14) if cjk_path.is_file() else font
    title_font = next((ImageFont.truetype(p, 25) for p in mono_paths if p and Path(p).is_file()), font)
    caption_font = next((ImageFont.truetype(p, 14) for p in mono_paths if p and Path(p).is_file()), font)
    cw, ch, pad, top = 9, 22, 20, 124
    colors = {"default": "#e9eee8", "black": "#182c35", "white": "#e9eee8",
              "red": "#ec918b", "green": "#b8cdad", "brown": "#dfc586",
              "blue": "#92b9cf", "magenta": "#c6afc7", "cyan": "#aad2d1",
              "brightblack": "#879c9f", "brightwhite": "#ffffff"}
    def color(value, default):
        if value == "default":
            return default
        return colors.get(value, "#" + value if len(value) == 6 else default)
    tiles = {}
    def frame(elapsed):
        im = Image.new("RGB", (COLS*cw+pad*2, ROWS*ch+top+54), "#182c35")
        draw = ImageDraw.Draw(im)
        _, title, caption, keys = next(scene for scene in reversed(SCENES) if elapsed >= scene[0])
        draw.text((pad, 10), "c.  cleanroom  /  ENGLISH CLI  /  SCRIPTED WORK DATA  /  NO MODEL CALLS", font=font, fill="#b4cbd2")
        draw.text((pad, 34), title, font=title_font, fill="#f4f0e5")
        draw.text((pad, 75), caption, font=caption_font, fill="#c6d9db")
        draw.line((pad, 110, im.width-pad, 110), fill="#547889")
        draw.text((pad, im.height-35), keys, font=caption_font, fill="#e7cd8f")
        draw.text((im.width-316, im.height-34), "REAL CONTROLS / FIXTURE RESULTS", font=font, fill="#b4cbd2")
        for y in range(ROWS):
            for x in range(COLS):
                cell = screen.buffer[y][x]
                if not cell.data:
                    continue
                fg, bg = color(cell.fg, "#e9eee8"), color(cell.bg, "#182c35")
                if cell.reverse:
                    fg, bg = bg, fg
                ident = (cell.data, fg, bg, cell.bold, cell.underscore)
                tile = tiles.get(ident)
                if tile is None:
                    wide = any(unicodedata.east_asian_width(a) in ("W", "F") for a in cell.data)
                    tile = Image.new("RGB", (cw*(2 if wide else 1), ch), bg)
                    td = ImageDraw.Draw(tile)
                    td.text((0, 1), cell.data, font=cjk if wide else font, fill=fg)
                    if cell.underscore:
                        td.line((0, ch-3, tile.width, ch-3), fill=fg)
                    tiles[ident] = tile
                im.paste(tile, (pad+x*cw, top+y*ch))
        return im
    actions = []
    def type_at(at, text):
        for n, char in enumerate(text):
            actions.append((at+n*.025, char.encode()))
    type_at(.8, "Build an offline notes app")
    actions += [(1.8, b"\r")]
    type_at(8.15, "L-000001")
    actions += [(8.65, b"\r"), (12.15, b"\r")]
    type_at(12.55, "Offline first: keep my notes on my device.")
    actions += [(14.0, b"\r"), (18.6, b"\r"), (19.1, b"\r"),
                (19.65, b"\x1b[B"), (20.25, b"\r"),
                (21.5, b"\r"), (22.0, b"\r")]
    type_at(22.25, "Offline")
    actions += [(23.45, b"\x15"), (23.85, b"\r")]
    type_at(24.15, "Keep")
    actions += [(24.7, b"\t"), (25.5, b"\x03")]
    type_at(26.15, "What remains unverified?")
    actions += [(27.0, b"\r"), (30.3, b"\x1b[6~"), (31.8, b"\x1b[5~"),
                (33.6, b"\x04")]
    actions.sort(key=lambda a:a[0])
    frames, records, frame_times = [], [], []
    start = time.monotonic()
    index = 0
    next_frame = 0.0
    poster = None
    try:
        while time.monotonic()-start < DURATION:
            elapsed = time.monotonic()-start
            while index < len(actions) and elapsed >= actions[index][0]:
                os.write(master, actions[index][1])
                index += 1
            if select.select([master], [], [], .02)[0]:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    break
                if not data:
                    break
                value = decoder.decode(data)
                records.append([round(elapsed, 3), "o", value])
                stream.feed(value)
            if elapsed >= next_frame:
                image = frame(elapsed)
                if 6.0 <= elapsed < 6.5:
                    poster = image.copy()
                frames.append(image.quantize(colors=96))
                frame_times.append(elapsed)
                next_frame = elapsed + .2
            if process.poll() is not None:
                break
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)
        os.close(master)
        isolated.cleanup()
    if time.monotonic() - start < DURATION - 2:
        tail = "".join(row[2] for row in records)[-4000:]
        raise RuntimeError("CLI recording ended before the planned walkthrough.\n" + tail)
    if not frames:
        raise RuntimeError("The CLI produced no recording frames.")
    gif = output / "cli-demo.gif"
    # Preserve real elapsed timing instead of speeding up when frame drawing is slow.
    finish = min(DURATION, time.monotonic() - start)
    delays = [max(20, round((end - begin) * 100) * 10)
              for begin, end in zip(frame_times, [*frame_times[1:], finish])]
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=delays, loop=0, optimize=False)
    (poster or frames[min(30, len(frames)-1)].convert("RGB")).save(output / "cli-demo-poster.png")
    # This trace contains only the public fixture, never real project history.
    with (output / "cli-demo.cast").open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"version":2,"width":COLS,"height":ROWS,"title":"Cleanroom English walkthrough / scripted fixtures","env":{"LANG":"en","TERM":"xterm-256color"}})+"\n")
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=True)+"\n")
    subprocess.run(["ffmpeg","-y","-loglevel","error","-i",str(gif),"-vf","pad=ceil(iw/2)*2:ceil(ih/2)*2,fps=10",
                    "-c:v","libx264","-pix_fmt","yuv420p","-movflags","+faststart",str(output/"cli-demo.mp4")], check=True)
    print(json.dumps({"kind":"scripted-cli-demonstration","model_calls":0,"frames":len(frames),
                      "locale":"en","duration_limit_seconds":DURATION,"output":str(output),"gif_bytes":gif.stat().st_size}))


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--session", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT/"public"/"cleanroom")
    args=parser.parse_args()
    if args.session:
        demo_session()
    else:
        record(args.output)
