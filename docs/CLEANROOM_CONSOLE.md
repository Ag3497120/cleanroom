# Cleanroom: Agent left, Owner right

Cleanroom is a project research notebook with a workbench. AI may do most of the
implementation; purpose, judgment, evidence and understanding remain visible to
the human owner. Two panes are not two agents or two independent conversations.

## Start

```sh
verantyx
verantyx "Improve the project landing page"
```

The interactive entry creates the existing safe project configuration if needed.
It opens an Agent workbench on the left and an Owner notebook on the right.
The request input is below Agent; the personal memo / search input is above Owner.
There is no requirement to learn slash commands, enter model terminology, or
configure a learning curriculum before the first task.
Before calling the configured AI, the Owner reviews the selected external context.
Declining this confirmation does not call a model. The existing context selector
chooses at most eight small text files. Filename exclusions are not a guarantee
that their contents contain no secrets; inspect the proposed disclosure.

## Navigation

| Operation | Control |
| --- | --- |
| Open the visible action menu | F2 |
| Choose an action | Up / Down, then Enter |
| Cycle Agent -> Owner memo -> Owner search -> Agent | Enter with the active input empty |
| Find Owner references while writing a request | Type the beginning of an Owner item's title |
| Browse reference suggestions | Up / Down |
| Insert a suggested reference without sending the request | Tab, or Enter while suggestions are open |
| Save a personal memo | Enter with text in the yellow MEMO input |
| Search the Owner notebook locally | Type in the green SEARCH input |
| Keep the current state or dismiss a question | Esc |
| Return to split view | Alt+0 |
| Owner / Agent / Evidence / Notebook | Alt+1 / Alt+2 / Alt+3 / Alt+4 |
| Move into the page to scroll | F3, then arrows or PageUp / PageDown |
| Open the learning margin; choose how to retain understanding | F4 |
| Return to the active input | Esc |
| Add a line to the active input | Alt+Enter |
| Close | Ctrl+D or Menu > Close |

The top page labels also accept mouse clicks. Actions include history, model
settings, context scope, human decisions, candidate content, finite verification,
learning choices and review of already prepared adoption plans. Settings use
English provider names; project text and human-facing explanations can be Japanese.

At 140 columns and at least 24 rows the workbench is side-by-side, with the Owner
allocated more width. Agent remains on the left and Owner on the right, including
while idle. At 90 columns and at least 36 rows Agent is above Owner. Smaller
terminals show the column containing the active input. `--plain` retains the
previous scrollback interface. `NO_COLOR` disables color; MEMO and SEARCH labels
still distinguish the modes. `VERANTYX_REDUCE_MOTION=1` shows transfers immediately
instead of animating the boundary.

## Two inputs, different destinations

```text
+---------------------------+---+--------------------------------+
| Agent                     |   | Owner                          |
| Observable work           |   | MEMO / SEARCH input            |
| Progress and results      |   |                                |
|                           |   | Your requests and decisions    |
|                           |   | Personal notes                 |
|                           |   | Questions and understanding    |
|                           |   | Evidence and unknowns          |
|                           |   |                                |
| Request input             |   |                                |
+---------------------------+---+--------------------------------+
```

The initial cursor is in the Agent request input. An empty Enter moves it to
Owner MEMO, the next empty Enter switches Owner to SEARCH, and the next returns
to Agent. A nonempty input keeps its own meaning: send a request, save a memo, or
search. Memo and search drafts are kept separately when switching modes.

Owner MEMO uses a yellow treatment and saves personal text locally. Owner SEARCH
uses a green treatment and filters the Owner catalogue as the user types. Neither
operation calls a model, submits a task, approves a candidate, or promotes a rule.
The Owner input can be used while an Agent operation is running. A request typed
during that operation remains a draft rather than silently entering a work queue.

Requests appear in Owner with their source and state; an in-session request is
not evidence that the runtime has accepted or completed it. The notebook separates
requests, personal notes, human decisions, Agent assumptions, questions, candidate
metadata, learning items, verification records and unknowns.

## Refer to a particular Owner item without learning a command

Type at least two leading characters of an Owner item's title in the Agent input,
including at the end of a sentence. Suggestions show the title and item category.
Use arrows to browse and Tab to insert the selected reference. Enter also accepts
an open suggestion without submitting the request. F2, not Tab, opens the action
menu. Escape dismisses suggestions without inserting them.

An inserted reference is bound to the selected item's content, source, run and
revision when available. Only selected references whose tokens are still present
in the submitted request are attached. Owner notes that were not selected are not
automatically included. Search narrows which Owner items are offered.

The attachment is quoted reference context, not a new instruction, approval or
independent proof. It does not replace the existing external-context disclosure:
selected project files and other runtime context remain subject to that workflow.
The selected Owner content is shown before the explicit send confirmation. A
maximum of eight references and a combined 12,000-character request are accepted;
an oversized selection is returned for editing rather than silently truncated.

## Transfers across the boundary

A request moving into Owner, a selected Owner reference moving into Agent, a human
question, or a newly surfaced optional understanding card can trigger a short
boundary animation. Part of the separator opens and the transfer label appears in
the Owner handoff area. The boundary then returns to its normal shape.

The animation is an interface notification, not simulated model reasoning or
evidence of task completion. It does not block typing or trigger a model call.
Reduced-motion mode displays the transfer immediately. Both direction and item
kind remain readable without relying on motion or color alone.

## Personal notes are reference material

Personal memos are appended to `.verantyx/owner-notes.jsonl`. Entries carry a local
operation key, timestamp, content digest and optional run association. File locking
serializes writers and an operation key allows the same save to be retried without
duplicating the entry. A failed save leaves the draft available; an incomplete
journal is reported rather than silently repaired.

This is a separate, reference-only local journal, not the authoritative SQLite
event stream. Its note revision is displayed separately. A note does not count as
a human approval, authenticated identity, verified evidence or achieved learning.
Existing learning choices and reflections continue to use their original
revision-checked learning operations, not the personal memo journal.

## A second terminal is optional

```sh
verantyx watch
verantyx watch --run <actual-run-id>
verantyx watch <actual-run-id> --once --json
verantyx --project /absolute/project/path watch
```

`watch` follows the Owner's selected run unless a run is pinned. It reads the same
validated SQLite snapshot and never starts another model, authorizes an action,
creates a run, or bootstraps missing configuration. A pipe, `--plain`, `--once` or
`--json` produces one snapshot instead of starting a full-screen interface.
Missing configuration is an error, not permission to initialize a second project.

The cursor `.verantyx/cleanroom-session.json` is an ephemeral display subscription:
run ID, owner presence, phase, and heartbeat. It contains no approval or execution
receipt. Its phase is an observation, not evidence. An expired heartbeat is shown
as an offline Owner, not as successful work. The SQLite event ledger remains the
source of task revisions, decisions, candidate content, verification and learning.
The Owner and Agent projections are produced from one snapshot. A failed read
retains the previous view with a STALE label instead of silently showing it as live.

## What the notebook means

- Human decisions are recorded choices and task-local assumptions, not AI prose.
- Candidate file hashes describe recorded content, not automatic application.
- Evidence is tied to recorded targets and method contracts; opening a page does
  not recheck files or establish independent correctness.
- A different model's agreement is not automatically independent evidence.
- Learning targets, self-explanations, reference choices and delegation are
  distinct from established human mastery and from execution permissions.
- Linked verification runs retain their own revisions and bounded outcomes.
- Current operation messages are marked as transient, separate from ledger notes.
- Agent output shows observable progress and events, not hidden model reasoning.

The receipt separates Project, Human, Evidence, System and Growth. No synthetic
understanding percentage or automatic rule promotion is added by the interface.

## Grow with the project, without stopping the work

After a recorded task, the Owner can see one optional understanding card in the
margin. It is shown only in digest mode, when the interface is idle, and when a
stored candidate still needs attention. It does not interrupt generation, demand
an answer, or block adoption. Narrow terminals retain the same actions in the
menu. Manual mode requires opening the learning view; off mode suppresses
unselected suggestions. Explicitly recorded ownership choices remain readable.

The card and its notebook page connect a concept to the actual request, the reason
it became a candidate, a minimum principle, a counterexample, a question, its
source and the Owner's own notes. All teaching material comes from existing
records, with its candidate status retained. No tutor model is called just by
opening, reading or recording a card.

- Read the principle without automatically marking it understood.
- Record an explanation in your own words, a boundary case, or an application.
- Choose OWN or REVIEW as a goal, not an automatic achievement.
- Defer a topic without halting development, and explicitly reopen it later.
- Keep a topic as REFERENCE or choose DELEGATE without granting execution rights.

F4 opens the current card. Press F4 again for its actions, or use the clickable
reading / reflection / later / reference / delegation controls. The learning
library remains available for detailed asset and verification workflows.

Choices and reflections use the existing append-only learning operations and
the displayed item's expected revision. They are not stored in a parallel notes
database. An out-of-date choice fails rather than silently applying to a different
revision. A reflection is identified as a self-report, never independently proved
mastery. If saving fails, the submitted draft remains in the session notes and is
not presented as successfully stored.

The same concept ID in another work item is shown as a related experience. Its
old goals and self-reports remain references: they neither establish applicability
to the new task nor inherit authorization. Notebook summaries count choices,
deferred items and self-reports; they do not assign a percentage to understanding.

SQLite read failures retain the last valid view with a STALE label and its last
successful read time. The reader connection is closed and reopened on the next
poll. This read recovery does not replay a model call or retry a domain mutation.

## Execution boundaries and present limits

The interface uses the existing `develop` workflow, model adapters, authority
checks, command locks, verification and learning APIs. One interactive Owner per
project is enforced by a separate advisory lock; additional terminals use `watch`.
This is process coordination, not an OS sandbox against arbitrary programs.

Recorded decision choices retain their expected revision so a changed task cannot
silently accept an answer to an old question. Adoption authorization and execution
are separate explicit operations. The UI can review and apply an existing prepared
adoption plan; it does not invent a worktree, evidence, or an approval to copy an
arbitrary multi-file model response directly into the project. Preparing that
general execution/adoption pipeline remains the job of the existing advanced
workflow. Finite verification retains its existing supported targets and limits.

Closing an idle Owner leaves durable records available. During work, Close waits
for the current bounded operation, canceling an unanswered UI question if present.
This is not a daemon or detached job service. A forcibly killed process can leave
an external invocation outcome unknown; reopening or watching never retries it.
The existing invocation journal is responsible for recovery and duplicate control.
