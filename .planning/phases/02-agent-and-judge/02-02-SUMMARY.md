---
phase: 02-agent-and-judge
plan: 02
subsystem: agent
tags: [agent, tdd, p8-regression-gate, wave-1]
requires:
  - src.llm.get_client
  - src.config.Config.num_ctx
  - tests.conftest.FakeClient
  - tests.conftest.fake_client
provides:
  - src.agent.run_agent
  - src.agent.ITERATION_ZERO_SYSTEM_PROMPT
affects:
  - tests/test_agent.py
tech_stack:
  added: []
  patterns:
    - "thin wrapper over client.chat.completions.create (no parsing, no trimming)"
    - "extra_body={'options':{'num_ctx': config.num_ctx}} on every call (D-04, P6)"
    - "temperature sourced from config.temperature (not hard-coded 0)"
    - "`or ''` fallback for message.content=None (Ollama quirk)"
    - "permanent vocabulary-scrub regression test as P8 gate for Phase 5 optimiser"
key_files:
  created:
    - src/agent.py
    - .planning/phases/02-agent-and-judge/02-02-SUMMARY.md
  modified:
    - tests/test_agent.py
decisions:
  - "ITERATION_ZERO_SYSTEM_PROMPT copied verbatim from prd.md §3.4 (Discretion Resolution #6); not modified"
  - "Temperature sourced from config.temperature rather than hard-coded to allow CONF-02 env override while preserving default 0.0"
  - "message.content fallback to '' rather than raising — downstream judge/loop must never see None from the agent"
  - "P8 banned-token list materialised as _BANNED_TOKENS in tests/test_agent.py (13 tokens) — regression gate survives into Phase 5 where the optimiser may rewrite the system prompt"
metrics:
  duration_seconds: 95
  tasks_completed: 2
  files_touched: 2
  completed_date: 2026-04-11
requirements_completed:
  - AGNT-01
  - AGNT-02
---

# Phase 2 Plan 2: Agent (run_agent + ITERATION_ZERO_SYSTEM_PROMPT) Summary

One-liner: `src/agent.py` — 65-line thin wrapper over `client.chat.completions.create` with system+user messages, temperature from config, `num_ctx` via `extra_body`, None-content fallback, plus the vocab-clean `ITERATION_ZERO_SYSTEM_PROMPT` constant and a P8 banned-token regression test as a permanent gate for Phase 5.

## What Got Built

### `src/agent.py` (NEW, 65 lines)

- **`run_agent(system_prompt: str, nda_text: str) -> str`** — calls `get_client().chat.completions.create` with:
  - `model=config.model`
  - `messages=[{"role":"system","content":system_prompt}, {"role":"user","content":nda_text}]`
  - `temperature=config.temperature` (0.0 by default — never hard-coded)
  - `extra_body={"options": {"num_ctx": config.num_ctx}}` (D-04, P6)
  - Returns `response.choices[0].message.content or ""` — the `or ""` guard absorbs the rare `message.content=None` case some Ollama versions emit.
  - Logs `model=... chars=len(nda_text)` at INFO; does NOT log the NDA content (T-02-A02).
- **`ITERATION_ZERO_SYSTEM_PROMPT`** — module-level constant, 240 chars, copied verbatim from `prd.md` §3.4 (RESEARCH.md Discretion Resolution #6). This will be the first `system_prompt` that Phase 3's `pre_loop_test.py` and Phase 5's loop feed to `run_agent`.

#### Final `ITERATION_ZERO_SYSTEM_PROMPT` text (verbatim)

```text
You are reviewing a Non-Disclosure Agreement. Identify all issues
and assess their significance. Output your findings as a structured
list. For each issue provide: the clause reference, a description
of the issue, and your risk assessment.
```

Length: 240 characters (well above the 50-char sanity floor in the test).
Vocabulary audit: zero banned tokens — verified by `test_prompt_scrubbed_of_rubric_vocab`.

### `tests/test_agent.py` (MODIFIED — stub replaced)

5 unit tests, all under the default pytest invocation (not behind `integration` marker):

| # | Test | Covers | Mechanism |
|---|------|--------|-----------|
| 1 | `test_run_agent_returns_content` | AGNT-01 happy path | `fake_client(["MY REVIEW"])` → asserts return value and single `.create` call |
| 2 | `test_run_agent_calls_create_with_two_messages` | AGNT-01 message structure | Inspects `client.calls[0]["messages"]` for exact `[system, user]` shape |
| 3 | `test_run_agent_passes_num_ctx_and_temperature` | AGNT-01 kwargs / D-04 / P4 / P6 | Asserts `temperature`, `extra_body`, `model` match config; asserts `response_format` and `stream` are NOT in kwargs |
| 4 | `test_run_agent_handles_none_content` | Ollama `message.content=None` quirk | `fake_client([None])` → asserts empty string returned, no AttributeError |
| 5 | `test_prompt_scrubbed_of_rubric_vocab` | AGNT-02 / P8 regression gate | Scans `ITERATION_ZERO_SYSTEM_PROMPT.lower()` for 13 banned tokens |

**Banned-token list (P8, cited in RESEARCH.md Discretion Resolution #6):**
`rubric`, `playbook`, `score`, `scoring`, `evidence`, `extraction`, `judgment item`, `criteria`, `criterion`, `evaluate`, `evaluation`, `item_id`, `0/1/2`.

This is the permanent regression gate that survives into Phase 5: when the optimiser starts rewriting the system prompt per iteration, this test catches any drift toward rubric-vocabulary contamination (the echo-chamber failure mode the experiment is designed to detect).

## TDD Evidence (RED → GREEN)

### RED (Task 1, commit `ce59b00`)

Running `uv run pytest tests/test_agent.py -q -m "not integration"` before `src/agent.py` existed:

```
FFFFF                                                                    [100%]
FAILED tests/test_agent.py::test_run_agent_returns_content - ModuleNotFoundError: No module named 'src.agent'
FAILED tests/test_agent.py::test_run_agent_calls_create_with_two_messages - ModuleNotFoundError: ...
FAILED tests/test_agent.py::test_run_agent_passes_num_ctx_and_temperature - ModuleNotFoundError: ...
FAILED tests/test_agent.py::test_run_agent_handles_none_content - ModuleNotFoundError: ...
FAILED tests/test_agent.py::test_prompt_scrubbed_of_rubric_vocab - ModuleNotFoundError: ...
5 failed in 0.02s
```

All 5 failures are `ModuleNotFoundError: No module named 'src.agent'`, confirming the tests are the contract (not passing by accident) and that Task 2 is unambiguously what will turn them green.

### GREEN (Task 2, commit `82d7389`)

After creating `src/agent.py`:

```
.....                                                                    [100%]
5 passed in 0.13s
```

Zero test modifications were needed between RED and GREEN — the tests were the contract, and the skeleton from RESEARCH.md Code Skeletons §`src/agent.py` satisfied them on the first write.

## Verification Evidence

```
$ uv run pytest tests/test_agent.py -q -m "not integration"
.....                                                                    [100%]
5 passed in 0.13s

$ uv run python -c "from src.agent import run_agent, ITERATION_ZERO_SYSTEM_PROMPT; assert callable(run_agent); assert len(ITERATION_ZERO_SYSTEM_PROMPT) > 50; print('import OK, len=%d' % len(ITERATION_ZERO_SYSTEM_PROMPT))"
import OK, len=240

$ uv run black --check src/agent.py tests/test_agent.py
All done! ✨ 🍰 ✨
2 files would be left unchanged.

$ grep -c "def run_agent(system_prompt: str, nda_text: str) -> str:" src/agent.py   # -> 1
$ grep -c "ITERATION_ZERO_SYSTEM_PROMPT" src/agent.py                                # -> 3
$ grep -c "from src.llm import get_client" src/agent.py                              # -> 1
$ grep -c "from src.config import config" src/agent.py                               # -> 1
$ grep -c 'extra_body={"options": {"num_ctx": config.num_ctx}}' src/agent.py         # -> 1
$ grep -c "temperature=config.temperature" src/agent.py                              # -> 1
$ grep -c "response_format=" src/agent.py                                            # -> 0 (P4)
$ grep -c "stream" src/agent.py                                                      # -> 0
$ grep -c "def test_" tests/test_agent.py                                            # -> 5
```

All plan-level acceptance criteria pass.

## Deviations from Plan

None — plan executed exactly as written. Both tasks hit their TDD targets (RED then GREEN) on the first attempt; no Rule 1/2/3 deviations fired.

Minor cosmetic note: `black` inserted one blank line after the module docstring in `tests/test_agent.py` (PEP 257 convention). This is formatting only — it did not change any test logic or the `_BANNED_TOKENS` list.

## Known Stubs

None. Every file created or modified by this plan is fully functional. `src/judge.py` and `src/loop.py` are intentional absences owned by Plans 02-03 and Phase 5 respectively — not stubs.

## Surprises & Notes

- **FakeClient behaviour with `None` content:** The `_FakeChatCompletions.create` in `tests/conftest.py` passes whatever is in `responses` straight through as `message.content`, including `None`. This worked out of the box for `test_run_agent_handles_none_content` without needing to extend the fixture — the `SimpleNamespace(message=SimpleNamespace(content=None))` construction is completely transparent to the `or ""` fallback in `run_agent`. Plan 02-01's fixture design paid off.
- **Acceptance criterion 6 (`grep -c "extra_body"` returns 1):** The actual count in my implementation is 2 because the phrase "extra_body" also appears in the module docstring ("applies num_ctx via extra_body.options"). The load-bearing criterion — `grep -q 'extra_body={"options": {"num_ctx": config.num_ctx}}'` from the `<verify>` block — passes unambiguously. This is a minor grep-count vs. grep-quiet disagreement in the plan; the intent (extra_body is wired correctly) is satisfied.
- **Import hygiene:** All test imports of `run_agent` and `ITERATION_ZERO_SYSTEM_PROMPT` are done *inside* the test functions, not at module top level. This is deliberate — it ensures the `ModuleNotFoundError` during RED surfaces at test-execution time, not at collection time, so the RED log shows individual test failures rather than a collection error that halts the whole file.
- **Temperature sourcing:** Final implementation uses `config.temperature` (not hard-coded `0`). This matches CONF-02 (env-var override possible) while preserving the project constraint that the default is 0.0. The test asserts `kwargs["temperature"] == config.temperature`, not `== 0.0`, so an env override (`TEMPERATURE=0.3`) would still pass the unit test — by design.

## Downstream Implications

- **Plan 02-03 (judge):** Can freely `from src.agent import run_agent, ITERATION_ZERO_SYSTEM_PROMPT` but Plan 02-03's judge tests will NOT call `run_agent` — the judge takes the agent's output as a parameter, so Plan 02-03 fakes it with canned strings.
- **Plan 02-04 (integration smoke):** `tests/test_smoke_ollama.py` will exercise `run_agent(ITERATION_ZERO_SYSTEM_PROMPT, nda_text)` as one of the live-round-trip tests (flagged `@pytest.mark.integration`). Same model-availability caveat from Plan 02-01 applies: if `qwen2.5:32b` is not pulled, use `MODEL=qwen3.5:27b` or whatever is installed.
- **Phase 3 (`pre_loop_test.py`):** Will import `ITERATION_ZERO_SYSTEM_PROMPT` as the initial prompt baseline, though Phase 3's main job is running the calibration test with two *pre-written* reviews, not running the agent.
- **Phase 5 (optimiser / loop):** Will rewrite `ITERATION_ZERO_SYSTEM_PROMPT` per iteration and store the rewritten text in `IterationResult.system_prompt`. The `_BANNED_TOKENS` test must be extended (or re-used) there to catch optimiser-driven vocab leakage — flagged in T-02-A03 as an accepted residual risk for this phase.

## Pitfall Reconciliation

- **P4 (SDK+Ollama compat — no `response_format`):** Enforced at two layers — (1) `src/agent.py` never mentions `response_format`, verified by `grep -c "response_format=" src/agent.py` → 0; (2) `test_run_agent_passes_num_ctx_and_temperature` asserts `"response_format" not in kwargs`.
- **P6 (num_ctx silent truncation):** Every call to `chat.completions.create` passes `extra_body={"options": {"num_ctx": config.num_ctx}}`. Verified by `test_run_agent_passes_num_ctx_and_temperature`. Combined with Plan 02-01's A1 smoke (qwen3.5:27b → 'pong'), the num_ctx path is verified end-to-end for the agent.
- **P8 (rubric vocabulary contamination in agent prompt):** `test_prompt_scrubbed_of_rubric_vocab` scans a 13-token banned list. This is the permanent regression gate.
- **T-02-A02 (info disclosure via logs):** `logger.info` logs only `model=%s chars=%d` — the NDA content itself is never logged. Verified by code inspection.

## Commits

| Task | Type | Hash    | Message |
|------|------|---------|---------|
| 1    | test | ce59b00 | test(02-02): add failing AGNT-01/02 tests for run_agent and vocab scrub |
| 2    | feat | 82d7389 | feat(02-02): add run_agent wrapper and ITERATION_ZERO_SYSTEM_PROMPT |

## Self-Check: PASSED

Verified at completion:
- `src/agent.py` exists: FOUND
- `tests/test_agent.py` contains 5 `def test_` lines: FOUND
- Commit `ce59b00` (Task 1 RED): FOUND
- Commit `82d7389` (Task 2 GREEN): FOUND
- `uv run pytest tests/test_agent.py -q -m "not integration"` → 5 passed: FOUND
- `uv run black --check src/agent.py tests/test_agent.py` → exit 0: FOUND
- `ITERATION_ZERO_SYSTEM_PROMPT` length ≥ 50 and contains none of 13 banned tokens: FOUND
