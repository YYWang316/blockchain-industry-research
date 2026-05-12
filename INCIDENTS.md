---
schema_version: 1
description: Append-only log of past failure modes and the contract that prevents them. Frozen into meta/system_prompt.frozen.txt at session start, alongside MEMORY.md. Read PRE-RUN to avoid repeating; read POST-RUN (P_INCIDENT_POSTCHECK) before delivery as a final self-check.
---

# Stack Anamnesis — INCIDENTS

This file is the project's institutional memory of failure. Each entry is a real incident that happened, the root cause, and the *load-bearing* rule that keeps it from happening again. Treat every entry as a hard constraint, not advice. If a new run hits a situation that smells like one of these, **stop and re-read the relevant entry before proceeding**.

**Format contract.** Append only. Never delete an incident — supersede it with a new entry that links back. Keep `id` monotonically increasing (`I-001`, `I-002`, …). Keep entries short: the *what / why / rule / detection* fields are load-bearing; everything else is optional context.

**Lifecycle fields (optional).** Most entries are `active` by default and have no explicit status line. When an entry's rule is replaced or invalidated by a newer entry (e.g. the underlying file was refactored away, or a stricter rule subsumes it), mark the old one with two extra bullets:

- `- **Status:** superseded`
- `- **Superseded by:** I-NNN`

The new entry should reciprocate with `- **Supersedes:** I-NNN`. `P_INCIDENT_POSTCHECK` skips superseded entries (records `status: skipped` with the supersedes link); their `Detection` clauses are no longer enforced. **Never delete a superseded entry** — the historical record is the audit trail. `tools/io/lint_incidents.py` verifies that cross-references resolve and that `Detection` clauses still point to files that exist on disk.

---

<!--
No incidents logged yet for this repo. The first failure mode caught by /log-incident
will be inserted here as I-001. For reference examples of what entries look like in a
mature domain (Porter formatting, locked HTML template bypass, financial-metrics table
contents, SEC EDGAR User-Agent PII, P0 gate bypass via auto-mode default), see
references/equity_incidents_archive.md — archived, not enforced.
-->

---

## How this file is used

1. **Pre-run** (`P_INCIDENT_PRECHECK`, fires before `P0_intent`): the orchestrator reads this file end-to-end. For each incident, it ensures the corresponding rule is wired into the current plan. If a rule is unclear or the incident is novel-looking for the current target, the orchestrator notes it in `meta/run.jsonl` as `incident_precheck.acknowledged`.
2. **Post-run** (`P_INCIDENT_POSTCHECK`, fires after `P12_final_audit` and before `P_DB_INDEX`): the orchestrator re-reads this file and confirms each incident's detection signal is green for this run. Output: `validation/incident_postcheck.json` with one entry per incident (`status: pass | flagged`, plus evidence path).
3. **On new failure**: the user runs `/log-incident <one-line description>`. Claude pulls the latest `meta/run.jsonl`, the user's description, and any phase outputs; drafts a candidate entry; the user confirms; the entry is appended here as `I-NNN`.
