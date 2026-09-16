# 実装中の記録、Obsidian、他エージェントとの接続

Veraの目的は、人間を採点することではなく、AIが実装しても判断・経験・理解が手元に残ることです。
技術名は検索の入口です。解説の材料は実装中の説明、原文、実際のツール記録、本人が明示した希望です。

## 記録を作業中に残す

個人ノートを有効にすると、作業ターンごとに説明と実際の結果を別々に保存します。
モデルには共有を許したプロフィールと提案ペースを渡します。説明は任意で、生成されないターンもあります。
その場でモデルが明示した前提、手順、代替案、失敗条件を保存し、終了後の要約から復元したことにしません。
モデル内部の非公開思考を保存する機能ではありません。

~~~sh
verantyx my-profile enable
verantyx my-learning moments --json
verantyx my-learning unpack --moment MOMENT_ID --send
verantyx my-learning unpack --run RUN_ID --send
verantyx my-learning unpack --skill SKILL_ID --send
verantyx my-learning show --id GUIDE_ID --detail summary
verantyx my-learning show --id GUIDE_ID --detail full
verantyx my-learning show --id GUIDE_ID --detail sources
~~~

F2 > During work、Learning guidesから同じ記録を選べます。
技術タグがない記録、別プロジェクトやMCPから来た記録も、その記録自体から開けます。
整理AIが停止しても、作業・途中の説明・原文は消しません。
個人索引が失敗した場合は、プロジェクト側の元イベントから明示的に再索引できます。
その際、当時保存されなかったプロフィールは復元したと主張しません。

~~~sh
verantyx my-learning index --run RUN_ID --yes
verantyx my-learning record --moment MOMENT_ID --state NEXT_TIME \
  --text "次にこの境界を触るときに考えたい" --yes
~~~

本人の「説明できる」「使った」「今は疑問がある」「次回にする」「参照」「委譲」は明示発言として保存します。
未記録、スキップ、Git操作の委譲から能力不足を推測しません。
自己申告と独立した習熟確認は別です。この操作でスキルを自動認定しません。
共有は既定OFFで、--shareも選んだ記録だけが、個人プロフィール全体の共有設定に従って次回へ渡ります。

## Owner / Agent分割CLI

- Agentは通常どおり依頼と作業を扱います。
- OwnerのDuring workには、その時点で保存された説明を表示します。
- Owner項目は既存の入力候補から選び、必要なものだけAgentへ参照として渡せます。
- F2 > ConnectionsはObsidian、移植、MCPの入口です。
- F2 > Parent / child models、setup rolesでモデルの役割を設定できます。
- 理解状態の記録や資料の閲覧は、実行権限の承認ではありません。

## Obsidianから始める / 後で接続する

~~~sh
verantyx setup notebook
# または空のフォルダを初めのノート置き場にする
verantyx connections connect --vault /absolute/path/to/MyVault \
  --include-private --auto --yes
verantyx connections status --json
verantyx connections sync --yes
verantyx web
~~~

Obsidianで同じフォルダをvaultとして開いてください。アプリを自動インストールしたり、アカウントへログインしたりはしません。
接続後のWebグラフでは本人の記録、AIの手順、実装中の説明、技術タグを分け、Obsidianリンクから開けます。
グラフの線は記録上の関連であり、習得や能力のスコアではありません。

Cleanroom/recordsへ原文入りのMarkdownを版別に保存し、技術ノートとのWikiリンクを作ります。
既存版に手を加えていたら上書きせず、同期を保留します。自分の追記は別のノートからリンクする方法が安全です。
autoは今後の実装記録・解説・明示理解記録・移植の保存後にも書き出します。他の操作はsyncで反映できます。

**Obsidianは閲覧・関連付け・自分の追記の場所です。権威ある保存先は引き続きCleanroomのローカル台帳です。**
双方向の自動統合ではありません。Markdownを編集しても、人間の承認、AIの実行権限、習得状態へは昇格しません。
Localを選べば以後の書き出しを停止します。既に書き出したファイルは削除しません。

**プライバシー:** vaultには私的プロフィールを含む原文を出力します。
Obsidian Sync、iCloud、Git、別のプラグインが同期するフォルダなら、そのサービスにも渡り得ます。
そのため明示確認なしには接続しません。接続済みvaultの扱いは本人が管理してください。

## 他エージェントのスキルを移植する

~~~sh
verantyx skill-import /absolute/path/SKILL.md \
  --origin "Source agent / repository / revision" \
  --title "入力と副作用を分ける手順" --technology Python --yes
verantyx my-skills
~~~

受け取るのはMarkdownまたはテキストの手順です。原文・出典・ハッシュを保持します。
添付スクリプト、フック、エージェント権限、認証情報を実行・移植する機能ではありません。
文書に「習得済み」「承認済み」と書かれていても事実として採用しません。

初期状態はAI手順のDRAFTと、本人についてのNO_RECORDです。
NO_RECORDは「学んでいない」ではなく「ここで本人の記録がまだない」です。
既に知っていれば本人が説明・使用例を残せます。次回、参照、委譲も有効な選択です。
他製品の学習評価をそのまま本人の習熟証明に変換しません。
同じ原文と出典の再取り込みでは、既存の本人の選択をリセットしません。

## MCPで外部エージェントから使う

リポジトリ直下で追加依存を導入します。CLIだけなら不要です。

~~~sh
python -m pip install -e './core[mcp]'
verantyx --project /absolute/project mcp
~~~

stdioを扱えるMCPクライアントに、例えば次を設定します。commandはそのMacの実際の実行ファイルへ合わせます。

~~~json
{
  "mcpServers": {
    "cleanroom": {
      "command": "/absolute/cleanroom/.venv/bin/verantyx",
      "args": ["--project", "/absolute/project", "mcp", "--allow-personal", "--allow-import"]
    }
  }
}
~~~

- project_handoff: 指定プロジェクトの作業文脈を読む。
- list_learning_moments / read_learning_guide / read_skill: --allow-personalで個人ノートを読む。
- record_work_note: --allow-importで、実装の途中に外部AIの説明を追記する。
- import_skill: --allow-importで、外部手順を実行せず受け取る。

--allow-personalは私的なプロジェクト横断の記録への読み取り許可です。信頼する接続先だけに付けてください。
--allow-importは外部AIの報告を保存する許可であり、本人の発言や実行証拠を作る許可ではありません。
記録は外部報告として区別され、モデル名も外部が申告した値です。
同じsession/keyの再送は重複せず、異なる内容なら競合として拒否します。
任意シェル、習得認定、有効規則への昇格、承認生成ツールは公開しません。

この実装はCleanroomのMCPサーバーです。
任意の外部MCPサーバーをCleanroomの実行ツールへ取り込む汎用MCPクライアントではありません。

## Webの言語

~~~sh
verantyx setup language
verantyx web
# 今回だけ明示的に上書き
verantyx --lang en web
~~~

既定はプロジェクト設定に従います。APIには言語フラグを含めます。
画面内で言語を選び直した場合はその選択を優先し、選び直さなければ更新時もプロジェクトの言語へ追従します。
ラベルを切り替えても、本人の原文や保存済みAI解説を勝手に翻訳・上書きしません。
HTMLファイルをfile://で直接開くのではなく、webが発行した私的なローカルURLを使ってください。

## 親モデル・助言用の子モデル・自然言語での切り替え

~~~sh
verantyx setup models
verantyx model-roles register --alias main \
  --adapter .verantyx/model-adapters/CONNECTION/implementation.json --yes
verantyx model-roles register --alias adviser \
  --adapter .verantyx/model-adapters/OTHER/implementation.json --yes
verantyx model-roles set --role parent --alias main --yes
verantyx model-roles set --role child --alias adviser --yes
verantyx setup roles
verantyx model-roles show --json
~~~

アダプターのパスは例です。Modelsで保存された実際のパスを使ってください。
設定画面から現在の接続に短い名前を付けることもできます。
親をDefaultへ戻すと通常のWork設定に従います。子をDefaultへ戻すと子への呼び出しを無効にします。
登録時の設定ハッシュが変わった場合は再登録が必要です。秘密情報の値はこの登録へコピーしません。

Agentに「次からadviserを親にして」と頼むこともできます。
意味は作業AIが読み、request_model_changeを提案し、Ownerの確認後に次の呼び出しから切り替えます。
モデルの文章だけで変更は確定しません。外部送信先や料金の違いがあり得るためです。
非対話実行ではPENDING_OWNERとして残します。

子モデルはconsult_childを呼んだときの1回の助言です。
子のツール提案は実行しません。複数writerの並列エージェントや、外部ハーネス内部の子モデル制御ではありません。
汎用コマンドアダプター自体は信頼するプログラムである必要があります。

## 引き継ぎと圧縮

~~~sh
verantyx handoff RUN_ID --budget 60000 --json
~~~

通常の「続きを進める」経路では前回の目的、依頼、候補、出典付きイベントを新しいWork文脈へ入れます。
モデルを変えても元の記録は保持します。共有を取り消した私的プロフィールを自動再送しません。
大きな入力では古い入力イベントを省略し、省略した出典とハッシュを記録します。
原文を削除する圧縮ではなく、容量制限付きの入力投影です。LLM要約を真実へ昇格しません。
モデルはread_work_historyで現在または直前の作業の原文を取り直せます。1イベントの取得にも容量制限があります。
必須文脈が上限に収まらない場合は、制約を黙って消すのではなく容量制限を返します。

## 確認範囲と残るもの

ローカルの契約テストと実プロセス/stdio/HTTP試験は、保存・権限・参照・表示を確認するためのものです。
それだけでLLMの説明品質、実機Obsidian、全MCPクライアント、外部OSSの隔離を保証しません。
過去の未記録の判断理由の復元、個人能力の自動認定、完全な意味保存圧縮は対象外です。

関連: [学習記録](LEARNING_CONTINUITY.ja.md) / [外部サンドボックス](SANDBOX_BACKENDS.ja.md)
