# English CLI walkthrough

The README and both website source trees use a recording of the actual Python Cleanroom terminal UI, set to English. The recording runs in a pseudoterminal and sends the real keyboard events. Only the external work and ledger-polling inputs are replaced with labelled, public fixtures.

**It is an interaction demonstration, not a live-model benchmark, a test receipt or a claim of human understanding.** No model, API, shell work tool or real project is invoked by the fixture. Candidate diffs and time ranges are examples. Choosing a permission in the recording does not create a real permission grant.

## What the 34-second recording shows

| Time | Interaction |
|---|---|
| 0s | Ask normally. Your request has a background. The answer stays separate from system activity. |
| 4s | Understanding does not wait for the finish. A small optional note arrives during work, with a stable L-number. |
| 8s | Ask about one insight without replacing the work. Send L-000001. This recorded explanation is scripted; no model is called. |
| 12s | Keep a private memo. Empty Enter moves to the yellow Owner field. Your note is not sent to AI. |
| 17s | Review a candidate, without losing your place. A choice appears in Agent. Owner keeps focus until you switch back. |
| 21s | Find and reuse only what matters. Green searches Owner. A title prefix and Tab insert a chosen reference. |
| 26s | A conversation, not a screen that resets. The next question joins the same conversation. Your notebook stays beside it. |
| 30s | Your pace. Your own notebook. Scroll the active side while the other keeps its place. No homework list. |

The side-question answer is scripted, not a model call. The ordinary memo key handler writes only to an isolated temporary profile. It does not access the user's personal notebook. All fixture storage is removed when recording ends.

## Reproduce

Run from the repository root on macOS or Linux, with Python 3.11+, `uv` and `ffmpeg` available:

~~~sh
uv run --with pillow --with pyte --with ./core python scripts/record-cli-demo.py
~~~

Alternatively, install the CLI and optional recording libraries into a dedicated environment:

~~~sh
python3 -m venv .demo-venv
source .demo-venv/bin/activate
python -m pip install -e ./core pillow pyte
python scripts/record-cli-demo.py
~~~

This recorder uses POSIX pseudoterminal APIs. On Windows, run it inside a suitable Linux/WSL environment; native Windows capture is not claimed.

`CLEANROOM_DEMO_FONT=/absolute/path/to/a/monospace.ttf` selects another font. Menlo is preferred on macOS; DejaVu Sans Mono is the Linux fallback. The output uses 140 columns by 38 rows, 14px terminal glyphs and separate chapter captions so the purpose of each action is visible.

## Outputs

- `public/cleanroom/cli-demo.gif`: README and optional website GIF.
- `public/cleanroom/cli-demo.mp4`: website video with pause/seek controls.
- `public/cleanroom/cli-demo-poster.png`: static, reduced-motion alternative.
- `public/cleanroom/cli-demo.cast`: public fixture terminal output, not private project history.
- `public/cleanroom/cli-demo.{en,ja,zh-Hans,ko,es}.vtt`: translated chapter captions.

The English screen is the same for all caption languages. Both website copies embed the same assets. The website opens the animated GIF only when requested and also offers the controllable MP4 and static image. GitHub clients control README GIF playback; the static alternative is linked directly below it.

An early child-process exit aborts generation rather than publishing a partial recording as a completed walkthrough. Successful recording alone does not establish CLI regression, provider, deployment, keyboard-compatibility or accessibility coverage.

## 日本語

英語設定の実CLIへキー操作を送り、画面をプログラムで収録します。モデル処理と作業データだけを明示した説明用データに置き換えます。L番号への解説・予想時間・変更候補は例であり、実モデルの応答やテスト合格を示しません。

個人用DBとワークスペースは一時ディレクトリに隔離し、実際のプロフィール・認証情報・作業台帳を動画へ含めません。メモ入力には通常のUI処理を使いますが、保存先は一時プロフィールだけです。READMEとWebのGIF、再生操作付き動画、静止画を同じ収録から作ります。全体の回帰テストや本番配信とは別の工程です。
