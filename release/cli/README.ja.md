# Verantyx CLI preview 0.7.4.dev1

AIと実用的な成果物を作り、判断と検証方法を自分の資産に残します。
自分が理解したい原理は学び、AIに任せる技能は条件と権限を分けて再利用します。

まず自分の作業ログから、モデルを呼ばずに学習候補と辞書を確認できます。認証後は固定二役で生成し、別の有限条件で検査する道へ進みます。原文取込み、二役の一致、有限検査、人間の理解、実行許可、採用は別の状態です。

## 配布対象と公開前の確認

- 初期対象はmacOS 26.0以上・Apple Silicon（arm64）です。最低OSは同梱CrossバイナリのLC_BUILD_VERSIONに基づきます。Windows・Intel Mac・Linuxは未検証です。
- Python 3.11以上が必要です。配布物はCLIのwheelとCrossバイナリを含みますが、Python本体や認証済みCodex環境を提供するものではありません。
- 未署名・未公証です。checksums検査は同梱ファイルの整合性確認であり、配布元の認証やコード署名・公証の代わりではありません。
- MITで公開する案はユーザー承認待ちのため、現段階はprivate packagingです。公開前に採用ライセンスとライセンス文、依存物・同梱Crossの必要な表記を確定してください。このREADMEはMIT許諾の確定や公開済み状態を宣言しません。
- 認証情報、利用者DB、秘密キー、個人の原文・台帳・生成履歴・回収bundleを公開配布物へ同梱しないことが条件です。個人データの非同梱確認は、機能テストとは別の公開前確認です。

## 1. 導入して作業projectを指定する

Python 3.11以上を利用できる環境で、展開した配布フォルダから実行します。

```sh
sh install.command
```

install.commandはchecksumsを検査し、この配布フォルダにローカルの.venvを作成して、wheelと依存パッケージをpipでインストールします。依存パッケージの取得には通信が必要です。「モデル不要」はインストールも通信不要という意味ではありません。

導入がエラーで止まった場合は、そのエラーを確認してください。checksums検査やOSの保護を無効化する手順は案内しません。未確認のPython・Codex導入コマンドもここでは追加しません。

同じ配布フォルダで、PROJECTを自分の作業フォルダの絶対パスへ置き換えます。

```sh
PROJECT="/absolute/path/to/my-work"
mkdir -p "$PROJECT"
./verantyx --project "$PROJECT" --lang ja setup
```

以後の起動も、この配布フォルダから行います。

```text
./verantyx --project PATH --lang ja <command>
```

--projectは毎回明示してください。launcherはPythonの-Iでcwd・PYTHONPATHの混入を避け、同梱Crossのパスを自動設定します。Pythonのimport経路の分離は、任意コードを安全に実行するsandboxとは別です。

## 2. 最初はモデル不要: 作業ログから辞書へ

自分の既存の作業ログをUTF-8テキストとして--inputに指定します。以下のwork-log.txtは、実際に存在する原文ファイルのパスへ置き換えてください。外部AIとの作業原文も入力できますが、公開用配布物へその原文を混ぜないでください。

```sh
./verantyx --project "$PROJECT" --lang ja develop "自分の作業ログから学習候補を整理する" \
  --input "$PROJECT/work-log.txt" --origin-project "$PROJECT" \
  --capture-mode assisted --key work-log-001
```

--inputとassistedまたはmanualによる取込みはモデルを呼びません。手動で候補を選びたい場合は、上の--capture-modeをmanualへ変更します。--keyは取込みの識別子であり認証キーではありません。別の取込みには別の識別子を使ってください。

取込み結果に表示されたrun IDを使います。

```sh
RUN_ID="取り込み結果に表示されたrun ID"
./verantyx --project "$PROJECT" --lang ja dictionary --run "$RUN_ID"
./verantyx --project "$PROJECT" --lang ja skills-report --run "$RUN_ID"
./verantyx --project "$PROJECT" --lang ja --json skills-stack --run "$RUN_ID"
SCOPE_ID="直前のskills-stackが返したscope.id"
./verantyx --project "$PROJECT" --lang ja --json skills-newsletter \
  --run "$RUN_ID" --scope-id "$SCOPE_ID" --output "$PROJECT/newsletter.md"
```

newsletterは上で作成したprojectディレクトリ直下へ保存します。--outputの相対パスは--projectではなくシェルcwd基準で、親ディレクトリは自動作成されません。例のように絶対パスと既存の親ディレクトリを指定してください。この形でのローカル出力は実測済みです。

この操作は公開サイトへの投稿ではありません。scope IDはrun IDではなく、対象範囲を表す別の値です。対象や履歴が変わったら、skills-stackから取得し直してください。

原文に「理解した」「承認済み」と書かれていても、取込みだけで検証・本人習熟・承認にはなりません。OWN/REVIEW/REFERENCE/DELEGATEも本人の関わり方であり、実行権限ではありません。

## 3. 認証後: 固定二役で生成して有限条件を検査する

モデル利用前に、既存のadapters接続設定と利用者自身のCodexログインが必要です。ログインは利用者の環境にある既存手順で完了してください。認証情報や認証済み環境をこの配布物から取り込むことはありません。

```sh
./verantyx --project "$PROJECT" --lang ja codex-config --directory "$PROJECT/adapters"
```

codex-configによる設定作成だけではログイン済みになりません。ログイン・既存接続設定を済ませてから、開発依頼を入力します。

```sh
./verantyx --project "$PROJECT" --lang ja develop
```

作成役・検査役は固定のgpt-5.3-codex-spark、reasoning lowです。モデル利用には利用者の契約・利用制限が適用されます。この経路のアプリ独自の生成量上限は撤廃済みで、新しいモデル選択・生成上限設定は追加していません。検証上限やタイムアウトをなくした意味ではありません。

1. 生成された候補とhandoffの判定を確認します。MATCHEDでも意味的正しさや採用を確定したとは扱いません。
2. 生成後メニューの3から条件検査へ進みます。既存deliverの案内に従って、検査対象・独立した期待値・反例を確認します。固定JSON条件の検査と任意Pythonの実行は別の経路です。
3. 検査runの結果・方法・失敗をdictionaryとskills-reportで確認します。元の生成runと検査runを混同しないでください。不一致を勝手にMATCHEDや採用済みに変更しません。

接続設定後の利用状況は、同じadaptersディレクトリで確認します。

```sh
./verantyx --project "$PROJECT" --lang ja codex-usage --directory "$PROJECT/adapters"
```

### 有限JSON仕事の一括経路も実測済み

既存の`partner --mode implement --deliver`経路では、二役生成から有限検査・資産化までを一括で進められます。0.7.4.dev1では日本語4行の依頼でこの経路が完走し、英語の二段フローとともにCOMPLETE_BOUNDEDを確認しています。一括経路でも生成はモデルを呼ぶため、第2節のモデル不要取込みとは別です。

この日本語実行では引用8件の原文byte一致、既存代替案8件のID選択復元、Cross VMのMATCHEDを確認しました。allow_contested_handoffはfalseのままで、差戻しを例外扱いして通したものではありません。有限JSON条件3件と反例を検査し、元ファイルを変更せず、portable実行資産1件と学習候補1件を残しました。

引用・代替案のロスレス転送は意味の正しさを保証しません。既存代替案の選択拒否や新しい異論を一致へ補完せず、不一致として残す設計です。今回の有限な完走を全言語・全仕事の成功、本人習熟、source canonicalへの採用、UIや任意コードworkの完成とは扱いません。

### 回収モードの違い

| モード | 回収・抽出での追加AI呼出し |
|---|---|
| manual | なし。原文と候補を手動で扱う |
| assisted（既定） | なし。既存の抽出で候補を補助する |
| auto | 選択した仕事に対する二役の追加呼出しあり |

生成を依頼するdevelopは、assistedでもAIを呼びます。モデル不要なのは上記--inputによるassisted/manualの取込みです。autoの新規抽出は選択仕事の原文・判断文脈・規範を使い、通常開発の過去規則・検査資産の再利用とは別です。setupの--learning manual|digest|offは表示設定であり、この回収モードではありません。

## 4. 成功と失敗を同じ範囲で報告する

成功生成・条件検査・被覆失敗の3runをまとめ、skills-stackから得たscope IDでnewsletterのローカル出力へ接続した実測があります。手元にそれぞれのrunがある場合だけ、以下の値を実際のIDへ置き換えて使います。失敗runを作るためにモデルを追加で呼ぶ必要はありません。

```sh
GENERATED_RUN="成功生成のrun ID"
CHECKED_RUN="条件検査のrun ID"
FAILED_RUN="被覆失敗のrun ID"
./verantyx --project "$PROJECT" --lang ja --json skills-stack \
  --run "$GENERATED_RUN" --run "$CHECKED_RUN" --run "$FAILED_RUN"
SCOPE_ID="直前のskills-stackが返したscope.id"
./verantyx --project "$PROJECT" --lang ja --json skills-newsletter \
  --run "$GENERATED_RUN" --run "$CHECKED_RUN" --run "$FAILED_RUN" \
  --scope-id "$SCOPE_ID" --output "$PROJECT/newsletter.md"
```

両コマンドに同じ--run集合を指定します。1runだけを扱う場合は第2節の例で十分です。失敗の記録も資産であり、成功に書き換える必要はありません。

## 5. コピーした有限JSON検査を再利用する

コピーしたportable bundleでは、元DBと認証を使わず、model_calls=0、writes=falseで、元の固定契約に対する整数5をBOUNDED、文字列の"5"をREFUTEDと判別できました。型の違いを成功へ丸めた結果ではありません。これは学習辞書へ記録された有限JSON条件の再利用であり、任意コード実行ではありません。

既存replay.pyへ--bundleを渡す場合は、bundleディレクトリではなく、その中のmanifest.jsonを指定します。既存replay.pyは隣接するmanifest.jsonを既定で使えるため、その配置で--bundleを省略する使い方も成立します。既存のasset・対象入力の指定を使い、新しい実行器や認証情報を追加する必要はありません。

## 確認したことと、まだ主張しないこと

| 項目 | 今回の有限な確認結果 |
|---|---|
| 引用転送 | 引用IDと原文SHA-256を使って元リクエストから復元。Spark low二役の実通信で改行原文の完全保持を確認 |
| 二役生成 | ケース被覆不足を最初の実通信でREPAIR_REQUIREDとして検出。ケースIDと担当引用IDを固定した後はCANDIDATE_SAVED、handoff MATCHED、不一致なし |
| 生成の残る状態 | semantic_fidelity UNPROVEN、evidence UNVERIFIED、canonical_adopted false。状況・選択肢・期待値はモデル生成 |
| 別のdeliver検査 | COMPLETE_BOUNDED。独立JSON条件3件が一致し、retryの不一致入力を拒否。検査中のモデル呼出し0、元ファイル未変更 |
| 検査経験の回収 | portable実行資産1件・方法1件。human_mastery NOT_ASSESSED。学習辞書の所有対象は提案状態を保持 |
| 辞書からローカル報告 | 成功生成・検査・被覆失敗の3runを同じscopeでnewsletterへ接続 |
| 日本語一括経路 | partnerのimplement＋deliverでCOMPLETE_BOUNDED。Cross VM MATCHED、例外許容false、有限JSON条件3件と反例、元ファイル未変更 |
| 再利用・再送 | portable bundleは元DB・認証なしで整数と文字列の違いを判別。同じkeyのdevelop再送はduplicate:trueとなり同じ候補を再利用 |
| 局所テスト | focused tests 14件通過。広い全機能・全環境テストの通過を意味しない |

portable JSON条件の再利用とORACLEは別です。ORACLEの方法・範囲・出典・成功／反証／不明の履歴は辞書へ回収できますが、任意Pythonをportable replayから実行するものではありません。ORACLE再利用にはREQUIRES_FRESH_ORACLE_PLAN_AND_SANDBOXとして、新しい計画、明示対象、現在の観測、元エンジン、新規許可、利用可能なsandboxが必要です。

任意コードのwork採用は未完です。workのGit基準、固定テスト、個別の実行許可や実行器の条件は残っています。CLI開発・テストへの許可を、Git操作や任意コード実行への包括的許可に読み替えません。

既存oracleのmacOS sandboxでは、専用canaryへのproject外書込みと自作localhost listenerへの接続を各1回試し、権限拒否を観測しています。これは固定2ケースの観測であって、任意コード全般の安全性、秘密保持、sandbox脱出耐性の証明ではありません。Pythonの-Iとも別の境界です。

このpreviewは、全仕様・全経路の完走、一般的な正しさ、本人習熟、採用権限、公開済み状態を宣言しません。既存のstart、ask、partner、work、verify-*、oracle-*、command-*などの高度な経路は引き続き存在し、それぞれの条件に従います。
