# Vera Ownership MVP

Veraは、AIが実装の大部分を担う開発において、プロジェクトの目的、設計判断、検証方法、失敗、技術的理解を人間側へ残し、人間がプロジェクトを理解しながら一緒に育て続けられるようにする共同開発基盤です。AIが行った作業のうち、人間が判断すべきこと、理解すべきこと、参照できればよいこと、自動化して委譲できることを分離・可視化し、開発者の経験喪失と知的所有権の空洞化を防ぎます。

外部AIは交換可能な候補生成器・実装者です。Veraが所有するのは、AIの会話履歴ではなく、人間の目的、判断理由、検証、失敗、UNKNOWN、再利用規則、そして人間が後から回収する理解です。

## 最短の一周

```bash
verantyx --project . constitution-set \
  --purpose "AI実装を使いながら、設計判断と検証能力を人間側へ残す" \
  --non-negotiable "根拠不足を完成扱いしない" \
  --human-decision "公開範囲" \
  --human-decision "不可逆なデータ形式変更"

verantyx --project . develop "内部CLIの表示を改善する" --include src/example.py

verantyx --project . ownership RUN_ID
verantyx --project . constitution-gaps
```

`ownership RUN_ID` は、同じ仕事について次の六つを表示します。

1. Project Delta: 元ファイルの観測、未適用の候補差分、実行・統合で何が変わったか。候補には元観測と候補本文のハッシュが付き、元へ適用済みとは扱いません。
2. Human Decisions: 人間が選んだことと、今回限りの前提。
3. AI Decisions and Assumptions: AI候補・明示された仮定。明示されなければ未記録として残す。
4. Evidence and Unknowns: BUILD、EVIDENCE、OWNERSHIP、未解決判断。
5. Human Learning Delta: OWN、REVIEW、REFERENCE、DELEGATEの候補と選択。
6. System Delta: 検証資産、失敗事例、再利用候補。

この出力は履歴を読むだけで、モデル呼出し、ファイル書換え、現在の対象の再検査、実行許可の発行を行いません。

## 判断が残った場合

公開、削除、移行、互換性、権限、個人情報などを含む依頼は、AIが勝手に進めず、一つの判断ギャップとして保存されます。

```bash
verantyx --project . constitution-gaps
verantyx --project . constitution-resolve GAP_ID \
  --reason "公開APIは維持し、新しい挙動は別コマンドとして追加する"
```

今回だけの前提で進める場合は、恒久規則にせずに記録できます。

```bash
verantyx --project . develop "公開に関わる表示を調整する" \
  --assumption "今回はローカル開発用CLIだけを対象とし、公開APIは変更しない"
```

## 境界

- AI候補は、人間の決定でも検証済みの事実でもありません。
- 学習候補は、人間の習熟認定ではありません。
- 保存された検査は、現在のファイルを再検査した結果ではありません。
- Veraが扱えるのは、Vera経由の仕事と、明示的に取り込んだ外部AI記録です。
