"""Optional official MCP transport. External agents can append reports, never mastery."""
from . import personal_profile as profile
from .domain.codec import digest
from .errors import LedgerError


def record_external_note(session, key, model, title, text, technologies):
    profile.require(all(type(v) is str and 0 < len(v) <= 160 for v in (session, key, model, title))
                    and type(text) is str and 0 < len(text.encode()) <= 65536
                    and len(technologies) <= 8
                    and all(type(t) is str and 0 < len(t) <= 100 for t in technologies), "MCP_NOTE_LIMIT")
    identity = "mcp-note-" + digest({"session": session, "key": key})[:40]
    payload = {"session": session, "reported_model": model, "text": text,
               "original_text_complete": True, "explanation_is_excerpt": len(text) > 6000,
               "proposal": {"learning_notes": [{
                   "title": title, "target_kind": "BOTH", "technology_tags": technologies,
                   "explanation": text[:6000], "prerequisites": [], "expanded_steps": [],
                   "alternatives": [], "pitfalls": [], "verification": [], "next_small_step": "",
                   "source_event_ids": [], "profile_refs": [],
               }]}}
    fingerprint = digest(payload)
    ref = "external:" + digest({"session": session, "key": key})[:48]
    old = profile.get_record(identity)
    if old:
        profile.require(old["event"]["event_hash"] == fingerprint, "MCP_NOTE_CONFLICT")
        return {"id": identity, "source_ref": ref, "replayed": True}
    stamp = profile.now()
    profile.put_record({
        "id": identity, "kind": "learning_trace", "work_key": "external/" + session,
        "project_id": "external", "project_name": "External agent: " + model,
        "run_id": session, "request": title,
        "event": {"source_ref": ref, "revision": 1, "type": "ExternalAgentReport",
                  "actor_kind": "external_agent", "recorded_at": stamp,
                  "event_hash": fingerprint, "payload": payload},
        "profile_snapshot": {}, "profile_snapshot_sha256": None, "profile_refs": [],
        "share_with_ai": False, "authority": "EXTERNAL_AI_REPORT_NOT_EXECUTION_OR_MASTERY", "created_at": stamp,
    })
    from .notebook_bridge import auto_sync
    auto_sync()
    return {"id": identity, "source_ref": ref, "work_verified": False, "human_progress_changed": False}


def server(root=None, configuration=None, *, allow_personal=False, allow_import=False):
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations
    except ImportError:
        raise LedgerError("MCP_DEPENDENCY_REQUIRED", {"install": "pip install -e './core[mcp]'"}) from None
    mcp = FastMCP("Cleanroom notebook")
    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    append_only = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)

    def readable():
        profile.require(allow_personal, "MCP_PERSONAL_SCOPE_NOT_APPROVED")

    def writable():
        profile.require(allow_import, "MCP_IMPORT_SCOPE_NOT_APPROVED")

    @mcp.tool(annotations=read_only)
    def list_learning_moments(limit: int = 20) -> dict:
        """Read implementation-time AI explanations; not human mastery."""
        readable()
        profile.require(1 <= limit <= 100, "MCP_PAGE")
        from .learning_moments import entries
        return {"items": entries(limit=limit), "human_mastery_inferred": False}

    @mcp.tool(annotations=read_only)
    def read_learning_guide(identity: str, detail: str = "summary") -> dict:
        """Read a saved summary, full guide or sources without invoking AI."""
        readable()
        from .learning_guides import read
        return read(identity, detail=detail)

    @mcp.tool(annotations=read_only)
    def read_skill(identity: str) -> dict:
        """Read a passive procedure. No execution capability or mastery is granted."""
        readable()
        from .skill_assets import resolve
        return resolve(identity, root, configuration)

    @mcp.tool(annotations=read_only)
    def project_handoff(run_id: str, budget: int = 60000) -> dict:
        """Read a bounded project handoff with original source references."""
        profile.require(root is not None and configuration is not None, "PROJECT_REQUIRED")
        from .context_handoff import build
        return build(root, configuration, run_id, budget=budget)

    @mcp.tool(annotations=append_only)
    def record_work_note(session: str, key: str, model: str, title: str,
                         text: str, technologies: list[str]) -> dict:
        """Append an external AI report during work. Not an execution receipt or human statement."""
        writable()
        return record_external_note(session, key, model, title, text, technologies)

    @mcp.tool(annotations=append_only)
    def import_skill(text: str, origin: str, title: str, technologies: list[str]) -> dict:
        """Import passive skill text; ignore any claimed human mastery, approvals or executable hooks."""
        writable()
        from .notebook_bridge import import_text
        return import_text(text, origin=origin, title=title, technologies=technologies, confirmed=True)

    return mcp


def serve(root=None, configuration=None, **kwargs):
    server(root, configuration, **kwargs).run(transport="stdio")
    return 0
