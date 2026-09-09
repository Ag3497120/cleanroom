# mk-verantyx

CLI型のWeb画面。依頼、実装案、再利用できる判断、任意の学習項目を扱うVerantyxへの接続画面です。

公開ページ: https://ag3497120.github.io/mk-verantyx/

## 現在の公開状態

画面を公開しています。MacへのHTTPS接続とGitHub OAuthアプリは未設定のため、AI処理はまだ実行されません。未接続と表示し、架空のモデル一覧や回答を返しません。

`/lang ja|en|zh-Hans|ko|es` で表示言語、接続後は `/models` と `/model inspection 番号`・`/model implementation 番号` で担当モデルを選択します。Enter送信、Ctrl+J改行、上下キーで履歴、Tab補完、複数行貼付に対応します。

## 配布

GitHub Actionsが型検査・lint・端末テスト・静的ビルドを行いGitHub Pagesへ配布します。`COMPUTE_GATEWAY_URL`というRepository variableを設定すると、そのHTTPS originへ接続します。空の場合は未接続画面を公開します。

ローカルの画面開発: `npm ci` → `npm run dev`。

## Macとの接続

このリポジトリはWeb画面と接続用Gatewayです。Macには別途Verantyx本体とその.cross実行器が必要です。`VERANTYX_HOME`にVerantyx本体のディレクトリを設定し、`Open-Compute-Gateway.command`から初回設定を行います。必要な項目はサイトURL、MacのHTTPS origin、device flowを有効にしたGitHub OAuthアプリのClient ID、所有者のGitHub数値IDです。

HTTPSトンネルはMacの127.0.0.1:8766に接続し、元のHostを保持します。8767の管理画面、Ollama、PTYは公開しません。`.gateway`内の設定・台帳・トークンはGitに含めません。

各依頼はGitHubログイン後、Macの許可ダイアログで所有者が許可した場合だけ処理します。アカウントごとに日本時間1日1依頼。別アカウントを使う同一人物を完全に識別する仕組みではありません。

ローカル2モデルはOllamaの総パラメータ合計40B以下に限定し、同一digestや数不明モデルは拒否します。RAM使用量の上限ではありません。公開経路は実装案と応答の返却までで、生成コードの実行・採用は行いません。

Sparkの個人サブスク接続は所有者本人のみです。[公式のPro案内](https://help.openai.com/en/articles/9793128-what-is-chatgpt-pro)に従い第三者向けのサブスク共有を提供しません。100人枠と通知処理を、公開Sparkサービスの稼働と解釈しないでください。通知メールはMac内で設定し、管理リンクは同じMacで開くためのものです。
