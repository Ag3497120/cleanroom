# My Skills と Work Harness

この文書は、二段階のスキル保存と交換可能な作業ハーネスのソース実装を説明します。
今回の追加経路は起動・実モデル・回帰テスト未実施です。公開済み配布物に入ったことや、安全性・習熟を保証するものではありません。

## 目的

AIが仕事を進めても、本人の目的、判断、経験、理解が手元に残ることが目的です。
スキル数を競うこと、全項目を学ぶこと、社員の能力を推定することが目的ではありません。

実装中のWork AIは説明を元イベントへ残し、作業後の整理AIは実際の作業イベントから手順候補を作ります。
本人が学びたい時には、その手順を[前提・省略手順・確認方法へ紐解けます](LEARNING_CONTINUITY.ja.md)。
技術名による固定分類、学習のスキップによる能力推定、全員共通の必修リストは使いません。

## 二つの段階

1. AIの手順を仮保存する。作業を止めず、手順・入力・出力・適用条件・中止条件・検証方法案・人間に残す判断・出典を残します。
2. 本人が必要な項目だけ選ぶ。次の仕事で自分の言葉、適用した場面、別の問題へ使った例を少しずつ記録します。

AIの候補が増えても、人間の習得欄が増えるとは限りません。それで正常です。
「このまま進める」は、本人の習得、手順の検証、ツール実行の承認を意味しません。

| 軸 | 保存する状態 |
|---|---|
| AI手順の利用方針 | DRAFT / REFERENCE / REVIEW_REQUIRED / RETIRED |
| 本人の記録 | NO_RECORD / SELF_REPORTED / EXPLAINED / APPLIED / TRANSFERRED |
| 本人の希望 | UNSELECTED / WANT / NEXT_TIME / REFERENCE / DELEGATE / NOT_NEEDED |

EXPLAINEDなどは本人が書いた説明・実例の来歴です。AIや会社による能力認定ではありません。
NO_RECORDは「記録がない」であり、「理解していない」ではありません。
DELEGATEは学習の所有方針であり、削除・公開・任意コマンド実行の権限ではありません。

## 普段の操作

起動後、F2から **My skills** を選びます。コマンド名の暗記は不要です。
カタログから自分に必要な項目を選び、On my boardまたはNext opportunityに置きます。
盤面は端末幅に応じて1〜3列になります。空欄を全て埋める課題、完成率、連続日数、ランキングはありません。

~~~text
MY SKILLS / 必要な穴だけ、自分のペースで
+--------------------------+--------------------------+
| リクエスト境界の整理     | 失敗時の戻り方           |
| [E] EXPLAINED            | [ ] NO_RECORD            |
| WANT / AI:DRAFT          | NEXT_TIME / AI:REFERENCE |
+--------------------------+--------------------------+
~~~

この表示は説明用です。実際には保存された項目だけ表示します。

- Keep working: 今は学習を後回しにする。
- Choose my part: 身につけたい、次回、参照、委譲、不要から選ぶ。
- My experience: 自分の説明・適用例・転用例を残す。
- AI procedure: 手順を参考にするか、見直すかを選ぶ。
- History: 以前の選択と説明を見る。
- Portfolio: 自分で選んだ自己申告を、AIとの共同制作として書き出す。

Owner欄には本人が選んだ盤面の一部を表示します。詳しい一覧はMy skillsへ降りられます。
手順の表示・盤面の編集・履歴の閲覧だけではAIを呼びません。

## CLIの入口

~~~sh
verantyx setup skills
verantyx my-skills
verantyx my-skills show --json
verantyx my-skills board --json
verantyx my-skills show --search Flask --page 0 --json
~~~

自動化から本人の明示選択を記録する場合は、一覧に出た実在のIDを指定します。

~~~sh
verantyx my-skills choose --id SKILL_ID --plan NEXT_TIME
verantyx my-skills choose --id SKILL_ID --human EXPLAINED --text "自分の説明"
verantyx my-skills choose --id SKILL_ID --ai-use REFERENCE
verantyx my-skills choose --id SKILL_ID --share yes
verantyx my-skills history --id SKILL_ID --json
verantyx my-skills export --select SKILL_ID --output /absolute/path/my-selected-skill.json
~~~

学習確認を後回しにする設定:

~~~sh
verantyx my-skills quiet --scope TODAY
~~~

SESSIONはそのCLIプロセスだけです。後続の別コマンドにも適用する場合はTODAYまたはGLOBALを使います。
My paceから提案量・重さ・質問の設定を戻せます。この操作は実行・送信・公開の承認をバイパスしません。

## 保存と次のプロジェクト

生成した手順の正本は、プロジェクトのReflectionイベントです。
整理AIが有効で、実際に候補を返した場合にだけ作成します。
整理なし、整理失敗、候補なしの場合は、仕事の記録を保持し、意味をキーワードで捏造しません。

個人ノートが有効な場合、候補は個人カタログにも自動収録します。
無効な場合もプロジェクトの候補は残ります。後から明示的に収録できます。

~~~sh
verantyx my-skills sync --yes
~~~

個人カタログと本人の進捗は、同じOSユーザーの個人ノートに保存します。
クラウド同期、他のMacへの自動同期、社員情報の組織共有は行いません。
AIへ渡す個人記録には、全体の共有設定と項目単位の共有選択の両方が必要です。
現在のプロジェクトに元から存在する作業・候補の来歴は、個人共有とは別のプロジェクト文脈です。

同じ技術の次の仕事では、共有された本人の選択・説明・実例をAIが参照できます。
別の言語を知っているからといって、新しい言語を習得済みにしません。
新しい手順は別版として残り、以前の版や本人の習得記録を上書きしません。
続きの手順であることをAIが提案しても、習得状態は自動で移しません。

累積保存件数に製品上の固定上限は設けていません。ただし端末容量は有限です。
1回の整理は最大8候補、通常0〜3候補を目安にし、モデル文脈・一覧は件数と容量を制限します。
一覧はページ送りで過去へ到達できます。文脈から省略した項目は消しません。
個人ノート全体の旧バックアップ経路には5,000件・8MBの上限があります。大規模な分割バックアップは未対応です。

## ハーネスは必要か

小さい実行ハーネスは必要です。ここでいうハーネスは、
文脈を渡す、提案を受け取る、許可されたツールを動かす、結果を戻す、停止・再開を扱う実行ループです。

Cleanroomには既にこの役割を担う内蔵ループがあります。
Veraの意味論や個人ノートを、外部エージェントフレームワークへ移す必要はありません。
通常利用は内蔵のままで構いません。

~~~text
Work proposal producer: builtin model adapter / trusted external process
             |
       WorkProposal
             |
Cleanroom host: tool permission -> execution -> receipt -> next turn
             |
       saved WorkResult
             |
selectable Reflection AI -> project procedures / personal notebook / my skill board
~~~

外部接続を選んでも、本人の習得や規則の有効化を外部プロセスの文章から確定しません。
作業結果と整理結果は別です。分類失敗で作業回答や候補を取り消しません。

## 外部ハーネスの接続

~~~sh
verantyx setup harness
verantyx setup harness --show --json
~~~

F2のWork harnessからも変更できます。設定を開くだけではモデルや外部プロセスを起動しません。
設定ファイルはプロジェクト内の.verantyx/work-harness.jsonです。

実装した接続は、既存の汎用コマンドアダプターを使う **JSON提案プロセス** です。
外部のエージェント全体へ任意ツール権限を移譲する方式ではありません。

アダプター設定の例:

~~~json
{
  "argv": ["/absolute/path/to/trusted-work-adapter"],
  "cwd": "/absolute/path/to/adapter-workspace",
  "inherit_env": []
}
~~~

これは形式の例であり、実在する接続や検証済みプログラムではありません。
実際のファイルを.verantyx/model-adapters配下に置き、setup harnessで信頼を明示して選びます。
シェル文字列ではなく、絶対パスの実行ファイルと引数配列を使います。
既存のプロセスアダプターはPATH、HOME、LANGなど一部環境を引き継ぎます。秘密隔離ではありません。

- stdin: verantyx.work-agent-request.v1のJSONを1件受け取る。
- stdout: verantyx.work-proposal.v1のJSONオブジェクトを1件返して終了する。
- status: CONTINUE / COMPLETE / NEEDS_OWNER。
- tool_requests: Cleanroomが公開しているツールへの提案。実行事実ではない。
- answer / owner_question / assumptions: 既存のWorkProposalスキーマに従う。
- ログはstdoutのJSONに混ぜない。対話型CLIをそのまま指定する方式ではない。
- タイムアウト、出力量、操作キー、開始済みで結果不明な呼び出しの扱いは既存の呼び出し台帳を使う。
- アダプター設定のハッシュを保存し、変更後は再選択を要求する。実行ファイル本体や依存パッケージの署名・固定までは行わない。

ReflectionのSame as Work AIは、Models設定の作業モデルを指します。
外部ハーネスのプロセスへ整理要求を自動送信しません。Reflectionは別設定またはOffを選べます。

**外部プロセスはOSサンドボックスではありません。**
そのプログラム自身が行うファイル操作、ネットワーク、ネイティブツール実行をCleanroomは阻止・観測できません。
信頼するアダプターだけを接続してください。タイムアウトやJSON検査は権限隔離の代わりになりません。

[外部OSSサンドボックスの接続境界](SANDBOX_BACKENDS.ja.md)を別に用意しています。
設定済みでも隔離を実証したことにはしません。外部プロセスを使う仕事の本体変更状態は未確認です。

## 今回の実装に含まれないもの

- AI手順を任意のシェルスクリプトへ変換し、無承認で自動実行する機能。
- 人間の理解をAIだけで認定する機能。
- Codex、Claude Code、OpenClawなどのネイティブハーネス全機能を、そのまま透過接続するアダプター。
- 外部ハーネスの内部ツール実行を独立検証済みreceiptへ変換する監視。
- 外部コードのOS隔離、秘密情報の完全隔離、依存バイナリの署名固定。
- 組織・社員への自動共有、能力ランキング、人事評価。
- 今回の経路の起動確認、実モデル試験、配布・GitHub公開。

最初に必要なのは、仕事を妨げずに経験が残る小さいループです。
高度な外部ハーネスは、そのループと人間の所有状態を壊さない交換可能な部品として後から追加できます。
