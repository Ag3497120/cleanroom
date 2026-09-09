# mk-verantyx

AIとの仕事を、自分に残る判断と学びへ変える開発基盤。CLI型のWeb画面、本体の判断・検証・学習辞書、立体十字実行器を収録しています。

公開ページ: https://ag3497120.github.io/mk-verantyx/

## コードの構成

- `app/`, `lib/`: GitHub Pagesで公開するCLI型画面
- `compute_gateway.py`: 認証・Mac所有者の許可・利用制限
- [`core/`](core/): 提案、判断、検証、採用、再利用資産、人間の学習辞書
- [`cross/`](cross/): 立体十字構造と言語のC++実行器・標準ライブラリ
- [`execution/`](execution/): 隔離候補の実行・検査・統合を扱うPrecedent

一言で表すと、**AIとの仕事を、自分に残る判断と学びへ変える開発基盤**です。連携した作業の提案・判断・検証を区別して扱います。任意の外部AIの全作業を自動回収できる、または自然言語を完全に検証できるという意味ではありません。

本体の起動とコードの入口は[本体ガイド](core/docs/QUICKSTART.ja.md)を参照してください。

## 現在の公開状態

画面とMacのHTTPS通信経路を接続し、実際に導入済みのモデルを取得できます。GitHubログイン用アプリを登録し、公開HTTPS経由の本人認証とモデル一覧取得を確認しました。依頼はMac所有者が許可してから処理します。実モデルでの依頼完了はまだ検証していません。現在の接続は試用用Cloudflare Quick Tunnelで、再起動するとURLが変わります。

`/lang ja|en|zh-Hans|ko|es` で表示言語、接続後は `/models` と `/model inspection 番号`・`/model implementation 番号` で担当モデルを選択します。Enter送信、Ctrl+J改行、上下キーで履歴、Tab補完、複数行貼付に対応します。

## 配布

GitHub Actionsが型検査・lint・端末テスト・静的ビルドを行いGitHub Pagesへ配布します。`COMPUTE_GATEWAY_URL`というRepository variableを設定すると、そのHTTPS originへ接続します。空の場合は未接続画面を公開します。

ローカルの画面開発: `npm ci` → `npm run dev`。

## Macとの接続

このリポジトリにはWeb画面とGatewayに加え、Verantyx本体、.cross実行器、候補実行器を収録しています。`Open-Compute-Gateway.command`は本体の依存を導入して.crossをビルドします。別配置の本体を使う場合だけ`VERANTYX_HOME`を指定します。必要な項目はサイトURL、MacのHTTPS origin、device flowを有効にしたGitHub OAuthアプリのClient ID、所有者のGitHub数値IDです。

HTTPSトンネルはMacの127.0.0.1:8766に接続し、元のHostを保持します。8767の管理画面、Ollama、PTYは公開しません。`.gateway`内の設定・台帳・トークンはGitに含めません。

各依頼はGitHubログイン後、Macの許可ダイアログで所有者が許可した場合だけ処理します。アカウントごとに日本時間1日1依頼。別アカウントを使う同一人物を完全に識別する仕組みではありません。

ローカル2モデルはOllamaの総パラメータ合計40B以下に限定し、同一digestや数不明モデルは拒否します。RAM使用量の上限ではありません。公開経路は実装案と応答の返却までで、生成コードの実行・採用は行いません。

Sparkの個人サブスク接続は所有者本人のみです。[公式のPro案内](https://help.openai.com/en/articles/9793128-what-is-chatgpt-pro)に従い第三者向けのサブスク共有を提供しません。100人枠と通知処理を、公開Sparkサービスの稼働と解釈しないでください。通知メールはMac内で設定し、管理リンクは同じMacで開くためのものです。
