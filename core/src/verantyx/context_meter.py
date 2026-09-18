"""Local request composition in bytes. Never claim tokenizer or cache estimates."""
from collections import defaultdict
from datetime import datetime, timezone
import os
from pathlib import Path
import uuid

from .domain.codec import canonical, decode

LABELS = {
    "instructions": ("Contract", "指示・契約"), "skills": ("Skills", "スキル"),
    "history": ("Conversation", "会話"), "tools": ("Tool definitions", "ツール定義"),
    "results": ("Tool results", "ツール結果"), "personal": ("Shared personal notes", "共有済み個人記録"),
    "request": ("Request", "依頼・選択した参照"), "project": ("Project context", "プロジェクト情報"),
    "attachments": ("Attachments", "添付"), "structure": ("Other / JSON", "その他・JSON構造"),
}


def composition(request):
    buckets = defaultdict(int)
    def walk(value, path=()):
        if isinstance(value, dict):
            for key, part in value.items():
                walk(part, (*path, key))
            return
        top = path[0] if path else ""
        if "skills" in path or "skill_assets" in path:
            category = "skills"
        elif top == "personal_context":
            category = "personal"
        elif top in ("turns", "owner_instructions") or any(key in path for key in ("prior_work", "session_summary", "model_handoff")):
            category = "history"
        elif top == "tool_receipts":
            category = "results"
        elif top == "tool_capabilities":
            category = "tools"
        elif top in ("output_contract", "output_schema"):
            category = "instructions"
        elif top == "request":
            category = "request"
        elif top == "attachments":
            category = "attachments"
        elif top == "project_context":
            category = "project"
        else:
            category = "structure"
        buckets[category] += len(canonical(value).encode("utf-8"))
    walk(request)
    total = len(canonical(request).encode("utf-8"))
    buckets["structure"] += total - sum(buckets.values())
    return {"bytes": total, "categories": dict(sorted(buckets.items(), key=lambda row: -row[1])),
            "unit": "UTF8_BYTES_NOT_TOKENS", "scope": "PREPARED_WORK_REQUEST_NOT_PROVIDER_CONTEXT",
            "run_id": request.get("run_id"), "sharing": request.get("personal_context", {}).get("sharing", "UNKNOWN"),
            "capture_learning": request.get("capture_learning") is True}


def capture(root, request, metadata):
    result = {**composition(request), "prepared_at": datetime.now(timezone.utc).isoformat(),
              "semantic_summary": metadata.get("semantic_summary", False),
              "compacted": metadata.get("compacted", False)}
    folder = Path(root) / ".verantyx"
    temporary = folder / (".context-" + uuid.uuid4().hex)
    try:
        if folder.is_symlink() or not folder.is_dir():
            return result
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(canonical(result) + "\n")
        os.replace(temporary, folder / "context-usage.json")
    except OSError:
        pass
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return result


def read(root):
    from .adapters.observations import read_document
    from .errors import LedgerError
    try:
        value = decode(read_document(Path(root) / ".verantyx/context-usage.json", 16384), 16384)
        if (value.get("unit") == "UTF8_BYTES_NOT_TOKENS" and type(value.get("bytes")) is int
                and value["bytes"] >= 0 and isinstance(value.get("categories"), dict)
                and set(value["categories"]) <= set(LABELS)
                and all(type(count) is int and count >= 0 for count in value["categories"].values())
                and sum(value["categories"].values()) == value["bytes"]
                and type(value.get("sharing", "UNKNOWN")) is str):
            return value
    except (OSError, LedgerError, ValueError, AttributeError):
        pass
    return None


def describe(value, japanese=False):
    if not value:
        return "まだWork AIの依頼を準備していません。" if japanese else "No Work AI request prepared yet."
    lines = [("直近の依頼の構成（UTF-8バイト比率）" if japanese else "Latest prepared request (UTF-8 byte shares)"),
             value.get("prepared_at", ""), f"{value['bytes']:,} bytes"]
    for key, count in value["categories"].items():
        lines.append(f"{LABELS.get(key, (key, key))[int(japanese)]}: {count / max(1, value['bytes']):.1%} ({count:,} B)")
    lines += ["", ("トークン比率・コンテキスト使用率ではありません。本家CLIが保持する履歴やプロバイダ側の追加分は含みません。"
                   if japanese else "Not token shares or context-window utilization. Native CLI history and provider overhead are excluded."),
              ("準備した依頼の内訳です。送信成功の証拠ではありません。実測トークン・キャッシュは /usage。"
               if japanese else "Prepared request only, not proof of delivery. Reported tokens and cache: /usage."),
              ("Ownerノートの全履歴を自動送信しません。参照として選んだ内容だけ依頼へ展開します。"
               if japanese else "Browsing Owner history does not send it. Only explicitly selected references are expanded."),
              "Personal sharing: " + value.get("sharing", "UNKNOWN"),
              "Inline learning capture: " + str(value.get("capture_learning", False)),
              "Saved semantic summary: " + str(value.get("semantic_summary", False))]
    return "\n".join(lines)
