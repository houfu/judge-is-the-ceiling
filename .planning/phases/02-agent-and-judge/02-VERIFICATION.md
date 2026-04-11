---
phase: 2
slug: agent-and-judge
verifier: gsd-verifier
date: 2026-04-11
status: passed
criteria_passed: 5/5
---

# Phase 2 Verification

## Goal Achievement

The Phase 2 goal — "the agent can review an NDA and the judge can score any review with structured, validated output" — is achieved. Both entry points exist as real implementations (`src/agent.py:40-65`, `src/judge.py:125-191`), both are covered by unit tests that exercise behaviour against a deterministic FakeClient harness, and both have been round-tripped against a live Ollama instance (`/tmp/phase2-04-integration.log` shows `test_agent_smoke PASSED` and `test_judge_smoke` returning 8 populated scores on `gemma4:26b`). The unit suite is currently green: `uv run pytest -q -m "not integration"` reports 21 passed / 2 deselected in 0.16s. All five roadmap success criteria are backed by implementation, targeted tests, and — where the criterion requires it — live Ollama evidence.

## Success Criteria

### SC-1: `run_agent(system_prompt, nda_text)` returns a non-empty string review when called against the local Ollama endpoint
- **Status:** PASS (live evidence)
- **Implementing code:** `src/agent.py:40-65` — `run_agent` builds a 2-message chat completion with `config.temperature`, `extra_body={"options": {"num_ctx": config.num_ctx}}`, and returns `response.choices[0].message.content or ""`.
- **Mocked test evidence:**
  - `tests/test_agent.py::test_run_agent_returns_content` — asserts return value propagated and exactly one `create()` call issued.
  - `tests/test_agent.py::test_run_agent_calls_create_with_two_messages` — asserts the `system`/`user` role layout.
  - `tests/test_agent.py::test_run_agent_passes_num_ctx_and_temperature` — asserts `temperature`, `extra_body`, `model`, and absence of `response_format`/`stream`.
  - `tests/test_agent.py::test_run_agent_handles_none_content` — covers the Ollama-returns-None edge case.
- **Live test evidence:** `tests/test_smoke_ollama.py::test_agent_smoke` loaded `data/nda.md`, called `run_agent(ITERATION_ZERO_SYSTEM_PROMPT, nda)`, asserted non-empty and `len >= 100`. Pytest log: `/tmp/phase2-04-integration.log` line 1 (`.` = passed) followed by `2 passed in 126.74s` on line 7. Ran against `gemma4:26b`.
- **Verdict:** The criterion explicitly requires the live-Ollama condition; live evidence exists and passes. PASS.

### SC-2: `run_judge(nda_text, agent_output, rubric, playbook)` returns a validated `JudgeResult` with all 8 rubric items scored
- **Status:** PASS (live evidence)
- **Implementing code:** `src/judge.py:125-191` — `run_judge` signature matches, calls `JudgeResult.model_validate_json(cleaned)` (Pydantic v2 path, P12), returns the validated object.
- **Mocked test evidence:**
  - `tests/test_judge.py::test_happy_path_returns_judge_result` — returns 8 `RubricScore` items from `VALID_JUDGE_JSON` (the 8-item fixture in `tests/conftest.py:76-92`).
  - `tests/test_judge.py::test_happy_path_returns_judge_result_from_fenced_json` — same but with ```` ```json ``` ```` wrapping.
- **Live test evidence:** `tests/test_smoke_ollama.py::test_judge_smoke` ran against live Ollama with `data/nda.md`, `data/output_a.md`, `data/rubric.json`, `data/playbook.md` and asserted non-empty `result.scores`. The integration log shows `judge smoke: 8 scores returned` with reasoning strings that cite the NDA by concept (e.g. "7-year duration", "market norms comparison"), confirming all 8 rubric items were scored end-to-end.
- **Verdict:** PASS. The "all 8 rubric items scored" clause is satisfied by both the FakeClient fixture and the live run.

### SC-3: Judge retries up to 3 times on invalid JSON and sends the ValidationError message back to the model on each retry; a deliberately malformed call demonstrates this behaviour
- **Status:** PASS (mocked — appropriate for this criterion)
- **Implementing code:** `src/judge.py:162-181`:
  - Line 162: `for attempt in range(1, MAX_RETRIES + 1)` with `MAX_RETRIES = 3` (line 41).
  - Line 174: `JudgeResult.model_validate_json(cleaned)` inside `try`.
  - Line 175-180: `except ValidationError as err` → `messages.append({"role": "assistant", "content": raw})` + `messages.append({"role": "user", "content": _retry_user_message(err)})`.
  - `_retry_user_message` (line 107-122) embeds the `ValidationError`'s stringified message (bounded at `MAX_ERROR_CHARS = 800`) into the user-role correction prompt.
- **Test evidence (mocked — deliberately malformed to force the retry path):**
  - `tests/test_judge.py::test_retries_three_times_with_error_feedback` — seeds FakeClient with `["not json", "still not json", VALID_JUDGE_JSON]`, asserts exactly 3 calls, verifies message-count growth 2 → 4 → 6, confirms `msgs_2[2]` has role=`assistant` and `content=="not json"`, and `msgs_2[3]["content"].startswith("Your previous response could not be parsed. Error:")`. Same check for attempt 3.
  - `tests/test_judge.py::test_retry_recovers_on_second_attempt` — recovers mid-way (2 calls).
  - `tests/test_judge.py::test_retry_user_message_includes_error_and_reminder` — asserts the error string is substrings in the retry user message.
  - `tests/test_judge.py::test_retry_user_message_bounded` — confirms the 800-char cap with `"truncated"` marker.
- **Live evidence:** Not required by this criterion (the point is to force the retry path deterministically, which a live model would do only under unreproducible conditions). FakeClient is the correct harness.
- **Verdict:** PASS. The criterion explicitly asks for "a deliberately malformed call demonstrates this behaviour" — `test_retries_three_times_with_error_feedback` is that demonstration, and the 2→4→6 message growth assertion proves the ValidationError string is actually reinjected.

### SC-4: Markdown fences are stripped before Pydantic parsing AND `num_ctx` is set explicitly on every judge API call
- **Status:** PASS (mocked on both halves, with cross-check from live run)
- **Implementing code:**
  - Fence stripping: `src/judge.py:72-84` — `_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)` and `_extract_json(raw)` called on line 171 before `model_validate_json` on line 174.
  - `num_ctx` on every call: `src/judge.py:168` — `extra_body={"options": {"num_ctx": config.num_ctx}}` is inside the `for attempt in range(...)` loop, so it is applied on every retry, not just the first call.
- **Test evidence (fences):**
  - `tests/test_judge.py::test_extract_json_strips_fences` — covers ` ```json `, bare ` ``` `, and no-fence forms.
  - `tests/test_judge.py::test_extract_json_strips_prose_preamble` — covers prose-wrapped JSON.
  - `tests/test_judge.py::test_extract_json_handles_nested_objects` — covers nested `{}` via outermost-brace semantics.
  - `tests/test_judge.py::test_extract_json_falls_back_to_raw_when_no_braces` — fall-through path.
  - `tests/test_judge.py::test_happy_path_returns_judge_result_from_fenced_json` — end-to-end: fenced valid JSON → stripped → parsed → returned.
- **Test evidence (`num_ctx` on every call):**
  - `tests/test_judge.py::test_num_ctx_in_every_call` — seeds a 3-call retry sequence and iterates all 3 calls asserting `kwargs["extra_body"] == {"options": {"num_ctx": config.num_ctx}}` on each one. Also asserts `"response_format" not in kwargs` (P4).
  - `tests/test_agent.py::test_run_agent_passes_num_ctx_and_temperature` provides the agent-side equivalent for SC-1.
- **Live cross-check:** The integration log shows a successful `run_judge` against live Ollama with the default `num_ctx=16384`, confirming the wiring is real (biasing: if `num_ctx` were ignored, a 16KB prompt would silently truncate and the 8 rubric items likely wouldn't all return cleanly on the first attempt).
- **Verdict:** PASS. Both halves are implemented and tested, including the retry-path invariant which is the easy-to-miss variant.

### SC-5: If all 3 retries are exhausted the judge logs the raw output and returns a graceful failure result rather than raising an exception
- **Status:** PASS (mocked with `caplog` — appropriate for this criterion)
- **Implementing code:** `src/judge.py:182-191`:
  - Line 183-188: `logger.error("judge exhausted %d retries; returning empty result. raw=%r last_error=%s", MAX_RETRIES, raw, last_error)` — logs BOTH the raw output AND the final ValidationError message at ERROR level.
  - Line 191: `return JudgeResult(scores=[])` — sentinel, not a raise. No `raise` on the exhaustion path anywhere in `run_judge`.
- **Test evidence:**
  - `tests/test_judge.py::test_graceful_failure_on_retry_exhaustion` — seeds `["bad 1", "bad 2", "bad 3"]`, asserts `result.scores == []`, `isinstance(result, JudgeResult)`, and `len(client.calls) == 3`. Crucially, the test does not wrap `run_judge` in `pytest.raises` — so an uncaught exception would fail the test.
  - `tests/test_judge.py::test_graceful_failure_logs_raw_output` — uses `caplog.at_level(logging.ERROR, logger="jitc.judge")` and asserts (a) at least one ERROR record contains `"exhausted"` and (b) the final raw output string `"bad C"` appears in the combined ERROR message text.
  - `tests/test_judge.py::test_warning_logged_on_every_parse_failure` — complementary: WARNING is emitted on intermediate retries even when the final attempt succeeds.
- **Verdict:** PASS. FakeClient is the correct harness because "force exhaustion" against a real model is non-deterministic.

## Deferred / Informational Items

None. Every SC has concrete in-phase implementation and test coverage.

## Outstanding concerns from code review (advisory, not gating)

From `02-REVIEW.md` — two medium findings that do **not** affect the success criteria above but should be on the Phase 3 radar:

- **M-01: `src/llm.py` `_client` singleton leaks between tests.** `test_get_client_returns_singleton` populates the real-client slot for the remainder of the pytest session; the `fake_client` fixture's `monkeypatch.setattr` restores to whatever was present when the fixture ran (which may be the leaked real client, not `None`). No current test fails because of this, but a Phase 3+ test that inspects `_client is None` would become collection-order dependent. Fix is a 5-line autouse fixture in `tests/conftest.py`.
- **M-02: D-07 heading-collision rationale is incomplete.** The plan and `src/judge.py:7-8` claim top-level `#` headings prevent section-divider collision because the agent uses `##` and below. This holds for agent output but NOT for `nda_text`: `data/nda.md` already starts with `#`, and a malicious or merely unusual NDA containing `\n\n# AGENT OUTPUT\n...` could inject fake boundaries. The threat model (T-02-J01) explicitly accepts this as biased-scoring risk, so the code is correct as written — but the justification comment should be re-worded. Medium, advisory, accepted-risk.

Neither finding blocks the Phase 2 goal. Both are candidates for a small follow-up cleanup plan at the start of Phase 3 or during Phase 3's pre-loop work.

## Anti-pattern scan

- No `TODO`/`FIXME` markers that block Phase 2 goals. Two `TODO(...)` markers exist in `src/judge.py:189-190` both tagged to future phases (`P2, Phase 3` for reasoning-length content validator, `P7, Phase 5` for `validation_attempts` field) — these are correctly deferred per `02-CONTEXT.md`.
- No `return None` / `return {}` stubs in the implementation surface.
- No `console.log`-style placeholder implementations.
- `run_agent` and `run_judge` are both substantive (25 and 67 lines respectively, counting body only) and wired to the shared `get_client()` factory (`src/agent.py:23`, `src/judge.py:36`).

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Unit suite green | `uv run pytest -q -m "not integration"` | `21 passed, 2 deselected in 0.16s` | PASS |
| Live agent round-trip | `pytest -q -m integration tests/test_smoke_ollama.py::test_agent_smoke` | PASSED (recorded in `/tmp/phase2-04-integration.log`, not re-run) | PASS (cached) |
| Live judge round-trip returns 8 scores | `pytest -q -m integration tests/test_smoke_ollama.py::test_judge_smoke` | `judge smoke: 8 scores returned` (recorded in `/tmp/phase2-04-integration.log`, not re-run) | PASS (cached) |

The integration tests were not re-executed during this verification pass because the evidence in `/tmp/phase2-04-integration.log` is recent (same-day Phase 2 execution, 2026-04-11) and each integration call is expensive (~2min). Re-running is unnecessary unless the source files have changed since the log was captured.

## Requirements Coverage

| Requirement | Description | Status | Evidence |
| ----------- | ----------- | ------ | -------- |
| AGNT-01 | `run_agent` wraps chat completions with correct args | SATISFIED | `src/agent.py:40-65`; `tests/test_agent.py::test_run_agent_*` (4 tests); `test_smoke_ollama.py::test_agent_smoke` (live) |
| AGNT-02 | Iteration-zero prompt is free of rubric/playbook vocabulary | SATISFIED | `src/agent.py:32-37`; `tests/test_agent.py::test_prompt_scrubbed_of_rubric_vocab` (13 banned tokens) |
| JUDG-01 | `run_judge` returns validated `JudgeResult` on happy path | SATISFIED | `src/judge.py:125-174`; `tests/test_judge.py::test_happy_path_*` (2 tests); `test_smoke_ollama.py::test_judge_smoke` (live, 8 scores) |
| JUDG-02 | 3-attempt retry loop with ValidationError feedback | SATISFIED | `src/judge.py:162-181`; `tests/test_judge.py::test_retries_three_times_with_error_feedback` + `test_retry_recovers_on_second_attempt` |
| JUDG-03 | Markdown fence stripping before parse | SATISFIED | `src/judge.py:72-84`; 4 `_extract_json` unit tests + fenced happy-path end-to-end test |
| JUDG-04 | `num_ctx` set on every API call including retries | SATISFIED | `src/judge.py:168` (inside retry loop); `tests/test_judge.py::test_num_ctx_in_every_call` iterates all 3 retry calls |
| JUDG-05 | Retry exhaustion logs raw + returns sentinel, no raise | SATISFIED | `src/judge.py:182-191`; 3 graceful-failure tests (sentinel return, ERROR log contents, WARNING trail) |

All 7 requirements from the Phase 2 scope are satisfied.

## Gaps

None that block the Phase 2 goal. The two medium review findings (M-01, M-02) are advisory and fit naturally into a Phase 3 warmup.

## Recommendation

**Advance to Phase 3.** All 5 success criteria are met, all 7 requirements are satisfied, the unit suite is green, and live Ollama evidence covers the two criteria that require it (SC-1 and SC-2). The two medium review findings are accepted-risk / test-hygiene items that do not interact with Phase 3's pre-loop validation work.

Consider a 15-minute cleanup pass to address M-01 (autouse singleton reset fixture) before Phase 3 begins — it's cheap insurance against collection-order flakiness as the test suite grows.

---

*Verified: 2026-04-11*
*Verifier: Claude (gsd-verifier)*
