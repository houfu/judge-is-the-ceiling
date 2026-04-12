---
phase: 04-optimiser
reviewer: claude (gsd-code-reviewer)
date: 2026-04-11
status: clean
depth: standard
findings_count:
  critical: 0
  warning: 0
  info: 3
  total: 3
files_reviewed_list:
  - src/models.py
  - src/optimiser.py
  - tests/test_optimiser.py
  - tests/test_agent.py
---

## Summary

Phase 4 ships the optimiser: a pure, non-raising library function `run_optimiser(system_prompt, judge_result) -> OptimiserResult` that rewrites the agent's system prompt from judge feedback inside a 3-retry post-validation loop, plus schema extensions and 12 FakeClient-backed unit tests. OPTM-01 is structurally enforced (NDA is not a parameter); OPTM-02/03 are carried in `OptimiserResult.feedback_seen` / `prompt_diff`; and P5/P8 detection fires via the post-hoc `_check_banned_vocab` scrub without retrying or failing.

**All 15 decisions (D-01..D-15) are implemented correctly at the sites the Summary claims.** Pitfall mitigations P5, P8, and P11 are present and demonstrably exercised by the test suite. Backward compatibility with Phase 3's `results/pre_loop_test.json` was verified live via `PreLoopTestResult.model_validate(...)` — it still parses cleanly, `decision="go"`, with defaulted new fields on each `IterationResult`.

Both Rule 1 auto-fixes recorded in `04-01-SUMMARY.md` were correct and improved the codebase: the `_compute_prompt_diff` fix produces a genuinely valid multi-line unified diff (verified by running the function with the same inputs the test uses), and the `_synthetic_judge_result` rewrite tightened the D-07 item_id-strip assertion to actually test the thing it claims to test (see dedicated section below).

Only three INFO items surfaced: a documented-but-worth-highlighting substring-matching sensitivity in the scrub, a minor test hygiene nit, and a log-level sanity observation. No Critical or Warning findings.

The implementation mirrors Phase 2's `run_judge` retry skeleton faithfully, including the `num_ctx` P6 guard on every call, None-content guard (`response.choices[0].message.content or ""`), deep-copied kwargs capture in the FakeClient fixture (so multi-call retry tests don't alias live `messages` lists), and the non-raising sentinel contract. Black-clean; imports well-organised; type hints present on all helpers; docstrings on every non-trivial function.

**Verification performed:**
- `uv run pytest tests/test_optimiser.py -q` → 12 passed in 0.14s.
- Live reproduction of `_compute_prompt_diff(old, new)` with the same single-line inputs used by `test_prompt_diff_is_unified_diff_format` confirms the output is a valid, newline-separated unified diff with headers, hunk, `-` line, and `+` line — readable by any unified-diff consumer.
- Live `PreLoopTestResult.model_validate(json.load(open('results/pre_loop_test.json')))` round-trips successfully under the extended `IterationResult` schema. Decision remains `"go"`, and each nested `IterationResult` carries the three new fields at their defaults (`[]`, `""`, `0`).
- `_check_banned_vocab` applied to both the "clean" and "contaminated" fixture strings behaves as the tests claim (contaminated → `['rubric']`; clean → `[]`).
- `OptimiserResult._check_structural_invariants` walked through all three failing constructions in test 10 — each raises at the expected check (word-count mismatch, negative `old_word_count`, `retry_count > 3`).

## Findings

### IN-01: `_check_banned_vocab` substring matching can produce false positives on `1a`..`4b`

**File:** `/Users/houfu/Projects/judge-is-the-ceiling/src/optimiser.py:126-135`
**Severity:** Info
**Issue:** The scrub does `tok in lowered` for every banned token. Most tokens are long enough that substring matching is safe, but the rubric-id tokens `"1a"`, `"1b"`, `"2a"`, `"2b"`, `"3a"`, `"3b"`, `"4a"`, `"4b"` are only two characters and can match unrelated text. Reproduced live:

```python
text = "version 2a1 of the draft has a 4a score"
# hits -> ['score', '2a', '4a']
```

Per D-15 this only raises a warning — it doesn't retry or fail — so the downside is a small rate of spurious `vocab_warning=True` in Phase 5's trajectory logs, which could muddy the P5 correlation analysis called out in the Phase 5 hand-off items. The design intent (detect, don't prevent) means this is tolerable, and tightening matching risks missing the real drift signals it's designed to catch.

**Fix hint:** Optional — if false positives become noise in Phase 5's analysis, consider word-boundary matching for the short 2-char rubric-id tokens only (e.g., `re.search(r"\b" + re.escape(tok) + r"\b", lowered)` for tokens whose length is `< 4`). Do not word-boundary the longer semantic tokens (`"rubric"`, `"score"`, etc.) — substring matching there is load-bearing and catches morphological variants (`"rubric"` in `"rubrics"`, `"score"` in `"scoring"`). Leaving as-is is also acceptable; note this as a Phase 5 analysis caveat.

### IN-02: `test_vocab_warning_false_on_clean_output` discards the fake_client handle without asserting call count

**File:** `/Users/houfu/Projects/judge-is-the-ceiling/tests/test_optimiser.py:195-206`
**Severity:** Info
**Issue:** The test calls `fake_client([clean])` without binding the result and asserts only `result.vocab_warning is False`. The fixture monkeypatches `src.llm._client`, so the test functionally works. However, it misses a cheap opportunity to assert `len(client.calls) == 1` and `result.failed is False`, both of which would guard against future refactors that accidentally cause the "clean" path to spin extra retries or flip the sentinel.

**Fix hint:**
```python
def test_vocab_warning_false_on_clean_output(fake_client):
    from src.optimiser import run_optimiser

    clean = (
        "Read the confidentiality agreement carefully. "
        "Identify clauses that may be unfair. Note duration and scope. "
        + " ".join(["term"] * 60)
    )
    client = fake_client([clean])
    result = run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    assert result.vocab_warning is False
    assert result.failed is False
    assert result.retry_count == 0
    assert len(client.calls) == 1
```

### IN-03: `logger.info` on every attempt of the retry loop may double-log success

**File:** `/Users/houfu/Projects/judge-is-the-ceiling/src/optimiser.py:176, 194-199`
**Severity:** Info
**Issue:** `run_optimiser` emits `logger.info("optimiser attempt %d/%d", attempt, MAX_RETRIES)` on every attempt AND `logger.info("optimiser success: ...")` on the winning attempt. This is fine for observability, but on the happy path this produces three log records per call (entry banner, attempt 1, success) where two would suffice. Phase 5's main loop will run this repeatedly and stdout/log volume may become noisy.

**Fix hint:** Leave as-is unless Phase 5 log volume becomes a concern. If pruning is desired, drop the per-attempt INFO and keep only the outer `optimiser call:` and `optimiser success:` lines (and the WARNING/ERROR paths unchanged). Non-blocking.

## Decision Compliance Matrix

| Decision | Requirement | Implementation Site | Verified |
|----------|-------------|---------------------|----------|
| D-01 | Signature excludes NDA, returns OptimiserResult | `src/optimiser.py:138` `def run_optimiser(system_prompt: str, judge_result: JudgeResult) -> OptimiserResult` | Yes — only two params |
| D-02 | `OptimiserResult` with 8 fields | `src/models.py:239-263` | Yes — 8 fields as spec'd |
| D-03 | `@model_validator` enforces structural invariants | `src/models.py:265-282` `_check_structural_invariants` | Yes — test 10 exercises all 3 failing cases |
| D-04 | Extend `IterationResult` with 3 defaulted fields | `src/models.py:66-68` | Yes — `optimiser_feedback_seen=[]`, `prompt_diff=""`, `prompt_word_count=0` |
| D-05 | `_check_totals` unchanged | `src/models.py:70-94` — byte-identical to Phase 3 | Yes — no new-field participation |
| D-06 | Backward compat with Phase 3 JSON | Defaults on new fields | Yes — live `PreLoopTestResult.model_validate(...)` on `results/pre_loop_test.json` returns `decision="go"` |
| D-07 | Feedback sorted ascending, item_id stripped | `src/optimiser.py:72-78` `_build_feedback_block` | Yes — test 8 with override scores `[2,0,1,2,0,1,2,0]` asserts first/last and banned-id tokens absent |
| D-08 | User message layout (fenced old prompt + numbered feedback + instruction) | `src/optimiser.py:81-94` `_build_user_message` | Yes — test 9 substring-matches all 8 entries in `client.calls[0]["messages"][1]["content"]` |
| D-09 | Meta-prompt enforces limit + banned vocab + no preamble | `src/optimiser.py:46-64` `OPTIMISER_SYSTEM_PROMPT` with `_BANNED_LIST_FORMATTED` interpolated from `BANNED_RUBRIC_VOCAB_TOKENS` at module load | Yes — single source of truth, cannot drift |
| D-10 | WORD_LIMIT = 300 | `src/optimiser.py:38` `WORD_LIMIT = 300` | Yes — module constant |
| D-11 | Retry loop + non-raising sentinel preserving old prompt byte-identical | `src/optimiser.py:175-240` — for-loop, retry-correction messages, exhaustion path returns `new_system_prompt=system_prompt`, `prompt_diff=""`, `retry_count=MAX_RETRIES`, `failed=True` | Yes — test 3 asserts `result.new_system_prompt == _OLD_PROMPT` and `prompt_diff == ""` |
| D-12 | Logger `jitc.optimiser` with INFO/WARNING/ERROR | `src/optimiser.py:35, 161, 176, 192, 212, 225` | Yes — tests 5 and 12 both use `caplog.at_level(..., logger="jitc.optimiser")` |
| D-13 | `prompt_diff` via `difflib.unified_diff` (stdlib only) | `src/optimiser.py:106-123` `_compute_prompt_diff` | Yes — test 7 asserts headers + `-`/`+` body lines |
| D-14 | Post-hoc case-insensitive scrub reusing shared `BANNED_RUBRIC_VOCAB_TOKENS` | `src/optimiser.py:126-135` `_check_banned_vocab` — `lowered = prompt.lower()` and iterates `BANNED_RUBRIC_VOCAB_TOKENS` from `src.models` | Yes — same import as `OPTIMISER_SYSTEM_PROMPT` interpolation and `tests/test_agent.py` regression gate |
| D-15 | Detect don't prevent — WARNING + `vocab_warning=True`, NO retry, NO failure | `src/optimiser.py:189-209` — scrub runs INSIDE the success branch, returns immediately after WARNING | Yes — test 5 asserts `retry_count == 0`, `failed is False`, `vocab_warning is True`, `len(client.calls) == 1` |

All 15 decisions implemented at the sites and in the semantics specified. No deviations.

## Pitfall Verification Matrix

| Pitfall | Mitigation Required | Implementation Site | Test Coverage |
|---------|---------------------|---------------------|---------------|
| **P5** (Goodhart's Law — the thesis-preserving pitfall) | Detection only — do not retry or fail on vocab drift | `src/optimiser.py:189-198` — scrub runs AFTER the word-count success check; WARNING log; `vocab_warning=True`; returns on the SAME attempt without re-entering the retry loop | `test_vocab_warning_set_when_banned_token_present` (test 5): asserts `retry_count == 0`, `failed is False`, `vocab_warning is True`, `len(client.calls) == 1`. This test is load-bearing for the thesis — if it were accidentally loosened to allow retry on vocab hits, the P5 detection signal would be silently suppressed. |
| **P8** (rubric vocabulary contaminating the agent prompt) | Two-layer defense: (1) meta-prompt instructs the optimiser to avoid the banned list; (2) post-hoc scrub detects violations | Layer 1: `OPTIMISER_SYSTEM_PROMPT` (`src/optimiser.py:46-64`) interpolates `_BANNED_LIST_FORMATTED` at module load from `BANNED_RUBRIC_VOCAB_TOKENS`. Layer 2: `_check_banned_vocab` at `src/optimiser.py:126-135` imports the same tuple. Drift is structurally impossible — both layers reference the single source of truth in `src/models.py`. | `test_vocab_warning_set_when_banned_token_present` (test 5) and `test_vocab_warning_false_on_clean_output` (test 6). Phase 2's `test_prompt_scrubbed_of_rubric_vocab` (`tests/test_agent.py:60`) now imports `BANNED_RUBRIC_VOCAB_TOKENS` from `src.models`, proving the refactor did not break the Phase 2 gate. |
| **P11** (prompt grows monotonically across iterations) | Hard 300-word cap per iteration, enforced via 3-retry post-validation loop, sentinel preserves old prompt on exhaustion (so a pathologically-verbose optimiser cannot force growth by default) | `src/optimiser.py:175-240` — retry loop, `_build_retry_message` correction turn, exhaustion sentinel | `test_retry_recovers_on_second_attempt` (test 2): 350→70 transition with `retry_count == 1`. `test_retry_exhaustion_returns_sentinel` (test 3): all-350 → `failed=True`, byte-identical old prompt preserved, `prompt_diff == ""`, `prompt_word_count == len(_OLD_PROMPT.split())`. `test_word_overrun_triggers_retry_with_word_count_in_message` (test 4): confirms the 350 observation is surfaced to the optimiser in the correction turn. |

Per-iteration P11 mitigation is sound. The cross-iteration monotonic-growth monitor is correctly deferred to Phase 5 per the hand-off items in `04-01-SUMMARY.md`.

**Trust assumptions (T-04-01..T-04-05):**
- T-04-01 (NDA-in-system-prompt): structurally unreachable via the type signature — `run_optimiser` has no NDA parameter. Runtime assertion correctly deferred to Phase 5 call site.
- T-04-02 (judge_result is trusted): upstream validation by `run_judge` Pydantic schema, accepted.
- T-04-03 (bounded retry): MAX_RETRIES=3, sentinel on exhaustion, non-raising. Network-unbounded but turn-count-bounded.
- T-04-04 (file I/O): none. `run_optimiser` does not touch the filesystem.
- T-04-05 (network): exactly one `chat.completions.create` per attempt, up to 3 attempts per call, no fan-out. Bounded.

## Rule 1 Auto-Fix Review

Phase 4 Task 3 recorded two Rule 1 (bug-discovered-during-implementation) auto-fixes. Both were evaluated against their stated intent:

### Fix 1: `_compute_prompt_diff` — `splitlines(keepends=True)` + `"".join` → `splitlines()` + `"\n".join`

**Status:** Correct fix. Verified live.

**Root cause (as documented in `04-01-SUMMARY.md`):** The RESEARCH skeleton used `old.splitlines(keepends=True)` with `lineterm=""` and `"".join(...)`. For a single-line input without a trailing newline, `splitlines(keepends=True)` returns a single element with no line terminator; `lineterm=""` tells `difflib.unified_diff` to add no terminator either; and `"".join(...)` concatenates everything into a single unseparated string. The resulting "diff" cannot be split by `splitlines()` and cannot be read by a human or any downstream consumer.

**Verification:** I ran the current implementation with the same single-line inputs that `test_prompt_diff_is_unified_diff_format` uses and observed the raw bytes of the returned string:

```
--- old_system_prompt\n+++ new_system_prompt\n@@ -1 +1 @@\n-You are reviewing ...\n+Completely different content. alt alt ...
```

This is a genuinely valid unified diff: two file headers, one hunk header, one `-` line, one `+` line, each separated by a single `\n`. It round-trips through `.splitlines()` as five elements. Any consumer that grep's or line-splits the diff (including Phase 5's JSON serializer and a human reader) will work.

**Additional consideration evaluated:** Using `splitlines()` (no keepends) with `lineterm=""` means the diff body lines will never carry a trailing newline. This is correct for `"\n".join` — it gives exactly one newline between each line and none at the end. Alternative `"\n".join(old.splitlines(keepends=True))` would duplicate newlines in multi-line inputs. The chosen formulation is the right one.

**Side-effect check:** The fix does not affect the `fromfile` or `tofile` header labels, the `n=3` context-line count, or any consumer of `prompt_diff` elsewhere. The docstring correctly explains the rationale, preventing future regressions. No downside observed.

### Fix 2: `_synthetic_judge_result` feedback text rewrite — item-id substrings → descriptive phrases

**Status:** Correct fix. Does NOT undermine the D-07 strip assertion — it strengthens it.

**Root cause:** The RESEARCH skeleton built feedback entries as `f"Feedback for item {issue}{letter}."`. The `_build_feedback_block` implementation correctly strips `item_id` *metadata* (i.e., it does not write `f"{item_id}. ..."` into the output) and formats as `f"{idx}. [score={s.score}] {s.feedback}"`. But the feedback *text* itself contained the substrings `"1a"`, `"1b"`, etc. The test then asserted `"1a" not in joined` and failed — not because the strip logic was wrong, but because the fixture was carrying contraband.

**Why the fix strengthens the test:** The D-07 invariant is "the optimiser never sees rubric vocabulary including item_ids as metadata." The original fixture could only have passed if `_build_feedback_block` scrubbed arbitrary substrings from feedback text — which is NOT what D-07 asks for and would be a semantically different (and worse) contract. The fixed fixture isolates the test to what `_build_feedback_block` actually does: it does not prepend/include `item_id` as metadata. The descriptive replacements (`"confidentiality duration clarity"`, etc.) are free of any `[0-9][a-b]` patterns, so the assertion `bad not in joined` now cleanly proves the metadata-strip claim.

**Verification:** Walked through `test_feedback_block_sorted_ascending_and_strips_item_ids` by hand with the current fixture:
- Scores `[2, 0, 1, 2, 0, 1, 2, 0]`, sorted ascending → entries `(score=0, idx=1..3)`, `(score=1, idx=4..5)`, `(score=2, idx=6..8)`.
- First entry has `[score=0]`, last has `[score=2]` — matches the `startswith` assertions.
- The joined string contains substrings like `"confidentiality duration clarity"`, `"duration risk judgment text"`, etc. None contain `"1a".."4b"` as substrings. The `bad not in joined` loop passes only because `_build_feedback_block` correctly omits `s.item_id` from the format string.

**Does the docstring overstate the rationale?** The fixture docstring (`tests/test_optimiser.py:33-36`) explains the fix inline — "feedback text is deliberately free of item-id tokens ... so that the item-id strip assertion ... tests the `_build_feedback_block` behaviour (stripping metadata) rather than accidentally passing because the feedback text has no item ids to begin with." This is the correct framing: the test *does* pass because the feedback text has no item ids, BUT that is precisely what lets the test cleanly isolate metadata-strip semantics. If a future maintainer adds contraband back into the fixture and the test breaks, the docstring tells them why.

Both auto-fixes are correct, documented, and produce provably better code than the skeleton. No regression risk introduced.

## REVIEW CLEAN

All 15 decisions implemented at the documented sites. P5/P8/P11 mitigations present and exercised. Backward compat with Phase 3 verified live. Both Rule 1 auto-fixes correct. No Critical or Warning findings — 3 Info items are non-blocking observations for Phase 5 consideration.

---

_Reviewed: 2026-04-11_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
