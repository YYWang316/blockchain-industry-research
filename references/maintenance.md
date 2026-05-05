---
schema_version: 1
description: Maintainer notes for the locked HTML template, palette consistency, DB schema migrations, and submodule bumps. Read this only when changing the harness itself, not on a normal run.
---

# Maintenance

These notes apply when **modifying the harness**, not when running it. A normal production run never needs to touch any of this.

## Locked HTML report template

`skills_repo/er/agents/report_writer_{cn,en}.md` contains a SHA256-pinned HTML skeleton. Phase P5 extracts the skeleton via `tools/research/extract_template.py` and substitutes `{{PLACEHOLDER}}` markers only — **never** edit structure.

If the upstream ER skill changes the template:

1. The ER maintainer updates the SHA256 in `skills_repo/er/tests/test_extract_report_template.py`.
2. Anamnesis Research picks up the new SHA at the next `git submodule update --remote`.
3. Bump the submodule SHA deliberately in a single commit; `meta/submodule_shas.json` per run records what was used.

## Palette consistency

All six cards in one run **must** use the same `--palette`. The palette is **not** stored in `card_slots.json`; it lives only as a CLI arg to `tools/photo/render_cards.py` and `tools/photo/validate_cards.py`. Mismatched single-card re-renders cause silent header-colour drift across the pack.

If you add a new palette:
1. Add the palette name to `P0_palette` `values` in `workflow_meta.json`.
2. Add the palette tokens to `skills_repo/ep/references/` (upstream).
3. Add a sticky option to `USER.md.template`.

## DB schema changes

- Each schema change is a new file `db/schema/00X_*.sql`.
- Bump `PRAGMA user_version` inside the migration.
- **Never destroy** existing columns or tables — additive only. Rename via `ALTER TABLE ... ADD COLUMN` + dual-write window.
- Run `pytest tests/test_db_migrations.py` to verify the migration applies cleanly to a cold DB and an existing one.
- `tests/test_db_pii.py` is a regression: any TEXT column matching the email regex after a fixture run = test fails = release blocked.

## Card slot schema

When `skills_repo/ep/references/card-slots.schema.json` changes (upstream EP), re-check `tools/audit/reconcile_numbers.py`'s path mappings — its slot-to-source-JSON mapping is hand-maintained and silently wrong if a key is renamed.

## Tolerances (P12 layer 1, from MEMORY.md)

If you change tolerance numbers, update **both**:
- `MEMORY.md` (the human-readable contract)
- `tools/audit/reconcile_numbers.py` (the enforcer)

Current tolerances:

| Type | Tolerance |
|---|---|
| margins / ratios / percentage points | ±0.5pp |
| currency amounts | ±0.5% relative |
| growth rates | ±0.5pp |
| prices, share counts, anything tagged `"exact": true` | 0 |

## Submodule bumps

Both `skills_repo/er` and `skills_repo/ep` are pinned by SHA in `.gitmodules`. To bump:

```bash
cd skills_repo/er && git fetch && git checkout <sha> && cd ../..
git add skills_repo/er
git commit -m "bump er submodule to <sha>"
```

Run the full `pytest -q` suite before commit. Submodule bumps are deliberate — never auto-update.

## Hook cwd-invariance

Hook commands in `.claude/settings.json` and `.codex/hooks.json` must resolve their script path **independent of the user's cwd**, including when cwd is inside a submodule (`skills_repo/er`, `skills_repo/ep`). A hook that uses a bare relative path (`python3 .claude/hooks/inject_incidents.py`) silently breaks the moment the user changes directory into a submodule — the relative path resolves against the submodule root, the file isn't there, and `UserPromptSubmit` is blocked. Treat this as an Auditability failure, not a quality-of-life bug: an incident gate that doesn't fire when cwd drifts is the same as no gate.

Host-specific patterns:

- **Claude Code** — uses the injected `$CLAUDE_PROJECT_DIR`:
  ```json
  "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/inject_incidents.py\""
  ```
- **Codex** — does not inject a project-root env var. Resolve via git, with submodule fallback:
  ```json
  "command": "sh -c 'R=$(git rev-parse --show-superproject-working-tree 2>/dev/null); [ -z \"$R\" ] && R=$(git rev-parse --show-toplevel); exec python3 \"$R/.codex/hooks/inject_incidents.py\"'"
  ```
  `--show-superproject-working-tree` returns the parent repo's worktree when cwd is inside a submodule (empty otherwise); the fallback to `--show-toplevel` covers the non-submodule case. **Do not** use `--show-toplevel` alone — inside a submodule it returns the submodule root, which is the bug we're trying to prevent.

Hook Python scripts themselves should anchor with `Path(__file__).resolve().parent.parent.parent` so once invoked correctly they don't depend on cwd either. The fragile layer is always the shell command in the config file.
