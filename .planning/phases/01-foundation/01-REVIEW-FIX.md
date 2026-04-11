---
phase: 01-foundation
fixed_at: 2026-04-11T00:00:00Z
review_path: .planning/phases/01-foundation/01-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 1: Code Review Fix Report

**Fixed at:** 2026-04-11
**Source review:** `.planning/phases/01-foundation/01-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (critical_warning)
- Fixed: 3
- Skipped: 0

## Fixed Issues

### WR-01: `Config` reads env vars at class-definition time, not instance construction

**Files modified:** `src/config.py`
**Commit:** `ea126f8`
**Applied fix:** Replaced `os.getenv(...)`-based dataclass field defaults with plain literal defaults, and added a `Config.from_env()` classmethod that reads env vars at call time. The env reads are wrapped in `_float` / `_int` helpers that raise `ValueError` with a clear message (`f"Invalid {key}={raw!r}; expected float"`) instead of an anonymous traceback into the class body. Module-level `config = Config.from_env()` is preserved so existing import sites continue to work, while tests and Phase 2 harnesses can now construct fresh `Config()` or `Config.from_env()` instances after mutating env vars. Verified with `python3 -m ast.parse` and by re-reading the file.

---

### WR-02: `.gitignore` does not ignore `.env`, risking API key leakage

**Files modified:** `.gitignore`
**Commit:** `c4269c2`
**Applied fix:** Appended the review's suggested ignore blocks to the existing `.gitignore`, preserving the original five lines (`results/*`, `!results/.gitkeep`, `__pycache__/`, `*.pyc`, `.venv/`). Added sections for Environment (`.env`, `.env.*`, `!.env.example`), Python caches (`.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `*.egg-info/`), and OS (`.DS_Store`). Verified by re-reading the file; `.gitignore` has no syntax checker so Tier 3 fallback applied.

---

### WR-03: `IterationResult` denormalizes score totals without a validator

**Files modified:** `src/models.py`
**Commit:** `051f0ab`
**Applied fix:** Imported `model_validator` from `pydantic`, defaulted `total_score` / `extraction_score` / `judgment_score` to `0`, and added a `@model_validator(mode="after")` method `_check_totals` that computes the expected values via `compute_category_scores(self.scores)` and either (a) fills in the defaults when all three totals are still `0`, or (b) raises `ValueError` with the observed vs expected tuple when the caller supplied inconsistent values. Uses `object.__setattr__` for the default-fill branch per the review's suggestion. The forward reference to `compute_category_scores` (defined later in the module) resolves correctly because the validator runs at instance construction, after module body execution.

Verified with `python3 -m ast.parse` and with a runtime test via `uv run python` covering all three branches:
- defaults fill-in: `IterationResult(..., scores=[ext=2, jud=1])` produces `extraction_score=2, judgment_score=1, total_score=3`. PASS
- consistent values supplied: no error raised. PASS
- inconsistent values supplied: raises `ValueError` containing "inconsistent". PASS

**Note:** This fix includes a logic branch (default-fill vs enforcement) that was verified at runtime against representative inputs, so it is marked `fixed` rather than `fixed: requires human verification`. Downstream callers in Phase 2 should, however, confirm they are not relying on the old behaviour of passing `0` totals as explicit "no score" sentinels — the new validator will now auto-fill those to the computed values.

---

_Fixed: 2026-04-11_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
