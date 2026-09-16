# Release validation and MVP scope

Date: 2026-09-17 (Japan Standard Time)

This document describes the source preview accompanying this change. It is not
a certification that the twenty live project scenarios have all passed, that
a person has mastered a skill, or that a configured external process is isolated.

## English

### Confirmed in this release

| Check | Result | Boundary |
| --- | --- | --- |
| Python core suite | 1,005 passed in the full run; the one missing-dependency MCP case passed on retry; 10 skipped; 862 subtests passed | macOS, Python 3.11; skipped cases are not passes |
| Cross native tests | 6 passed | Locally built runtime, pinned only for the test environment |
| Web type checking, lint and Node tests | Passed; 9 Node tests | Static application and terminal-input contracts |
| Browser interactions | 14 passed | Scripted rehearsal in Chrome, not a live agent benchmark |
| CLI entry points | 8 passed | Fresh temporary workspace and personal database; no AI calls |
| Real subscription-model smoke test | Work SUCCEEDED; Reflection PROPOSED | One small task using official Codex CLI and gpt-5.6-luna, low reasoning |
| Main and marketing builds | Passed | Static exports; deployment health is checked separately |
| New site appearance | Desktop, 390px layout, light/dark and reduced motion checked | No full WCAG conformance claim |

The full suite initially lacked the optional MCP package in the isolated release environment. After installing core[mcp], all 30 notebook-connection and Codex tests passed. These overlap the full-suite counts; they are not thirty additional independent cases. The 10 skips comprise two external Vera MCP integration cases and eight optional historical-fixture cases. CI now installs the MCP extra and runs these regression modules.

The browser checks cover Shift+Enter, continuous conversation, draft/history,
empty-Enter pane switching, private memos, search, reference completion,
temporary chat, non-focus-stealing change review, arrow-key approval,
independent Agent/Owner sessions, five languages and narrow screens.

CLI checks cover setup, version, status, tutorial, new, cleanroom, models and
command discovery. The CLI was also recorded through a real terminal with
scripted work data for the English walkthrough. That GIF is explicitly a
demonstration, not evidence of model performance.

### What the real-model check established

The model produced candidate answer.json and README.md. Two candidate writes
were recorded. A separate check verified the artifact hashes, that /answer
was the number 43 rather than a string or object, and that the source workspace
had not received these files.

The work result correctly remained NOT_VERIFIED: the model had not run a
test. The additional release check did not silently promote that work's
evidence state. Reflection was saved independently as a source-linked proposal,
not as a confirmed human decision or proof of learning.

There were three successful provider calls for this one task, not twenty
projects or twenty model runs. An earlier smoke attempt used an incomplete
test adapter without initializing its usage database. It failed before a
model call; the corrected setup is the successful run reported above.

### What remains outside this release claim

- The complete twenty-project, live-model evaluation has not been rerun here.
- Fresh-account onboarding on another Mac and sustained real-project usage need more user evaluation.
- Windows/WSL2, Linux, remote Ollama/Qwen, MCP integrations, Obsidian and external sandboxes were not all end-to-end revalidated in this release.
- A model-generated learning suggestion is not evidence that it is useful to a particular person or that the person learned it.
- The browser workspace is an in-memory rehearsal. Its optional explicit AI connection is not the full local filesystem agent.
- Long-term usefulness, recovery under extended workloads and the quality of learning suggestions still need field feedback.

This supports publishing an **early MVP / developer preview**, with the tested
scope visible. It does not support advertising an all-scenarios-passed,
production-hardened replacement for mature coding agents.

### Reproducing the checks

From the repository root, with Python 3.11+ and CMake installed:

```sh
python -m pip install -e './core[mcp]' pytest
cmake -S cross -B cross/build -DCMAKE_BUILD_TYPE=Release
cmake --build cross/build -j 2
python scripts/pin-cross-runtime.py
export VERANTYX_PERSONAL_HOME="$(mktemp -d)/profile"
export VERANTYX_PRECEDENT="$PWD/execution"
export VERANTYX_CROSS="$PWD/cross/build/cross"
export PYTHONPATH="$PWD/core/src:$PWD/core/tests"
python -m pytest core/tests -q
npm run typecheck
npm run lint
npm test
```

The runtime pin is machine-build metadata, not a public release artifact.
Keep test projects, profiles, model credentials and model transcripts out of
commits.

For the browser interaction checks, serve the built preview and marketing
site locally, use an installed Playwright module and an installed Chrome, and
run:

```sh
CLEANROOM_BROWSER_MODULE=/absolute/path/to/playwright/index.mjs \
CLEANROOM_PREVIEW_URL=http://127.0.0.1:8793/ \
CLEANROOM_SITE_URL=http://127.0.0.1:8794/ \
node scripts/test-playground.mjs
```

The test makes no model calls. See [the recording recipe](DEMO_RECORDING.md)
for the separate CLI GIF/MP4 workflow.

## 日本語

### 公開判断

今回の確認範囲では、**初期MVP・開発者向けプレビューとしての公開**を想定しています。
「20課題の実モデル検証をすべて完了した」「本人の習得を証明した」
「本番運用の安全性を保証した」という意味ではありません。

Pythonの通しテストでは1,005件と862件のサブテストが成功し、10件がスキップされました。
MCP依存の未導入で失敗した1件は、依存追加後に関連30件とともに再実行して成功しました。
この30件には通し検査と重なるものがあり、単純に合算していません。
スキップは外部Vera MCP連携2件と、任意の過去版フィクスチャ8件です。これとは別に、Cross 6件、
WebのNodeテスト9件、ブラウザ操作14項目、独立したCLI入口8項目を確認しました。
スキップした検査を合格へ数え替えていません。

Codexサブスクの gpt-5.6-luna / low で小さな1課題を実行し、
候補2ファイルの保存と、出典付きの整理候補の保存を確認しました。
候補のハッシュ、数値43の型と値、本体へ書き込まれていないことは別途検査しました。
モデル自身がテストを実行していない事実は変更せず、作業の証拠状態は
NOT_VERIFIED のままです。今回のテストに先立つ接続失敗は、
検証用設定の使用量DBを初期化していなかったことによるもので、モデル呼び出し前でした。

今回のサイト変更は文章や機能を削らず、静かな入室フレーム、淡い室内光、
読みやすい作業台を加えたものです。ライト・ダーク、狭い画面、
動きを減らす設定を確認しています。英語GIFは実CLIを台本付きのデータで
操作した記録であり、実モデルの成功動画ではありません。

別Macでの新規アカウント導入、長時間利用、20課題全件、外部連携の全組合せは、
今回の確認だけでは完了扱いにしていません。学習提案の有用性や、
使い続けることで本人の経験が積み重なるかは、実利用を通して評価を続ける対象です。

**仕事の成果、AIの整理候補、人間の判断・理解を混ぜないこと。**
この境界を残したまま、試せるものから公開して育てるためのリリースです。
