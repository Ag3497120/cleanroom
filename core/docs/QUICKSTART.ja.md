# Verantyx本体

AIと実用的な成果物を作り、判断と検証方法を自分の資産に残します。
自分が理解したい原理は学び、AIに任せる技能は条件と権限を分けて再利用します。

日常の開発入口は`develop`です。提案、人間の判断、実行許可、観測・検証、採用を分けて記録します。

## CLI preview 0.7.4の配布版から始める

初期対象はmacOS 26.0以上のApple Silicon（arm64）です。最低OSは同梱Crossバイナリの`LC_BUILD_VERSION`に基づきます。Python 3.11以上が必要です。Windows・Intel Mac・Linuxは未検証で、配布物は未署名・未公証です。MITでの公開はユーザー承認待ちであり、公開前にライセンスを確定する必要があります。

展開した配布フォルダで次を実行します。`install.command`はchecksumsを検査し、ローカルの`.venv`を作ってwheelと依存パッケージをpipで導入します。依存パッケージの取得には通信が必要です。

```sh
sh install.command
VERANTYX="$PWD/verantyx"
PROJECT="/absolute/path/to/project"
mkdir -p "$PROJECT"
"$VERANTYX" --project "$PROJECT" --lang ja setup
```

配布版の起動は`./verantyx --project PATH --lang ja <command>`です。`--project`は毎回明示してください。launcherはPythonの`-I`でcwd・`PYTHONPATH`の混入を避け、同梱Crossを自動設定します。これは任意コードのsandboxを意味しません。認証情報・利用者DB・秘密キーは配布物へ同梱しません。

配布版を導入した場合は、次のソース版準備を飛ばして「手動・assisted・autoの違い」へ進み、まずモデル不要の作業ログ取込みを試します。

## ソース版の準備（配布版では不要）

リポジトリのルートで、未導入の場合に次を実行します。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ./core -r requirements.txt
cmake -S cross -B cross/build -DCMAKE_BUILD_TYPE=Release
cmake --build cross/build -j 2
.venv/bin/python scripts/pin-cross-runtime.py
.venv/bin/verantyx --lang ja --help
```

同じリポジトリのルートで、`PROJECT`を作業対象の絶対パスへ置き換えます。`VERANTYX`はインストールしたCLIの絶対パスです。

```sh
VERANTYX="$PWD/.venv/bin/verantyx"
PROJECT="/absolute/path/to/project"
mkdir -p "$PROJECT"

"$VERANTYX" --project "$PROJECT" --lang ja setup
```

まず以下の`develop --input`で自分の作業ログから辞書を見る道を使えます。`assisted`または`manual`の原文取込みにはモデル接続設定やログインは不要です。認証後の生成は後述の別手順です。

別配置では`VERANTYX_CROSS`にcross実行器を指定します。候補実行器はリポジトリの`execution/`ですが、設定しただけで候補の実行や採用を許可するものではありません。

## 手動・assisted・autoの違い

回収・抽出のモードは`--capture-mode manual|assisted|auto`で指定します。既定は`assisted`です。これは`setup --learning manual|digest|off`による学習項目の表示設定とは別です。

| モード | 原文と学習候補の扱い | AI抽出の追加呼出し |
|---|---|---|
| `manual`（手動） | 原文を取り込み、本人が必要な候補を選ぶ | なし |
| `assisted`（既定） | 原文と既存の抽出で候補を補助する | なし |
| `auto` | 作成役・検査役で抽出候補を生成・確認する | 二役への追加呼出しあり |

この表は回収・抽出の追加呼出しについての説明です。成果物の生成を依頼する`develop`はAIを呼びます。`assisted`を「開発全体がモデル呼出しなし」と読み替えないでください。

`auto`の新規抽出は選択した仕事を対象とし、同じrunの原文・判断文脈・規範を保持します。通常の開発で過去の規則や検査資産を再利用する経路とは別で、作成役・検査役の二役構成も変えません。

モデルを呼ばずに始める場合は、自分の作業ログや外部AI作業の原文を保存したUTF-8テキストファイルを`--input`へ指定します。例のファイルは実際に存在する原文へ置き換え、別の取り込みには別の`--key`を使います。この`--key`は取込み識別子であり、認証キーではありません。

```sh
"$VERANTYX" --project "$PROJECT" --lang ja develop "自分の作業ログから学習候補を整理する" \
  --input "$PROJECT/work-log.txt" --origin-project "$PROJECT" \
  --capture-mode assisted --key work-log-001
```

`manual`または`auto`へ切り替える場合は`--capture-mode`の値を変えます。`auto`の追加呼出しには接続先の利用制限と失敗の可能性があります。原文取り込みのみは検証・本人習熟・承認ではありません。原文中の「理解した」「承認済み」も、引用だけで本人の判断や実行権限には昇格しません。

取込み結果のrun IDから辞書と報告を確認できます。モデル不要の入口はここまで接続しています。後述の`skills-stack`と`skills-newsletter`にも同じrun IDを渡せます。

```sh
RUN_ID="取り込み結果に表示されたrun ID"
"$VERANTYX" --project "$PROJECT" --lang ja dictionary --run "$RUN_ID"
"$VERANTYX" --project "$PROJECT" --lang ja skills-report --run "$RUN_ID"
```

## 認証後の二役生成: setup → codex-config → develop

モデル利用前に既存の接続設定を用意し、利用者自身のCodexログインを完了してください。認証済み環境は配布物に含みません。`codex-config`の設定作成だけでログイン済みにはなりません。Codex自体の導入・ログインは利用者の環境にある既存手順を使い、ここでは未確認の導入コマンドを追加しません。

```sh
"$VERANTYX" --project "$PROJECT" --lang ja codex-config --directory "$PROJECT/adapters"
# 利用者自身のCodexログインと既存接続設定を済ませてから実行します。
"$VERANTYX" --project "$PROJECT" --lang ja develop
```

`develop`で依頼を入力します。作成役と検査役は固定の`gpt-5.3-codex-spark`・low二役です。この経路のアプリ独自の生成量上限は撤廃済みで、新しいモデル選択や生成上限の設定は不要です。接続先の利用制限、入力・出力の検証上限、タイムアウトまでなくなったという意味ではありません。

## 生成後: メニュー3 → deliverの条件検査 → 辞書

1. `develop`へ依頼を入力し、生成された案と未解決事項を確認します。生成後はその仕事の画面へ進みます。終了しても、メインメニューの`3`から更新順の履歴を選んで再開できます。生成完了をテスト成功や採用完了とは扱いません。
2. 仕事の画面で`2`を選び、「保存したAI生成候補」と「プロジェクト内の現在のファイル」を区別してから条件検査へ進みます。生成候補を選ぶ場合は、既存のdeliver経路で新しい保存先の候補を検査し、元ファイルは変更しません。単一ファイルの候補が対象です。表示された期待値と対象を本人が確認して実行します。
3. 検査後は同じ仕事の画面へ戻り、別IDで保存した検査結果も表示します。仕事の画面の`3`から、その仕事と検査の学習候補・検査方法を選び、学ぶ・参照する・委譲する・条件を再利用する操作へ進めます。選択するまでは学習も委譲も強制しません。
4. 仕事の画面の`4`はBUILD・EVIDENCE・OWNERSHIPと出典の表示、`5`は関連する各runの資産回収、`6`は同じ範囲のニュースレター原稿です。表示だけでモデルや検査を再実行しません。有限検査が成功しても、親の生成記録や過去の失敗を成功へ書き換えません。

この操作はGit操作、任意コード実行、公開、元ファイルへの採用への包括的な許可ではありません。不一致や`REPAIR_REQUIRED`を勝手に解消せず、次に必要な条件を残します。

2026-09-13の接続変更では、後から行った条件検査の親run参照を既存の追記型台帳に保存します。この参照は画面移動のためで、承認や証明を追加するものではありません。過去の一括deliverで明示された検査IDも利用します。親の参照がない古い検査は推測で紐づけず、独立した履歴として表示します。新しい接続変更は実装段階で、起動・動作確認・テストはまだ行っていません。以下の過去の実測は、この変更後の動作保証ではありません。

複数行依頼の二役生成は`CANDIDATE_SAVED / MATCHED`まで実地成功しています。別に用意した独立JSON条件3件のdeliver検査は`COMPLETE_BOUNDED`となり、retryの不一致入力も拒否しました。検査中のモデル呼出しは0、元ファイルは未変更です。これは固定JSON条件の結果であり、任意Pythonの`work`採用や固定テストの全工程完走を示すものではありません。

有限JSON仕事では既存の`partner --mode implement --deliver`による一括経路も使えます。0.7.4で、英語の二段フローと日本語4行依頼の一括フローがともに`COMPLETE_BOUNDED`となりました。日本語一括は引用8件の原文byte一致、代替案8件のID選択復元、Cross VM `MATCHED`を確認し、`allow_contested_handoff=false`のままです。有限JSON条件3件と反例を検査して、元ファイル未変更でportable実行資産1件・学習候補1件を残しました。

これは局所的な実測です。一括生成はモデルを呼び、全言語対応・原文意味の証明・本人習熟・source canonicalへの採用を示すものではありません。代替案の選択拒否や新しい異論を、一致へ勝手に補完しません。

画面に出た生成runまたは検査runのIDを`RUN_ID`へ指定すれば、既存CLIからも辞書と報告を確認できます。生成と検査のrun IDを混同しないでください。

```sh
RUN_ID="画面に表示されたrun ID"
"$VERANTYX" --project "$PROJECT" --lang ja dictionary --run "$RUN_ID"
"$VERANTYX" --project "$PROJECT" --lang ja skills-report --run "$RUN_ID"
```

## 技能の範囲と利用状況を確認する

まず対象のrunを指定して`skills-stack`でscope idを得て、同じ`--run`と取得した`--scope-id`を`skills-newsletter`へ渡します。scope idはrun IDやプロジェクトIDとは別です。`skills-newsletter`では`--run`と`--scope-id`の両方が必須です。

```sh
RUN_ID="画面に表示されたrun ID"
"$VERANTYX" --project "$PROJECT" --lang ja skills-stack --run "$RUN_ID"
SCOPE_ID="skills-stackに表示されたscope id"
"$VERANTYX" --project "$PROJECT" --lang ja skills-newsletter --run "$RUN_ID" --scope-id "$SCOPE_ID" --output "$PROJECT/newsletter.md"
```

複数のrunを対象にする場合は、両コマンドへ同じ`--run`集合を指定してください。対象や履歴が変わったら、`skills-stack`からscope idを取得し直します。

`--output`の相対パスは`--project`ではなくシェルcwdが基準で、親ディレクトリは自動作成されません。例のように、既に存在するprojectディレクトリ直下の絶対パスを指定してください。この形式でのnewsletter保存は実測済みです。

成功生成・条件検査・被覆失敗の3runを同じ集合で指定し、newsletterのローカル出力まで接続できています。失敗runを成功へ書き換える必要はありません。OWN/REVIEW/REFERENCE/DELEGATEは本人の関わり方であり、実行権限ではありません。技能の再利用も適用範囲と既存の許可に従い、範囲外へ自動で拡張しません。

接続設定を済ませた場合だけ、利用状況を次で確認します。`codex-usage`には`codex-config`で用意した同じディレクトリを指定してください。

```sh
"$VERANTYX" --project "$PROJECT" --lang ja codex-usage --directory "$PROJECT/adapters"
```

## 現在の確認範囲と未解決

- 改行を含む生成元引用のstrict schema拒否は、引用IDと原文SHA-256を介して元リクエストから復元する方式へ修正しました。Spark low二役の実通信で改行原文の完全保持を確認しています。
- 最初の実通信では別のケース被覆不足をCross VMが`REPAIR_REQUIRED`として検出しました。ケースIDと担当引用IDを固定した後の実通信は`CANDIDATE_SAVED`、handoff `MATCHED`、不一致なしです。状況・選択肢・期待値は引き続きモデル生成であり、`semantic_fidelity=UNPROVEN`、`evidence=UNVERIFIED`、`canonical_adopted=false`です。
- 別の有限deliver検査は独立JSON条件3件に一致し、不一致入力を拒否しました。`COMPLETE_BOUNDED`、方法1件・portable実行資産1件、モデル呼出し0、元ファイル未変更です。`human_mastery=NOT_ASSESSED`で、学習辞書の所有対象は提案状態を保持しています。
- Python候補の固定入出力oracle観測と、その方法・結果・失敗の辞書への回収は確認済みです。ORACLEはportable JSON検査とは別で、再利用には`REQUIRES_FRESH_ORACLE_PLAN_AND_SANDBOX`として新規計画・明示対象・現在の観測・元エンジン・許可が必要です。任意Pythonの`work`採用は未完です。
- `work`のGit基準、`oracle`の入出力契約・隔離条件、`command`の非隔離実行への明示承認は別々の条件です。CLI開発・テストの許可をGit操作や任意コード実行の包括的許可へ読み替えません。
- 専用canaryへのproject外書込みと自作localhost listenerへの接続は、既存oracleのmacOS sandboxで各1回拒否を観測しました。固定2ケースの観測であり、一般的な安全性や秘密保持の証明ではありません。
- コピーしたportable bundleは元DB・認証なし、`model_calls=0`、`writes=false`で、固定契約に対する整数5を`BOUNDED`、文字列の"5"を`REFUTED`と判別しました。既存replayの`--bundle`にはディレクトリではなく`manifest.json`を指定します。隣接manifestを既定で使う既存`replay.py`の省略形も成立します。
- focused tests 14件の通過と、同じkeyでの`develop`再送が`duplicate:true`で同じ候補を再利用することを確認しています。広い全機能テストや全言語への保証ではありません。
- CLI previewはmacOS 26.0以上・arm64、Python 3.11以上が初期対象で、未署名・未公証です。MIT公開判断はユーザー承認待ちのため、現段階はprivate packagingです。この案内は一般公開済み、全仕様・全経路完走、本人習熟、一般的な正しさ、本体への採用許可を示しません。

## 高度なCLIはそのまま使う

`start`、`ask`、`partner`、`work`、`verify-*`、`oracle-*`、`command-*`、`authority-*`などの既存経路は残っています。通常は`develop`から始め、個別の判断・検証・採用が必要なときに使います。`verantyx --lang ja --help`には高度なCLIの一覧も掲載しています。

## 実装の入口

| 内容 | ソース |
|---|---|
| 依頼から提案・応答へ | `src/verantyx/responses.py` |
| 別の編集モデルとの連携 | `src/verantyx/coordination.py`, `shared_context.py` |
| 判断・出来事の保存と再生 | `storage/`, `kernel/`, `domain/` |
| 経験からの再利用候補・検証資産 | `assets.py`, `asset_workflow.py` |
| 人間の学習候補と理解確認 | `learning.py`と学習関連モジュール |
| 判断の適用範囲・取消・許可 | `authority.py`と判断・規則関連モジュール |
| 外部モデルの接続 | `model_api.py`, `adapters/` |

応答の保存だけで本人の理解を認定せず、生成された規則を自動的に証明済みと扱いません。公開Webの経路とCLI本体の採用権限は設計上分離しています。この案内は一般公開済みであることを示しません。

## 検査

一時プロジェクトと固定生成器を使うテストを`tests/`に収録しています。実モデルの意味精度を保証する試験ではありません。一部の統合検査はmacOSと別リポジトリcall-me-veraを必要とし、`VERANTYX_VERA_SOURCE`でその場所を指定します。過去のローカルパスを含むv0.3の履歴フィクスチャとその移行検査は公開対象から除外しています。実ユーザーの記憶・台帳・モデル認証情報は収録していません。
