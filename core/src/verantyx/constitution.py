"""Project-owned decision rights and unresolved judgments.

These records are local, append-only, and model-independent.  They are not a
conversation summary: they are the project context and the remaining human
decisions that govern a future external-AI invocation.
"""

from __future__ import annotations

import fcntl
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from .domain.codec import canonical, decode, digest
from .errors import LedgerError


CONSTITUTION_FORMAT = "verantyx.project-constitution.v1"
GAP_FORMAT = "verantyx.judgment-gap.v1"
_MAX_ITEMS = 16


def _now():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _invalid(reason):
    raise LedgerError("CONSTITUTION_INVALID", {"reason": reason})


def _path(root, name):
    return Path(root) / ".verantyx" / name


def _text(value, label, maximum):
    if not isinstance(value, str) or not value.strip():
        _invalid(label + " must be non-empty text")
    value = value.strip()
    if len(value) > maximum:
        _invalid(label + " is too long")
    return value


def _items(values, label):
    if not isinstance(values, list):
        _invalid(label + " entries must be a list")
    result = [_text(value, label, 500) for value in values]
    if len(result) > _MAX_ITEMS:
        _invalid(label + " has too many entries")
    return list(dict.fromkeys(result))


def _append(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "a", encoding="utf-8", closefd=False) as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.write(canonical(record) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _records(path):
    if not path.exists():
        return []
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = decode(line)
            if not isinstance(value, dict):
                _invalid("append-only record is not an object")
            result.append(value)
    return result


def _derived(configuration):
    project = configuration.get("project", {})
    purpose = project.get("purpose", "") if isinstance(project, dict) else ""
    return {"format": CONSTITUTION_FORMAT, "revision": 0,
            "purpose": purpose if isinstance(purpose, str) else "", "non_negotiables": [],
            "human_owned_decisions": [], "source": "CONFIG_DERIVED_NOT_RECORDED"}


def validate_packet(value, *, allow_empty_purpose=False):
    if not isinstance(value, dict) or value.get("format") != CONSTITUTION_FORMAT:
        _invalid("unsupported constitution format")
    if not isinstance(value.get("revision"), int) or value["revision"] < 0:
        _invalid("invalid constitution revision")
    purpose = value.get("purpose")
    if allow_empty_purpose and purpose == "":
        purpose = ""
    else:
        purpose = _text(purpose, "constitution purpose", 4000)
    return {"format": CONSTITUTION_FORMAT, "revision": value["revision"], "purpose": purpose,
            "non_negotiables": _items(value.get("non_negotiables", []), "non-negotiable"),
            "human_owned_decisions": _items(value.get("human_owned_decisions", []), "human-owned decision")}


def snapshot(root, configuration):
    for record in reversed(_records(_path(root, "constitution.jsonl"))):
        if record.get("type") == "CONSTITUTION_SET" and isinstance(record.get("constitution"), dict):
            return validate_packet(record["constitution"]) | {"source": "LOCAL_APPEND_ONLY_LEDGER",
                "record_id": record.get("id"), "recorded_at": record.get("at")}
    return _derived(configuration)


def set_constitution(root, configuration, *, purpose, non_negotiables=(), human_owned_decisions=()):
    previous = snapshot(root, configuration)
    constitution = validate_packet({"format": CONSTITUTION_FORMAT, "revision": previous["revision"] + 1,
        "purpose": purpose, "non_negotiables": list(non_negotiables),
        "human_owned_decisions": list(human_owned_decisions)})
    record = {"format": CONSTITUTION_FORMAT, "type": "CONSTITUTION_SET",
        "id": "constitution-" + digest(constitution)[:24], "at": _now(),
        "previous_record_id": previous.get("record_id"), "constitution": constitution}
    _append(_path(root, "constitution.jsonl"), record)
    return constitution | {"source": "LOCAL_APPEND_ONLY_LEDGER", "record_id": record["id"], "recorded_at": record["at"]}


def model_packet(root, configuration):
    value = snapshot(root, configuration)
    return {"format": CONSTITUTION_FORMAT, "revision": value["revision"], "purpose": value["purpose"],
            "non_negotiables": value["non_negotiables"], "human_owned_decisions": value["human_owned_decisions"],
            "authority": "PROJECT_CONTEXT_ONLY_NOT_PERMISSION_NOT_EVIDENCE"}


_HIGH_IMPACT = ("公開", "release", "deploy", "配布", "課金", "決済", "削除", "消去", "移行",
                "migration", "互換", "backward", "security", "権限", "secret", "credential",
                "privacy", "個人情報", "目的変更", "constitution", "利用規約", "license", "ライセンス")
_LOW_CONTEXT = ("これ", "それ", "いい感じ", "適切に", "よしなに", "whatever")


def assess(root, configuration, request):
    """Classify a task by decision rights, never by prompt length."""
    request = _text(request, "request", 12000)
    constitution = model_packet(root, configuration)
    from .work_output import split_owner_context
    instruction = split_owner_context(request)[0]
    lowered = instruction.casefold()
    # A demonstrative inside a concrete request is not a missing task. Match
    # only an underspecified instruction as a whole, not every use of "これ".
    bare = re.sub(r"[\s。！!？?、,\.]+", "", lowered)
    underspecified = bool(re.fullmatch(
        r"(?:これ|それ|いい感じ|適切に|よしなに|whatever)"
        r"(?:(?:これ|それ|を|に|で|と|は|も|いい感じ|適切に|よしなに|修正|変更|実装|改善|説明|要約|お願い|して|する|ください|頼む))*", bare))
    matched = [term for term in _HIGH_IMPACT if term.casefold() in lowered]
    matched += [item for item in constitution["human_owned_decisions"] if item.casefold() in lowered]
    matched = list(dict.fromkeys(matched))
    if matched:
        status, question = "ASK_ONE_DECISION", "今回の変更で優先する人間の判断を一つだけ記録してください。"
        reason = "人間専有になり得る領域に触れています: " + "、".join(matched[:3])
    elif not constitution["purpose"] and underspecified:
        status, question = "UNKNOWN", "この作業で達成したい結果を一文で記録してください。"
        reason = "プロジェクト目的も具体的な作業対象も記録されていません。"
    elif underspecified:
        status, question = "ASSUME_AND_EXECUTE", None
        reason = "既存目的を参照して可逆な調査から進めます。未委譲の判断や本体への変更を許可するものではありません。"
    else:
        status, question = "EXECUTE", None
        reason = "既存のプロジェクト文脈を注入し、可逆な範囲から進められます。"
    return {"format": GAP_FORMAT, "status": status, "request": request, "reason": reason,
            "question": question, "matched_terms": matched, "constitution": constitution,
            "scope": "TASK_PREFLIGHT_NOT_EVIDENCE_NOT_EXECUTION_AUTHORITY"}


def _gap_state(root):
    result = {}
    for record in _records(_path(root, "judgment-gaps.jsonl")):
        gap_id = record.get("gap_id")
        if not isinstance(gap_id, str):
            continue
        if record.get("type") == "GAP_RAISED":
            result[gap_id] = dict(record)
        elif record.get("type") == "GAP_RESOLVED" and gap_id in result:
            result[gap_id].update(resolved_at=record.get("at"), resolution=record.get("resolution"))
    return result


def open_gap(root, gate):
    if gate.get("status") not in ("ASK_ONE_DECISION", "UNKNOWN"):
        return None
    identity = {"revision": gate["constitution"]["revision"], "request": gate["request"], "question": gate["question"]}
    gap_id = "gap-" + digest(identity)[:24]
    existing = _gap_state(root).get(gap_id)
    # The same request under the same constitution is the same decision.  A
    # resolved gap remains evidence of that prior answer; it is not reopened
    # merely because another adapter invokes the work again.
    if existing is None:
        _append(_path(root, "judgment-gaps.jsonl"), {"format": GAP_FORMAT, "type": "GAP_RAISED",
            "gap_id": gap_id, "at": _now(), "gate": dict(gate)})
    return gap_id


def resolve_gap(root, gap_id, resolution):
    gap_id, resolution = _text(gap_id, "gap id", 100), _text(resolution, "resolution", 4000)
    current = _gap_state(root).get(gap_id)
    if current is None:
        raise LedgerError("JUDGMENT_GAP_UNKNOWN", {"gap_id": gap_id})
    if current.get("resolved_at"):
        return {"gap_id": gap_id, "status": "ALREADY_RESOLVED", "resolution": current.get("resolution")}
    record = {"format": GAP_FORMAT, "type": "GAP_RESOLVED", "gap_id": gap_id, "at": _now(), "resolution": resolution}
    _append(_path(root, "judgment-gaps.jsonl"), record)
    return {"gap_id": gap_id, "status": "RESOLVED", "resolution": resolution, "resolved_at": record["at"]}


def gaps(root):
    result = []
    for gap_id, record in _gap_state(root).items():
        gate = record.get("gate", {})
        result.append({"gap_id": gap_id, "status": "RESOLVED" if record.get("resolved_at") else "OPEN",
            "opened_at": record.get("at"), "resolved_at": record.get("resolved_at"),
            "resolution": record.get("resolution"), "request": gate.get("request"),
            "question": gate.get("question"), "reason": gate.get("reason"), "matched_terms": gate.get("matched_terms", [])})
    return sorted(result, key=lambda item: (item["status"] != "OPEN", item["opened_at"] or "", item["gap_id"]))


def prepare(root, configuration, request, *, assumption=None):
    gate = assess(root, configuration, request)
    if gate["status"] in ("ASK_ONE_DECISION", "UNKNOWN"):
        gap_id = open_gap(root, gate)
        gate["gap_id"] = gap_id
        if assumption and assumption.strip():
            gate["human_assumption"] = _text(assumption, "assumption", 4000)
            gate["gap_resolution"] = resolve_gap(root, gap_id, gate["human_assumption"])
            gate["status"] = "ASSUME_AND_EXECUTE"
            gate["reason"] = "人間の今回限りの前提を記録し、一般規則へ昇格させずに進めます。"
    return gate
