# モデル呼び出し・キャッシュの修正前の確認（2026-09-17）

これは最適化を加える前の監査記録です。その後の変更と利用方法は
[モデル利用効率と入力欄の改善](MODEL_EFFICIENCY.ja.md)を参照してください。
以下の「現在」は監査時点を指します。

対象: Cleanroomのローカルコード（HEAD `17a1181` にWeb・読み取りUIの作業変更を加えた状態）。
この確認時点ではモデル接続の実装は未変更でした。検証用の有料モデル呼び出しもしていません。

## 結論

重複実行防止、履歴圧縮、出力の短縮は存在しますが、本家CodexやClaude Codeと同等の
プロンプトキャッシュ効率を保証できる状態ではありません。
特にClaude API直結のキャッシュ指定不足、毎回変わるCLI実行ディレクトリ、
毎ターンの全体JSON組み直し、作業後の追加モデル呼び出し、経路による利用量記録の欠落が課題です。

このプロジェクトで現在選択されているCodexアダプターの保存済み利用記録を、本文を読まずに集計しました。

| 指標 | 保存済みの値 |
|---|---:|
| 呼び出し | 7 |
| 入力トークン | 240,335 |
| キャッシュ済み入力 | 0 |
| 出力トークン | 4,817 |
| 推論出力トークン（別報告フィールド） | 780 |
| 利用量記録がない呼び出し | 0 |

推論出力を出力トークンへ単純加算していません。上表は、この保存記録に限った値です。
他プロジェクト・他セッション・アカウント全体の統計ではありません。
7件すべてに `cached_input_tokens` が記録されており、項目が欠けているものを0扱いした集計ではありません。

## 接続経路ごとの状態

| 経路 | あるもの | 不足・注意点 |
|---|---|---|
| Codex CLI / ChatGPT認証 | 同一リクエストの成功結果をローカル再利用。プロバイダー報告の入力・キャッシュ済み入力・出力を記録 | 呼び出しごとに一時ディレクトリで `codex exec --ephemeral`。会話をresumeしない。ネイティブ側のキャッシュ自体をOFFにはしていないが、安定した共通接頭辞を保てるとは限らない |
| Claude Code / サブスク認証 | 本家CLIを使用し、ホスト側の呼び出しジャーナルで再実行を防止 | 毎回別の一時ディレクトリと `--no-session-persistence`。会話をresumeしない。返答のusageやcache_read/cache_creationを取り出して保存していない |
| OpenAI API直結 | 共通のinstructions、1回だけのHTTP POST、入力上限、出力上限 | 全体JSONを1つの入力として毎回再構成。明示的なキャッシュ境界・継続会話の設計がない。usageを保存せず本文だけ返す |
| Claude API直結 | 共通のsystem、入力・出力上限、再送防止のホストジャーナル | リクエストに `cache_control` がない。usageも保存しないため、キャッシュ状況を利用者が確認できない |

`store:false` やセッション非保存は、それだけでプロバイダーのプロンプトキャッシュを無効化する指定ではありません。
逆に、本家CLIを呼び出しているだけで、本家の継続会話と同じ再利用率になるわけでもありません。

コードの主な根拠:

- `core/src/verantyx/codex_cli.py`: `_argv`, `_invoke`, `request`
- `core/src/verantyx/codex_budget.py`: `reserve`, `record_usage`, `usage`
- `core/src/verantyx/claude_cli.py`: `_argv`, `_exchange`, `request`
- `core/src/verantyx/model_api.py`: `payload`, `request`
- `core/src/verantyx/agent_models.py`: `invoke_prepared`, `reflection_setting`

## キャッシュ以外の増加要因と既存の最適化

`agent_runtime.py` は、依頼・プロジェクト文脈・過去のturns・ツール結果・候補ファイル情報などを
各ターンで再送します。`canonical()` はキーをソートするため、変化する `candidate_manifest` や
`generation_id` が、大きな固定部分より前に来ることがあります。共通prefixの再利用に不利です。

履歴の再送自体は本家でも必要です。違いは、履歴を安定したメッセージ単位で追記するか、
変化するJSONにまとめ直すか、そしてプロバイダーがその境界をキャッシュ対象にできるかです。

作業後には `organize()` による整理・スキル候補生成があり、Reflectionの既定はWorkと同じモデルです。
このローカル設定も明示上書きがなく、既定のsameが適用されます。作業1回で完結する短い依頼なら、
整理1回の追加により呼び出し回数が1回から2回になる場合があります。
ただし入力・出力量は異なるため、これを料金2倍とは換算できません。

既存の節約策もあります:

- `InvocationJournal` とCodexの予約記録により、成功済み結果の再利用や結果不明時の無条件再送を防ぐ。
- `session_context.py` に履歴の要約・省略と入力予算がある。ただし要約にもモデル呼び出しが必要。
- `codex_wire.py` と `agent_schema.py` に、参照IDやネイティブ構造化出力を使う出力の縮小がある。
- WorkとReflectionのモデルを分ける、Reflectionをoffにする既存設定がある。
- 入出力上限はあるが、`codex_budget.usage()` が示すとおり金額・総トークンのハード上限ではない。

## 優先する改善

1. 全接続で入力・出力・キャッシュ読み取り・キャッシュ書き込み・呼び出し用途を記録し、Workと整理を分けて表示する。
2. 固定の指示・スキーマ・参照文脈を前に置き、毎回変わるIDや状態は後ろに分離する。監査用のハッシュ生成は変更しない。
3. Claude APIには安定したブロックのキャッシュ指定を追加する。変化する全体JSON末尾へ指定するだけでは十分ではない。
4. CLI連携は実行ディレクトリと会話を安定させる設計を検討する。既存の権限・読み取り範囲を維持した上で継続する必要がある。
5. Reflectionを毎回実行するか、手動・まとめ実行・別モデルにするかを明示的に選べる表示にする。

## 公式仕様との照合

OpenAIのキャッシュは一致するprefixとモデルごとの境界・最低長に依存します。
GPT-5.6以降と以前では、暗黙のキャッシュ境界や `prompt_cache_key` の役割が異なります。
キーを1つ追加するだけで全モデルの無駄が解消するとは言えません。
[OpenAI Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)

Claude APIのキャッシュは `cache_control` で指定できます。固定prefixの末尾に境界を置くことが重要です。
[Claude API Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)

Claude Codeはキャッシュを自動管理しますが、作業ディレクトリなどがprefixへ入り、
異なるディレクトリのセッション間でキャッシュが一致しなくなることが公式に説明されています。
[How Claude Code uses prompt caching](https://code.claude.com/docs/en/prompt-caching)

実際の差額・倍率には同じモデル・依頼・ツール・出力条件での比較が必要です。
APIの従量課金とChatGPT/Claude契約の利用枠消費を同じ金額として扱わないでください。
