---
description: Forward-looking design notes deferred until the fork stabilizes. Each entry is a deliberate non-decision recorded so it does not get lost — not a generic backlog.
---

# stack-anamnesis — Deferred Design Notes

## TD-001 — X long-post delivery: quality rubric + red-team, not SHA-locked template

**Decision (2026-05-11):** The X (Twitter) long-post / thread emitter will NOT use the SHA256-pinned locked HTML template approach inherited from equity (I-002 lineage in `references/equity_incidents_archive.md`). Use instead:

- **Quality rubric** — checklist of required structural elements per post type (hook / claim / evidence / counter / CTA), enforced as a fail-closed validator analogous to the role `validate_report_html.py` plays for reports, but operating on prose structure rather than HTML SHA.
- **Red-team narrative attacker** — repurpose the existing `red_team_narrative.md` pattern to attack hooks, claims, and missing counter-evidence in the post draft.
- **Key-element post-check** — at delivery, verify each rubric element is present and non-degenerate (not a placeholder, not under length floor).

**Why:** SHA pinning fits HTML reports because the visual layout *is* the contract; for X posts the *content shape* is the contract, and a SHA pin would either be too rigid (every wording change breaks the pin) or meaningless (any text passes a SHA check on an outer wrapper). Rubric + narrative red-team + element post-check is the right shape for free-form prose with a strict structural skeleton.

**Revisit when:** the first X long-post phase is being designed.

## TD-002 — Add `sector` and `stack_position` scopes when pipelines exist

**Decision (2026-05-12):** P0_scope enum starts with `single` only. The multi-subject scopes (sector for horizontal comparison, stack_position for vertical dependency trace) are deferred until their pipelines exist.

**Why:** P0 gate values must route to real phase pipelines. Adding enum options without backing pipelines violates the "rule must be enforceable in code" principle inherited from references/inherited_principles.md.

**Revisit when:**

- 20+ single-scope runs accumulated, OR
- An incident logs "writer attempted comparison but no pipeline available", OR
- Manual sector/stack-trace work becomes a recurring pain

## TD-003 — Add 365d freshness window when mature subjects warrant it

**Decision (2026-05-12):** P0_freshness enum is `7d / 30d / 90d / since_TGE`. Skips 365d because current research subjects (crypto payments infra, agentic payments) are mostly < 2 years old, where 365d ≈ since_TGE provides no analytical difference.

**Revisit when:**

- We start covering protocols > 2 years old (Aave, Uniswap, Maker) and finding lifetime data too noisy
- A validator phase wants to compare "365d window vs lifetime" as a signal-quality check
- An incident logs "writer averaged across full history when only recent year was relevant"

## TD-004 — Add issuer attestation feeds to data_source_registry

**Decision (2026-05-12):** data_source_registry starts with four core APIs + RPC tier. Issuer attestation feeds (Circle transparency, Tether reserves, Paxos attestations) are deferred to a separate entry.

**Why deferred:** each issuer publishes attestations in inconsistent shapes (PDF reports, HTML pages, JSON APIs). Designing uniform fetching across them is non-trivial and shouldn't bottleneck Phase A.

**Workaround in the meantime:** agents can use web_fetch to grab issuer transparency pages on demand, with the URL noted in the report's source list. RPC tier covers the on-chain truth side (verifying reserve balances), so 80% of attestation research is already possible.

**Revisit when:**

- First stablecoin issuer research run produces an incident around "couldn't verify reserve composition", OR
- 3+ runs require manual transparency page parsing

## TD-005 — Add CEX APIs (Binance, Coinbase) when listing/flow research warrants it

**Decision (2026-05-12):** CEX APIs not included in v0 registry. Most exchange-related data (volume, listing status, price) is available from CoinGecko without API key complexity.

**Why deferred:** CEX APIs require API key management, auth rotation, and per-exchange rate-limit handling — significant engineering load for coverage that overlaps ~80% with CoinGecko.

**Revisit when:**

- Custody flow research (how much USDC sits on Coinbase vs in self-custody) becomes a recurring need, OR
- Proof-of-reserves analysis across multiple CEXes is required, OR
- An incident logs "CoinGecko data insufficient for [specific question]"

## TD-006 — Re-establish locked-skeleton HTML template discipline when crypto report skeleton is designed

**Decision (2026-05-12):** Removed the "Locked HTML template" Hard Rule from `MEMORY.md`. The deleted rule pinned `skills_repo/er/agents/report_writer_{cn,en}.md` to a SHA256-pinned skeleton and required P5 to extract via `tools/research/extract_template.py` and substitute `{{PLACEHOLDER}}` only. That contract is equity-domain-specific and has no live surface in this fork until a crypto-domain report template exists.

**Why:** "A rule that is not enforceable in code is not a rule, it is a wish" (`references/inherited_principles.md`). With no crypto report skeleton, no `extract_template.py` invocation, and no SHA pin to enforce, the inherited bullet was advisory text masquerading as a hard rule — exactly the kind of memory inflation the Anamnesis Pattern is designed to prevent. Keeping it in `MEMORY.md` would also bake "the equity report shape" into the harness's frozen prompt, biasing future crypto report design.

**Revisit when:**

- The first `output_format: report` run is designed and a crypto-tailored HTML skeleton lands in the repo, OR
- A red-team incident logs "writer hand-crafted HTML instead of filling the skeleton" — at which point this rule re-enters `MEMORY.md` with the crypto skeleton's SHA pin and the new `extract_template.py` invocation path

## TD-007 — Decide QC merge math + competitive framework (Porter or replacement) in Phase B

**Decision (2026-05-12):** Removed the `## QC scoring math (P3.6)` section (the `weighted = 0.34·draft + 0.33·peer_a + 0.33·peer_b` rule with `|delta| > 1.00` change-or-maintain semantics) and the `## Porter score orientation` section (threat-scale 1–5; intense rivalry = high red) from `MEMORY.md`. Both are equity-research artefacts. The QC math assumed the draft+two-peer triangle from `skills_repo/er/agents/qc_*`; Porter's five forces were the canonical equity competitive frame.

**Why:** Crypto subjects may not fit Porter cleanly — a chain's "rivalry" is not the same shape as a public company's; an `agentic_payment_layer`'s "supplier power" is barely meaningful. The right competitive frame for stack-position-defensibility research may be Porter as-is, a modified Porter with crypto-specific forces, a new stack-position-defensibility rubric, or no framework at all. Deciding this in Phase A would foreclose the Phase B design exercise; keeping the equity-era math in `MEMORY.md` would gravitationally pull any new frame toward equity shape.

**Revisit when:**

- Phase B picks a competitive-analysis frame for crypto subjects, AND
- The QC peer agents (or their replacements) are wired into that frame — at which point the chosen scoring math re-enters `MEMORY.md` alongside the framework

## TD-008 — Re-introduce card-pack hard rules as a block when card production returns

**Decision (2026-05-12):** Removed three card-pack Hard Rules from `MEMORY.md`:

- "Logo save order" (P7 must create the cards/ directory, save `logo_official.png`, set `logo_asset_path`, only then proceed).
- "Palette consistency" (all six cards in one run must use the same `--palette`; palette is **not** stored in `card_slots.json`).
- "No fallback copy generation in EP" (`card_slots.json` must be complete before render; missing keys abort at load time).

These belong to the inherited EP (Equity Photo) pipeline's P7..P11 phases. With `P0_palette` retired and the card pipeline dormant in Phase A (`output_format` enum is `{report, thread}` only; no `cards` value), these rules guard a surface that does not currently exist.

**Why:** Card production is deferred to Phase C — see the Phase-A `P0_output_format` decision to ship without `cards`. Hard rules that protect a dormant pipeline create memory clutter and confuse future-us about which guardrails are live. The rules themselves are correct and load-bearing *when* card production is live; they should re-enter `MEMORY.md` as a block at that time, not piecemeal.

**Revisit when:**

- `output_format` enum widens to include `cards` (or equivalent), AND
- The card-production pipeline is being re-implemented for the crypto subject classes — at which point all three rules return as a block, repalleted and renamed for the crypto card design

## TD-009 — Re-introduce secret-handling discipline (model on retired SEC EDGAR rule) when first secret-requiring crypto API is integrated

**Status:** **closed 2026-05-13** by B.0 #1.5 — pattern instantiated for SEC EDGAR in `references/data_source_registry.md` §6 (re-added as the sixth registered source with the I-003-style two-UA contract: `sec_user_agent` for `*.sec.gov` hosts only; `public_user_agent` PII-free for everything else). The MEMORY.md privacy-invariant bullet returns in B.0 #16 (MEMORY.md rewrite). Template preserved here as forward reference for the next secret-requiring source (Dune API key, Etherscan/Alchemy/Infura/QuickNode keys, Pro CoinGecko key) when those land in B.1.5+.

**Decision (2026-05-12):** Removed the SEC EDGAR email privacy bullet from `MEMORY.md`'s `## Privacy invariants` section. The deleted bullet stated: "SEC EDGAR email is **never** persisted. It lives only as a runtime arg to `tools/research/sec_edgar_fetch.py`." With `P0_sec_email` retired and SEC EDGAR not a crypto-domain data source, the rule has no live surface.

**Why:** The *shape* of the rule (never-persist, runtime-only, regex redaction guard with a `tests/test_db_pii.py` regression) is the right template for any future API key or credential the crypto harness needs — Dune API key, Alchemy/Infura/QuickNode keys, Etherscan family keys, Pro CoinGecko key, RPC bearer tokens (see `references/data_source_registry.md` for the full key inventory). But the SEC-specific instance does not apply. Removing it now and re-introducing the pattern when the first secret-requiring API is integrated keeps the harness from carrying a dead rule while preserving the template's existence as this TD.

**Revisit when:**

- ~~The first secret-requiring crypto API is integrated~~ — fulfilled by SEC EDGAR re-add in B.0 #1.5.
- The next non-SEC secret-requiring API is integrated (Dune, Etherscan, CoinGecko Pro, or any RPC tier) — re-open as TD-009b or a new TD for that key family. The shape of this entry is the template: per-source key file (`~/.config/anamnesis/<provider>.key`), per-source redaction guard, `tests/test_db_pii.py`-style regression.

## TD-010 — Phase B harmonization pass: stale MEMORY.md references in orchestrator.md §P1+ and HARNESS.md ownership table

**Decision (2026-05-12):** orchestrator.md:174 references "QC scoring math from MEMORY.md" (the equation deleted in Phase A per TD-007), and HARNESS.md:240 lists "Locked HTML template" in an ownership table (the hard rule deleted in Phase A per TD-006). Phase A's scope discipline (P0-only) left these untouched. Both will be resolved during Phase B's broader orchestrator §P1+ and HARNESS rewrites.

**Revisit when:** Phase B redesigns the P1+ pipeline (which will rewrite orchestrator §P1+ end-to-end) and the HARNESS overview (which will rebuild the ownership table for the crypto-shaped pipeline).

## TD-011 — Validate seed CIKs on first SEC EDGAR fetch

**Decision (2026-05-13):** Coinbase, Galaxy Digital, Marathon Digital, and Robinhood entries in `references/subject_relationships.yaml` were drafted in B.0 #2 from non-SEC public sources only (the path-(a) workflow restriction is strict: agent may not consult SEC EDGAR to verify SEC-listing facts because `P0_sec_email` has not yet fired). Their `sources:` URLs are investor-relations pages, not EDGAR filings. The CIKs are not yet recorded; the `note:` field on each entry flags this.

**Why:** Path (a)'s restriction (no SEC EDGAR) is load-bearing — it prevents a chicken-and-egg dependency where the table entry needed to fire the gate is itself fetched via the gate's downstream API. The honest state of the table is "drafted from public sources; SEC verification pending first run".

**Required action when the first SEC EDGAR fetcher invocation lands** for each entity in B.1+: verify the CIK against EDGAR, update the entry with `sources: + <SEC EDGAR URL with CIK>` (don't replace existing sources, append), and refresh `confirmed_at: <that run's date>` so `next_review_due` slides forward by 6 months. If the CIK lookup returns a name mismatch, surface as an incident (the entry's listed-claim is wrong and the gate fired on bad data).

Circle's CIK (`0001876042`) is already user-confirmed and does not need re-verification.

**Revisit when:** B.1's first SEC EDGAR fetcher lands and runs against any of (Coinbase, Galaxy Digital, Marathon Digital, Robinhood).

## TD-012 — Implement subject_relationships.yaml lint tool

**Decision (2026-05-13):** `tools/io/lint_subject_relationships.py` is referenced in `references/subject_relationships_design.md` as the pre-check lint surface but does not yet exist. Authoring it in B.0 is out of scope (B.0 is documentation + agent contracts, no new tooling); B.1's first SEC EDGAR fetcher is the natural pairing because that's when the table starts changing under real runs. Lints the data file `references/subject_relationships.yaml` (pure YAML; `yaml.safe_load` parse — no markdown parsing needed since the B.0 mid-flight split moved design rationale to a separate `_design.md` file).

**Required behaviour:**

- Validate `schema_version: 1`.
- For every entry, validate required fields are present and well-shaped: `subject_entity_type`, `listed` (bool), `confirmed_by` (`user` or `user_direct`), `confirmed_at` (ISO date), `next_review_due` (ISO date), `sources` (non-empty list of URLs), `relationship_to_subject` (string, defaults `self`).
- When `listed: true`, `ticker` and `exchange` must be non-null strings; when `listed: false`, both must be `null`.
- `next_review_due >= confirmed_at` and `next_review_due <= confirmed_at + (review_cadence_months OR 6) + 14d` drift tolerance. The optional `review_cadence_months` field overrides the default 6-month cadence — Stripe's seed entry sets `review_cadence_months: 3` due to active IPO speculation; the lint must read the structured field, not parse the prose `note:`.
- Every URL in `sources:` resolves via HEAD request (allow `200/301/302`; warn on `4xx/5xx/timeout`).
- `pending_fill[].name` does not collide with any `entries:` key.

**Run surfaces:**

- `P_INCIDENT_PRECHECK` at run start (warn on stale `next_review_due`, error on missing required fields).
- Commit-time hook (so edits to `subject_relationships.yaml` are linted before commit).
- Manual invocation: `python tools/io/lint_subject_relationships.py [--check-urls]`.

**Revisit when:** B.1 SEC EDGAR fetcher lands (paired implementation).

## TD-013 — Implement append_subject_entry.py atomic write tool

**Decision (2026-05-13):** `tools/io/append_subject_entry.py` — thin wrapper around `yaml.safe_load` / `yaml.safe_dump` on `references/subject_relationships.yaml`, with atomic write (temp file + `os.replace` rename). Adds an entry under `entries:`, preserves alphabetical key order, removes the corresponding `pending_fill[]` stub if one exists, and refuses to overwrite an existing entry without an explicit `--update` flag. B.1 paired with the first SEC EDGAR fetcher (entries start changing under real runs at that point).

**Why it is its own TD:** the write tool is called from `agents/subject_class_resolver.md` path (a) step 4 and path (c) step 3. Authoring it in B.0 is out of scope (B.0 = documentation + agent contracts, no new tooling).

**History:** Original TD-013 scope was a 9-step parser-based tool targeting a markdown+YAML hybrid format. Reduced mid-flight in B.0 when data and design were split into separate files (`subject_relationships.yaml` + `subject_relationships_design.md`), eliminating the parser need. See "B.0 #16 MEMORY.md staging — pending lessons" below for the design lesson that drove the split.

**Revisit when:** B.1 SEC EDGAR fetcher lands (paired implementation, alongside TD-012).

## TD-014 — Consolidated event vocabulary registry

**Status:** **close-as-unnecessary 2026-05-13** during B.0 mid-flight restart to 4-gate design.

Original premise: 7-gate framework introduced 11+ meta/run.jsonl event names across agents, raising drift and forgotten-consumer concerns. User identified that 7-gate design was over-engineering inherited from Phase A; simplified 4-gate design has far fewer events. The drift risk that motivated TD-014 is substantially reduced.

**Resolution:** 4-gate design's event vocabulary is small enough to maintain inline in each agent file's "Events" section without a separate registry. If event count grows to 15+ in future phases (B.5+ red team, B.6 validator), revisit.

**Preserve as audit trail because:** the consolidated registry pattern itself may be valuable when event count grows. Reopen with explicit new justification (e.g., "we now have 20+ events across 8 agents and drift is occurring") rather than silently revive.

**History:** opened 2026-05-13 during 7-gate framework design; closed same day during mid-flight restart to 4-gate design.

## TD-015 — Orchestrator support for restart-from-gate

**Status:** **closed-as-unnecessary 2026-05-13** during B.0 #6 review.

Original premise: `scope_gate` path (a) narrow needed an internal restart-from-gate mechanism to continue the same run with a narrowed prompt. User challenged this design as overengineered given that the sector pipeline is not implemented and the narrowed prompt is genuinely a different prompt, not the same one "fixed".

**Resolution:** path (a) was redesigned to abort the current run and ask the user to re-run with the new prompt as a fresh single-pipeline run. No orchestrator restart mechanism needed.

**Preserve as audit trail because:** if a future scenario genuinely needs restart-from-gate semantics (e.g., a writer agent discovers a Part 4.1 lineage gap and needs to revise `parent_or_issuer` mid-run), this TD documents the prior consideration and its negative resolution. Reopen with explicit new justification; do not silently revive.

**History:** original decision (2026-05-13) closed within the same session by a user mid-flight correction.

---

## B.0 #16 MEMORY.md staging — pending lessons

Lessons surfaced during B.0 sub-phase work that should land in `MEMORY.md` when deliverable #16 (MEMORY.md rewrite for the 7-gate set) is executed. This is a recurring slot — append new lessons as they emerge.

### Lesson: "human readability" is not a default assumption

When designing spec files in an LLM-agent workflow, ask "who directly reads this file, when?" before optimizing for human readability. Many agent-mediated workflows have users interact only via agent translation — direct file reads are rare. Optimizing for "human readability inline with data" in those cases may add complexity (e.g., needing a parser-based write tool for markdown-with-YAML) rather than reduce it.

**Origin:** B.0 #2 originally designed `references/subject_relationships.md` as a markdown+YAML hybrid. User challenged the "human readability" assumption mid-flight (B.0 mid-flight session, 2026-05-13); correct architecture was data (`.yaml`) + design (`.md`) split. TD-013 reduced from 9-step parser to 3-line pyyaml wrapper.

**Applies to:** future spec file design. Don't default to markdown+YAML hybrid without first justifying why a human directly reads the file. If the answer is "they don't, the agent translates", split data from design.

### Lesson: mid-flight course corrections are first-class moves

When a foundational assumption is challenged mid-deliverable, pause the deliverable, steel-man the challenge, sanity-check the alternative architecture **before** editing files. The cost of a 10-step migration before deeper work depends on the wrong architecture is far smaller than the cost of unwinding the wrong architecture after it has propagated to 5+ files. Mid-flight corrections are not "thrash" — they are the cheapest point at which to catch a wrong design.

**Origin:** B.0 #2 markdown+YAML → split into `.yaml` + `_design.md`, mid-flight during B.0 deliverable sequencing, 2026-05-13. The pattern executed: user challenged the assumption in one sentence; agent steel-manned the challenge instead of defending the design; we paused and sanity-checked the split before any file changes; 10-step migration executed atomically; lesson staged for permanent capture in `MEMORY.md`. This is the Anamnesis Pattern working as designed — catch design errors early, write the lesson, don't pay the cost twice.

**Applies to:** any deliverable where a foundational assumption surfaces under challenge. The right move is to pause, not to defend. Pausing is cheaper than unwinding.

**Additional origin (2026-05-13, same day as #2 split):** B.0 mid-flight restart to 4-gate design. Discovered 7-gate framework was inherited from Phase A equity-era without challenging whether it served crypto research workflow. Restart cost: 7 agent files removed (~1600 lines of in-progress design work), ~5.5 session redo. Restart vs unwinding cost ratio: ~1:3 (mid-flight cheaper than post-completion correction).

The pattern reinforced: when foundational assumption is challenged, steel-man the challenge, restart cleanly, do not patch around it.

### Lesson candidate: "different prompt = different run"

When a P0 gate's processing implies that the user's intent warrants a different prompt (e.g., narrowing a sector prompt to a single-subject prompt), the right architectural move is **abort + ask the user to re-run**, NOT internal restart-from-gate with prompt substitution. Two prompts means two runs; the audit trail of each run is cleaner if it corresponds to exactly one prompt. Internal restart mechanisms that splice two prompts into one run trade audit clarity for marginal UX savings (one extra command typed by the user vs. mangled audit history).

**Origin:** B.0 #6 (`agents/scope_gate.md`) initially designed path (a) sector narrow with internal restart-from-gate; user challenged the necessity 2026-05-13; correction made path (a) abort + user re-run; TD-015 (orchestrator restart capability) closed-as-unnecessary.

**Applies to:** future gate design when "user changed their mind / clarified intent" could be interpreted as "same run, patch state" vs. "different intent, new run". Default to "different intent = new run" unless there is explicit justification for in-run patching.

### Lesson candidate: over-engineering through inherited framework

When forking a harness for a new domain, the inherited framework's shape (gate count, decision points, abstractions) must be challenged against the new domain's actual workflow — NOT silently adopted as default. Inherited frameworks carry assumptions about user behavior that may not transfer. The cost of detecting framework mismatch early (mid-design) is far smaller than detecting it late (mid-implementation).

**Origin:** Phase A inherited 7-gate framework from equity research era. Phase B silently extended it without asking "what does the crypto research workflow actually need?" Mid-flight at B.0 #9 (after 9 ship deliverables), user described a 4-step user-visible flow that exposed 3 gates as over-engineering. Restart cost was 5.5 session; unwinding after B.0 completion would have been 12+ session.

**Applies to:** any fork or domain extension. Before adopting inherited framework, walk through the new domain's actual user workflow end-to-end and verify each framework element earns its place. Default to fewer abstractions, not more.

**Detection signal:** if you can't immediately answer "what does GATE_X do for THIS user's workflow", that gate may be over-engineering. The answer should be specific to the new domain, not generic.
