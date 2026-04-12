---
phase: 05-main-loop
plan: "01"
subsystem: loop
tags:
  - main-loop
  - integration
  - experiment-run
  - tdd
dependency_graph:
  requires:
    - src/agent.py::run_agent
    - src/judge.py::run_judge
    - src/optimiser.py::run_optimiser
    - src/pre_loop_test.py::run_pre_loop_test
    - src/models.py::ExperimentRun
    - src/models.py::IterationResult
  provides:
    - src/loop.py::run_experiment
    - src/loop.py::_compute_deltas
    - src/loop.py::_write_results
    - src/loop.py::_get_ollama_version
    - results/run_001.json (at runtime)
  affects:
    - results/run_001.json
tech_stack:
  added: []
  patterns:
    - TDD (RED/GREEN): tests written first, then implementation
    - FakeClient injection via monkeypatch (established Phase 2 pattern)
    - Pydantic model_dump() + dict injection for non-schema JSON keys
    - urllib.request with timeout for Ollama version fetch
    - Per-iteration incremental file writes for crash resilience
key_files:
  created:
    - src/loop.py
    - tests/test_loop.py
  modified: []
decisions:
  - "Optimiser not called after last iteration (D-12): avoids wasted LLM call and clean iteration boundary"
  - "Deltas computed at write time via _compute_deltas, not stored in IterationResult: avoids Pydantic model changes"
  - "model_dump() + dict injection pattern: allows deltas top-level key without schema change"
  - "Judge/optimiser sentinel resilience: loop continues on failure, sentinel recorded in IterationResult"
  - "vocab_warning logged at WARNING level per D-15: detection signal, not prevention"
metrics:
  duration_minutes: 11
  completed_date: "2026-04-12"
  tasks_completed: 2
  tasks_total: 3
  files_created: 2
  files_modified: 0
---

# Phase 05 Plan 01: Main Loop Summary

**One-liner:** `run_experiment()` wires pre-loop gate -> N iterations of agent->judge->optimiser with incremental JSON writes and per-item delta tracking in `results/run_001.json`.

## What Was Built

### src/loop.py (219 lines)

The capstone integration module that assembles all Phase 2-4 components into a single `uv run python src/loop.py` command:

- `run_experiment() -> ExperimentRun | None`: Full experiment orchestration. Calls pre-loop gate first; returns None on no-go (no file written). On go: runs N iterations of agent->judge->optimiser, writes results after each iteration, returns completed ExperimentRun.
- `_compute_deltas(iterations)`: Per-item score delta computation. Iteration 0 returns None; sentinel iterations (scores==[]) return None; subsequent iterations compute delta against last valid iteration's scores.
- `_write_results(run, deltas, path)`: Serialises ExperimentRun via `model_dump()` + dict injection for the `deltas` key (avoiding schema changes).
- `_get_ollama_version()`: Fetches Ollama version from `localhost:11434/api/version` with 5-second timeout. Returns "unknown" on any failure.
- `__main__` block: `logging.basicConfig` + `run_experiment()` + `sys.exit(1)` on None return.

### tests/test_loop.py (492 lines)

11 FakeClient-backed unit tests:

1. `test_happy_path_three_iterations` - 3 iterations, correct structure
2. `test_optimiser_skipped_on_last_iteration` - 8 total LLM calls (3+3+2)
3. `test_optimiser_fields_empty_on_last_iteration` - last iteration audit fields are empty
4. `test_results_file_written_with_all_iterations` - file exists with all iterations + deltas key
5. `test_deltas_key_in_output_json` - deltas[0]=None, deltas[1..N] are 8-key dicts
6. `test_run_metadata_envelope` - config has all 5 required keys including ollama_version
7. `test_judge_sentinel_continues_loop` - sentinel iteration has scores=[], loop continues
8. `test_optimiser_sentinel_continues_loop` - old prompt preserved on optimiser exhaustion
9. `test_nogo_returns_none_no_file_written` - no-go returns None, no file created
10. `test_delta_null_on_sentinel_iteration` - sentinel delta is None, next delta vs last valid
11. `test_vocab_warning_logged` - vocab_warning=True triggers WARNING log with "vocab_warning"

## Test Results

- `uv run pytest tests/test_loop.py` — **11/11 passed**
- `uv run pytest tests/ --ignore=tests/test_smoke_ollama.py` — **45/45 passed** (no regressions)
- `uv run black --check src/loop.py tests/test_loop.py` — clean after reformatting

## Deviations from Plan

### Minor: 11 tests instead of 10

**Found during:** Task 1 (RED phase)
**Issue:** The plan's `test_optimiser_skipped_on_last_iteration` combined two concerns: LLM call count AND audit field verification. Split into two tests for clarity.
**Fix:** Added `test_optimiser_fields_empty_on_last_iteration` as a separate test. The call count assertion remains in `test_optimiser_skipped_on_last_iteration`.
**Files modified:** `tests/test_loop.py`
**Impact:** Additional coverage, no behaviour change.

## Task 3 Status: Awaiting Human Verification

Task 3 is a `checkpoint:human-verify` requiring a live Ollama run. Tasks 1 and 2 are complete and committed. Task 3 requires:

1. Ollama running with `gemma4:26b` loaded
2. `NUM_ITERATIONS=2 uv run python src/loop.py` producing `results/run_001.json`
3. JSON validation: 2 iterations, deltas key, correct config structure

## Self-Check

Files created:
- `/Users/houfu/Projects/judge-is-the-ceiling/src/loop.py` — FOUND
- `/Users/houfu/Projects/judge-is-the-ceiling/tests/test_loop.py` — FOUND

Commits:
- `b8d12e5` — test(05-01): add failing tests for run_experiment loop — FOUND
- `373ee19` — feat(05-01): implement src/loop.py — run_experiment + helpers + __main__ — FOUND

## Self-Check: PASSED
