"""Report observed host behavior without inventing a filesystem audit."""


def observation(state):
    session = state.get("work_session") or {}
    harness = session.get("context", {}).get("work_harness") or {}
    provider = session.get("work_model", {}).get("provider", "")
    providers = {provider, (state.get("work_result") or {}).get("model", {}).get("provider", "")}
    providers.update(turn.get("model", {}).get("provider", "") for turn in state.get("work_turns", []))
    child_called = any(tool.get("request", {}).get("tool") == "consult_child"
                       for tool in state.get("work_tools", []))
    tool_process = any(tool.get("status") == "SUCCEEDED" and tool.get("request", {}).get("tool")
                       in ("call_mcp", "list_mcp_tools", "run_project_check")
                       for tool in state.get("work_tools", []))
    external = (harness.get("kind") == "external_process" or tool_process
                or bool(providers & {"explicit_adapter", "external_work_harness"}) or child_called)
    known_host = harness.get("kind") == "builtin" and harness.get("authority") == "HOST_TOOLS_ONLY" and not external
    return {
        "source_project_changed": False if known_host else None,
        "source_change_status": "HOST_TOOLS_CANDIDATE_ONLY" if known_host else "UNKNOWN_EXTERNAL_EFFECTS",
        "observation_scope": "HOST_TOOL_RECEIPTS_NOT_A_WHOLE_FILESYSTEM_AUDIT",
        "external_native_effects_observed": False,
        "whole_project_audited": False,
        "sandbox": harness.get("sandbox", {"status": "NOT_RECORDED", "isolation_verified": False}),
    }


def message(state):
    if observation(state)["source_project_changed"] is None:
        return "本体の変更状態は未確認です。外部プロセスの独自操作は観測していません。"
    return "記録したホスト操作は候補への書き込みのみです。本体全体の変更監査とは別です。"
