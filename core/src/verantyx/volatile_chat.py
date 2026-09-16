"""Temporary text conversation without project, profile or learning memory."""
from argparse import Namespace
from copy import deepcopy
from pathlib import Path
import tempfile
import uuid

from .authority import command_scope
from .domain.codec import canonical, decode
from .errors import LedgerError


def chat(root, configuration, text, history=()):
    if not text.strip() or len(text) > 16000:
        raise LedgerError("ARGUMENTS")
    from .agent_models import selected_work, invoke
    from .agent_schema import WORK_REQUEST, schema
    from .adapters.observations import read_document
    # No prompt is included in the authority operation or project invocation journal.
    args = Namespace(command="develop", interactive_operation="temporary_chat")
    with command_scope(root, configuration, args):
        adapter = selected_work(root, configuration)
        native = decode(read_document(adapter, 65536), 65536)
        if native.get("format") not in (
                "verantyx.codex-cli.v1", "verantyx.claude-cli.v1", "verantyx.model-api.v1"):
            raise LedgerError("TEMPORARY_CHAT_BUILTIN_ADAPTER_REQUIRED")
        with tempfile.TemporaryDirectory(prefix="cleanroom-temporary-chat-") as directory:
            base = Path(directory)
            (base / ".verantyx").mkdir(mode=0o700)
            local = deepcopy(native)
            if local["format"] == "verantyx.codex-cli.v1":
                from .codex_budget import initialize
                local["budget_directory"] = str(base / "native-receipts")
                initialize(local["budget_directory"], local["max_calls"])
            copied = base / "adapter.json"
            copied.write_text(canonical(local), encoding="utf-8")
            copied.chmod(0o600)
            request = {
                "format": WORK_REQUEST, "request": text, "run_id": "temporary-" + uuid.uuid4().hex,
                "response_locale": configuration["ui"]["locale"], "memory_mode": "temporary",
                "project_context": {"temporary_conversation": list(history)[-8:]},
                "personal_context": {}, "approved_files": [], "tool_receipts": [],
                "candidate_manifest": [], "tool_capabilities": {}, "learning_sources": [],
                "capture_learning": False,
                "output_contract": "Answer the conversation only. No tools or file access are authorized. "
                    "Return COMPLETE with your actual answer, empty tool_requests, assumptions, owner_question "
                    "and learning_notes. Do not produce learning, ownership or skill records.",
            }
            request["output_schema"] = schema(request)
            result = invoke(base, str(copied), request, key=uuid.uuid4().hex)
            document = result["document"]
            if document["tool_requests"] or document["status"] != "COMPLETE":
                raise LedgerError("TEMPORARY_CHAT_NO_TOOLS")
            return {"transient": True, "answer": document["answer"], "model": result["model"]}
