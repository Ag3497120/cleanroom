# 学習を紐解く / 実装中の情報を残す

Cleanroomは、AIの手順を本人の習得と同じものにはしません。
身につけたいと本人が選んだ時に、手順の間に省略された前提・判断・失敗条件を、
元の仕事と結び付けて開きます。スキルにも技術スタックにも同じ入口を用意しています。

## 三つの情報を分ける

| 記録 | 意味 |
|---|---|
| 実装中の説明 | 作業AIが、その時点の共有プロフィールを参照して書いた説明候補 |
| 実行イベント | 実際に受け付けたツール、結果、候補内容、失敗、本人の回答 |
| 後からの紐解き | 選択した整理AIが作る学習案。記録にある説明と追加解説を区別 |

隠れた思考過程の収集ではありません。公開できる判断理由・前提・操作の説明を保存します。
「委譲した」「説明を求めなかった」「Git操作を頼んだ」から能力不足を推定しません。
解説を生成・閲覧しただけで、習得、理解、規則の有効化、実行権限は変わりません。

## 実装中に残すもの

Work AIへの依頼に任意の learning_notes を含めています。
原則0〜2件、1ターン最大4件の説明を、作業を止めずに保存できます。

- 対象スキル・技術、前提知識、具体的な中間手順。
- 採らなかった選択肢、失敗条件、確認方法案、小さな次の一歩。
- 実在する出典イベントと、参照した共有プロフィールの版のハッシュ。
- 元のWorkイベント。モデルの説明と実行receiptは別のまま保持。

学習ノートの形式が壊れていても、適正なWorkResultを失敗扱いしません。
元のイベントを残し、紐解き時には使えなかった説明を区別します。
説明が書かれなかった昔の仕事について、当時の理由を復元できたとは表示しません。

個人ノートを有効にすると、その作業イベントをプロジェクト共通の個人DBへ索引化します。
無効なら正本はプロジェクト内です。個人DBの保存に失敗してもプロジェクト側の作業は保持します。
後から次で明示的に索引を作れます。当時のプロフィールが欠けていれば補作しません。

~~~sh
verantyx my-learning index --run RUN_ID --yes
~~~

保存量は増えます。個人ノートの旧一括バックアップには5,000件・8MBの上限があり、
大量の作業イベントを収録したノートの分割バックアップはまだ実装していません。
元イベントを黙って削除して容量を合わせることはしません。

## 普段の操作

F2から Learning guides を選ぶか、My skillsで項目を開いて Unpack を選びます。
コマンド名を暗記する必要はありません。次の入口も利用できます。

~~~sh
verantyx my-learning
verantyx my-skills unpack --id SKILL_ID
verantyx my-learning topics --json
verantyx my-learning list --json
~~~

技術の一覧は、AIが実際の記録に付けた技術タグから作ります。
依頼文の単語で「これを学ぶべき」と分類するものではありません。
技術タグがない仕事も、RUN_IDで指定できます。

生成前に、送る記録の件数とページ範囲を示します。全文の送信内容も確認できます。
整理AIは設定で選んだモデルです。別モデルで新しい解説を作っても前の解説を上書きしません。

~~~sh
verantyx my-learning unpack --skill SKILL_ID --send
verantyx my-learning unpack --technology Flask --send
verantyx my-learning unpack --run RUN_ID --technology Swift --send
~~~

長い記録はイベント単位でページを分け、元の文章を切って要約に置き換えません。
対話メニューは先頭ページを扱います。続きは表示されたページ数に応じて --page 1 などで指定します。
単一イベントが送信予算を超える場合は、黙って切らず送信を止めます。
ページ外の知識や記録されなかった判断を把握したとは扱いません。

## 要約 / 詳しい解説 / 保存時の記録

~~~sh
verantyx my-learning show --id GUIDE_ID --detail summary
verantyx my-learning show --id GUIDE_ID --detail full
verantyx my-learning show --id GUIDE_ID --detail sources --json
verantyx web
~~~

- Summary: 負担を抑えた要点と次の機会。
- Full guide: 前提、省略手順、理由、試す例、確認方法、委譲してよい部分。
- Original records: その解説が使ったページの元イベント、ハッシュ、参照プロフィールの版。

My Atlasの「学びを紐解く」棚でも三つを切り替えられます。
Web画面と保存済み解説の閲覧は読み取り専用で、AIを再実行しません。
グラフの本人の経験とAIの解説は別です。「未習得の穴」や点数を増やしません。

全文とは「保存された説明・作業イベントの全文」です。
モデル内部の思考、外部ハーネスの未観測操作、当時記録しなかった情報の全文ではありません。

## プロフィールの共有

元のWork要求には、その時点で本人が共有を許可したプロフィールだけを入れます。
個人索引はその版をローカルに残します。
後から解説を作る際、昔共有していたプロフィール本文を理由なく再送しません。
現在共有されている本文と、過去版のハッシュ・現在も共有している参照だけを使います。

ただし、過去の作業説明自体に当時共有した内容が書かれている可能性があります。
共有解除は過去イベントの意味を自動的に消す操作ではありません。送信プレビューを確認してください。
個人ノートはプロジェクト外の私的領域であり、GitHubへ自動公開しません。
別Macや組織への自動同期、社員の能力認定はありません。

## 本・公式資料を探す

検索は任意です。本人が指定した検索語だけを検索先へ送り、プロジェクトの全文やプロフィールを
検索クエリへ自動変換しません。検索結果の本文をAI命令として扱わないよう分離しています。

~~~sh
verantyx my-learning unpack --technology Flask --send --web \
  --query "Flask official tutorial" \
  --query "Flask book author publisher"
~~~

既定の検索には環境変数 BRAVE_SEARCH_API_KEY が必要です。
検索で取得できた資料のIDだけを解説AIが推薦に使えます。
検索が使えない場合、架空の本で埋めず、解説と検索の失敗を分けて保存します。
検索結果のタイトル・URL・要旨・取得日時・検索提供元と、AIの推薦理由を区別します。
本文未読、版・価格・在庫未確認の結果を「確認済みの良書」と断定しません。

BraveのAPI認証と検索形式は[公式認証資料](https://api-dashboard.search.brave.com/documentation/guides/authentication)と
[公式検索API](https://api-dashboard.search.brave.com/api-reference/web/search/get)を参照しています。

独自のWeb検索スキルも、信頼するJSONアダプターとして接続できます。

~~~sh
verantyx my-learning unpack --run RUN_ID --send --web \
  --query "official documentation" \
  --search-adapter .verantyx/search-adapters/search.json --trust-search-adapter
~~~

アダプターは絶対パスの実行ファイルを指定する汎用コマンド設定です。

~~~json
{"argv":["/absolute/path/to/trusted-search-adapter"],"inherit_env":[]}
~~~

stdinは次の1件のJSON、stdoutは検索結果JSONだけにします。

~~~json
{"format":"verantyx.web-search.v1","query":"official documentation","limit":5}
~~~

~~~json
{"results":[{"title":"Observed title","url":"https://example.org/resource","description":"Observed snippet"}]}
~~~

これは汎用アダプター契約で、MCPサーバーをそのまま起動する設定ではありません。
信頼した検索プログラム自体はOS権限で動きます。Work用サンドボックスには含まれません。

## 限界

モデルが説明を残す品質や、本人に合った教材になるかは構造検査だけでは保証できません。
存在する出典IDであることは、その説明が意味的に正しいことの証明ではありません。
作業中の保存で要約による情報落ちは抑えますが、記録前に省略された情報は残りません。
学びは選択肢です。次回へ回す、参照に留める、委譲する選択で仕事を止めません。

## 接続・途中の理解記録・モデル引き継ぎ

[Obsidian / MCP / スキル移植 / 親子モデル / 言語と文脈の操作](NOTEBOOK_CONNECTIONS.ja.md)
