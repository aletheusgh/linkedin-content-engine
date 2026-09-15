# Identity Model

Build four separate files under `.linkedin-content-engine/identity/`. Never collapse these layers into one profile.

## voice-profile.md

Purpose: model writing behavior, not biography.

Primary evidence:
- user-authored posts/shares with commentary
- user-authored comments
- user-authored replies
- additional writing samples explicitly supplied by the user

Ignore for voice:
- text written by third parties
- content that the user only liked/reacted to
- quoted/shared text unless the user's own commentary is separable

Capture:
- dominant language and code-switching
- sentence-length distribution: short / medium / long
- paragraph length
- opening styles
- vocabulary and jargon
- punctuation habits
- rhetorical devices
- directness vs hedging
- humor/irony level
- use of numbers and examples
- CTA habits
- emoji/hashtag habits
- phrases or patterns to avoid because they sound unlike the user

Include an `Evidence` section with approximate sample counts and date range.
Record the current dataset hash in `.linkedin-content-engine/identity/model-state.json`. If authorship is `unknown` or `mixed`, exclude the text from the voice model until the user confirms which text is theirs.

## proof-library.md

Purpose: approved factual substrate for content.

Use a table or structured bullets with:
- fact / claim
- category: role, company, project, metric, tool, responsibility, achievement, education, etc.
- status: verified / needs-confirmation / deprecated
- source type
- source detail/date when available
- safe wording

Promote a claim to `verified` only when it is explicit in profile/position data, an authoritative local document, or explicitly confirmed by the user.

Never infer seniority, ownership, results, years of experience, revenue, team size or business outcomes from topic familiarity alone.

## interest-map.md

Purpose: rank topics that consistently attract the user's attention.

Signals may include:
- authored posts/comments
- repeated reactions
- recurring keywords/entities
- profile skills

For each topic record:
- topic
- signal types
- frequency/recency
- confidence
- notes

A reaction is interest evidence, not endorsement evidence.

## opinion-map.md

Purpose: capture views the user has actually expressed.

For each opinion record:
- topic
- position summary
- supporting excerpts/paraphrases
- number of supporting signals
- contradictory/counter-signals
- last observed date
- confidence
- acceptable phrasing in future drafts

Only use user-authored text as opinion evidence. A reaction by itself cannot establish an opinion.

When evidence conflicts, preserve both sides and lower confidence.
