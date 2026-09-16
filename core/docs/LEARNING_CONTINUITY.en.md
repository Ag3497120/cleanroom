# Unpack skills and technologies

Cleanroom keeps AI procedures separate from a person's experience.
When you want to learn a skill or technology, open the prerequisites, intermediate
steps, alternatives, failure conditions and checks linked to the original work.

## Capture before details disappear

The Work AI can leave optional learning_notes during implementation, normally
zero to two notes and at most four per turn. These are user-facing explanations,
not hidden chain-of-thought. They use only the personal context shared at that time.

Original Work events preserve proposals, candidate contents, actual tool receipts,
failures and owner replies separately. AI explanations are neither execution
evidence nor proof of human mastery. Invalid learning notes do not invalidate an
otherwise valid WorkResult. Missing historical explanations remain missing.

With the personal notebook enabled, an index of the work events is also stored in
your private cross-project database. An index failure does not cancel committed
project work. You can explicitly recover the index without reconstructing a missing
historical profile:

~~~sh
verantyx my-learning index --run RUN_ID --yes
~~~

This increases local storage. The existing whole-notebook backup still has a
5,000-record / 8 MB limit; large segmented backups are not implemented.

## Open an explanation

Use F2 > Learning guides, or open a skill and select Unpack.
No command vocabulary is required for normal use.

~~~sh
verantyx my-learning
verantyx my-skills unpack --id SKILL_ID
verantyx my-learning topics --json
verantyx my-learning unpack --skill SKILL_ID --send
verantyx my-learning unpack --technology Flask --send
verantyx my-learning unpack --run RUN_ID --technology Swift --send
~~~

Technology discovery uses structured tags proposed by the AI, not keyword
classification of your request. Without tags, select a work run directly.

The interactive flow shows the number of source events, page coverage and an
optional full outbound preview before you approve generation. It uses your selected
Reflection AI. Each new generation is another version, not an overwrite.

Large traces are paged at event boundaries, never silently summarized or truncated.
The interactive flow starts with page 0. Use --page 1 and later pages as needed.
An individual event exceeding the request budget is refused rather than truncated.
A partial page is not represented as coverage of the entire project.

## Three views

~~~sh
verantyx my-learning show --id GUIDE_ID --detail summary
verantyx my-learning show --id GUIDE_ID --detail full
verantyx my-learning show --id GUIDE_ID --detail sources --json
verantyx web
~~~

Summary is a lightweight entry point. Full guide keeps the detailed explanation,
examples, checks and delegation options. Original records shows the exact events
used by that guide page and their provenance. My Atlas offers the same three views.

Reading a saved guide or opening the Web view does not call a model, mark a skill
learned, activate a rule or grant a capability. Guides do not add deficit scores to
the personal experience graph. Full means the saved record, not unavailable model
reasoning or unobserved native operations inside an external harness.

## Personal context

The local index can retain the profile snapshot used at the time.
Later generation uses your currently shared profile text, plus hashes of historical
versions and references still shared now. Old profile bodies are not automatically
re-sent merely because they were once shared.

Previously written work events can themselves contain information shared earlier.
Revoking profile sharing does not erase that meaning from old events. Review the
outbound packet before sending. No automatic cloud, other-Mac or employee sharing
is added. Delegation and skipped learning are never evidence of low ability.

## Optional books and documentation

~~~sh
verantyx my-learning unpack --technology Flask --send --web \
  --query "Flask official tutorial" \
  --query "Flask book author publisher"
~~~

The default search backend needs BRAVE_SEARCH_API_KEY. Only your explicit queries
are sent to the search provider, not an automatically generated dump of your project
or profile. The guide can recommend only resource IDs returned by the search.
Search failure does not invent books or discard the learning guide.

Titles, URLs, snippets, retrieval dates and providers are stored separately from the
AI's recommendation. Search snippets are not a read book, verified edition, price,
availability or proof that a tutorial works. The implementation follows the
[official authentication](https://api-dashboard.search.brave.com/documentation/guides/authentication)
and [search API](https://api-dashboard.search.brave.com/api-reference/web/search/get).

A trusted local search skill can implement the JSON adapter contract documented in
[the Japanese guide](LEARNING_CONTINUITY.ja.md#本公式資料を探す). Select it with
--search-adapter and --trust-search-adapter. This is not a direct MCP transport.
The native search executable is not covered by the external Work sandbox.

## What is not guaranteed

Preserving source text reduces losses caused by end-of-task summaries; it does not
recover details a model never recorded. Existing source IDs do not prove semantic
correctness. Guide quality, personalization and learning benefit still need real
model and human evaluation. Reference, delegation and the next opportunity remain
valid choices, not unfinished homework.

## Connections, implementation moments and model handoff

[Obsidian / MCP / skill imports / model roles / language and context](NOTEBOOK_CONNECTIONS.en.md)
