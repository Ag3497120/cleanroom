# Live evaluation and external tools

Cleanroom is the product. Vera Kernel retains provenance and authority.
The CLI and implementation namespace remain verantyx.

Use 'verantyx commands' or 'verantyx commands toolbox --json' to discover the
actual registered commands, including their required arguments.

The notebook MCP server and the outbound MCP client are separate features.
Owner-approved toolbox JSON selects trusted executables, individual tool names,
and optional JSON Schema restrictions on arguments. Server descriptions and
read-only hints never grant permission. Processes do not inherit account
credentials or signed-in browser profiles automatically.

During work, the AI may propose list_mcp_tools, call_mcp, or a named
run_project_check. Checks require an explicitly selected OSS sandbox launcher.
The model cannot supply an arbitrary shell command. The launcher receives a
host-generated policy requesting network denial and disposable-workspace-only
writes. Configured isolation is not attested isolation; failures never fall
back to unsandboxed execution.

Each check records the input and candidate hashes, exit status, bounded output,
and scope. A check on an earlier candidate is stale, not proof for the new one.
Explicit write_candidates=false enforces read-only operation without classifying
natural-language intent by keywords.

MCP images are retained as hashed local media. The current text transport does
not send their pixels to the model; a browser snapshot and visual inspection
are different observations.

Use synthetic projects and a separate VERANTYX_PERSONAL_HOME for evaluation.
Do not use real Downloads, production deployment credentials, or inferred
human mastery as fixtures. Connection success, functional tests, semantic
relevance, and human understanding require different evidence.

See LIVE_EVALUATION.ja.md for complete JSON configuration examples.
