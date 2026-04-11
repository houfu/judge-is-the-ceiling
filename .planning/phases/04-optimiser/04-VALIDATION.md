---
phase: 4
slug: optimiser
status: draft
nyquist_compliant: false
wave_0_complete: true
created: 2026-04-12
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> **Wave 0 infrastructure was fully established by Phase 2** (pytest, integration marker, FakeClient, VALID_JUDGE_JSON, autouse _reset_llm_singleton). Phase 4 adds zero Wave 0 work.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (inherited) |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` (unchanged) |
| **Quick run command** | `uv run pytest -q -m "not integration"` |
| **Full suite command** | `uv run pytest -q` (model defaults to `gemma4:26b`, no env override needed) |
| **Estimated runtime** | ~0.5s unit only (21 baseline + ~10-12 new Phase 4 tests); ~3-5 min integration (reuses Phase 2+3 integration tests; optional new optimiser smoke adds ~30-60s) |

---

## Sampling Rate

- **After every task commit:** `uv run pytest -q -m "not integration"` — cheap, catches schema extension regressions and optimiser unit logic
- **After every plan wave:** Same unit-only command
- **Before `/gsd-verify-work`:** Full suite with integration — runs Phase 2, 3, and optional Phase 4 integration tests
- **Max feedback latency:** 15 seconds (unit only)

---

## Per-Task Verification Map

*Populated by the planner with real task IDs during plan authoring. Phase 4 is likely a single plan (04-01) with 3-4 tasks: (a) src/models.py schema extension + BANNED_RUBRIC_VOCAB_TOKENS constant, (b) src/optimiser.py library, (c) tests/test_optimiser.py unit suite, (d) optional live integration smoke.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | 04-01 | 1 | — (schema) | — | `OptimiserResult` validates; `IterationResult` gains 3 defaulted fields without breaking `_check_totals`; `BANNED_RUBRIC_VOCAB_TOKENS` is importable from `src/models.py` | unit regression | `uv run pytest -q -m "not integration"` returns 21+ passed (Phase 2+3 baseline, no regressions) | ✅ (Phase 2) | ⬜ pending |
| TBD | 04-01 | 1 | OPTM-01 | T-04-01 (NDA never in signature) | `run_optimiser(system_prompt: str, judge_result: JudgeResult) -> OptimiserResult` — type signature excludes NDA structurally; no defensive assertion needed (Phase 5 enforces at call site) | unit | `grep -n 'def run_optimiser' src/optimiser.py` returns `run_optimiser(system_prompt: str, judge_result: JudgeResult)` — signature does not contain `nda` parameter | ✅ (plan 04-01) | ⬜ pending |
| TBD | 04-01 | 1 | OPTM-02 | — | `OptimiserResult.feedback_seen` is populated with the exact list of formatted feedback strings passed to the LLM; `IterationResult.optimiser_feedback_seen` extension field captures it across iteration boundary | unit (FakeClient) | `uv run pytest -q tests/test_optimiser.py::test_feedback_pass_through_logged` | ✅ (plan 04-01) | ⬜ pending |
| TBD | 04-01 | 1 | OPTM-03 | — | `OptimiserResult.prompt_diff` contains a non-empty unified-diff string when `new_system_prompt != system_prompt`; empty string when sentinel/failed | unit (FakeClient) | `uv run pytest -q tests/test_optimiser.py::test_prompt_diff_is_unified_diff tests/test_optimiser.py::test_prompt_diff_empty_on_sentinel` | ✅ (plan 04-01) | ⬜ pending |
| TBD | 04-01 | 1 | OPTM-02 + P11 | — | Word-count post-validation enforces 300-word limit; retry with stricter reminder up to 3 attempts; on exhaustion returns `OptimiserResult(failed=True, new_system_prompt=system_prompt)` without raising | unit (FakeClient) | `uv run pytest -q tests/test_optimiser.py::test_word_overrun_triggers_retry tests/test_optimiser.py::test_retry_recovers_on_second_attempt tests/test_optimiser.py::test_retry_exhaustion_returns_sentinel tests/test_optimiser.py::test_sentinel_preserves_input_prompt` | ✅ (plan 04-01) | ⬜ pending |
| TBD | 04-01 | 1 | — (P8) | T-04-02 (vocab leak) | Post-hoc P8 scrub detects banned rubric vocabulary in optimiser output; sets `vocab_warning=True` + logs WARNING; does NOT retry (per P5 "detect don't prevent" guidance) | unit (FakeClient) | `uv run pytest -q tests/test_optimiser.py::test_vocab_scrub_flags_banned_token tests/test_optimiser.py::test_vocab_scrub_clean_output_passes` | ✅ (plan 04-01) | ⬜ pending |
| TBD | 04-01 | 1 | OPTM-02 | — | Feedback extraction produces numbered list sorted by score ascending; all 8 items included; item_ids stripped | unit | `uv run pytest -q tests/test_optimiser.py::test_feedback_sorted_by_score_ascending tests/test_optimiser.py::test_all_eight_items_included tests/test_optimiser.py::test_item_ids_stripped` | ✅ (plan 04-01) | ⬜ pending |
| TBD (optional) | 04-01 | 1 | OPTM-01 + OPTM-02 + OPTM-03 | — | Live optimiser round-trip against gemma4:26b using Phase 3's real JudgeResult from `results/pre_loop_test.json` as seed; returns OptimiserResult with `failed=False`, `prompt_word_count <= 300`, non-empty `prompt_diff` | integration | `uv run pytest -q -m integration tests/test_optimiser_smoke.py::test_optimiser_live_round_trip` (or folded into existing `tests/test_smoke_ollama.py`) | ⚠️ optional per plan | ⬜ pending |

**Note on requirement coverage:** OPTM-01 (NDA never passed) is verified by the type signature — a grep check plus the function-compilation check is sufficient since Python's type system doesn't enforce at runtime but the absence of an `nda` parameter in the signature is structurally enforced. OPTM-02 (pass-through logging) is verified by 4 tests. OPTM-03 (prompt diff stored) is verified by 2 tests.

---

## Wave 0 Requirements

**None.** Phase 2 Wave 0 already installed and verified everything Phase 4 needs:
- [x] pytest installed as dev dependency (Plan 02-01)
- [x] `pyproject.toml [tool.pytest.ini_options]` with `integration` marker (Plan 02-01)
- [x] `tests/conftest.py` with `FakeClient` fixture + `VALID_JUDGE_JSON` constant (Plan 02-01)
- [x] `tests/__init__.py` (Plan 02-01)
- [x] Autouse `_reset_llm_singleton` fixture (Plan 02-REVIEW-FIX M-01) — also protects Phase 4's new `src/optimiser.py` module if it caches any client state
- [x] `config.model` default = `gemma4:26b` (Option B decision, Phase 2 post-mortem)

Phase 4 reuses every fixture and helper verbatim. No new Wave 0 work.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Qualitative review that the rewritten prompt still reads as a coherent NDA-review task description after optimisation | P5 + readability | An LLM-generated rewrite can pass word-count + vocab checks but still be incoherent or off-topic. No automated check can verify that. | After the Phase 4 optional integration smoke runs (or during Phase 5's first real iteration), read the `new_system_prompt` output and confirm it still instructs "review this NDA and identify issues" in some form. Log result in SUMMARY. |
| Qualitative spot-check that the retry reminder wording produces well-behaved rewrites under word pressure | P11 retry loop effectiveness | A poorly-worded retry message could make the model panic-compress or produce degenerate output | If any integration test exercises the retry path (by reducing WORD_LIMIT temporarily or by constructing a prompt that's hard to shorten), eyeball the final output for quality. Optional — skip if retry path is only exercised by unit tests. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies (to be populated by planner)
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify (should be easy — each Phase 4 task has a test)
- [ ] Wave 0 covers all MISSING references → **N/A, Wave 0 empty**
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s (unit only)
- [ ] `nyquist_compliant: true` set in frontmatter — set by planner after task IDs are populated

**Approval:** pending (planner populates task IDs, then flips frontmatter nyquist_compliant: true)
