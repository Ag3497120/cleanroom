# 外部サンドボックスとCleanroomの責任分担

CleanroomはOSサンドボックスを自作しません。
交換可能な SandboxBackend は、信頼する外部Work提案プロセスを起動する手前の境界です。

| Cleanroomで持つもの | 外部OSS・ランチャーで持つもの |
|---|---|
| 本人の選択、提案と実行の区別 | プロセス・コンテナ・VMの隔離 |
| ホストツールの許可範囲とreceipt | 実際のファイルマウントと書き込み制限 |
| 出典・設定ハッシュ・呼び出し来歴 | ネットワーク、秘密、子プロセスの隔離 |
| 判断・理解・スキルのローカル保存 | 対応OS、終了処理、資源制限の強制 |

## 観測していない変更を「未変更」と言わない

内蔵のホストツールだけを観測した場合も、「ホストの書き込みは候補領域のみ」という限定表示です。
外部Workハーネス、汎用コマンドモデルアダプター、観測情報のない古い仕事では、
本体の変更状態を UNKNOWN_EXTERNAL_EFFECTS とします。source_project_changed は null です。

これは「変更された」という断定でもありません。
変更がないことをファイルシステム全体で監査していない、という意味です。
外部プロセスが「触っていない」と返しても、この状態を自動で確認済みにしません。

## 接続の入口

~~~sh
verantyx setup harness
verantyx setup sandbox
verantyx setup sandbox --show --json
~~~

F2 > Sandbox backendからも選べます。設定表示・保存だけでプロセスは起動しません。
外部Workハーネスにだけ適用します。内蔵ハーネスのままサンドボックスを有効にすると、
適用されたふりをせず SANDBOX_REQUIRES_EXTERNAL_WORK_HARNESS で停止します。

設定は .verantyx/sandbox.json に保存されます。外部OSS用ランチャーの例:

~~~json
{
  "format": "verantyx.sandbox.v1",
  "mode": "command",
  "label": "My trusted OSS launcher",
  "argv_prefix": [
    "/absolute/path/to/trusted-oss-launcher",
    "--read-only", "{project}",
    "--read-write", "{candidate_root}",
    "--network", "deny",
    "--"
  ],
  "requested_policy": {"source": "read-only", "network": "deny"},
  "trusted_launcher": true
}
~~~

**これはランチャーの契約例であり、特定OSSへそのまま渡せる動作確認済みコマンドではありません。**
ランチャー側で、使用するコンテナ・VM・OS隔離機構の引数へ変換してください。
シェル文字列ではなくargv配列です。先頭は実行可能ファイルの絶対パスです。
projectとcandidate_rootはそれぞれ独立した引数内で展開し、後ろに外部ハーネスのargvを付けます。

展開して使う候補ワークスペースは .verantyx/workspaces 配下です。{candidate_root} と {workspace_root} が指します。
版ごとの不変な候補保存先は .verantyx/work-candidates 配下で、{candidate_store} が指します。
二つは別の実在する保存先です。原本の候補版を作業用マウントと混同しないでください。
ランチャーは、モデル実行ファイル・必要な依存・作業領域を実際にどうマウントするか、
ネットワークを許可する必要がある場合にどこへ許可するかを実装する必要があります。
requested_policyは意図の記録であり、Cleanroomが隔離を強制できた証拠ではありません。

## 安全性の表示

- 構成状態: REQUESTED_NOT_ATTESTED。設定があってもisolation_verifiedはfalseです。
- ランチャー不在・起動失敗時: 無隔離で再実行するフォールバックはありません。
- 外部のネイティブ操作: Cleanroomの実行receiptへ勝手に昇格しません。
- 設定の変更: ハッシュで来歴を分けます。バイナリや依存の署名・完全固定ではありません。
- Off: 外部プログラムは通常のOS権限で動きます。信頼できるものだけを選んでください。

この境界はモデルAPI、Reflection、検索アダプター、ホスト自身のツールを包括的に隔離しません。
環境変数、HOME、ソケット、マウント、ネットワークを含む秘密隔離は外部実装の責務です。
タイムアウトやJSON検査はOSの権限境界ではありません。

## 接続先を選ぶ時

LinuxのBubblewrapなど、隔離の部品となるOSSはありますが、
[公式README](https://github.com/containers/bubblewrap)でも、強制する安全方針は起動引数に依存すると説明されています。
Cleanroomはそれを「インストールしただけで安全」な部品として扱いません。
macOSでLinux向けツールをそのまま動かせるとも想定しません。
Docker/Podman/VM等の具体的な接続と対応OSの検証は、ランチャー実装ごとに必要です。

現在追加したのは汎用接続境界であり、各OSS専用アダプターや隔離証明機構ではありません。
外部ハーネスの内部ツール監視、OS横断の隔離保証、ネイティブな対話型CLIの透過接続は未対応です。
