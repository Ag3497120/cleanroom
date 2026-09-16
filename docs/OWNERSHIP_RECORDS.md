# Keeping the record without grading the person

## Three distinct cases

| Recorded input | Projection | What it does not imply |
|---|---|---|
| AI explanation with unknown source IDs | Source review pending | A valid citation, successful check or human mastery |
| Owner chooses "I understood" | Self-reported understanding | The person explained or applied it |
| Owner chooses "Explained" or "Applied" | The chosen experience state | Independent certification |
| Owner chooses "Next time" | A contextual bookmark | An overdue task or lack of ability |

## Source review

Work events retain original explanation payloads even when source references are invalid.
The implementation-time catalogue and Owner view expose those notes as pending rather
than silently dropping them. Pending notes use IDs distinct from existing accepted-note
IDs. They can be opened in Unpack, which reads the actual saved trace and records a
new explanation proposal. It does not rewrite the old note, repair citations by guessing,
or block a completed work result.

Generation schemas distinguish project event IDs from personal profile IDs. This is an
identifier boundary, not a keyword-based classification or a requirement that AI answers agree.
Runtime validation still permits useful work when optional learning notes are malformed.

## Experience and bookmarks

New owner-understanding records keep technology tags and project attribution as structured
source metadata. Older records can recover those fields only from the referenced saved
moment. Atlas never splits free text to guess a person's skills.

Atlas includes both skills-board bookmarks and lessons explicitly deferred to next time.
A deferred implementation-time note also appears as a bookmark, not an experience claim.
Reference and delegation remain separate choices. Only the person records their experience;
saving, importing, reading, skipping or delegating does not mark a skill as learned.

These are implementation boundaries, not an assertion that every live-model evaluation
or every teaching outcome has passed.
