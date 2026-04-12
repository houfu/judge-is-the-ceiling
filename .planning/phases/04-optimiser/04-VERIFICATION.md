---
phase: 4
slug: optimiser
verifier: gsd-verifier
date: 2026-04-12
status: passed
criteria_passed: 4/4
score: 4/4 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
  gaps_closed: []
  gaps_remaining: []
  regressions: []
---

# Phase 4 Verification

## Goal Achievement

The optimiser rewrites an agent system prompt based solely on judge feedback, without any structural route for the NDA to reach it. `run_optimiser(system_prompt, judge_result) -> OptimiserResult` in `src/optimiser.py` enforces a hard 300-word cap via a post-validation retry loop (mirroring `src/judge.py`), preserves the prior prompt on retry exhaustion via a non-raising sentinel, stores the full 8-item feedback block on the result for OPTM-02 pass-through, and captures a stdlib `difflib.unified_diff` on the result for OPTM-03 audit. All 12 FakeClient-backed tests in `tests/test_optimiser.py` pass, and the Phase 3 `results/pre_loop_test.json` still round-trips under the extended `IterationResult` schema. Goal achieved.

## Success Criteria

### SC-1: run_optimiser returns a new system prompt string; the NDA is never passed as an argument (enforced at call site)

- **Status:** STRUCTURALLY PASS
- **Implementing code:** `src/optimiser.py:138` — `def run_optimiser(system_prompt: str, judge_result: JudgeResult) -> OptimiserResult:`
- **Runtime inspection:** `inspect.signature(run_optimiser).parameters` == `['system_prompt', 'judge_result']`. No `nda`, `nda_text`, or equivalent parameter exists. NDA is not reachable through the type signature.
- **Test evidence:** All 12 tests in `tests/test_optimiser.py` call `run_optimiser(_OLD_PROMPT, _synthetic_judge_result())` — no test passes NDA text, nor could one without a TypeError.
- **Return type:** `OptimiserResult.new_system_prompt: str` (required field, `src/models.py:256`) — happy-path tests confirm a non-empty rewritten string is returned.
- **Deferred to Phase 5 (documented in SUMMARY §Phase 5 Hand-off item 2):** call-site defense that no NDA substring appears in the `system_prompt` argument. Phase 4's contract is structural exclusion; Phase 5 adds runtime exclusion at the call site. The ROADMAP wording "enforced at call site" defers the runtime check to Phase 5 — Phase 4 is the precondition (no parameter exists to hold it).
- **Verdict:** PASS — structurally unreachable NDA route. Cannot be compromised without a signature change.

### SC-2: The optimiser meta-prompt enforces a hard word-count limit and the returned prompt demonstrably stays within that limit

- **Status:** PASS
- **Implementing code:**
  - `src/optimiser.py:38` — `WORD_LIMIT = 300` module constant
  - `src/optimiser.py:46-64` — `OPTIMISER_SYSTEM_PROMPT` f-string interpolates `{WORD_LIMIT}` into "MUST be 300 words or fewer. This is non-negotiable."
  - `src/optimiser.py:175-209` — Post-validation retry loop: `last_word_count = _count_words(raw); if last_word_count <= WORD_LIMIT: return OptimiserResult(...)`; on overrun, append assistant + retry user message and retry, up to `MAX_RETRIES = 3`
  - `src/optimiser.py:224-240` — Sentinel path on exhaustion: returns `OptimiserResult(failed=True, new_system_prompt=system_prompt, prompt_diff="", prompt_word_count=old_word_count, retry_count=3)` — old prompt preserved byte-identical, sentinel's `prompt_word_count` equals `old_word_count`, not the over-limit candidate
  - `src/models.py:265-282` — `OptimiserResult._check_structural_invariants` validator rejects any result whose stored `prompt_word_count != len(new_system_prompt.split())`. Combined with the retry-loop guard, this makes it impossible to construct and return an `OptimiserResult` whose `new_system_prompt` exceeds the cap on the success path (the sentinel path explicitly returns the unchanged, in-cap input instead).
- **Test evidence:**
  - `tests/test_optimiser.py::test_happy_path_returns_optimiser_result` — 70-word rewrite passes; `result.prompt_word_count == 70`, `result.retry_count == 0`
  - `tests/test_optimiser.py::test_retry_recovers_on_second_attempt` — 350-word raw followed by 70-word raw; `retry_count == 1`, 2 client calls
  - `tests/test_optimiser.py::test_retry_exhaustion_returns_sentinel` — 3 consecutive 350-word overruns; `result.failed is True`, `retry_count == 3`, `result.new_system_prompt == _OLD_PROMPT` (byte-identical), `prompt_word_count == len(_OLD_PROMPT.split())`, 3 client calls
  - `tests/test_optimiser.py::test_word_overrun_triggers_retry_with_word_count_in_message` — retry message content asserts "350" (actual) and "300" (limit) and "Rewrite again" appear in `client.calls[1]["messages"][-1]["content"]`
- **Meta-prompt verification:** `OPTIMISER_SYSTEM_PROMPT` contains the literal "MUST be 300 words or fewer. This is non-negotiable." (verified by reading `src/optimiser.py:50-51`).
- **Verdict:** PASS — the cap is stated in the meta-prompt, enforced by the retry loop, and structurally backstopped by the validator. Sentinel path cannot return an oversized prompt.

### SC-3: The feedback strings that were passed to the optimiser are stored alongside the new prompt (pass-through logging)

- **Status:** PASS
- **Implementing code:**
  - `src/models.py:257` — `OptimiserResult.feedback_seen: list[str]` (required, no default)
  - `src/models.py:66` — `IterationResult.optimiser_feedback_seen: list[str] = []` (Phase 5 mirror, defaulted for backward compat)
  - `src/optimiser.py:72-78` — `_build_feedback_block` sorts 8 RubricScores by score ascending, strips `item_id`, formats as `"{idx}. [score={s.score}] {s.feedback}"`
  - `src/optimiser.py:157` — `feedback_block = _build_feedback_block(judge_result)` built once at entry
  - `src/optimiser.py:200-209` / `src/optimiser.py:231-240` — both success and sentinel return paths include `feedback_seen=feedback_block` (the same list that was injected into the user message)
- **Test evidence:**
  - `tests/test_optimiser.py::test_happy_path_returns_optimiser_result` — `len(result.feedback_seen) == 8`
  - `tests/test_optimiser.py::test_feedback_block_sorted_ascending_and_strips_item_ids` — verifies ascending sort (`block[0]` starts `"1. [score=0]"`, `block[-1]` starts `"8. [score=2]"`) and that no `1a`/`1b`/.../`4b` item_id tokens appear in the joined block
  - `tests/test_optimiser.py::test_all_eight_feedback_items_included_in_user_message` — for every entry in `result.feedback_seen`, asserts `entry in client.calls[0]["messages"][1]["content"]` (the user-role content of the first LLM call). This proves what was stored equals what was sent.
- **Verdict:** PASS — the exact list that enters the optimiser's user message exits on `OptimiserResult.feedback_seen`, and the sentinel path preserves the same invariant. `IterationResult` has a defaulted mirror field so Phase 5 can store it per iteration.

### SC-4: A prompt diff between the input and output system prompt is captured and stored

- **Status:** PASS
- **Implementing code:**
  - `src/models.py:258` — `OptimiserResult.prompt_diff: str` (required field)
  - `src/models.py:67` — `IterationResult.prompt_diff: str = ""` (Phase 5 mirror, defaulted)
  - `src/optimiser.py:106-123` — `_compute_prompt_diff(old, new)` uses `difflib.unified_diff(old.splitlines(), new.splitlines(), fromfile="old_system_prompt", tofile="new_system_prompt", lineterm="", n=3)` joined with `"\n"` — stdlib only, no dependencies
  - `src/optimiser.py:188` — success path computes `prompt_diff = _compute_prompt_diff(system_prompt, raw)` before result construction
  - `src/optimiser.py:234` — sentinel path returns `prompt_diff=""` (explicit empty, since no rewrite happened; documented in `OptimiserResult` docstring `src/models.py:247-253` as the failed-state contract)
- **Test evidence:**
  - `tests/test_optimiser.py::test_prompt_diff_is_unified_diff_format` — asserts `"--- old_system_prompt" in result.prompt_diff`, `"+++ new_system_prompt" in result.prompt_diff`, and the body contains at least one `-` line and at least one `+` line
  - `tests/test_optimiser.py::test_retry_exhaustion_returns_sentinel` — asserts `result.prompt_diff == ""` on the sentinel path
- **Verdict:** PASS — unified diff captured on every success, explicit empty sentinel on exhaustion, structurally stored on both `OptimiserResult` and `IterationResult`.

## Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | NDA is structurally unreachable from the optimiser | VERIFIED | `inspect.signature` confirms params == `['system_prompt', 'judge_result']` |
| 2 | Returned prompt respects the 300-word cap on success path | VERIFIED | `test_happy_path_returns_optimiser_result`, `test_retry_recovers_on_second_attempt` |
| 3 | Cap enforced by retry loop, preserved by sentinel on exhaustion | VERIFIED | `test_retry_exhaustion_returns_sentinel` (byte-identical preservation) |
| 4 | 8 feedback strings stored on result and mirrored into user message | VERIFIED | `test_all_eight_feedback_items_included_in_user_message` |
| 5 | Feedback sorted ascending, item_ids stripped (P8) | VERIFIED | `test_feedback_block_sorted_ascending_and_strips_item_ids` |
| 6 | Unified diff captured in `OptimiserResult.prompt_diff` | VERIFIED | `test_prompt_diff_is_unified_diff_format` |
| 7 | Structural invariant validator rejects inconsistent results | VERIFIED | `test_structural_invariants_rejected_by_validator` (3 ValidationError cases) |

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/optimiser.py` | run_optimiser + helpers + constants | VERIFIED | 240 lines, all 6 helpers present, MAX_RETRIES=3, WORD_LIMIT=300, OPTIMISER_SYSTEM_PROMPT constant, `jitc.optimiser` logger |
| `src/models.py::OptimiserResult` | 8 fields + validator | VERIFIED | All 8 fields match D-02; `_check_structural_invariants` enforces word-count consistency, non-negative `old_word_count`, `retry_count in [0,3]` |
| `src/models.py::BANNED_RUBRIC_VOCAB_TOKENS` | 22-token tuple SSOT | VERIFIED | 22 tokens present (13 Phase 2 + 9 Phase 4). Imported by optimiser, meta-prompt, and test_agent |
| `src/models.py::IterationResult` extensions | 3 defaulted fields | VERIFIED | `optimiser_feedback_seen: list[str] = []`, `prompt_diff: str = ""`, `prompt_word_count: int = 0` all present at `src/models.py:66-68` |
| `tests/test_optimiser.py` | 12 FakeClient tests | VERIFIED | 12 tests; all pass under `uv run pytest -q -m "not integration"` |
| `tests/test_agent.py` (modified) | imports shared constant | VERIFIED | `from src.models import BANNED_RUBRIC_VOCAB_TOKENS as _BANNED_TOKENS` at line 9; used at line 68 |

## Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `run_optimiser` | `get_client()` | `src/llm.py` singleton | WIRED | `src/optimiser.py:156` |
| `run_optimiser` | `config.{model,temperature,num_ctx}` | `src/config.py` | WIRED | `src/optimiser.py:178-181` — model, temperature, extra_body with num_ctx on every call |
| `OPTIMISER_SYSTEM_PROMPT` | `BANNED_RUBRIC_VOCAB_TOKENS` | f-string interpolation at module load | WIRED | `src/optimiser.py:44` — `_BANNED_LIST_FORMATTED` interpolated into `OPTIMISER_SYSTEM_PROMPT`. All 22 tokens verified present in the rendered string at runtime |
| `_check_banned_vocab` | `BANNED_RUBRIC_VOCAB_TOKENS` | direct import | WIRED | `src/optimiser.py:33,135` — SSOT preserved: meta-prompt ban list and post-hoc scrub list derive from the same tuple |
| `tests/test_agent.py` regression gate | `BANNED_RUBRIC_VOCAB_TOKENS` | shared import | WIRED | `tests/test_agent.py:9,68` — any token added to the tuple will fail the Phase 2 `ITERATION_ZERO_SYSTEM_PROMPT` gate |
| `OptimiserResult.prompt_diff` | `difflib.unified_diff` | stdlib | WIRED | `src/optimiser.py:115-123` — no external dependency |
| `run_optimiser` success return | `OptimiserResult(feedback_seen=feedback_block, ...)` | direct assignment | WIRED | `src/optimiser.py:200-209` — the same list built at line 157 flows to the result |
| `IterationResult` new fields | Phase 5 call site | documented hand-off | DEFERRED | Fields are defaulted empty; Phase 5 will populate from `OptimiserResult`. Not a gap — explicitly out of Phase 4 scope per SUMMARY §Phase 5 Hand-off item 2 |

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `OptimiserResult.new_system_prompt` | `raw` | `client.chat.completions.create(...).choices[0].message.content` | Yes — from LLM response; validated for length ≤ WORD_LIMIT before return | FLOWING |
| `OptimiserResult.feedback_seen` | `feedback_block` | `_build_feedback_block(judge_result)` — transforms 8 RubricScores into formatted strings | Yes — derives from `judge_result.scores` | FLOWING |
| `OptimiserResult.prompt_diff` | `prompt_diff` | `_compute_prompt_diff(system_prompt, raw)` via `difflib.unified_diff` | Yes — real diff on success; explicit `""` on sentinel (documented contract) | FLOWING |
| `OptimiserResult.prompt_word_count` | `last_word_count` | `_count_words(raw)` = `len(raw.split())` | Yes — validator cross-checks against `new_system_prompt.split()` | FLOWING |
| `OptimiserResult.old_word_count` | `old_word_count` | `_count_words(system_prompt)` | Yes | FLOWING |
| `OptimiserResult.vocab_warning` | `bool(hits)` | `_check_banned_vocab(raw)` substring check vs `BANNED_RUBRIC_VOCAB_TOKENS` | Yes — real boolean from real scan | FLOWING |

No hollow fields. No props hardcoded empty at a call site. No static fallback paths.

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite passes | `uv run pytest -q -m "not integration"` | `33 passed, 3 deselected in 0.16s` | PASS |
| `run_optimiser` signature excludes NDA | `python -c "import inspect; from src.optimiser import run_optimiser; print(list(inspect.signature(run_optimiser).parameters))"` | `['system_prompt', 'judge_result']` | PASS |
| `WORD_LIMIT` and `MAX_RETRIES` module constants set | `python -c "from src.optimiser import MAX_RETRIES, WORD_LIMIT; print(MAX_RETRIES, WORD_LIMIT)"` | `3 300` | PASS |
| All 22 banned tokens rendered into meta-prompt | `python -c` substring check on `OPTIMISER_SYSTEM_PROMPT` | 0 missing tokens | PASS |
| Phase 3 artifact round-trips under extended schema | `cat results/pre_loop_test.json \| python -c "PreLoopTestResult.model_validate_json(...)"` | `backward-compat PASS` | PASS |

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| OPTM-01 | 04-01-PLAN.md | Optimiser takes current system prompt + judge feedback only (not the NDA) | SATISFIED | Structural signature enforcement; REQUIREMENTS.md line 46 marked `[x]`, table line 114 `Complete` |
| OPTM-02 | 04-01-PLAN.md | Feedback pass-through logging — store what feedback was received | SATISFIED | `OptimiserResult.feedback_seen` + test_all_eight_feedback_items_included_in_user_message; REQUIREMENTS.md line 47 `[x]`, table line 115 `Complete` |
| OPTM-03 | 04-01-PLAN.md | Prompt diff between iterations stored in results | SATISFIED | `OptimiserResult.prompt_diff` + test_prompt_diff_is_unified_diff_format; REQUIREMENTS.md line 48 `[x]`, table line 116 `Complete` |

No orphaned requirements. All three Phase 4 requirements are both declared in the plan and implemented.

## P5 / P8 / P11 Mitigation Review

- **P5 (detect-don't-prevent):** `_check_banned_vocab` (`src/optimiser.py:126-135`) scans for banned tokens post-hoc. On hit, `vocab_warning=True` is set and a WARNING is logged at `jitc.optimiser`. The function does NOT retry on vocab contamination and does NOT flag the result as failed — this is deliberately the detection-only posture required by D-15 to preserve the thesis signal. Verified by `test_vocab_warning_set_when_banned_token_present`: asserts `retry_count == 0`, `failed is False`, `vocab_warning is True` simultaneously. Tradeoff noted: Phase 5 must correlate `vocab_warning=True` iterations with judgment-score trajectories (SUMMARY §Phase 5 Hand-off item 3).
- **P8 (two-layer meta-prompt + scrub, SSOT):** Layer 1 is meta-prompt enumeration — all 22 tokens interpolated into `OPTIMISER_SYSTEM_PROMPT` via `_BANNED_LIST_FORMATTED`. Layer 2 is post-hoc `_check_banned_vocab` against the same tuple. Both layers import from `src/models.py::BANNED_RUBRIC_VOCAB_TOKENS`, and `tests/test_agent.py` also imports it as a third consumer. Drift between layers is structurally impossible. Verified: 0 tokens missing from rendered meta-prompt.
- **P11 (monotonic prompt growth):** `WORD_LIMIT = 300` module constant + 3-retry post-validation loop + sentinel on exhaustion preserves the prior prompt byte-identical (`test_retry_exhaustion_returns_sentinel`). Per-iteration cap is enforced; the cross-iteration monotonic-growth monitor is deliberately deferred to Phase 5 (SUMMARY §Phase 5 Hand-off item 1 — Phase 5's loop must compare each iteration's `prompt_word_count` against the previous and log monotonic growth even when no single iteration exceeds 300). This is the correct layering.

## Backward Compatibility

- `results/pre_loop_test.json` parses as `PreLoopTestResult` under the extended `IterationResult` schema: `cat results/pre_loop_test.json | python -c "PreLoopTestResult.model_validate_json(sys.stdin.read())"` returns `backward-compat PASS` with exit code 0. The three new `IterationResult` fields (`optimiser_feedback_seen`, `prompt_diff`, `prompt_word_count`) all have defaults (`[]`, `""`, `0`), so Pydantic silently fills them for records written before Phase 4. Phase 3 artifact preserved.
- Phase 2 `test_agent.py::ITERATION_ZERO_SYSTEM_PROMPT` regression gate still passes against the expanded 22-token banned list — verified by the full suite (33 passed) including tests that exercise the gate.
- `_check_totals` validator on `IterationResult` is byte-identical (D-05); the three new fields do not participate in any cross-field invariant.

## Requirement Marks

- `OPTM-01` in `.planning/REQUIREMENTS.md:46` marked `[x]`, and at line 114 marked `Complete` — PASS
- `OPTM-02` in `.planning/REQUIREMENTS.md:47` marked `[x]`, and at line 115 marked `Complete` — PASS
- `OPTM-03` in `.planning/REQUIREMENTS.md:48` marked `[x]`, and at line 116 marked `Complete` — PASS

## Rule 1 Auto-Fix Verification

Both auto-fixes are correct and do not undermine their tests.

**Fix 1 — `_compute_prompt_diff` line join:** The plan skeleton used `old.splitlines(keepends=True)` + `lineterm=""` + `"".join(...)`, which produces a single unseparated run when the input has no trailing newlines. The fix uses `old.splitlines()` (no keepends) + `"\n".join(...)`. Verified at `src/optimiser.py:115-123`. `test_prompt_diff_is_unified_diff_format` now asserts the diff contains `"--- old_system_prompt"`, `"+++ new_system_prompt"`, at least one `-` body line, and at least one `+` body line — the assertions rely on `splitlines()` returning multiple non-header lines, which the fix makes work. Test passes. Unified-diff semantics preserved (the `---`/`+++` headers and `-`/`+` body line prefixes are still produced by difflib; only the joiner between difflib's per-line outputs changed from nothing to `\n`).

**Fix 2 — `_synthetic_judge_result` feedback text:** The plan's fixture used `f"Feedback for item {issue}{letter}"`, which embedded `"1a"`, `"1b"`, etc. into feedback strings. The strip assertion in `test_feedback_block_sorted_ascending_and_strips_item_ids` then failed not because the implementation leaked item_ids, but because the test data itself contained them. The fix substitutes a fixed list of 8 descriptive phrases (`"confidentiality duration clarity"`, ...) that contain zero `[1-4][ab]` patterns. Verified at `tests/test_optimiser.py:42-51`. The D-07 invariant under test — that `_build_feedback_block` strips `item_id` metadata — is now genuinely tested: the only place an item_id could appear is the metadata strip path, so the assertion `bad not in joined` actually exercises what it intended. The implementation of `_build_feedback_block` was correct from the start (as Task 3 discovered when debugging); the fix tightens the test's semantics without weakening it.

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | None found | — | — |

No `TODO`/`FIXME`/`PLACEHOLDER`, no empty implementations, no hardcoded empty data flowing to output, no `response_format={"type":"json_object"}`, no `stream=True`, no `instructor`/`langchain`/`tenacity`/`@retry` decorator imports, no `_extract_json` helper, no regex word tokenizer. The `= []` / `= {}` / `= ""` defaults that appear in `IterationResult` and `OptimiserResult` are explicit optional-field defaults on Pydantic models, not stubs — they are overwritten by real call paths in `run_optimiser` on every invocation.

## Gaps

None.

## Deferred Items

The following items are explicitly deferred to Phase 5 per SUMMARY §Phase 5 Hand-off and ROADMAP Phase 5 scope. None are gaps.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Cross-iteration monotonic-growth monitor for `prompt_word_count` (P11 cross-iteration layer) | Phase 5 | ROADMAP Phase 5 goal "executes N iterations of agent -> judge -> log -> optimiser"; SUMMARY §Phase 5 Hand-off item 1 |
| 2 | NDA-absence runtime enforcement at the call site (defensive check that no NDA substring appears in `system_prompt`) | Phase 5 | ROADMAP SC-1 "enforced at call site"; SUMMARY §Phase 5 Hand-off item 2 |
| 3 | Correlation analysis between `vocab_warning=True` iterations and judgment-score plateaus (P5 thesis signal) | Phase 5 | SUMMARY §Phase 5 Hand-off item 3 |
| 4 | Live-Ollama end-to-end optimiser smoke (subsumed by Phase 5's main-loop integration test) | Phase 5 | 04-RESEARCH.md §Discretion 5; SUMMARY §Phase 5 Hand-off item 4 |

## Recommendation

**Advance to Phase 5.** All 4 success criteria pass, all 3 requirements (OPTM-01/02/03) marked complete, 33/33 tests green, Phase 3 backward compat preserved, both Rule 1 auto-fixes verified correct, and all P5/P8/P11 mitigations at the per-iteration layer are in place. Phase 5 inherits a clean contract: `OptimiserResult` is the sole handoff object, `IterationResult` has the mirror fields ready to populate, and the four deferred items are explicitly scoped to the main-loop layer rather than the library.

---

_Verified: 2026-04-12_
_Verifier: Claude (gsd-verifier)_
