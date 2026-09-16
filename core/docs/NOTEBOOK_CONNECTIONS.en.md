# Original work notes, Obsidian and external agents

Vera preserves human ownership, not a score of the person. Technology names are entry points, not a keyword classifier.
Guides use original implementation explanations, actual receipts and explicit owner preferences.

## Capture during implementation

Enable the private personal notebook to index work as each turn is committed.
The model receives only opted-in personal context and the requested learning pace.
Useful explanations are optional; not every turn has one. Missing explanations stay missing.
These are public explanations of observable choices, not hidden chain-of-thought.

~~~sh
verantyx my-profile enable
verantyx my-learning moments --json
verantyx my-learning unpack --moment MOMENT_ID --send
verantyx my-learning unpack --run RUN_ID --send
verantyx my-learning unpack --skill SKILL_ID --send
verantyx my-learning show --id GUIDE_ID --detail summary
verantyx my-learning show --id GUIDE_ID --detail full
verantyx my-learning show --id GUIDE_ID --detail sources
~~~

F2 > During work and Learning guides open these same records.
A moment can come from another project or an external MCP agent, with no technology tag required.
If indexing fails, the project events remain. Explicit reindexing does not reconstruct an unrecorded past profile.

~~~sh
verantyx my-learning index --run RUN_ID --yes
verantyx my-learning record --moment MOMENT_ID --state NEXT_TIME \
  --text "Revisit this when I touch this boundary again." --yes
~~~

EXPLAINED, APPLIED, STILL_EXPLORING, NEXT_TIME, REFERENCE and DELEGATE record the owner's own words.
They do not certify mastery, create permissions or infer inability from silence or delegation.
Sharing is off unless explicitly requested and allowed by the personal sharing preference.

## Owner and Agent

Agent continues the normal work conversation. Owner shows saved During work explanations.
Existing reference completion can insert an Owner item into an Agent request when the owner chooses it.
F2 > Connections opens Obsidian, imports and MCP guidance; Parent / child models opens model roles.
Reading, learning and execution authorization remain distinct.

## Obsidian-first or connect later

~~~sh
verantyx setup notebook
verantyx connections connect --vault /absolute/path/to/MyVault \
  --include-private --auto --yes
verantyx connections status --json
verantyx connections sync --yes
verantyx web
~~~

Open that directory as a vault in Obsidian. Cleanroom does not install Obsidian or sign in to an account.
It exports versioned original Markdown records under Cleanroom/records and Wiki links to technology nodes.
The local Web graph distinguishes owner records, AI procedures, implementation notes and technologies.
Edges represent recorded associations, never mastery scores. Obsidian links open the associated file.

Owner edits are not overwritten: an edited export causes synchronization to defer.
Keep personal additions in separate linked notes. Auto-export follows implementation capture, guide creation,
explicit understanding entries and imports; use sync for other updates.
Choosing Local disables future export but does not erase exported files.

**The authoritative store remains the Cleanroom local ledger.**
Obsidian-first means using the vault as the reading, linking and annotation workspace from the start.
It is not bidirectional authoritative synchronization. Markdown edits cannot grant permissions or certify learning.

**Privacy:** exported originals can contain private profile and project information.
A vault synced by Obsidian Sync, iCloud, Git or plugins may copy it to those services.
Private export requires explicit consent. Existing exported copies remain under the owner's control.

## Import skills without importing mastery

~~~sh
verantyx skill-import /absolute/path/SKILL.md \
  --origin "Source agent / repository / revision" \
  --title "Separate parsing from effects" --technology Python --yes
verantyx my-skills
~~~

Imports accept passive Markdown/text, retain original content, origin and hashes, and execute nothing.
Scripts, hooks, credentials and tool permissions are not migrated.
Text claiming approval or human mastery is still untrusted source text.

The initial AI procedure is DRAFT; the human record is NO_RECORD, meaning no explicit record here,
not an assertion that the person does not know it.
The owner may add an explanation or use case, keep it for later, reference it or delegate it.
Re-importing the same origin and content does not reset existing owner choices.

## Optional MCP server

Install the optional transport from the repository root:

~~~sh
python -m pip install -e './core[mcp]'
verantyx --project /absolute/project mcp
~~~

An example stdio MCP client configuration:

~~~json
{
  "mcpServers": {
    "cleanroom": {
      "command": "/absolute/cleanroom/.venv/bin/verantyx",
      "args": ["--project", "/absolute/project", "mcp", "--allow-personal", "--allow-import"]
    }
  }
}
~~~

Use actual executable and project paths for that Mac.

- project_handoff reads work records in the selected project.
- list_learning_moments, read_learning_guide and read_skill require --allow-personal.
- record_work_note and import_skill require --allow-import.
- No shell, mastery certification, approval creation or rule activation tools are exposed.

Personal access includes private cross-project records. Enable it only for a trusted client.
Import access allows external AI reports, not authenticated human statements or execution receipts.
External model names are declared by the caller. Reusing session/key with changed content is rejected.
Have the external agent call record_work_note at meaningful intermediate steps, not only at the end.

This is a Cleanroom MCP server, not a general outbound MCP tool execution client.

## Language

~~~sh
verantyx setup language
verantyx web
verantyx --lang en web
~~~

The Web menu follows project settings unless explicitly overridden.
A language flag is returned by the local API. Refresh follows the project setting until the user changes the Web selector.
Original personal text and existing AI guides are not translated or overwritten.
Open the private local URL issued by web, not the raw HTML file.

## Parent and advisory child models

~~~sh
verantyx setup models
verantyx model-roles register --alias main \
  --adapter .verantyx/model-adapters/CONNECTION/implementation.json --yes
verantyx model-roles register --alias adviser \
  --adapter .verantyx/model-adapters/OTHER/implementation.json --yes
verantyx model-roles set --role parent --alias main --yes
verantyx model-roles set --role child --alias adviser --yes
verantyx setup roles
verantyx model-roles show --json
~~~

Paths are examples: select adapters actually saved by Models.
The menu can register the current connection with a short name.
Default parent returns to the normal Work model; Default child disables child calls.
Changed adapter configuration requires re-registration. Credentials are not copied into role registrations.

A natural-language request such as "Use adviser as the parent from now on" is interpreted by the Work AI.
Its request_model_change tool requests owner confirmation before changing the next model call.
Noninteractive runs leave PENDING_OWNER. A model cannot grant its own provider switch.

consult_child makes one advisory call. Proposed child tools are returned as data, never executed by the host.
This is not a parallel multi-writer agent system or control over an external harness's internal child agents.
A generic command adapter must itself be trusted.

## Handoff and context compaction

~~~sh
verantyx handoff RUN_ID --budget 60000 --json
~~~

Continuing work injects the prior purpose, request, candidate manifest and source-linked events.
Original archives remain across model changes. Revoked private profile text is not automatically re-shared.
When input grows, older input records are omitted with their source IDs and hashes recorded.
This is a loss-aware bounded view, not a destructive archive rewrite or a certified semantic summary.
read_work_history can retrieve a current or previous work event within the per-event size limit.
If indispensable input still exceeds the request limit, the runtime returns a limit instead of silently deleting constraints.

## Scope

Contract tests and actual local stdio/HTTP/process tests cover records and boundaries, not real-model teaching quality.
They do not certify the Obsidian app, every MCP client or external OS isolation.
No automatic ability assessment, reconstruction of unrecorded past rationale, or perfect semantic compression is claimed.

See [learning continuity](LEARNING_CONTINUITY.en.md) and [sandbox boundaries](SANDBOX_BACKENDS.en.md).
