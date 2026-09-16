# 実モデルと外部ツールの検証

製品名は Cleanroom、中核は Vera Kernel、CLI/実装名前空間は verantyx です。

## コマンドを覚えずに探す

~~~sh
verantyx commands
verantyx commands develop --json
verantyx commands toolbox --json
~~~

実際に登録されたコマンドから一覧を作ります。引数不足のコマンドを
手当たり次第に実行する機能ではありません。

## 外部MCPを作業中に利用する

CleanroomのMCPサーバーと、外部MCPを呼ぶクライアントは別機能です。
toolbox configureで、信頼した起動コマンド、公開するツール名、
任意の引数JSON Schema制約をプロジェクトへ保存します。
接続プロセスは信頼境界の外です。ツールの自己申告のread-only属性を権限にはしません。
認証済みブラウザや個人環境変数は自動継承しません。

~~~json
{
  "format": "cleanroom.toolbox.v1",
  "write_candidates": true,
  "checks": {},
  "sandbox": null,
  "mcp_servers": {
    "search": {
      "argv": ["/absolute/path/duckduckgo-mcp-server"],
      "tools": ["search"],
      "argument_schemas": {},
      "timeout": 30,
      "env": {}
    }
  }
}
~~~

~~~sh
verantyx toolbox configure --file toolbox.json --yes
verantyx toolbox list --server search --yes
verantyx toolbox call --server search --tool search --arguments '{"query":"Python asyncio official documentation","max_results":3}' --yes
~~~

通常作業ではAIが list_mcp_tools / call_mcp を提案します。
同じ作業の間は接続を保持し、呼出結果と許可設定ハッシュを記録します。
MCPの画像は原本を保存しますが、現在のJSONテキスト経路ではモデルへ画素を渡しません。
ブラウザのDOM・アクセシビリティ情報と、画像そのものを見たことを混同しません。
外部ツールの失敗を、テスト合格や人間の理解済みに変換しません。

## 実装途中の検査

検査名と完全なargvを登録します。モデルは任意のシェル文字列を渡せません。
AI生成コードの実行に伴う隔離は、信頼した外部OSSに委ねます。

~~~json
{
  "format": "cleanroom.toolbox.v1",
  "write_candidates": true,
  "checks": {"tests": {"argv": ["/absolute/path/python3", "-m", "unittest", "discover", "-s", "tests"], "timeout": 30}},
  "sandbox": {
    "argv_prefix": ["/absolute/path/srt", "--settings", "{policy}", "--"],
    "allow_read": ["/absolute/path/required-runtime"]
  },
  "mcp_servers": {}
}
~~~

{policy} はホストが生成する一時JSONです。ネットワーク拒否、
入力コピー以外への書込み禁止、個人ディレクトリの読取制限を要求します。
allow_read は実行環境に必要な最小限のパスだけを指定してください。
ランチャーがこの設定を守ることは別の実機検証で確認する必要があります。
起動できなければ無隔離実行に戻りません。

検査は元プロジェクトでなく、許可された入力と最新候補の使い捨てコピーに対して実行します。
対象のハッシュ、終了コード、stdout、stderr、上限と適用範囲を保存します。
Owner画面では実行記録として表示し、候補が変わった古い検査は現在版の合格に数えません。
読取専用課題では write_candidates: false を本人が明示設定できます。
文章からコードが「変更禁止」を推測する分類器ではありません。

## 評価結果の読み方

- モデル接続の拒否は、実装課題の合格ではありません。
- MCP初期化と実際の検索結果取得は別に記録します。
- 学習の候補生成と、人間が習得したという自己申告を分けます。
- 自動テストの合格と、意味の適切さ・実利用品質の確認を分けます。
- モデル交換は名前だけでなく、各ターンのモデル・元イベント・候補保存を確認します。
- 本番デプロイ、実Downloads整理、無許可の削除は評価用fixtureで代替します。

OSS: [Playwright MCP](https://github.com/microsoft/playwright-mcp),
[DuckDuckGo MCP](https://github.com/nickclyde/duckduckgo-mcp-server),
[Anthropic Sandbox Runtime](https://github.com/anthropics/sandbox-runtime)。
