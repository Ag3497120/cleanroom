"""M1 grants only the file observations explicitly requested through the CLI."""


def read_rights(state, trusted=True):
    return {
        "source_ref": state["request_ref"],
        "read_paths": list(state["read_scope"]),
        "grants": list(state["read_grants"]),
        "effective_read_paths": list(state["read_scope"]) if trusted else [],
        "write_grants": [],
        "network_grants": [],
        "external_approvals_adopted": False,
        "trust": "LOCAL_COMMAND" if trusted else "ARCHIVE_ONLY",
    }
