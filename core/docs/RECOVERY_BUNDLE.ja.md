# 判断回収パッケージ

目的は、外部AIの仕事が会話だけで終わらず、再実行できる検証方法と、人間に残す理解を残すことです。

## 既存CLIへの接続

- partner の相談・実装後に自動保存します。
- skills-import / skills-build の後にも、同じ既存台帳から自動保存します。
- work の実行後は、結果と失敗を含めた版を自動保存します。
- 過去の仕事には recover RUN_ID を使います。モデル呼出しはありません。

保存先はプロジェクト内の vera-recovery/RUN_ID/CONTENT_HASH/ です。
manifest.json、README.md、replay.py、最後に完了レシートの receipt.json を保存します。
既存のファイルは上書きしません。保存失敗は INCOMPLETE として返し、元の仕事の結果を隠したりAIを再度呼んだりしません。

## 再実行

VerantyxをインストールしたPythonで実行します。元のプロジェクトDBやモデルへの接続は不要です。

    python replay.py --list
    python replay.py --asset ASSET_ID --root TARGET_DIRECTORY --target RELATIVE_FILE

既存の有限述語エンジンを使用します。期待値や負例をモデルに生成し直させません。
json.equals / json.type / text.equals / text.contains / bytes.sha256 / bytes.size に対応します。
TEST と NEGATIVE_CONTROL が対象です。他の契約は消さず、元の実行器が必要な資産として残します。
再実行は読み取り専用で、任意のコマンド、Pythonコード、ネットワーク、修復は実行しません。

## 二つの軸

学習辞書は learn / reference / delegate に分かれます。
DELEGATEの候補を本人が選択済みのものとして扱いません。
学習対象の選択と、保存済みの実行方針は別です。パッケージを共有しても権限は移転しません。

## 未実装を混ぜない

自然言語の候補しかない場合は NO_PORTABLE_EXECUTABLE_CONTRACT と明示します。
任意の自然言語を安全な実行契約に自動変換したとは主張しません。
有限検証の成功は自然言語の主張全体や、人間の習熟の証明ではありません。
このパッケージはローカルの私的データです。判断理由や教材の公開前確認は必要です。
ハッシュは改変検知であり署名ではありません。元の台帳にある出典と失敗の鎖を維持します。
任意の外部AIアプリを常時監視する機能ではなく、既存カーネル経由の仕事と明示取り込みを対象にします。
