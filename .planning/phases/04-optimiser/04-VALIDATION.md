---
phase: 4
slug: optimiser
status: planned
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-12
updated: 2026-04-12
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> **Wave 0 infrastructure was fully established by Phase 2** (pytest, integration marker, FakeClient, VALID_JUDGE_JSON, autouse _reset_llm_singleton). Phase 4 adds zero Wave 0 work.
> **Task IDs populated by planner on 2026-04-12 from 04-01-PLAN.md.**

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (inherited) |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` (unchanged) |
| **Quick run command** | `uv run pytest -q -m "not integration"` |
| **Full suite command** | `uv run pytest -q` (model defaults to `gemma4:26b`, no env override needed) |
| **Estimated runtime** | ~0.5s unit only (21 baseline + 12 new Phase 4 tests = 33+); ~3-5 min integration (reuses Phase 2+3 integration tests; Phase 4 adds no new integration tests — deferred to Phase 5 per RESEARCH.md §Discretion 5) |

---

## Sampling Rate

- **After every task commit:** `uv run pytest -q -m "not integration"` — cheap, catches schema extension regressions and optimiser unit logic
- **After every plan wave:** Same unit-only command
- **Before `/gsd-verify-work`:** Full suite with integration — runs Phase 2, 3 integration tests; Phase 4 adds no new integration
- **Max feedback latency:** 15 seconds (unit only)

---

## Per-Task Verification Map

Phase 4 is a single plan (**04-01**) with **3 sequential tasks** in **Wave 1**. All tasks are unit-testable with FakeClient — zero integration dependencies. The optional live optimiser smoke test is deferred to Phase 5 per RESEARCH.md §Discretion 5.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-T1 | 04-01 | 1 | — (schema, MODL-foundation) | T-04-02 (shared vocab source) | `OptimiserResult` validates; `IterationResult` gains 3 defaulted fields without breaking `_check_totals`; `BANNED_RUBRIC_VOCAB_TOKENS` is importable from `src/models.py`; `tests/test_agent.py` refactored to import shared constant; existing 21+ Phase 1-3 tests still pass (D-06 backward-compat) | unit regression | `uv run pytest -q -m "not integration"` returns all pre-existing tests green (≥21 passed, no regressions); `uv run python -c "from src.models import BANNED_RUBRIC_VOCAB_TOKENS, OptimiserResult, IterationResult; assert len(BANNED_RUBRIC_VOCAB_TOKENS) == 22"` exits 0 | ✅ (Phase 2 infra) | ⬜ pending execute |
| 04-01-T2 | 04-01 | 1 | OPTM-01, OPTM-02, OPTM-03 | T-04-01 (NDA structurally absent), T-04-02 (two-layer P8), T-04-04 (bounded retry) | `run_optimiser(system_prompt: str, judge_result: JudgeResult) -> OptimiserResult` — signature excludes NDA structurally; retry loop enforces `WORD_LIMIT=300` with `MAX_RETRIES=3`; sentinel on exhaustion preserves old prompt byte-identical; `_check_banned_vocab` sets `vocab_warning=True` but does NOT retry (P5 detect-don't-prevent); `num_ctx` on every call (P6); non-raising | unit (import + structural) | `uv run python -c "from src.optimiser import run_optimiser, OPTIMISER_SYSTEM_PROMPT, MAX_RETRIES, WORD_LIMIT; import inspect; assert list(inspect.signature(run_optimiser).parameters) == ['system_prompt', 'judge_result']; assert MAX_RETRIES == 3 and WORD_LIMIT == 300"` exits 0 | ⬜ (plan 04-01) | ⬜ pending execute |
| 04-01-T3 | 04-01 | 1 | OPTM-01 (indirect), OPTM-02, OPTM-03 | T-04-01, T-04-02, T-04-03, T-04-04, T-04-05 | 12 FakeClient-backed unit tests cover: happy path (1 call, failed=False), retry recovery (2 calls, retry_count=1), retry exhaustion (3 calls, failed=True, sentinel preserves old prompt), retry message carries observed word count + limit, vocab warning set on contamination with NO retry (P5/D-15), vocab warning false on clean output, unified-diff format (`---`/`+++` headers + `-`/`+` body lines), feedback sort ascending + item_id stripped, all 8 items in user message, OptimiserResult structural invariants (3 ValidationError cases), num_ctx on every call (P6 / 3-call sequence), retry exhaustion logs ERROR at jitc.optimiser | unit (FakeClient) | `uv run pytest -q tests/test_optimiser.py` returns 12 passed; `uv run pytest -q -m "not integration"` returns ≥33 passed (21 baseline + 12 new) with no regressions | ⬜ (plan 04-01) | ⬜ pending execute |

### Requirement Coverage Breakdown

- **OPTM-01** (NDA never passed): Verified structurally by `run_optimiser` type signature (T2 acceptance criteria grep + inspect.signature check) and indirectly by `test_happy_path_returns_optimiser_result` exercising the two-parameter call shape.
- **OPTM-02** (feedback pass-through): Verified by `test_all_eight_feedback_items_included_in_user_message` + `test_feedback_block_sorted_ascending_and_strips_item_ids` + the `OptimiserResult.feedback_seen` field populated in the happy-path test.
- **OPTM-03** (prompt diff stored): Verified by `test_prompt_diff_is_unified_diff_format` (non-empty unified-diff format) + `test_retry_exhaustion_returns_sentinel` (`prompt_diff == ""` on failure).

### Pitfall Coverage Map

| Pitfall | Mitigation Site | Verification Test | Posture |
|---------|-----------------|-------------------|---------|
| **P5** (Goodhart / self-reference collapse) | `_check_banned_vocab` + `vocab_warning=True` — **detection only, no retry, no fail** | `test_vocab_warning_set_when_banned_token_present` asserts `retry_count == 0` AND `failed is False` AND `vocab_warning is True` | **DETECT, DO NOT PREVENT.** The drift IS the expected failure mode for judgment items — the experiment's positive result. Suppressing it would destroy diagnostic signal. |
| **P6** (num_ctx silent truncation) | `extra_body={"options": {"num_ctx": config.num_ctx}}` inside retry-loop body | `test_num_ctx_in_every_call` exercises a 3-call sequence; every call's kwargs checked for extra_body, temperature, model, and absence of response_format/stream | Mitigate — locked at Phase 2 D-04 |
| **P7** (retry loop masks systematic failure) | `MAX_RETRIES=3` hard cap; ERROR log at exhaustion; sentinel return | `test_retry_exhaustion_logs_error_at_jitc_optimiser` asserts ERROR log contains "exhausted" + final word count | Mitigate — bounded, logged, surfaces to Phase 5 via `failed=True` |
| **P8** (rubric vocab contamination) | Two-layer: meta-prompt enumeration (OPTIMISER_SYSTEM_PROMPT) + post-hoc scrub (_check_banned_vocab) | `test_vocab_warning_set_when_banned_token_present` (scrub layer) + shared-source-of-truth constant prevents meta-prompt drift from scrub | Two-layer defence with shared BANNED_RUBRIC_VOCAB_TOKENS constant |
| **P11** (prompt gets longer every iteration) | `WORD_LIMIT=300` + retry loop + sentinel preserves old prompt on failure | `test_happy_path...` + `test_retry_recovers_on_second_attempt` + `test_retry_exhaustion_returns_sentinel` + `test_word_overrun_triggers_retry_with_word_count_in_message` | Per-iteration cap enforced; cross-iteration monotonic-growth monitor deferred to Phase 5 (D-10 tradeoff acknowledgement) |
| **P12** (Pydantic v2 ValidationError covers both JSON and schema) | N/A — optimiser output is plain text, no JSON parsing | N/A | Not applicable to Phase 4 |

### Threat Coverage Map

| Threat ID | Component | Mitigation Site | Verification |
|-----------|-----------|-----------------|--------------|
| **T-04-01** | `run_optimiser` signature — NDA leakage | Type signature excludes NDA parameter; docstring documents contract | T2 grep + inspect.signature verify; T3 `test_happy_path_returns_optimiser_result` exercises two-parameter call |
| **T-04-02** | Rubric vocab leak into `new_system_prompt` (P8/P5) | Meta-prompt ban list + post-hoc scrub; shared BANNED_RUBRIC_VOCAB_TOKENS source of truth | T3 `test_vocab_warning_set_when_banned_token_present`; phase-level shared-source check in `<verification>` section |
| **T-04-03** | Prompt injection via `judge_result.scores[*].feedback` | Accepted risk — no tool access, output is plain string, degraded rewrite caught by word-count/vocab/cross-iteration monitor | No direct test; accepted under same trust model as Phase 2 T-02-J01 |
| **T-04-04** | Unbounded retry / hanging client | MAX_RETRIES=3 hard cap; client timeout inherited; non-raising sentinel | T3 `test_retry_exhaustion_returns_sentinel` + `test_retry_exhaustion_logs_error_at_jitc_optimiser` |
| **T-04-05** | Contaminated `prompt_diff` stored in results | `vocab_warning=True` surfaced prominently in OptimiserResult + WARNING log + Phase 5 IterationResult mirroring | T3 `test_vocab_warning_set_when_banned_token_present` asserts warning log capture |

All threats disposition: **mitigate** (4) + **accept** (1, T-04-03). Severity: all LOW.

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
| Qualitative review that the rewritten prompt still reads as a coherent NDA-review task description after optimisation | P5 + readability | An LLM-generated rewrite can pass word-count + vocab checks but still be incoherent or off-topic. No automated check can verify that. | Deferred to Phase 5's first real iteration. Read the `new_system_prompt` output of iteration 1 and confirm it still instructs "review this NDA and identify issues" in some form. Log result in Phase 5 SUMMARY. |
| Qualitative spot-check that the retry reminder wording produces well-behaved rewrites under word pressure | P11 retry loop effectiveness | A poorly-worded retry message could make the model panic-compress or produce degenerate output | Optional — only if Phase 5 integration smoke exercises the retry path naturally. Skip if the retry path is only exercised by unit tests. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies — 3/3 tasks have automated pytest commands; Task 1 also has a direct python import smoke check
- [x] Sampling continuity: no 3 consecutive tasks without automated verify — every task has a pytest command
- [x] Wave 0 covers all MISSING references → **N/A, Wave 0 empty**
- [x] No watch-mode flags
- [x] Feedback latency < 15s (unit only) — ~0.5s-2s for full unit suite
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ✅ planner (2026-04-12) — task IDs populated from 04-01-PLAN.md, all 3 tasks have automated verify commands, no watch-mode, all thresholds met.
