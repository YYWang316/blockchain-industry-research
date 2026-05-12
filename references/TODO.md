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
