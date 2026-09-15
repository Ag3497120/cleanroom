# Work, Ownership, Authority

Vera is a collaborative-development foundation for retaining human purpose,
judgment, technical understanding, experience and project provenance when AI
performs most implementation. Cleanroom is its agent/owner notebook interface.

## Normal path

1. Select one Work AI. The previous reviewer connection is not required.
2. Approve the selected project context and its destination before sending.
3. The Work AI interprets the request and iterates over approved tools.
4. The host saves WorkResult and candidate hashes in the local event ledger.
5. An independently selected Reflection AI organizes that immutable trace.
6. Owner displays observed facts separately from AI interpretations.
7. Future work receives bounded prior work/reflection records as references.

There is no task-keyword classifier, technical-keyword learning fallback, or
mandatory agreement between model interpretations in this path.

WorkResult and ReflectionRecorded have independent statuses. A reflection
failure cannot delete the answer, change the work outcome, or rerun work.
An uncertain interrupted model invocation is not retried automatically.
Reorganizing appends a new classification revision over the same source range.

## Settings and reuse

The model menu offers Work AI, Reflection same-as-work, a separate connection,
reflection off, and organization of previously recorded work. API credentials
remain environment variables. API/local connections need only one model name.

Automation can use:

```sh
verantyx organize WORK_RUN_ID
verantyx organize WORK_RUN_ID --adapter /absolute/path/to/approved-adapter.json
```

The explicit adapter overrides the saved reflection connection for that run.
It is an external-send instruction, not a read-only lookup. Existing command
approval applies when signed-command protection is enabled.

All ownership items are PROPOSAL_ONLY. A HUMAN_DECISION interpretation must
cite an actual human-decision/reply event and still cannot grant authority.
A model cannot declare human mastery, create an execution receipt, or activate
a rule by adding those fields to its output. Unknown source IDs are rejected.

## Current executable boundary

The new work gateway implements a bounded agent loop with list_files,
approved UTF-8 read_file, and versioned write_candidate. Other tool names,
including shell, delete and publish, are refused. Source files are unchanged.
Candidate paths, sizes, receipts and hashes are host-controlled.

This is not yet a general autonomous shell agent. Bridging existing explicit
command/worktree authorization into this new loop, executing build/tests and
repairing from those receipts remain work to do. No successful generation is
reported as independently verified. Candidate adoption remains separate.

The prior two-role finite-contract workflow remains available when an explicit
verification target/expectation is supplied. Historical events retain their
original meaning. That advanced path is not the normal request classifier.

## Ownership UI limitations

The Owner projection distinguishes actual user input, candidate artifacts,
tool receipts, model assumptions, learning/delegation proposals, draft
rules/checks, and unresolved items. It reports no understanding percentage.
Existing learning-state controls are not automatically overwritten by a model.
Attaching new reflection cards to every existing learning exercise/editor
and full interactive terminal layout QA are not complete in this change.

## Acceptance scope

The accompanying focused tests use controllable model adapters to check the
work/reflection boundary, provenance, replay, permission refusal, same-model
selection, and reorganization. They do not establish semantic accuracy of any
live provider, Ajax classification quality, live terminal appearance, shell
isolation, or general MVP release readiness.
