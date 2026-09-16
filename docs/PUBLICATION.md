# Public presentation and trust boundaries

## What this publication does

Repository: **Ag3497120/cleanroom**. Product: **Cleanroom**. Kernel: **Vera**. Existing CLI: **verantyx**.
Historical requests embedded in supplied notes are documentation sources, not new rename or implementation instructions.

The README, five operating guides, logo, programmed CLI recording, author page, and landing page describe an evolving source preview. There is no new claim of full MVP readiness or of completing all live-model evaluations.

## GitHub About

> Build with AI without giving up authorship. A local-first Agent/Owner workspace that keeps your decisions, understanding, evidence, and experience.

Describe the human outcome first, the two-pane workspace second. Avoid “deterministic intelligence”, “fully sandboxed”, “human mastery certified”, or “all tests pass”.

## Four distinct surfaces

| Surface | Execution | Data |
|---|---|---|
| Pages interaction playground | Scripted UI by default; beta AI conversation is a separate explicit action | In-memory notes, cleared by reload; no project access |
| Recorded CLI GIF / MP4 | Real CLI UI with fixture work | Public scripted data; no live-model success claims |
| Local CLI / private Atlas | Configured work providers and local notebook | Personal/project stores; explicit sharing controls |
| Existing optional hosted compute gateway | Separate owner-operated service | Its own GitHub authentication, approval, retention and usage limits |

GitHub Pages only serves static files. It cannot run a model, authenticate the visitor into a native Codex session, or act as an OS sandbox. The gateway link does not silently start public compute.

## Credentials and subscriptions

The beta AI dialog can copy a handoff, import an answer, or explicitly call an OpenAI-compatible / Ollama endpoint. It may accept an API key into tab memory, never a subscription token. Keys are not persisted in localStorage, cookies or an application database. The field clears when sending starts or the dialog closes; this is not forensic memory erasure. The selected endpoint receives the key and prompt, and browser extensions may observe browser memory. They contain no analytics or external font requests of their own. Hosting infrastructure may retain access logs; providers and the separately configured gateway have their own policies. This is not a blanket “no data is ever retained” promise.

Use the official local Codex or Claude Code login from CLI setup. Their credential stores remain local to their tools. Do not expose authenticated Codex execution to untrusted public visitors. ChatGPT subscriptions are not an anonymous public API credit pool.

Connecting a visitor's local model from an HTTPS page requires an explicitly paired, origin-restricted local bridge and compatible browser networking permissions. That new bridge is **not implemented by this publication**. Direct browser API mode works only when the selected endpoint and browser allow it. It is a text conversation, not a filesystem/tool-capable CLI connection. Use the installed CLI for real work. Do not disable CORS globally or expose Ollama on an unauthenticated public address to make a demo work.

A guest model on the author's separate Mac needs a hardened gateway, quotas, cancellation, a bounded capability set, explicit consent and operations monitoring. The existing gateway integration remains available, but no new public Mac endpoint, tunnel, secret, or subscription relay is enabled here. Gateway execution and the split CLI are not claimed to have identical capabilities.

## Personal intent and licensing

The author's “sanctuary” explanation is a personal interpretation, not a claim that the Japanese term universally means that. The project has personal, non-commercial motivation. This statement does not introduce a non-commercial license or remove permissions in the repository's actual license.

## Sources and interpretation

The X post's URL, author and original posting date have not been provided. The supplied Japanese excerpt is attributed only as supplied material. Discussion summaries are not verbatim model transcripts or evidence that old quantitative claims are true. Device names, private workspace paths and tokens are excluded from the public origin notes.

## Maintenance

Five-language guides are human-readable translations of the same operating model. The runtime command catalogue remains the CLI parser. Translated docs do not imply every runtime message is localized. Re-record fixtures when keybindings or pane layout change; do not stage private `.verantyx`, personal databases, evaluation credentials, or local recordings of real projects.

## UI references

[Pi](https://pi.dev/) informed the logo / installation / demonstration sequence. [M3E Canvas](https://lnkiai.github.io/m3e-canvas/) demonstrated two useful AI entry points: a direct API call and a copyable external-agent instruction. Cleanroom implements its own interface and keeps credentials ephemeral rather than copying another site's retention behavior.

API payload references: [Ollama chat](https://docs.ollama.com/api/chat), [OpenAI chat API](https://developers.openai.com/api/reference/resources/chat), [official Codex authentication](https://learn.chatgpt.com/docs/auth). Provider availability and browser CORS are not guaranteed by the UI.
