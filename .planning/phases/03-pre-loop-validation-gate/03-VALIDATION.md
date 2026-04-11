---
phase: 3
slug: pre-loop-validation-gate
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-11
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> **Wave 0 infrastructure was entirely established by Phase 2** (pytest installed, `integration` marker registered in `pyproject.toml`, `FakeClient` + `VALID_JUDGE_JSON` fixtures in `tests/conftest.py`). Phase 3 adds zero Wave 0 work.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (inherited from Phase 2) |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` (unchanged) |
| **Quick run command** | `uv run pytest -q -m "not integration"` |
| **Full suite command** | `MODEL=gemma4:26b uv run pytest -q` — or without MODEL env since `gemma4:26b` is now the default per Option B |
| **Estimated runtime** | ~0.2s unit only (unchanged from Phase 2); ~3-5 min with integration (Phase 2 integration ~2min + Phase 3 integration ~2-4min for 4 judge calls against gemma4:26b) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q -m "not integration"` — this is cheap (21+ tests in ~0.2s), catches regressions in Phase 2 code and any unit work in Phase 3 if added
- **After every plan wave:** Same unit-only command
- **Before `/gsd-verify-work`:** Full suite including `-m integration` must be green — this runs Phase 2's `test_smoke_ollama.py` AND Phase 3's `test_pre_loop_gate.py`
- **Max feedback latency:** 15 seconds (unit only)

---

## Per-Task Verification Map

*All Phase 3 work maps to a single integration test: `tests/test_pre_loop_gate.py::test_pre_loop_gate_passes` (marked `@pytest.mark.integration`), which exercises the entire pipeline end-to-end against live Ollama. Task 1 (models edit) also has a unit regression check to prove it does not break Phase 1+2 tests.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-T1 | 03-01 | 1 | — (infra) | T-03-05 (path traversal — mitigated in T2) | `PreLoopTestResult` model validates; `ExperimentRun.pre_loop_test` retyped from `dict` to `PreLoopTestResult \| None`; `_compute_gate` @model_validator enforces "exactly 2 runs per output" invariant (V5 Input Validation / ASVS L1); existing 21+ unit tests still pass | unit | `uv run pytest -q -m "not integration"` returns 21+ passed, 0 failed | ✅ (Phase 2) | ⬜ pending |
| 03-01-T2 | 03-01 | 1 | — (plumbing) | T-03-01 (NDA-in-JSON — accept, gitignored), T-03-05 (path traversal — `Path(__file__).resolve().parent.parent` is CWD-independent, no traversal surface) | `src/pre_loop_test.py` imports cleanly; `run_pre_loop_test` is the sole public API; `_print_banner` is module-private and called only from `__main__` (D-10); no `try/except` around `run_judge` (inherits JUDG-05 sentinel contract); threshold is hard-coded on the model (P10) | import smoke | `uv run python -c "from src.pre_loop_test import run_pre_loop_test, _print_banner, _build_rationale, _judge_one; print('import ok')"` returns `import ok` exit 0; AND `uv run pytest -q -m "not integration"` still returns 21+ passed | ✅ (plan 03-01 T2) | ⬜ pending |
| 03-01-T3 | 03-01 | 1 | TEST-01 (SC-1), TEST-02 (SC-1) | T-03-02 (prompt injection — mitigated upstream in Phase 2 D-07), T-03-04 (sentinel masking — mitigated by rationale Case 3 in Resolution #4) | `run_pre_loop_test()` returns `PreLoopTestResult` with 4 populated `IterationResult` entries, writes `results/pre_loop_test.json` in same schema as loop iterations, prints banner to stdout via `__main__`; integration test discoverable under `@pytest.mark.integration` | integration | `uv run pytest -q -m integration tests/test_pre_loop_gate.py::test_pre_loop_gate_passes 2>&1 \| tee /tmp/phase3-integration.log` returns `1 passed`; AND `test -f results/pre_loop_test.json && echo artifact present` prints `artifact present` | ✅ (plan 03-01 T3) | ⬜ pending |
| 03-01-T3 | 03-01 | 1 | TEST-02 (SC-2) | — | `result.gap >= result.threshold` (≥ 2.0) on live gemma4:26b run against `data/output_a.md` vs `data/output_b.md`; P10 hard-coded threshold | integration | Same command as above — the assertion is inside `test_pre_loop_gate_passes` and fails specifically with a gap message if SC-2 is not met | ✅ (plan 03-01 T3) | ⬜ pending |
| 03-01-T3 | 03-01 | 1 | TEST-02 (SC-3) | T-03-04 (masking — separate assert surfaces the thesis-critical failure explicitly) | `result.judgment_gap > 0` on the same live run (thesis-critical judgment signal per P1) | integration | Same command as above — the assertion is a SEPARATE `assert` (not bundled with the decision check) so pytest reports P1-style failures explicitly | ✅ (plan 03-01 T3) | ⬜ pending |
| 03-01-T3 | 03-01 | 1 | TEST-01/TEST-02 (SC-4) | — | `result.decision == "go"` documented in results file AND printed to stdout banner via `_print_banner` when invoked as `uv run python src/pre_loop_test.py` | integration + artifact check | `python -c "import json; d=json.load(open('results/pre_loop_test.json')); assert d['decision']=='go', d['rationale']; print('go')"` prints `go` exit 0 | ✅ (plan 03-01 T3) | ⬜ pending |

**Note on requirement mapping:** TEST-01 covers "Run output A and output B through judge with same rubric and playbook" → satisfied by Task 2's library function + Task 3's integration test successful run. TEST-02 covers "Results logged in same JSON schema as loop iterations for direct comparison" → satisfied by Task 1's D-01 `PreLoopTestResult` embedding `IterationResult` verbatim and Task 1's D-02 `ExperimentRun.pre_loop_test` retype.

**Note on task IDs:** `03-01-T1` / `03-01-T2` / `03-01-T3` refer to Tasks 1, 2, 3 inside `03-01-PLAN.md` in the order they appear. Task 3 has four rows in the map because the single integration test simultaneously verifies SC-1, SC-2, SC-3, and SC-4 via distinct assertions.

---

## Wave 0 Requirements

**None.** Phase 2 Wave 0 already installed and verified all Phase 3 needs:
- [x] pytest installed as dev dependency (Plan 02-01)
- [x] `pyproject.toml [tool.pytest.ini_options]` with `integration` marker registered (Plan 02-01)
- [x] `tests/conftest.py` with `FakeClient` fixture + `VALID_JUDGE_JSON` constant (Plan 02-01)
- [x] `tests/__init__.py` (Plan 02-01)
- [x] Autouse `_reset_llm_singleton` fixture (Plan 02-REVIEW-FIX M-01) — ensures `src.llm._client` state doesn't leak across the new Phase 3 tests either
- [x] `.env` file convention with `MODEL=gemma4:26b` (developer-local, gitignored)
- [x] `config.model` default = `gemma4:26b` (Option B decision)

If the planner chooses to add optional FakeClient-based unit tests for `PreLoopTestResult` validator / gap computation, those tests can reuse the existing `conftest.py` fixtures with no new Wave 0 work. **Research recommended NOT adding these** (Resolution #8) since the aggregation math is 2 lines and the integration test already covers the same code path with real data. The plan honours this — **0 unit tests added in Phase 3**.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Qualitative check that `rationale` string actually explains the decision | D-05 readability | "Hand-written at test-authoring time" means the planner authors 2-3 template sentences; no automated check can verify they're *readable* | After Task 3 runs, `cat results/pre_loop_test.json \| python -m json.tool \| grep rationale` and confirm the sentence makes sense. Record result in SUMMARY. |
| Qualitative check that the console banner is legible | D-05 banner format | Portability across terminal widths can't be unit-tested | Run `uv run python src/pre_loop_test.py` interactively once and eyeball the banner. Record result in SUMMARY. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (populated above — Task 1 has unit regression, Task 2 has import smoke, Task 3 has integration + artifact check)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (each of the 3 tasks has its own automated check)
- [x] Wave 0 covers all MISSING references → **N/A, Wave 0 empty because Phase 2 set up everything**
- [x] No watch-mode flags
- [x] Feedback latency < 15s (unit only — `uv run pytest -q -m "not integration"` runs in < 1s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planner-approved 2026-04-11. Ready for `/gsd-execute-phase 03`.
