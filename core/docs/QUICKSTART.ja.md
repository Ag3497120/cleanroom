# Verantyx本体

AIの提案、人間の判断、実行許可、観測・検証、採用を分けて記録するCLIです。判断と失敗を再利用候補へ、本人が身につけたい原理を任意の学習候補へ残します。

リポジトリのルートで次を実行します。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ./core -r requirements.txt
cmake -S cross -B cross/build -DCMAKE_BUILD_TYPE=Release
cmake --build cross/build -j 2
.venv/bin/python scripts/pin-cross-runtime.py
.venv/bin/verantyx --help
```

作業対象のフォルダで`verantyx setup`を実行し、`verantyx start`で対話を始めます。インストール先をPATHへ追加するか、上で作った.venv内の絶対パスを使います。別配置では`VERANTYX_CROSS`にcross実行器を指定します。候補実行器はルートの`execution/`です。

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

応答の保存だけで本人の理解を認定せず、生成された規則を自動的に証明済みと扱いません。公開Webの経路は提案・実装案の返却までで、CLI本体の採用権限とは分かれています。

## 検査

一時プロジェクトと固定生成器を使うテストを`tests/`に収録しています。実モデルの意味精度を保証する試験ではありません。一部の統合検査はmacOSと別リポジトリcall-me-veraを必要とし、`VERANTYX_VERA_SOURCE`でその場所を指定します。過去のローカルパスを含むv0.3の履歴フィクスチャとその移行検査は公開対象から除外しています。実ユーザーの記憶・台帳・モデル認証情報は収録していません。
