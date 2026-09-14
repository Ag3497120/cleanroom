# CLI MVP: 成果物から判断と学習まで

最初の二つの思想を、一つの限定された仕事で最後まで通す入口です。
既存のモデルアダプター、Cross照合、追記型台帳、有限検証、学習辞書、回収パッケージを使います。

## 成果物の生成・検査・回収

    verantyx partner 'settings.json の enabled を false、retry_limit を整数の3にする' \
      --mode implement --deliver --target settings.json \
      --include settings.json \
      --expect 'JSON /enabled = false' --expect 'JSON /retry_limit = 3' \
      --reject-json '{"enabled":false,"retry_limit":4}' \
      --creator-adapter IMPLEMENTATION_JSON --reviewer-adapter VERIFICATION_JSON \
      --key UNIQUE_WORK_KEY

条件はモデル呼出し前に構文検査され、元の依頼と一緒に両役へ渡されます。
モデル二役が解釈を渡し合い、既存Crossの照合が一致しなければ公開や上書きをせず止まります。
例外として --allow-contested-handoff を明示すると、代替解釈の文章だけが不一致で、
他の有限チェックが一致した場合に限り、条件付き受け渡しを行えます。
解釈の照合はREPAIR_REQUIREDのままです。語句の同義性も、全体の正しさも認定しません。
依頼の扱い・強さ・依存関係・具体例の選択などの不一致は、この指定でも停止します。
生成物は vera-deliveries に新しい版として保存され、元ファイルは変更しません。
既存の有限検証で条件を検査し、判定・出典・方法・学習項目を台帳へ保存します。
COMPLETE_BOUNDEDは明示した条件での完了です。任意プログラムの全意味を証明しません。
この入口は一つの明示した対象ファイルを扱います。生成コードや任意コマンドは実行しません。

## 既存の仕事を、手書きの検証JSONなしに資産化

モデルが生成済みの候補を再利用する場合は、追加のモデル呼出しなしで実行できます。

    verantyx deliver WORK_ID --target settings.json \
      --expect 'JSON /enabled = false' --expect 'JSON /retry_limit = 3' \
      --expect 'JSON /label = "keep-me"' \
      --reject-json '{"enabled":false,"retry_limit":4,"label":"keep-me"}' \
      --reason '不一致を残し、依頼時に明示した条件だけを確認して受け取る' \
      --key UNIQUE_DELIVERY_KEY --allow-contested-handoff --execute

--execute なしはプレビューです。条件は候補の内容から推測せず、依頼時の条件を指定します。
成果物は vera-deliveries/WORK_ID/HASH/files/ に保存されます。
同じ版の handoff.json に照合結果・元の解釈・生成候補・承認範囲を残します。
COMPLETE_BOUNDEDでも正規ファイルへの採用、生成コードの実行、規則の自動昇格はしません。

    verantyx judge WORK_ID --target settings.json \
      --expect 'JSON /retry_limit = 3' \
      --reason '明示した仕様の値を、生成結果から推測せず確認する' \
      --key UNIQUE_CHECK_KEY --execute

--execute を外すと、契約の構文変換だけです。モデルも検査も起動しません。
既知の正解値や適用条件がない自由文は推測で実行規則にしません。
同じkeyの再要求は過去のレシートを返し、再実行しません。現在の結果を調べる場合は新しいkeyを明示します。

## 自分が持つ理解を選ぶ

judge に --ownership OWN|REVIEW|REFERENCE|DELEGATE と --ownership-reason を付けると、
同じ既存の学習台帳へ本人の選択として記録されます。省略時はREVIEWの候補で、本人の選択ではありません。
学習を委譲しても、コマンド実行やファイル上書きの許可にはなりません。
生成された学習項目には、今回の条件、なぜ必要か、反例、理解を確かめる問いが付きます。

## モデルなしの再利用

回収パッケージの replay.py は、元の会話DBやAI接続を使わず、同じ条件を別の明示対象へ適用します。
VerantyxをインストールしたPythonは必要です。過去の方針や権限は移転しません。

## 完了の範囲

このMVPは、外部AIの仕事から明示した判断と検証を資産化し、学習辞書へつなぐ閉ループです。
万能な自然言語コンパイラー、任意アプリの常時監視、全言語の自律コード実行、一般性能保証ではありません。
通常の partner / ask / start / work の既存経路を置き換えません。
