# PROJECT_SNAPSHOT

> Updated: 2026-03-21 — update this before every session.

## Identity
- **Project:** Eggent AI / Second Brain Retrieval Hardening
- **Goal:** Isolate retrieval validation on `00 System`, eliminate side effects during tests, and harden Eggent to distinguish read path vs write path before broader rollout.
- **Stack:** TypeScript, Python, Docker, webhook-based write flow, local `.venv`
- **Status:** eval-isolation complete, validation passed

## Architecture
- **Flow:** User prompt → runtime tool routing → Python skill execution → retrieval or write path → structured result
- **Key modules:** `src/lib/tools/code-execution.ts`, `src/eggent_skills/search_vault.py`, `src/eggent_skills/write_vault.py`, `src/eggent_skills/migrate_corpus.py`
- **Entry point:** `src/lib/tools/code-execution.ts`

## Environment
- **Local repo:** `/Users/admin/Dev/eggent-ai`
- **Vault scope under validation:** `/Users/admin/Documents/z-mind_25/00 System`
- **Container app:** `eggent-app-1`
- **Python runtime in container:** `/opt/eggent-python/bin/python3`
- **Protected retrieval mount:** `/app/vault`
- **Runtime skills path:** `/app/src/eggent_skills/`

## Current State
- **What works:** eval-isolation contour fully validated; read/write path separation enforced at routing, script, and env levels; `00 System` is the only active search scope in eval mode
- **Main blocker:** none blocking for `00 System` scope; broader rollout to other vault sections not yet started
- **Critical issue:** resolved — analytical prompts can no longer trigger `write_vault.py` side effects in eval mode

## Completed in this session

### Patch 1 — `src/prompts/system.md`
Added rule 6 to `## Important Rules`: explicit prohibition on calling `write_vault.py` for analytical, retrieval, summarization, classification, and table-answer tasks. Agent must ask user if intent is ambiguous.

### Patch 2 — `src/eggent_skills/write_vault.py`
- Moved eval-guard to immediately after `parse_args()` — before metadata parsing, tag normalization, and markdown assembly
- `reason` field now distinguishes ENV-triggered vs flag-triggered eval
- Old unreachable guard removed
- Improved `except` blocks for webhook: replaced broad `except Exception` with specific `requests.exceptions` handlers (Timeout, ConnectionError, HTTPError, RequestException)

### Patch 3 — `src/eggent_skills/search_vault.py`
- In eval mode, `subdir` is forced to `"00 System"` regardless of caller argument
- `_build_entity_registry()` restricted to `search_path` in eval mode (was `base_path` = full vault)
- OR-fallback disabled in eval mode: strict AND-only search, `no_results` on miss

### Validation results
All 10 steps passed locally without webhook side effects:
- Syntax clean on both Python files after apply
- `write_vault.py` exits at eval-guard before any data processing (`exit: 0`, no N8N env check)
- Usual write mode unchanged: reaches webhook block and exits with expected `N8N_WEBHOOK_URL missing` error
- `search_vault.py` with `--subdir "Trading"` in eval returns `effective_subdir: 00 System`
- Search without `--subdir` in eval no longer returns `eval_mode_requires_restricted_scope`
- Non-existent query returns `status: no_results`, `result_count: 0` — OR-fallback confirmed disabled
- `EGGENT_EVAL_MODE` propagates correctly through bash (terminal runtime path)

## Session Focus
- **Objective:** apply and validate eval-isolation hardening across four files
- **Status:** complete

### Definition of Done
- [x] Snapshot reflects current repo state accurately
- [x] All four patches applied and validated
- [x] Eval-isolation contour is stable and proven locally
- [ ] Rollout beyond `00 System` — next phase, not yet started
