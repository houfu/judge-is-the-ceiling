---
phase: 02-agent-and-judge
plan: 03
subsystem: testing
tags: [pydantic, openai, ollama, retry, regex, logging, tdd]

# Dependency graph
requires:
  - phase: 02-agent-and-judge
    provides: "src/llm.get_client, src/config.num_ctx, tests FakeClient + VALID_JUDGE_JSON fixtures"
provides:
  - "run_judge(nda, agent_output, rubric, playbook) → JudgeResult with retry + graceful failure"
  - "_extract_json outermost-brace DOTALL regex handling ```json fences, prose preambles, and nested objects in one pass"
  - "_build_user_message with top-level # heading collision mitigation (D-07)"
  - "_retry_user_message bounded at MAX_ERROR_CHARS=800 with fixed reminder text"
  - "JUDGE_SYSTEM_PROMPT constant with single-example schema (D-09) and D-10 no-fences instruction"
  - "JudgeResult(scores=[]) graceful-failure sentinel contract for downstream consumers"
  - "Hardened FakeChatCompletions: deep-copies kwargs on capture so multi-call retry tests can inspect per-call history"
affects: [03-pre-loop-test, 05-loop, 04-optimiser]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-message judge layout: system = stable rules+schema+example, user = case data (D-05)"
    - "Retry-with-error-feedback loop: append (assistant raw, user correction) turns between attempts (P7)"
    - "Outermost-brace DOTALL regex for JSON extraction instead of separate fence-stripping step (P14)"
    - "Pydantic v2 single `except ValidationError` catches both JSON-decode AND schema failures (P12)"
    - "Graceful failure as sentinel instance (empty scores list) — never raise, always return JudgeResult (JUDG-05)"
    - "WARNING per failed attempt + ERROR on exhaustion with raw output dump (P7 compliance)"
    - "num_ctx inside the retry loop, not outside — applied on every call (D-04, P6)"

key-files:
  created:
    - "src/judge.py"
  modified:
    - "tests/test_judge.py (replaced stub with 15 tests)"
    - "tests/conftest.py (deep-copy kwargs at capture in FakeChatCompletions.create)"
    - "src/config.py (black reformat of pre-existing multi-line raises)"

key-decisions:
  - "Graceful failure shape: JudgeResult(scores=[]) sentinel — simpler for downstream than Optional or wrapper type; detect via `if not result.scores:`"
  - "Fence stripping: single outermost-brace DOTALL regex handles ```json fences + prose + nested objects in one pass (no separate fence removal step)"
  - "Retry feedback: bounded at 800 chars + fixed reminder, sent as user message after assistant raw turn"
  - "Single `except ValidationError` — Pydantic v2 raises this for both JSON decode AND schema violations (P12), so no JSONDecodeError catch needed"
  - "Section headings use top-level `#` (not `## ===` style) because agent output never emits `#`, only `##` and below (D-07)"

patterns-established:
  - "FakeClient deep-copy-on-capture: required whenever caller code mutates a persistent messages list across multiple client calls. Single-call tests don't need it; multi-call retry tests do."
  - "Retry loop structure: the success-return is INSIDE try/return, the sentinel-return is AFTER the for-loop body — NOT in a for/else clause"
  - "Logger naming convention `jitc.{module}` continues from jitc.agent established in Plan 02-02"

requirements-completed: [JUDG-01, JUDG-02, JUDG-03, JUDG-04, JUDG-05]

# Metrics
duration: 4min
completed: 2026-04-11
---

# Phase 2 Plan 03: Judge Summary

**Retry-and-parse judge with outermost-brace regex fence stripping, single-except ValidationError loop, and JudgeResult(scores=[]) graceful-failure sentinel — 15 FakeClient unit tests green.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-04-11T07:03:57Z
- **Completed:** 2026-04-11T07:07:30Z
- **Tasks:** 3 (1 RED, 1 GREEN, 1 full-sweep)
- **Files modified:** 4 (`src/judge.py` created, `tests/test_judge.py` + `tests/conftest.py` + `src/config.py` modified)

## Accomplishments

- **JUDG-01** happy path: `run_judge` returns populated `JudgeResult` with 8 `RubricScore` entries from the canonical `VALID_JUDGE_JSON` fixture; also works end-to-end on fenced valid JSON (fence stripping path).
- **JUDG-02** retry-with-feedback: 3-attempt retry where attempts 2 and 3 receive the prior attempt's `assistant` raw response AND a `user` correction message starting with `"Your previous response could not be parsed. Error:"`. Verified call count grows exactly as expected (2 → 4 → 6 messages).
- **JUDG-03** fence stripping: `_extract_json` handles ```` ```json ```` fences, prose preambles (`"Sure, here is the JSON: {...} Let me know!"`), nested objects (`{"outer": {"inner": 2}}`), and falls back to raw input when no braces present.
- **JUDG-04** num_ctx propagation: `extra_body={"options": {"num_ctx": config.num_ctx}}` appears on every create call — including every retry — alongside `temperature=config.temperature`, never `response_format`.
- **JUDG-05** graceful failure: after 3 exhausted attempts, `run_judge` returns `JudgeResult(scores=[])` sentinel instead of raising. An ERROR log record is emitted containing `"exhausted"` AND the raw response body of the final attempt (`bad C` in the test).
- Per-attempt WARNING logs satisfy P7 beyond the mandatory ERROR-on-exhaustion trail.

## Task Commits

1. **Task 1: RED — write failing JUDG-01..05 tests** — `7bd49e0` (test)
2. **Task 2: GREEN — implement `src/judge.py`** — `aa72d02` (feat)
3. **Task 3: Full-sweep verify** — `ed60e10` (chore)

**Plan metadata:** (next commit — SUMMARY + STATE + ROADMAP)

## Files Created/Modified

- `src/judge.py` — `run_judge` + `_extract_json` + `_build_user_message` + `_retry_user_message` + `JUDGE_SYSTEM_PROMPT` + module constants; ~195 lines including comprehensive docstrings covering D-04/D-05/D-07/D-09/D-10 and threat model T-02-J01/T-02-J02.
- `tests/test_judge.py` — 15 tests replacing the stub: 2 happy-path, 2 retry behaviour, 4 `_extract_json` unit cases, 1 num_ctx propagation, 2 graceful failure (return shape + ERROR log), 1 WARNING log trail, 3 helper plumbing (retry message content, bound, heading layout).
- `tests/conftest.py` — `_FakeChatCompletions.create` now `deepcopy`s kwargs at capture time so multi-call tests can inspect per-call `messages` history without aliasing the caller's mutable list. Documented in class docstring with the root-cause explanation.
- `src/config.py` — black reformat of pre-existing multi-line `raise ValueError(...) from exc` patterns into single-line form. Pre-existing issue from Plan 02-01; blocking Task 3's `black --check src/ tests/` gate.

## Decisions Made

The plan front-loaded most decisions (D-04..D-10 + five discretion resolutions from RESEARCH.md). Implementation adhered verbatim. No new architectural decisions.

**Sentinel contract recap (for Phase 3's `pre_loop_test.py` author):** callers detect failure with `if not result.scores:`. The return type is always `JudgeResult`, never `None`, never a raised exception. `len(result.scores) == 0` is the canonical failure check; `len(result.scores) == 8` on successful scoring against the current 8-item rubric.

**P12 observation (single except clause):** Pydantic v2's `JudgeResult.model_validate_json("not json")` raises `ValidationError` with `type=json_invalid` — a single `except ValidationError:` handles BOTH JSON-decode failures AND schema-violation failures. No `JSONDecodeError` needed. This was verified empirically by `test_retries_three_times_with_error_feedback` where the canned responses `"not json"` and `"still not json"` produce `ValidationError` with `json_invalid` type codes visible in the captured WARNING log lines.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `FakeChatCompletions.create` captured kwargs by reference, aliasing the mutable `messages` list**

- **Found during:** Task 2 GREEN verification (`test_retries_three_times_with_error_feedback` failed with `assert 6 == 2`)
- **Issue:** `run_judge` builds a single `messages: list[dict]` and appends to it on each retry. `chat.completions.create(messages=messages, ...)` passes the SAME list reference on every call. `FakeChatCompletions.create` was storing `kwargs` directly in `self.calls`, so all three entries of `calls[i]["messages"]` pointed at the final (6-element) state of the list — making it impossible to assert per-call message history.
- **Fix:** `self.calls.append(copy.deepcopy(kwargs))` with a docstring explaining the aliasing root cause. Deep copy is cheap (messages are small dicts of strings) and the fixture is test-only.
- **Files modified:** `tests/conftest.py`
- **Verification:** After the fix, all 15 judge tests pass; the prior 6 agent/llm tests still pass (single-call tests are unaffected by the aliasing behaviour, which is why this bug was latent through Plan 02-02).
- **Committed in:** `aa72d02` (bundled with Task 2 GREEN)
- **Scope boundary note:** modifying conftest.py at first glance looks like out-of-scope Plan 02-01 work, but it is the only way for Plan 02-03's multi-call tests to assert retry behaviour, so it falls under Rule 1 (bug in supporting infrastructure discovered while executing the current task's tests).

**2. [Rule 3 - Blocking] `src/config.py` failed `black --check src/ tests/` — pre-existing from Plan 02-01**

- **Found during:** Task 3 full-sweep verification
- **Issue:** Two `raise ValueError(f"Invalid {key}={raw!r}; expected float") from exc` blocks in `Config.from_env()` were formatted as multi-line statements that black 26.3.1 wants collapsed to a single line. Task 3's acceptance criteria requires `uv run black --check src/ tests/` to exit 0, but the violation was inherited from Plan 02-01 and no prior plan ran the full `src/ tests/` black check.
- **Fix:** `uv run black src/config.py` collapsed the two multi-line raises into single-line form (2 lines removed, 0 lines added beyond that).
- **Files modified:** `src/config.py`
- **Verification:** `uv run black --check src/ tests/` now passes (12 files unchanged); `uv run pytest -q -m "not integration"` still shows 21 passed.
- **Committed in:** `ed60e10` (Task 3 chore commit)

---

**Total deviations:** 2 auto-fixed (1 Rule 1 bug, 1 Rule 3 blocking)
**Impact on plan:** Both were latent issues surfaced by Plan 02-03's deeper test coverage (multi-call retry inspection) and stricter gate (full black check across src/+tests/). No scope creep; both fixes are minimal and defensively documented.

## Issues Encountered

None beyond the two deviations above. The RED→GREEN→FULL-SWEEP TDD flow progressed without iteration on the implementation itself — the GREEN code from RESEARCH.md §Code Skeletons was correct on the first try; the only rework was to the test harness.

## Verification Evidence

```
$ uv run pytest -q -m "not integration"
.....................                                                    [100%]
21 passed in 0.16s
```

Breakdown:
- `tests/test_llm.py`: 1 test (from Plan 02-01)
- `tests/test_agent.py`: 5 tests (from Plan 02-02)
- `tests/test_judge.py`: 15 tests (this plan)

```
$ uv run black --check src/ tests/
All done! ✨ 🍰 ✨
12 files would be left unchanged.
```

```
$ grep -rn "response_format=" src/
(no matches — P4 compliance verified)
```

```
$ grep -rn "parse_raw" src/ tests/
(no matches — P12 compliance verified)
```

```
$ uv run python -c "from src.agent import run_agent, ITERATION_ZERO_SYSTEM_PROMPT; from src.judge import run_judge; from src.llm import get_client; from src.config import config; print('imports_ok num_ctx=', config.num_ctx)"
imports_ok num_ctx= 16384
```

## Next Phase Readiness

**Phase 2 Plan 04 (integration smoke test):** `run_agent` and `run_judge` are both ready to be wired against a live Ollama host. The sentinel contract is pinned so the integration test can assert `result.scores` is non-empty after a happy-path call and equal to `[]` on deliberate failure.

**Phase 3 (`pre_loop_test.py`):** can now `from src.judge import run_judge` and call with `(nda_text, output_a_text, rubric_json, playbook_text)` / `(nda_text, output_b_text, ...)` — the rubric is passed as a raw JSON string (D-08). Failure detection is `if not result.scores:`.

**Known hot paths Phase 5's optimiser will touch:** `JUDGE_SYSTEM_PROMPT` is a module-level constant; if Phase 5 ever needs to vary the judge prompt (it should not — only the agent prompt rotates), a function-parameterised version will be needed. Out of scope here.

## Known Stubs

None. All test code and implementation code is connected to real inputs; no placeholder data paths flow to consumers.

## Self-Check: PASSED

- `src/judge.py` exists
- `tests/test_judge.py` contains 15 `def test_*` functions (≥13 required)
- Commit `7bd49e0` (Task 1 RED) present in `git log`
- Commit `aa72d02` (Task 2 GREEN) present in `git log`
- Commit `ed60e10` (Task 3 full-sweep) present in `git log`
- `grep -c "def run_judge" src/judge.py` = 1
- `grep -c "def _extract_json" src/judge.py` = 1
- `grep -c "def _build_user_message" src/judge.py` = 1
- `grep -c "def _retry_user_message" src/judge.py` = 1
- `grep -c "MAX_RETRIES = 3" src/judge.py` = 1
- `grep -c "MAX_ERROR_CHARS = 800" src/judge.py` = 1
- `grep -c "re.DOTALL" src/judge.py` = 1
- `grep -c "model_validate_json" src/judge.py` = 1
- `grep -c "return JudgeResult(scores=\[\])" src/judge.py` = 1
- `grep -c "response_format=" src/judge.py` = 0
- `grep -c "parse_raw" src/judge.py` = 0
- `uv run pytest -q -m "not integration"` → `21 passed`
- `uv run black --check src/ tests/` → `12 files would be left unchanged.`

---
*Phase: 02-agent-and-judge*
*Completed: 2026-04-11*
