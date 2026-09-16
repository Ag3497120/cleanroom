# 別のMacでCleanroomを導入・確認する

Veraは、AIに実装を任せながら、人間の目的・判断・理解とプロジェクトの経験を手元に残す共同開発基盤です。設定メニューはその入口であり、初回にすべての設定や内部用語を覚える必要はありません。

このページは導入と手動確認の手順です。別Macや各プロバイダーでの動作確認済みを意味しません。CLIの起動、AIの接続、候補生成、人間の理解はそれぞれ別に確認します。

## 1. 前提

- Python 3.11以上。以下の例は `python3.11` を使います。macOS付属・Xcode付属の古い `python3` は使わないでください。
- Gitと、対話入力のできるTerminalなどの端末。
- AIの接続確認には、そのMacのCodexログイン、APIキー、または起動済みのローカルモデルが必要です。設定画面を開くだけなら不要です。
- 元のMacの `.venv` はコピーせず、新しいMacで作成してください。Apple SiliconとIntelでバイナリ依存が異なります。この手順だけでは両方の実機検証を済ませたことにはなりません。

Homebrewを既に使っている場合のPython導入例:

```sh
brew install python@3.11
```

## 2. GitHubからインストール

```sh
mkdir -p "$HOME/Projects"
cd "$HOME/Projects"
git clone https://github.com/Ag3497120/project-cleanroom.git
cd project-cleanroom
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ./core
verantyx --version
```

`core` がPythonパッケージの場所です。リポジトリ直下で `pip install -e .` としないでください。既存の同名フォルダがある場合は別の名前へcloneし、以下のパスも読み替えてください。

別のターミナルを開いたら、作業前に仮想環境を有効にします。

```sh
source "$HOME/Projects/project-cleanroom/.venv/bin/activate"
```

## 3. 試すプロジェクトを分ける

Cleanroom自身のソースと、AIに作業してもらうプロジェクトは別のフォルダで構いません。最初は機密情報のない専用フォルダを使います。

```sh
mkdir -p "$HOME/Projects/cleanroom-playground"
cd "$HOME/Projects/cleanroom-playground"
verantyx --lang ja setup
```

設定がなければ安全な既定値でプロジェクト設定を作り、英語ベースの設定メニューを表示します。AIの呼び出しやファイルの外部送信は、メニューを開いただけでは行いません。

通常は `Models & organization` で作業AIを選ぶだけで始められます。目的や学習表示は後から変更できます。設定を終えたら:

```sh
verantyx
```

## 4. 設定コマンド一覧

| コマンド | 内容 |
| --- | --- |
| `verantyx setup` | 設定メニューを開く。初回の設定作成にも使う |
| `verantyx settings` | 同じ設定メニューへの別名 |
| `verantyx setup accounts` | ChatGPT / Claudeの本人契約を公式CLIで接続する |
| `verantyx setup codex` | ChatGPT接続のインストール・ログイン・モデル設定へ直接進む |
| `verantyx setup claude` | Claude接続のインストール・ログイン・モデル設定へ直接進む |
| `verantyx setup models` | 作業AIと整理AIを設定する |
| `verantyx models` | モデル設定への短い入口。`verantyx model` も同じ |
| `verantyx setup project` | プロジェクト名と目的を変更する |
| `verantyx setup learning` | 学習候補の表示方法と1作業あたり1〜3件の上限を選ぶ |
| `verantyx setup language` | ノートの表示言語を選ぶ。変更後はノートを再起動する |
| `verantyx setup workspace` | 現在のプロジェクトとローカル保存の範囲を説明する。権限拡張はしない |
| `verantyx setup boundary` | 権限と候補・証拠・理解の境界を表示する。設定変更はしない |
| `verantyx settings --show` | 保存済みの設定を表示する。設定作成・変更・AI呼び出しはしない |
| `verantyx settings --json` | 同じ情報をJSONで表示する。接続成功の判定ではない |
| `verantyx config` | 既存の設定表示コマンド |
| `verantyx doctor` | Python・プロジェクト・設定の基本状態を表示する。AI接続テストではない |
| `verantyx setup --guided` | 従来の詳細なプロジェクト設定フォームを開く |
| `verantyx --help` | 設定を含むコマンドの案内を見る |

`settings models` など、`settings` の後ろにも同じ設定項目を指定できます。設定変更には保存確認があります。設定画面はコマンド名を暗記しなくても選択肢から操作できます。単独の設定コマンドでは番号入力、分割UI内では選択UIを使用します。

別の場所のプロジェクトを設定する場合:

```sh
verantyx --project "$HOME/Projects/cleanroom-playground" setup models
verantyx --project "$HOME/Projects/cleanroom-playground" settings --show
```

`--project` はCleanroomが扱う対象のフォルダです。現在の作業範囲へ親フォルダを無条件に追加する操作ではありません。

スクリプト用の従来の設定方法も残しています。

```sh
verantyx --project "$HOME/Projects/cleanroom-playground" --lang ja setup --non-interactive \
  --name "Cleanroom playground" --purpose "AIと作業しながら判断を残す" \
  --learning digest --max-items 1
```

対話端末がない環境では、閲覧に `settings --show` または `settings --json` を使います。対話メニューはパイプから操作できる前提にしていません。

## 5. 作業AIと整理AI

`verantyx models` の `Choose Work AI` で接続先を選びます。

| 接続先 | このMacで用意するもの |
| --- | --- |
| ChatGPT subscription / Codex | 公式Codex CLIと、そのMacでのChatGPTログイン |
| Claude subscription / Claude Code | 最新版の公式Claude Codeと、そのMacでのClaudeログイン |
| Ollama / local | 起動済みのOllamaとインストール済みモデル |
| OpenAI API | 使用するモデル名と `OPENAI_API_KEY` |
| Anthropic API | 使用するモデル名と `ANTHROPIC_API_KEY` |
| Gemini API | 使用するモデル名と `GEMINI_API_KEY` |
| OpenAI-compatible server | サーバーのエンドポイントと、そのサーバーのモデル名 |

APIとローカル接続ではモデル名を指定します。Ollamaの一覧が取れる場合は導入済みモデルから選択できます。モデル名を保存できることと、そのモデルが必要な応答形式を返せることは別です。

整理AIは既定で `Reflection: same as Work AI` です。別のAIを使うなら `Reflection: choose a different AI`、整理のモデル呼び出しを止めるなら `Reflection: off; keep work facts only` を選びます。整理を止めても、作業記録を意味の推測で埋め合わせることはしません。

`setup learning` は表示方法の設定です。整理AIの呼び出しを止める設定とは別であり、表示を消しても「理解済み」にはなりません。

### ChatGPT / Claudeのサブスクリプションを接続する

一つだけ使う場合は、次のどちらかで直接設定できます。

```sh
verantyx setup codex
verantyx setup claude
```

接続先を画面で選ぶ場合は `verantyx setup accounts`、設定の入口からなら `verantyx setup` の `Accounts` を選びます。モデル一覧からも同じ導線へ進めます。

1. そのMacの公式CLIを検出する。PATHに加え、`~/.local/bin`、Apple Silicon / IntelのHomebrew標準位置などを探す。
2. 未導入なら `Install the official CLI` を選ぶ。実行コマンドと公式配布元を表示し、確認後だけインストーラーを起動する。自動でインストールしない。
3. `Sign in with your subscription / browser` で公式CLIの本人ログインを進める。既に対応するアカウントへログイン済みなら、そのアカウントを利用できる。
4. `Use this account` で作業AIとして保存する。標準はCLIの既定モデル。必要な人だけ `Choose a model ID or alias` で変更する。
5. `verantyx` で通常のノート画面へ戻り、仕事を依頼する。

単独の設定コマンドでは、公式CLIへターミナルを一時的に渡します。分割画面内からは、macOSのTerminalに別の認証画面を開きます。本人ログインが終わったら元のCleanroomへ戻ってContinueを選んでください。Continue自体を成功扱いせず、公式CLIの認証状態を再取得します。macOSの自動操作許可でTerminalを開けない場合は、表示されたコマンドを別のターミナルで実行できます。

インストールもログインも本人が選んだときだけ行います。メニュー閲覧はAI生成を開始しません。認証状態取得は公式CLIを呼びますが、プロジェクトの依頼・ファイル内容は渡しません。ログイン変更は同じ公式CLIの認証を使う他プロジェクトにも影響し得ます。

#### ChatGPT

内部で利用する本人操作は `codex login` と `codex login status` です。ブラウザ認証が使いにくい場合は、設定メニューのdevice codeから `codex login --device-auth` を選べます。device codeはアカウント・組織側で有効化が必要な場合があります。[OpenAI公式認証ガイド](https://learn.chatgpt.com/docs/auth)

新しい通常設定はSpark固定ではありません。`default` はCodex CLIの既定モデルを使い、指定した場合だけ `--model` を渡します。旧プロファイルのSpark指定は勝手に変更しません。変更する場合は `verantyx setup codex` で接続を作り直してください。高度な旧 `codex-config` コマンドの既定値は従来どおりです。

インストーラーの配布元・手順は[Codex公式CLIガイド](https://learn.chatgpt.com/docs/codex/cli)を参照してください。

#### Claude

内部で利用する本人操作は `claude auth login` と `claude auth status` です。Claudeを利用できる自分の契約でログインしてください。Cleanroomの通常Work / Reflection経路は、未改変の公式Claude Codeを起動して構造化された提案を受け取ります。サブスクリプションのトークンをAnthropic APIへ流用する方式ではありません。[Claude Code CLIリファレンス](https://code.claude.com/docs/en/cli-reference)

認証はAnthropic自身の画面で完結させます。Cleanroomはパスワード・OAuthトークンの入力欄を設けず、認証ファイルを読み込んで保存・コピーしません。公式CLIを製品から利用する場合の条件は[Claude Codeの公式規定](https://code.claude.com/docs/en/legal-and-compliance)に従います。自社サービスとして配布・運用する場合は、未改変バイナリ、本人の認証・直接課金、商用条件などを別途確認してください。

最新版のClaude Codeを必要とします。構造化出力、`--safe-mode`、`--restricted`などが未対応の古いCLIは更新してください。制限フラグが未対応でも、制限を外して再実行しません。`--bare` はサブスクリプション認証を使用しないため、この経路では使いません。[プログラムからの利用](https://code.claude.com/docs/en/headless)

モデル名は `default`、`sonnet`、`opus`、`haiku`、利用権限のあるモデルIDを設定できます。保存成功はモデルへのアクセス成功を保証しません。旧来の高度なワークフロー用プロトコルすべてを、このClaude接続で扱えるわけではありません。

#### 共通の境界

- 認証情報は公式CLI側に残します。旧Macの `.codex/auth.json`、Claude認証ファイル、Keychainの内容、`setup-token` の出力をCleanroom・Git・Issueへ持ち込まないでください。
- この接続は本人のネイティブアカウント認証用です。APIキー・抽出したOAuthトークン・別プロバイダーへの環境変数は引き継ぎません。API課金で使いたい場合は、ModelsのOpenAI API / Anthropic APIを明示的に選んでください。
- 契約の対象モデル、上限、追加利用の課金は各社側の条件に従います。Cleanroomは無料・無制限や、追加料金が絶対に発生しないことを保証しません。
- `SIGNED_IN` は公式CLIの認証状態であり、生成試験・モデル利用権限・残量の確認ではありません。別方式のログイン、取得失敗、読めない状態報告は接続確認済みにしません。
- モデル固有の組み込みツールを使わせず、通常WorkではVera側の許可済み読み取り・隔離候補への書き込みを利用します。Claudeではユーザーのカスタマイズも抑制しますが、組織管理ポリシーは残ります。これはOSサンドボックスの保証ではありません。
- 整理AIは独立設定です。既定のSame as Work AIなら同じ接続を使い、別の整理AIを選んでいた場合は勝手に変更しません。整理の失敗で作業結果を破棄しません。
- この変更について、実ログイン・実生成・別Macでの動作確認はまだ実施していません。

### APIキー

キー自体を設定メニューへ入力する必要はありません。API呼び出し時に、選んだ接続先に対応する環境変数から取得します。CLIを起動するのと同じターミナルで設定してください。

macOS標準のzshで、キーをコマンド履歴へ直接書かずに入力する例:

```zsh
read -s "OPENAI_API_KEY?OpenAI API key: "
export OPENAI_API_KEY
verantyx models
```

他の接続先では変数名を表のものに変更します。キーをGitへ追加したり、問題報告へ含めたりしないでください。API利用の料金とChatGPTサブスクリプションの利用枠を同一視しないでください。

### ローカルモデル

Ollamaを使う場合はサーバーを起動し、モデルを用意しておきます。設定時の既定接続先は `http://127.0.0.1:11434/api/chat` です。

OpenAI互換サーバーの既定接続先は `http://127.0.0.1:1234/v1/chat/completions` です。使用中のサーバーに合わせて設定画面で変更します。初期設定はローカルHTTPサーバー向けであり、認証付きの任意のリモート互換サーバーをすべて設定できるという意味ではありません。

## 6. 設定とデータの保存場所

- `<対象プロジェクト>/.verantyx/config.json`: プロジェクト名・目的・表示言語・学習表示・モデル選択。
- `<対象プロジェクト>/.verantyx/model-adapters/`: モデル接続用の設定。接続方式によってはMac固有の実行ファイルパスを含みます。
- 対象プロジェクトの `.verantyx/` 以下には、作業記録・候補・判断・ノートなどのローカルデータもあります。全体を公開用リポジトリへ追加しないでください。
- 人間のメモやAIに渡すことを明示した内容は、同じ「設定」ではありません。設定変更は既存の理解記録を理解済みにしたり、規則を有効化したりしません。

新Macの導入確認では空のプロジェクトから始めます。既存記録を移す場合は別途バックアップを取り、認証情報や端末固有の接続設定を混ぜないでください。自動移行ウィザードはありません。

## 7. 新Macでの手動確認

最初は外部AIを呼ばずに確認できます。

1. `verantyx --version` で起動した版を記録する。
2. `verantyx setup` を開き、Models・Project・Learningなどの設定項目が見えるか確認する。
3. Projectで名前や目的を保存し、`verantyx settings --show` に反映されるか確認する。
4. `verantyx models` で作業AIと整理AIの選択肢を確認する。設定しただけで接続成功とは記録しない。
5. `verantyx` を起動し、空欄EnterでAgent入力からOwnerメモ、Owner検索へ移動できるか確認する。
6. 自分のメモを保存し、検索で見つけられるか確認する。
7. Agent欄に短い依頼を入力し、外部送信前の確認まで進める。まずは `n` で中止し、次の依頼を入力できるか確認する。
8. 入力待ちの状態でCtrl+Cを押し、CLIが終了するか確認する。

その後、必要なら自分のAI接続で実作業を試します。ここからはプロジェクトの依頼・承認した文脈が選択したAIへ渡り、クラウド接続では利用枠や料金が発生し得ます。

```sh
verantyx "このプロジェクトの目的を短く説明してください。ファイルは変更しないでください。"
```

送信範囲を確認してから開始してください。自然文の「変更しないで」はAIへの指示であり、OSレベルの権限設定に置き換わるものではありません。現行Work経路の書き込み先は隔離候補です。応答と作業状態を確認し、整理が失敗した場合は作業失敗と区別して記録してください。

この確認で分かるのは、そのMac・その接続・その依頼での結果です。全モデル対応、実装候補の正しさ、人間の理解、MVP全体の完成を証明するものではありません。

## 8. 更新とトラブル対処

更新はインストール元で行います。設定した作業プロジェクトのフォルダと取り違えないでください。

```sh
cd "$HOME/Projects/project-cleanroom"
source .venv/bin/activate
git pull --ff-only
python -m pip install -e ./core
verantyx --version
```

| 症状 | 対処 |
| --- | --- |
| `verantyx: command not found` | 上記の仮想環境を有効にする。`python -m pip install -e ./core` をインストール元で行う |
| Pythonの型構文などで起動に失敗する | Python 3.11以上で新しい仮想環境を作る。旧Macの `.venv` を再利用しない |
| 設定コマンドが認識されない | インストール元の更新と有効な仮想環境を確認する |
| `NOT_CONFIGURED` | 対象プロジェクトで `verantyx setup`。別フォルダを誤って指定していないか確認する |
| 分割画面が狭い・表示が合わない | ターミナルを広げる。幅・高さにより上下配置へ切り替わる。`verantyx --plain` も使える |
| Codexが起動しない | そのMacでCodexのインストール・ログインを行い、`verantyx models` から再設定する |
| APIへ接続できない | 環境変数名、モデル名、エンドポイント、利用権限を確認する |
| ローカルAIへ接続できない | モデルサーバーの起動、モデル名、ポート、応答形式の対応を確認する |
| `doctor` は成功するのにAIが失敗する | `doctor` は基本設定の確認であり、モデルへの実通信は確認しない |

問題報告には以下を記録してください。APIキー、認証トークン、機密の依頼全文、`.verantyx` 全体は含めないでください。

```text
macOS version:
CPU architecture (arm64 / x86_64):
Python version:
Verantyx version:
Source commit:
Entry command:
Setup menu: opened / failed / not checked
CLI request confirmation: reached / failed / not checked
Cancel and next request: passed / failed / not checked
AI provider and model (no credentials):
Actual AI request: succeeded / failed / not run
Work result:
Reflection result:
Error code and a sanitized excerpt:
```
