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
COLS, ROWS = 140, 30
DURATION = 28
SCENES = [
    (0, "01  Ask normally.", "One request. Agent works on the left; your notebook stays on the right.", "TYPE A REQUEST  /  ENTER"),
    (2.8, "02  Keep an insight, not a homework list.", "An explanation arrives in Owner while work proceeds. Learning remains optional.", "AGENT  >  OWNER"),
    (7, "03  A note just for you.", "Empty Enter opens the yellow memo. Saving it does not send it to AI.", "EMPTY ENTER  /  TYPE  /  ENTER"),
    (11.3, "04  Find the context you want.", "Empty Enter switches to green search. Only your local Owner records are searched.", "EMPTY ENTER  /  SEARCH"),
    (15, "05  Reuse only the part you choose.", "Type the first letters, choose with the arrow keys, then insert an exact reference.", "PREFIX  /  ARROWS  /  TAB"),
    (19, "06  Read one side without losing the other.", "Page keys move the active pane. The other pane keeps its place.", "PAGE DOWN  /  PAGE UP"),
    (23, "07  Your notebook has room to grow.", "Open the menu for your profile, journal, skills and next-time bookmarks.", "F2  /  ARROWS  /  ENTER"),
]



def demo_session():
    sys.path.insert(0, str(ROOT / "core" / "src"))
    from verantyx.cleanroom_tui import Cleanroom
    from verantyx.cleanroom_owner import make_item, read_notes

    class FixtureCleanroom(Cleanroom):
        async def _refresh(self):
            items = list(getattr(self, "fixture_items", []))
            for note in read_notes(self.root):
                items.append(make_item("note", note["body"], note["body"], source_ref="demo-note:" + note["id"]))
            self.view = {
                "run_id": "DEMO-001", "revision": len(items), "project_revision": len(items),
                "owner_note_revision": len(read_notes(self.root)), "state": {},
                "owner_items": items, "growth": {},
                "panes": {"agent": getattr(self, "fixture_answer",
                           "PUBLIC FIXTURE / NO MODEL CALLS\n\nAsk for work here.\nKeep your decisions and notes in Owner.\n\nThe recording uses the actual CLI controls\nand a scripted work result."),
                          "evidence": "No checks have been executed in this fixture.",
                          "notebook": "Fixture notebook; no user history.",
                          "review": "AI proposals are not human decisions."},
            }
            self._render()

        def start_action(self, action, **kwargs):
            if action != "work":
                self.notice("This fixture demonstrates input and navigation only.")
                return
            self.pending_request = kwargs["request"]
            self.busy = True
            self.phase = "DEMO / scripted work"
            self.fixture_items = [make_item("request", kwargs["request"], kwargs["request"], source_ref="fixture:request")]
            self.work_task = asyncio.create_task(self.finish_fixture())

        async def finish_fixture(self):
            await self._refresh()
            await asyncio.sleep(.9)
            self.fixture_answer = (
                "SCRIPTED WORK RESULT / NOT EXECUTED\n\n"
                "Offline notes example\n\n"
                "A local storage approach is proposed.\n"
                "No source tree or network was accessed.\n\n"
                "Keeping with you:\n"
                "  - Purpose and design choices\n"
                "  - AI assumptions, separately labelled\n"
                "  - A small optional learning bookmark\n\n"
                "Validation has NOT run.\n"
                "Human understanding is NOT certified.\n\n"
                + "\n".join("Fixture detail %02d: provenance remains a reference." % i for i in range(1, 17))
            )
            self.fixture_items += [
                make_item("assumption", "One device for now", "AI fixture assumption, not a human decision.", source_ref="fixture:assumption"),
                make_item("learning", "Offline storage", "Optional insight from this fixture: keep a recoverable copy before sync. Next time is a bookmark, not homework.", source_ref="fixture:learning"),
                make_item("unknown", "Multi-device conflicts", "Not checked. No real test receipt is claimed.", source_ref="fixture:unknown"),
            ]
            self.busy = False
            self.phase = "DEMO / optional insight"
            self._transfer("agent_to_owner", "fixture-learning", "Offline storage", "AI proposal / not mastery")
            await self._refresh()

    with tempfile.TemporaryDirectory(prefix="cleanroom-public-demo-") as tmp:
        (Path(tmp) / ".verantyx").mkdir(mode=0o700)
        conf = {"project": {"name": "offline-notes / DEMO FIXTURE", "id": "public-demo"}, "ui": {"locale": "en"}}
        asyncio.run(FixtureCleanroom(tmp, conf).run())


def record(output):
    import pyte
    from PIL import Image, ImageDraw, ImageFont

    output.mkdir(parents=True, exist_ok=True)
    master, slave = pty.openpty()
    fcntl.ioctl(slave, __import__("termios").TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
    child_python = Path(sys.executable)
    env = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor",
               PROMPT_TOOLKIT_NO_CPR="1", PYTHONPATH=str(ROOT / "core" / "src"))
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
    font = next((ImageFont.truetype(p, 13) for p in mono_paths if p and Path(p).is_file()), ImageFont.load_default())
    cjk_path = Path("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc")
    cjk = ImageFont.truetype(str(cjk_path), 13) if cjk_path.is_file() else font
    title_font = next((ImageFont.truetype(p, 25) for p in mono_paths if p and Path(p).is_file()), font)
    caption_font = next((ImageFont.truetype(p, 14) for p in mono_paths if p and Path(p).is_file()), font)
    cw, ch, pad, top = 8, 19, 20, 124
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
    actions += [(1.8,b"\r"),(7.1,b"\r")]
    type_at(7.45, "Offline first: keep my notes on my device.")
    actions += [(9.0,b"\r"),(11.4,b"\r")]
    type_at(11.75, "Offline")
    actions += [(14.5,b"\x15"),(14.8,b"\r")]
    type_at(15.2, "Offline")
    actions += [(15.9,b"\x1b[B"),(16.1,b"\x1b[B"),(16.5,b"\t"),
                (18.3,b"\x03"),(19.5,b"\x1b[6~"),(21.1,b"\x1b[5~"),
                (23.1,b"\x1bOQ"),(25.8,b"\x1b"),(27.2,b"\x04")]
    actions.sort(key=lambda a:a[0])
    frames, records = [], []
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
                if 5.0 <= elapsed < 5.5:
                    poster = image.copy()
                frames.append(image.quantize(colors=96))
                next_frame = elapsed + .2
            if process.poll() is not None:
                break
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)
        os.close(master)
    if not frames:
        raise RuntimeError("The CLI produced no recording frames.")
    gif = output / "cli-demo.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=200, loop=0, optimize=False)
    (poster or frames[min(30, len(frames)-1)].convert("RGB")).save(output / "cli-demo-poster.png")
    # This trace contains only the public fixture, never real project history.
    with (output / "cli-demo.cast").open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"version":2,"width":COLS,"height":ROWS,"title":"Cleanroom English walkthrough / scripted fixtures","env":{"LANG":"en","TERM":"xterm-256color"}})+"\n")
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=True)+"\n")
    subprocess.run(["ffmpeg","-y","-loglevel","error","-i",str(gif),"-vf","pad=ceil(iw/2)*2:ceil(ih/2)*2",
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
