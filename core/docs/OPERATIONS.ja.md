# Cleanroom操作ガイド

[English](OPERATIONS.en.md) · [日本語](OPERATIONS.ja.md) · [简体中文](OPERATIONS.zh-Hans.md) · [한국어](OPERATIONS.ko.md) · [Español](OPERATIONS.es.md) · [README](../../README.md)

Cleanroomは、Vera Kernelを基盤とする共同開発空間です。AIが実装の大部分を担っても、プロジェクトの目的、設計判断、検証方法、失敗、技術的理解を人間側に残し、一緒に育て続けられるようにします。

## 01 / 手元で始める

各PCでPython 3.11以上の新しい仮想環境を作ります。Linuxはソース導入手順であり、全ディストリビューションで検証済みという意味ではありません。Windowsはネイティブ版ではなくWSL2を使います。有効化後、作業したいプロジェクトへ移動してください。

```sh
git clone https://github.com/Ag3497120/cleanroom.git cleanroom
cd cleanroom
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./core
verantyx setup accounts
verantyx
```

```sh
source /absolute/path/to/cleanroom/.venv/bin/activate
cd /absolute/path/to/your-project
verantyx
```

## 02 / 左はAgent、右はOwner

左下のAgent欄へ普通の文章で依頼します。独自のコマンドを覚える必要はありません。

| 日本語 | Key |
|---|---|
| 仕事を依頼 | Agent: Enter |
| 自分用メモ | Empty Enter → MEMO |
| Owner内の検索 | Empty Enter → SEARCH |
| 記録を参照 | 2+ characters → ↑/↓ → Tab |
| 操作一覧 | F2 |
| スクロール | F3 |
| 理解の画面 | F4 |
| 分割表示 | Alt+0 |
| 改行 | Ctrl+J / Esc then Enter |
| 終了 | Ctrl+D |

空欄でEnterを押すと、Agent → 黄色のOwnerメモ → 緑色のOwner検索 → Agentを巡回します。

Owner項目の先頭2文字以上を入力し、上下矢印で選び、Tabで参照を挿入します。補完候補が開いている間のEnterは選択だけで、依頼は送りません。

左右分割は140列・24行以上。90列・36行以上では上下配置、それより狭い場合は入力先に応じた画面になります。MacのFキーにはFnが必要な場合があります。OptionをEscapeとして送る設定やF2メニューを利用できます。

```sh
VERANTYX_REDUCE_MOTION=1 verantyx
NO_COLOR=1 verantyx
verantyx --plain
verantyx watch
```

Ctrl+C: clear the current draft / cancel the current question; with no draft, request closure. It is not a guarantee of forcibly stopping an external program. Esc closes a menu or suggestion without accepting it.

## 03 / Commands

設定メニューは英語ベースです。ガイドの翻訳は、CLIの全表示が5言語化済みという意味ではありません。実際の登録一覧は `verantyx --help` と `verantyx commands NAME` を参照します。

| Command | 日本語 / scope |
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

Codex・Claudeは公式CLIのローカルログインを使います。サブスク認証トークンをWebへ貼り付けません。API料金とサブスクは別です。ローカルモデルは稼働中の接続先と利用できるモデルが必要です。作業AIと整理AIは別々に選べ、整理なしでも作業結果は残ります。

```sh
verantyx setup accounts
verantyx setup codex
verantyx setup claude
verantyx setup models
verantyx setup roles
verantyx settings --show
```

## 05 / My profile · My pace · My skills

F2 > My profileで経験を短く書くか、スキップできます。My paceで提案の量・重さを調整します。My skillsではAIの仮手順、次に触りたい項目、本人の説明・適用例を分けます。盤面を全部埋める必要はありません。pushをAIへ頼むことをGitの理解不足と判断しません。

作業結果とAIによる整理は別状態です。モデルごとの見方が違っても過去の整理を消しません。AIの手順が保存されたことを、本人の習得とは数えません。スキップ、委譲、相談を理解不足と推定しません。

```sh
verantyx setup profile
verantyx setup pace
verantyx my-skills
verantyx my-skills quiet --scope TODAY
verantyx my-journal
verantyx my-learning
```

## 06 / Owner · Privacy

Ownerメモは既定でローカルです。依頼へ選んだ参照だけを挿入します。外部への送信範囲は作業フローで別に確認します。メモ・参照・学習の選択で実行権限は増えません。

Ownerのメモと検索だけではAIを呼びません。依頼に明示的に挿入した参照は送信範囲に入ります。プロジェクトと個人の私的な記録を公開GitHubへ追加しないでください。

## 07 / My Atlas

`verantyx web` はループバックで動く私的なMy Atlasを開きます。ターミナルは起動したままにします。表示するのは本人の経験記録で、点数や未習得一覧ではありません。同じOSユーザーの個人記録はプロジェクト共通ですが、別Macへ自動同期はしません。

```sh
verantyx web
verantyx web --no-open
verantyx --lang ja web
```

The actual view follows its supported language catalogue; untranslated items may fall back. These guides do not claim complete five-language runtime localization.

## 08 / Work · Reflection

範囲外のパスを無理に迂回しません。明示的に許可した範囲か、別プロジェクトを使います。整理が失敗しても作業結果は残し、後から `verantyx organize RUN_ID` で整理できます。以前の見方は `verantyx perspectives RUN_ID` から参照できます。

## 09 / Obsidian · MCP · Harness

F2 > Notebook bridgeで指定したObsidian vaultへ接続します。取り込んだスキルは出典付きの候補で、習得認定でも実行許可でもありません。MCPと外部ハーネスは明示設定が必要です。サンドボックスの設定済み表示は隔離保証ではありません。

[Connections](NOTEBOOK_CONNECTIONS.en.md) · [日本語](NOTEBOOK_CONNECTIONS.ja.md) · [Sandbox boundary](SANDBOX_BACKENDS.en.md)

## 10 / Web preview

公開Pagesの体験欄とGIFはデモデータを使います。AI実行、ファイル変更、サブスク認証、検査成功の認定はしません。既存の任意ゲートウェイは別サービスで、設定と所有者の承認が必要です。公開Webへ個人のCodex実行権限をそのまま渡す構成にはしません。

> ソース版のプレビューであり、MVP全項目の合格宣言ではありません。GIFは実際のCLI描画に台本付きのデモデータを流したものです。実モデルの成功記録ではありません。Webの体験欄はメモリ内だけの操作デモで、リモートシェルではありません。

[Publication & privacy](../../docs/PUBLICATION.md) · [Recording recipe](../../docs/DEMO_RECORDING.md) · [Origins](origins/README.md)

## Active-pane scrolling / AI beta

[Independent scrolling and terminal limitations](../../docs/SCROLLING.md)

Wheel / PageUp / PageDown operate on the currently selected pane. Empty Enter changes the input and scroll destination together. The other pane keeps its viewport. This does not control the terminal emulator's native history scrollbar.

The Pages beta additionally offers **Copy handoff**, **Direct API** (OpenAI-compatible / Ollama), and **Import answer**. Direct API is explicit, may be blocked by browser networking rules, and does not run tools or change files. Keys are kept only in tab memory and cleared from the field at send time or on dialog close. AI answers remain unverified proposals, not successful execution receipts. Use the local CLI for subscription-based development.
