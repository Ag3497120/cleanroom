# Programmed CLI recording / CLIのプログラム録画

The GIF under the README logo is produced by the real Python Cleanroom TUI renderer.
The work backend and ledger read are replaced by explicit public fixtures in the recording driver.
Input, empty-Enter cycling, local memo storage, search, reference completion, pane scrolling and the transfer animation use the actual CLI UI.

It is not a real-model evaluation, a sandbox test, or proof that a project was implemented.
No credentials, personal profile, real workspace files or prior conversations are read.
The recording has a permanent fixture label. The fixture config explicitly sets `ui.locale` to `en`.
English chapter captions and key hints explain each action. They describe the interaction, not model performance.

## Reproduce

Install the CLI source first as described in README. For recording only, install ffmpeg and uv.
Capture dependencies do not become runtime CLI dependencies.

```sh
uv run --with pillow --with pyte --with ./core python scripts/record-cli-demo.py
```

Outputs under public/cleanroom:

- cli-demo.gif: README animation
- cli-demo.mp4: browser video with explicit controls
- cli-demo-poster.png: static, reduced-motion-friendly poster
- cli-demo.cast: public ANSI trace

macOS uses system Menlo and Hiragino fonts. On Linux, provide a suitable monospace font through CLEANROOM_DEMO_FONT; CJK fallback may require adapting the font path.
The scripted process uses a fresh temporary directory which is removed after capture.
It never uses a real project as its fixture.

## What is shown in under 30 seconds

1. A normal English Agent request, visible in the opening seconds.
2. Fixture work and an Owner learning proposal.
3. Empty Enter to the yellow memo; a real local note is saved in the temporary fixture.
4. Empty Enter to the green search field.
5. Return to Agent; type an Owner prefix and press Tab.
6. Page scrolling in the active pane; the other pane's viewport is independent.
7. The existing F2 menu: profile, journal, skills and next-time options.

The recorder uses the same Python interpreter as its launcher, an isolated temporary
workspace, and public fixture data. No real-model call is made. The permanent caption
remains in GIF, MP4 and poster. Timed VTT tracks provide five-language captions.

実モデルの結果と誤解させないため、録画内・README・Webの横の説明にデモデータであることを表示します。
実プロジェクトや私的なノートをこの録画に混ぜないでください。
