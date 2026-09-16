# Cleanroom

## 名前に込めた考え

私は日本語の「クリーンルーム」という言葉から、外部と隔てられ、人間の判断と理解を大切に保つ聖域のような場所を思い描き、このプロジェクトを始めました。これは一般的な辞書の定義ではなく、作者自身の命名の意図です。

AIを遠ざけるのではなく、作る仕事をAIと分担しながら、目的・選択・理解まで手放さないための共同開発空間が **Cleanroom** です。実装名前空間と起動コマンドは `verantyx`、中核の判断・来歴管理は Vera Kernel と呼びます。


AIが実装の大部分を担っても、人間に目的・設計判断・失敗・検証方法・理解が残る共同開発基盤です。更新候補: **0.7.5rc2**。

## 始める

Python 3.11以上を使用してください。リポジトリ直下から:

~~~sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./core
cd /absolute/path/to/your-project
verantyx setup
verantyx
~~~

### まず、操作を練習する

`verantyx setup`は矢印キーとEnterで選択する設定メニューです。言語、公式CLIアカウント、API、ローカルのOllamaモデルを設定できます。初めてメニューを閉じると、モデルを呼ばず、練習内容を仕事・メモ・学習記憶に残さないチュートリアルへ進めます。画面サイズの案内は警告のみで、進行を止めません。

~~~sh
verantyx tutorial
~~~

通常画面からは`/tutorial`でも練習できます。`/done`で終了します。

### 左はAgent、右はOwner

回答とシステム通知を分けて表示し、操作中の入力欄を太い枠とラベルで示します。設定中のモデルは上部で確認できます。

| 操作 | 動作 |
|---|---|
| 文章付きEnter | 送信。補完や設定の選択中は選択を優先 |
| 空欄Enter | Agent → 黄色のメモ → 緑色の検索 → Agent |
| Shift+Enter | 対応端末で改行。代替はAlt+Enter / Ctrl+J |
| ↑ / ↓ | 入力欄ごとのセッション履歴と元の下書き。複数行は先頭行・最終行で操作 |
| 項目の先頭文字 + 矢印 + Tab | Ownerの参照を依頼へ挿入 |
| `/model` / `/verantyx` | Agent欄内でモデルやその他の設定を開く |
| `/help` / F2 | 利用できる操作を表示 |

設定への回答は`/値`、通常の依頼へ戻るには`/`なしの文章を使います。設定と`//`対話は入力履歴に含めません。端末がShift+EnterをEnterと同じ信号で送る場合は、代替キーを使ってください。

`/attach "/path/to/file.pdf"`でPDF・画像を添付し、送信範囲を確認できます。PDFは`--text`で本文のみ、`--pages 1-3`でページを選択します。画像には視覚対応モデルが必要で、外部ハーネス経由の添付は未対応です。

`//相談内容`はツールを使わない一時対話です。Cleanroomの仕事・日記・スキル・学習記憶へ保存しませんが、接続先サービスの保存方針は別です。

[二分割画面・設定・添付・プライバシーの操作ガイド（5言語）](../docs/two-pane-interaction.md)



## ノートとモデルをつなぐ

実装中の説明を、その場の出典・プロフィール版とともに保存します。
Owner / Agent分割画面から記録を選び、技術名だけでなく元の出来事から解説を開けます。
Obsidianのvaultを最初のノート置き場にする、後から接続する、Cleanroom内だけで使う方法を選べます。

~~~sh
verantyx setup notebook
verantyx my-learning moments --json
verantyx setup roles
verantyx web
~~~

- WebはCLIの言語設定に従います。グラフは本人の経験、AI手順、作業記録を混ぜずに関連付けます。
- 他エージェントのSKILL.mdを原文・出典付きで取り込めます。スクリプトは実行せず、本人の習得済みとは扱いません。
- オプションのMCPサーバーで、他エージェントから実装途中の説明を残せます。個人情報の読取・書込は明示設定です。
- 親と助言用の子モデルを登録し、会話から変更を提案できます。送信先の変更は本人の確認後です。
- 続きの仕事へ出典付き文脈を注入し、長い入力は原文を消さずに容量調整します。

Obsidianは版付きの書き出しと明示的な取り込みです。台帳を置き換える双方向同期ではありません。
子モデルは助言用で、複数writerの自律実行ではありません。
詳しい操作、共有範囲、MCP設定、移植時の理解状態:
[日本語](docs/NOTEBOOK_CONNECTIONS.ja.md) / [English](docs/NOTEBOOK_CONNECTIONS.en.md)

## 実装の途中を残し、必要になった時に紐解く

スキルと技術スタックの説明を、仕事の終了後だけでなく作業ターンの途中から保存します。
当時の前提・手順・失敗条件と実際のツール記録を残し、本人の現在の共有プロフィールに合わせて
「要約」「詳しい解説」「元の記録」を選べます。解説の生成・閲覧を本人の習得とは数えません。

~~~sh
verantyx my-learning
verantyx my-learning unpack --technology Flask --send
verantyx my-learning show --id GUIDE_ID --detail full
verantyx web
~~~

F2の Learning guides、My skillsの Unpack からも利用できます。
本や資料の検索は本人が検索語を選んだ時だけ実行し、検索結果とAIの推薦理由を分けて保存します。
記録されなかった過去の説明、未観測の操作、資料の本文を知っているふりはしません。
[詳しい操作と共有範囲](docs/LEARNING_CONTINUITY.ja.md) / [English](docs/LEARNING_CONTINUITY.en.md)

### 隔離機構は外部OSSへ、判断と来歴はCleanroomへ

~~~sh
verantyx setup sandbox
verantyx setup sandbox --show --json
~~~

外部Workハーネスを信頼するOSSランチャーで包む接続境界を用意しています。
プロセス・ファイル・ネットワーク隔離は外部実装、権限・出典・本人の選択・資産保存はCleanroomの責務です。
各OSS用の完成済みランチャーを同梱したものではありません。
設定済みでも隔離検証済みとは表示せず、起動失敗時に無隔離へ切り替えません。
外部の副作用を観測できない仕事では「本体未変更」と断定せず、変更状態を未確認として表示します。
[責任分担・設定契約・限界](docs/SANDBOX_BACKENDS.ja.md) / [English](docs/SANDBOX_BACKENDS.en.md)

## My Atlas / 自分の経験を、Webで見渡す

~~~sh
verantyx web
verantyx web --no-open
verantyx --lang en web
~~~

本人の経験・説明・適用例・転用例を、技術と記録した月のドットマップで表示します。
点から実際の記録を開き、検索やプロジェクト名で絞り込めます。日本語・英語を画面内でも切り替えられます。

これは「未習得の一覧」や理解率ではありません。本人が取り組みたい・次の機会にと選んだ項目は、
期限のないしおりとして置きます。AIの手順、参照・委譲の選択は別の棚にし、本人の習得数に混ぜません。

127.0.0.1だけで動く読み取り専用画面です。既定では空いているポートを選び、
起動ごとの私的なURLで開きます。画面表示のためのAI呼び出し、クラウド送信、プロフィールの変更はありません。
CLIの起動はそのままにし、終了はCtrl+Cです。記録の追加はMy skills / My profileで行います。

空の画面は能力不足を意味しません。本人の記録がない、個人ノートに未収録、絞り込みに合わない場合があります。
技術や月を集約するグラフであり、技能認定や社員評価ではありません。
**ソース版の機能です。公開済み配布物への収録、実モデルの学習効果、全環境での動作を保証するものではありません。**

操作ガイド: [日本語](docs/OPERATIONS.ja.md) / [English](docs/OPERATIONS.en.md)。
背景資料: [日本語原文と英語版の資料庫](docs/origins/README.md)。X投稿とAIとの議論の本文は提供待ちです。

リポジトリ: [Ag3497120/cleanroom](https://github.com/Ag3497120/cleanroom)。起動コマンドは引き続きverantyxです。

## My Notebook / 自分の経験と日記

プロジェクトを越えた任意の自己申告、個人日記、学習の続きを追加しています。**この追加実装の起動・実モデル・回帰検証は未実施です。**

F2の My profile / My journal / Next time / My pace から操作できます。初回登録はスキップ可能です。委譲回数や説明の省略から能力を推定しません。AIによる更新は候補、本人の経験・理解の記録は自己申告、検査結果は実行記録として分離します。

~~~sh
verantyx setup profile
verantyx setup pace
verantyx my-profile show --json
verantyx my-journal
~~~

個人記録はmacOSの ~/Library/Application Support/Verantyx/Personal に保存し、共有を選んだ抜粋だけ次の仕事へ渡します。今日だけ静かにすること、参照・委譲・次回を選ぶこと、日記から自分の実績を選ぶことができます。学習候補の整理失敗は作業結果へ伝播させません。

[設定・日記・プライバシー・現在の限界](docs/PERSONAL_GROWTH.ja.md)

## My Skills / AIの手順と、自分が育てる盤面

AIが仕事から抽出した手順をまず仮保存し、本人は必要な項目だけ後から選びます。
AIの手順、本人の説明・適用例、参照・委譲の希望は別々です。
「このまま進める」「確認は後で」を、習得済みや実行権限に変換しません。

F2の **My skills** で、ビンゴのように必要な項目だけを並べられます。
完成率や全項目の習得は求めません。通常は仕事を進め、次の関連する仕事で少しずつ経験を残します。
個人ノートが有効ならプロジェクト共通のカタログへ収録し、共有を選んだ記録だけ次のAIへ渡します。

~~~sh
verantyx setup skills
verantyx my-skills
verantyx my-skills quiet --scope TODAY
verantyx setup harness
~~~

内蔵の作業ループを既定とし、信頼する外部JSON提案アダプターも選べる接続口を追加しました。
これはOS隔離や、外部エージェントの全機能の透過接続ではありません。
**今回のスキル・ハーネス経路はソース実装段階で、起動・実モデル・回帰検証・配布は未実施です。**

[二段階スキル、個人の盤面、ハーネスの設計と制約](docs/SKILLS_AND_HARNESSES.ja.md)

## 柔軟な見方と、消えない来歴

通常作業に多モデル合意や同じ分類の再現を要求しません。AIの整理は候補です。人間は理解・レビュー・参照・委譲を選び直せます。

~~~sh
verantyx organize RUN_ID --perspective "次に保守する人の観点"
verantyx perspectives RUN_ID
verantyx ownership RUN_ID
verantyx --json notebook
~~~

新しい整理では新しくAIを呼びます。同じキーの再送だけは過去の実行結果を再利用します。以前の見方や人間の選択は上書きしません。

## 検査記録

~~~sh
verantyx check RUN_ID --label "Unit tests" \
  --argv '["python3","-m","unittest","discover","-s","tests"]' --confirm
~~~

保存した候補のコピーに対する、明示許可付きのコマンド実行です。終了コードと対象版を記録します。**OSサンドボックスではないため、信頼できるコードだけを実行してください。** 実行環境のAPIキー変数は引き継ぎませんが、プロセスにはOSユーザーの権限が残ります。

## 範囲

作業結果、整理の成功、検査結果、人間の理解は別状態です。分類の失敗で回答を失敗扱いしません。個人メモは自動送信しません。次のAIには、共有を選んだ人間の判断・関わり方・メモを渡します。

任意コードの無人実行、本体への自動採用、Computer Use、完全な習熟判定は提供していません。

詳しい設定と制限は[リポジトリのREADME](../README.md)、[MVPの範囲](docs/PROVENANCE_MVP.ja.md)を参照してください。

## コマンドと外部作業ツール

```sh
verantyx commands
verantyx commands toolbox --json
verantyx toolbox status
verantyx toolbox configure --file toolbox.json --yes
```

一覧は実際のCLI登録情報から生成します。外部MCPは許可するサーバー・ツール・引数範囲を明示して接続します。作業AIは実装途中に登録済み検査を呼び、対象スナップショット・終了コード・出力を記録できます。検査には明示したOSSサンドボックスランチャーが必要で、起動失敗時に無隔離実行へ切り替えません。

接続済み・コマンド成功は、万能な隔離や製品全体の正しさの証明ではありません。実モデルの20課題評価は、未実施・接続不可・機能未対応と実際の合格を分けて報告します。

[実モデル・MCP・検査の操作](docs/LIVE_EVALUATION.ja.md) / [Live evaluation](docs/LIVE_EVALUATION.en.md)
