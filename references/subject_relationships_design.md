---
schema_version: 1
description: Design document for the subject_relationships data file (references/subject_relationships.yaml). Explains why the file pair exists, the agent-drafts-user-confirms maintenance contract, the path (a)/(b)/(c) workflow, the schema, and the runtime-overlay semantics. The data file itself is pure YAML and is read directly by agents; this design doc is read only by humans (or by an agent answering a design question on behalf of a human). Companion: references/subject_relationships.yaml (the data file), references/research_dimensions.md §6.3 (the subject_entity vs parent_or_issuer_entity separation contract), references/data_source_registry.md §6 (SEC EDGAR — the downstream consumer of the `listed` boolean).
---

# Subject Relationships — Design Document

## Quick start

If you only need to know two things:

1. **Where the data lives**: `references/subject_relationships.yaml`. That's the file agents read at runtime. This file you're reading now is the *design document* — it explains why the data file looks the way it does.

2. **Don't edit the data file by hand**. Entries are added via the path (a)/(b)/(c) workflow when `agents/subject_class_resolver.md` hits an unknown entity during a real research run. Manual edits skip the provenance discipline (`confirmed_by`, `sources`, etc.) and risk corrupting the contract.

Read the rest of this doc to understand *why* the file is designed this way.

## Why this file pair exists

The harness keeps two physically separate files for one logical concern:

| File | Content | Read by |
|---|---|---|
| `references/subject_relationships.yaml` | Pure YAML data — `entries:` + `pending_fill:` | Agents at runtime; humans rarely |
| `references/subject_relationships_design.md` | Pure markdown design rationale — this document | Humans, and agents only when answering a design question on behalf of a human |

The split was a B.0 mid-flight correction. The first draft of this file was a single markdown document with YAML data inlined as code blocks, justified as "human readability inline with data". That justification did not survive scrutiny: in this harness's agent-mediated workflow, no human directly reads the data section. Users see agent translations of entries (e.g. *"Circle is listed on NYSE as CRCL"*) — they do not open `entries:` in a text editor. Optimising for human-readable-inline-with-data added complexity (a markdown+YAML hybrid would have required a parser-based write tool — see `references/TODO.md` TD-013 for the lesson) to serve a need that did not exist.

The corrected architecture is **data file** (`subject_relationships.yaml`) + **design doc** (this file). Pure YAML is round-trippable via `yaml.safe_load` / `yaml.safe_dump` in three lines. Pure markdown is read only when somebody actually wants the design rationale.

The lesson is staged for `MEMORY.md` under "B.0 #16 MEMORY.md staging — pending lessons" in `references/TODO.md`: *when designing spec files in an LLM-agent workflow, ask "who directly reads this file, when?" before optimizing for human readability.*

## The two consumers of `subject_relationships.yaml`

The data file has exactly two consumers; both are agents.

1. **`P0_sec_email.applies_when`** — fires when `subject_entity.listed == true OR parent_or_issuer_entity.listed == true`. The booleans come from this file. Without this file, the gate cannot answer correctly and either over-fires (asks for SEC email pointlessly, or worse, fetches against the SEC with a misclassified entity) or under-fires (silently misses listed parents). The agent that owns the gate is `agents/sec_email_gate.md`.
2. **`agents/subject_class_resolver.md`** — at `P0_subject_class`, when the subject is an asset/token or a project whose lineage matters (Arc → Circle; USDC → Circle; Base → Coinbase; Tempo → Stripe), the resolver looks up the parent/issuer here and populates `parent_or_issuer_entity` in `meta/run.json`.

A hallucination in `subject_relationships.yaml` propagates downstream as a silent failure on either consumer. Hence the maintenance principle below.

## Maintenance principle (load-bearing)

**Agent may research, agent may draft, agent MUST NOT write autonomously. Every entry is confirmed by the user at least once.**

The agent-drafts-user-confirms model is non-negotiable for this file. The cost of a wrong fact (false `listed: true`, wrong ticker, wrong exchange) is silent and only catchable by independent re-verification — which is what user confirmation provides. The harness explicitly trades the speed of autonomous writes for the auditability of every entry having a human signature.

### Why hybrid (not autonomous, not pure-manual)

| Pure-autonomous write | Pure-manual entry | **Hybrid (this contract)** |
|---|---|---|
| Fast but unverifiable; one bad CIK propagates silently | Slow; user types every fact from scratch | Agent does the legwork (search, draft, source URLs); user confirms in one keypress |
| No human signature → no audit chain | Maximum signature → maximum friction → entries don't get added → table stays sparse → gate fails silently | Per-entry human signature with low friction |

The path-(a) draft is the difference between this contract and pure-manual entry: the user does not type the entry, only verifies it. The path-(c) shortcut is reserved for cases where the user already has the facts at hand and finds drafting overhead unnecessary.

## Workflow contract — paths (a) / (b) / (c)

When `subject_class_resolver` encounters an entity that is not in `entries:` and that the resolver believes may need an entry (typically because the subject is an asset/token, or the resolver heuristically detects a parent relationship in the prompt), the resolver halts at `P0_subject_class` and offers the user three explicit paths.

The **execution** of the workflow (verbatim user-facing prompt, source allowlist + trust tiers, what to fetch and how to label sources) is the resolver agent's contract — see `agents/subject_class_resolver.md` §"Source allowlist + trust tiers" and §Procedure Step 4. This document defines the **shape** of the three paths; it does not re-author the resolver's execution rules. One contract has one canonical author file.

### Path (a) — Research + draft (recommended for new entities)

1. The resolver invokes a mini-research subroutine restricted to **non-SEC public sources only** with a three-tier trust framework (see `agents/subject_class_resolver.md` §"Source allowlist + trust tiers"). Tier 1 = entity-controlled (official site, IR page, press release); tier 2 = established secondary (CoinGecko, mainstream news, Crunchbase) — corroborated for any `listed: true` claim; tier 3 = identity-only (Wikipedia, glossaries) — never for `listed`, `ticker`, `exchange`, or financial facts.
2. **SEC EDGAR is forbidden during path (a)** — the `P0_sec_email` gate has not yet fired, no email has been collected, and the dependency direction is strict: `table entry → gate trigger → EDGAR access`; never the reverse. See `agents/subject_class_resolver.md` §Forbidden for the verbatim chicken-and-egg statement.
3. The agent synthesises a candidate entry with **explicit source URLs for every fact**.
4. The agent presents the candidate to the user verbatim, using this exact format:
   ```
   Candidate entry for [entity_name]. Please review and confirm:
     [YAML/JSON entry]
   Confirm? [Y/n/edit]
   ```
5. On `Y` — write the entry to `subject_relationships.yaml` with `confirmed_by: "user"`, `confirmed_at: <today ISO date>`, `next_review_due: <today + review_cadence_months (default 6)>`.
6. On `edit` — surface the specific field the user wants to change, accept the edit, re-present the whole entry, loop until `Y` or `n`. Never write a partially-confirmed entry.
7. On `n` — do **not** write. Resolver falls back to path (b) or halts the run for user direction.

### Path (b) — Skip and defer

1. `P0_sec_email` auto-skips with `source: "applies_when_false_unverified"` (distinct from `applies_when_false_verified`, which means the resolver positively checked and confirmed the entity is not listed). The distinction matters for audit — `unverified` says "we did not check"; `verified` says "we checked and the answer is no".
2. The entity is appended to the top-level `pending_fill:` list in `subject_relationships.yaml` with `name`, `date_encountered`, and `run_id`.
3. Research continues with the **default-not-listed assumption** for the rest of this run. The run completes without SEC EDGAR access for this entity.
4. The entry can be filled in a later run via path (a) or (c).

### Path (c) — User provides facts directly

1. The user types the facts (`subject_entity_type`, `listed`, `ticker`, `exchange`, ...) directly without an agent draft.
2. The agent echoes back the exact entry it will write, in the same `Confirm? [Y/n/edit]` shape as path (a) step 4.
3. On `Y` — write with `confirmed_by: "user_direct"`, `confirmed_at: <today ISO date>`, `next_review_due: <today + 6 months>`.

## Re-review cadence

Every entry auto-flags for re-review every **6 months** (the `next_review_due:` field is the trigger), or sooner if any of these incident triggers fire:

- The entity completes an IPO, gets delisted, gets acquired, changes exchange, or changes its corporate parent.
- An `INCIDENTS.md` entry references the entity as the source of a gate-bypass or PII-leak failure.
- A red-team review at P5.7 flags the entry as stale (e.g., "the `listed` claim references an entity that filed a Form 25 last quarter").

The `review_cadence_months` field (optional, default `6`) overrides per-entry. Stripe's seed entry sets `review_cadence_months: 3` because a Stripe IPO would flip `listed: false → true` and dramatically change `P0_sec_email.applies_when` results; the asymmetric cost of missing that transition justifies tighter cadence. The override is a structured machine-readable field, not a prose flag in `note:`.

`tools/io/lint_subject_relationships.py` (TD-012, to be authored in B.1) raises a **warning** (not a halt) at `P_INCIDENT_PRECHECK` when `next_review_due < today` for any entry the current run will consult. Users refresh by re-confirming with `confirmed_at: <today>`, which slides `next_review_due` forward by `review_cadence_months` (default 6).

## Schema

The canonical instance lives in `references/subject_relationships.yaml`. This section explains the fields.

```yaml
schema_version: 1

entries:
  <EntityName>:
    subject_entity_type: company | foundation | dao | asset_token | other
    listed: <bool>                     # true if shares publicly traded on a stock exchange
    ticker: <symbol> | null            # required if listed; null otherwise
    exchange: <exchange-id> | null     # required if listed; null otherwise; multi-exchange recorded as "NASDAQ/TSX"
    relationship_to_subject: <label>   # default "self" — overridden at runtime when this entity is a parent of another subject (see "Worked example" below)
    confirmed_by: user | user_direct   # who confirmed this entry — see workflow paths (a) and (c)
    confirmed_at: <ISO date>           # YYYY-MM-DD
    sources:                           # at least one URL backing the facts; required field
      - <url>
    next_review_due: <ISO date>        # confirmed_at + review_cadence_months (default 6); slides forward on re-confirm
    review_cadence_months: <int>       # OPTIONAL; defaults to 6; override when listed-status is volatile
    note: <free text>                  # optional context; multi-line OK

pending_fill:                          # populated by path (b)
  - name: <entity_name>
    date_encountered: <ISO date>
    run_id: <run-id>
```

### Schema notes

- **`relationship_to_subject: self`** is the default for every static entry. At runtime, when an entity is resolved as `parent_or_issuer_entity` for a *different* subject, the resolver overlays a specific contextual label (`issuer`, `parent`, `parent_chain_operator`, etc.) into the runtime `meta/run.json` object — the static file is **not** edited. See the worked example below.
- **`sources`** is required (must be at least one URL). The lint at pre-check rejects entries with empty `sources`. URLs should be HEAD-resolvable and on stable hosts (avoid PDF anchors, archive.org snapshots, or anything that 404s within a year).
- **`review_cadence_months`** is **optional**; default `6`. Override per-entry when the entity's `listed` status is volatile and missing a transition has asymmetric cost — e.g., Stripe's seed entry sets `review_cadence_months: 3` due to active IPO speculation. The lint tool (TD-012) computes the allowed `next_review_due` window from this field; do **not** parse prose `note:` for the cadence override.
- **`pending_fill`** is a flat list. When an entity is filled via path (a) or (c) later, the `pending_fill` entry is removed in the same write.

## Worked example — runtime overlay (USDC researched, Circle is parent)

Suppose a future run resolves `subject_entity = USDC` (type `Asset/Token`) with USDC not yet in `entries:` and Circle already seeded. The static Circle entry in `subject_relationships.yaml` remains exactly as written:

```yaml
Circle:
  ...
  relationship_to_subject: self
  ...
```

The static `self` value reflects "when Circle is researched as the subject, the relationship is self". For the USDC run, the resolver does **not edit** Circle's static entry. Instead, it constructs a runtime `parent_or_issuer_entity` object in `meta/run.json` by reading Circle's static fields and **overlaying** the contextual relationship label:

```json
{
  "subject_entity": {
    "name": "USDC",
    "type": "Asset/Token"
  },
  "parent_or_issuer_entity": {
    "name": "Circle",
    "listed": true,
    "ticker": "CRCL",
    "exchange": "NYSE",
    "relationship_to_subject": "issuer"
  }
}
```

The `relationship_to_subject` field in the runtime object is `"issuer"` — not `"self"` — because the relationship is computed contextually to *this run's* subject (USDC), not to Circle's own static record. The static field is the entity's self-description; the runtime field is the per-run contextual label.

This is why every static entry carries `relationship_to_subject: self` even though it looks redundant — the field reserves the slot in the schema so the runtime overlay has somewhere to write, and the `self` value is the legitimate answer when the entity is the subject of its own research run. The two are different layers (per `references/research_dimensions.md` §6 meta-principle: authority / storage / context separation), and the schema makes the layering explicit rather than implicit.

## Asset/token entries (USDC, ETH, etc.)

The B.0 seed contains only `subject_entity_type: company` entries — legal entities that directly correspond to listed-or-private corporations. The schema supports `asset_token`, `foundation`, `dao`, `other` types, and they are added **on demand** via the workflow above.

When the harness encounters an asset/token subject whose issuer/foundation **is** in `entries:` (e.g., USDC → Circle is already seeded), the resolver may proceed without writing a new `asset_token` entry: it populates `parent_or_issuer_entity` directly from the company entry, sets `subject_entity` to the asset, and leaves a `pending_fill` stub for the asset itself if the run benefits from tracking it. Whether to *always* add an `asset_token` entry vs *only* add one when runtime resolution is ambiguous is a Phase B.1 implementation question for `agents/subject_class_resolver.md`; the schema accommodates either pattern.

When the asset/token's issuer is **not** in `entries:` (e.g., a new prompt about a token issued by a project we haven't seen), the resolver follows path (a) to draft the issuer entry first, then optionally drafts the asset entry — the issuer is the load-bearing one for `P0_sec_email.applies_when`.

## Linting (forward-looking)

`tools/io/lint_subject_relationships.py` is to be authored in B.1 — full scope in `references/TODO.md` TD-012. It runs at `P_INCIDENT_PRECHECK` and:

- Validates `schema_version: 1`.
- For every entry, validates required fields are present and well-shaped: `subject_entity_type`, `listed` (bool), `confirmed_by` (`user` or `user_direct`), `confirmed_at` (ISO date), `next_review_due` (ISO date), `sources` (non-empty list of URLs), `relationship_to_subject` (string, defaults `self`).
- When `listed: true`, `ticker` and `exchange` must be non-null strings; when `listed: false`, both must be `null`.
- `next_review_due >= confirmed_at` and `next_review_due <= confirmed_at + (review_cadence_months OR 6) + 14d` drift tolerance.
- Every URL in `sources:` resolves via HEAD request (allow `200/301/302`; warn on `4xx/5xx/timeout`).
- `pending_fill[].name` does not collide with any `entries:` key.

Lint failures **raise warnings** for stale `next_review_due` and unresolvable source URLs; they **raise errors** for missing required fields, schema mismatches, or `null` tickers on listed entities. Errors at `P_INCIDENT_PRECHECK` halt the run.

The write tool that creates entries (`tools/io/append_subject_entry.py`, TD-013, B.1) is the complement — a thin pyyaml wrapper with atomic write (temp + rename), alphabetical-order preservation, and pending_fill handling.

## Cross-references

| File | Use |
|---|---|
| `references/subject_relationships.yaml` | **The data file**. Read at runtime. Manual edits forbidden. |
| `references/research_dimensions.md` §6.3 | The `subject_entity` vs `parent_or_issuer_entity` separation contract — this file populates the runtime objects |
| `references/data_source_registry.md` §6 SEC EDGAR | Downstream consumer of the `listed` boolean; SEC EDGAR access is gated by `applies_when` reading `subject_relationships.yaml` |
| `references/p0_gates.md` §`P0_sec_email` | The gate that consumes `listed` to evaluate `applies_when` |
| `agents/subject_class_resolver.md` (B.0 #3) | Reads `subject_relationships.yaml` at `P0_subject_class`; implements the path (a)/(b)/(c) workflow on misses; owns the source allowlist + trust tier framework |
| `agents/sec_email_gate.md` (B.0 #9) | Reads `entries[<entity>].listed` to compute `applies_when` |
| `tools/io/append_subject_entry.py` (TD-013, B.1) | Atomic write tool — pyyaml wrapper |
| `tools/io/lint_subject_relationships.py` (TD-012, B.1) | Pre-check lint for staleness, missing fields, broken URLs |
