# Cleanroom操作ガイド

[English](OPERATIONS.en.md) · [日本語](OPERATIONS.ja.md) · [简体中文](OPERATIONS.zh-Hans.md) · [한국어](OPERATIONS.ko.md) · [Español](OPERATIONS.es.md) · [README](../../README.md)

Cleanroomは、Vera Kernelを基盤とする共同開発空間です。AIが実装の大部分を担っても、プロジェクトの目的、設計判断、検証方法、失敗、技術的理解を人間側に残し、一緒に育て続けられるようにします。

## 新しい操作を最短で把握する

`verantyx setup`の新規導入時は英語で始まり、言語を選ぶと案内と選択肢の説明もその言語へ切り替わります。初回終了時のチュートリアルは疑似画面です。その中で`verantyx`と入力すると練習を終えて実CLIへ進み、`/done`でも練習表示を終了できます。端末サイズの案内は警告のみです。

横120文字 × 縦28行以上ではAgent約70%・Owner約30%の左右2欄、横80文字 × 縦48行以上では上下表示、それより小さい場合は操作中の欄を表示します。サイズを理由に進行を止めません。空EnterによるAgent → メモ → 検索は同じです。端末の文字サイズは端末アプリ側で変更し、Web体験版では画面内の文字サイズボタンも使えます。

### 完成を待たず、作りながら理解する

プロジェクトの「完成」まで、理解の表示を待つ必要はありません。

- **普通に依頼して、そのまま続ける。** Agentには背景色付きの依頼、背景色なしの回答が会話として続きます。システム通知は別欄にし、実行中はスピナーと穏やかな入力欄の明滅を表示します。
- **必要な説明だけを手元へ。** 作業の安全な区切りで、実装中のノートを本人の提案量に合わせてOwnerへ表示できます。`L-000001`のような番号をAgentに送れば、元の実装を置き換えずに質問できます。実行中の長いツール呼び出しは、その呼び出しが終わってから応答します。
- **予想時間は予想として。** AIが提示した場合に実装と検査の時間幅を分けて表示します。質問にかかった時間を加え、次の作業ターンで再見積もりできます。未取得・古い見積もりを確実な時刻に見せません。
- **自分のペースで残す。** メモ、参照、委譲、次回のどれでも構いません。質問・スキップ・スキル移植・許可の操作から、本人の習得を認定しません。

Agentの`/verantyx new`はAgentの会話だけを新しくします。OwnerのCleanroomは独立した名前と確認操作で管理します。候補の変更は**一度だけ／このワークスペース／永久／拒否**から選び、本体採用や公開の許可とは分けます。

[作業中の学び・セッション・権限・保存](../../docs/live-learning-and-sessions.md) · [会話表示と差分確認](../../docs/conversation-and-change-review.md)

| 入力 | 動作 |
|---|---|
| `verantyx new [name]` | Agentの会話だけを新しくし、Ownerは維持 |
| `verantyx new --owner [name]` | シェルからOwnerのCleanroomを作成。実行前に確認 |
| `verantyx cleanroom [name]` | OwnerのCleanroom一覧。切り替え前に確認 |
| `verantyx compact` | 原文を消さず、出典付き文脈をAIで圧縮 |
| `/insights` | 実装中に残った最近の説明を開く |
| `L-000001` | 安全な区切りで、そのノートについて質問 |
| `/approvals` | 候補の変更に関する許可を確認 |
| `/queue` | 実行中の入力を待ち列か次の安全な区切りへ |

Ownerのメモは日時付きで個人用のローカルSQLiteへ保存します。全件を一度に描画せずページ単位で読み込み、検索は保存されたメモを対象にします。作業の原記録はプロジェクト台帳に残り、AI要約は原文の置き換えではなく出典付きの追加表示です。通常経路の負荷を抑える対策であり、全台帳の再生・全件エクスポートまで一定メモリで動くという保証ではありません。

ブラウザ体験版は入力先の切り替え、参照、メモ、連続した会話、許可選択の例を再現します。保存先はそのタブ内であり、CLIのDBではありません。例の予想時間や結果は実作業・証拠ではありません。サブスク実行・実際の圧縮・永続セッション・ファイル編集はローカルCLIで行い、「AIに頼む」の接続は明示操作として分けます。

[現在の操作](../../docs/two-pane-interaction.md) · [作業中の学びとセッション](../../docs/live-learning-and-sessions.md) · [英語の録画デモ](../../docs/DEMO_RECORDING.md)


## 01 / 手元で始める

各PCでPython 3.11以上の新しい仮想環境を作ります。Linuxはソース導入手順であり、全ディストリビューションで検証済みという意味ではありません。Windowsはネイティブ版ではなくWSL2を使います。有効化後、作業したいプロジェクトへ移動してください。

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

横120文字 × 縦28行以上ではAgent約70%・Owner約30%の左右2欄、横80文字 × 縦48行以上では上下表示、それより小さい場合は操作中の欄を表示します。サイズを理由に進行を止めません。空EnterによるAgent → メモ → 検索は同じです。端末の文字サイズは端末アプリ側で変更し、Web体験版では画面内の文字サイズボタンも使えます。

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
