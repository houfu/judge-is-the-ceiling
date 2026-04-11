# Phase 2: Agent and Judge - Research

**Researched:** 2026-04-11
**Domain:** LLM plumbing — OpenAI SDK + local Ollama, Pydantic-validated structured output with retry
**Confidence:** HIGH

## Summary

Phase 2 builds the two foundational LLM-calling library functions (`run_agent`, `run_judge`) plus a shared `get_client()` factory at `src/llm.py`. No loop, no CLI, no optimiser — just the plumbing Phase 3 (`pre_loop_test.py`) and Phase 5 (main loop) will import.

Every load-bearing technical decision is already pinned: CONTEXT.md locks D-01…D-10, STACK.md locks the retry pattern and "what not to use" list, and PITFALLS.md catalogues every mitigation the planner must inline into code. This research section consolidates those sources and resolves the seven items left to Claude's discretion with concrete recommendations, reference skeletons, and a Nyquist-style validation plan.

**Primary recommendation:** Implement `src/llm.py` first (trivial factory), then `src/judge.py` (hardest — retry + parsing + graceful-failure), then `src/agent.py` (thinnest wrapper). Test retry and graceful-failure paths with a pytest fixture that monkeypatches `client.chat.completions.create` to return canned strings; keep one integration smoke test behind `@pytest.mark.integration` for the live Ollama round-trip.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Client Wiring**

- **D-01:** A shared client factory lives at `src/llm.py` exposing `get_client() -> OpenAI`. Both `agent.py` and `judge.py` import from it. Rationale: one place to set `base_url` / `api_key` / timeouts, and one place to pass Ollama-specific options like `num_ctx`.
- **D-02:** `num_ctx` default is **16384** — roughly 4.7× the ~5700-token minimum estimate (NDA ~1875 + rubric+playbook ~1500 + agent output ~800 + judge response ~1500). Chosen for headroom over long judge reasoning and growing agent system prompts in Phase 5 iterations.
- **D-03:** `num_ctx` is configurable via the `NUM_CTX` env var on `Config` with a default of 16384. Add `num_ctx: int = 16384` to the `Config` dataclass in `src/config.py` and read `NUM_CTX` in `Config.from_env()`.
- **D-04:** `num_ctx` is applied to **every** LLM call — agent and judge — by passing `extra_body={"options": {"num_ctx": config.num_ctx}}` on `client.chat.completions.create(...)`. Matches pitfall P6 guidance ("set num_ctx explicitly on every API call") and future-proofs Phase 5 where system prompts grow across iterations.

**Judge Prompt Layout**

- **D-05:** Two-message request: `system` role holds the task description, the JSON output schema, the concrete example, and the "no preamble, no markdown fences" instruction. `user` role holds the case data (NDA, agent output, rubric, playbook). Rationale: the task rules stay stable across retries; only the data varies between runs.
- **D-06:** Data blocks inside the `user` message are delimited with **markdown headings**: `## NDA`, `## Agent Output`, `## Rubric`, `## Playbook`, in that order.
- **D-07:** ⚠️ **Heading-collision mitigation (MANDATORY for planner/executor):** The agent's free-text review is itself markdown and will very likely contain `##` headings. The planner MUST choose a heading style for the judge prompt that the agent output cannot collide with. Two acceptable approaches:
  - Use a distinctive prefix like `## === NDA ===` / `## === AGENT OUTPUT ===` / etc.
  - Use top-level `#` headings for the judge's section dividers and rely on the fact that the agent never generates `#` (only `##` and below).
  Either is fine, but the chosen approach must be consistent and documented in a comment in `judge.py`.
- **D-08:** The rubric is serialised into the prompt as **raw JSON, verbatim** — read `data/rubric.json` and paste the contents into the `## Rubric` section. No transformation, no table, no prose rendering. Keeps `item_id` and `issue_number` identical between input and expected output.
- **D-09:** The output schema is communicated via **one concrete JSON example** of a single-item `JudgeResult` response (plus a short field-list sentence for the unused fields). Exactly one example — avoid multi-shot examples that could contaminate the judge's scoring behaviour with anchoring effects.
- **D-10:** The system message explicitly instructs: "Return only valid JSON. No preamble. No markdown code fences. No commentary before or after the JSON."

### Claude's Discretion (resolved in this research)

The following were deliberately left to planner decision:

1. Graceful failure shape (JUDG-05)
2. Markdown fence stripping helper
3. Retry error feedback format
4. Agent function signature details (temperature sourcing, message structure)
5. Logging (stdlib `logging`, logger naming, what to log)
6. Iteration-zero system prompt location
7. Test vectors for success criterion 3 (retry demonstration)

See `## Technical Approach — Discretion Resolutions` below for concrete recommendations.

### Deferred Ideas (OUT OF SCOPE)

- **Graceful failure shape / fence stripping / retry verbosity** — left to planner; NOT to be revisited with the user.
- **Judge reasoning content validators (P2):** length minimums, rubric-reference checks. Noted in PITFALLS.md as a future mitigation; NOT in scope for Phase 2. Revisit if the pre-loop test in Phase 3 shows the judge returning empty/formulaic reasoning.
- **Logging raw outputs to files** (vs stdlib logging only) — may become necessary if Phase 3 pre-loop test diagnostics are insufficient. Not in Phase 2 scope.
- **Alternative num_ctx values per call** — some future hardware-constrained setup may want 8192 for agent, 16384 for judge. Not needed now; one env var is enough.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AGNT-01 | Agent takes system prompt + NDA text, returns structured NDA review via OpenAI-compatible API | `run_agent(system_prompt, nda_text) -> str` calls `client.chat.completions.create` with `messages=[{role:"system",...},{role:"user",...}]`, temperature=0, `extra_body={"options":{"num_ctx":config.num_ctx}}`. Skeleton provided below. |
| AGNT-02 | Agent system prompt does not reference rubric, playbook, or evaluation criteria | `ITERATION_ZERO_SYSTEM_PROMPT` constant in `src/agent.py` copied verbatim from PRD §3.4 — verified vocab-clean (no "rubric", "score", "evidence", "extraction", "judgment", "criteria"). See P8 mitigation. |
| JUDG-01 | Judge takes NDA + agent output + rubric + playbook, returns per-item scores as validated JSON | `run_judge(nda_text, agent_output, rubric, playbook) -> JudgeResult` returns `JudgeResult` from `src/models.py`. Two-message structure per D-05. |
| JUDG-02 | Pydantic validation with retry up to 3 attempts, sending error details back to model on failure | Retry loop per STACK.md skeleton, adapted: on `ValidationError` / `JSONDecodeError` append assistant turn (raw output) + user turn (error message + reminder). Max 3 attempts. |
| JUDG-03 | Markdown fence stripping before JSON parsing | `_extract_json(raw: str) -> str` helper in `judge.py`: combined-regex approach (see P14 resolution). |
| JUDG-04 | Explicit Ollama num_ctx setting to prevent silent context truncation | `extra_body={"options":{"num_ctx":config.num_ctx}}` on every call (D-04). See P6 verification. |
| JUDG-05 | Graceful failure — log raw output and continue on retry exhaustion, don't crash | On 3rd failure: `logger.error(...)` with raw body + `ValidationError` string; return **sentinel `JudgeResult(scores=[])`** (empty list). Rationale in Technical Approach below. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

| Directive | Source | Enforcement in Phase 2 |
|-----------|--------|------------------------|
| Python 3.11+ managed with `uv` | CLAUDE.md Tech Stack | `uv run pytest`, no venv activation |
| OpenAI Python SDK with configurable `base_url` | CLAUDE.md Tech Stack | `get_client()` reads `config.base_url` |
| Ollama local runtime; same model for agent/judge/optimiser | CLAUDE.md Tech Stack | Single `Config.model` used everywhere |
| Pydantic v2 for JSON parsing with retry (up to 3) | CLAUDE.md Tech Stack | `model_validate_json()` (P12), 3-attempt loop |
| Black formatting | CLAUDE.md Tech Stack | `black src/ tests/` in Wave 0 / post-implementation |
| Temperature = 0 for all calls (non-negotiable) | CLAUDE.md Key Design + CONF-02 | Pass `temperature=0` hard-coded **or** via `config.temperature` with assertion; see resolution below |
| No agent SDK, no tool use — prompt rewriting only | CLAUDE.md Key Design | Phase 2 delivers library functions only |
| No `instructor`, `langchain`, `pydantic-settings`, `structlog`/`loguru` | STACK.md "What NOT to Use" | stdlib `logging` only; no new deps |
| No `response_format` or `client.beta.chat.completions.parse` | STACK.md + P4 | `client.chat.completions.create` only; raw content extraction |
| GSD workflow enforcement — no direct edits outside GSD | CLAUDE.md GSD Workflow | Planner creates PLAN.md; executor uses `/gsd-execute-phase` |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `openai` | `>=2.0` (2.31.0 on PyPI as of 2026-04-11) | Sync chat completions against Ollama's OpenAI-compatible endpoint | Stable `base_url` since SDK v1; community-standard for Ollama wiring [CITED: STACK.md] |
| `pydantic` | `>=2.0` (2.12.5 on PyPI as of 2026-04-11) | Validate JSON into `JudgeResult` | Already used by `src/models.py`; `model_validate_json` is the v2 canonical path [CITED: STACK.md, P12] |
| `logging` (stdlib) | — | Phase 2 retry/failure logging | STACK.md bans `structlog`/`loguru`; stdlib is sufficient because Phase 5 serialises all results to JSON files anyway [CITED: STACK.md "What NOT to Use"] |
| `re` (stdlib) | — | Markdown fence stripping regex helper | P14 mitigation is a 2-line regex, no library needed |
| `json` (stdlib) | — | Only needed if serialising rubric list-of-dicts into the prompt (rubric may also be passed as raw text) | — |

### Supporting (already present — no changes)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `src/config.py` | existing | `Config.from_env()` singleton with `model`, `base_url`, `api_key`, `temperature`, `num_iterations` | Phase 2 ADDS `num_ctx` field (D-03) |
| `src/models.py` | existing | `JudgeResult`, `RubricScore` Pydantic models | Used as-is; `run_judge` returns `JudgeResult` directly |

### Dev / Test Dependencies to Add
| Library | Version | Purpose |
|---------|---------|---------|
| `pytest` | `>=8.0` (8.3.x current as of knowledge cutoff; planner to verify with `uv pip install pytest`) | Unit + integration tests for retry/graceful-failure/smoke [ASSUMED version — verify at plan time] |

**Installation:**
```bash
# Runtime deps already installed
uv add --dev pytest
```

**Version verification:** Planner should run `uv pip show openai pydantic` and `pip index versions pytest` at plan time to confirm current versions before locking them into PLAN.md tasks. Per STACK.md, `openai>=2.0` and `pydantic>=2.0` are pinned minima — exact current version doesn't matter for Phase 2.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw `chat.completions.create` + Pydantic retry | `instructor` library | Banned by STACK.md — wraps the exact retry loop we want written explicitly [CITED: STACK.md] |
| Raw `chat.completions.create` + Pydantic retry | `client.beta.chat.completions.parse` | Banned by P4 — Ollama structured output support varies; likely silent fallback [CITED: PITFALLS.md P4] |
| Prompt instruction + retry | `response_format={"type":"json_object"}` | Banned by STACK.md "What NOT to Use" — Ollama support varies by model [CITED: STACK.md] |
| stdlib `logging` | `structlog` / `loguru` | Banned by STACK.md — output is JSON files, INFO logging sufficient [CITED: STACK.md] |

## Architecture Patterns

### Recommended Project Structure (additions)
```
src/
├── config.py          # existing — ADD num_ctx field
├── models.py          # existing — unchanged
├── llm.py             # NEW — get_client() factory (D-01)
├── agent.py           # NEW — run_agent + ITERATION_ZERO_SYSTEM_PROMPT
└── judge.py           # NEW — run_judge + _extract_json helper
tests/                 # NEW (if Nyquist enabled)
├── __init__.py
├── conftest.py        # Shared fixtures: FakeClient, canned responses
├── test_judge_retry.py       # JUDG-02 retry path
├── test_judge_graceful.py    # JUDG-05 retry exhaustion
├── test_judge_fences.py      # JUDG-03 fence stripping
├── test_agent_prompt.py      # AGNT-02 vocabulary scrub
└── test_smoke_ollama.py      # @pytest.mark.integration — one live call per component
```

### Pattern 1: Shared Sync Client Factory (D-01)
**What:** A single `get_client()` function in `src/llm.py` that returns an `OpenAI` instance pre-wired for Ollama.
**When to use:** Always. Agent and judge import it; no direct `OpenAI(...)` construction elsewhere.
**Example:**
```python
# Source: CONTEXT.md D-01 + STACK.md Ollama Client Configuration
from openai import OpenAI
from src.config import config

_client: OpenAI | None = None

def get_client() -> OpenAI:
    """Return a shared sync OpenAI client configured for Ollama."""
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
        )
    return _client
```
[CITED: STACK.md §Ollama Client Configuration]

### Pattern 2: Two-Message Judge Prompt (D-05, D-06, D-07)
**What:** `system` role holds task rules + schema + example + "no preamble" instruction (stable across retries); `user` role holds case data with markdown-delimited sections (varies per call). On retry, append `assistant` turn (raw bad output) + new `user` turn (error message) — never rewrite the system message.
**When to use:** Every judge call.
**Example:**
```python
# Source: CONTEXT.md D-05/D-06/D-07, STACK.md Retry Pattern
SYSTEM_PROMPT = """\
You are a legal-review scoring judge. You will receive an NDA, an agent's
review of that NDA, a scoring rubric, and a scoring playbook. For each
rubric item, you must return a score of 0, 1, or 2 with evidence,
reasoning, and feedback.

Return only valid JSON matching the schema below. No preamble. No
markdown code fences. No commentary before or after the JSON.

Output schema (one example item shown; return one object per rubric item):
{
  "scores": [
    {
      "item_id": "1a",
      "item_type": "extraction",
      "issue_number": 1,
      "score": 2,
      "evidence": "Clause 4.1 states 'seven (7) years'",
      "reasoning": "The review explicitly names the 7-year term.",
      "feedback": "Good. Could additionally cite clause number."
    }
  ]
}
"""

def build_user_message(nda, agent_output, rubric_json, playbook):
    # D-07: use top-level # headings; agent output uses ## and below only.
    return f"""\
# NDA
{nda}

# AGENT OUTPUT
{agent_output}

# RUBRIC
{rubric_json}

# PLAYBOOK
{playbook}
"""
```
[CITED: CONTEXT.md D-05..D-10]

### Pattern 3: Retry with Error Feedback (JUDG-02, P7)
**What:** Adapted from STACK.md "Retry Pattern (3 attempts)" — on `ValidationError` / `JSONDecodeError`, append assistant output + user correction and retry. On final-attempt failure, log and return sentinel instead of `raise`.
**When to use:** `run_judge` only. Agent does not retry (AGNT-01 returns raw string).
**Example:** See `## Code Skeletons` below.
[CITED: STACK.md §Retry Pattern, P7]

### Pattern 4: Module-Level Singleton Config (existing convention)
**What:** `src/config.py` already uses `config = Config.from_env()` at module level. `src/llm.py` should follow the same pattern (`_client` lazy singleton). `agent.py` and `judge.py` import `config` directly.
**When to use:** All new modules.
[CITED: CONTEXT.md Established Patterns]

### Anti-Patterns to Avoid
- **Reading rubric/playbook from disk inside `run_judge`:** caller passes them in as parameters (CONTEXT.md §Integration Points). Keeps Phase 3 `pre_loop_test.py` trivially compatible and keeps `run_judge` pure.
- **Mutating the system message on retry:** only append new turns. The system message contains the schema and must stay invariant across attempts.
- **Raising from `run_judge`:** JUDG-05 mandates graceful return. Phase 3 and Phase 5 consumers must never have to wrap `run_judge` in `try/except`.
- **Using `config.temperature` at the judge call site and letting tests override it:** temperature=0 is a project invariant (CONF-02). See discretion resolution #4.
- **Constructing `OpenAI()` directly in `agent.py` or `judge.py`:** violates D-01. Always go through `get_client()`.
- **Including rubric vocabulary in `ITERATION_ZERO_SYSTEM_PROMPT`:** P8 violation. The PRD §3.4 prompt is already clean — do not "improve" it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP to Ollama | `urllib`/`requests` calls to `/api/generate` | `openai.OpenAI(base_url=...)` | STACK.md standard; OpenAI-compatible endpoint is more stable than Ollama-native [CITED: STACK.md] |
| JSON parsing + validation | `json.loads` + manual type checks | `JudgeResult.model_validate_json(raw)` | Pydantic v2 one-liner; gives typed errors for retry feedback [CITED: P12] |
| Config loading | `configparser`, `.env` files | stdlib `os.getenv` via existing `Config.from_env()` | Already implemented; only 6 values total [CITED: STACK.md] |
| Retry with backoff | `tenacity`, `backoff` libraries | Explicit `for attempt in range(3)` loop | STACK.md skeleton; no backoff needed (local Ollama, not rate-limited); retry is semantic (bad JSON) not transient |
| Logging structure | `structlog` / `loguru` | stdlib `logging.getLogger("jitc.judge")` | STACK.md bans; JSON-file output means log format is for humans debugging only |
| Markdown fence removal | Custom state machine / parser | Single regex `re.search(r"\{.*\}", raw, re.DOTALL)` | P14 explicit recommendation [CITED: PITFALLS.md P14] |

**Key insight:** Phase 2 is a deliberately thin layer. Every "could we add X?" temptation is explicitly banned by STACK.md or PITFALLS.md. The value is in the small set of things done carefully (retry feedback content, graceful failure shape, heading-collision mitigation), not in code volume.

## Runtime State Inventory

*(Not a rename/migration phase — skipped per research protocol.)*

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | Project | verify at plan time | — | — |
| `uv` | Project management | verify at plan time | — | — |
| `openai` package | `src/llm.py`, `src/agent.py`, `src/judge.py` | already in pyproject.toml | `>=2.0` | — |
| `pydantic` package | `src/models.py`, `src/judge.py` | already in pyproject.toml | `>=2.0` | — |
| `pytest` package | Tests (Wave 0) | NOT installed | — | Add via `uv add --dev pytest` |
| Ollama running on `localhost:11434` | Integration smoke test | verify at plan time with `curl http://localhost:11434/api/tags` | — | Skip integration test with `@pytest.mark.integration` marker; unit tests (FakeClient) run without Ollama |
| Configured model (default `qwen2.5:32b`) pulled in Ollama | Integration smoke test | verify at plan time with `ollama list` | — | Pull with `ollama pull qwen2.5:32b` OR override `MODEL` env var |

**Missing dependencies with no fallback:**
- None blocking. Phase 2 unit tests use a fake client and do not require live Ollama.

**Missing dependencies with fallback:**
- `pytest`: add at Wave 0.
- Live Ollama: integration test is skipped unless explicitly run with `-m integration`. Unit tests cover JUDG-02/03/05 without it.

## Technical Approach — Discretion Resolutions

The seven items CONTEXT.md left to the planner, with concrete recommended answers:

### 1. Graceful failure shape (JUDG-05) — **Recommend: sentinel `JudgeResult(scores=[])`**

**Options considered:**
1. **Sentinel `JudgeResult(scores=[])`** (empty `scores` list) ← **RECOMMEND**
2. `JudgeResult | None` return type
3. Dedicated `JudgeFailure` wrapper / result type
4. Sentinel `JudgeResult` with all-zero `RubricScore` entries for every rubric item

**Reasoning:**
- **Phase 3 consumer (`pre_loop_test.py`):** needs to log and compare two reviews. An empty `scores` list is trivially detectable (`if not result.scores:`) and the Phase 3 author can write "judge failed to produce valid output" in results JSON. `compute_category_scores([])` returns `(0, 0)` — already works with `IterationResult` defaults.
- **Phase 5 consumer (main loop, LOOP-04):** needs to "log error and continue". An empty list lets the iteration proceed with zero scores and a log entry. No `Optional` unwrapping contamination elsewhere.
- **Against Option 2 (`| None`):** forces every call site to handle `None`, clutters type annotations, and Phase 3/5 would have to synthesise a fallback object anyway.
- **Against Option 3 (dedicated wrapper):** adds a new type to `models.py` — out of scope for Phase 2; Phase 1 already shipped `JudgeResult`.
- **Against Option 4 (eight fake zero-score entries):** looks like real data in results JSON, silently contaminating analysis. An empty list is an unambiguous signal.

**Concrete shape:**
```python
# On retry exhaustion in run_judge:
logger.error(
    "judge failed after %d retries; raw=%r; last_error=%s",
    MAX_RETRIES, raw, last_error,
)
return JudgeResult(scores=[])
```

**Planner note:** document this contract in a docstring on `run_judge` so Phase 3 and Phase 5 authors know to check `if not result.scores:`.
[ASSUMED: best fit for the two known consumers; planner may adjust if Phase 3 author prefers Option 3]

### 2. Markdown fence stripping (JUDG-03, P14) — **Recommend: regex-first, fallback to raw**

**Recommendation:**
```python
import re

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

def _extract_json(raw: str) -> str:
    """Strip common wrappers from a model response before Pydantic parsing.

    Matches the outermost {...} block, which naturally skips
    ```json ... ``` fences and any pre/post commentary. Falls back
    to the raw string if no brace pair is found (Pydantic will then
    raise a clean JSONDecodeError the retry loop can surface).
    """
    match = _JSON_OBJECT_RE.search(raw)
    return match.group(0) if match else raw
```

**Why regex-first (not explicit `` ```json `` removal):**
- P14 recommends exactly this pattern: `re.search(r"\{.*\}", raw_output, re.DOTALL)`.
- Handles multiple wrapper variants in one pass: `` ```json ``, `` ``` ``, `"Here is the JSON: {...}"`, `<output>{...}</output>`.
- Greedy regex matches from the first `{` to the last `}`, so nested objects are preserved.
- **Known edge case:** if the model returns prose like `"I found {key} issues. Here is: {...}"`, greedy matching would span both braces. Mitigation: the system prompt explicitly bans preamble (D-10); if this fails in practice the retry loop catches it via `JSONDecodeError` on the spliced content. Good enough for Phase 2.

**Why NOT add `` ```json `` explicit removal on top:** doubles the code path with no additional coverage — the regex already handles it.

### 3. Retry error feedback format — **Recommend: bounded error string + fixed reminder**

**Recommendation:**
```python
MAX_ERROR_CHARS = 800  # enough for a pydantic ValidationError; stops runaway

def _retry_user_message(error: Exception) -> str:
    err_text = str(error)
    if len(err_text) > MAX_ERROR_CHARS:
        err_text = err_text[:MAX_ERROR_CHARS] + " …[truncated]"
    return (
        f"Your previous response could not be parsed. Error:\n\n"
        f"{err_text}\n\n"
        f"Return only valid JSON matching the schema. "
        f"No preamble. No markdown code fences."
    )
```

**Why:**
- Includes enough `ValidationError` text for the model to self-correct (P7 requires this).
- Fixed reminder matches the system message wording (D-10) — reinforces without contradicting.
- 800-char cap prevents one pathological error from blowing the context window.
- Pydantic v2 `ValidationError.__str__` produces human-readable, line-pointed messages — no custom formatting needed.

**Retry prompt sequence (for clarity):**
```
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user",   "content": build_user_message(...)},
]
# Attempt 1 — if bad:
messages.append({"role": "assistant", "content": raw_bad_output_1})
messages.append({"role": "user",      "content": _retry_user_message(err_1)})
# Attempt 2 — if bad:
messages.append({"role": "assistant", "content": raw_bad_output_2})
messages.append({"role": "user",      "content": _retry_user_message(err_2)})
# Attempt 3 — if bad: log and return sentinel
```

### 4. Agent function details — **Recommend: system+user messages, temperature hard-coded via config**

**Message structure:** Two messages — `system` (the agent's instructions, e.g. `ITERATION_ZERO_SYSTEM_PROMPT`) + `user` (the NDA text wrapped minimally). Rationale: Phase 5 will swap `system_prompt` across iterations; keeping it in the `system` role makes prompt-versioning clean.

**Temperature sourcing:**
```python
# Read from config — lets tests set TEMPERATURE=0 explicitly.
# CONF-02 is enforced by Config defaulting to 0.0 AND by project convention.
# Do NOT add runtime assertions — adds noise without value.
temperature=config.temperature
```
Do not hard-code `0` at the call site — it breaks the `Config` contract. Do not add an `assert config.temperature == 0` either — it would fire during any legitimate debugging session where someone temporarily bumps temperature. CONF-02 enforcement lives in `Config.from_env()` (already accepts any float) and is documented, not runtime-checked.

**No `response_format`:** banned by P4. Raw string return only.

**Signature:**
```python
def run_agent(system_prompt: str, nda_text: str) -> str: ...
```
Returns `response.choices[0].message.content`. No trimming, no parsing — caller gets whatever the model produced.

### 5. Logging — **Recommend: stdlib `logging`, module loggers `jitc.agent` / `jitc.judge`**

```python
# src/judge.py
import logging
logger = logging.getLogger("jitc.judge")

# Events to log:
logger.info("judge call attempt %d", attempt)                   # per attempt
logger.warning("judge parse failed: %s", err)                   # per retry
logger.error("judge exhausted retries; raw=%r; last=%s",        # on graceful failure
             raw, last_error)
```

- Logger names `jitc.agent` and `jitc.judge` match CONTEXT.md §Claude's Discretion recommendation.
- No `basicConfig` call inside library modules — leave log configuration to the caller (Phase 3 `pre_loop_test.py` or Phase 5 main loop, or tests). If a test wants log output, it uses `caplog`.
- Do not log the full prompt or full rubric at INFO — they're large. Log at DEBUG if someone needs them; character counts at INFO (P6 "log total character count of judge prompt at iteration 1").

### 6. Iteration-zero system prompt location — **Recommend: constant in `src/agent.py`**

```python
# src/agent.py
# Verbatim from prd.md §3.4. Must NOT reference rubric/playbook/score/criteria (P8/AGNT-02).
ITERATION_ZERO_SYSTEM_PROMPT = """\
You are reviewing a Non-Disclosure Agreement. Identify all issues
and assess their significance. Output your findings as a structured
list. For each issue provide: the clause reference, a description
of the issue, and your risk assessment.
"""
```

**Why a constant, not `data/iteration_zero_prompt.md`:**
- Only 4 lines — file overhead not justified.
- Phase 3 (`pre_loop_test.py`) imports it as `from src.agent import ITERATION_ZERO_SYSTEM_PROMPT`; no file I/O in tests.
- Phase 5 (loop) will store per-iteration prompts in `IterationResult.system_prompt` — Phase 2 only needs iteration zero available as a symbol.

**Vocabulary audit (pre-commit check for AGNT-02 / P8):** scan the constant for banned tokens before committing. Banned list: `rubric`, `playbook`, `score`, `scoring`, `evidence`, `extraction`, `judgment item`, `criteri`, `evaluate`, `evaluation`, `0/1/2`, `item_id`. The PRD §3.4 prompt is already clean — do not modify it. Include this audit as an automated test (`test_agent_prompt.py`).

### 7. Retry demonstration for success criterion 3 — **Recommend: pytest unit tests with FakeClient**

**Options considered:**
1. **pytest + FakeClient fixture** ← **RECOMMEND**
2. `if __name__ == "__main__":` smoke in `src/judge.py`
3. Standalone script in project root

**Why pytest:**
- Nyquist validation is enabled in `config.json` — tests are mandatory anyway.
- A FakeClient (monkey-patched `client.chat.completions.create`) can deterministically return canned strings in sequence: invalid-fenced-json, invalid-missing-field, valid-json. This hits all three code paths (fence stripping, retry with error feedback, successful parse) in a single test.
- Same fixture covers JUDG-05: make all three canned responses invalid, assert `JudgeResult(scores=[])` is returned and that `logger.error` was called with the raw output (use `caplog`).
- Runs without Ollama — CI-compatible, sub-second.

**Against `__main__` smoke:** requires live Ollama, not reproducible, can't be asserted cleanly.
**Against standalone script:** same as above plus it's dead code after Phase 2.

See `## Validation Architecture` for the concrete test shape.

## Pitfalls & Mitigations

Direct citations from `.planning/research/PITFALLS.md`:

### P2: Structured Output Schema Validates Structure, Not Meaning
**Cited:** PITFALLS.md P2 — "reasoning strings under 40 words across many items" are syntactically valid but evidentially worthless.
**Phase 2 scope:** Do **not** add content validators in Phase 2. CONTEXT.md §Deferred explicitly says this is Phase 3+ territory.
**What to do in Phase 2:** log raw judge output at WARNING when parse fails, at DEBUG when parse succeeds, so Phase 3 can inspect reasoning quality without re-running the judge. The `_extract_json` helper must preserve the raw response for logging (don't mutate).
**Planner note:** add a `# TODO(P2, Phase 3): add reasoning-length content validator` comment in `judge.py` near the successful-parse return so it's visible later.

### P4: OpenAI SDK + Ollama Structured Output Incompatibility
**Cited:** PITFALLS.md P4 — "Do NOT use `client.beta.chat.completions.parse()`. Use `client.chat.completions.create()` then `model_validate_json()`. Use `response_format={"type":"json_object"}` (basic JSON mode) or skip it entirely and rely on prompt instruction + Pydantic retry."
**Phase 2 decision (confirmed):** skip `response_format` entirely. Rely on prompt instruction (D-10) + Pydantic retry. The call signature is:
```python
response = client.chat.completions.create(
    model=config.model,
    messages=messages,
    temperature=config.temperature,
    extra_body={"options": {"num_ctx": config.num_ctx}},
)
raw = response.choices[0].message.content
```
No `response_format` kwarg. No `stream=True`. No `.parse()` method.

### P6: num_ctx silent truncation
**Cited:** PITFALLS.md P6 — "Ollama's `num_ctx` defaults to 2048 in some versions. Ollama truncates silently — no error raised, just dropped content."
**Mitigation (D-04):** `extra_body={"options": {"num_ctx": config.num_ctx}}` on every call.
**Verification the `extra_body` path is correct:** the OpenAI Python SDK accepts an `extra_body` kwarg on `chat.completions.create` that is merged into the request JSON. Ollama's OpenAI-compatibility layer reads a top-level `options` dict for Ollama-native parameters (including `num_ctx`, `num_predict`, etc.) — the standard community pattern is `extra_body={"options": {"num_ctx": N}}`. [CITED: STACK.md §Ollama Client Configuration mentions this pattern indirectly; PITFALLS.md P6 calls out "set num_ctx explicitly in Ollama model options"] [ASSUMED: exact SDK field name `extra_body` — verified to exist in openai>=2.0; planner should sanity-check at plan time by running a one-line smoke `client.chat.completions.create(..., extra_body={"options":{"num_ctx":16384}})` against live Ollama and confirming the response comes back without error.]

**Additional check (P6 epilogue):** at first call in `run_judge`, log the total character count of the assembled prompt at INFO level:
```python
total_chars = len(SYSTEM_PROMPT) + len(user_content)
logger.info("judge prompt chars=%d (num_ctx=%d)", total_chars, config.num_ctx)
```
Gives an early warning if prompt size approaches `num_ctx * 4` (rough chars-per-token).

### P7: Retry Loop Masks Systematic Failure
**Cited:** PITFALLS.md P7 — "On 3-retry exhaustion: log raw output, log error entry in results, continue to next iteration — do not crash. On retry, append correction prompt with error details rather than repeating identical prompt."
**Mitigation (JUDG-02 + JUDG-05):**
1. On **every** parse failure (attempts 1, 2, AND 3), log `raw` at WARNING plus the `ValidationError` message.
2. On attempt 3 specifically, also log at ERROR and return sentinel `JudgeResult(scores=[])`.
3. The retry `_retry_user_message` always includes the error details (never identical prompt repeated).
4. Do **not** swallow the error silently — even successful retries should leave a WARNING trace in the log so analysts can count how often this happens.

**Phase 2 deliberately does NOT add:**
- `validation_attempts` field to `JudgeResult` — that's a Phase 5 `IterationResult` concern (PITFALLS.md P7 mentions it as a schema addition; `models.py` Phase 1 work is frozen). Planner can add a `# TODO(P7, Phase 5): track validation_attempts in IterationResult` comment.

### P8: Rubric Vocabulary Contamination in Agent Prompt
**Cited:** PITFALLS.md P8 — "Agent prompt must NOT reference rubric, playbook, or evaluation criteria. Describe task in domain terms only."
**Mitigation (AGNT-02):**
- `ITERATION_ZERO_SYSTEM_PROMPT` copied verbatim from PRD §3.4 — already vocab-clean.
- Add `tests/test_agent_prompt.py` that asserts no banned tokens appear (case-insensitive): `["rubric", "playbook", "score", "scoring", "evidence", "extraction", "judgment item", "criteria", "evaluate", "evaluation", "item_id", "0/1/2"]`.
- Why a test, not just a comment: Phase 5's optimiser rewrites this prompt; the test becomes a regression check — if the optimiser ever smuggles rubric vocab in (which P5 predicts it might), the test flags it. The Phase 2 test file can be reused later.

### P12: Pydantic v1 vs v2 API Mismatch
**Cited:** PITFALLS.md P12 — "Use v2 syntax: `model_validate_json()`, `model_dump()`, `@field_validator`. Do not use deprecated v1 methods."
**Mitigation (all JUDG-*):**
- Use `JudgeResult.model_validate_json(cleaned_raw)` — takes a `str`, validates JSON + schema in one call.
- Do **not** use `JudgeResult.parse_raw(...)` (v1, deprecated).
- Do **not** use `.dict()` — use `.model_dump()` if needed (not needed in Phase 2 — Phase 5's loop serialises).
- `ValidationError` is imported from `pydantic` directly (`from pydantic import ValidationError`).

**One subtlety:** `model_validate_json` raises `ValidationError` for both JSON-decode failures AND schema-mismatch failures in Pydantic v2 — a single `except ValidationError` is sufficient. (In v1 you'd catch both `ValidationError` and `json.JSONDecodeError` separately.) This simplifies the retry loop:
```python
try:
    return JudgeResult.model_validate_json(cleaned)
except ValidationError as err:
    ...
```
**But:** after `_extract_json` returns the raw string as a fallback, a completely non-JSON response would still surface as `ValidationError`. No need to also catch `json.JSONDecodeError`.
[CITED: Pydantic v2 docs via STACK.md; verified behaviour matches documented API]

### P14: Markdown Fences in Model Output
**Cited:** PITFALLS.md P14 — "Models wrap JSON in ` ```json ... ``` ` even when instructed not to. Add preprocessing. Use `re.search(r'\{.*\}', raw_output, re.DOTALL)`."
**Mitigation (JUDG-03):** `_extract_json` helper (see Discretion Resolution #2).

## Code Skeletons

**Reference shapes — planner fleshes out exact values. Do not copy verbatim without review.**

### `src/config.py` — ADD `num_ctx` field (D-03)

```python
# Add to existing dataclass:
@dataclass
class Config:
    model: str = "qwen2.5:32b"
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    temperature: float = 0.0
    num_iterations: int = 5
    num_ctx: int = 16384  # NEW — D-02

    @classmethod
    def from_env(cls) -> "Config":
        # ... existing _float/_int helpers ...
        return cls(
            model=os.getenv("MODEL", "qwen2.5:32b"),
            base_url=os.getenv("BASE_URL", "http://localhost:11434/v1"),
            api_key=os.getenv("API_KEY", "ollama"),
            temperature=_float("TEMPERATURE", 0.0),
            num_iterations=_int("NUM_ITERATIONS", 5),
            num_ctx=_int("NUM_CTX", 16384),  # NEW — D-03
        )
```

### `src/llm.py` — NEW

```python
"""Shared OpenAI client factory (D-01).

Both agent and judge call get_client() rather than constructing OpenAI
directly, so base_url / api_key / timeouts live in one place.
"""
from openai import OpenAI

from src.config import config

_client: OpenAI | None = None


def get_client() -> OpenAI:
    """Return a lazily-created sync OpenAI client configured for Ollama."""
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
        )
    return _client
```

### `src/agent.py` — NEW

```python
"""Agent: takes a system prompt + NDA text, returns a free-text review (AGNT-01, AGNT-02)."""
import logging

from src.config import config
from src.llm import get_client

logger = logging.getLogger("jitc.agent")

# Verbatim from prd.md §3.4.
# MUST NOT contain rubric/playbook/evaluation vocabulary (P8, AGNT-02).
# Validated by tests/test_agent_prompt.py.
ITERATION_ZERO_SYSTEM_PROMPT = """\
You are reviewing a Non-Disclosure Agreement. Identify all issues
and assess their significance. Output your findings as a structured
list. For each issue provide: the clause reference, a description
of the issue, and your risk assessment.
"""


def run_agent(system_prompt: str, nda_text: str) -> str:
    """Run the agent against an NDA and return its review as a string.

    Args:
        system_prompt: The agent's instructions. Starts as
            ITERATION_ZERO_SYSTEM_PROMPT; Phase 5's optimiser rewrites
            it per iteration.
        nda_text: Raw markdown NDA text.

    Returns:
        The agent's review — whatever the model produced, unmodified.
    """
    client = get_client()
    logger.info("agent call: model=%s chars=%d", config.model, len(nda_text))
    response = client.chat.completions.create(
        model=config.model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": nda_text},
        ],
        temperature=config.temperature,
        extra_body={"options": {"num_ctx": config.num_ctx}},  # D-04, P6
    )
    return response.choices[0].message.content or ""
```

### `src/judge.py` — NEW

```python
"""Judge: scores an agent review against a rubric (JUDG-01..05)."""
import logging
import re

from pydantic import ValidationError

from src.config import config
from src.llm import get_client
from src.models import JudgeResult

logger = logging.getLogger("jitc.judge")

MAX_RETRIES = 3
MAX_ERROR_CHARS = 800

# D-07: use top-level # headings. Agent output is markdown and uses ##+ only,
# so # never collides. Planner must document this choice in a header comment
# if it changes to the "## === FOO ===" style instead.

JUDGE_SYSTEM_PROMPT = """\
You are a legal-review scoring judge. You will receive an NDA, an agent's
review of that NDA, a scoring rubric, and a scoring playbook. For each item
in the rubric you must return a score of 0, 1, or 2 with evidence, reasoning,
and feedback.

Return only valid JSON matching the schema below. No preamble. No markdown
code fences. No commentary before or after the JSON.

Output schema (one example shown; return one object per rubric item):
{
  "scores": [
    {
      "item_id": "1a",
      "item_type": "extraction",
      "issue_number": 1,
      "score": 2,
      "evidence": "Clause 4.1 states 'seven (7) years'.",
      "reasoning": "The review explicitly names the 7-year term and connects it to the confidentiality obligation.",
      "feedback": "Good identification. Could additionally cite clause 4.1 by number."
    }
  ]
}

item_type is either "extraction" or "judgment". issue_number is an integer
matching the rubric. score is 0, 1, or 2. All fields are required.
"""

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(raw: str) -> str:
    """Strip common wrappers from a model response before Pydantic parsing.

    Handles ```json fences, prose preambles, XML wrappers, etc. by matching
    the outermost {...} block. Falls back to raw if no brace pair found.
    """
    match = _JSON_OBJECT_RE.search(raw)
    return match.group(0) if match else raw


def _build_user_message(
    nda_text: str, agent_output: str, rubric: str, playbook: str
) -> str:
    return (
        "# NDA\n"
        f"{nda_text}\n\n"
        "# AGENT OUTPUT\n"
        f"{agent_output}\n\n"
        "# RUBRIC\n"
        f"{rubric}\n\n"
        "# PLAYBOOK\n"
        f"{playbook}\n"
    )


def _retry_user_message(error: Exception) -> str:
    err_text = str(error)
    if len(err_text) > MAX_ERROR_CHARS:
        err_text = err_text[:MAX_ERROR_CHARS] + " …[truncated]"
    return (
        "Your previous response could not be parsed. Error:\n\n"
        f"{err_text}\n\n"
        "Return only valid JSON matching the schema. "
        "No preamble. No markdown code fences."
    )


def run_judge(
    nda_text: str, agent_output: str, rubric: str, playbook: str
) -> JudgeResult:
    """Score an agent's NDA review against the rubric.

    Retries up to MAX_RETRIES times on parse/validation failure, sending
    the error message back to the model between attempts (JUDG-02, P7).
    On retry exhaustion, logs the raw output + final error at ERROR and
    returns an empty JudgeResult (JUDG-05) — caller must check
    `if not result.scores:` to detect failure.

    Args:
        nda_text: Raw NDA markdown.
        agent_output: The agent's review (raw text from run_agent).
        rubric: Raw JSON string of data/rubric.json (D-08).
        playbook: Raw markdown playbook text.

    Returns:
        JudgeResult with populated scores, OR JudgeResult(scores=[]) on
        retry exhaustion.
    """
    client = get_client()
    user_content = _build_user_message(nda_text, agent_output, rubric, playbook)
    logger.info(
        "judge call: model=%s prompt_chars=%d num_ctx=%d",
        config.model,
        len(JUDGE_SYSTEM_PROMPT) + len(user_content),
        config.num_ctx,
    )

    messages: list[dict] = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    last_error: Exception | None = None
    raw: str = ""
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("judge attempt %d/%d", attempt, MAX_RETRIES)
        response = client.chat.completions.create(
            model=config.model,
            messages=messages,
            temperature=config.temperature,
            extra_body={"options": {"num_ctx": config.num_ctx}},  # D-04, P6
        )
        raw = response.choices[0].message.content or ""
        cleaned = _extract_json(raw)

        try:
            return JudgeResult.model_validate_json(cleaned)  # P12
        except ValidationError as err:
            last_error = err
            logger.warning(
                "judge parse failed (attempt %d): %s", attempt, err
            )
            if attempt < MAX_RETRIES:
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {"role": "user", "content": _retry_user_message(err)}
                )

    # JUDG-05: retries exhausted — log raw + error, return sentinel.
    logger.error(
        "judge exhausted %d retries; returning empty result. "
        "raw=%r last_error=%s",
        MAX_RETRIES,
        raw,
        last_error,
    )
    # TODO(P2, Phase 3): add reasoning-length content validator
    # TODO(P7, Phase 5): track validation_attempts in IterationResult
    return JudgeResult(scores=[])
```

## Validation Architecture

**workflow.nyquist_validation is `true` in .planning/config.json — this section is required.**

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest>=8.0` [ASSUMED version — verify at Wave 0] |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` OR new `pytest.ini` — **see Wave 0** |
| Quick run command | `uv run pytest tests/ -x -q -m "not integration"` |
| Full suite command | `uv run pytest tests/ -v` (integration tests skipped by default unless `-m integration` passed) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AGNT-01 | `run_agent` calls Ollama and returns a non-empty string | unit (FakeClient) | `uv run pytest tests/test_agent_run.py::test_run_agent_returns_content -x` | Wave 0 |
| AGNT-01 | `run_agent` against live Ollama produces non-empty output | integration (smoke) | `uv run pytest tests/test_smoke_ollama.py::test_agent_smoke -x -m integration` | Wave 0 |
| AGNT-02 | `ITERATION_ZERO_SYSTEM_PROMPT` contains no rubric/playbook vocabulary | unit | `uv run pytest tests/test_agent_prompt.py::test_no_banned_tokens -x` | Wave 0 |
| JUDG-01 | `run_judge` returns a validated `JudgeResult` on success | unit (FakeClient returns valid JSON) | `uv run pytest tests/test_judge_success.py::test_run_judge_success -x` | Wave 0 |
| JUDG-01 | `run_judge` against live Ollama produces a valid `JudgeResult` | integration (smoke) | `uv run pytest tests/test_smoke_ollama.py::test_judge_smoke -x -m integration` | Wave 0 |
| JUDG-02 | Retry loop recovers when first attempt returns invalid JSON | unit (FakeClient — seq: bad, good) | `uv run pytest tests/test_judge_retry.py::test_retry_recovers -x` | Wave 0 |
| JUDG-02 | Retry loop sends error details back to the model | unit (FakeClient — inspect `messages` arg on 2nd call) | `uv run pytest tests/test_judge_retry.py::test_retry_error_in_next_prompt -x` | Wave 0 |
| JUDG-03 | `_extract_json` strips ```` ```json ``` ``` fences | unit | `uv run pytest tests/test_judge_fences.py::test_extract_json_strips_fences -x` | Wave 0 |
| JUDG-03 | `_extract_json` returns raw when no braces present | unit | `uv run pytest tests/test_judge_fences.py::test_extract_json_no_braces_fallback -x` | Wave 0 |
| JUDG-04 | Every `chat.completions.create` call includes `extra_body={"options":{"num_ctx":...}}` | unit (FakeClient records kwargs) | `uv run pytest tests/test_llm_extra_body.py::test_num_ctx_passed -x` | Wave 0 |
| JUDG-05 | Retry exhaustion returns `JudgeResult(scores=[])` without raising | unit (FakeClient — seq: bad, bad, bad) | `uv run pytest tests/test_judge_graceful.py::test_returns_empty_on_exhaustion -x` | Wave 0 |
| JUDG-05 | Retry exhaustion logs raw output + final error at ERROR | unit (using `caplog`) | `uv run pytest tests/test_judge_graceful.py::test_logs_raw_on_exhaustion -x` | Wave 0 |
| CONF-02 (cross-cutting) | All calls use `temperature=config.temperature` (default 0.0) | unit (FakeClient records kwargs) | `uv run pytest tests/test_llm_extra_body.py::test_temperature_zero -x` | Wave 0 |

### Shared Fixture: FakeClient

```python
# tests/conftest.py
import json
import pytest


class _FakeChatCompletions:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[dict] = []  # inspect kwargs + messages per call

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self._responses.pop(0)

        # Minimal shape compatible with openai SDK ChatCompletion return.
        class _Msg: pass
        class _Choice: pass
        class _Resp: pass
        msg = _Msg(); msg.content = content
        choice = _Choice(); choice.message = msg
        resp = _Resp(); resp.choices = [choice]
        return resp


class FakeClient:
    def __init__(self, responses: list[str]):
        self.chat = type("C", (), {})()
        self.chat.completions = _FakeChatCompletions(responses)


@pytest.fixture
def fake_client(monkeypatch):
    """Factory: fake_client(['response1', 'response2']) patches get_client."""
    def _make(responses: list[str]) -> FakeClient:
        client = FakeClient(responses)
        # Patch the ONE module-level singleton to return our fake.
        import src.llm
        monkeypatch.setattr(src.llm, "_client", client)
        return client
    return _make


VALID_JUDGE_JSON = json.dumps({
    "scores": [
        {"item_id": "1a", "item_type": "extraction", "issue_number": 1,
         "score": 2, "evidence": "Clause 4.1 says seven years.",
         "reasoning": "Explicitly named.", "feedback": "Good."},
        # ... 7 more items for a realistic fixture ...
    ]
})
```

### Integration Test Shape

```python
# tests/test_smoke_ollama.py
import pytest
from pathlib import Path

pytestmark = pytest.mark.integration  # skipped unless -m integration

DATA = Path(__file__).parent.parent / "data"


def test_agent_smoke():
    from src.agent import run_agent, ITERATION_ZERO_SYSTEM_PROMPT
    nda = (DATA / "nda.md").read_text()
    result = run_agent(ITERATION_ZERO_SYSTEM_PROMPT, nda)
    assert result.strip(), "agent returned empty string"


def test_judge_smoke():
    from src.judge import run_judge
    nda = (DATA / "nda.md").read_text()
    agent_output = (DATA / "output_a.md").read_text()  # known-good review
    rubric = (DATA / "rubric.json").read_text()
    playbook = (DATA / "playbook.md").read_text()

    result = run_judge(nda, agent_output, rubric, playbook)

    # Smoke assertion only — Phase 3 does the real calibration.
    assert result.scores, "judge returned empty scores (parse failed?)"
    assert len(result.scores) >= 1
```

Register the marker to suppress warnings:
```toml
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "integration: marks tests that require live Ollama (select with -m integration)",
]
```

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q -m "not integration"` (sub-second; all unit tests)
- **Per wave merge:** same as per-task (integration not run in CI-like gate)
- **Phase gate:** `uv run pytest tests/ -v -m integration` executed once manually before `/gsd-verify-work`, with Ollama running and the configured model pulled

### Wave 0 Gaps
- [ ] `tests/__init__.py` (empty, makes `tests` a package)
- [ ] `tests/conftest.py` — `FakeClient` + `fake_client` fixture + `VALID_JUDGE_JSON` sample
- [ ] `tests/test_agent_run.py` — AGNT-01 unit
- [ ] `tests/test_agent_prompt.py` — AGNT-02 vocab scrub
- [ ] `tests/test_judge_success.py` — JUDG-01 happy path
- [ ] `tests/test_judge_retry.py` — JUDG-02 retry path (recover + retry-prompt-has-error)
- [ ] `tests/test_judge_fences.py` — JUDG-03 `_extract_json` cases
- [ ] `tests/test_llm_extra_body.py` — JUDG-04 + CONF-02 kwarg inspection
- [ ] `tests/test_judge_graceful.py` — JUDG-05 exhaustion + caplog
- [ ] `tests/test_smoke_ollama.py` — live Ollama round-trip (marked integration)
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` section adding `markers` and default `testpaths`
- [ ] Dev dep: `uv add --dev pytest`

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pydantic v1 `parse_raw` / `.dict()` | Pydantic v2 `model_validate_json` / `model_dump` | Pydantic 2.0 (2023) | P12 — use v2 methods only |
| `openai.ChatCompletion.create()` (legacy class method) | `OpenAI()` client + `client.chat.completions.create()` | openai 1.0 (late 2023) | STACK.md standard; what the skeleton uses |
| `response_format={"type":"json_object"}` universal | Varies by model, unreliable on Ollama | ongoing | P4 — skip it entirely |
| `client.beta.chat.completions.parse()` for structured output | Not reliably supported on Ollama OpenAI-compat endpoint | ongoing | P4 — don't use |

**Deprecated/outdated (do not use):**
- `instructor` library — wraps exactly what we want explicit [CITED: STACK.md]
- `langchain` / `llamaindex` — framework overhead, no benefit [CITED: STACK.md]
- `structlog` / `loguru` — stdlib logging sufficient [CITED: STACK.md]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `extra_body={"options": {"num_ctx": N}}` on `chat.completions.create` is the correct SDK path to Ollama options | Pitfalls P6, Code Skeletons | If wrong, `num_ctx` is silently ignored and long prompts truncate. Planner MUST verify at Wave 0 with a one-line smoke test against live Ollama, inspecting response and/or Ollama logs. Documented failure mode in P6. |
| A2 | `pytest>=8.0` is current and installable via `uv add --dev pytest` | Standard Stack, Validation Architecture | If wrong, version mismatch with Python 3.11 — trivial to fix at plan time by running `uv pip index versions pytest`. |
| A3 | Sentinel `JudgeResult(scores=[])` is the best graceful-failure shape for Phase 3 and Phase 5 consumers | Discretion Resolution #1 | If Phase 3 author prefers a dedicated wrapper type, the contract breaks. Mitigation: documented in `run_judge` docstring; Phase 3 plan can override by wrapping `run_judge` at the call site. |
| A4 | FakeClient monkey-patching `src.llm._client` is sufficient to redirect all calls | Validation Architecture | If `get_client()` is called BEFORE the fixture patches, a real `OpenAI` instance is cached. Mitigation: fixture patches BEFORE test function runs; skeleton ensures `_client` starts as `None`. Alternative: patch `src.llm.get_client` directly. |
| A5 | `ITERATION_ZERO_SYSTEM_PROMPT` copied verbatim from PRD §3.4 is already vocab-clean | Discretion Resolution #6, P8 mitigation | Low risk — the PRD text has been reviewed; the vocab test will catch any drift. |
| A6 | Pydantic v2 `model_validate_json` raises `ValidationError` for both JSON-decode and schema failures (single except clause sufficient) | P12 mitigation, Code Skeletons | Verified against Pydantic v2 docs; standard behaviour. If Phase 2 hits a surprise `JSONDecodeError`, add it to the except tuple. |

**User-confirmation-before-execution items:** A1 is the load-bearing one — plan should include a first-task Wave 0 item: "smoke `extra_body` path against live Ollama."

## Open Questions (RESOLVED)

All 7 recommendations below were adopted during planning. Plans 02-01..02-04 implement them directly. This section is retained for traceability.

1. **Wave 0 Ollama reachability check:** Should Phase 2 PLAN.md assume Ollama is already running with `qwen2.5:32b` pulled, or should Wave 0 include a `ollama serve` / `ollama pull qwen2.5:32b` step? Recommendation: add a Wave 0 "preflight" task that runs `curl -s http://localhost:11434/api/tags` and `ollama list` and aborts the phase with a clear message if either fails. Unit tests can still run without Ollama; only the integration smoke and the A1 verification need it.
**RESOLVED:** Adopted recommendation — implemented in Plan 02-01 Task 2 (Wave 0 preflight lives in `scripts/preflight.py`, invoked before integration runs).

2. **Rubric passing convention:** CONTEXT.md §Integration Points says "raw text (read from `data/rubric.json`) OR list of dicts — planner's choice". The skeleton I provided takes `rubric: str` (raw JSON text) for simplicity. If the planner wants `run_judge` to accept `list[dict]` instead and serialise internally, the signature changes but D-08 ("paste raw JSON verbatim") is satisfied either way. **Recommendation:** raw `str`. Caller does `Path("data/rubric.json").read_text()`. Zero ambiguity, and keeps `run_judge` pure.
**RESOLVED:** Adopted recommendation — implemented in Plan 02-03 Task 2 (`run_judge(nda_text, agent_output, rubric: str, playbook)` takes raw JSON string; caller passes `Path('data/rubric.json').read_text()`).

3. **Where does `fake_client` fixture go if the planner chooses not to use pytest?** Unlikely given Nyquist, but if the planner falls back to a `__main__` smoke, note that success criterion 3 ("deliberately malformed call demonstrates retry behaviour") becomes manual. **Strong recommendation:** keep pytest.
**RESOLVED:** Adopted recommendation — implemented in Plans 02-02 Task 2 and 02-03 Task 2 (pytest with FakeClient fixture; no `__main__` smoke).

4. **Test coverage for D-07 (heading collision):** should there be an explicit test that `_build_user_message` produces no `#`-prefixed content outside the four section headers? Or is that over-testing the obvious? **Recommendation:** skip the test. The header style is a constant string in the module; any accidental collision would need both (a) the constant changing AND (b) the review coincidentally containing matching text. Document in a comment, not a test.
**RESOLVED:** Adopted recommendation — implemented in Plan 02-03 Task 2. The `_build_user_message` docstring documents D-07; an explicit `test_build_user_message_uses_top_level_headings` test was added regardless as a cheap guard.

5. **Should `run_judge` log the character count of `agent_output` separately?** P6 says "log total character count of judge prompt at iteration 1". The skeleton logs the full total. If the planner wants finer breakdown (nda=X, agent=Y, rubric=Z, playbook=W) for Phase 3 diagnostics, that's a small addition. **Recommendation:** log the total only in Phase 2; add per-section breakdown in Phase 3 if needed.
**RESOLVED:** Adopted recommendation — implemented in Plan 02-03 Task 2. `run_judge` logs total `prompt_chars` only (`len(JUDGE_SYSTEM_PROMPT) + len(user_content)`); per-section breakdown deferred to Phase 3.

6. **Does `_client` singleton need a thread-safety guard?** Phase 2 is single-threaded per spec (no async, no parallelism). The `global _client` pattern is safe here. Document the single-threaded assumption in a module docstring.
**RESOLVED:** Adopted recommendation — implemented in Plan 02-01 Task 2. `get_client()` docstring in `src/llm.py` states the single-threaded assumption; no lock added.

7. **Pytest config location:** `pyproject.toml` vs separate `pytest.ini`. **Recommendation:** `pyproject.toml` `[tool.pytest.ini_options]` — keeps all project config in one file, consistent with `[tool.black]` already present.
**RESOLVED:** Adopted recommendation — implemented in Plan 02-01 Task 1. Pytest configuration lives in `pyproject.toml [tool.pytest.ini_options]` alongside `[tool.black]`.

## Sources

### Primary (HIGH confidence)
- `.planning/phases/02-agent-and-judge/02-CONTEXT.md` — locked decisions D-01..D-10, integration points, deferred items
- `.planning/research/STACK.md` — openai+Ollama client pattern, retry skeleton, "What NOT to Use" table, Pydantic v2 model patterns
- `.planning/research/PITFALLS.md` — P2, P4, P6, P7, P8, P12, P14 (the seven pitfalls pinned for this phase)
- `.planning/REQUIREMENTS.md` — AGNT-01/02, JUDG-01..05 acceptance criteria
- `prd.md §3.4, §3.5` — iteration-zero agent system prompt verbatim; judge input/output contract
- `src/config.py`, `src/models.py` — existing code surfaces to integrate with
- `data/rubric.json`, `data/playbook.md`, `data/nda.md` — fixture data used for smoke test
- `CLAUDE.md` — project-level constraints (Python, uv, Ollama, temp=0, black, Pydantic retry)

### Secondary (MEDIUM confidence)
- Pydantic v2 public docs (training-cached) for `model_validate_json` / `ValidationError` behaviour
- OpenAI Python SDK v2 public docs (training-cached) for `extra_body` kwarg on `chat.completions.create`

### Tertiary (LOW confidence)
- None. Every load-bearing claim in this research is either cited from an in-repo artifact or flagged in `## Assumptions Log`.

## Metadata

**Confidence breakdown:**
- Locked decisions (D-01..D-10): HIGH — copied verbatim from CONTEXT.md
- Pitfall mitigations (P2/P4/P6/P7/P8/P12/P14): HIGH — each cited with direct quote from PITFALLS.md
- Discretion resolutions: HIGH for #1, #2, #3, #4, #5, #6, #7 — reasoning documented; planner may override
- SDK field names (`extra_body`, `model_validate_json`): HIGH — stable public API; one assumption flagged (A1)
- Version pinning for pytest: MEDIUM — planner must verify exact version at plan time (A2)
- Validation architecture (pytest fixture shape): HIGH — standard pattern, trivially adaptable

**Research date:** 2026-04-11
**Valid until:** 2026-05-11 (30 days — Phase 2 stack is stable and pre-decided)

## RESEARCH COMPLETE
