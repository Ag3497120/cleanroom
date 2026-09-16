# Security policy

Cleanroom is an evolving source preview. No release is represented as an audited
security boundary or a production-safe public shell.

## Supported scope

Report problems against the latest default-branch source, including path scope,
credential handling, external sends, local notebook exposure, provenance integrity,
unsafe tool execution, public demos and external harness boundaries.
Older previews do not have a guaranteed backport or response schedule.

## Report privately when possible

Use GitHub's **Report a vulnerability** action on the repository Security tab if it is
available: [security advisories](https://github.com/Ag3497120/cleanroom/security/advisories).
If private reporting is unavailable, open a minimal issue requesting a private contact
channel. Do not put exploit details, tokens, personal records or live endpoints in a public issue.

Include the affected version, environment, minimal synthetic reproduction, impact and
whether external data or permissions were involved. Never probe other users or deployed
services without authorization. Do not attach a real user's notebook or credentials.

If you exposed a secret, revoke or rotate it at its provider. Deleting a post alone is insufficient.
Maintainers will coordinate a fix and disclosure when possible; no fixed response-time guarantee is offered.

## Boundaries to keep explicit

- Agent/Owner panes are an interface, not operating-system isolation.
- A configured sandbox or external harness is not proof that isolation is enforced.
- AI-written explanations do not constitute execution evidence or permissions.
- API keys entered in the browser are held transiently and sent only by explicit action
  to the selected endpoint. Browser extensions, hosts and providers have their own risks.
- Never expose authenticated subscription sessions or unprotected local model ports to public visitors.
- Project logs, personal profiles and imported skills may contain sensitive information.

For ordinary bugs and usage questions, use the public issue templates with synthetic data.
