---
phase: 03-pre-loop-validation-gate
reviewer: gsd-code-reviewer (Claude Opus 4.6 1M)
date: 2026-04-11
depth: standard
status: issues_found
findings_count:
  blocker: 0
  high: 0
  medium: 1
  low: 2
  info: 4
  total: 7
files_reviewed_list:
  - src/models.py
  - src/pre_loop_test.py
  - tests/test_pre_loop_gate.py
---

## Summary

Phase 3 implements the pre-loop validation gate cleanly and faithfully against CONTEXT.md D-01..D-11 and pitfall mitigations P1/P3/P10. The `PreLoopTestResult.model_validator` correctly separates the sentinel path (D-06) from the happy-path arithmetic, the probe-then-final construction pattern keeps rationale assembly out of the validator per resolution #1, the path shim is tightly guarded for script-mode only, and the `__main__`-only banner keeps library consumers free of stdout spam (D-10). The test is a thin integration wrapper and asserts in strictness order so failure messages are maximally informative.

Review found **one medium finding** around the hard-coded-threshold invariant (P10): the `threshold: float = 2.0` field is a default, not a frozen constraint, so a caller could technically construct `PreLoopTestResult(..., threshold=0.5)` and the validator would happily compute `passed` against the weakened bar. The production path never does this, but the whole point of P10 is that weakening the bar must be structurally impossible, not just unused. Two low findings cover (a) the probe/final dual-construction paying a small re-validation cost for list re-binding and (b) a latent duplicate-`item_id` hole in the variance check inherited from `JudgeResult` not enforcing uniqueness. Four info items cover docstring gaps against the T-03-01 mitigation plan, rationale-vs-banner asymmetry on run-2 sentinel, a minor log-level decision on the sentinel branch, and the absence of a test-cleanup fixture for the results artifact.

No blockers. All eight decisions and three pitfalls have a concrete implementation site. The gate is ready to run live.

## Findings

### M-01 — `threshold` field is a default, not an enforced invariant (P10 structural weakness)

**Severity:** medium
**File:** `src/models.py:98`
**Decision / pitfall:** P10 mitigation, D-01 field spec

**Description:** The docstring at `src/models.py:91-93` is explicit that "threshold is hard-coded at 2.0. Do NOT make this an env var". The implementation backs this up in the runtime path — `run_pre_loop_test` never passes `threshold=` to the constructor, and `config.py` has no threshold key. However the field itself is:

```python
threshold: float = 2.0  # P10 mitigation — hard-coded
```

This is a default value, not a frozen constraint. A caller (today or in a future Phase 4/5 refactor) can write `PreLoopTestResult(..., threshold=0.5, ...)` and the `_compute_gate` validator will use 0.5 in `passed = (gap >= self.threshold) and (judgment_gap > 0)`. The P10 mitigation plan is that weakening the bar at runtime must be structurally impossible because the gate's diagnostic value depends on its unforgeability. "Hard-coded on the model" should mean "cannot be overridden on the model", not just "happens to have a default of 2.0".

**Fix hint:** Use Pydantic v2's `Field(..., frozen=True)` or reject non-2.0 values in the validator. The simplest fix:

```python
from pydantic import BaseModel, Field, model_validator

# ...

class PreLoopTestResult(BaseModel):
    # ...
    threshold: float = Field(default=2.0, frozen=True)  # P10 — cannot be overridden
```

With `frozen=True`, Pydantic raises a `ValidationError` at construction if a caller passes `threshold=` at all, even `threshold=2.0`. If that's too strict, use a validator instead:

```python
@model_validator(mode="after")
def _compute_gate(self) -> "PreLoopTestResult":
    if self.threshold != 2.0:
        raise ValueError(
            f"PreLoopTestResult.threshold is load-bearing (P10) and must be 2.0; "
            f"got {self.threshold}. Weakening the bar defeats the gate."
        )
    # ... rest unchanged
```

Either way, the P10 docstring becomes enforceable, not just aspirational.

---

### L-01 — Duplicate `item_id` silently dedupes in variance check

**Severity:** low
**File:** `src/models.py:148-149`
**Decision / pitfall:** D-07 variance aggregation

**Description:** The variance check builds two dicts keyed on `item_id`:

```python
r1_by_id = {s.item_id: s.score for s in runs[0].scores}
r2_by_id = {s.item_id: s.score for s in runs[1].scores}
```

If the judge ever emits two scores for the same `item_id` in a single run (a retry-less Phase 2 `JudgeResult` does not enforce uniqueness — `scores: list[RubricScore]` accepts duplicates), the dict comprehension keeps the *last* entry and silently drops the rest. A genuine 0↔2 flip hidden inside a duplicated id would not trigger `variance_warning`, and worse, the upstream `IterationResult.total_score` (computed via `sum(s.score for s in scores ...)`) *would* see the duplicate. Run 1 total_score and `r1_by_id` would be computed on different views of the same list.

Note: this is primarily a Phase 2 schema gap (`JudgeResult.scores` should enforce unique ids), not strictly a Phase 3 bug. Logging it here because Phase 3 is the first consumer that does item-level cross-run reasoning. The runtime risk is low because gemma4:26b is unlikely to produce duplicate ids on a well-specified rubric, but the failure mode is silent, which is exactly what P3 is trying to surface.

**Fix hint:** Either (a) add a duplicate-id check at the top of `_compute_gate`'s happy path:

```python
for runs_label, runs in (("output_a", self.output_a_runs), ("output_b", self.output_b_runs)):
    for i, run in enumerate(runs):
        if run.scores:
            ids = [s.item_id for s in run.scores]
            if len(ids) != len(set(ids)):
                raise ValueError(
                    f"{runs_label} run {i+1} has duplicate item_ids: {ids}"
                )
```

or (b) push the invariant up to `JudgeResult` in Phase 2 with a `@field_validator`. Option (b) is cleaner and fixes all current and future consumers, but it is Phase-2 scope — defer if out of Phase 3 budget, but note in the Phase 3 summary so Phase 5 doesn't trip over it.

---

### L-02 — Probe-then-final dual construction re-runs the validator twice

**Severity:** low
**File:** `src/pre_loop_test.py:179-206`
**Decision / pitfall:** Resolution #1 (validator owns arithmetic only)

**Description:** The probe pattern constructs `PreLoopTestResult` twice — once with `rationale="<probe>"` to pull out the computed `gap`/`judgment_gap`/`decision`, and once with the real rationale. This is intentional per resolution #1 (keep rationale assembly out of the validator), and the cost is negligible (4 `int`/`float` computations plus a variance loop over 16 items). Pydantic v2's default `revalidate_instances='never'` means the nested `IterationResult` instances are not re-copied, so the cost is truly O(items), not O(nested model graph).

However, this pattern is non-obvious to a future reader. A simpler alternative would be to expose a free function `compute_gate_fields(a_runs, b_runs, threshold) -> tuple[float, int, bool, str, bool]` that both the validator and `run_pre_loop_test` call, eliminating the double construction. This would also make the computation unit-testable without constructing a full model.

**Fix hint:** Optional refactor — not required for correctness. If the double-construction is kept, consider adding one inline comment near line 180 explaining *why* we construct twice (currently it's documented in the prose comment lines 176-179, which is actually fine — upgrading from low to info-ish). Leaving at low in case you prefer the free-function approach.

---

### I-01 — Module docstring does not explicitly state that `results/pre_loop_test.json` contains fixture + NDA text

**Severity:** info
**File:** `src/pre_loop_test.py:1-22`
**Decision / pitfall:** T-03-01 mitigation (PLAN.md threat model)

**Description:** The T-03-01 mitigation in `03-01-PLAN.md:891` states: *"Document in `src/pre_loop_test.py` module docstring that the artifact contains fixture text."* The current docstring lists the inputs and outputs:

```
Runs data/output_a.md and data/output_b.md through run_judge twice each
and emits a go/no-go decision to:
  - results/pre_loop_test.json   (structured — PreLoopTestResult dump)
```

A careful reader can infer that `PreLoopTestResult` embeds `IterationResult.agent_output`, which (per D-04) is the full fixture file contents, which means the JSON carries the full NDA text verbatim. But the docstring does not say that out loud. A casual reader sharing the artifact — say, pasting it into a bug report — may not realise they are also pasting `data/nda.md`.

**Fix hint:** Add one sentence at the top of the module docstring, e.g.:

```
SECURITY NOTE: results/pre_loop_test.json contains the full text of
data/nda.md and data/output_{a,b}.md (embedded via D-04 self-contained
IterationResult.agent_output). results/ is gitignored; do not paste the
artifact into public channels. Threat T-03-01 accepted because the NDA
is synthetic.
```

---

### I-02 — `_build_rationale` sentinel branch checks only run 1; run-2 sentinel is silent in rationale but visible in banner

**Severity:** info
**File:** `src/pre_loop_test.py:94-109`
**Decision / pitfall:** D-06 vs D-07

**Description:** The sentinel branch in `_build_rationale` only flags outputs whose run 1 failed:

```python
if not a1.scores:
    sentinel_failures.append("data/output_a.md run 1")
if not b1.scores:
    sentinel_failures.append("data/output_b.md run 1")
```

If run 1 succeeded but run 2 sentinel'd, the rationale takes the go/no-go branch (based on run-1 arithmetic) and never mentions the run-2 failure. The banner (`_print_banner` lines 240-243) *does* list all four run states, so the human sees it on the console. But the JSON rationale — which is what a Phase 5 consumer or post-hoc analyst will read — is silent about the run-2 sentinel, even though `variance_warning=True` (set by `_compute_gate`'s variance loop at line 146 when run 2 scores are empty).

This is consistent with D-06's *decision* rules (sentinel only forces no-go on run 1 because run 1 is authoritative per D-07) but inconsistent with the spirit of D-05 ("The decision is observable in **both** the JSON file AND a stdout console banner"). A reader checking only the JSON would see `variance_warning=True` with a generic gap-based rationale and have to cross-reference the 4 `IterationResult` entries to figure out why.

**Fix hint:** After the `decision == "go"` / else rationale is built, append a sentence when run 2 sentinel'd:

```python
tail = ""
if not a_runs[1].scores:
    tail += " Note: data/output_a.md run 2 sentinel'd — variance_warning is set."
if not b_runs[1].scores:
    tail += " Note: data/output_b.md run 2 sentinel'd — variance_warning is set."
return base + tail
```

Low-priority — the banner already covers the interactive case, and Phase 5 won't use the banner.

---

### I-03 — Sentinel-branch log level is ERROR per-call, WARNING in aggregate — consider promoting aggregate log to ERROR on sentinel

**Severity:** info
**File:** `src/pre_loop_test.py:209-217`
**Decision / pitfall:** Logging convention from CONTEXT.md "Claude's Discretion"

**Description:** CONTEXT.md says *"INFO at start+end, WARNING on variance, ERROR on judge sentinel."* The per-call sentinel is logged at ERROR at line 72 (good). The aggregate end-of-run log at line 209-217 uses:

```python
log_level = logging.INFO if result.decision == "go" else logging.WARNING
```

So a sentinel-forced no-go is logged at WARNING in the aggregate summary, even though the convention says "ERROR on judge sentinel". The individual sentinel failure is already logged at ERROR, so the total ERROR count is accurate; the aggregate summary is just softer than the convention implies.

**Fix hint:** Promote the aggregate log level to ERROR when the sentinel path fired:

```python
if not result.output_a_runs[0].scores or not result.output_b_runs[0].scores:
    log_level = logging.ERROR
elif result.decision == "go":
    log_level = logging.INFO
else:
    log_level = logging.WARNING
```

Purely stylistic — the per-call ERROR is already captured.

---

### I-04 — Integration test does not clean up `results/pre_loop_test.json` and does not assert on fresh timestamps

**Severity:** info
**File:** `tests/test_pre_loop_gate.py:38-70`
**Decision / pitfall:** D-09 (intentional overwrite) + T-03-03 (freshness)

**Description:** Per D-09 the artifact is overwritten every run, which is intentional. But the test:

1. Does not assert that the on-disk `timestamp` matches (or is at least as recent as) the returned `result.timestamp`. A previously-cached artifact would still satisfy `_RESULTS_FILE.exists()` even if `run_pre_loop_test()` crashed before writing (hypothetically — it doesn't today because the function doesn't have early exits past `read_text`, but defensively this assertion is free).
2. Does not teardown — if Phase 5 ever runs the integration suite in parallel (pytest-xdist), two workers racing on the same `results/pre_loop_test.json` would be a test-isolation bug. Not a concern today; pytest is invoked serially.

**Fix hint:** Add one extra assertion after the `_RESULTS_FILE.exists()` check:

```python
import json
on_disk = json.loads(_RESULTS_FILE.read_text())
assert on_disk["timestamp"] == result.timestamp, (
    "results/pre_loop_test.json is stale — run_pre_loop_test() did not "
    "write the artifact this run."
)
```

No teardown needed — D-09 intentional-overwrite stays. Parallel-test concern is deferred to the day pytest-xdist is introduced.

---

## Decision Compliance Matrix

| Decision | Requirement | Implementation site | Verdict |
|---|---|---|---|
| D-01 | `PreLoopTestResult` with 13 fields | `src/models.py:73-168` | COMPLIANT |
| D-02 | `ExperimentRun.pre_loop_test: PreLoopTestResult \| None` retype | `src/models.py:62` + `model_rebuild()` at 171 | COMPLIANT |
| D-03 | `system_prompt` sentinel per fixture | `src/pre_loop_test.py:50-51, 79` | COMPLIANT |
| D-04 | `agent_output` is full fixture file contents | `src/pre_loop_test.py:161-162, 168-173` | COMPLIANT |
| D-05 | Decision in JSON + stdout banner, not exit code | `src/pre_loop_test.py:208` (JSON) + 298-299 (banner) | COMPLIANT |
| D-06 | Judge sentinel forces no-go, no raise | `src/models.py:124-131` + `src/pre_loop_test.py:71-76` | COMPLIANT |
| D-07 | 2 runs per output, run 1 authoritative, run 2 variance | `src/models.py:114-119, 134-161` + `src/pre_loop_test.py:167-174` | COMPLIANT |
| D-08 | metadata (model/temp/num_ctx/timestamp) captured before first judge call | `src/pre_loop_test.py:149-158` | COMPLIANT |
| D-09 | library function reads 5 inputs, writes JSON, mkdir results/ | `src/pre_loop_test.py:134-218` | COMPLIANT |
| D-10 | `__main__` block + `_print_banner` module-private | `src/pre_loop_test.py:221-299` | COMPLIANT |
| D-11 | `pytest.mark.integration` marker, wraps `run_pre_loop_test()` | `tests/test_pre_loop_gate.py:32, 38-70` | COMPLIANT |

All 11 decisions have a concrete implementation site. No decision drift.

## Pitfall Verification Matrix

| Pitfall | Risk | Mitigation site | Verdict |
|---|---|---|---|
| P1 (judge self-reference collapse) | The loop optimises a metric the judge has already internalised, and convergence is an artefact not a signal | The gate's existence is the falsification mechanism. `src/pre_loop_test.py:134` + docstring lines 20-22. The gate runs *before* Phase 4/5 exist, so a small-gap no-go kills the project at the cheapest possible moment. | MITIGATED — the phase's existence demonstrably falsifies P1; rationale Case 2 in `_build_rationale` lines 121-131 explicitly names "loop is not worth building" as the outcome of a small gap |
| P3 (Ollama temperature=0 not deterministic across runs) | Per-run score drift makes any single-run signal unreliable | Dual-run design at `src/pre_loop_test.py:167-174`, variance check at `src/models.py:142-161`, metadata snapshot at `src/pre_loop_test.py:149-158` | MITIGATED — variance loop catches 0↔2 flips and missing items; metadata enables re-run reproduction. See L-01 for a latent duplicate-id hole that slightly weakens the variance check. |
| P10 (pre-loop test not diagnostic if gap is small) | A generous threshold would let weak discrimination pass as validation | `threshold: float = 2.0` at `src/models.py:98`; docstring warning at 91-93; `run_pre_loop_test` never overrides | **PARTIALLY MITIGATED** — the runtime path respects P10, but the field is a default not a frozen constraint (see M-01). A caller or future refactor could pass `threshold=` and the validator would accept it. Fix by adding `Field(..., frozen=True)` or a validator rejection. |

## REVIEW ISSUES FOUND

**Top-line count by severity:**
- blocker: 0
- high: 0
- medium: 1 (M-01: P10 threshold is overridable)
- low: 2 (L-01: duplicate item_id dedupes; L-02: double construction cost)
- info: 4 (I-01..I-04: docstring T-03-01, rationale asymmetry, log level, test freshness assert)

**Total:** 7 findings. No blockers; Phase 3 is safe to proceed to live integration run. M-01 should be fixed before Phase 4 starts consuming `PreLoopTestResult` so the P10 contract is enforceable top-to-bottom.
