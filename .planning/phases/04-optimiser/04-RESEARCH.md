# Phase 4: Optimiser - Research

**Researched:** 2026-04-11
**Domain:** LLM prompt-rewriting library function + P5/P8/P11 mitigation scaffolding
**Confidence:** HIGH (almost entirely derived from locked CONTEXT.md decisions D-01..D-15 and verified against Phase 2/3 source code)

## Summary

Phase 4 builds `src/optimiser.py::run_optimiser(system_prompt, judge_result) -> OptimiserResult`. Architecturally it is a **thin wrapper around a retry-with-feedback loop that mirrors Phase 2's `src/judge.py`**, differing only in the validation step (word-count ≤ 300 instead of Pydantic JSON schema). Every other pattern — `get_client()` import, `extra_body={"options": {"num_ctx": ...}}` on every call, stdlib `logging.getLogger("jitc.optimiser")`, graceful sentinel return instead of raising, FakeClient-backed unit tests — carries over 1:1 from Phase 2.

The phase is load-bearing for the entire experiment's thesis. PITFALLS.md P5 (Goodhart's Law / self-reference collapse on judgment items) is the **expected failure mode** this experiment is designed to expose, not prevent. D-14/D-15 explicitly implement **detection** (post-hoc P8 scrub → `vocab_warning=True`) rather than prevention (no retry, no fail). This is the correct posture: preventing the drift would destroy the experiment's diagnostic signal. The researcher's job in Phase 4 is to make sure the detection is plumbed through to the results JSON so Phase 5's analysis can correlate vocab-drift with judgment-score trajectories.

**Primary recommendation:** Implement `run_optimiser` as a near-verbatim clone of `run_judge`'s retry loop with three structural differences: (1) the validation check is `len(raw.split()) <= WORD_LIMIT` instead of `JudgeResult.model_validate_json(...)`; (2) on success, compute `prompt_diff` via `difflib.unified_diff` and run `_check_banned_vocab` before constructing the `OptimiserResult`; (3) the sentinel on retry exhaustion carries the **unchanged old prompt** (not an empty result) so Phase 5's loop can continue with the previous iteration's system prompt unchanged.

## User Constraints (from CONTEXT.md)

### Locked Decisions — D-01..D-15

All 15 decisions are locked and copied from `.planning/phases/04-optimiser/04-CONTEXT.md`. The planner MUST honour every one. Summary (full text in CONTEXT.md):

| ID | Lock |
|----|------|
| **D-01** | Signature: `run_optimiser(system_prompt: str, judge_result: JudgeResult) -> OptimiserResult`. **NDA is structurally unreachable** — not a parameter. No rubric, playbook, or iteration number either. |
| **D-02** | New `OptimiserResult` model with 8 fields: `new_system_prompt`, `feedback_seen`, `prompt_diff`, `prompt_word_count`, `old_word_count`, `vocab_warning` (default `False`), `retry_count` (default `0`), `failed` (default `False`). |
| **D-03** | `@model_validator(mode="after")` on `OptimiserResult` enforcing structural invariants: `prompt_word_count == len(new_system_prompt.split())`, `old_word_count >= 0`, `0 <= retry_count <= 3`. |
| **D-04** | Extend `IterationResult` with 3 new fields (all defaulted): `optimiser_feedback_seen: list[str] = []`, `prompt_diff: str = ""`, `prompt_word_count: int = 0`. |
| **D-05** | Existing `_check_totals` validator on `IterationResult` is untouched. New fields are passive logging — no cross-field invariants. |
| **D-06** | Phase 3's `PreLoopTestResult` and `results/pre_loop_test.json` parse transparently under the schema extension because all new fields have defaults. Verify via `uv run pytest -q -m "not integration"` after the edit. |
| **D-07** | `_build_feedback_block(judge_result) -> list[str]`: take all 8 `RubricScore` entries (include score=2 wins), sort by `score` ascending, format `f"{index}. [score={s.score}] {s.feedback}"` with 1-based index after sort. **Strip `item_id` entirely** (P8). Returns 8 strings — becomes both `feedback_seen` AND the user-message body. |
| **D-08** | User-role message layout: old system prompt inside `---` fences, then the numbered feedback block, then the "Rewrite… Hard limit: 300 words." instruction line. |
| **D-09** | Optimiser system prompt: canonical text in CONTEXT.md D-09, enforcing word limit + banned vocabulary + "no preamble / no commentary / return only the new system prompt" + "describe what the reviewer should do, not how they will be scored". Planner may polish wording; must preserve every directive. |
| **D-10** | `WORD_LIMIT = 300`. Tradeoff acknowledged: user chose 300 over a tighter 150/200, weakening P11 mitigation. Phase 5 **MUST** add a cross-iteration monotonic-growth monitor as compensation. |
| **D-11** | `MAX_RETRIES = 3` word-count retry loop. On success: return populated `OptimiserResult`. On exhaustion: return sentinel `OptimiserResult(failed=True, new_system_prompt=system_prompt, prompt_diff="", retry_count=3, ...)`. Non-raising. |
| **D-12** | Logger namespace `jitc.optimiser`. WARNING per overrun attempt; ERROR on retry exhaustion; INFO at function entry with word counts. |
| **D-13** | `prompt_diff` is a plain string produced by `difflib.unified_diff(splitlines(keepends=True), fromfile="old_system_prompt", tofile="new_system_prompt", lineterm="", n=3)`, joined with `"".join(...)`. Stdlib only. |
| **D-14** | Post-hoc P8 scrub reuses the banned-token list from `tests/test_agent.py::_BANNED_TOKENS` (the source of truth). Case-insensitive substring check in `new_system_prompt`. |
| **D-15** | On P8 hit: `logger.warning(...)` + `vocab_warning=True`. **Do NOT retry. Do NOT fail.** Per PITFALLS P5: the drift is the signal, not a bug. |

### Claude's Discretion

All 7 discretion items raised in the planner's research request are resolved in §3 below and restated in §7 ("Open Questions (RESOLVED)") for planner pickup.

### Deferred (OUT OF SCOPE for Phase 4)

- Cross-iteration word-count trend analysis — Phase 5 monitor
- Optimiser self-critique / reflection pass — explicitly ruled out by PROJECT.md
- Feedback deduplication across iterations — Phase 5 loop-level concern
- Adaptive word limit — violates P11 mitigation posture
- Alternative diff formats (HTML, colour) — plain unified diff only
- Optimiser meta-prompt evolution — converts single-variable experiment into multi-variable search
- Runtime NDA-substring assertion inside `run_optimiser` — OPTM-01 enforces NDA absence at the Phase 5 call site; an internal runtime check would duplicate a guarantee the type signature already provides

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **OPTM-01** | Optimiser takes current system prompt + judge feedback only (not the NDA), returns rewritten prompt. | `run_optimiser` type signature (D-01) makes NDA a compile-time unreachable parameter. Planner adds no internal check — the signature IS the enforcement. |
| **OPTM-02** | Feedback pass-through logging — store what feedback was received. | `OptimiserResult.feedback_seen: list[str]` (D-02) populated by `_build_feedback_block` (D-07). Phase 5's loop mirrors into `IterationResult.optimiser_feedback_seen` (D-04). |
| **OPTM-03** | Prompt diff between iterations stored in results. | `OptimiserResult.prompt_diff: str` via `difflib.unified_diff` (D-13). Phase 5 mirrors into `IterationResult.prompt_diff` (D-04). |

### Phase 4 Success Criteria (from ROADMAP)

1. `run_optimiser(system_prompt, judge_result)` returns a new system prompt string; NDA never passed as argument — **enforced at call site** in Phase 5, and structurally unreachable in Phase 4's signature.
2. Optimiser meta-prompt enforces a hard word-count limit; returned prompt demonstrably stays within that limit — **enforced by the D-11 retry loop, not just by prompt instruction**.
3. Feedback strings passed to the optimiser are stored alongside the new prompt — **`feedback_seen` field**.
4. Prompt diff between input and output system prompt is captured and stored — **`prompt_diff` field**.

All four map to verifiable unit tests in §6.

## Standard Stack

No new runtime dependencies. Entirely stdlib + existing Phase 2 modules.

| Module | Version | Purpose | Why Standard |
|--------|---------|---------|--------------|
| `openai` | ≥2.0 (installed) | LLM client via `src/llm.get_client()` | Already established in Phase 2 |
| `pydantic` | ≥2.0 (installed) | `OptimiserResult` model + `IterationResult` extension | Already established in Phase 1 |
| `difflib` | stdlib | `unified_diff` for `prompt_diff` | D-13 locked — zero dependency cost |
| `logging` | stdlib | `jitc.optimiser` namespace | Matches `jitc.agent` / `jitc.judge` / `jitc.preloop` convention |

**No `pytest` plugin changes, no new packages in `pyproject.toml`.** The FakeClient-backed tests reuse `tests/conftest.py` as-is.

## Architecture Patterns

### Recommended File Layout (post-Phase-4)

```
src/
├── agent.py            # unchanged
├── judge.py            # unchanged
├── llm.py              # unchanged
├── config.py           # unchanged
├── models.py           # +OptimiserResult, +IterationResult.optimiser_feedback_seen/prompt_diff/prompt_word_count, +BANNED_RUBRIC_VOCAB_TOKENS
├── optimiser.py        # NEW — run_optimiser + helpers + constants
└── pre_loop_test.py    # unchanged (backward-compatible under D-06)

tests/
├── conftest.py         # unchanged
├── test_agent.py       # MINIMAL edit — import BANNED_RUBRIC_VOCAB_TOKENS instead of local _BANNED_TOKENS
├── test_judge.py       # unchanged
├── test_optimiser.py   # NEW — ~10 FakeClient unit tests
└── (optional) test_smoke_optimiser.py  # defer to Phase 5 — see §3 item 5
```

### Pattern 1: Retry-with-Feedback (mirrors `src/judge.py::run_judge`)

**What:** Loop up to `MAX_RETRIES=3` attempts, each calling `client.chat.completions.create`. Validate the raw response. On success, return; on failure, append `(assistant=raw, user=correction_message)` to `messages` and retry. On exhaustion, return a sentinel result (not raise).

**Why:** Phase 2 already established this as the house pattern (JUDG-02, JUDG-05, P7). Phase 4's loop is structurally identical. The **only** differences:

| Aspect | `run_judge` | `run_optimiser` |
|--------|-------------|-----------------|
| Validation step | `JudgeResult.model_validate_json(_extract_json(raw))` inside `try: except ValidationError` | `len(raw.split()) <= WORD_LIMIT` via an `if` check |
| Sentinel value | `JudgeResult(scores=[])` — empty list, caller detects with `if not result.scores:` | `OptimiserResult(failed=True, new_system_prompt=system_prompt, ...)` — unchanged old prompt, caller detects with `if opt.failed:` |
| Correction message style | Echoes truncated `ValidationError` text + "Return only valid JSON" reminder | Reports the observed word count + "Rewrite again strictly under 300 words" reminder |

Everything else — `num_ctx` via `extra_body`, `temperature=config.temperature`, `messages: list[dict]`, per-attempt `logger.info`, deep-copy-safe FakeClient fixture — is copy-paste-level identical.

### Pattern 2: Pydantic v2 `@model_validator(mode="after")` for Structural Invariants

**What:** `OptimiserResult` uses a single post-construction validator to enforce internal consistency.

**Why:** Phase 1 (`PreLoopTestResult._compute_gate`) and Phase 2 (`IterationResult._check_totals`) both use this pattern. D-03 locks it for `OptimiserResult`.

### Pattern 3: Module-Level Constants for Load-Bearing Invariants

**What:** `MAX_RETRIES = 3`, `WORD_LIMIT = 300`, `OPTIMISER_SYSTEM_PROMPT = "..."` at module level in `src/optimiser.py`.

**Why:** Matches `src/judge.py::MAX_RETRIES = 3`, `MAX_ERROR_CHARS = 800`, `JUDGE_SYSTEM_PROMPT = "..."`. Phase 3 CONTEXT.md explicitly locked the 2.0 threshold as non-configurable (P10 mitigation) via rejection in a Pydantic validator; Phase 4 should follow the same spirit — `WORD_LIMIT` and `MAX_RETRIES` are experiment invariants, not configuration.

### Anti-Patterns to Avoid

- **Do NOT** add a `response_format={"type": "json_object"}` parameter — the optimiser returns freeform text, not JSON. Mirrors `run_agent`, not `run_judge`.
- **Do NOT** add the `_extract_json` preprocessing — the optimiser output IS the prompt string, not a wrapped JSON object. (If the model emits commentary or fences, that's a meta-prompt failure — address it in the meta-prompt, not via post-processing. The retry loop will catch gross overruns; the vocab scrub is the only post-hoc check.)
- **Do NOT** make the optimiser accept an NDA parameter "for defence in depth". OPTM-01 is enforced by the type signature; adding a runtime check duplicates it and invites a false sense of security.
- **Do NOT** build a second retry layer on top of `run_optimiser` in Phase 5. Phase 4's retry loop is authoritative.
- **Do NOT** raise exceptions on retry exhaustion. Mirror JUDG-05's sentinel contract.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Prompt diff | Regex line matcher, custom unified-diff generator | `difflib.unified_diff` (stdlib) | D-13 locks this; stdlib handles edge cases (empty strings, trailing newlines, identical inputs → empty diff) correctly |
| Retry loop | Any `tenacity`/`backoff` wrapper, `instructor`-style retries | Hand-written `for attempt in range(MAX_RETRIES):` mirroring `src/judge.py` | STACK.md "What NOT to Use" explicitly bans `instructor`. House pattern is transparent. |
| Word counting | `re.findall(r'\S+', ...)`, NLP tokenizer, `nltk.word_tokenize` | `len(prompt.split())` | CONTEXT.md §Specific Ideas: "Use Python's default whitespace split. Consistent with how humans count words." The meta-prompt says "300 words" in plain English; the check must match plain English expectation. |
| Banned-vocab detection | Full-text-search library, regex compilation per call | Case-insensitive `in` check over `BANNED_RUBRIC_VOCAB_TOKENS` constant list | 13 tokens, case-folded once, substring check. <1μs per call. |
| OpenAI client | `OpenAI(...)` in `src/optimiser.py` | `src.llm.get_client()` | Phase 2 D-01 locked the shared factory. Do not re-instantiate. |

**Key insight:** Phase 4 is a test of whether the house patterns scale. If you need to reach outside `stdlib + openai + pydantic + existing Phase 2 modules` to build this, you're over-engineering.

## Technical Approach (Discretion Items Resolved)

### Discretion 1 — Where does `BANNED_RUBRIC_VOCAB_TOKENS` live?

**RESOLVED: Put it in `src/models.py`**, exported at module level near `RubricScore`.

**Reasoning:**
- It is rubric-level vocabulary (conceptually an attribute of the rubric domain, not of the agent or optimiser specifically)
- Both `src/optimiser.py` and `tests/test_agent.py` need to import it — a shared ancestor module is required
- `src/models.py` is already imported by every Phase 2/3 module, so adding a constant there costs nothing
- A new `src/banned_vocab.py` module for 13 strings is over-engineered (STACK.md "no framework overhead" principle)
- `src/agent.py` is wrong because Phase 4's optimiser would have to import from `src/agent.py` just for this constant, creating a cross-component dependency that doesn't otherwise exist

**Implementation:**
```python
# in src/models.py, near RubricScore
BANNED_RUBRIC_VOCAB_TOKENS: tuple[str, ...] = (
    "rubric",
    "playbook",
    "score",
    "scoring",
    "evidence",
    "extraction",
    "judgment item",
    "criteria",
    "criterion",
    "evaluate",
    "evaluation",
    "item_id",
    "0/1/2",
)
```

Use `tuple` not `list` — these are immutable by design (changing the list mid-experiment would invalidate the regression gate). Exported via ordinary top-level assignment; Python exposes it to both `from src.models import BANNED_RUBRIC_VOCAB_TOKENS` (`src/optimiser.py`) and `from src.models import BANNED_RUBRIC_VOCAB_TOKENS` (`tests/test_agent.py`).

### Discretion 2 — Exact banned-token list contents

**RESOLVED: Use the 13 tokens currently in `tests/test_agent.py::_BANNED_TOKENS` verbatim.**

Verified by reading `tests/test_agent.py` lines 11-25. The current list:

```
"rubric", "playbook", "score", "scoring", "evidence",
"extraction", "judgment item", "criteria", "criterion",
"evaluate", "evaluation", "item_id", "0/1/2"
```

**Coverage analysis against D-09's meta-prompt ban list:**

| D-09 meta-prompt ban | In `_BANNED_TOKENS`? | Notes |
|----------------------|----------------------|-------|
| `rubric` | ✅ | |
| `judge` | ❌ | **Proposed addition** — D-09 lists it, current test doesn't |
| `score` | ✅ | |
| `evaluation` | ✅ | |
| `criteria` | ✅ | |
| `extraction` | ✅ | |
| `judgment item` | ✅ | |
| `1a`/`1b`/`2a`/`2b`/`3a`/`3b`/`4a`/`4b` | ❌ | **Proposed additions** — item_id patterns from D-09 |

**Recommendation — extend the list to cover every D-09 ban verbatim:**

```python
BANNED_RUBRIC_VOCAB_TOKENS: tuple[str, ...] = (
    # Existing 13 tokens from tests/test_agent.py::_BANNED_TOKENS — Phase 2 regression gate
    "rubric",
    "playbook",
    "score",
    "scoring",
    "evidence",
    "extraction",
    "judgment item",
    "criteria",
    "criterion",
    "evaluate",
    "evaluation",
    "item_id",
    "0/1/2",
    # Added in Phase 4 per D-09 / D-14 to align with optimiser meta-prompt ban list
    "judge",
    "1a", "1b", "2a", "2b", "3a", "3b", "4a", "4b",
)
```

**Verification required by planner:** Adding `"judge"` and the item_id tokens to the shared constant means `tests/test_agent.py::test_prompt_scrubbed_of_rubric_vocab` will also run those checks against `ITERATION_ZERO_SYSTEM_PROMPT`. Read the current iteration-zero prompt (`src/agent.py` lines 32-37):

> "You are reviewing a Non-Disclosure Agreement. Identify all issues and assess their significance. Output your findings as a structured list. For each issue provide: the clause reference, a description of the issue, and your risk assessment."

None of the new tokens appear in this text. **Safe to extend.** The test still passes after the extension. Adding the tokens costs nothing and tightens Phase 2's regression gate retroactively.

**Minor caveat:** `"1a"`..`"4b"` are 2-character substrings. A legitimate prompt containing the string "this is a 1a-class NDA" would false-positive — but (a) that phrase is contrived, (b) the iteration-zero prompt contains none of them, and (c) false positives here are fine because the check is `vocab_warning=True` (non-fatal, detection-only). The risk is a slightly over-sensitive warning, not a broken pipeline.

### Discretion 3 — `_build_feedback_block` return type: `list[str]` or pre-formatted `str`?

**RESOLVED: Return `list[str]`. Build the user message as a separate step that joins the list.**

**Reasoning:**
- D-07 says `list[str]`, which is what `OptimiserResult.feedback_seen: list[str]` stores directly — no round-tripping
- The user-message assembly in D-08 needs the list joined with newlines, which is a trivial `"\n".join(feedback_block)` one-liner — keeping it in the list form at build time avoids having to re-split a joined string back into a list for the `feedback_seen` field
- Tests can assert shape (`len(feedback) == 8`, sorted by `[score=N]` prefix) against the list directly without string parsing

**Implementation:**
```python
def _build_feedback_block(judge_result: JudgeResult) -> list[str]:
    """D-07: sorted ascending by score, item_id stripped, [score=N] prefix."""
    sorted_scores = sorted(judge_result.scores, key=lambda s: s.score)
    return [
        f"{i}. [score={s.score}] {s.feedback}"
        for i, s in enumerate(sorted_scores, start=1)
    ]


def _build_user_message(system_prompt: str, feedback_block: list[str]) -> str:
    """D-08: old prompt fences + numbered feedback + rewrite instruction."""
    joined = "\n".join(feedback_block)
    return (
        "Current agent system prompt (to be rewritten):\n"
        "---\n"
        f"{system_prompt}\n"
        "---\n\n"
        "Judge feedback on the latest review "
        "(sorted by score ascending, worst first):\n"
        f"{joined}\n\n"
        "Rewrite the agent system prompt to address the lowest-scoring items "
        "while preserving what already works. Hard limit: "
        f"{WORD_LIMIT} words."
    )
```

### Discretion 4 — FakeClient unit test suite shape

**RESOLVED: 10 tests mirroring `tests/test_judge.py` structure. Function list below.** Each test is one-assertion-focused; names follow the `test_<behaviour>` convention.

| # | Test function | What it verifies |
|---|---------------|------------------|
| 1 | `test_happy_path_returns_optimiser_result` | Single-attempt valid rewrite (70-word canned response). Asserts `isinstance(result, OptimiserResult)`, `failed=False`, `retry_count=0`, `prompt_word_count == 70`, `old_word_count == len(old.split())`, `vocab_warning=False`, `feedback_seen` has 8 items, `len(client.calls) == 1`. |
| 2 | `test_retry_recovers_on_second_attempt` | First response has 350 words, second has 80 words. Asserts `failed=False`, `retry_count=1`, `len(client.calls) == 2`, second-call messages include the `(assistant=350-word-raw, user=retry-correction)` turn. |
| 3 | `test_retry_exhaustion_returns_sentinel` | All 3 responses exceed 300 words. Asserts `failed=True`, `retry_count=3`, `new_system_prompt == system_prompt` (unchanged), `prompt_diff == ""`, `len(client.calls) == 3`. Non-raising. |
| 4 | `test_word_overrun_triggers_retry_with_word_count_in_message` | First response 450 words, second 100 words. Inspects `client.calls[1]["messages"][-1]["content"]` — must contain `"450"` and `"300"` (shows the model what it did wrong and what the bar is). |
| 5 | `test_vocab_warning_set_when_banned_token_present` | Canned response contains `"Use the rubric to score..."`. Asserts `failed=False`, `vocab_warning=True`, `retry_count=0` (does NOT retry — D-15), warning logged at `jitc.optimiser` WARNING level with the hit tokens. |
| 6 | `test_vocab_warning_false_on_clean_output` | Canned response contains no banned tokens. Asserts `vocab_warning=False`. |
| 7 | `test_prompt_diff_is_unified_diff_format` | Canned response differs from input by one line. Asserts `prompt_diff` starts with `"--- old_system_prompt"`, contains `"+++ new_system_prompt"`, has `"+"` and `"-"` hunk lines. Sanity only — no full-diff equality. |
| 8 | `test_feedback_block_sorted_ascending_and_strips_item_ids` | Call `_build_feedback_block` directly on a synthetic `JudgeResult` with scores `[2, 0, 1, 2, 0, 1, 2, 0]`. Asserts returned list is length 8, first entry starts `"1. [score=0]"`, last starts `"8. [score=2]"`, no `item_id` strings (`"1a"`, `"2b"`, etc.) appear in any entry. |
| 9 | `test_all_eight_feedback_items_included` | Same synthetic `JudgeResult`. Call `run_optimiser`, assert `len(result.feedback_seen) == 8`, and that the user-role message in `client.calls[0]["messages"]` contains all 8 feedback strings. |
| 10 | `test_structural_invariants_rejected_by_validator` | Construct `OptimiserResult(new_system_prompt="one two three", prompt_word_count=99, old_word_count=0, feedback_seen=[], prompt_diff="", ...)` — should raise `ValidationError` because `99 != len("one two three".split()) == 3`. Also test `retry_count=-1` and `retry_count=4` both raise. |

**Plus 2 auxiliary tests mirroring `test_judge.py`:**

| # | Test function | What it verifies |
|---|---------------|------------------|
| 11 | `test_num_ctx_in_every_call` | For a 3-attempt retry sequence, every `client.calls[i]` has `extra_body == {"options": {"num_ctx": config.num_ctx}}`, `temperature == config.temperature`, `model == config.model`, and `"response_format" not in kwargs`. Mirrors `test_judge.py::test_num_ctx_in_every_call`. |
| 12 | `test_retry_exhaustion_logs_error_at_jitc_optimiser` | `caplog.at_level(ERROR, logger="jitc.optimiser")`; after 3 overruns, at least one ERROR record contains "exhausted" and the final attempt's word count. Mirrors `test_judge.py::test_graceful_failure_logs_raw_output`. |

**Total: 12 tests in `tests/test_optimiser.py`.** Combined with existing 21 passing Phase 2/3 tests, `uv run pytest -q -m "not integration"` should return **33+ passed** after Phase 4 lands.

### Discretion 5 — Integration smoke test: now or defer?

**RESOLVED: Defer to Phase 5.**

**Reasoning:**
- FakeClient unit tests cover every deterministic behaviour: retry loop, word counting, P8 scrub, diff format, structural invariants. A live integration test adds no new *determinable* coverage.
- Phase 5's main loop will run `run_optimiser` live against Ollama on every iteration — the first Phase 5 loop execution IS the integration test, with better signal (you see 5 iterations of actual optimiser behaviour under realistic feedback).
- A Phase 4 smoke test would need to fabricate a `JudgeResult` (from `results/pre_loop_test.json` or synthetic), which Phase 5 builds authentically from a live agent run. The Phase 4 test would test the fabrication, not the optimiser.
- Consistent with Phase 2: `tests/test_smoke_ollama.py` was the integration harness that covered agent + judge round-trip; Phase 4's equivalent belongs in the Phase 5 smoke or live-run gate, not as a standalone file.

**If planner disagrees**, the minimal smoke would be:
```python
# tests/test_smoke_optimiser.py (OPTIONAL — NOT RECOMMENDED FOR PHASE 4)
@pytest.mark.integration
def test_optimiser_live_round_trip():
    """Seed with ITERATION_ZERO_SYSTEM_PROMPT and a synthetic 8-score JudgeResult
    (all score=1, generic feedback). Call run_optimiser. Assert failed=False,
    prompt_word_count <= 300, prompt_diff != ""."""
    from src.agent import ITERATION_ZERO_SYSTEM_PROMPT
    from src.models import JudgeResult, RubricScore
    from src.optimiser import run_optimiser

    judge_result = JudgeResult(scores=[
        RubricScore(
            item_id=f"{i}{letter}",
            item_type=item_type,
            issue_number=i,
            score=1,
            evidence="placeholder",
            reasoning="placeholder",
            feedback=f"Improve coverage of issue {i}{letter}.",
        )
        for i in (1, 2, 3, 4)
        for letter, item_type in (("a", "extraction"), ("b", "judgment"))
    ])

    result = run_optimiser(ITERATION_ZERO_SYSTEM_PROMPT, judge_result)
    assert not result.failed
    assert result.prompt_word_count <= 300
    assert result.prompt_diff != ""
```

Gate it behind `@pytest.mark.integration` so `uv run pytest -q -m "not integration"` still runs unit-only in under a second.

### Discretion 6 — Backward-compat verification for `IterationResult`

**RESOLVED: Will work. Verified by tracing every construction site.**

**Grep of existing `IterationResult(...)` construction sites** (only production/test code, excluding `.planning/` docs):

1. **`src/pre_loop_test.py` line 77-82** — constructs with `iteration`, `system_prompt`, `agent_output`, `scores` only. All three new fields (`optimiser_feedback_seen`, `prompt_diff`, `prompt_word_count`) default: `[]`, `""`, `0`. **Safe.**
2. **No other production code constructs `IterationResult`.** `src/judge.py` returns `JudgeResult`, not `IterationResult`. `src/agent.py` returns `str`.
3. **Tests:** `tests/test_judge.py` and `tests/test_agent.py` never construct `IterationResult`. `tests/test_pre_loop_gate.py` would, but it presumably exercises the pre-loop path through `run_pre_loop_test()` (not by hand-constructing rows) — the schema extension is transparent to it because `_judge_one` still omits the new fields and the defaults fill them in.

**Existing `results/pre_loop_test.json` compatibility:** Pydantic v2 `model_validate` treats missing fields as their defaults when parsing. The existing JSON file will round-trip without modification because:
- `optimiser_feedback_seen: list[str] = []` — missing from JSON → `[]`
- `prompt_diff: str = ""` — missing → `""`
- `prompt_word_count: int = 0` — missing → `0`

**`_check_totals` interaction:** Read the validator at `src/models.py` lines 28-52. It inspects only `self.scores`, `self.extraction_score`, `self.judgment_score`, `self.total_score`. The three new fields are **not referenced** in the validator body. The "if all defaults, auto-fill" branch (lines 31-41) checks `self.extraction_score == 0 and self.judgment_score == 0 and self.total_score == 0` — the new fields are not part of this gate. **No interference. No validator changes needed.** This is exactly what D-05 locks.

**Verification plan for planner (automated):**
```bash
uv run pytest -q -m "not integration"
```
Should continue to return all pre-existing tests green. If Phase 3's live integration test (gemma4:26b) is needed, run:
```bash
uv run pytest -q tests/test_pre_loop_gate.py
```
which will re-read `results/pre_loop_test.json` if it exists and confirm the schema still parses.

### Discretion 7 — `_check_totals` interaction with new fields

**RESOLVED: Zero interference.** (Same reasoning as item 6 above; stating separately because the planner asked as a distinct concern.)

The `_check_totals` validator body at `src/models.py:29-52` references only: `self.scores`, `self.extraction_score`, `self.judgment_score`, `self.total_score`. It has two branches:
- **Auto-fill branch** (lines 31-41): triggered when all three totals are `0`. Computes them from `self.scores` and sets via `object.__setattr__`. Does not inspect `optimiser_feedback_seen`/`prompt_diff`/`prompt_word_count`.
- **Consistency branch** (lines 42-51): triggered when any total is non-zero. Raises if the 3-tuple doesn't match the computed values. Again, new fields are not inspected.

Phase 5's main loop will construct `IterationResult` with populated `scores` AND populated optimiser fields. The new fields are passive — the validator runs, auto-fills totals from `scores`, and the optimiser fields pass through untouched. No ordering dependency.

## Pitfall Cross-References

### P5 (Goodhart's Law / Self-Reference Collapse) — DETECTION ONLY

**Why Phase 4 does not prevent P5:** This is the thesis of the entire experiment. The research question is *"does the optimiser converge on judge-approval rather than correctness when feedback is vague?"* Preventing the drift would destroy the experiment. Detection at multiple levels surfaces the signal for analysis.

**Enforcement sites:**

| Layer | Site | What it does |
|-------|------|--------------|
| 1. Meta-prompt warning | `src/optimiser.py::OPTIMISER_SYSTEM_PROMPT` (D-09) | Instructs the model NOT to use rubric/judge/score vocabulary. First line of defence — training the model not to drift. |
| 2. Post-hoc detection | `src/optimiser.py::_check_banned_vocab` + `OptimiserResult.vocab_warning` (D-14/D-15) | Scans rewritten prompt for banned tokens. Logs warning + sets `vocab_warning=True`. **Does not retry. Does not fail.** |
| 3. Pass-through logging | `OptimiserResult.feedback_seen` + `IterationResult.optimiser_feedback_seen` (D-02/D-04) | Phase 5 dumps to JSON. Post-hoc analysis correlates feedback patterns with score trajectories. |
| 4. Prompt evolution trace | `OptimiserResult.prompt_diff` + `IterationResult.prompt_diff` (D-13) | Every iteration's rewrite is captured as a unified diff. Post-hoc analysis can grep for rubric-phrase additions over time. |

**Documented failure mode:** If judgment scores rise in lockstep with extraction scores after iteration 3 AND `vocab_warning=True` in those iterations AND the `prompt_diff`s show rubric phrases being added — that's P5 confirmed, which is the experiment's positive result.

### P8 (Rubric Vocabulary Contamination) — TWO-LAYER DEFENCE

**Phase 4 has two explicit P8 enforcement sites.** This is deliberate: P8 is the mechanism by which P5 manifests, and detecting it requires both an a-priori instruction AND a post-hoc audit.

| Layer | Site | Type | Behaviour on violation |
|-------|------|------|------------------------|
| 1. Meta-prompt instruction | `src/optimiser.py::OPTIMISER_SYSTEM_PROMPT` banned-vocab enumeration (D-09) | Preventive | Hopefully the model obeys. No enforcement mechanism at this layer. |
| 2. Post-hoc scrub | `src/optimiser.py::_check_banned_vocab(new_system_prompt)` (D-14) | Detective | Logs WARNING + sets `vocab_warning=True`. **Does NOT retry and does NOT fail** (per D-15, which is the P5-preserving policy). |

**Shared source of truth:** Both layers reference `BANNED_RUBRIC_VOCAB_TOKENS` in `src/models.py` (§3 Discretion 1). The meta-prompt enumerates the list verbatim (string-interpolated at module load); the post-hoc scrub imports the constant. **Any addition to the list flows through both layers automatically.** This is the key anti-drift invariant the planner must preserve — **never** inline the list as a hand-maintained literal inside `OPTIMISER_SYSTEM_PROMPT`.

Implementation detail for the meta-prompt: string-interpolate the token list at module load:
```python
_BANNED_LIST_FORMATTED = ", ".join(f'"{t}"' for t in BANNED_RUBRIC_VOCAB_TOKENS)
OPTIMISER_SYSTEM_PROMPT = f"""\
You are a prompt optimiser. ...
- Do NOT use words from the rubric or playbook. Banned vocabulary includes:
  {_BANNED_LIST_FORMATTED}
..."""
```

### P11 (Optimiser Prompt Gets Longer Every Iteration) — MITIGATED BUT WEAKENED

**Mitigation sites:**

| Layer | Site | What it does |
|-------|------|--------------|
| 1. Per-iteration hard cap | `WORD_LIMIT = 300` module constant (D-10) | Structural ceiling on any single optimiser output |
| 2. Per-iteration retry on overrun | `run_optimiser` retry loop (D-11) | If the model overshoots 300 words, send it back with the observed count + a stricter reminder. Up to 3 attempts. |
| 3. Sentinel on exhaustion | `OptimiserResult(failed=True, new_system_prompt=system_prompt)` (D-11) | If the model cannot comply in 3 attempts, keep the old prompt unchanged. Prompt cannot grow via a failed optimisation. |

**Weakening acknowledged per D-10:** The user chose 300 words over 150-200. Analysis:
- A 300-word prompt is still 1.5-2× the iteration-zero prompt (~40 words). Over 5 iterations, monotonic growth from 40 → 300 is possible and would not trigger any single-iteration alarm.
- Phase 5 must implement a cross-iteration monotonic-growth monitor. This belongs in Phase 5's analysis code, not in Phase 4. Add to Phase 5 plan backlog as a required item.

**Proposed Phase 5 cross-iteration monitor (for the planner to hand forward to Phase 5):**

```python
# In Phase 5's analysis code (NOT Phase 4)
def detect_prompt_growth_trend(iterations: list[IterationResult]) -> bool:
    """P11 cross-iteration signal. Returns True if prompt_word_count grows
    monotonically across 3+ iterations — a drift indicator even when no
    single iteration hits WORD_LIMIT."""
    if len(iterations) < 3:
        return False
    counts = [it.prompt_word_count for it in iterations]
    growing = sum(
        1 for a, b in zip(counts, counts[1:]) if b > a
    )
    return growing >= len(counts) - 1  # monotonic growth
```

Phase 4's contribution: **populate `prompt_word_count` on every iteration so Phase 5's monitor has data.** The D-04 schema extension makes this the structural payload for the Phase 5 check.

## Runtime State Inventory

Not applicable — Phase 4 is new-file creation and additive schema extension. No rename, no refactor, no migration. Scanned `src/optimiser.py` (does not exist yet), `results/pre_loop_test.json` (schema-extends but defaults make it read-compatible), stored data (none), service config (none), OS state (none), secrets (none), build artifacts (none).

**Explicit null:** Nothing cached, stored, or registered under an old name — there IS no old name for the optimiser.

## Environment Availability

Not applicable — Phase 4 adds no external dependencies beyond what Phase 2 already depends on. `openai`, `pydantic`, `difflib` (stdlib), `logging` (stdlib) are all installed. Ollama is assumed available (same Phase 2/3 assumption).

## Common Pitfalls

### Pitfall 1: Vocabulary list drift between meta-prompt and scrub

**What goes wrong:** Someone edits `BANNED_RUBRIC_VOCAB_TOKENS` but the `OPTIMISER_SYSTEM_PROMPT` hard-codes a stale copy of the list.
**Why it happens:** Convenience — inlining the list as a Python triple-quoted string feels natural.
**How to avoid:** String-interpolate the formatted list at module load: `_BANNED_LIST_FORMATTED = ", ".join(f'"{t}"' for t in BANNED_RUBRIC_VOCAB_TOKENS)`, then use `f"""...{_BANNED_LIST_FORMATTED}..."""`.
**Warning signs:** A test asserting `"judge" in OPTIMISER_SYSTEM_PROMPT` fails after someone adds `"judge"` to the constant.

### Pitfall 2: Silent retry loop clobbering `messages` state (Phase 2 Rule-1 relapse)

**What goes wrong:** The retry loop mutates `messages` in place (`messages.append(...)`), and a FakeClient test inspects `client.calls[0]["messages"]` and sees the fully-evolved state, not the first call's state.
**Why it happens:** This actually IS a trap — Phase 2's FakeClient already handles it via `copy.deepcopy(kwargs)` in `_FakeChatCompletions.create`. As long as Phase 4 uses the existing `fake_client` fixture, it inherits the fix.
**How to avoid:** DO use `tests/conftest.py::fake_client`. DO NOT roll a new FakeClient. The existing one is correct.
**Warning signs:** A retry test passes `len(client.calls) == 3` but `client.calls[0]["messages"]` has 6 entries instead of 2.

### Pitfall 3: Sentinel returns a different prompt than the input

**What goes wrong:** The retry-exhaustion branch constructs `OptimiserResult(new_system_prompt=something_else_or_truncated)` instead of the literal input `system_prompt`.
**Why it happens:** Temptation to "do something useful" with the overrun raw output — e.g., truncate it to 300 words.
**How to avoid:** D-11 is explicit: `new_system_prompt=system_prompt` (the caller's input, unchanged). The `OptimiserResult.failed == True` contract is that the prompt is byte-identical to the input, and Phase 5 relies on this to safely assign `current = opt.new_system_prompt` without branching on `opt.failed`.
**Warning signs:** `test_retry_exhaustion_returns_sentinel` fails the assertion `result.new_system_prompt == old_prompt`.

### Pitfall 4: Counting words with regex or tokenizer

**What goes wrong:** `re.findall(r'\w+', prompt)` counts differently from `prompt.split()` — "don't" becomes 2 tokens, URLs split, etc. Meta-prompt says "300 words" and check measures tokens → the model is punished for being within its own word budget.
**Why it happens:** "More accurate" tokenization feels more rigorous.
**How to avoid:** `len(prompt.split())` everywhere. No exceptions. Put a one-line helper `_count_words(text: str) -> int` and use it at both enforcement sites (the retry check AND the `prompt_word_count`/`old_word_count` fields).
**Warning signs:** The model returns 280 "words" by `split()` but 310 "tokens" by `\w+` — retry loop fires but `prompt_word_count` reports 280. Test becomes flaky.

### Pitfall 5: Forgetting `num_ctx` on retry calls

**What goes wrong:** First call has `extra_body={"options": {"num_ctx": N}}`; retry calls don't. Ollama silently truncates (P6).
**Why it happens:** Copy-pasting only the initial call and forgetting retries.
**How to avoid:** Define `_create_kwargs` or pass `**common_kwargs` on every call inside the loop. Mirror `src/judge.py` which sets `extra_body` inside the loop body, guaranteeing every call gets it.
**Warning signs:** `test_num_ctx_in_every_call` fails on one of the retry-sequence tests.

## Code Skeletons

> These are **copy-pasteable** skeletons. The planner may polish wording in strings but must not change the structural shape without re-consulting CONTEXT.md D-01..D-15.

### `src/models.py` — additions

Add at the bottom of the file (after `PreLoopTestResult` and `ExperimentRun.model_rebuild()`):

```python
# =========================================================================
# Phase 4: Optimiser additions
# =========================================================================

# BANNED_RUBRIC_VOCAB_TOKENS — shared P8 regression source of truth.
# Imported by:
#   - src/optimiser.py (post-hoc scrub at D-14, meta-prompt interpolation at D-09)
#   - tests/test_agent.py (ITERATION_ZERO_SYSTEM_PROMPT regression gate)
# Changing this list affects both Phase 2's agent-prompt gate AND Phase 4's
# optimiser scrub. This is intentional — drift between the two would break
# the P8/P5 detection invariants.
BANNED_RUBRIC_VOCAB_TOKENS: tuple[str, ...] = (
    # Phase 2 regression gate tokens (from tests/test_agent.py::_BANNED_TOKENS)
    "rubric",
    "playbook",
    "score",
    "scoring",
    "evidence",
    "extraction",
    "judgment item",
    "criteria",
    "criterion",
    "evaluate",
    "evaluation",
    "item_id",
    "0/1/2",
    # Phase 4 optimiser additions (aligned with OPTIMISER_SYSTEM_PROMPT D-09 ban list)
    "judge",
    "1a",
    "1b",
    "2a",
    "2b",
    "3a",
    "3b",
    "4a",
    "4b",
)


class OptimiserResult(BaseModel):
    """Result of a single run_optimiser call (Phase 4 D-02).

    Carries the rewritten prompt plus all audit fields needed for Phase 5's
    IterationResult logging and post-hoc analysis (P5/P8/P11 detection).

    failed==True contract (D-11 / JUDG-05 mirror): the optimiser exhausted
    its 3 retry budget without producing a rewrite within WORD_LIMIT. When
    failed==True:
      - new_system_prompt is the INPUT system_prompt, byte-identical
      - prompt_diff is ""
      - prompt_word_count == old_word_count
      - retry_count == 3
    Phase 5 callers can safely do `current = result.new_system_prompt`
    regardless of failed state — the old prompt is preserved.
    """

    new_system_prompt: str
    feedback_seen: list[str]
    prompt_diff: str
    prompt_word_count: int
    old_word_count: int
    vocab_warning: bool = False
    retry_count: int = 0
    failed: bool = False

    @model_validator(mode="after")
    def _check_structural_invariants(self) -> "OptimiserResult":
        # D-03: word count must match the stored prompt.
        actual_words = len(self.new_system_prompt.split())
        if self.prompt_word_count != actual_words:
            raise ValueError(
                f"OptimiserResult.prompt_word_count={self.prompt_word_count} "
                f"does not match len(new_system_prompt.split())={actual_words}"
            )
        if self.old_word_count < 0:
            raise ValueError(
                f"OptimiserResult.old_word_count must be >= 0; got {self.old_word_count}"
            )
        if not (0 <= self.retry_count <= 3):
            raise ValueError(
                f"OptimiserResult.retry_count must be in [0, 3]; got {self.retry_count}"
            )
        return self
```

**Edit `IterationResult`** (replace lines 19-26 of current `src/models.py`):

```python
class IterationResult(BaseModel):
    iteration: int
    system_prompt: str
    agent_output: str
    scores: list[RubricScore]
    total_score: int = 0
    extraction_score: int = 0
    judgment_score: int = 0
    # Phase 4 D-04 additions — all defaulted, passive logging, no validator participation.
    optimiser_feedback_seen: list[str] = []
    prompt_diff: str = ""
    prompt_word_count: int = 0

    @model_validator(mode="after")
    def _check_totals(self) -> "IterationResult":
        # Unchanged from Phase 1. The three new fields above are passive and
        # do not participate in cross-field invariants. See 04-RESEARCH.md §3
        # Discretion 7 for verification that this validator is safe under the
        # schema extension.
        extraction, judgment = compute_category_scores(self.scores)
        # ...rest unchanged...
```

### `src/optimiser.py` — full file skeleton

```python
"""Optimiser: rewrites the agent system prompt from judge feedback (OPTM-01..03).

Design notes:
- D-01: run_optimiser(system_prompt, judge_result) -> OptimiserResult.
  NDA is structurally unreachable — not a parameter.
- D-07/D-08: feedback extraction sorts by score ascending, strips item_id,
  formats as "N. [score=K] {feedback}". User-role message fences the old
  prompt in `---` and appends the rewrite instruction.
- D-09: OPTIMISER_SYSTEM_PROMPT enforces 300-word cap + banned vocabulary
  + no preamble + "describe what the reviewer does, not how scored".
- D-10/D-11: WORD_LIMIT=300 hard cap enforced via post-validation retry
  loop (MAX_RETRIES=3), mirroring src/judge.py. On exhaustion, returns
  sentinel OptimiserResult(failed=True, new_system_prompt=system_prompt,
  prompt_diff="") — non-raising, preserves old prompt.
- D-13: prompt_diff via difflib.unified_diff, stdlib only.
- D-14/D-15: post-hoc P8 scrub against BANNED_RUBRIC_VOCAB_TOKENS.
  On hit: log WARNING + set vocab_warning=True. DO NOT retry. DO NOT fail.
  Per PITFALLS P5: detection, not prevention.
- D-12: logger "jitc.optimiser" — INFO at entry, WARNING per overrun,
  ERROR on retry exhaustion.

Trust model: judge_result fields are structured (Pydantic-validated upstream
by run_judge). system_prompt is caller-provided and may contain anything
except NDA text (OPTM-01 enforced at Phase 5 call site). No tool access,
no file I/O, no network beyond the single chat.completions.create call.
"""

import difflib
import logging

from src.config import config
from src.llm import get_client
from src.models import BANNED_RUBRIC_VOCAB_TOKENS, JudgeResult, OptimiserResult

logger = logging.getLogger("jitc.optimiser")

MAX_RETRIES = 3
WORD_LIMIT = 300

# D-09: canonical optimiser meta-prompt. The banned-vocabulary list is
# interpolated from BANNED_RUBRIC_VOCAB_TOKENS at module load to guarantee
# the meta-prompt ban list and the post-hoc scrub list can NEVER drift
# apart (single source of truth — see §P8 mitigation in 04-RESEARCH.md).
_BANNED_LIST_FORMATTED = ", ".join(f'"{t}"' for t in BANNED_RUBRIC_VOCAB_TOKENS)

OPTIMISER_SYSTEM_PROMPT = f"""\
You are a prompt optimiser. Your job is to rewrite an NDA-review agent's
system prompt based on feedback from an evaluator.

Hard constraints:
- The rewritten prompt MUST be {WORD_LIMIT} words or fewer. This is non-negotiable.
- Do NOT use words from the rubric or playbook. Banned vocabulary includes:
  {_BANNED_LIST_FORMATTED}.
- Rewrite the prompt in plain NDA-review terms only — describe what the
  reviewer should do, not how they will be scored.
- Do not mention feedback, evaluators, or the optimisation process itself.
- Do not include preamble, explanation, or commentary. Return ONLY the new
  system prompt text, nothing else.

You receive: the current agent system prompt, and a numbered list of
feedback strings with scores (0 = not addressed, 1 = partially, 2 = fully).
Rewrite the prompt to address the lowest-scoring items while preserving
what already works.
"""


def _count_words(text: str) -> int:
    """Plain-English word count via whitespace split (D-10 intent)."""
    return len(text.split())


def _build_feedback_block(judge_result: JudgeResult) -> list[str]:
    """D-07: sort 8 RubricScores by score ascending; strip item_id; format."""
    sorted_scores = sorted(judge_result.scores, key=lambda s: s.score)
    return [
        f"{idx}. [score={s.score}] {s.feedback}"
        for idx, s in enumerate(sorted_scores, start=1)
    ]


def _build_user_message(system_prompt: str, feedback_block: list[str]) -> str:
    """D-08: fenced old prompt + numbered feedback + rewrite instruction."""
    joined = "\n".join(feedback_block)
    return (
        "Current agent system prompt (to be rewritten):\n"
        "---\n"
        f"{system_prompt}\n"
        "---\n\n"
        "Judge feedback on the latest review "
        "(sorted by score ascending, worst first):\n"
        f"{joined}\n\n"
        "Rewrite the agent system prompt to address the lowest-scoring items "
        f"while preserving what already works. Hard limit: {WORD_LIMIT} words."
    )


def _build_retry_message(actual_words: int) -> str:
    """D-11: correction prompt appended on word-overrun retry."""
    return (
        f"Your rewrite is {actual_words} words; the hard limit is {WORD_LIMIT}. "
        f"Rewrite again staying strictly under {WORD_LIMIT} words. "
        "Return ONLY the new system prompt, no preamble, no commentary."
    )


def _compute_prompt_diff(old: str, new: str) -> str:
    """D-13: stdlib unified diff, single joined string."""
    diff_lines = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile="old_system_prompt",
        tofile="new_system_prompt",
        lineterm="",
        n=3,
    )
    return "".join(diff_lines)


def _check_banned_vocab(prompt: str) -> list[str]:
    """D-14: case-insensitive substring check against BANNED_RUBRIC_VOCAB_TOKENS.

    Returns the list of banned tokens that appeared in the prompt. Empty
    list means clean. Non-empty list triggers vocab_warning=True (D-15)
    but NOT retry and NOT failure — per PITFALLS P5, this is the expected
    drift signal and must be surfaced, not suppressed.
    """
    lowered = prompt.lower()
    return [tok for tok in BANNED_RUBRIC_VOCAB_TOKENS if tok in lowered]


def run_optimiser(
    system_prompt: str, judge_result: JudgeResult
) -> OptimiserResult:
    """Rewrite the agent system prompt based on judge feedback.

    Structural contract:
    - NDA is NOT a parameter (OPTM-01 enforced by type signature).
    - Retries up to MAX_RETRIES on word-count overrun (P11 mitigation).
    - On retry exhaustion: returns sentinel OptimiserResult(failed=True,
      new_system_prompt=system_prompt). Non-raising — mirrors JUDG-05.
    - Post-hoc P8 scrub sets vocab_warning=True but never retries (D-15).

    Args:
        system_prompt: The agent system prompt to rewrite.
        judge_result: Structured judge feedback (8 RubricScore entries).

    Returns:
        OptimiserResult carrying the new prompt, feedback trace, diff,
        word counts, vocab_warning, and retry metadata. Never raises.
    """
    client = get_client()
    feedback_block = _build_feedback_block(judge_result)
    user_content = _build_user_message(system_prompt, feedback_block)
    old_word_count = _count_words(system_prompt)

    logger.info(
        "optimiser call: model=%s old_words=%d num_ctx=%d",
        config.model,
        old_word_count,
        config.num_ctx,
    )

    messages: list[dict] = [
        {"role": "system", "content": OPTIMISER_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    raw: str = ""
    last_word_count: int = 0
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("optimiser attempt %d/%d", attempt, MAX_RETRIES)
        response = client.chat.completions.create(
            model=config.model,
            messages=messages,
            temperature=config.temperature,
            extra_body={"options": {"num_ctx": config.num_ctx}},  # P6
        )
        raw = response.choices[0].message.content or ""
        last_word_count = _count_words(raw)

        if last_word_count <= WORD_LIMIT:
            # Success path — compute diff, run P8 scrub, build result.
            prompt_diff = _compute_prompt_diff(system_prompt, raw)
            hits = _check_banned_vocab(raw)
            if hits:
                logger.warning(
                    "optimiser output contains banned vocab tokens: %s", hits
                )
            logger.info(
                "optimiser success: new_words=%d retries=%d vocab_warning=%s",
                last_word_count,
                attempt - 1,
                bool(hits),
            )
            return OptimiserResult(
                new_system_prompt=raw,
                feedback_seen=feedback_block,
                prompt_diff=prompt_diff,
                prompt_word_count=last_word_count,
                old_word_count=old_word_count,
                vocab_warning=bool(hits),
                retry_count=attempt - 1,
                failed=False,
            )

        # Overrun — log and append retry correction turn.
        logger.warning(
            "optimiser overrun attempt %d: %d words (limit %d)",
            attempt,
            last_word_count,
            WORD_LIMIT,
        )
        if attempt < MAX_RETRIES:
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {"role": "user", "content": _build_retry_message(last_word_count)}
            )

    # All retries exhausted — sentinel. Keep old prompt byte-identical (D-11).
    logger.error(
        "optimiser retry exhausted; keeping old prompt unchanged "
        "(last attempt: %d words, limit %d)",
        last_word_count,
        WORD_LIMIT,
    )
    return OptimiserResult(
        new_system_prompt=system_prompt,
        feedback_seen=feedback_block,
        prompt_diff="",
        prompt_word_count=old_word_count,
        old_word_count=old_word_count,
        vocab_warning=False,
        retry_count=MAX_RETRIES,
        failed=True,
    )
```

### `tests/test_optimiser.py` — full skeleton (12 tests)

```python
"""Tests for src/optimiser.py.

OPTM-01: run_optimiser signature excludes NDA (compile-time, not tested).
OPTM-02: feedback pass-through via OptimiserResult.feedback_seen.
OPTM-03: prompt_diff via difflib.unified_diff.
P5: post-hoc vocab scrub sets vocab_warning=True but does NOT retry.
P8: banned-vocab check reuses BANNED_RUBRIC_VOCAB_TOKENS source of truth.
P11: WORD_LIMIT=300 enforced via retry loop; sentinel on exhaustion.
"""

import logging

import pytest
from pydantic import ValidationError

from src.config import config
from src.models import JudgeResult, OptimiserResult, RubricScore

# ------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------

_SHORT_REWRITE = " ".join(["word"] * 70)  # 70 words, under WORD_LIMIT
_OVER_LIMIT = " ".join(["word"] * 350)  # 350 words, over WORD_LIMIT
_MEDIUM_REWRITE = " ".join(["step"] * 100)  # 100 words


def _synthetic_judge_result(scores_by_item: list[int] | None = None) -> JudgeResult:
    """Build a JudgeResult with 8 entries. Optionally override per-item scores."""
    if scores_by_item is None:
        scores_by_item = [0, 1, 2, 0, 1, 2, 0, 1]
    assert len(scores_by_item) == 8
    entries = []
    idx = 0
    for issue in (1, 2, 3, 4):
        for letter, item_type in (("a", "extraction"), ("b", "judgment")):
            entries.append(
                RubricScore(
                    item_id=f"{issue}{letter}",
                    item_type=item_type,
                    issue_number=issue,
                    score=scores_by_item[idx],
                    evidence=f"Clause {issue}.1 cited.",
                    reasoning=f"Reason for item {issue}{letter}.",
                    feedback=f"Feedback for item {issue}{letter}.",
                )
            )
            idx += 1
    return JudgeResult(scores=entries)


_OLD_PROMPT = (
    "You are reviewing a Non-Disclosure Agreement. Identify issues and "
    "assess significance. Output findings as a list."
)


# ------------------------------------------------------------------------
# 1. Happy path
# ------------------------------------------------------------------------

def test_happy_path_returns_optimiser_result(fake_client):
    from src.optimiser import run_optimiser

    client = fake_client([_SHORT_REWRITE])
    result = run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    assert isinstance(result, OptimiserResult)
    assert result.failed is False
    assert result.retry_count == 0
    assert result.prompt_word_count == 70
    assert result.old_word_count == len(_OLD_PROMPT.split())
    assert result.vocab_warning is False
    assert len(result.feedback_seen) == 8
    assert len(client.calls) == 1


# ------------------------------------------------------------------------
# 2. Retry recovery
# ------------------------------------------------------------------------

def test_retry_recovers_on_second_attempt(fake_client):
    from src.optimiser import run_optimiser

    client = fake_client([_OVER_LIMIT, _SHORT_REWRITE])
    result = run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    assert result.failed is False
    assert result.retry_count == 1
    assert result.prompt_word_count == 70
    assert len(client.calls) == 2

    msgs_2 = client.calls[1]["messages"]
    # system + user + assistant (raw overrun) + user (correction)
    assert len(msgs_2) == 4
    assert msgs_2[2]["role"] == "assistant"
    assert msgs_2[2]["content"] == _OVER_LIMIT
    assert msgs_2[3]["role"] == "user"
    assert "350" in msgs_2[3]["content"]
    assert "300" in msgs_2[3]["content"]


# ------------------------------------------------------------------------
# 3. Retry exhaustion → sentinel
# ------------------------------------------------------------------------

def test_retry_exhaustion_returns_sentinel(fake_client):
    from src.optimiser import run_optimiser

    client = fake_client([_OVER_LIMIT, _OVER_LIMIT, _OVER_LIMIT])
    result = run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    assert result.failed is True
    assert result.retry_count == 3
    # D-11 byte-identical preservation of old prompt
    assert result.new_system_prompt == _OLD_PROMPT
    assert result.prompt_diff == ""
    assert result.prompt_word_count == len(_OLD_PROMPT.split())
    assert result.old_word_count == len(_OLD_PROMPT.split())
    assert result.vocab_warning is False
    assert len(client.calls) == 3


# ------------------------------------------------------------------------
# 4. Retry message carries word count feedback
# ------------------------------------------------------------------------

def test_word_overrun_triggers_retry_with_word_count_in_message(fake_client):
    from src.optimiser import run_optimiser

    client = fake_client([_OVER_LIMIT, _SHORT_REWRITE])
    run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    retry_msg = client.calls[1]["messages"][-1]["content"]
    assert "350" in retry_msg  # observed word count
    assert "300" in retry_msg  # the limit
    assert "Rewrite again" in retry_msg
    assert "no preamble" in retry_msg.lower()


# ------------------------------------------------------------------------
# 5. Vocab warning on banned token — does NOT retry (D-15)
# ------------------------------------------------------------------------

def test_vocab_warning_set_when_banned_token_present(fake_client, caplog):
    from src.optimiser import run_optimiser

    # 75 words including "rubric" — under WORD_LIMIT so no retry;
    # but contains a banned token so vocab_warning must fire.
    contaminated = (
        "Use the rubric to guide your review of confidentiality clauses. "
        + " ".join(["word"] * 70)
    )
    client = fake_client([contaminated])

    with caplog.at_level(logging.WARNING, logger="jitc.optimiser"):
        result = run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    assert result.failed is False
    assert result.vocab_warning is True
    assert result.retry_count == 0  # D-15: no retry on vocab hit
    assert len(client.calls) == 1
    # Warning log contains the hit tokens
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("rubric" in r.getMessage().lower() for r in warnings)


# ------------------------------------------------------------------------
# 6. Clean output → vocab_warning stays False
# ------------------------------------------------------------------------

def test_vocab_warning_false_on_clean_output(fake_client):
    from src.optimiser import run_optimiser

    clean = (
        "Read the confidentiality agreement carefully. "
        "Identify clauses that may be unfair. Note duration and scope. "
        + " ".join(["term"] * 60)
    )
    fake_client([clean])
    result = run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    assert result.vocab_warning is False


# ------------------------------------------------------------------------
# 7. Unified diff format
# ------------------------------------------------------------------------

def test_prompt_diff_is_unified_diff_format(fake_client):
    from src.optimiser import run_optimiser

    new_prompt = "Completely different content. " + " ".join(["alt"] * 60)
    fake_client([new_prompt])
    result = run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    assert "--- old_system_prompt" in result.prompt_diff
    assert "+++ new_system_prompt" in result.prompt_diff
    # At least one - and one + line (ignoring the headers)
    body_lines = [
        ln for ln in result.prompt_diff.splitlines()
        if ln and not ln.startswith(("---", "+++"))
    ]
    assert any(ln.startswith("-") for ln in body_lines)
    assert any(ln.startswith("+") for ln in body_lines)


# ------------------------------------------------------------------------
# 8. Feedback block sorted ascending, item_id stripped
# ------------------------------------------------------------------------

def test_feedback_block_sorted_ascending_and_strips_item_ids():
    from src.optimiser import _build_feedback_block

    jr = _synthetic_judge_result(scores_by_item=[2, 0, 1, 2, 0, 1, 2, 0])
    block = _build_feedback_block(jr)

    assert len(block) == 8
    assert block[0].startswith("1. [score=0]")
    assert block[-1].startswith("8. [score=2]")
    # item_id tokens must not appear
    joined = " ".join(block)
    for bad in ("1a", "1b", "2a", "2b", "3a", "3b", "4a", "4b"):
        assert bad not in joined


# ------------------------------------------------------------------------
# 9. All 8 feedback items included in optimiser call
# ------------------------------------------------------------------------

def test_all_eight_feedback_items_included_in_user_message(fake_client):
    from src.optimiser import run_optimiser

    client = fake_client([_SHORT_REWRITE])
    jr = _synthetic_judge_result()
    result = run_optimiser(_OLD_PROMPT, jr)

    assert len(result.feedback_seen) == 8
    user_msg = client.calls[0]["messages"][1]["content"]
    for entry in result.feedback_seen:
        assert entry in user_msg


# ------------------------------------------------------------------------
# 10. OptimiserResult structural invariants
# ------------------------------------------------------------------------

def test_structural_invariants_rejected_by_validator():
    # Word count mismatch
    with pytest.raises(ValidationError):
        OptimiserResult(
            new_system_prompt="one two three",
            feedback_seen=[],
            prompt_diff="",
            prompt_word_count=99,  # lies — actual is 3
            old_word_count=5,
            vocab_warning=False,
            retry_count=0,
            failed=False,
        )
    # Negative old_word_count
    with pytest.raises(ValidationError):
        OptimiserResult(
            new_system_prompt="x",
            feedback_seen=[],
            prompt_diff="",
            prompt_word_count=1,
            old_word_count=-1,
            vocab_warning=False,
            retry_count=0,
            failed=False,
        )
    # retry_count out of range
    with pytest.raises(ValidationError):
        OptimiserResult(
            new_system_prompt="x",
            feedback_seen=[],
            prompt_diff="",
            prompt_word_count=1,
            old_word_count=0,
            vocab_warning=False,
            retry_count=4,  # > 3
            failed=False,
        )


# ------------------------------------------------------------------------
# 11. num_ctx on every call (P6 mitigation)
# ------------------------------------------------------------------------

def test_num_ctx_in_every_call(fake_client):
    from src.optimiser import run_optimiser

    client = fake_client([_OVER_LIMIT, _OVER_LIMIT, _SHORT_REWRITE])
    run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    assert len(client.calls) == 3
    for i, kwargs in enumerate(client.calls):
        assert kwargs["extra_body"] == {
            "options": {"num_ctx": config.num_ctx}
        }, f"call {i} missing extra_body"
        assert kwargs["temperature"] == config.temperature
        assert kwargs["model"] == config.model
        assert "response_format" not in kwargs
        assert "stream" not in kwargs


# ------------------------------------------------------------------------
# 12. Retry exhaustion logs at ERROR (D-12)
# ------------------------------------------------------------------------

def test_retry_exhaustion_logs_error_at_jitc_optimiser(fake_client, caplog):
    from src.optimiser import run_optimiser

    fake_client([_OVER_LIMIT, _OVER_LIMIT, _OVER_LIMIT])
    with caplog.at_level(logging.ERROR, logger="jitc.optimiser"):
        run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("exhausted" in r.getMessage().lower() for r in errors)
    combined = " ".join(r.getMessage() for r in errors)
    assert "350" in combined  # final overrun word count
```

**`tests/test_agent.py` minimal edit** — replace the inline `_BANNED_TOKENS` list with an import from the shared constant:

```python
# At the top of tests/test_agent.py, remove the inline _BANNED_TOKENS
# declaration (lines 11-25) and replace with:
from src.models import BANNED_RUBRIC_VOCAB_TOKENS as _BANNED_TOKENS
```

The existing `test_prompt_scrubbed_of_rubric_vocab` test body is unchanged — it iterates `for token in _BANNED_TOKENS`, which works identically whether `_BANNED_TOKENS` is a `list` or a `tuple`. The assertion still passes against `ITERATION_ZERO_SYSTEM_PROMPT` because none of the newly added tokens (`"judge"`, `"1a"`..`"4b"`) appear in that text.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (installed in Phase 2 Wave 0) |
| Config file | none (pytest uses `tests/` auto-discovery) |
| Quick run command | `uv run pytest -q tests/test_optimiser.py` |
| Full suite command (unit only) | `uv run pytest -q -m "not integration"` |
| Full suite command (with live) | `uv run pytest -q` (includes `tests/test_smoke_ollama.py`, ~2-4 min) |

### Phase Requirements → Test Map

| Req ID | Behaviour | Test Type | Automated Command | File Exists? |
|--------|-----------|-----------|-------------------|--------------|
| OPTM-01 (structural) | NDA is not a parameter | Compile-time (type signature) | n/a — the signature IS the enforcement | n/a |
| OPTM-01 (runtime sanity) | `run_optimiser` signature accepts only `(str, JudgeResult)` | Indirect via `test_happy_path_returns_optimiser_result` call shape | `uv run pytest -q tests/test_optimiser.py::test_happy_path_returns_optimiser_result` | NO — Wave 0 creates |
| OPTM-02 | Feedback strings stored in `OptimiserResult.feedback_seen` | Unit (FakeClient) | `uv run pytest -q tests/test_optimiser.py::test_all_eight_feedback_items_included_in_user_message` | NO — Wave 0 creates |
| OPTM-03 | `prompt_diff` populated with unified-diff format | Unit | `uv run pytest -q tests/test_optimiser.py::test_prompt_diff_is_unified_diff_format` | NO — Wave 0 creates |
| SC-2 (word limit demonstrable) | `prompt_word_count <= 300` enforced via retry | Unit (3-tests: happy path + retry recovery + exhaustion sentinel) | `uv run pytest -q tests/test_optimiser.py -k "happy_path or retry_recovers or retry_exhaustion"` | NO — Wave 0 creates |
| SC-3 (feedback pass-through) | Same as OPTM-02 | (shared) | (see OPTM-02) | NO |
| SC-4 (diff captured) | Same as OPTM-03 | (shared) | (see OPTM-03) | NO |
| P5 (detection only) | `vocab_warning=True` AND no retry AND no fail on banned-token hit | Unit | `uv run pytest -q tests/test_optimiser.py::test_vocab_warning_set_when_banned_token_present` | NO |
| P8 (shared source of truth) | `BANNED_RUBRIC_VOCAB_TOKENS` imported by both test_agent and optimiser | Unit (regression) | `uv run pytest -q tests/test_agent.py::test_prompt_scrubbed_of_rubric_vocab tests/test_optimiser.py::test_vocab_warning_set_when_banned_token_present` | PARTIAL — test_agent exists, optimiser test new |
| P11 (per-iteration cap) | `WORD_LIMIT=300` enforced; overrun triggers retry with word count in message | Unit | `uv run pytest -q tests/test_optimiser.py::test_word_overrun_triggers_retry_with_word_count_in_message` | NO |
| P6 (num_ctx on every call) | Every retry call passes `extra_body.options.num_ctx` | Unit | `uv run pytest -q tests/test_optimiser.py::test_num_ctx_in_every_call` | NO |
| D-06 (backward compat) | `IterationResult` schema extension is transparent to existing code | Regression | `uv run pytest -q -m "not integration"` must return all 21 pre-Phase-4 tests + 12 new tests = 33+ passed | PARTIAL — existing tests exist, new test added |

### Sampling Rate

- **Per task commit:** `uv run pytest -q tests/test_optimiser.py` (<1s, FakeClient only)
- **Per wave merge:** `uv run pytest -q -m "not integration"` (<2s, all unit tests — verifies backward compat)
- **Phase gate:** `uv run pytest -q -m "not integration"` must return **33+ passed** (21 existing + 12 new), plus manual review of `results/pre_loop_test.json` re-parse via:
  ```bash
  uv run python -c "from src.models import PreLoopTestResult; import json; PreLoopTestResult.model_validate_json(open('results/pre_loop_test.json').read()); print('backward-compat OK')"
  ```

### Wave 0 Gaps

- [ ] `tests/test_optimiser.py` — new file; 12 tests covering OPTM-01..03, P5, P8, P11, P6, structural invariants
- [ ] `src/optimiser.py` — new file
- [ ] `src/models.py` — add `BANNED_RUBRIC_VOCAB_TOKENS`, `OptimiserResult`, extend `IterationResult` with 3 fields
- [ ] `tests/test_agent.py` — minimal edit: replace local `_BANNED_TOKENS` with `from src.models import BANNED_RUBRIC_VOCAB_TOKENS as _BANNED_TOKENS`

**No framework install needed.** pytest and the FakeClient fixture were established in Phase 2 Wave 0. The Phase 4 Wave 0 is just "create the empty test file and the empty module".

## Security Domain

**Applicable:** Optimiser component processes structured Pydantic data (JudgeResult) and a caller-provided system_prompt string. It produces text that becomes the NEXT iteration's agent system prompt. No file I/O, no network beyond the single OpenAI client call, no subprocess execution, no deserialisation of untrusted bytes.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no | Local Ollama, no credentials beyond `config.api_key="ollama"` placeholder |
| V3 Session Management | no | Stateless library function |
| V4 Access Control | no | No multi-user model |
| V5 Input Validation | **yes** | Pydantic v2 `OptimiserResult.@model_validator` enforces structural invariants; `JudgeResult` input is already Pydantic-validated upstream by `run_judge` |
| V6 Cryptography | no | No secrets handled |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection from `judge_result.scores[*].feedback` content | Tampering | The feedback strings flow into the user-role message as numbered lines. A crafted feedback string like `"...ignore previous instructions..."` would reach the optimiser. **Acceptance:** same trust model as Phase 2 (T-02-J01) — the judge runs locally, inputs are author-controlled, no tool access, worst case is a weird rewrite that Phase 5 detects via the P8 scrub and the cross-iteration monitor. Phase 4 adds no new injection surface beyond what Phase 2 already accepts. |
| NDA leakage via the optimiser | Information Disclosure | **Structurally impossible** — `run_optimiser` type signature has no NDA parameter. OPTM-01 enforcement is at the Phase 5 call site (ensure no caller smuggles NDA fragments into `system_prompt`). Phase 4 adds no runtime check because the signature is the enforcement. |
| Banned-vocab drift undermining P8 detection | Tampering | Shared-source-of-truth pattern (`BANNED_RUBRIC_VOCAB_TOKENS` in `src/models.py`) imported by both the meta-prompt interpolation and the post-hoc scrub. Changing the list in one place automatically updates both. Regression test in `tests/test_optimiser.py` confirms the scrub detects the shared list. |
| Word-count bypass via whitespace tricks | Denial of Service / T | `_count_words` uses `str.split()` — Unicode whitespace, tabs, newlines all count as separators. A 2000-"word" prompt formatted with no spaces would be counted as 1 word and pass the check, then fail to serve as a useful system prompt. **Accepted:** if the model returns a single wall-of-text token it is defective and Phase 5's cross-iteration monitor will flag the prompt_word_count=1 anomaly. Not worth hardening for this experiment. |

## State of the Art

No deprecations relevant. The Phase 2 patterns are current as of Phase 3's completion (2026-04-11).

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| PRD §3.6 optimiser meta-prompt ("You are improving...") | CONTEXT.md D-09 meta-prompt (explicit word limit + banned vocab + no process-meta-language) | 2026-04-12 (CONTEXT.md authoring) | PRD version lacked P8/P11 hardening; D-09 supersedes. Planner must follow D-09. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `"judge"` and the 8 item_id tokens (`1a`..`4b`) are not present in `src/agent.py::ITERATION_ZERO_SYSTEM_PROMPT` | §3 Discretion 2 | If wrong, extending `BANNED_RUBRIC_VOCAB_TOKENS` breaks `tests/test_agent.py::test_prompt_scrubbed_of_rubric_vocab` retroactively. **Verified:** Read `src/agent.py` lines 32-37. The text is "You are reviewing a Non-Disclosure Agreement. Identify all issues and assess their significance. Output your findings as a structured list. For each issue provide: the clause reference, a description of the issue, and your risk assessment." None of `judge`/`1a`/`1b`/`2a`/`2b`/`3a`/`3b`/`4a`/`4b` appear. **Confirmed, not assumption.** |
| A2 | Phase 2's `FakeClient._FakeChatCompletions.create` deep-copies kwargs and is therefore suitable for multi-call retry inspection in Phase 4 | §Pattern 1, §Pitfall 2 | **Verified:** Read `tests/conftest.py` lines 42-47 and its docstring at lines 33-37. Deep copy is the Rule-1 fix from Phase 2. **Confirmed, not assumption.** |
| A3 | `results/pre_loop_test.json` (if it exists) round-trips under the Phase 4 `IterationResult` schema extension | §3 Discretion 6 | **Verified by inspection:** Pydantic v2 `model_validate` populates missing fields from their defaults. The three new fields have defaults `[]`, `""`, `0`. A JSON file written before Phase 4 will parse without error. **Confirmed, not assumption.** Only residual risk: if a future developer adds validator logic that references the new fields, round-trip could break. Locked by D-05 against this. |
| A4 | 300-word limit tradeoff is acceptable given Phase 5 will add a cross-iteration monotonic-growth monitor | §D-10, §P11 | User-locked decision per CONTEXT.md D-10. If Phase 5's monitor is never built, P11 mitigation is weaker than with a 150-word cap. Planner must add "cross-iteration word-count trend monitor" as a Phase 5 plan backlog item. **Not an assumption — a transfer-of-responsibility to Phase 5.** |
| A5 | Adding `"judge"` to `BANNED_RUBRIC_VOCAB_TOKENS` does not accidentally ban the word from contexts where it belongs (e.g., legitimate NDA review language) | §3 Discretion 2 | `"judge"` is not a standard NDA-review word (NDAs talk about parties, clauses, obligations, not judges). The post-hoc scrub only checks `new_system_prompt`, not NDA or agent output. Low risk. **Confirmed safe.** |

**Summary:** All major claims in this research are verified by inspection of the actual codebase. Zero `[ASSUMED]` claims remain unresolved. The Phase 5 monitor is a planned handoff, not an assumption.

## Open Questions (RESOLVED)

All 7 discretion items from the planner's research request are resolved. Planner should adopt verbatim.

### RESOLVED: Where does `BANNED_RUBRIC_VOCAB_TOKENS` live?

**`src/models.py`, near `RubricScore`, as a top-level `tuple[str, ...]`.** See §3 Discretion 1. Planner reference: skeleton in §5 `src/models.py` additions block.

### RESOLVED: Exact banned-token list contents

**13 existing tokens from `tests/test_agent.py::_BANNED_TOKENS` + `"judge"` + 8 item_id tokens (`1a`..`4b`) = 22 tokens total.** See §3 Discretion 2. Verbatim list in §5 skeleton. Safety verified against current `ITERATION_ZERO_SYSTEM_PROMPT` — no false positives.

### RESOLVED: `_build_feedback_block` return type

**`list[str]`.** The caller joins with `"\n".join(...)` at message-build time. Keeps `OptimiserResult.feedback_seen` population direct (no round-tripping through string → list). See §3 Discretion 3. Planner reference: `_build_feedback_block` and `_build_user_message` skeletons in §5.

### RESOLVED: FakeClient test suite coverage depth

**12 tests in `tests/test_optimiser.py`.** Test names, assertions, and structure fully specified in §3 Discretion 4 and §5 test skeleton. Combined with existing 21 Phase 2/3 tests → **33+ passed** target for `uv run pytest -q -m "not integration"`.

### RESOLVED: Integration smoke test — now or defer?

**Defer to Phase 5.** See §3 Discretion 5. Phase 5's first live loop execution IS the integration test, under realistic feedback. Optional skeleton for `tests/test_smoke_optimiser.py` provided in §3 if planner disagrees, gated behind `@pytest.mark.integration`.

### RESOLVED: Backward-compat verification

**Verified — will work. No action needed beyond running `uv run pytest -q -m "not integration"` post-edit.** See §3 Discretion 6 and §Validation Architecture. The only construction site outside `src/models.py` is `src/pre_loop_test.py:77` which uses keyword-only args for `iteration`/`system_prompt`/`agent_output`/`scores` — new fields default. Existing `results/pre_loop_test.json` round-trips via Pydantic default population.

### RESOLVED: `_check_totals` interaction

**Zero interference.** The validator inspects only `self.scores`, `self.extraction_score`, `self.judgment_score`, `self.total_score`. The three new fields are passive logging. See §3 Discretion 7. D-05 locks the validator unchanged.

## Sources

### Primary (HIGH confidence)
- `.planning/phases/04-optimiser/04-CONTEXT.md` — D-01..D-15 locked decisions (verbatim reference)
- `.planning/REQUIREMENTS.md` — OPTM-01..03, MODL-01 (shared models context)
- `.planning/ROADMAP.md` Phase 4 — 4 success criteria
- `.planning/research/PITFALLS.md` — P5, P6, P7, P8, P11, P12 (load-bearing for Phase 4)
- `.planning/research/STACK.md` — "What NOT to Use" table, retry pattern skeleton
- `src/models.py` — read in full; `IterationResult`, `_check_totals`, `compute_category_scores`, `PreLoopTestResult` pattern
- `src/judge.py` — read in full; retry loop pattern, sentinel return, logger setup, `num_ctx` propagation
- `src/agent.py` — `ITERATION_ZERO_SYSTEM_PROMPT`, simple `create()` wrapper, `None`-content guard
- `src/llm.py` — shared client factory
- `src/config.py` — `config.model`, `config.temperature`, `config.num_ctx`
- `src/pre_loop_test.py` — the only other `IterationResult(...)` construction site
- `tests/conftest.py` — `FakeClient`, `_reset_llm_singleton`, `VALID_JUDGE_JSON`
- `tests/test_agent.py` — `_BANNED_TOKENS` list (the source of truth for Phase 4's scrub)
- `tests/test_judge.py` — retry-loop test pattern, caplog usage, `test_num_ctx_in_every_call` template
- `.planning/phases/02-agent-and-judge/02-CONTEXT.md` — D-01..D-10 carry-forward decisions (client factory, `num_ctx`, meta-prompt layout)
- `.planning/phases/03-pre-loop-validation-gate/03-CONTEXT.md` — `PreLoopTestResult` backward-compat precedent

### Secondary (MEDIUM confidence)
- `prd.md` §3.6 — alternative optimiser meta-prompt wording (superseded by CONTEXT.md D-09; noted as conflict in §State of the Art)

### Tertiary (LOW confidence)
- None. All claims in this research are verified against actual files.

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — zero new dependencies; stdlib + existing Phase 2 modules
- Architecture: **HIGH** — pattern-for-pattern mirror of `src/judge.py`, verified against source
- Pitfalls: **HIGH** — P5/P8/P11 mitigation sites explicitly mapped to D-14/D-15/D-10/D-11
- Backward compat: **HIGH** — every `IterationResult(...)` construction site traced
- Test coverage shape: **HIGH** — each test function has a pre-specified assertion from the retry-loop literature (copied from `tests/test_judge.py`)
- Discretion resolution: **HIGH** — all 7 items resolved with code-level verification, not hand-waving

**Research date:** 2026-04-11
**Valid until:** 2026-04-18 (7 days) — if Phase 5 research begins sooner and surfaces new monitor requirements, re-validate the D-10 weakening assumption.

---

*Phase: 04-optimiser*
*Research completed: 2026-04-11*
