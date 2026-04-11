---
phase: 03-pre-loop-validation-gate
reviewer: gsd-code-fixer (Claude)
date: 2026-04-11
status: all_fixed
findings_in_scope: 1
fixed: 1
skipped: 0
iteration: 1
---

# Phase 3: Code Review Fix Report

**Fixed at:** 2026-04-11
**Source review:** `.planning/phases/03-pre-loop-validation-gate/03-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope (blocker/high/medium): 1
- Fixed: 1
- Skipped: 0

The single in-scope finding (M-01, medium) was fixed. The two `low`
findings (L-01, L-02) and four `info` findings (I-01..I-04) are out of
scope for `critical_warning` fix depth and were not touched.

## Fixed Issues

### M-01 — `PreLoopTestResult.threshold` is a Pydantic default, not frozen (P10 structural weakness)

**Files modified:** `src/models.py`
**Commit:** `e843456`
**Approach chosen:** Option C (`@field_validator`) — rejected per-field
`Field(frozen=True)` after empirical verification that Pydantic 2.12.5's
per-field `frozen=True` only blocks post-construction mutation, NOT
construction-time overrides. A direct test
(`M(x=0.5)` against `x: float = Field(default=2.0, frozen=True)`) showed
the override was silently accepted, which would leave the P10 invariant
unenforced. Option C is portable, explicit, and works for any Pydantic
v2.x version.

**Applied fix (diff summary):**

1. Imported `Field` and `field_validator` alongside `model_validator`:
   ```python
   from pydantic import BaseModel, Field, field_validator, model_validator
   ```

2. Replaced the bare default with a `Field(default=2.0, description=...)`
   that documents the P10 invariant and points the reader at the
   enforcing validator:
   ```python
   threshold: float = Field(
       default=2.0,
       description=(
           "P10 mitigation — load-bearing gate threshold, hard-coded at 2.0. "
           "Enforced by _reject_threshold_override below: any construction-time "
           "override raises ValidationError. Weakening the bar defeats the gate."
       ),
   )
   ```

3. Added a `@field_validator("threshold")` above `_compute_gate` that
   raises `ValueError` for any value other than 2.0, with a comment
   explaining WHY `Field(frozen=True)` was not used:
   ```python
   @field_validator("threshold")
   @classmethod
   def _reject_threshold_override(cls, v: float) -> float:
       # P10 mitigation: the 2.0-point bar is load-bearing and must be
       # structurally unforgeable. Pydantic's per-field `Field(frozen=True)`
       # only blocks post-construction mutation, not construction-time
       # overrides, so we reject non-2.0 values here. This makes the
       # docstring invariant ("hard-coded at 2.0") enforceable rather than
       # aspirational.
       if v != 2.0:
           raise ValueError(
               f"PreLoopTestResult.threshold is load-bearing (P10) and must "
               f"be 2.0; got {v}. Weakening the bar defeats the gate."
           )
       return v
   ```

**Verification output:**

- **Pydantic version probed:** 2.12.5
- **Per-field frozen probe (Option A rejected):**
  ```
  Construction with override ACCEPTED: x=0.5
  Default construction: x=2.0
  Mutation REJECTED: ValidationError ... Field is frozen
  ```
  Confirms `Field(frozen=True)` does not guard construction-time values —
  hence Option C.
- **Sanity check (guard fires):**
  ```
  OK: override rejected with ValidationError: 1 validation error for PreLoopTestResult
  threshold
    Value error, PreLoopTestResult.threshold is load-bearing (P10) and must be 2.0;
    got 0.5. Weakening the bar defeats the gate. [type=value_error, ...]
  ```
- **Test suite:** `uv run pytest -q -m "not integration"` → `21 passed,
  3 deselected in 0.22s`. No regressions. Existing `pre_loop_test.py`
  runtime path (which never passes `threshold=`) is unaffected: the
  default 2.0 flows through the field_validator unchanged, and the
  `_compute_gate` model_validator still reads `self.threshold` for the
  `passed` computation.
- **Formatting:** `uv run black --check src/ tests/` → `14 files would be
  left unchanged.` Clean.
- **Syntax:** `python -c "import ast; ast.parse(...)"` → OK.

**Semantic-correctness note:** This fix enforces a structural invariant
(reject non-2.0) rather than introducing new logic. Tier 1 + Tier 2
verification (re-read, syntax, sanity check, full test suite, format)
cover the change. Marked as `fixed` — no human follow-up needed.

## Skipped Issues

None. All in-scope findings were fixed.

Out-of-scope findings (low/info — deferred per fix_scope=`critical_warning`):
- L-01 — duplicate `item_id` silently dedupes in variance check (severity: low)
- L-02 — probe-then-final dual construction re-runs validator twice (severity: low)
- I-01 — T-03-01 docstring gap on fixture+NDA text in artifact (severity: info)
- I-02 — `_build_rationale` run-2 sentinel asymmetry vs banner (severity: info)
- I-03 — aggregate sentinel log level WARNING vs ERROR (severity: info)
- I-04 — test does not assert on-disk timestamp freshness (severity: info)

---

_Fixed: 2026-04-11_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
