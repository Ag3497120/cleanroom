# Vera / Verantyx

> 更新候補: **0.7.5rc1**。起動・入力操作・Codex 応答取得の限定実演後に見つかった、空の憲章による不要な保留と、ファイルを変更しない回答を保存できない問題を修正しています。修正後の再実行・回帰・配布物検査は未実施で、安定版の動作保証ではありません。

通常の入口は `verantyx` です。Agent 側に依頼を入力し、Owner 側ではメモ・検索・参照選択を使えます。以下の個別コマンドは詳細操作向けです。回答候補は内容未検証のまま、変更候補とは分けて表示・保存します。

## AIに作らせても、開発者であることまで手放さない

Veraは、AIが実装の大部分を担う開発で、プロジェクトの目的、設計判断、検証方法、失敗、技術的理解を人間側へ残すためのローカルファーストCLIです。

外部AIは交換可能な候補生成器として扱います。Veraが保存するのは会話の要約ではなく、次回の作業で参照できるプロジェクト文脈、候補、判断、検証の範囲、失敗、学習候補、委譲候補です。

```text
AIによる候補生成
        |
        +-- 未適用候補として隔離保存
        +-- 人間が決めたこと / AIが仮定したことを分離
        +-- 検証済み / UNKNOWN / 未確認を分離
        +-- 学ぶ価値があること / 参照でよいこと / 委譲できることを分離
        `-- 次回から使える規則・検査・失敗記録として残す
```

## MVPでできること

- `constitution-set`: プロジェクトの目的、守る条件、人間が保持する判断をローカルに記録する。
- `develop`: 二役の外部AIへ候補生成を頼み、元ファイルを変更せずに候補を隔離保存する。
- `ownership RUN_ID`: 一つの作業を、`Project Delta`、`Human Decisions`、`AI Decisions and Assumptions`、`Evidence and Unknowns`、`Human Learning Delta`、`System Delta` の六面から表示する。
- `constitution-gaps`: 公開・削除・移行・互換性・権限・個人情報など、AIだけで決めない判断を一件の質問として残す。
- 学習候補: `OWN`、`REVIEW`、`REFERENCE`、`DELEGATE` を、人間の選択とAIの提案として混同せずに扱う。
- 候補実行: 明示的な許可と固定された検査契約がある場合にだけ、元の作業場所とは別のworktreeで扱う。

## 最短の一周

Python 3.11以上を用意したうえで、プロジェクトの外側または仮想環境でインストールします。

```bash
python -m pip install .

verantyx --project ./my-project setup --non-interactive \
  --name "My project" \
  --purpose "AI実装を使いながら、設計判断と検証能力を人間側へ残す" \
  --learning digest

verantyx --project ./my-project constitution-set \
  --purpose "AI実装を使いながら、設計判断と検証能力を人間側へ残す" \
  --non-negotiable "根拠不足を完成扱いしない" \
  --human-decision "公開範囲" \
  --human-decision "不可逆なデータ形式変更"

verantyx --project ./my-project develop \
  "src/example.py のCLI表示を改善する候補を作成する。元ファイルへは適用しない。" \
  --include src/example.py

verantyx --project ./my-project ownership RUN_ID
```

`develop` はAIの候補を `.verantyx` と候補ディレクトリへ保存します。元ファイルへ勝手に適用しません。`ownership` は再度AIを呼ばず、保存済みの出典を読むだけです。

外部AIを使わず、過去の作業ログや他サービスの回答から始めることもできます。

```bash
verantyx --project ./my-project develop \
  "外部AI作業を人間側の資産へ回収する" \
  --input ./work-log.txt --origin-project external-ai \
  --capture-mode assisted --key imported-work-001
```

詳細は [MVPガイド](docs/OWNERSHIP_MVP.ja.md) と [CLIガイド](docs/QUICKSTART.ja.md) を参照してください。

## 安全性と正確さの境界

- AI候補、AIの説明、AIが暗黙に置いた前提は、人間の決定や検証済みの事実ではありません。
- `BUILD`、`EVIDENCE`、`OWNERSHIP` は別の状態です。候補が保存されても、正しさや人間の理解を証明しません。
- `UNKNOWN` は推測で埋めません。高影響の判断は、既存の憲章に根拠がない限り判断ギャップとして止めます。
- worktreeは候補の作業場所を分けますが、外部サービス、秘密情報、最終統合まで自動的に安全にするものではありません。
- このMVPはローカル記録と明示的な接続設定を前提にします。外部モデルの認証情報・利用枠・会話履歴を配布物へ含めません。

## 現在のMVPの範囲

このリポジトリは、候補の生成・隔離・記録・所有状態の可視化・判断ギャップ・学習候補を一つの流れで提供します。

まだ一般化を主張しない範囲も明示します。

- AIの自然言語の説明が、要求やコードの意味を完全に満たすことを自動証明しません。
- 通常の候補生成は単一の候補を扱います。複数案の比較と最終統合は、既存の隔離候補・adoption・integration経路を使う明示的な作業です。
- `ownership` の表示は保存済みの履歴です。現在のファイルを再検査したり、実行権限を付与したりしません。
- 人間が理解したかどうかは、固定された演習・本人の選択・実際の適用記録なしに推定しません。

これらの境界は不足を隠すためではなく、AIが作業したこと、検証されたこと、人間が所有することを混ぜないための設計です。

## 開発時の確認

```bash
PYTHONPATH=src:tests python -m unittest -v \
  tests/test_ownership_mvp.py \
  tests/test_personal_skills_mvp.py \
  tests/test_recovery_bundle_mvp.py \
  tests/test_experience_report_cli.py
python -m pip wheel --no-deps --wheel-dir ./dist .
```

ライセンスおよび公開形態は、プロジェクト所有者が別途決定します。Veraは、その判断自体もAIの暗黙の選択へ委ねない設計を取ります。
