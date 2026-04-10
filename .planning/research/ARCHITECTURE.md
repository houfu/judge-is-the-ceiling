# Architecture Patterns

**Domain:** LLM evaluation / auto-optimising agent experiment
**Researched:** 2026-04-11
**Confidence:** HIGH — architecture is fully specified in PRD and CLAUDE.md; this document maps it for roadmap use

---

## Recommended Architecture

This system follows a **closed-loop prompt optimisation** pattern: a fixed task (NDA review), evaluated by a fixed judge (rubric + playbook), with feedback fed to an optimiser that rewrites only the agent's system prompt. No agent SDK, no tools, no code generation — just iterative prompt mutation.

```
Static Inputs (data/)
    nda.md  rubric.json  playbook.md
        |         |           |
        v         v           v
    ┌───────────────────────────────┐
    │           loop.py             │  <-- orchestrator
    │  ┌──────────────────────────┐ │
    │  │ agent.py                 │ │  system_prompt + nda -> str
    │  └──────────┬───────────────┘ │
    │             │ agent_output     │
    │  ┌──────────v───────────────┐ │
    │  │ judge.py                 │ │  nda + output + rubric + playbook -> JudgeResult
    │  └──────────┬───────────────┘ │
    │             │ JudgeResult      │
    │  ┌──────────v───────────────┐ │
    │  │ log (inside loop.py)     │ │  IterationResult -> results/run_001.json
    │  └──────────┬───────────────┘ │
    │             │ feedback         │
    │  ┌──────────v───────────────┐ │
    │  │ optimiser.py             │ │  system_prompt + feedback -> new system_prompt
    │  └──────────────────────────┘ │
    └───────────────────────────────┘
         ^
         |
    pre_loop_test.py  (runs judge in isolation on output_a.md + output_b.md)
         |
    results/pre_loop_test.json
```

---

## Component Boundaries

| Component | File | Inputs | Outputs | Talks To |
|-----------|------|--------|---------|----------|
| Config | `src/config.py` | Env vars / defaults | Config values (model, base_url, temp, iterations) | All components import from here |
| Data models | `src/models.py` | — | Pydantic classes: `JudgeResult`, `IterationResult`, `ExperimentRun` | judge.py, loop.py, pre_loop_test.py |
| Agent | `src/agent.py` | system_prompt (str), nda_text (str) | agent_output (str) | OpenAI SDK (Ollama) |
| Judge | `src/judge.py` | nda_text, agent_output, rubric, playbook | `JudgeResult` (validated Pydantic) | OpenAI SDK (Ollama), models.py |
| Optimiser | `src/optimiser.py` | system_prompt (str), judge_result (`JudgeResult`) | new_system_prompt (str) | OpenAI SDK (Ollama) |
| Loop | `src/loop.py` | config, nda, rubric, playbook | `results/run_001.json` | agent.py, judge.py, optimiser.py, config.py, models.py |
| Pre-loop test | `src/pre_loop_test.py` | output_a.md, output_b.md, rubric, playbook | `results/pre_loop_test.json` | judge.py, config.py, models.py |
| Static data | `data/` | — | nda.md, rubric.json, playbook.md, output_a.md, output_b.md | loop.py, pre_loop_test.py |
| Results | `results/` | — | pre_loop_test.json, run_001.json, human_review.json | Downstream Streamlit app (out of scope) |

**Key boundary rule:** The optimiser does NOT receive the NDA. It receives the current system prompt plus `JudgeResult.feedback` strings only. This is deliberate and must be enforced at the call site in `loop.py`.

---

## Data Flow

### Static inputs → memory (at startup)

```
data/nda.md          → str  (nda_text)
data/rubric.json     → list[dict]  (rubric)
data/playbook.md     → str  (playbook)
```

### Loop iteration data flow

```
Iteration N start:
  system_prompt (str)         [mutates each iteration; initial value is hardcoded]
        |
        v
  agent.py → LLM call → agent_output (str)
        |
        v
  judge.py → LLM call (with retry) → JudgeResult (Pydantic)
        |
        ├──► loop.py: build IterationResult → append to results list
        |
        v
  optimiser.py → LLM call → new system_prompt (str)
        |
        v
  Iteration N+1
```

### At experiment completion

```
loop.py: ExperimentRun (Pydantic) → json.dumps → results/run_001.json
```

### Pre-loop test data flow (independent of loop)

```
data/output_a.md → str
data/output_b.md → str
        |
        v  (two sequential judge calls, same rubric + playbook)
pre_loop_test.py → judge.py → JudgeResult x2
        |
        v
results/pre_loop_test.json
```

---

## Patterns to Follow

### Pattern 1: Pydantic Retry on JSON Parse Failure

The judge LLM is instructed to return only valid JSON. On failure, the raw output and Pydantic validation error are sent back to the model with a correction prompt. Retry up to 3 times. After 3 failures, log the error and skip the iteration (do not crash the loop).

```python
for attempt in range(3):
    raw = call_llm(prompt)
    try:
        return JudgeResult.model_validate_json(raw)
    except ValidationError as e:
        prompt = correction_prompt(raw, str(e))
raise RuntimeError("Judge failed after 3 retries")
```

This pattern lives entirely inside `judge.py` — the loop sees only the validated `JudgeResult` or a raised exception.

### Pattern 2: Thin Function Signatures

Each component exposes exactly one function with a clear, typed signature:

```python
# agent.py
def run_agent(system_prompt: str, nda_text: str) -> str: ...

# judge.py
def run_judge(nda_text: str, agent_output: str, rubric: list, playbook: str) -> JudgeResult: ...

# optimiser.py
def run_optimiser(system_prompt: str, judge_result: JudgeResult) -> str: ...
```

`loop.py` imports these three functions and orchestrates them. No shared mutable state.

### Pattern 3: Config as a Singleton Module

`config.py` reads from environment variables at import time and exposes constants. All components import from it directly. No dependency injection, no config object passed around.

```python
# config.py
import os
MODEL = os.getenv("MODEL", "qwen2.5:32b")
BASE_URL = os.getenv("BASE_URL", "http://localhost:11434/v1")
TEMPERATURE = 0
NUM_ITERATIONS = int(os.getenv("NUM_ITERATIONS", "5"))
```

### Pattern 4: Write Results Atomically at End, Not Incrementally

The loop accumulates `IterationResult` objects in memory and writes the full `ExperimentRun` JSON once at the end. This avoids partial writes and keeps the output format clean. The tradeoff: a crash mid-run loses all results. For a 5-iteration local experiment this is acceptable.

### Pattern 5: Separate Pre-Loop Test as an Independent Entry Point

`pre_loop_test.py` is a standalone script, not imported by `loop.py`. It reuses `judge.py` and `models.py` but runs independently. This means the judge can be validated before the loop introduces confounding variables.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Passing the NDA to the Optimiser

**What:** Including `nda_text` in the optimiser's prompt.
**Why bad:** Breaks the deliberate design constraint (mirrors Harvey's approach; keeps context window smaller for local model). Also conflates the optimiser's role — it should work from failure analysis, not re-read the source.
**Instead:** Pass only `system_prompt` and the feedback strings extracted from `JudgeResult`.

### Anti-Pattern 2: Incrementally Appending to JSON Files

**What:** Writing partial results to `run_001.json` after each iteration.
**Why bad:** Produces malformed JSON mid-run; harder to produce a clean `ExperimentRun` structure; complicates the Streamlit reader.
**Instead:** Accumulate in memory, write once at the end. Add a simple try/finally in `loop.py` to write whatever was accumulated if the loop fails early.

### Anti-Pattern 3: Putting LLM Client Instantiation in Module-Level Code

**What:** Creating the `openai.OpenAI(base_url=..., api_key=...)` client at import time in each component.
**Why bad:** Any import triggers an attempted client construction; hard to test; duplicates client config.
**Instead:** Create the client once in a shared location (a helper in `config.py` or a `get_client()` function) and import it.

### Anti-Pattern 4: Embedding Rubric Logic in Component Code

**What:** Hardcoding item IDs, extraction vs. judgment logic, score calculation inside `judge.py` or `loop.py`.
**Why bad:** The rubric is the experiment's core variable; it should live in `data/rubric.json` and be read at runtime. Hardcoding makes the experiment harder to re-run with a different rubric.
**Instead:** Rubric items drive scoring. The `JudgeResult` model mirrors rubric item structure. Scores are computed from `JudgeResult`, not from hardcoded IDs.

---

## Scalability Considerations

This is a contained experiment, not a production system. These concerns apply at the relevant scale:

| Concern | At 5 iterations (target) | At 20+ iterations | If multi-model |
|---------|--------------------------|-------------------|----------------|
| Context window | ~10-page NDA + rubric + playbook fits comfortably in most 32B models | Monitor judge prompt length; accumulated feedback can bloat optimiser context | Each model needs its own client config |
| Result storage | Single JSON file, trivially small | Still fine as JSON; Streamlit reads entire file | Separate run files per model |
| Retry failures | Rare at temperature 0; retry budget of 3 is sufficient | Same | Same |
| Runtime | 5 iterations × 3 LLM calls × local inference ≈ 5–15 minutes | Linear scaling; acceptable locally | Parallel calls possible but adds complexity |

---

## Build Order (with dependencies)

The build order below reflects hard dependencies: a component cannot be built until its dependencies exist.

```
Layer 0 — Static data (no code dependencies)
  └── data/nda.md, rubric.json, playbook.md, output_a.md, output_b.md

Layer 1 — Foundation (no inter-module dependencies)
  ├── src/models.py        (Pydantic models; depends only on pydantic)
  └── src/config.py        (constants; depends only on os/env)

Layer 2 — LLM components (depend on models.py + config.py)
  ├── src/agent.py         (depends on config.py, openai SDK)
  └── src/judge.py         (depends on config.py, models.py, openai SDK)

Layer 3 — Verification gate (depends on judge.py, models.py, data/)
  └── src/pre_loop_test.py  ← RUN AND EVALUATE BEFORE PROCEEDING

Layer 4 — Optimiser (depends on config.py, models.py; builds on judge output)
  └── src/optimiser.py

Layer 5 — Orchestrator (depends on all of layers 1–4)
  └── src/loop.py
```

**Critical gate at Layer 3:** The PRD specifies a decision point after the pre-loop test — if the judge cannot reliably distinguish the good review (Output A) from the flawed review (Output B) on judgment items, the thesis should be reconsidered before the loop is built. The build order enforces this: `pre_loop_test.py` is built and run before `optimiser.py` and `loop.py`.

---

## Error Handling Patterns

| Site | Error | Handling |
|------|-------|----------|
| `judge.py` | LLM returns malformed JSON | Retry up to 3 times with error fed back to model; raise after 3 failures |
| `judge.py` | Pydantic validation failure | Same retry loop; error message included in correction prompt |
| `loop.py` | Judge raises after retries | Log the failure, decide: skip iteration or abort run |
| `loop.py` | Unexpected exception mid-loop | try/finally: write accumulated results before propagating |
| `agent.py` / `optimiser.py` | LLM call fails | Let exception propagate to `loop.py`; these are not retried (no structured output requirement) |

---

## Sources

- PRD (`prd.md`) — specifies component signatures, data models, sequence of work, and all design decisions. HIGH confidence.
- CLAUDE.md — confirms architecture, data flow, and file structure. HIGH confidence.
- General LLM eval / prompt-optimisation system patterns (DSPy, Harvey-style loops) — training data, MEDIUM confidence. No specific library verification attempted; this system does not use DSPy or any eval framework.
