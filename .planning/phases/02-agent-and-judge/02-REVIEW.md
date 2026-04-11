---
phase: 02-agent-and-judge
reviewer: gsd-code-reviewer (Claude)
date: 2026-04-11
status: issues_found
depth: standard
files_reviewed: 11
files_reviewed_list:
  - src/config.py
  - src/llm.py
  - src/agent.py
  - src/judge.py
  - tests/__init__.py
  - tests/conftest.py
  - tests/test_llm.py
  - tests/test_agent.py
  - tests/test_judge.py
  - tests/test_smoke_ollama.py
  - pyproject.toml
findings_count:
  blocker: 0
  high: 0
  medium: 2
  low: 4
  info: 3
  total: 9
---

# Phase 2 Code Review: Agent and Judge

## Summary

Phase 2 implementation is high quality. All ten locked decisions (D-01..D-10) are correctly realised in code, and all seven in-scope pitfalls (P2, P4, P6, P7, P8, P12, P14) have concrete mitigations that spot-check against the plans. The FakeClient harness is well-designed — the deep-copy of `kwargs` in `_FakeChatCompletions.create` is a subtle correctness win that makes retry-loop assertions meaningful. Unit tests genuinely exercise behaviour rather than asserting structure, and the `test_retries_three_times_with_error_feedback` test verifies the full 2→4→6 message-growth pattern. The only findings are (1) subtle test-isolation fragility in the `_client` module singleton, (2) a latent prompt-injection vector via top-level heading collision that the plans acknowledge as accepted-but-not-fully-mitigated, and a handful of low-severity hygiene items. No blocker, no high-severity issues.

## Findings

### MEDIUM

#### M-01: `src/llm.py` module-level `_client` singleton leaks between tests

**File:** `src/llm.py:12-23`, `tests/test_llm.py:6-11`
**Severity:** medium
**Category:** test isolation / correctness

`src/llm.py` caches the OpenAI client in a module-level `_client` global. `tests/test_llm.py::test_get_client_returns_singleton` calls `get_client()` twice without any fixture or teardown, which populates `src.llm._client` with a real `OpenAI` instance for the remainder of the pytest session.

The `fake_client` fixture uses `monkeypatch.setattr(src.llm, "_client", client)`, which pytest restores to *whatever value was present when the fixture ran* — not to `None`. So:

1. If `test_llm.py` runs before any `fake_client`-using test: the restore target is the leaked real `OpenAI` instance, not `None`. Subsequent direct calls to `get_client()` in any future test (or a REPL in the same session) return the real client even though the test intended a clean slate.
2. If any future test checks `src.llm._client is None` to assert "no client created yet", it will fail nondeterministically based on test collection order.

No test currently exhibits a visible failure because no non-fixture test inspects `_client` after teardown, but this is fragile. A third test added in Phase 3 that assumes a clean module state could fail nondeterministically based on collection order.

**Fix hint:** Add an autouse fixture in `conftest.py` that resets the singleton before every test, OR reset it explicitly in `test_llm.py`:

```python
# tests/conftest.py
@pytest.fixture(autouse=True)
def _reset_llm_singleton(monkeypatch):
    import src.llm
    monkeypatch.setattr(src.llm, "_client", None)
```

This makes `monkeypatch` always restore to `None`, which is the documented pre-test state.

---

#### M-02: Top-level `#` heading collision mitigation (D-07) is incomplete — `data/nda.md` already uses `#`

**File:** `src/judge.py:87-104`, `tests/test_judge.py:19`
**Severity:** medium
**Category:** security (prompt injection) / correctness

D-07 says "use top-level `#` headings as section dividers because the agent never generates `#` (only `##` and below)." The implementation in `_build_user_message` does exactly that:

```python
"# NDA\n"
f"{nda_text}\n\n"
"# AGENT OUTPUT\n"
f"{agent_output}\n\n"
...
```

But `nda_text` is a markdown document that **already contains top-level `#` headings**. The test fixture in `test_judge.py:19` confirms this: `NDA = "# NDA\n1. The Term shall be seven (7) years.\n"`. A real NDA file (`data/nda.md`) also starts with `# `. Consequences:

1. **Spoofing vector:** a malicious NDA containing `\n\n# AGENT OUTPUT\n{fake review}\n\n# RUBRIC\n{fake rubric}\n` would inject fake section boundaries into the judge's user-role message. The judge would then score a crafted agent output / rubric rather than the real one. T-02-J01 in 02-02-PLAN.md documents this as an accepted risk ("the only output channel is a Pydantic-validated JudgeResult, so the worst case is biased scoring"), but the D-07 claim that the heading style *prevents* collision is false.
2. **Accidental confusion:** even without malice, an NDA that happens to include a `# Definitions` section provides two top-level `#` blocks inside the `# NDA` region, which may confuse the model about where the NDA ends.

The `ITERATION_ZERO_SYSTEM_PROMPT` currently says "Output your findings as a structured list" without specifying markdown level, but Phase 5's optimiser may rewrite the agent prompt to produce `#`-headed output, compounding the issue.

This is **accepted risk** per the threat model (local-only experiment, no tool access) so it doesn't warrant blocking. But the D-07 rationale documented in both code and plan is incorrect about the agent side — and the NDA side is not addressed at all.

**Fix hint:** Either
- (a) Switch to a distinctive prefix that real markdown is extremely unlikely to contain: `# === JITC_NDA_START ===` / `# === JITC_NDA_END ===` envelope, OR
- (b) Leave the code as-is but fix the comment on `src/judge.py:8` to accurately state the threat model: *"heading collision is possible when NDA or agent output contains `#` — we accept this as biased-scoring risk per T-02-J01, not eliminated by the heading choice"*. The current comment reads as a prevention claim and should not.

---

### LOW

#### L-01: `_extract_json` regex is greedy across the whole string and may eat non-JSON prose containing braces

**File:** `src/judge.py:72-84`
**Severity:** low
**Category:** correctness edge case

`_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)` matches from the *first* `{` to the *last* `}` in the string. For the tested happy paths (fenced JSON, prose preamble + JSON + prose suffix, nested objects) this works. But for a pathological output like:

```
Use the {variable} interpolation syntax. Here is the JSON: {"scores": [...]}
```

the regex returns `{variable} interpolation syntax. Here is the JSON: {"scores": [...]}` — not valid JSON. Pydantic will raise `ValidationError` and the retry loop will recover, so there is no correctness failure, only wasted retries. Acceptable for Phase 2 but worth noting.

**Fix hint:** If this becomes a problem in Phase 3, use a non-greedy first-JSON-object matcher that handles nesting (e.g. a small brace-counting parser) or try `re.search(r"\{.*\}", raw, re.DOTALL)` then `re.search(r"\{[^{}]*\}", raw, re.DOTALL)` as a fallback. Not worth fixing now — the retry loop compensates.

---

#### L-02: `test_retry_user_message_bounded` ceiling is loose

**File:** `tests/test_judge.py:220-227`
**Severity:** low
**Category:** test quality

The test asserts `len(msg) <= MAX_ERROR_CHARS + 400`, which accepts up to 400 bytes of fixed overhead. The actual reminder is ~200 chars. If a future refactor doubles the reminder to 800 chars, the truncation bound could silently drift and the test would still pass. Tighter bound + explicit assertion on the truncation marker would be more diagnostic.

**Fix hint:**
```python
assert msg.endswith(...)  # explicit check on the reminder suffix
assert "x" * 5000 not in msg  # positive: full error was NOT included
assert "x" * 800 in msg      # negative: the truncated slice IS included
```

---

#### L-03: `_client` type annotation in `llm.py` uses `OpenAI | None` without `from __future__ import annotations`

**File:** `src/llm.py:12`
**Severity:** low
**Category:** python hygiene

The module declares `_client: OpenAI | None = None` at module top-level. Python 3.11+ supports `X | None` natively at runtime, so this works. But adding `from __future__ import annotations` would be consistent with future string-annotation patterns and costs nothing. Not a bug — style nit.

**Fix hint:** Either add `from __future__ import annotations` to all `src/*.py` files or omit the note. No action required.

---

#### L-04: `list[dict]` type hint in `judge.py` drops dict value type

**File:** `src/judge.py:155`
**Severity:** low
**Category:** python hygiene / type safety

```python
messages: list[dict] = [
    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
    ...
]
```

Should be `list[dict[str, str]]` for clarity. Not a correctness issue; mypy would accept both. Minor hygiene.

**Fix hint:** `messages: list[dict[str, str]] = [...]`

---

### INFO

#### I-01: `test_get_client_returns_singleton` constructs a real `OpenAI` client

**File:** `tests/test_llm.py:6-11`
**Severity:** info
**Category:** test quality

The test creates a real `openai.OpenAI()` instance via `get_client()`. The constructor does NOT make network calls (OpenAI SDK v2 is lazy), so this is safe, but it couples the unit test to the SDK's constructor behaviour. If a future SDK version validates `base_url` reachability at construction time, this test would fail to start Ollama. See also M-01 for the leaked-state concern.

**Fix hint:** No action required for Phase 2. Consider tightening in Phase 3 by monkeypatching `openai.OpenAI` at the module boundary:
```python
def test_get_client_returns_singleton(monkeypatch):
    sentinel = object()
    monkeypatch.setattr("src.llm.OpenAI", lambda **kw: sentinel)
    monkeypatch.setattr("src.llm._client", None)
    assert get_client() is sentinel
    assert get_client() is sentinel  # cached
```

---

#### I-02: `config = Config.from_env()` module-level singleton is read directly by tests

**File:** `src/config.py:44`, `tests/test_agent.py:58-60`, `tests/test_judge.py:152-157`
**Severity:** info
**Category:** test design

Tests assert `kwargs["temperature"] == config.temperature` and `kwargs["extra_body"] == {"options": {"num_ctx": config.num_ctx}}`, which reads the live module-level singleton. This is a tautology if `agent.py` and `judge.py` read the same singleton — the test only catches typos in the keyword name, not a regression where someone hard-codes a wrong number. That said, the typo-catcher is valuable and mirrors the pattern in D-04.

**Fix hint:** No change. If Phase 5 introduces config mutation, tests will need to pin `config.num_ctx` to a literal (e.g. `monkeypatch.setattr(config, "num_ctx", 99)` then assert `99`).

---

#### I-03: `data/nda.md` is read from disk by `tests/test_smoke_ollama.py` with no size guard

**File:** `tests/test_smoke_ollama.py:32-36`
**Severity:** info
**Category:** documentation / DoS awareness

`_load` reads fixture files unconditionally. If someone swaps `data/nda.md` for a 200KB stress-test document, the integration test would silently exceed `num_ctx=16384` (T-02-S02). The `judge.py` logger emits `prompt_chars=` on every call, so the human running integration tests can observe this, but the test does not *assert* on it. Accepted per the plan's human-verification step; noted here for completeness.

**Fix hint:** No change needed for Phase 2. Phase 3 pre-loop test may want to add an explicit `assert prompt_chars < 40000` guard.

---

## Pitfall Verification Matrix

| Pitfall | Scope | Mitigation Required | Implementation Location | Verified? |
|---|---|---|---|---|
| **P2: Structure ≠ meaning** | Judge | Content validators (length minimums, rubric-ref checks) were *deferred* to Phase 3 per CONTEXT.md §deferred. | `src/judge.py:189` — `# TODO(P2, Phase 3): add reasoning-length content validator` | ✅ Correctly deferred. TODO present. |
| **P4: SDK + Ollama compat** | Agent + Judge | No `response_format`, no `client.beta.chat.completions.parse`, no `stream`; use `model_validate_json` for parsing. | `src/agent.py:56-64` and `src/judge.py:164-174` — plain `chat.completions.create` + `JudgeResult.model_validate_json(cleaned)`. Tests `test_run_agent_passes_num_ctx_and_temperature` and `test_num_ctx_in_every_call` positively assert `"response_format" not in kwargs` and `"stream" not in kwargs`. | ✅ Implemented and tested. |
| **P6: Context window** | Agent + Judge | Set `num_ctx` explicitly on **every** call via `extra_body={"options": {"num_ctx": N}}`. | `src/agent.py:63` and `src/judge.py:168` both pass `extra_body={"options": {"num_ctx": config.num_ctx}}`. Test `test_num_ctx_in_every_call` iterates all 3 retry calls asserting the key. | ✅ Implemented and tested. |
| **P7: Retry masks failure** | Judge | 3 attempts; append error feedback between attempts; on exhaustion log raw output + error, return sentinel (don't raise). | `src/judge.py:162-191`. Tests `test_retries_three_times_with_error_feedback` (growth 2→4→6), `test_graceful_failure_on_retry_exhaustion` (returns `scores=[]`), `test_graceful_failure_logs_raw_output` (raw + "exhausted" in ERROR records), `test_warning_logged_on_every_parse_failure`. | ✅ Implemented and tested. Retry feedback is appended per-attempt (line 179-180), not a fresh prompt. |
| **P8: Rubric vocab contamination** | Agent | Iteration-zero agent prompt must not contain rubric/playbook/evaluation vocabulary. | `src/agent.py:32-37` is a 4-line prompt with domain vocabulary only ("NDA", "issues", "significance", "clause reference", "risk assessment"). Test `test_prompt_scrubbed_of_rubric_vocab` checks 13 banned tokens. | ✅ Implemented and tested. Note: "risk assessment" is not in the banned list but is close to "evaluation" — the banned list is a reasonable minimal set. |
| **P12: Pydantic v1/v2 mismatch** | Judge | Use `model_validate_json` (v2), not v1 `parse_raw`. Single `ValidationError` handles both JSON-decode and schema errors. | `src/judge.py:33` `from pydantic import ValidationError`; `src/judge.py:174` `JudgeResult.model_validate_json(cleaned)`. | ✅ Implemented. |
| **P14: Markdown fences** | Judge | Strip common wrappers before Pydantic parse via `re.search(r"\{.*\}", raw, re.DOTALL)`. | `src/judge.py:72-84` `_extract_json` with outermost-brace match. Test `test_extract_json_strips_fences` covers ` ```json `, ` ``` `, bare JSON, nested objects, prose preamble, and empty string. | ✅ Implemented and well-tested. See L-01 for a documented edge case (wasted retries, not incorrect output). |

**Summary:** All seven in-scope pitfalls have working mitigations with tests. P2 is correctly deferred to Phase 3 with a TODO marker.

---

## Decision Compliance Matrix

| Decision | Statement | Implementation | Compliant? |
|---|---|---|---|
| **D-01** | Shared `get_client()` factory in `src/llm.py`, imported by both `agent.py` and `judge.py`. | `src/llm.py:15-23` defines `get_client()`. `src/agent.py:23` and `src/judge.py:36` both `from src.llm import get_client`. | ✅ |
| **D-02** | `num_ctx` default 16384. | `src/config.py:12` `num_ctx: int = 16384`. | ✅ |
| **D-03** | `num_ctx` configurable via `NUM_CTX` env var in `Config.from_env()`. | `src/config.py:40` `num_ctx=_int("NUM_CTX", 16384)`. | ✅ |
| **D-04** | `num_ctx` applied to every LLM call via `extra_body={"options": {"num_ctx": N}}`. | `src/agent.py:63` and `src/judge.py:168`. Tests assert across all retry calls. | ✅ |
| **D-05** | Two-message request: system = task+schema+example+"no fences" instruction; user = case data. | `src/judge.py:44-70` is the system prompt containing task, schema example, and no-preamble instruction. `src/judge.py:155-158` builds the 2-message structure. | ✅ |
| **D-06** | Data blocks in user message delimited by markdown headings in order: NDA → Agent Output → Rubric → Playbook. | `src/judge.py:95-104` `_build_user_message` concatenates in exact order. Test `test_build_user_message_uses_top_level_headings` verifies all 4 headings present. | ✅ |
| **D-07** | Heading-collision mitigation: chose top-level `#` (agent uses `##` and below). Mandatory for planner to document choice in judge.py comment. | `src/judge.py:7-8` documents the choice. **See M-02** — the mitigation is partial: NDA input already contains `#` so collision is possible from the NDA side, not prevented by the heading choice. Documented but understated. | ⚠️ Compliant as written (top-level `#` used, choice documented) but the collision-prevention rationale is wrong for the NDA side. See M-02. |
| **D-08** | Rubric passed as raw JSON string, verbatim, no transformation. | `src/judge.py:125-127` signature `run_judge(nda_text, agent_output, rubric, playbook)` — all four are `str`. `src/judge.py:101-102` embeds `{rubric}` directly. Docstring line 139 confirms: "rubric: Raw JSON string of data/rubric.json (D-08)". | ✅ |
| **D-09** | Exactly ONE concrete JSON example of a single-item JudgeResult in the system prompt. | `src/judge.py:53-66` shows one `scores` array containing one `RubricScore`-shaped object. No second example. | ✅ |
| **D-10** | System prompt explicitly says "Return only valid JSON. No preamble. No markdown code fences. No commentary." | `src/judge.py:50-51`: "Return only valid JSON matching the schema below. No preamble. No markdown code fences. No commentary before or after the JSON." Verbatim. Retry user message (`src/judge.py:117-122`) repeats the reminder. | ✅ |

**Summary:** 9/10 decisions fully compliant. D-07 is compliant in letter (top-level `#` used, documented in comment) but the spirit of the mitigation — "prevents heading collision" — holds only for the agent-output side, not the NDA side. M-02 above captures this.

---

## REVIEW ISSUES FOUND

| Severity | Count |
|---|---|
| blocker | 0 |
| high | 0 |
| medium | 2 |
| low | 4 |
| info | 3 |
| **total** | **9** |

No blockers. No high-severity findings. Both medium findings are fixable in-place without architectural change:
- **M-01** (test singleton leak) is a 5-line autouse fixture.
- **M-02** (heading collision rationale) is either a comment correction or a switch to a distinctive envelope marker.

The implementation is ready to proceed to Phase 3 once M-01 and M-02 are triaged. M-02 in particular may be re-scoped rather than "fixed" — the threat model accepts biased-scoring risk, so updating the docstring to match reality is a valid resolution.

---

*Reviewed: 2026-04-11*
*Reviewer: Claude (gsd-code-reviewer)*
*Depth: standard*
