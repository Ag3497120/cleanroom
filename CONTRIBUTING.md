# Contributing to Cleanroom

Thank you for helping people keep the experience of making things with AI.
Small fixes, translations, reproducible failures and documentation improvements are welcome.
English and Japanese are welcome in discussions; other languages are welcome too.

## Product boundaries

- Ordinary work should proceed without keyword-based judgments about its meaning.
- AI proposes interpretations. Vera records permissions, sources, execution facts and explicit choices.
- Work results survive reflection failures. Preserve previous interpretations rather than overwriting them.
- Generated or imported AI procedures are not human mastery, active rules or new execution permissions.
- Skipping, delegating, asking for help or leaving a profile blank is not evidence of inability.
- Learning is voluntary. Preserve the person's pace and next-time choices across projects.
- Record useful explanations during work, not fabricated retrospective reasoning.
- Keep private profile and project material local unless the person explicitly chooses to share it.

## Pick a focused change

Use an issue for larger design changes. For a small fix, a focused pull request is enough.
Keep CLI behavior primary and preserve Agent/Owner controls.
Describe the user-visible effect, evidence, limits and any data-format or privacy impact.
Do not rewrite unrelated files or change historical records in place.

## Local setup

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./core
verantyx --help
```

Use a disposable project and a temporary `VERANTYX_PERSONAL_HOME` for tests.
Never run experiments against someone else's real notebook or credentials.
The installed parser is the command catalogue: `verantyx commands`.

## Relevant checks

Run only the checks relevant to your change and report exactly what ran.

```sh
cd core
PYTHONPATH=src:tests python -m unittest test_learning_continuity test_notebook_connections -v
```

For the website, use Node 22.13+ and the existing npm lockfile:

```sh
npm ci
npm run typecheck
npm run lint
npm test
npm run build
```

Fixture tests are not evidence of real-model teaching quality. A model saying a task
succeeded is not a test receipt. State the target version and remaining unknowns.
Do not launch paid model calls, external tools, deployments or destructive checks
without the operator's approval.

## Recording and translations

The English walkthrough uses real CLI interactions with labelled public fixtures.
Follow [the recording recipe](docs/DEMO_RECORDING.md). Do not record personal data.
Maintain language anchors and links in README; preserve meaning rather than forcing identical phrasing.
Runtime command support and translated documentation are distinct claims.

## Pull requests

Include a summary, scope, checks run, known gaps and privacy considerations.
Do not commit `.verantyx`, personal databases, tokens, evaluation workspaces or real-task captures.
Keep existing third-party notices. Contributions you are entitled to license are
submitted under this project's MIT License. Third-party quotations are not relicensed.

See the [code of conduct](CODE_OF_CONDUCT.md) and [security policy](SECURITY.md).
