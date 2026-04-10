# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An experiment testing whether an LLM judge can distinguish extraction tasks (finding information) from judgment tasks (assessing significance) in NDA review. Runs an auto-optimising agent loop: an agent reviews an NDA, a judge scores the output against a rubric, an optimiser rewrites the agent's system prompt based on feedback, and the loop repeats. All artifacts are written to JSON files consumed by a separate Streamlit app.

## Tech Stack

- **Language:** Python, managed with `uv`
- **LLM SDK:** `openai` Python SDK with configurable `base_url` (OpenAI-compatible API for Ollama)
- **LLM runtime:** Ollama (local), same model for agent/judge/optimiser, temperature 0
- **Validation:** Pydantic for JSON parsing with retry (up to 3 retries on validation failure)
- **Formatting:** Black
- **Dependencies:** `openai`, `pydantic`

## Common Commands

```bash
uv run python src/loop.py          # Run the main optimisation loop
uv run python src/pre_loop_test.py # Run pre-loop judge calibration test
uv run streamlit run streamlit_app/ # Run the Streamlit dashboard
```

## Architecture

The system has three LLM-calling components chained in a loop:

1. **Agent** (`src/agent.py`): Takes a system prompt + NDA text, returns a structured NDA review
2. **Judge** (`src/judge.py`): Takes NDA + agent output + rubric + playbook, returns per-item scores as validated JSON (Pydantic models)
3. **Optimiser** (`src/optimiser.py`): Takes current system prompt + judge feedback (not the NDA), rewrites the system prompt

The loop (`src/loop.py`) runs: agent -> judge -> log -> optimiser -> repeat for N iterations.

**Pre-loop test** (`src/pre_loop_test.py`): Runs two pre-written reviews (Output A = correct, Output B = flawed) through the judge to calibrate whether it can distinguish quality before the loop adds confounding variables.

## Key Design Decisions

- The optimiser deliberately does not receive the NDA — it works from judge feedback only (mirrors Harvey's approach where the coding agent works from failure analysis)
- The playbook is precise for extraction items but deliberately vague for judgment items — this is the design choice that produces the predicted failure mode
- No agent SDK or tool use — prompt rewriting only
- All components use the same model instance via OpenAI-compatible API

## Data Flow

- **Static inputs** in `data/`: NDA (`nda.md`), rubric (`rubric.json`), playbook (`playbook.md`), pre-written reviews (`output_a.md`, `output_b.md`)
- **Pydantic models** in `src/models.py`: `JudgeResult`, `IterationResult`, `ExperimentRun`
- **Config** in `src/config.py`: model name, base URL, temperature, iteration count (from env vars or defaults)
- **Results** in `results/`: JSON files (`pre_loop_test.json`, `run_001.json`, `human_review.json`)

## Rubric Structure

8 items across 4 NDA issues, each with an extraction (a) and judgment (b) variant. Scoring: 0 (not addressed), 1 (partially addressed), 2 (fully addressed). Results track `total_score`, `extraction_score`, and `judgment_score` separately — the thesis predicts extraction scores converge while judgment scores plateau.

<!-- GSD:project-start source:PROJECT.md -->
## Project

**Judge Is The Ceiling**

An experiment that runs an auto-optimising agent loop on an NDA review task to test whether an LLM judge can reliably distinguish extraction (finding information) from judgment (assessing significance). The loop captures all artifacts — prompts, outputs, scores, reasoning, feedback — as structured JSON for analysis.

**Core Value:** Produce a clean experiment run that demonstrates whether the optimisation loop converges on extraction scores while plateauing on judgment scores, validating the thesis that the judge's ceiling is the playbook author's foresight.

### Constraints

- **Runtime**: Ollama (local) — no API costs, reproducible
- **SDK**: OpenAI Python SDK with configurable base_url — works with any OpenAI-compatible endpoint
- **Environment**: uv for Python project management
- **Code style**: Black
- **Temperature**: 0 for all calls — reproducibility
- **JSON parsing**: Pydantic validation with retry (up to 3 attempts)
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
- Python 3.11+ — best Pydantic v2 performance, full type annotation support
- uv 0.7.x — `uv sync` + `uv run python src/loop.py`, no venv activation
- `openai>=2.0` (current: 2.31.0) — OpenAI Python SDK with `base_url` for Ollama
- `pydantic>=2.0` (current: 2.12.5) — structured output validation with retry
- `black>=26.0` (current: 26.3.1) — formatting
## Key Patterns
### Ollama Client Configuration
### Pydantic v2 Models
### Retry Pattern (3 attempts)
### Config Pattern (stdlib only)
### pyproject.toml
## What NOT to Use
| Library | Reason to Skip |
|---------|---------------|
| `instructor` | Wraps exactly the retry loop this project should write explicitly. Adds opacity. |
| `langchain` / `llamaindex` | Framework overhead for 3 serial LLM calls. Obscures loop logic. |
| Any agent SDK (AutoGen, CrewAI) | PRD explicitly rules this out. Prompt rewriting only. |
| `pydantic-settings` + `python-dotenv` | 5 config values don't warrant a dependency. |
| `openai.beta.chat.completions.parse` | Structured output endpoint; Ollama model support varies. |
| `asyncio` / async client | Sequential loop, no parallelism needed. Sync is simpler. |
| `structlog` / `loguru` | Output is JSON files. stdlib logging at INFO is sufficient. |
| `response_format={"type": "json_object"}` | Ollama support varies by model. Prompt instruction + Pydantic retry is more reliable. |
## Confidence Assessment
| Area | Level | Reason |
|------|-------|--------|
| Package versions | HIGH | Pulled live from PyPI JSON API (2026-04-11) |
| Ollama `base_url` pattern | HIGH | Stable SDK feature since v1; `api_key="ollama"` is community standard |
| Pydantic v2 model patterns | HIGH | Well-documented v2 API, `model_validate` is canonical |
| Retry loop pattern | HIGH | Standard Python, no external dependencies |
| `response_format` avoidance | MEDIUM | Ollama support varies by model — conservative to avoid |
| Config via `os.getenv` | HIGH | Stdlib, no ambiguity |
## Roadmap Implications
- Foundation layer (config + models) must come first — everything imports from them
- Only 2 runtime dependencies: `openai` and `pydantic`
- No framework overhead — loop logic IS the experiment
- Sync client sufficient — no async complexity needed
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
