# Validation: eval-isolation

> Status: completed and validated
> Date: 2026-03-21
> Scope: `00 System` only

---

## Goal

Enforce strict isolation between the read path and write path during retrieval evaluation.
Ensure that analytical, retrieval, and summarization prompts cannot trigger real writes to
the Obsidian vault via `write_vault.py` when `EGGENT_EVAL_MODE` is active.

---

## Applied Patches

### 1. `src/prompts/system.md`

Added rule 6 to `## Important Rules`:

- `write_vault.py` must only be called when the user explicitly requests saving a note
- Forbidden for: analytical, retrieval, summarization, classification, table-answer tasks
- If intent is ambiguous — ask the user, do not call `write_vault.py`

### 2. `src/eggent_skills/write_vault.py`

- Moved eval-guard to immediately after `parse_args()` — before metadata parsing,
  tag normalization, and markdown assembly
- In eval mode: returns structured JSON (`eval_success`, `skipped_write`) and exits
- `reason` field distinguishes `EGGENT_EVAL_MODE is enabled` vs `--eval-mode flag is set`
- Removed old unreachable guard (was at line 177, after full data processing)
- Replaced broad `except Exception` with specific `requests.exceptions` handlers:
  `Timeout`, `ConnectionError`, `HTTPError`, `RequestException`

### 3. `src/eggent_skills/search_vault.py`

- In eval mode, `subdir` is forced to `"00 System"` regardless of caller argument
- `_build_entity_registry()` restricted to `search_path` in eval mode
  (was using `base_path` = full vault root)
- OR-fallback disabled in eval mode: strict AND-only search; returns `no_results` on miss

### 4. `src/lib/tools/code-execution.ts`

- Added explicit `EGGENT_EVAL_MODE: process.env.EGGENT_EVAL_MODE || "false"`
  to `buildTerminalEnv()` — mirrors existing behaviour in `buildPythonEnv()`
- Ensures the variable is always present in child process env via both python
  and terminal runtime paths

---

## Validation Steps Passed

All 10 steps executed locally on 2026-03-21. No webhook calls. No writes to vault.

- Python syntax clean on both `write_vault.py` and `search_vault.py` after apply
- `write_vault.py --eval-mode`: returns `eval_success`, `skipped_write`; `tags_raw` not parsed
- `write_vault.py` with `EGGENT_EVAL_MODE=true`: returns `eval_success` via ENV path
- `write_vault.py` in eval: exits with `exit: 0`; no `N8N_WEBHOOK_URL` error in output
- `write_vault.py` in normal mode: reaches webhook block, exits with expected ENV error
- `search_vault.py` with `--subdir "Trading"` in eval: `effective_subdir` = `00 System`
- `search_vault.py` without `--subdir` in eval: no `eval_mode_requires_restricted_scope` error
- Non-existent query in eval: `status: no_results`, `result_count: 0` (OR-fallback not triggered)
- Terminal runtime path: `EGGENT_EVAL_MODE=true` via `bash -c` → `eval_success` confirmed
- `system.md`: rule 6 present at correct position; numbering 1–6 unbroken

---

## Validated Baseline

The following is now the stable expected behaviour:

- Analytical and retrieval prompts cannot trigger `write_vault.py` side effects in eval mode
- `search_vault.py` in eval mode is strictly scoped to `00 System`
- OR-fallback is disabled in eval mode — search results are deterministic
- `EGGENT_EVAL_MODE=true` reaches Python scripts via both python and terminal runtime paths
- `write_vault.py` exits before any data processing when eval mode is active
- Agent routing rules in `system.md` explicitly prohibit `write_vault.py` for read-only tasks

---

## Remaining Constraints

- Validation scope is `00 System` only — no other vault sections tested
- Rollout beyond `00 System` has not started
- Next phase requires explicit approval before any work begins
- `buildTerminalEnv()` patch in `code-execution.ts` is optional hardening —
  current behaviour is safe if `EGGENT_EVAL_MODE` is set in the app's `.env`

---

## Next Phase (not started)

- Validate retrieval quality beyond `00 System`
- Assess rollout readiness for other vault sections
- Requires separate scoping and explicit approval
