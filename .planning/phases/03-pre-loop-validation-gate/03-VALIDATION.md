---
phase: 3
slug: pre-loop-validation-gate
status: draft
nyquist_compliant: false
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

*Populated by the planner during plan authoring. All Phase 3 work maps to a single integration test: `tests/test_pre_loop_gate.py::test_pre_loop_gate_passes` (marked `@pytest.mark.integration`), which exercises the entire pipeline end-to-end against live Ollama.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD by planner | 03-01 | 1 | — (infra) | — | `PreLoopTestResult` model validates; `ExperimentRun.pre_loop_test` retyped from `dict` to `PreLoopTestResult \| None`; existing tests still pass | unit | `uv run pytest -q -m "not integration"` returns 21+ passed | ✅ (phase 2) | ⬜ pending |
| TBD by planner | 03-01 | 1 | TEST-01 (SC-1, SC-4) | T-03-01 (NDA in JSON) | `run_pre_loop_test()` returns `PreLoopTestResult` with non-empty runs, writes `results/pre_loop_test.json` in same schema as loop iterations, prints banner to stdout | integration | `uv run pytest -q -m integration tests/test_pre_loop_gate.py::test_pre_loop_gate_passes` | ✅ (plan 03-01) | ⬜ pending |
| TBD by planner | 03-01 | 1 | TEST-02 (SC-2) | — | `result.gap >= 2.0` on live gemma4:26b run against `data/output_a.md` vs `data/output_b.md` | integration | same as above | ✅ (plan 03-01) | ⬜ pending |
| TBD by planner | 03-01 | 1 | TEST-02 (SC-3) | — | `result.judgment_gap > 0` on the same live run (thesis-critical judgment signal) | integration | same as above | ✅ (plan 03-01) | ⬜ pending |

**Note on requirement mapping:** TEST-01 covers "Run output A and output B through judge with same rubric and playbook" → satisfied by the library function + the integration test's successful run. TEST-02 covers "Results logged in same JSON schema as loop iterations for direct comparison" → satisfied by D-01 + D-02 (PreLoopTestResult uses IterationResult entries verbatim, and ExperimentRun.pre_loop_test field retyped).

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

If the planner chooses to add optional FakeClient-based unit tests for `PreLoopTestResult` validator / gap computation, those tests can reuse the existing `conftest.py` fixtures with no new Wave 0 work. **Research recommends NOT adding these** since the aggregation math is 2 lines and the integration test already covers the same code path with real data — skipping saves ~100 lines of test scaffolding with no decrease in coverage.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Qualitative check that `rationale` string actually explains the decision | D-05 readability | "Hand-written at test-authoring time" means the planner authors 2-3 template sentences; no automated check can verify they're *readable* | After Plan 03-01 runs, `cat results/pre_loop_test.json \| python -m json.tool \| grep rationale` and confirm the sentence makes sense |
| Qualitative check that the console banner is legible | D-05 banner format | Portability across terminal widths can't be unit-tested | Run `uv run python src/pre_loop_test.py` interactively once and eyeball the banner |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies (to be populated by planner)
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify (should be trivially satisfied — Phase 3 is small)
- [ ] Wave 0 covers all MISSING references → **N/A, Wave 0 empty because Phase 2 set up everything**
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s (unit only)
- [ ] `nyquist_compliant: true` set in frontmatter — set by planner after task map is populated with real task IDs

**Approval:** pending (planner populates task IDs, then flips frontmatter nyquist_compliant: true)
