"""Bounded local newsletter drafts from supplied records, with no I/O or models."""
from html import escape

MAX_WORKS, MAX_ITEMS, MAX_REFS = 12, 8, 16
MAX_TEXT, MAX_CONTENT = 1000, 40000


def _text(value):
    if value is None:
        return "未記録"
    if type(value) not in (str, int, float, bool):
        return "[表示できない値の形式]"
    raw = str(value)
    clipped = raw[:MAX_TEXT].replace("\r\n", "\n").replace("\r", "\n")
    clipped = "".join(c for c in clipped if (c in "\n\t" or ord(c) >= 32)
                      and c not in "\x7f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
    return clipped + (" [文字数上限により省略]" if len(raw) > MAX_TEXT else "")


def render(snapshot, *, title, format="markdown"):
    """Render markdown/html; missing optional fields remain explicitly unrecorded.

    Bounds apply to records, references, field text and total content characters.
    Markdown uses only generated headings and indented literal source blocks;
    HTML escapes every displayed value. Neither format creates active links.
    """
    if format not in ("markdown", "html"):
        raise ValueError("format must be markdown or html")
    if (type(snapshot) is not dict or type(snapshot.get("scope")) is not dict
            or type(snapshot.get("works")) is not list or type(title) is not str):
        raise ValueError("snapshot requires scope dict and works list; title must be text")
    blocks, remaining, truncated = [], MAX_CONTENT, False

    def add(kind, value):
        nonlocal remaining, truncated
        if len(value) > remaining:
            value, truncated = value[:remaining], True
        remaining -= len(value)
        if value:
            blocks.append((kind, value))

    def field(label, value):
        add("record", label + ": " + _text(value))

    def refs(label, values):
        if values is None or values == []:
            field(label, None)
        elif type(values) is not list:
            add("record", label + ": [参照リストの形式が不正です]")
        else:
            for value in values[:MAX_REFS]:
                field(label, value)
            if len(values) > MAX_REFS:
                add("note", "参照一覧: " + str(len(values) - MAX_REFS) + "件を表示上限により省略。")

    add("h1", "スキル便り / ローカル下書き")
    field("タイトル", title)
    add("note", "選択された記録を整理した下書きです。生成時のモデル呼出し・検証実行・公開はありません。")
    add("note", "OWN/REVIEW/REFERENCE/DELEGATE は保有したい知識や委ねたい判断の対象です。習得や実行権限を認定しません。")
    add("h2", "選択した範囲と出典")
    scope = snapshot["scope"]
    field("範囲 ID", scope.get("id"))
    field("プロジェクト ID", scope.get("project_id"))
    refs("対象 run ID", scope.get("run_ids"))
    refs("範囲の出典", scope.get("source_refs"))
    if "model_called" in snapshot:
        field("入力に記録された model_called", snapshot["model_called"])
    sections = (
        ("skills", "学ぶこと・委ねる判断", (("id", "ID"), ("concept", "概念"),
         ("ownership_target", "保有・委任の対象"), ("minimum_model", "理解の手掛かり"),
         ("counterexample", "反例"), ("check", "自分で確かめる問い（任意）"))),
        ("judgments", "記録された人間の判断", (("point_id", "判断 ID"),
         ("choice", "選択"), ("reason", "理由"))),
        ("methods", "記録された実行契約（合格結果とは別）", (("id", "方法 ID"),
         ("name", "方法名"), ("family", "分類"), ("status", "記録された状態"))),
        ("failures", "保持する失敗・未確定結果", (("id", "失敗 ID"), ("reason", "理由"),
         ("outcome", "記録された結果"), ("closure", "検証の到達点"))),
        ("candidates", "未検証の候補（実行契約ではありません）", (("id", "候補 ID"),
         ("title", "候補名"), ("situation", "適用する状況の案"),
         ("procedure", "手順の案"), ("counterexample", "反例の案"))),
    )
    works = snapshot["works"]
    if not works:
        add("note", "この入力には作業の記録がありません。")
    for index, work in enumerate(works[:MAX_WORKS], 1):
        add("h2", "作業 " + str(index))
        if type(work) is not dict:
            add("note", "作業の形式が不正なため表示できません。")
            continue
        field("run ID", work.get("run_id"))
        field("作業名", work.get("label"))
        refs("作業の出典", work.get("source_refs"))
        for key, heading, fields in sections:
            add("h3", heading)
            rows = work.get(key, [])
            if type(rows) is not list:
                add("note", "記録リストの形式が不正なため表示できません。")
                continue
            if not rows:
                add("note", "この入力には実行契約がありません。" if key == "methods" else "この入力には記録がありません。")
            if key == "methods" and rows:
                add("note", "契約や状態の記録から合格を推定しません。合格の証拠と現在の適用条件は別途確認が必要です。")
            for number, row in enumerate(rows[:MAX_ITEMS], 1):
                add("note", "記録 " + str(number))
                if type(row) is not dict:
                    add("note", "記録の形式が不正なため表示できません。")
                    continue
                refs("出典", [row["source_ref"]] if key == "judgments" and "source_ref" in row else row.get("source_refs"))
                if key == "skills":
                    suggested = row.get("target_is_suggestion")
                    field("選択の区分", "人間が選択した対象" if suggested is False else
                          "提案された対象（未選択）" if suggested is True else "選択・提案の区分は未記録")
                for name, label in fields:
                    field(label, row.get(name))
            if len(rows) > MAX_ITEMS:
                add("note", "この分類の記録: " + str(len(rows) - MAX_ITEMS) + "件を表示上限により省略。")
    if len(works) > MAX_WORKS:
        add("note", "作業: " + str(len(works) - MAX_WORKS) + "件を表示上限により省略。")
    if truncated:
        blocks.append(("note", "全体の表示上限に達したため、以降の記録や参照を省略しています。完全な一覧ではありません。"))
    if format == "markdown":
        return "\n\n".join(("#" * int(kind[1:]) + " " + value) if kind.startswith("h") else
                           "\n".join("    " + line for line in (value.splitlines() or [""]))
                           for kind, value in blocks) + "\n"
    body = "\n".join("<{0}>{1}</{0}>".format(kind if kind.startswith("h") else "pre", escape(value, quote=True))
                     for kind, value in blocks)
    return ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + escape(_text(title), quote=True) + '</title><style>'
            'body{margin:0;background:#f5f2e9;color:#25362f;font-family:serif;line-height:1.7}'
            'article{max-width:760px;margin:auto;padding:32px 20px}h2{border-top:1px solid #b8b9a8;padding-top:24px}'
            'h3{color:#455d50}pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere;margin:10px 0}'
            '</style></head><body><article>' + body + '</article></body></html>\n')
