"""Owner-chosen parent/child models; AI may request, never self-authorize, a switch."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
import os
import re
import uuid

from .domain.codec import canonical, decode, digest
from .errors import LedgerError
from .authority import require_current_approval_valid

FILE = ".verantyx/model-roles.json"
CONFIRM = ContextVar("cleanroom_model_choice", default=None)
DEFAULT = {"format": "verantyx.model-roles.v1", "aliases": {}, "parent": None, "child": None}


def _adapter(root, path):
    value = Path(path)
    value = value if value.is_absolute() else Path(root) / value
    base = Path(root).resolve() / ".verantyx/model-adapters"
    if any(p.is_symlink() for p in [value, *value.parents]) or not value.resolve().is_relative_to(base):
        raise LedgerError("PATH_SCOPE")
    from .agent_models import identity
    model = identity(str(value))
    return str(value.resolve().relative_to(Path(root).resolve())), model


def load(root):
    from .work_harness import _read
    raw = _read(root, FILE, optional=True)
    value = decode(raw, 65536) if raw else deepcopy(DEFAULT)
    if type(value) is not dict or set(value) != set(DEFAULT) or value["format"] != DEFAULT["format"]:
        raise LedgerError("MODEL_ROLES_INVALID")
    if type(value["aliases"]) is not dict or len(value["aliases"]) > 32:
        raise LedgerError("MODEL_ROLES_INVALID")
    for name, row in value["aliases"].items():
        if (not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name) or type(row) is not dict
                or set(row) != {"adapter", "model"} or type(row["adapter"]) is not str):
            raise LedgerError("MODEL_ROLES_INVALID")
    if any(value[role] is not None and value[role] not in value["aliases"] for role in ("parent", "child")):
        raise LedgerError("MODEL_ROLES_INVALID")
    return value


def _save(root, value):
    from .adapters.invocation_journal import InvocationJournal
    with InvocationJournal(root, "model-roles-settings", "configuration"):
        require_current_approval_valid()
        base = os.open(Path(root).resolve(), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        directory = os.open(".verantyx", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=base)
        os.close(base)
        temporary = ".roles-" + uuid.uuid4().hex
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(canonical(value) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, "model-roles.json", src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
            os.close(directory)


def register(root, configuration, alias, adapter, *, confirmed=False):
    if not confirmed or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", alias):
        raise LedgerError("MODEL_ROLE_APPROVAL_REQUIRED")
    value = load(root)
    path, model = _adapter(root, adapter)
    if len(value["aliases"]) >= 32 and alias not in value["aliases"]:
        raise LedgerError("MODEL_ROLES_LIMIT")
    value["aliases"][alias] = {"adapter": path, "model": model}
    _save(root, value)
    return value


def choose(root, configuration, role, alias, *, confirmed=False):
    if not confirmed or role not in ("parent", "child"):
        raise LedgerError("MODEL_ROLE_APPROVAL_REQUIRED")
    value = load(root)
    if alias is not None and alias not in value["aliases"]:
        raise LedgerError("MODEL_ALIAS_UNKNOWN")
    if alias:
        _adapter(root, value["aliases"][alias]["adapter"])
    value[role] = alias
    _save(root, value)
    return {"ok": True, "role": role, "alias": alias, "effective": "NEXT_MODEL_CALL",
            "permissions_changed": False}


def selected(root, role):
    value = load(root)
    alias = value[role]
    if not alias:
        return None
    row = value["aliases"][alias]
    path, model = _adapter(root, row["adapter"])
    if model["adapter_sha256"] != row["model"]["adapter_sha256"]:
        raise LedgerError("MODEL_ALIAS_CHANGED")
    return str(Path(root) / path)


@contextmanager
def owner_confirmation(callback):
    token = CONFIRM.set(callback)
    try:
        yield
    finally:
        CONFIRM.reset(token)


def request_switch(root, configuration, role, alias):
    value = load(root)
    if role not in ("parent", "child") or alias not in value["aliases"]:
        raise LedgerError("MODEL_ALIAS_UNKNOWN")
    callback = CONFIRM.get()
    proposal = {"role": role, "alias": alias, "model": value["aliases"][alias]["model"]}
    if callback is None or callback(proposal) is not True:
        return {"status": "PENDING_OWNER", "proposal": proposal, "permissions_changed": False}
    return {**choose(root, configuration, role, alias, confirmed=True), "status": "OWNER_SELECTED"}


def consult(root, configuration, question, *, source_request, key, timeout=90):
    adapter = selected(root, "child")
    if adapter is None:
        raise LedgerError("CHILD_MODEL_NOT_SELECTED")
    if not isinstance(question, str) or not question.strip():
        raise LedgerError("ARGUMENTS")
    from .agent_schema import WORK_REQUEST, schema
    from .agent_models import invoke
    value = {"format": WORK_REQUEST, "request": question, "run_id": source_request["run_id"],
             "generation_id": key, "response_locale": configuration["ui"]["locale"],
             "turns": [], "tool_receipts": [], "approved_files": [], "candidate_manifest": [],
             "project_context": source_request.get("project_context", {}),
             "personal_context": source_request.get("personal_context", {}),
             "output_contract": "Give advice only. Return COMPLETE, with no tool_requests. "
                                "You are not permitted to execute, authorize, or mark human mastery.",
             "learning_sources": source_request.get("learning_sources", [])}
    value["output_schema"] = schema(value)
    if len(canonical(value).encode()) > 200000:
        raise LedgerError("WORK_CONTEXT_LIMIT")
    result = invoke(root, adapter, value, key=key, timeout=timeout)
    return {"authority": "CHILD_ADVICE_NOT_EXECUTION", "model": result["model"],
            "answer": result["document"]["answer"],
            "learning_notes": result["document"].get("learning_notes", []),
            "proposed_tools_not_executed": result["document"]["tool_requests"],
            "source_request_sha256": digest(value), "model_calls": 1}


def menu(root, configuration):
    from . import development_console as ui
    from .agent_models import selected_work
    from .agent_console import terminal_text
    while True:
        value = load(root)
        print("\nPARENT / CHILD MODELS\n" + terminal_text(canonical(value)))
        action = ui._pick("Model roles", ["register", "parent", "child"], str)
        if action is None:
            return
        if action == "register":
            alias = ui._ask("Short name for this configured connection")
            if not alias:
                continue
            path = ui._ask("Adapter path / Enter uses the current Work AI", selected_work(root, configuration))
            if ui._start("Register this model connection? No credentials are copied."):
                ui._mutate(root, configuration, register, alias, path, confirmed=True)
        else:
            alias = ui._pick("Choose a registered model; default disables child calls",
                             [None, *value["aliases"]], lambda name: name or "Default / no child")
            if ui._start("Use this model for " + action + "? Future requests may use a different provider."):
                ui._mutate(root, configuration, choose, action, alias, confirmed=True)
