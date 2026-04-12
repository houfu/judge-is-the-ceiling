---
phase: 05-main-loop
reviewed: 2026-04-12T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - src/loop.py
  - tests/test_loop.py
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-04-12
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

`src/loop.py` is a clean, well-structured orchestration module that correctly implements the agent->judge->optimiser loop with the D-01..D-12 design constraints documented in 05-CONTEXT.md. The code is readable and the flow maps directly to the design document. `tests/test_loop.py` has good coverage of the main paths (happy path, sentinel cases, metadata, deltas, no-go gate, vocab warning).

Three warnings are raised: one logic bug in the progress-line delta computation (uses iteration index rather than the last written result), one incomplete test body that contains dead code, and one missing edge-case assertion. Three info items cover minor quality issues.

---

## Warnings

### WR-01: Progress-line `prev_total` references stale index on sentinel iterations

**File:** `src/loop.py:186`

**Issue:** The progress delta is calculated as:

```python
prev_total = run.iterations[i - 1].total_score if i > 0 else 0
delta_total = iter_result.total_score - prev_total
```

`run.iterations[i - 1]` is correct for contiguous iteration numbering, but the `i` loop variable is the *loop counter*, not the number of completed iterations at that point. Because `iter_result` is appended to `run.iterations` at line 179 before this block runs, `run.iterations[i - 1]` refers to two iterations prior to the current one only when `i` matches the length of `run.iterations` minus one — which it always does in the happy path. The logic is therefore accidentally correct in the normal case. However if a future caller inserts or re-orders entries in `run.iterations` (or if `i` diverges from the list index), this silently produces wrong progress output. The cleaner, robust form is:

```python
prev_total = run.iterations[-2].total_score if len(run.iterations) >= 2 else 0
delta_total = iter_result.total_score - prev_total
```

This makes the intent ("delta vs. the immediately preceding entry") explicit and independent of the loop counter.

---

### WR-02: `test_optimiser_skipped_on_last_iteration` has dead/inert code after the assertion

**File:** `tests/test_loop.py:237-240`

**Issue:** Lines 237-240 assign to `last_iter` but never use it, and the comment says "we need to re-setup" — indicating a partially-written test was committed:

```python
last_iter = loop.run_experiment.__module__
# Check last iteration has no optimiser data — re-run to inspect
# (we already consumed the client, so we need to re-setup)
```

`loop.run_experiment.__module__` returns the string `"src.loop"`, which is assigned but never asserted. The test therefore passes vacuously — the intent (verify last iteration has empty optimiser fields) is already covered by `test_optimiser_fields_empty_on_last_iteration`, but the dead code signals an unfinished thought. If the intent was to verify the call count only, lines 237-240 should be deleted; if a separate assertion was planned, it needs a fresh `fake_client` setup and appropriate assertions.

**Fix:** Remove lines 237-240 from `test_optimiser_skipped_on_last_iteration`, leaving only the call-count assertion at line 235:

```python
def test_optimiser_skipped_on_last_iteration(fake_client, monkeypatch, tmp_path):
    """3-iteration run uses 8 LLM calls total (3 agent + 3 judge + 2 optimiser)."""
    import src.loop as loop

    client = fake_client(_happy_responses(3))
    monkeypatch.setattr(loop, "run_pre_loop_test", lambda: _make_go_result())
    monkeypatch.setattr(loop, "_get_ollama_version", lambda: "0.5.13")
    monkeypatch.setattr(loop, "_RESULTS_FILE", tmp_path / "run_001.json")
    monkeypatch.setattr(loop, "_RESULTS_DIR", tmp_path)
    monkeypatch.setattr(loop.config, "num_iterations", 3)

    loop.run_experiment()

    # 3 agent + 3 judge + 2 optimiser = 8 total LLM calls
    assert len(client.calls) == 8
```

---

### WR-03: `_compute_deltas` skips items present in `last_valid_scores` but absent from `current`

**File:** `src/loop.py:73-75`

**Issue:** The delta dict is built by iterating over `current` only:

```python
delta = {
    k: current.get(k, 0) - last_valid_scores.get(k, 0) for k in current
}
```

If the judge returns a partial result in which some item IDs that appeared in a previous valid iteration are missing (e.g. the model drops an item), those item IDs will be silently absent from `deltas[i]`. Downstream consumers of the JSON (Streamlit app) that iterate over all expected item IDs would then receive `KeyError` or produce asymmetric delta tables. The rubric is fixed at 8 items, so the typical case is fine, but a partial judge response (possible because the judge retry only validates Pydantic structure, not completeness of item coverage) can produce this silent truncation.

**Fix:** Union the key sets so dropped items get an explicit delta:

```python
all_keys = set(current) | set(last_valid_scores)
delta = {
    k: current.get(k, 0) - last_valid_scores.get(k, 0) for k in all_keys
}
```

---

## Info

### IN-01: Hardcoded results filename does not support multiple runs

**File:** `src/loop.py:32`

**Issue:** `_RESULTS_FILE = _RESULTS_DIR / "run_001.json"` is a module-level constant. If `run_experiment()` is called more than once in the same process (e.g. during tests), each call overwrites the same file. Tests work around this with `monkeypatch`, but the production path has no guard. This is acceptable for the current single-experiment scope but warrants a comment explaining the intent.

**Fix:** Add a brief comment:

```python
# Hardcoded to run_001 — single experiment per invocation by design.
_RESULTS_FILE = _RESULTS_DIR / "run_001.json"
```

---

### IN-02: `_happy_responses` docstring word count is correct but fragile to model changes

**File:** `tests/test_loop.py:168-181`

**Issue:** The docstring states "Total for 3 iters: 3 agent + 3 judge + 2 optimiser = 8 responses." This is correct. However, if the agent, judge, or optimiser retry counts change, this exact count will silently become wrong and `test_optimiser_skipped_on_last_iteration` will fail with a confusing `AssertionError` from `FakeChatCompletions.create` rather than a meaningful test failure message. This is a test maintainability concern, not a current bug.

**Fix:** Keep the docstring, but add a comment in `test_optimiser_skipped_on_last_iteration` explaining how the 8-call budget is derived so future maintainers know where to update the count.

---

### IN-03: `_make_nogo_result` reuses the same `IterationResult` objects for both runs

**File:** `tests/test_loop.py:140-160`

**Issue:**

```python
run1 = IterationResult(...)
run2 = IterationResult(...)
return PreLoopTestResult(
    output_a_runs=[run1, run2],
    output_b_runs=[run1, run2],  # same objects
    ...
)
```

`output_a_runs` and `output_b_runs` share the same two `IterationResult` instances. Pydantic v2 copies by value on assignment into list fields, so there is no aliasing risk at the model level. However, if any future test code mutates the instances before construction this would cause surprising cross-contamination. The issue is minor but it is cleaner to construct separate objects for `output_b_runs` or at least add a comment noting the sharing is intentional.

---

_Reviewed: 2026-04-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
