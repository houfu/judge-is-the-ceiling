---
phase: 04-optimiser
plan: 01
subsystem: optimiser
tags:
  - optimiser
  - pydantic
  - retry-loop
  - p5-detection
  - p8-scrub
  - p11-mitigation
dependency-graph:
  requires:
    - src/models.py (RubricScore, JudgeResult, IterationResult, @model_validator pattern)
    - src/judge.py (retry-loop pattern, MAX_RETRIES, num_ctx extra_body)
    - src/llm.py (get_client singleton)
    - src/config.py (model, temperature, num_ctx)
    - tests/conftest.py (FakeClient fixture, _reset_llm_singleton autouse)
    - data/rubric.json (shape of 8-item rubric consumed upstream by run_judge)
  provides:
    - src.models.BANNED_RUBRIC_VOCAB_TOKENS (22-token tuple, shared P8 SSOT)
    - src.models.OptimiserResult (Pydantic model with structural invariant validator)
    - src.models.IterationResult.optimiser_feedback_seen (new defaulted field)
    - src.models.IterationResult.prompt_diff (new defaulted field)
    - src.models.IterationResult.prompt_word_count (new defaulted field)
    - src.optimiser.run_optimiser (library function, signature excludes NDA)
    - src.optimiser.OPTIMISER_SYSTEM_PROMPT (meta-prompt constant with interpolated banned vocab)
    - src.optimiser.MAX_RETRIES (=3)
    - src.optimiser.WORD_LIMIT (=300)
    - src.optimiser._build_feedback_block / _build_user_message / _build_retry_message / _compute_prompt_diff / _check_banned_vocab / _count_words
    - jitc.optimiser logger namespace
  affects:
    - tests/test_agent.py (imports shared BANNED_RUBRIC_VOCAB_TOKENS via `as _BANNED_TOKENS`)
    - Phase 5 loop.py (not yet written): consumes OptimiserResult, mirrors feedback_seen/prompt_diff/prompt_word_count into IterationResult
tech-stack:
  added: []
  patterns:
    - stdlib difflib.unified_diff for prompt diff capture (no new deps)
    - post-validation retry loop mirroring src/judge.py (different validator: word-count vs Pydantic)
    - module-load f-string interpolation of BANNED_RUBRIC_VOCAB_TOKENS into system prompt (prevents drift)
    - Pydantic v2 @model_validator(mode="after") for structural invariants
    - @pytest.fixture fake_client with deep-copied kwargs capture for multi-call inspection
key-files:
  created:
    - src/optimiser.py
    - tests/test_optimiser.py
    - .planning/phases/04-optimiser/04-01-SUMMARY.md
  modified:
    - src/models.py (added BANNED_RUBRIC_VOCAB_TOKENS, OptimiserResult class, 3 fields on IterationResult)
    - tests/test_agent.py (inline _BANNED_TOKENS literal → shared import from src.models)
decisions:
  - Fixed a latent bug in the plan's _compute_prompt_diff skeleton (keepends=True + lineterm="" produced a single concatenated string with no inter-line separators); switched to splitlines() + "\n".join for readable multi-line unified diff output
  - Rewrote _synthetic_judge_result feedback text to use descriptive words instead of embedding item_id substrings, because the item-id strip assertion fails if the feedback text itself contains the tokens (the implementation strips metadata, not arbitrary substrings)
metrics:
  duration: ~20 minutes
  tasks: 3
  files: 4
  tests_baseline: 21
  tests_new: 12
  tests_final: 33
  completed: 2026-04-11
---

# Phase 4 Plan 1: Optimiser — schema extension, library function, and unit test suite Summary

Library `src/optimiser.py` with `run_optimiser(system_prompt, judge_result) -> OptimiserResult` that rewrites the agent system prompt from judge feedback, enforcing a 300-word hard limit via a 3-retry post-validation loop, running a post-hoc P8 vocab scrub that sets a warning flag (without retrying or failing), and capturing a unified-diff of the rewrite for OPTM-03 audit.

## Tasks Completed

- **Task 1 (commit c8438c5):** Extended `src/models.py` with the 22-token `BANNED_RUBRIC_VOCAB_TOKENS` tuple (shared P8 source of truth), new `OptimiserResult` Pydantic class with structural-invariant validator (D-02/D-03), and three defaulted passive-logging fields on `IterationResult` (`optimiser_feedback_seen`, `prompt_diff`, `prompt_word_count` per D-04). Refactored `tests/test_agent.py` to import the shared constant via `as _BANNED_TOKENS` so the Phase 2 agent-prompt regression gate and Phase 4 optimiser scrub cannot drift. Verified backward compatibility: Phase 3's `results/pre_loop_test.json` still parses under the extended `IterationResult`. Unit baseline: 21 passed, 3 deselected.
- **Task 2 (commit d5bf8a6):** Implemented `src/optimiser.py` from the Phase 4 RESEARCH skeleton. Structural highlights: `run_optimiser(system_prompt, judge_result) -> OptimiserResult` with NDA structurally absent from the signature (OPTM-01), 3-retry post-validation loop mirroring Phase 2's `run_judge`, sentinel `OptimiserResult(failed=True, new_system_prompt=system_prompt)` on exhaustion (mirrors JUDG-05 graceful failure), post-hoc `_check_banned_vocab` that sets `vocab_warning=True` and logs WARNING but never retries (D-15 / P5 "detect don't prevent"), `OPTIMISER_SYSTEM_PROMPT` with `BANNED_RUBRIC_VOCAB_TOKENS` interpolated at module load so meta-prompt and scrub lists cannot drift, stdlib `difflib.unified_diff` for OPTM-03 `prompt_diff` capture, `extra_body={"options": {"num_ctx": config.num_ctx}}` on every call (P6), and a `jitc.optimiser` logger.
- **Task 3 (commit dd1c2a1):** Created `tests/test_optimiser.py` with 12 FakeClient-backed unit tests covering: happy path, retry recovery on second attempt, retry exhaustion sentinel, retry-correction message content, vocab warning on banned token (with `retry_count == 0` assertion proving D-15), clean-output vocab-warning-false baseline, unified-diff format structure, feedback sort+item-id strip, all-8-items-in-user-message, OptimiserResult structural invariants (3 ValidationError cases), num_ctx/temperature/model on every call across a 3-call retry sequence, and retry exhaustion logging ERROR at `jitc.optimiser`. Final suite: `uv run pytest -q -m "not integration"` = **33 passed, 3 deselected**.

## Files Touched

- `src/models.py` — added `BANNED_RUBRIC_VOCAB_TOKENS` tuple (22 tokens), extended `IterationResult` with 3 defaulted fields, added `OptimiserResult` class with `_check_structural_invariants` validator.
- `src/optimiser.py` — **new file**, 240 lines. `run_optimiser`, 6 helpers (`_count_words`, `_build_feedback_block`, `_build_user_message`, `_build_retry_message`, `_compute_prompt_diff`, `_check_banned_vocab`), `OPTIMISER_SYSTEM_PROMPT` constant, `MAX_RETRIES`/`WORD_LIMIT` module constants, `jitc.optimiser` logger.
- `tests/test_optimiser.py` — **new file**, 12 tests.
- `tests/test_agent.py` — 1-line refactor: inline `_BANNED_TOKENS` list replaced by `from src.models import BANNED_RUBRIC_VOCAB_TOKENS as _BANNED_TOKENS`. All 5 Phase 2 agent tests still pass against the expanded 22-token list (verified safe: `ITERATION_ZERO_SYSTEM_PROMPT` contains none of "judge", "1a"..."4b").

## Decision Coverage (D-01 .. D-15)

| Decision | Where implemented | Verification |
|----------|-------------------|--------------|
| D-01 (signature excludes NDA) | `run_optimiser(system_prompt: str, judge_result: JudgeResult) -> OptimiserResult` | `inspect.signature` check in verify block returned `['system_prompt', 'judge_result']`. OPTM-01 structurally enforced. |
| D-02 (OptimiserResult fields) | `src/models.py::OptimiserResult` | 8 fields match spec (`new_system_prompt`, `feedback_seen`, `prompt_diff`, `prompt_word_count`, `old_word_count`, `vocab_warning`, `retry_count`, `failed`). |
| D-03 (structural invariant validator) | `OptimiserResult._check_structural_invariants` | Word-count mismatch, negative `old_word_count`, retry_count out of range all raise ValidationError. Covered by test 10. |
| D-04 (IterationResult 3 new fields) | `IterationResult.optimiser_feedback_seen / prompt_diff / prompt_word_count`, all defaulted | Construct-with-no-new-fields check in Task 1 verify block passes. |
| D-05 (_check_totals unchanged) | `IterationResult._check_totals` body byte-identical | 21 baseline tests (including Phase 3 pre_loop gate tests) still green. |
| D-06 (backward-compat) | Default values on new fields | `PreLoopTestResult.model_validate_json(results/pre_loop_test.json)` exits 0. |
| D-07 (feedback sort + item_id strip) | `_build_feedback_block` | Test 8: `[2,0,1,2,0,1,2,0]` scores → index 0 is `[score=0]`, index 7 is `[score=2]`, no item_id tokens present. |
| D-08 (user message layout) | `_build_user_message` | Test 9: all 8 `feedback_seen` entries substring-match in `client.calls[0]["messages"][1]["content"]`. |
| D-09 (meta-prompt ban list) | `OPTIMISER_SYSTEM_PROMPT` f-string interpolates `_BANNED_LIST_FORMATTED` | Post-hoc assertion in verify block: all 22 tokens appear quoted in the meta-prompt. |
| D-10 (WORD_LIMIT = 300) | `WORD_LIMIT = 300` module constant | Tests 1/2/3 all reference 300 via observed behaviour. |
| D-11 (retry loop + sentinel) | `for attempt in range(1, MAX_RETRIES+1)` + exhaustion-path return | Tests 2 (recovery), 3 (sentinel byte-identical preservation), 4 (retry-message content). Non-raising confirmed by test 3. |
| D-12 (logger namespace) | `logger = logging.getLogger("jitc.optimiser")` | Tests 5 (WARNING on vocab hit) and 12 (ERROR on exhaustion) both use `caplog.at_level(..., logger="jitc.optimiser")`. |
| D-13 (unified diff) | `_compute_prompt_diff` using `difflib.unified_diff` | Test 7: diff contains `--- old_system_prompt`, `+++ new_system_prompt`, at least one `-` body line, at least one `+` body line. |
| D-14 (single-source-of-truth scrub) | `_check_banned_vocab` imports `BANNED_RUBRIC_VOCAB_TOKENS` from `src.models`; `OPTIMISER_SYSTEM_PROMPT` interpolates the same tuple | Changing the list in `src/models.py` propagates to meta-prompt, scrub, and the Phase 2 agent test gate. Verified via cross-module assertion. |
| D-15 (detect don't prevent) | On vocab hit: log WARNING + set `vocab_warning=True`, NO retry, NO failure | Test 5 asserts `retry_count == 0` and `failed is False` alongside `vocab_warning is True` (the thesis-preserving posture per P5). |

All 15 decisions implemented as locked. No architectural deviations.

## Deviations from Plan

Two Rule 1 (auto-fix bug) deviations both rooted in latent bugs within the RESEARCH skeleton. Both discovered during Task 3 test runs; both fixed before committing Task 3.

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_compute_prompt_diff` produced unseparated single-line output**
- **Found during:** Task 3, `test_prompt_diff_is_unified_diff_format` initial run
- **Issue:** The plan skeleton used `old.splitlines(keepends=True)` + `lineterm=""` + `"".join(...)`. For single-line input strings without trailing newlines, `splitlines(keepends=True)` returns one element with no newline, `lineterm=""` tells difflib to add no line terminator, and `"".join(...)` concatenates everything — producing `'--- old_system_prompt+++ new_system_prompt@@ -1 +1 @@-...+..'`, a single unseparated run. `splitlines()` on that output returns a single-element list, breaking any consumer (grep, jq, human reader, the test assertion).
- **Fix:** Changed to `old.splitlines()` (no keepends) + `"\n".join(...)`. difflib now returns each header and body line as a separate string, and we join them with explicit newlines. Verified with a direct `splitlines()` debug probe before committing.
- **Files modified:** `src/optimiser.py::_compute_prompt_diff`
- **Commit:** `dd1c2a1`
- **Impact on OPTM-03:** None — the bug would have silently shipped a malformed `prompt_diff` that looked plausible in the JSON file but was unusable for downstream analysis. Phase 5's results-file consumers would have hit the same problem. Fix caught pre-merge.

**2. [Rule 1 - Bug] Synthetic feedback text embedded item_id substrings**
- **Found during:** Task 3, `test_feedback_block_sorted_ascending_and_strips_item_ids` initial run
- **Issue:** The plan skeleton's `_synthetic_judge_result` built feedback as `f"Feedback for item {issue}{letter}."` — embedding "1a", "1b", etc. directly into the feedback TEXT. The `_build_feedback_block` implementation correctly strips `item_id` metadata (D-07) and formats as `N. [score=K] {feedback}`, so the resulting entries looked like `1. [score=0] Feedback for item 1a.`. The test then asserted `"1a" not in joined` and failed — because the item_id had leaked in via the feedback text, not via the metadata strip.
- **Fix:** Rewrote `_synthetic_judge_result` to use a fixed list of 8 descriptive phrases (`"confidentiality duration clarity"`, etc.) for `reasoning` and `feedback`. These are free of any item_id patterns, so the assertion now tests the thing it was meant to test: that `_build_feedback_block` does not leak item_id metadata.
- **Files modified:** `tests/test_optimiser.py::_synthetic_judge_result`
- **Commit:** `dd1c2a1`
- **Impact:** Tightened the test to its intended semantics. The implementation of `_build_feedback_block` was correct from the start; only the test data was confused.

No other deviations. All 3 tasks executed directly from the RESEARCH skeletons.

## Authentication Gates

None — all tests run against `FakeClient`; no live Ollama required for this plan.

## Test Results

| Metric | Value |
|--------|-------|
| Baseline (Phases 1-3) | 21 passed, 3 deselected |
| New (Phase 4 Plan 1) | 12 added |
| Final | **33 passed, 3 deselected** (0.16s) |
| Regressions | 0 |
| Backward-compat `results/pre_loop_test.json` | PASS (parses under extended `IterationResult`) |
| `uv run black --check src/models.py src/optimiser.py tests/test_optimiser.py tests/test_agent.py` | clean |

## Success Criteria Verification

All 12 phase-level success criteria from `04-01-PLAN.md` `<success_criteria>` met:

1. **OPTM-01 structural enforcement** — signature `(system_prompt: str, judge_result: JudgeResult)`, no NDA param. `inspect.signature` check passes.
2. **OPTM-02 feedback pass-through** — `OptimiserResult.feedback_seen` populated; `IterationResult.optimiser_feedback_seen` field added with default. Tests 1, 8, 9.
3. **OPTM-03 prompt diff** — `OptimiserResult.prompt_diff` is a unified-diff string; empty on sentinel. Tests 3, 7.
4. **SC-2 word-limit enforced** — post-validation 3-retry loop. Tests 1, 2, 3.
5. **P5/P8 detect-don't-prevent** — `test_vocab_warning_set_when_banned_token_present` asserts `retry_count == 0 && vocab_warning is True`.
6. **P11 mitigation** — `WORD_LIMIT = 300` module constant + retry loop + sentinel preserves old prompt on exhaustion. Phase 5 monotonic-growth monitor noted below.
7. **P6 num_ctx propagation** — `test_num_ctx_in_every_call` exercises 3 calls, all pass `extra_body={"options": {"num_ctx": config.num_ctx}}`.
8. **Shared SSOT (D-14)** — `BANNED_RUBRIC_VOCAB_TOKENS` in `src/models.py`, imported by `src/optimiser.py` (meta-prompt + scrub) and `tests/test_agent.py` (agent gate).
9. **Backward compat (D-06)** — Phase 3's `results/pre_loop_test.json` round-trips.
10. **Graceful failure** — sentinel on exhaustion, non-raising. Test 3.
11. **≥33 passed** — `uv run pytest -q -m "not integration"` = 33 passed.
12. **No forbidden patterns** — no `response_format=`, no `stream=`, no `instructor`, no `langchain`, no `tenacity`, no `_extract_json`, no `@retry` decorator, no regex word tokenizer. Confirmed by grep acceptance criteria.

## Phase 5 Hand-off Items

These are deliberate deferrals — Phase 4 implements per-iteration enforcement; Phase 5 must add the cross-iteration and call-site layers.

1. **Cross-iteration monotonic-growth monitor for `prompt_word_count`** — D-10 acknowledged that 300 is a loose headroom. Phase 5's loop must compare each iteration's `OptimiserResult.prompt_word_count` against the previous iteration and log/surface monotonic growth as a P11 signal, even when no single iteration exceeds the limit. This is a Phase 5 analysis/logging concern, not a run_optimiser concern.
2. **NDA-absence runtime enforcement at the call site** — OPTM-01 is structurally enforced by Phase 4's type signature (NDA is not a parameter, so it cannot be passed). The Phase 5 main loop must additionally ensure no NDA substring appears in the `system_prompt` being passed in (e.g., defensive assertion or a `# NDA` delimiter check). Phase 4 does not defend against it internally per D-01.
3. **Correlation analysis between `vocab_warning=True` iterations and judgment-score trajectories** — The P5 positive result is the correlation between `vocab_warning=True` appearances in `IterationResult.optimiser_feedback_seen`-adjacent iterations and subsequent judgment-score plateaus. Phase 5's analysis code (or a follow-up analysis script) should compute and report this correlation.
4. **Optional live Ollama smoke test** — Deferred from Phase 4 per `04-RESEARCH.md §Discretion 5`. Phase 5's main-loop live smoke will exercise `run_optimiser` end-to-end against a real judge result, making a standalone optimiser smoke redundant.

## Known Stubs

None. All fields are populated by real call paths; no placeholder values or dead data flows.

## Self-Check: PASSED

- `src/optimiser.py` exists — FOUND
- `tests/test_optimiser.py` exists — FOUND
- `src/models.py` contains `BANNED_RUBRIC_VOCAB_TOKENS` — FOUND (22 tokens, tuple)
- `src/models.py` contains `class OptimiserResult` — FOUND (8 fields + `_check_structural_invariants`)
- `src/models.py::IterationResult` extended with 3 defaulted fields — FOUND
- `tests/test_agent.py` imports `BANNED_RUBRIC_VOCAB_TOKENS as _BANNED_TOKENS` — FOUND
- Commit c8438c5 (Task 1) — FOUND in `git log`
- Commit d5bf8a6 (Task 2) — FOUND in `git log`
- Commit dd1c2a1 (Task 3) — FOUND in `git log`
- `uv run pytest -q -m "not integration"` = 33 passed, 3 deselected — VERIFIED
- `results/pre_loop_test.json` round-trips under extended `IterationResult` — VERIFIED
- `black --check` clean on all 4 touched files — VERIFIED
- All 22 `BANNED_RUBRIC_VOCAB_TOKENS` entries appear quoted in `OPTIMISER_SYSTEM_PROMPT` — VERIFIED
- `run_optimiser` signature = `['system_prompt', 'judge_result']` — VERIFIED
