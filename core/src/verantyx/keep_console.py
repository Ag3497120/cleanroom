"""Explicit end-of-work choices, routed through the existing CLI gates.

No model, new memory store or implicit decision. The notice after an answer
offers a door; it never opens a learning session or picks a target for someone.
"""
import shlex
import uuid

from .errors import LedgerError


HINTS = {
    "ja": "次に残すもの: /keep で『仕組みに残す資産 / 自分が学ぶこと / 委ねること』を選べます。後回しでも構いません。",
    "en": "Keep what matters: /keep for reusable assets, things to learn, or things to delegate. Optional; you can defer.",
    "zh-Hans": "保留有用的成果: /keep 可查看复用资产、想学的内容和想委托的内容。可以稍后决定。",
    "ko": "남길 것 선택: /keep 에서 재사용 자산, 배울 것, 맡길 것을 볼 수 있습니다. 나중에 결정해도 됩니다.",
    "es": "Conserva lo importante: /keep muestra activos reutilizables, qué aprender y qué delegar. Puedes decidir después.",
}


def hint(locale):
    return HINTS.get(locale, HINTS["en"])


def arguments(request, last_run):
    """Parse /keep [RUN_ID], /keep learn|delegate ID REASON or /keep check FILE."""
    parts = request.split(None, 3)
    if not parts or parts[0] != "/keep":
        raise LedgerError("ARGUMENTS")
    if len(parts) == 1:
        return ["keep", last_run] if last_run else None
    operation = parts[1]
    if operation not in ("learn", "delegate", "check"):
        if len(parts) != 2:
            raise LedgerError("ARGUMENTS")
        return ["keep", operation]
    if not last_run:
        return None
    key = "console-keep-" + uuid.uuid4().hex
    if operation in ("learn", "delegate"):
        if len(parts) != 4 or not parts[3].strip():
            raise LedgerError("ARGUMENTS")
        return ["keep", last_run, "--" + operation, parts[2],
                "--reason", parts[3], "--key", key]
    try:
        tokens = shlex.split(request)
    except ValueError:
        raise LedgerError("ARGUMENTS") from None
    if len(tokens) != 3 or not tokens[2]:
        raise LedgerError("ARGUMENTS")
    return ["keep", last_run, "--check", tokens[2], "--key", key]
