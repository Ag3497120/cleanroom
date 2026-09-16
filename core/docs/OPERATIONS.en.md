# Cleanroom operating guide

[English](OPERATIONS.en.md) · [日本語](OPERATIONS.ja.md) · [简体中文](OPERATIONS.zh-Hans.md) · [한국어](OPERATIONS.ko.md) · [Español](OPERATIONS.es.md) · [README](../../README.md)

Cleanroom is a collaborative development workspace powered by the Vera Kernel. AI can do most of the implementation while your purpose, decisions, understanding, verification methods, and experience stay with you.

## Current interaction: a short route through the guide

Start with `verantyx setup`: a new installation starts in English, then guides and choices follow the language you select. The first-exit tutorial is simulated. Type `verantyx` inside it to leave practice and begin the real CLI, or use `/done` to leave the practice view. The terminal-size warning does not block you.

At 120 columns × 28 rows, the CLI uses two equal-width panes; at 80 × 48 it can stack them. Smaller windows show the active pane without blocking work. Empty Enter still cycles Agent → Memo → Search. Terminal font size belongs to your terminal application; the browser demo has its own text-size controls.

### While work continues

You do not have to wait for the project to be finished.

- **Ask and keep going.** The Agent pane is a continuous conversation: shaded requests, plain answers, and a separate activity area. A spinner and a gentle input pulse show work in progress.
- **Keep one useful explanation.** At safe work boundaries, eligible implementation-time notes can appear in Owner, within your chosen suggestion budget. Send an ID such as `L-000001` to ask about that note without replacing the implementation task. A long-running tool finishes its current call first.
- **Treat time as an estimate.** When the AI supplies one, implementation and testing have separate ranges. Questions add measured time; the next work turn can revise the estimate. Missing or outdated estimates remain labelled, not invented.
- **Choose the pace.** Keep a memo, refer back, delegate, or leave it for next time. Asking, skipping, importing a skill or granting permission never certifies understanding.

`/verantyx new` in Agent starts a new Agent conversation, not a new Owner notebook. Owner Cleanrooms have their own names and confirmation steps. Candidate edits offer **once / this workspace / permanent / deny**; these choices are not permission to publish or adopt into the main project.

[Live learning, sessions, permissions and storage](../../docs/live-learning-and-sessions.md) · [Conversation and change review](../../docs/conversation-and-change-review.md)

| Input | Meaning |
|---|---|
| `verantyx new [name]` | Start a separate Agent conversation; Owner is retained |
| `verantyx new --owner [name]` | Create an Owner Cleanroom from the shell; confirm first |
| `verantyx cleanroom [name]` | List named Owner Cleanrooms; switching requires confirmation |
| `verantyx compact` | Ask AI to compact source-backed context without deleting originals |
| `/insights` | Open recent implementation-time explanations |
| `L-000001` | Ask about the selected note at a safe work boundary |
| `/approvals` | Review current candidate-edit permissions |
| `/queue` | Choose queue or safe-step steering while a task is running |

Owner memos have timestamps and are kept in the private local SQLite store. The TUI loads pages, rather than rendering the whole archive at once; local search queries the stored notes. Original work events remain in the project ledger. AI summaries are an additional, source-backed view, not a replacement for original records. This reduces hot-path memory use, but does not claim that every full-ledger replay or export has constant memory cost.

The browser rehearsal mirrors input switching, references, private memos, continuous messages and example review choices. It keeps data in this tab, not in the CLI database. Its scripted estimates and results are not live work or evidence. Subscription execution, actual compaction, durable sessions and project edits belong to the local CLI; Ask your AI is a separate explicit connection.

[Current controls](../../docs/two-pane-interaction.md) · [Live learning and sessions](../../docs/live-learning-and-sessions.md) · [Recorded English walkthrough](../../docs/DEMO_RECORDING.md)


## 01 / Start locally

Use a new Python 3.11+ environment on each computer. Linux is a source installation path, not a claim of testing every distribution. Windows instructions refer to WSL2, not native Windows. Move to your project after activating the installation environment.

```sh
git clone https://github.com/Ag3497120/cleanroom.git cleanroom
cd cleanroom
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./core
verantyx setup
verantyx
```

```sh
source /absolute/path/to/cleanroom/.venv/bin/activate
cd /absolute/path/to/your-project
verantyx
```

## 02 / Split CLI: Agent on the left, Owner on the right

Ask in the lower-left Agent field. No new command language to learn.

| English | Key |
|---|---|
| Request work | Agent: Enter |
| Local memo | Empty Enter → MEMO |
| Local search | Empty Enter → SEARCH |
| Reference a record | 2+ characters → ↑/↓ → Tab |
| Open actions | F2 |
| Scroll | F3 |
| Learning view | F4 |
| Split view | Alt+0 |
| Newline | Shift+Enter where the terminal distinguishes it; fallback: Ctrl+J / Alt+Enter |
| Close | Ctrl+D |

Empty Enter moves to the yellow Owner memo, then the green Owner search, then back to Agent.

Type at least the first two characters of an Owner item, choose with Up/Down, and press Tab to insert that reference. Enter selects an open suggestion, rather than sending the task.

At 120 columns × 28 rows, the CLI uses two equal-width panes; at 80 × 48 it can stack them. Smaller windows show the active pane without blocking work. Empty Enter still cycles Agent → Memo → Search. Terminal font size belongs to your terminal application; the browser demo has its own text-size controls.

```sh
VERANTYX_REDUCE_MOTION=1 verantyx
NO_COLOR=1 verantyx
verantyx --plain
verantyx watch
```

Ctrl+C: clear the current draft / cancel the current question; with no draft, request closure. It is not a guarantee of forcibly stopping an external program. Esc closes a menu or suggestion without accepting it.

## 03 / Commands

Setup starts in English on a fresh installation. Choose a language to update the supported guides and choices. Provider/model identifiers and raw tool output retain their original language. Requests may be written in your own language. The live parser is authoritative: `verantyx --help` and `verantyx commands NAME`.

| Command | English / scope |
|---|---|
| `verantyx` | Open workspace / 作業を始める / 开始工作 / 작업 시작 / Abrir espacio |
| `verantyx commands` | List actual registered commands / 実装済みコマンド一覧 / 命令列表 / 명령 목록 / Catálogo de comandos |
| `verantyx commands setup --json` | Read command details / 詳細 / 详情 / 상세 / Detalles |
| `verantyx setup accounts` | ChatGPT/Codex, Claude Code, API, local |
| `verantyx setup models` | Work / reflection |
| `verantyx setup roles` | Parent / child model roles |
| `verantyx setup language` | en / ja / zh-Hans / ko / es |
| `verantyx setup profile` | Voluntary experience / 任意の経験 / 自愿填写经验 / 자율 경험 기록 / Experiencia voluntaria |
| `verantyx setup pace` | Suggestion load / 提案の負荷 / 建议量 / 제안량 / Carga de sugerencias |
| `verantyx my-skills` | Your choices / 本人の選択 / 本人选择 / 나의 선택 / Tus elecciones |
| `verantyx my-learning` | Notes captured during work / 実装中の記録 / 实现时记录 / 구현 중 기록 / Notas durante el trabajo |
| `verantyx my-journal` | Journal / 日記 / 日记 / 일지 / Diario |
| `verantyx web --no-open` | Local Atlas URL / ローカルAtlas / 本地Atlas / 로컬 Atlas / Atlas local |
| `verantyx setup notebook` | Obsidian / MCP / skill imports |
| `verantyx setup harness` | External work adapter |
| `verantyx setup sandbox` | OSS isolation adapter |
| `verantyx toolbox status` | MCP tools |
| `verantyx watch` | Read-only / 閲覧専用 / 只读 / 읽기 전용 / Solo lectura |

## 04 / Models

Choose Codex or Claude through the official local CLI login. Do not paste subscription tokens into a website. API usage is separate from subscription access. Local model connections require your running endpoint and an available model. Work and reflection may differ; reflection may be disabled.

```sh
verantyx setup accounts
verantyx setup codex
verantyx setup claude
verantyx setup models
verantyx setup roles
verantyx settings --show
```

## 05 / My profile · My pace · My skills

F2 > My profile accepts a short self-description or Skip. F2 > My pace limits suggestion weight and number. My skills distinguishes AI procedure drafts, what you want to explore next, and explanations/application examples you explicitly record. Nothing requires filling an entire board. Asking the AI to push code does not imply ignorance of Git.

Work results and AI reflection are independent. Different models can offer different interpretations without erasing previous ones. AI procedure drafts are not proof that you have learned a skill. Skipping, delegating, or asking for help is not an ability judgment.

```sh
verantyx setup profile
verantyx setup pace
verantyx my-skills
verantyx my-skills quiet --scope TODAY
verantyx my-journal
verantyx my-learning
```

## 06 / Owner · Privacy

Owner memos stay local by default. Choosing a reference inserts only that reference into your request. Sending it still follows the work flow's outbound scope. Notes, reference choices, and learning preferences never grant execution permissions.

Owner notes and search do not call AI. Explicitly inserted references enter the request's send scope. Private project and personal records are not meant for public GitHub commits.

## 07 / My Atlas

`verantyx web` opens the private My Atlas server on loopback. Keep the terminal running. It shows recorded experience, not scores or missing abilities. Notes shared across projects belong to the same OS user's personal store. There is no automatic cross-Mac sync.

```sh
verantyx web
verantyx web --no-open
verantyx --lang en web
```

The actual view follows its supported language catalogue; untranslated items may fall back. These guides do not claim complete five-language runtime localization.

## 08 / Work · Reflection

If a path is outside the workspace, do not bypass the boundary. Use an explicitly authorized scope or another project. If reflection fails, keep the work result and use `verantyx organize RUN_ID` later. Inspect old interpretations with `verantyx perspectives RUN_ID`.

## 09 / Obsidian · MCP · Harness

F2 > Notebook bridge connects an explicitly selected Obsidian vault. Imports remain provenance-bearing drafts, not proof of learning or automatic permission to execute. MCP tools and external harnesses require explicit configuration. A configured sandbox is not a certification of isolation.

[Connections](NOTEBOOK_CONNECTIONS.en.md) · [日本語](NOTEBOOK_CONNECTIONS.ja.md) · [Sandbox boundary](SANDBOX_BACKENDS.en.md)

## 10 / Web preview

The public Pages playground and the GIF use fixtures. They do not call AI, alter a project, authenticate a subscription, or certify successful checks. The optional existing gateway is a separate service; it requires configuration and owner approval. A public website cannot safely inherit your private Codex execution privileges.

> Source preview, not a certification of MVP completeness. The GIF uses scripted fixtures in the real CLI renderer; it is not a successful model benchmark. The browser playground is an in-memory interaction demo, not a remote shell.

[Publication & privacy](../../docs/PUBLICATION.md) · [Recording recipe](../../docs/DEMO_RECORDING.md) · [Origins](origins/README.md)

## Active-pane scrolling / AI beta

[Independent scrolling and terminal limitations](../../docs/SCROLLING.md)

Wheel / PageUp / PageDown operate on the currently selected pane. Empty Enter changes the input and scroll destination together. The other pane keeps its viewport. This does not control the terminal emulator's native history scrollbar.

The Pages beta additionally offers **Copy handoff**, **Direct API** (OpenAI-compatible / Ollama), and **Import answer**. Direct API is explicit, may be blocked by browser networking rules, and does not run tools or change files. Keys are kept only in tab memory and cleared from the field at send time or on dialog close. AI answers remain unverified proposals, not successful execution receipts. Use the local CLI for subscription-based development.
