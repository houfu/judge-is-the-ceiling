# Phase 4: Optimiser - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Build `src/optimiser.py` — a library function `run_optimiser(system_prompt: str, judge_result: JudgeResult) -> OptimiserResult` that rewrites the agent's system prompt based on judge feedback, without ever seeing the NDA. Enforces a hard 300-word limit on the rewritten prompt via post-validation + retry. Captures feedback pass-through logging and a unified-diff view of the prompt rewrite so Phase 5's main loop can record OPTM-02 / OPTM-03 evidence per iteration.

**In scope:** The library function, a new `OptimiserResult` Pydantic model, a schema extension to `IterationResult` (three new fields with defaults), the optimiser's meta-prompt (system message + anti-P8/P5 instructions + schema hint), a post-validation retry loop for the word-count limit, a post-hoc P8 vocab-warning scrub, a FakeClient-backed pytest unit test suite, and an optional live-Ollama integration smoke test.

**Out of scope:** Phase 5's main loop (`src/loop.py`), any orchestration that wires optimiser → agent → judge, the call-site NDA-absence enforcement (that lives in Phase 5), any per-iteration results-file writes, any optimiser-meta-prompt evolution across runs, any feedback-deduplication or aggregation across multiple iterations.

</domain>

<decisions>
## Implementation Decisions

### Function Signature + Return Shape

- **D-01:** `run_optimiser(system_prompt: str, judge_result: JudgeResult) -> OptimiserResult`. The input is the Phase 2 `JudgeResult` (structured, carries 8 `RubricScore` entries with `item_id`, `score`, `evidence`, `reasoning`, `feedback`). The NDA is NOT a parameter and will never be passable by the type signature alone — OPTM-01's "NDA-absence" constraint is enforced structurally. The function's only other input is the current `system_prompt: str`. No NDA, no rubric, no playbook, no iteration number.

- **D-02:** New `OptimiserResult` Pydantic model in `src/models.py` with these fields:
  - `new_system_prompt: str` — the rewritten agent system prompt, post-retry
  - `feedback_seen: list[str]` — the exact list of feedback strings (post-extraction, see D-07) the optimiser was given, for OPTM-02 pass-through logging
  - `prompt_diff: str` — unified-diff string comparing `system_prompt` (old) vs `new_system_prompt`, see D-10
  - `prompt_word_count: int` — `len(new_system_prompt.split())`, must be ≤ 300
  - `old_word_count: int` — `len(system_prompt.split())`, for before/after comparison in Phase 5 analysis
  - `vocab_warning: bool = False` — set True if post-hoc P8 scrub (D-11) finds banned rubric vocabulary in `new_system_prompt`
  - `retry_count: int = 0` — number of retries used to bring the output under the word limit (0 if first attempt succeeded; up to 3 per D-09)
  - `failed: bool = False` — True if all 3 retries exhausted and the sentinel path fired (see D-09). When True, `new_system_prompt == system_prompt` (unchanged) and Phase 5 should log the failure and continue.

- **D-03:** `@model_validator(mode="after")` on `OptimiserResult` to enforce:
  - If `failed == True`: `new_system_prompt == system_prompt_that_was_passed_in` (but since we only see `new_system_prompt` in the model, this invariant is enforced at `run_optimiser` construction time, not inside the validator — the validator only checks that `prompt_word_count == len(new_system_prompt.split())` and `old_word_count >= 0`).
  - Structural invariants: `prompt_word_count == len(new_system_prompt.split())`, `old_word_count >= 0`, `retry_count >= 0 and retry_count <= 3`.

### Schema Extension to IterationResult

- **D-04:** Extend `IterationResult` in `src/models.py` with three new fields, all with defaults so existing callers (Phase 2 tests, Phase 3 pre_loop_test) don't break:
  - `optimiser_feedback_seen: list[str] = []` — the `feedback_seen` from the OptimiserResult that produced this iteration's `system_prompt` (empty for iteration 0, when no optimiser has run yet)
  - `prompt_diff: str = ""` — the `prompt_diff` from the OptimiserResult that produced this iteration's `system_prompt` (empty for iteration 0)
  - `prompt_word_count: int = 0` — word count of `system_prompt` at iteration time (Phase 5 will populate even for iteration 0, which is the ITERATION_ZERO_SYSTEM_PROMPT)

- **D-05:** The existing `_check_totals` `@model_validator` on `IterationResult` stays intact. The three new fields do NOT participate in any cross-field invariants — they're passive logging. No validator changes needed beyond adding the fields.

- **D-06:** Phase 3's `PreLoopTestResult` uses `IterationResult` entries for `output_a_runs` and `output_b_runs`. Since the three new fields have defaults, existing `results/pre_loop_test.json` will continue to parse with the schema change — Pydantic treats missing fields as default-valued. Planner must verify this explicitly via `uv run pytest -q -m "not integration"` after the schema change.

### Feedback Extraction Strategy

- **D-07:** Internal helper `_build_feedback_block(judge_result: JudgeResult) -> list[str]` transforms the 8 `RubricScore` entries into a list of strings that become the `feedback_seen` field AND the core content of the user-role message to the optimiser. Algorithm:
  1. Take all 8 `RubricScore` entries (include score=2 "wins" so the optimiser doesn't regress what's working).
  2. Sort by `score` ascending (worst failures first).
  3. For each entry, format as `f"{index}. [score={score.score}] {score.feedback}"` where `index` is 1-based after sorting.
  4. **Strip `item_id` entirely.** `1a`, `1b`, `2a`, `2b`, etc. are rubric vocabulary (P8). The optimiser sees only `[score=N]` and the feedback text.
  5. Return the list of 8 formatted strings. Phase 5's `IterationResult.optimiser_feedback_seen` stores exactly this list.

- **D-08:** The user-role message to the optimiser is built from the feedback block plus the current system prompt. Example structure:
  ```
  Current agent system prompt (to be rewritten):
  ---
  {system_prompt}
  ---

  Judge feedback on the latest review (sorted by score ascending, worst first):
  1. [score=0] {feedback text}
  2. [score=0] {feedback text}
  3. [score=1] {feedback text}
  ...
  8. [score=2] {feedback text}

  Rewrite the agent system prompt to address the lowest-scoring items while preserving what already works. Hard limit: 300 words.
  ```

### Meta-Prompt (System Role for the Optimiser)

- **D-09:** The optimiser's `system` message enforces the hard limit and anti-P8/P5 instructions explicitly. Canonical content (planner may polish wording but must preserve ALL of these directives):
  ```
  You are a prompt optimiser. Your job is to rewrite an NDA-review agent's
  system prompt based on feedback from an evaluator.

  Hard constraints:
  - The rewritten prompt MUST be 300 words or fewer. This is non-negotiable.
  - Do NOT use words from the rubric or playbook. Banned vocabulary includes:
    "rubric", "judge", "score", "evaluation", "criteria", "extraction",
    "judgment item", "1a", "1b", "2a", "2b", "3a", "3b", "4a", "4b".
  - Rewrite the prompt in plain NDA-review terms only — describe what the
    reviewer should do, not how they will be scored.
  - Do not mention feedback, evaluators, or the optimisation process itself.
  - Do not include preamble, explanation, or commentary. Return ONLY the new
    system prompt text, nothing else.

  You receive: the current agent system prompt, and a numbered list of
  feedback strings with scores (0 = not addressed, 1 = partially, 2 = fully).
  Rewrite the prompt to address the lowest-scoring items while preserving
  what already works.
  ```
  The banned-vocabulary list in the meta-prompt mirrors the post-hoc scrub list (D-11) so the optimiser is told what to avoid AND checked against the same list.

- **D-10:** Word count of 300 is the hard limit. **Tradeoff acknowledged:** the user chose 300 (not 200 or 150) for looser headroom. This weakens P11 mitigation somewhat. Phase 5's main loop **MUST** monitor the word-count trend across iterations — if `prompt_word_count` grows monotonically across iterations, that's a P11 signal even if no single iteration exceeds the limit. Add this as a deferred analysis item for Phase 5.

### Word-Count Enforcement + Retry Loop

- **D-11:** Post-validate the word count after each optimiser call. Algorithm (mirrors Phase 2's judge retry pattern):
  ```python
  for attempt in range(MAX_RETRIES):  # MAX_RETRIES = 3
      response = client.chat.completions.create(..., extra_body={"options": {"num_ctx": config.num_ctx}})
      raw = response.choices[0].message.content or ""
      word_count = len(raw.split())
      if word_count <= WORD_LIMIT:  # WORD_LIMIT = 300
          # Success — compute diff, run P8 scrub, return OptimiserResult
          ...
          return ok_result
      # Too long — retry with stricter reminder
      logger.warning("optimiser overrun attempt %d: %d words (limit %d)", attempt + 1, word_count, WORD_LIMIT)
      messages.append({"role": "assistant", "content": raw})
      messages.append({
          "role": "user",
          "content": (
              f"Your rewrite is {word_count} words; the hard limit is {WORD_LIMIT}. "
              f"Rewrite again staying strictly under {WORD_LIMIT} words. "
              f"Return ONLY the new system prompt, no preamble, no commentary."
          ),
      })
  # All retries exhausted — log ERROR, return sentinel OptimiserResult
  logger.error("optimiser retry exhausted; keeping old prompt unchanged (last attempt: %d words)", word_count)
  return OptimiserResult(
      new_system_prompt=system_prompt,  # unchanged
      feedback_seen=feedback_block,
      prompt_diff="",  # no change
      prompt_word_count=len(system_prompt.split()),
      old_word_count=len(system_prompt.split()),
      vocab_warning=False,
      retry_count=MAX_RETRIES,
      failed=True,
  )
  ```
  This is non-raising — mirrors the judge's `JudgeResult(scores=[])` graceful-failure contract (Phase 2 JUDG-05 / D-06). Phase 5's loop.py detects `OptimiserResult.failed == True` and logs + continues the loop (the next iteration uses the unchanged system prompt, which may converge anyway or fail again).

- **D-12:** Use stdlib `logging.getLogger("jitc.optimiser")` consistent with `jitc.agent`, `jitc.judge`, `jitc.preloop` conventions. WARNING per overrun attempt; ERROR on retry exhaustion; INFO at function entry/exit with word counts.

### Prompt Diff Format

- **D-13:** `prompt_diff` is a plain unified-diff string computed via `difflib.unified_diff`:
  ```python
  import difflib
  diff_lines = difflib.unified_diff(
      system_prompt.splitlines(keepends=True),
      new_system_prompt.splitlines(keepends=True),
      fromfile="old_system_prompt",
      tofile="new_system_prompt",
      lineterm="",
      n=3,
  )
  prompt_diff = "".join(diff_lines)
  ```
  Stored as a single string in `OptimiserResult.prompt_diff` and `IterationResult.prompt_diff`. Human-readable in grep / `jq`; any diff viewer can render it. Stdlib only — no new dependencies.

### P8 Post-Hoc Scrub

- **D-14:** After the optimiser returns a successful rewrite (within word limit), run a case-insensitive check for banned rubric vocabulary in `new_system_prompt`. Banned tokens (reuse the same list from `tests/test_agent.py::test_prompt_scrubbed_of_rubric_vocab` so Phase 2 and Phase 4 share one source of truth):
  - Minimum set: `rubric`, `judge`, `score`, `evaluation`, `criteria`, `extraction`, `judgment`, plus item_id patterns `1a`, `1b`, `2a`, `2b`, `3a`, `3b`, `4a`, `4b` (as standalone tokens).
  - The planner should extract this list into a module-level constant in `src/optimiser.py` (e.g. `BANNED_OPTIMISER_OUTPUT_TOKENS`) and also refer to it from the Phase 2 test so drift is impossible.

- **D-15:** On P8 contamination detected:
  - Log `logger.warning("optimiser output contains banned vocab tokens: %s", hits)`
  - Set `OptimiserResult.vocab_warning = True`
  - **Do NOT retry. Do NOT fail.** Per PITFALLS.md P5: "This IS the expected failure mode for judgment items — part of the thesis. Don't prevent it; detect and document it." The warning surfaces the drift so Phase 5's analysis can correlate it with score trajectories.

### Claude's Discretion

The following are deliberately left for the planner/executor:

- **Exact meta-prompt wording.** D-09 gives a canonical version. Planner may polish but must preserve every directive (word limit, banned vocab, no preamble, rewrite-in-plain-terms, no process-meta-language).
- **Retry error message exact wording.** D-11 gives a template. Planner may adjust.
- **`MAX_RETRIES` and `WORD_LIMIT` placement.** Module-level constants in `src/optimiser.py` vs config fields. Recommend module-level constants — these are invariants, not config.
- **FakeClient-backed unit test structure.** Recommend mirroring Phase 2's `tests/test_judge.py`: happy path, retry recovers on attempt 2, retry exhaustion returns sentinel, word-count violation triggers retry, successful rewrite populates all OptimiserResult fields correctly, P8 scrub detection, prompt_diff format sanity. Planner decides exact test function names and coverage depth.
- **Live integration smoke test.** Optional — follow Phase 2's `test_smoke_ollama.py` pattern (`@pytest.mark.integration`). One round-trip: seed with `ITERATION_ZERO_SYSTEM_PROMPT` + a synthetic `JudgeResult` (can reuse Phase 3's actual `output_a` judge run from `results/pre_loop_test.json`), call `run_optimiser`, assert `failed=False`, `prompt_word_count <= 300`, `prompt_diff != ""`. Planner's call whether to add this now or defer to Phase 5.
- **Runtime NDA-leakage assertion.** OPTM-01 says the NDA is enforced at the Phase 5 call site. Phase 4 doesn't need to defend against it internally. But an optional assertion like `assert "nda" not in system_prompt.lower()` or checking for known NDA substrings could be added defensively. Planner's call — if it adds cost without catching real bugs, skip it.
- **Whether `run_optimiser` accepts an optional `model: str` parameter** to override `config.model`. Recommend no — use `config.model` like `run_agent`/`run_judge` do. Consistency wins.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 2 Artifacts (patterns to mirror)
- `src/judge.py` — retry-with-feedback loop pattern, `MAX_RETRIES = 3` constant, `num_ctx` via `extra_body`, stdlib `logging` setup, single-clause `except ValidationError` for Pydantic v2, graceful-failure sentinel return. Phase 4's retry loop mirrors this almost exactly (different validation: word-count instead of Pydantic schema).
- `src/agent.py` — simpler `create()` wrapper, `ITERATION_ZERO_SYSTEM_PROMPT` constant. Phase 4's meta-prompt is a new constant following the same style.
- `src/llm.py` — shared `get_client()` factory. Phase 4 imports from here, does not create its own client.
- `src/config.py` — `config.model`, `config.temperature`, `config.num_ctx`. Phase 4 reads all three.
- `src/models.py` — `JudgeResult`, `RubricScore`, `IterationResult`, `ExperimentRun`, `@model_validator(mode="after")` pattern. Phase 4 adds `OptimiserResult` here and extends `IterationResult`.
- `tests/conftest.py` — `FakeClient` fixture, `VALID_JUDGE_JSON`, `_reset_llm_singleton` autouse. Phase 4 tests reuse all three.
- `tests/test_judge.py` — retry-loop test pattern. Phase 4's tests (happy path, retry recovery, retry exhaustion) mirror these.
- `tests/test_agent.py::test_prompt_scrubbed_of_rubric_vocab` — THE shared banned-token list source of truth. Phase 4's `BANNED_OPTIMISER_OUTPUT_TOKENS` must reference the same list (import or mirror), not a divergent copy.

### Phase 3 Artifacts (consumer interface)
- `src/pre_loop_test.py` — demonstrates how a downstream consumer uses `IterationResult`. Phase 4's `IterationResult` schema extension must not break this module's existing behaviour.
- `.planning/phases/03-pre-loop-validation-gate/03-CONTEXT.md` — shows that schema extensions via default-valued fields are the expected pattern when adding to IterationResult
- `results/pre_loop_test.json` — a real-world example of `IterationResult` data the Phase 4 schema extension must be backward-compatible with.

### Research
- `.planning/research/PITFALLS.md`:
  - **P5** (Goodhart's Law) — the load-bearing pitfall for this phase. Detection, not prevention. D-14/D-15 implement detection.
  - **P11** (prompt gets longer every iteration) — the justification for the 300-word hard limit + retry loop (D-11).
  - **P8** (rubric vocab contamination) — the justification for the post-hoc scrub (D-14) and the meta-prompt's banned-vocabulary instructions (D-09).
- `.planning/research/STACK.md` — Pydantic v2 patterns, retry loop skeleton, "What NOT to Use" reminders (no `instructor`, no `response_format`).
- `.planning/research/FEATURES.md` — MVP scope confirmation

### Project-Level
- `.planning/PROJECT.md` — "Optimiser doesn't see NDA" key decision (lockdown)
- `.planning/REQUIREMENTS.md` §Optimiser — OPTM-01, OPTM-02, OPTM-03 acceptance text
- `.planning/ROADMAP.md` Phase 4 — the 4 success criteria
- `prd.md` — may contain exact optimiser wording or additional constraints; reconcile any conflicts with D-01..D-15 or flag explicitly

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`src/llm.py::get_client()`** — shared OpenAI client factory. Phase 4's `src/optimiser.py` imports from here. Do NOT create a new client.
- **`src/config.py::config`** — model, temperature, num_ctx, api_key all available. `config.temperature` = 0.0 is the project constraint.
- **`src/models.py::JudgeResult`, `RubricScore`** — Phase 4 takes `JudgeResult` as input, iterates `judge_result.scores` to build the feedback block.
- **`src/models.py::IterationResult`** — Phase 4 extends with 3 new fields (all with defaults).
- **Pattern: `src/judge.py::run_judge` retry loop** — Phase 4's retry loop is structurally identical, differ only in the validation step (word count vs Pydantic `model_validate_json`).
- **`tests/conftest.py` `FakeClient`** — Phase 4 unit tests monkeypatch it via the existing fixture. `FakeClient._FakeChatCompletions.create` already deep-copies kwargs (from Phase 2 Rule 1 fix), so retry tests can inspect per-call message history.
- **`tests/test_agent.py::test_prompt_scrubbed_of_rubric_vocab`** — the banned-token list source of truth. Phase 4's `BANNED_OPTIMISER_OUTPUT_TOKENS` either imports from there or extracts into a shared constant.

### Established Patterns
- **stdlib `logging.getLogger("jitc.<component>")`** — extend with `jitc.optimiser`.
- **Pydantic v2 `@model_validator(mode="after")`** — apply to `OptimiserResult` for basic structural invariants.
- **Constants at module level** — `MAX_RETRIES = 3` and `WORD_LIMIT = 300` in `src/optimiser.py` body, mirroring `src/judge.py::MAX_RETRIES`, `MAX_ERROR_CHARS`.
- **No `response_format`, no `stream`, no `client.beta.chat.completions.parse`** — STACK.md "What NOT to Use" list is still in effect. Phase 4 uses plain `client.chat.completions.create()` + string post-processing.
- **`extra_body={"options": {"num_ctx": config.num_ctx}}` on every call** — D-04 from Phase 2, still applies (P6 mitigation).

### Integration Points
- **New file:** `src/optimiser.py` with `run_optimiser`, `_build_feedback_block`, `_build_user_message`, `OPTIMISER_SYSTEM_PROMPT` constant, `BANNED_OPTIMISER_OUTPUT_TOKENS` constant, `MAX_RETRIES`, `WORD_LIMIT` constants, stdlib logger.
- **Edit:** `src/models.py` — add `OptimiserResult` class, extend `IterationResult` with 3 new fields.
- **New file:** `tests/test_optimiser.py` with FakeClient-backed unit tests (happy path, retry recovery, retry exhaustion sentinel, word-count overrun, P8 scrub detection, diff format sanity, structural invariants on OptimiserResult).
- **Optional new file:** `tests/test_smoke_optimiser.py` or a new function in `tests/test_smoke_ollama.py` for a live Ollama round-trip. Planner's call.
- **Does NOT touch:** `src/loop.py` (doesn't exist, Phase 5), `src/agent.py`, `src/judge.py`, `src/pre_loop_test.py`, `src/llm.py`, `src/config.py`, `data/*`.

</code_context>

<specifics>
## Specific Ideas

- **`OptimiserResult.failed` semantics.** When `failed=True`, `new_system_prompt` is the unchanged old prompt. This means Phase 5 callers can safely do:
  ```python
  opt = run_optimiser(current_system_prompt, judge_result)
  current_system_prompt = opt.new_system_prompt  # might be unchanged if failed
  iteration_result.prompt_diff = opt.prompt_diff  # empty string if failed
  iteration_result.optimiser_feedback_seen = opt.feedback_seen  # still populated
  if opt.failed:
      logger.warning("optimiser failed at iteration N; keeping old prompt")
  ```
  This contract lets the loop run to completion even if one optimisation fails — same philosophy as JUDG-05 graceful failure.

- **Banned token list as shared source of truth.** Phase 2's `test_prompt_scrubbed_of_rubric_vocab` defines a list like `["rubric", "judge", "score", ...]`. Rather than copy-pasting into `src/optimiser.py`, the planner should extract the list into a module-level constant (e.g., in `src/agent.py` since that's where the iteration-zero constant lives, or in a new `src/banned_vocab.py` — but that's heavier than needed for 13 tokens). **Recommendation:** put `BANNED_RUBRIC_VOCAB_TOKENS` in `src/models.py` (near the RubricScore definition, since it's a rubric-level constant), export it, and have both `tests/test_agent.py` and `src/optimiser.py` import from there. That way any addition is one-touch.

- **Retry message format.** D-11 gives the retry user-message template. Keep it under ~30 words — longer messages use context budget on each retry and may themselves grow over time.

- **Prompt diff readability.** Using `n=3` context lines in `difflib.unified_diff` gives 3 lines of surrounding context per hunk. For short agent prompts (~40-300 words), this often means the whole prompt fits in one hunk. That's fine — readable as a single block.

- **word count definition.** Use `len(prompt.split())` — Python's default whitespace split. Consistent with how humans count words. Do not use a regex or NLP tokenizer. The meta-prompt says "300 words" in plain English and the check should match plain English expectation.

- **Empty content guard.** Phase 2's `run_agent` uses `response.choices[0].message.content or ""` to absorb Ollama None-content quirks. Phase 4's retry loop must do the same — if the optimiser returns `None`, treat it as an empty string (0 words) which passes the word limit trivially and becomes a clear P5 signal in the log.

</specifics>

<deferred>
## Deferred Ideas

- **Cross-iteration word-count trend analysis.** Phase 5 should detect monotonic word-count growth across iterations as a P11 signal, even if no single iteration exceeds 300. Out of Phase 4 scope — Phase 4 only enforces the per-iteration limit. Add to Phase 5's analysis todo list.

- **Optimiser self-critique / reflection pass.** An additional LLM call that reviews the optimiser's own output before returning. Explicitly out of scope per PROJECT.md: "prompt rewriting only, no agent SDK or tool use, no reflection patterns".

- **Feedback deduplication across iterations.** If iterations 2, 3, 4 all get similar feedback ("flag 7-year duration as unusual"), the optimiser might keep adding the same instruction. Detect and dedupe. Out of Phase 4 scope — Phase 5 loop-level concern.

- **Adaptive word limit.** Shrink the limit if word count grows, grow it if iterations are too constrained. Out of scope — hard 300-word limit is the P11 mitigation.

- **Alternative diff formats.** HTML diff, colorized terminal diff, side-by-side. Out of scope — plain unified diff is what's stored in the JSON; rendering is a Phase 5+ analysis concern.

- **Optimiser meta-prompt evolution.** Rewriting the optimiser's own meta-prompt based on results. Explicitly out of scope — would convert this from a single-variable experiment into a multi-variable search.

- **Runtime NDA-substring assertion.** Defensive check that no NDA fragment appears in `system_prompt` or derived inputs. Out of Phase 4 scope — OPTM-01 says enforcement is at the Phase 5 call site, and adding a runtime assertion in `run_optimiser` would duplicate that concern without adding safety (the function signature already excludes NDA parameters).

</deferred>

---

*Phase: 04-optimiser*
*Context gathered: 2026-04-12*
