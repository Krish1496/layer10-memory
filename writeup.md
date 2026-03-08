# Layer10 Take-Home — Write-Up

## Corpus

**Source**: 15 synthetic email messages included in `data/corpus.json`.

The emails simulate a real engineering team working on "Project Nexus" — a data-sync platform. They contain realistic patterns: assignments, technical decisions, reversals, bug reports, personnel changes, and status updates. I chose a self-contained corpus so the project runs end-to-end without any downloads.

**To reproduce**: simply clone the repo and run `python run_pipeline.py`. The corpus is at `data/corpus.json`.

---

## Structured Extraction

### Ontology / Schema

**Entity types**: `Person`, `Project`, `Component`, `Technology`, `Infrastructure`

**Predicate types** (claim types): `LEADS`, `OWNS`, `ASSIGNED_TO`, `USES`, `DECIDED_ON`, `DEPLOYED_ON`, `HAS_STATUS`, `FIXED`, `APPROVED`, `CHANGED_FROM`

**Core tables in SQLite**:
- `sources` — raw messages (author, timestamp, body, subject)
- `entities` — people/projects/components with a `canonical_id` for dedup
- `aliases` — alternate names for the same entity
- `claims` — extracted facts (subject → predicate → object) with confidence and `is_current` flag
- `evidence` — links each claim to the exact message excerpt that supports it
- `merge_log` — full audit trail of every dedup merge

### Grounding

Every claim has at least one evidence row pointing to: `source_id` (the exact email), `excerpt` (the sentence), and `offset_start` (character position). Nothing enters the memory graph without evidence.

### Extraction Approach

In **demo mode** (default), pre-computed extractions are loaded from `src/extract.py`. In **API mode** (`--api`), each message is sent to `claude-haiku-4-5-20251001` with a structured prompt. The model returns JSON with entities and claims; we strip any markdown fences and parse it.

**Validation and repair**: if the model returns a non-entity as a claim subject (e.g., a raw string not in our entity map), we do a database lookup by name. If still not found, the claim is skipped — we never insert a dangling reference.

**Schema versioning**: the schema is versioned implicitly by the pipeline version. In production you'd add a `schema_version` column and a `backfill_log` table, and re-run extraction when the schema changes.

**Quality gates**: confidence < 0.7 claims are filtered during retrieval. In production, add a human-review queue for confidence < 0.5 and cross-evidence support checks (a claim supported by only one source gets lower durable confidence).

---

## Deduplication and Canonicalization

### Entity Dedup

`src/dedup.py` compares every pair of entities within the same type:
1. **Exact lowercase match** — trivially the same
2. **Initial abbreviation** — "A. Chen" matches "Alice Chen" (same last name, first initial)
3. **Subset words** — all words of the shorter name appear in the longer
4. **Initials match** — "bob.m" → B.M. matches "Bob Martinez"

When a match is found (score ≥ 0.8), the shorter/less complete name is merged into the longer canonical form. The old name is stored as an alias. All claims pointing to the dropped entity are re-pointed to the canonical one.

### Claim Dedup

After entity dedup, claims with identical `(subject_id, predicate, object_id)` tuples are merged: we keep the first one and re-attach all evidence to it. This handles the case where 5 emails all say "Alice leads the project" — we store one claim with 5 evidence items.

### Conflicts and Revisions

When a new extraction says `is_current=False` for a claim, we:
1. Find the existing matching claim
2. Call `mark_claim_historical(claim_id)` — sets `is_current=0` and `valid_until=now`

This creates a timeline: you can see "Project Nexus USES PostgreSQL → USES MySQL → USES PostgreSQL" with each phase grounded in evidence. Nothing is deleted.

### Reversibility

Every merge is logged in `merge_log` with `from_id`, `to_id`, `reason`, and timestamp. To undo a merge, you'd set `entities.canonical_id = id` for the dropped entity and re-point the affected claims. This is a supported future operation — the data is never destroyed.

---

## Memory Graph Design

**Store**: SQLite with 6 tables (see above). Simple, zero-infrastructure, portable.

**Time model**:
- `valid_from` / `valid_until` on claims: when the fact became true and when it was superseded
- `ts` on sources: the original event time (email sent time)
- `created_at` on entities/claims: ingestion time

**Idempotency**: `add_source` uses `INSERT OR IGNORE`. `add_entity` checks by name before inserting. `add_claim` checks for duplicates before inserting.

**Deletions / redactions**: to handle a redacted message, set `sources.body = "[REDACTED]"` and `is_current=0` on all claims that only have evidence from that source. Claims with multiple sources keep their other evidence.

**Permissions** (conceptual): add a `source_acl` table mapping `(source_id, user_id)`. At retrieval time, filter `evidence` to only rows where the user has access to the source, then filter out claims that become un-evidenced. A user never sees a claim they can't trace back to a source they're allowed to read.

**Observability**: log extraction latency, parse errors, number of skipped claims (bad subjects), and dedup merge counts per run. Alerting threshold: >10% of claims skipped in a batch → degraded extraction quality.

---

## Retrieval and Grounding

`src/retrieve.py` takes a question string and:
1. Tokenizes it into keywords
2. Scores all entities by keyword overlap with their name
3. Takes the top 3 matched entities
4. Collects all claims for those entities
5. Ranks claims: boosts `is_current`, weights by confidence, boosts predicate-keyword overlap
6. Fetches evidence for each claim
7. Returns a structured context pack

Every returned item includes: subject, predicate, object, confidence, is_current, and the full list of evidence excerpts with source metadata (author, timestamp, email subject, source ID).

**Ambiguity handling**: conflicting claims (e.g., "Project Nexus USES MySQL" and "Project Nexus USES PostgreSQL") both appear in results, with `is_current` flags making it clear which is the current truth. Historical items are retained for auditability.

---

## Visualization

`viz/index.html` — single self-contained HTML file, no server needed.

- **Graph panel** (vis.js): nodes are color-coded by type (Person=blue, Project=green, Component=amber, Technology=red, Infrastructure=purple). Edges show predicates, dashed for historical claims.
- **Filters**: current-only / historical-only / all, plus entity type filter
- **Details panel**: click any node → see all its claims
- **Evidence panel**: click any claim → see the exact email excerpts that support it, with author, date, and source ID
- **Search tab**: keyword search across all claims; click a result to jump to that node
- **Merges tab**: full audit log of all dedup merges

---

## Layer10 Considerations

### Adapting to Email, Slack, Jira/Linear

**Ontology changes**: add `Channel`, `Thread`, `Ticket`, `PR`, `Comment` entity types. Add predicates: `MENTIONED_IN`, `BLOCKS`, `RESOLVES`, `CHANGES_STATUS_TO`. Person entities need richer identity fields (email, Slack handle, Jira username) for cross-platform resolution.

**Unstructured + structured fusion**: the key link is `Ticket ↔ Message`. When a Slack message references a Jira ticket number, add a `REFERENCES` claim. When a PR closes a ticket, add a `RESOLVES` claim. This creates a connected graph that lets you answer "what was the conversation that led to this decision?" even when the decision itself is only recorded in Jira.

**Long-term memory**: mark a claim as "durable memory" when it has ≥3 independent evidence items from ≥2 different channels. Ephemeral context is a single message that hasn't been reinforced. Durable memory persists across context windows; ephemeral context expires after N days without reinforcement.

**Grounding and safety**: every memory item must have at least one evidence pointer. If the source is deleted (Slack message deleted, Jira ticket redacted), the evidence excerpt is preserved but the `source_body` is marked `[REDACTED]`. Claims that become un-evidenced are demoted to `confidence=0.1` and flagged for review.

**Permissions**: memory retrieval is always filtered by the user's access to underlying sources. If a user can't read the Slack channel where a decision was made, they don't get the claim that decision produced — even if the claim itself is "public-sounding."

**Operational reality**:
- Incremental ingestion: process only new messages since last run (use `ts > last_checkpoint`)
- Cost: use a cheap model (Haiku) for extraction; route complex/ambiguous cases to a smarter model
- Evaluation: maintain a golden test set of 100 (message, expected claims) pairs; run it on every extraction pipeline change and alert on F1 drops
- Scaling: partition the DB by workspace/org; the schema is simple enough to shard by `source.workspace_id`
