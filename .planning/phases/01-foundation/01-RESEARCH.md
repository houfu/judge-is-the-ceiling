# Phase 1: Foundation - Research

**Researched:** 2026-04-11
**Domain:** Python project setup (uv), Pydantic v2 data models, config module, static content authoring
**Confidence:** HIGH

## Summary

Phase 1 is a greenfield foundation phase with no LLM calls. It delivers five things: the uv project skeleton, the Pydantic data models that every later phase imports, the config module, the five static data files (NDA, rubric, playbook, Output A, Output B), and the results/ gitignore entry. Nothing in this phase makes network calls or runs experiments.

The stack is fully pre-decided by prior research (STACK.md) and confirmed against live PyPI. All three runtime dependencies (openai, pydantic, black) are at versions matching the project's pinned specs. The Pydantic model shapes and JSON structures are specified exactly in PRD section 5 — planner should treat those shapes as authoritative, not invent alternatives. The NDA content decisions (length, governing law, issue placement, clause numbering style) are locked in CONTEXT.md decisions D-01 through D-06.

The primary authoring risk in this phase is content quality and internal consistency of the five data files. Code is trivial; content is not. The rubric, playbook, Output A, and Output B must interlock correctly: rubric items map to NDA clauses, playbook scoring guidance maps to rubric items, Output A demonstrates correct detection of all four issues, and Output B deliberately fails on the two judgment items while passing extraction. Misalignment here will corrupt every phase that follows.

**Primary recommendation:** Write code files first (pyproject.toml, models.py, config.py), then author data files in dependency order: NDA first, rubric second (maps to NDA clauses), playbook third (maps to rubric items), Output A fourth (demonstrates all four issues), Output B last (deliberately partial).

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** NDA length ~1500 words (medium). Enough for issues to feel natural among standard clauses while staying within context window headroom for local Ollama models.
- **D-02:** Issues are lightly hidden — standard clause headings, detectable by careful reading. Tests whether the agent reads thoroughly, not whether it can decode obfuscation.
- **D-03:** Numbered sections format (1. Definitions, 2. Obligations, etc.) — standard commercial NDA style. Prevents model hallucination of clause numbers.
- **D-04:** Governing law is Singapore. NDA content uses generic commercial language but governing law clause references Singapore.
- **D-05:** Neutral review perspective — agent identifies issues for either side, no stated party perspective.
- **D-06:** Boilerplate-realistic standard clauses — entire agreement, severability, notices, assignment, waiver. The NDA should feel like a real agreement so the 4 embedded issues don't stand out structurally.
- **D-07:** Playbook is minimally vague for judgment items — gives general direction but lacks specifics. E.g., "Score 2 if the agent provides a substantive assessment of the practical effect." Not maximally vague and not artificially imprecise.
- **D-08:** Partial credit (score=1) for judgment items is deliberately fuzzy — mirrors the judgment vagueness in the playbook. The 0/1/2 boundary for judgment items should be harder for the judge to apply than for extraction items.
- **D-09:** Rubric JSON is minimal: item_id, item_type (extraction/judgment), issue_number, question, max_score. Scoring guidance lives in the playbook only, not duplicated in rubric.json.

### Claude's Discretion

- Data model schema design (Pydantic field names, nesting, aggregation logic)
- Sample review content (Output A and Output B) — Claude drafts, author edits for legal accuracy
- Config module structure (dataclass vs dict, env var naming)
- Project layout (src/ package structure, __init__.py files)

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.

</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SETP-01 | uv project with openai and pydantic dependencies, black for formatting | pyproject.toml template verified in STACK.md; all versions confirmed against PyPI 2026-04-11 |
| SETP-02 | results/ directory gitignored | Trivial — add `results/` line to .gitignore; referenced in Pitfalls P15 |
| CONF-01 | Configurable model name, base URL, API key, temperature, iteration count via env vars with defaults | Config dataclass pattern verified in STACK.md; uses stdlib os.getenv only |
| CONF-02 | Temperature enforced at 0 for all LLM calls | Default baked into Config dataclass; no dependency needed |
| MODL-01 | Pydantic models for RubricScore, JudgeResult, IterationResult, ExperimentRun | Exact field names derivable from PRD section 5 JSON shapes; Pydantic v2 patterns verified in STACK.md |
| MODL-02 | Category-level score aggregation (extraction_score, judgment_score) computed at write time | Computed fields on IterationResult; use @property or Pydantic @computed_field |
| DATA-01 | Synthetic NDA in markdown with 4 embedded issues (2 extraction, 2 judgment), numbered clauses | NDA issue table from PRD section 3.1; content decisions locked in D-01 to D-06 |
| DATA-02 | 8-item rubric JSON with metadata (item_id, type, issue_number, question, max_score) | Rubric items table from PRD section 3.2; schema from D-09 |
| DATA-03 | Playbook with precise extraction descriptions and deliberately vague judgment descriptions | Playbook pattern from PRD section 3.3; calibration decisions D-07 and D-08 |
| DATA-04 | Output A — model NDA review correctly identifying all 4 issues including judgment calls | Must score 2/2 on all 8 rubric items when run through judge |
| DATA-05 | Output B — plausible-but-flawed review that nails extraction but misses judgment | Must score 2/2 on extraction items (1a, 2a, 3a, 4a) and 0 or 1 on judgment items (1b, 2b, 3b, 4b) |

</phase_requirements>

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11+ | Runtime | Best Pydantic v2 performance, full type annotations |
| uv | 0.7.x (0.7.17 on this machine) | Package/env management | Project standard; `uv sync` + `uv run` workflow |
| pydantic | 2.12.5 | Data model validation, JSON serialisation | Locked decision; validates structured judge output |
| openai | 2.31.0 | LLM API client | OpenAI-compatible SDK; works with Ollama via `base_url` |
| black | 26.3.1 | Code formatting | Project standard; dev dependency only |

[VERIFIED: PyPI JSON API 2026-04-11]

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| stdlib: os, dataclasses, json, typing | — | Config, JSON I/O, type hints | No external dependencies for these; use stdlib |

### Alternatives Considered (and rejected)

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `os.getenv` Config dataclass | `pydantic-settings` + `python-dotenv` | 5 config values do not warrant a dependency — stdlib is sufficient |
| Custom retry loop | `instructor` | Adds opacity; retry logic should be explicit for this experiment |
| Sync openai client | `asyncio` async client | Sequential loop; no parallelism needed; sync is simpler |

**Installation:**
```bash
uv init judge-is-the-ceiling
uv add openai pydantic
uv add --dev black
```

**Version verification:** [VERIFIED: npm registry equivalent — PyPI JSON API]
- pydantic: 2.12.5 (verified 2026-04-11)
- openai: 2.31.0 (verified 2026-04-11)
- black: 26.3.1 (verified 2026-04-11)
- uv: 0.7.17 (verified on this machine via `uv --version`)

---

## Architecture Patterns

### Recommended Project Structure

```
judge-is-the-ceiling/
├── pyproject.toml          # uv project config + black settings
├── .gitignore              # MUST include results/
├── data/
│   ├── nda.md              # ~1500 word synthetic NDA with 4 issues
│   ├── rubric.json         # 8 items: item_id, item_type, issue_number, question, max_score
│   ├── playbook.md         # Judge scoring guidance per rubric item
│   ├── output_a.md         # Model NDA review (all 4 issues correct)
│   └── output_b.md         # Flawed review (extraction correct, judgment missed)
├── src/
│   ├── __init__.py
│   ├── models.py           # RubricScore, JudgeResult, IterationResult, ExperimentRun
│   └── config.py           # Config dataclass with os.getenv defaults
└── results/                # Gitignored; written at runtime
```

[ASSUMED] The `src/` package uses a flat structure with `__init__.py`. This is conventional but not mandated by any locked decision — planner has discretion here.

### Pattern 1: Pydantic v2 Model Hierarchy

**What:** Four models form a strict hierarchy: RubricScore (leaf) -> JudgeResult (collection of scores) -> IterationResult (adds prompt, agent output, aggregates) -> ExperimentRun (envelope with metadata and all iterations).

**When to use:** This exact hierarchy — PRD section 5 JSON shapes define it. Do not flatten or restructure.

```python
# Source: STACK.md + PRD section 5

from pydantic import BaseModel, computed_field
from typing import Literal

class RubricScore(BaseModel):
    item_id: str                              # e.g. "1a", "3b"
    item_type: Literal["extraction", "judgment"]
    issue_number: int
    score: Literal[0, 1, 2]
    evidence: str
    reasoning: str
    feedback: str

class JudgeResult(BaseModel):
    scores: list[RubricScore]

class IterationResult(BaseModel):
    iteration: int
    system_prompt: str
    agent_output: str
    scores: list[RubricScore]
    total_score: int
    extraction_score: int
    judgment_score: int

class ExperimentRun(BaseModel):
    experiment_id: str
    timestamp: str
    config: dict
    nda_file: str
    rubric_file: str
    playbook_file: str
    pre_loop_test: dict | None = None
    iterations: list[IterationResult] = []
```

**Score aggregation (MODL-02):** `extraction_score` and `judgment_score` must be computed from the `scores` list. This can be done as a regular method called at write time, or as Pydantic `@computed_field` (Pydantic v2.0+). Either approach is acceptable under Claude's Discretion.

[VERIFIED: STACK.md for Pydantic v2 patterns; PRD section 5 for field names]

### Pattern 2: Config Dataclass (stdlib only)

**What:** Single `Config` dataclass instantiated once at module level. No external config library.

```python
# Source: STACK.md
import os
from dataclasses import dataclass

@dataclass
class Config:
    model: str = os.getenv("MODEL", "qwen2.5:32b")
    base_url: str = os.getenv("BASE_URL", "http://localhost:11434/v1")
    api_key: str = os.getenv("API_KEY", "ollama")
    temperature: float = float(os.getenv("TEMPERATURE", "0"))
    num_iterations: int = int(os.getenv("NUM_ITERATIONS", "5"))

config = Config()
```

Note: `temperature` defaults to `0` (CONF-02 hardcodes it). Env var override exists but the documented default enforces the requirement.

[VERIFIED: STACK.md]

### Pattern 3: pyproject.toml Structure

```toml
[project]
name = "judge-is-the-ceiling"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "openai>=2.0",
    "pydantic>=2.0",
]

[tool.black]
line-length = 88
target-version = ["py311"]

[tool.uv]
dev-dependencies = [
    "black>=26.0",
]
```

[VERIFIED: STACK.md template; versions confirmed against PyPI]

### Pattern 4: rubric.json Schema

Per D-09: scoring guidance does NOT go in rubric.json — it lives in playbook.md only.

```json
[
  {
    "item_id": "1a",
    "item_type": "extraction",
    "issue_number": 1,
    "question": "Did the review identify the 7-year confidentiality period?",
    "max_score": 2
  },
  {
    "item_id": "1b",
    "item_type": "judgment",
    "issue_number": 1,
    "question": "Did the review flag the 7-year duration as unusual relative to market norms?",
    "max_score": 2
  }
  // ... 6 more items (2a, 2b, 3a, 3b, 4a, 4b)
]
```

Total: 8 items, 4 issues x 2 types (extraction/judgment). [VERIFIED: PRD section 3.2]

### Anti-Patterns to Avoid

- **Putting scoring guidance in rubric.json:** D-09 explicitly prohibits this. Guidance lives in playbook.md only.
- **HumanReview Pydantic model in models.py:** HumanReview is a manual post-experiment artifact (Phase 5+). Do not create a Pydantic model for it in this phase — it's not needed and not in scope.
- **Importing openai in models.py or config.py:** These modules must have zero LLM dependencies. They are pure data/config.
- **Skipping `__init__.py`:** `uv run python -c "from src.models import ExperimentRun"` (success criterion 1) requires `src/` to be a proper package.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON validation | Custom dict parsing | Pydantic `model_validate` | Edge cases in type coercion, Literal enforcement |
| Field type enforcement | `if score not in [0,1,2]` | Pydantic `Literal[0, 1, 2]` | Pydantic handles at parse time with clear errors |
| Model serialisation | `json.dumps(obj.__dict__)` | `model.model_dump()` | Handles nested models, datetime, custom types |
| Score aggregation ad-hoc | Summing in loop.py | Computed at model level | Keeps aggregation co-located with data definition |

**Key insight:** Pydantic v2's `model_validate` and `model_dump` handle the full serialisation round-trip. Don't duplicate this logic in loop code.

---

## Common Pitfalls

### Pitfall 1: rubric.json Has More or Fewer Than 8 Items (P13 adjacent)

**What goes wrong:** Success criterion 4 requires "rubric has 8 items." A typo or miscount produces a valid JSON file that fails verification silently.
**Why it happens:** Writing rubric items without systematically accounting for all 4 issues x 2 types.
**How to avoid:** Write rubric items in order: 1a, 1b, 2a, 2b, 3a, 3b, 4a, 4b. Count explicitly before finalising.
**Warning signs:** `len(rubric_items) != 8` when loaded in Python.

### Pitfall 2: NDA Clause Numbers Are Missing or Inconsistent (P13)

**What goes wrong:** Local models hallucinate clause references when NDA lacks explicit numbering. Judge output references non-existent clause numbers.
**Why it happens:** Markdown formatting without explicit section numbers (e.g., "## Remedies" not "## 7. Remedies").
**How to avoid:** Every section must have a numeric prefix: "1. Definitions", "2. Confidential Information", etc. D-03 locks this.
**Warning signs:** Section heading without leading number.

### Pitfall 3: Output B Accidentally Fails Extraction Items

**What goes wrong:** Output B is supposed to nail extraction but miss judgment. If it also misses extraction, the pre-loop judge test loses its diagnostic value.
**Why it happens:** Drafting Output B without explicitly cross-checking it item-by-item against extraction rubric items (1a, 2a, 3a, 4a).
**How to avoid:** After drafting Output B, verify each extraction item is explicitly addressed. The non-solicitation clause and independently-developed-information exception must be found and described — just without the judgment call.
**Warning signs:** Output B scoring < 2 on any (a) item during pre-loop test.

### Pitfall 4: Pydantic v1 API Used Accidentally (P12)

**What goes wrong:** Code that imports from v1 API (`.dict()`, `.parse_obj()`, `@validator`) breaks on Pydantic v2.
**Why it happens:** Training data and documentation mixed v1/v2 examples.
**How to avoid:** Use v2 only: `model_validate()`, `model_dump()`, `model_validate_json()`, `@field_validator`.
**Warning signs:** `DeprecationWarning: The `dict` method is deprecated` or `AttributeError` on validation calls.

### Pitfall 5: results/ Not Gitignored Before Phase 2

**What goes wrong:** Experiment output (potentially containing long LLM outputs) committed to git accidentally. (P15)
**Why it happens:** Creating the directory but forgetting .gitignore.
**How to avoid:** Add `results/` to .gitignore as part of SETP-02, and create an empty `results/.gitkeep` so the directory exists but is not tracked.

### Pitfall 6: Governing Law Clause Inconsistent with NDA Content

**What goes wrong:** D-04 sets governing law to Singapore but the substantive NDA clauses use non-Singapore-specific terms that contradict Singapore law. Judge model may flag internal inconsistency.
**Why it happens:** Copying boilerplate from a US NDA template without updating the governing law clause.
**How to avoid:** NDA body uses generic commercial language; only the governing law / dispute resolution clause names Singapore. No other Singapore-specific provisions needed.

### Pitfall 7: Config `float(os.getenv("TEMPERATURE", "0"))` Fails on Non-Numeric Env Var

**What goes wrong:** If `TEMPERATURE` is set to an invalid string in the environment, the dataclass instantiation crashes at import time with an uninformative `ValueError`.
**Why it happens:** `float()` on a non-numeric string raises immediately.
**How to avoid:** This is acceptable behaviour for a single-researcher experiment — document it. Alternatively, wrap in a try/except with a clear error message. No need for a full validation library.

---

## Code Examples

### models.py — Verified Pydantic v2 Pattern

```python
# Source: STACK.md (Pydantic v2 patterns)
from pydantic import BaseModel
from typing import Literal

class RubricScore(BaseModel):
    item_id: str
    item_type: Literal["extraction", "judgment"]
    issue_number: int
    score: Literal[0, 1, 2]
    evidence: str
    reasoning: str
    feedback: str

class JudgeResult(BaseModel):
    scores: list[RubricScore]
```

### Aggregation — Compute at Write Time

```python
# MODL-02: extraction_score and judgment_score computed from scores list
def compute_scores(scores: list[RubricScore]) -> tuple[int, int]:
    extraction = sum(s.score for s in scores if s.item_type == "extraction")
    judgment = sum(s.score for s in scores if s.item_type == "judgment")
    return extraction, judgment
```

### Loading rubric.json

```python
import json
from pathlib import Path

def load_rubric(path: str = "data/rubric.json") -> list[dict]:
    with open(path) as f:
        return json.load(f)
```

### .gitignore Entry (P15 prevention)

```
results/
```

---

## NDA Content Specification

The NDA must embed exactly these 4 issues (from PRD section 3.1):

| # | Issue | Category | What's Wrong |
|---|-------|----------|-------------|
| 1 | Confidentiality period | Extraction | 7-year term (market standard 2–3 years) |
| 2 | Definition scope | Extraction | Overbroad — captures all information relating to business, operations, customers, technology, strategy |
| 3 | Non-solicitation in remedies | Judgment | 24-month employee non-solicitation buried in remedies section |
| 4 | Gutted carve-out | Judgment | Independently-developed-information exception modified with requirements so onerous it's functionally unusable |

**NDA structural requirements (locked decisions):**
- ~1500 words total (D-01)
- Numbered sections: "1. Definitions", "2. ...", etc. (D-03)
- Governing law: Singapore (D-04); all other content uses generic commercial language (D-06)
- Issues are present but not structurally prominent — standard clause headings (D-02)
- Boilerplate sections required: entire agreement, severability, notices, assignment, waiver (D-06)

**Playbook calibration (locked decisions):**
- Extraction items: precise 0/1/2 descriptions (e.g., "Score 0 if period not mentioned. Score 1 if duration mentioned but not specific 7-year term. Score 2 if 7-year term explicitly identified.") (D-07)
- Judgment items: minimally vague 0/1/2 descriptions (D-07, D-08)

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pydantic v1 `.dict()`, `.parse_obj()` | Pydantic v2 `.model_dump()`, `.model_validate()` | Pydantic 2.0 (2023) | v1 API deprecated; use v2 only |
| `uv pip install` | `uv add` / `uv sync` | uv 0.2+ | `uv add` updates pyproject.toml; `uv pip` bypasses it |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `src/` uses flat package structure with `__init__.py` | Architecture Patterns | Wrong structure breaks `from src.models import ExperimentRun` (success criterion 1) |
| A2 | `ExperimentRun.pre_loop_test` should accept `dict \| None` initially | Code Examples | If it needs a typed model, will require refactor in later phase |
| A3 | Score aggregation via helper function (not `@computed_field`) is acceptable for MODL-02 | Code Examples | If planner prefers `@computed_field`, implementation detail changes but not interface |

---

## Open Questions

1. **`ExperimentRun.config` shape — typed or dict?**
   - What we know: PRD section 5 shows `"config": {"model": ..., "base_url": ..., ...}` as a nested object
   - What's unclear: Whether `config` should be a typed `Config`-derived dict or a raw `dict` in the Pydantic model
   - Recommendation: Use `dict` for now; Config dataclass is for runtime, not serialisation. Avoids circular import between models.py and config.py.

2. **`results/.gitkeep` vs empty directory**
   - What we know: `results/` must exist and be gitignored; git does not track empty directories
   - What's unclear: Whether to create `results/.gitkeep` to ensure the directory exists in checkout
   - Recommendation: Add `results/.gitkeep` with a `results/*` + `!results/.gitkeep` gitignore pattern, or simply document that `mkdir results/` is needed before first run.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | SETP-01 (project setup) | Yes | 0.7.17 | — |
| Python 3.11+ | SETP-01 (runtime) | Yes (3.13.5) | 3.13.5 | — |
| PyPI (network) | SETP-01 (uv sync) | Assumed yes | — | Use `--offline` if cached |

[VERIFIED: `uv --version` and `python3 --version` on this machine 2026-04-11]

Note: Python 3.13.5 exceeds the `>=3.11` requirement. No compatibility concern — Pydantic v2 and openai v2 both support 3.13.

**Missing dependencies with no fallback:** None. All required tools are present.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | None — no test framework installed yet |
| Config file | None — Wave 0 gap |
| Quick run command | `uv run python -c "from src.models import ExperimentRun"` (success criterion 1) |
| Full suite command | Manual verification against all 5 success criteria |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SETP-01 | `uv sync` installs without errors | smoke | `uv sync && echo OK` | No pyproject.toml yet — Wave 0 |
| SETP-02 | results/ is gitignored | manual | `grep "results/" .gitignore` | No .gitignore yet — Wave 0 |
| CONF-01 | Config reads from env vars with defaults | smoke | `uv run python -c "from src.config import config; print(config.model)"` | No config.py yet — Wave 0 |
| CONF-02 | Temperature defaults to 0 | smoke | `uv run python -c "from src.config import config; assert config.temperature == 0"` | No config.py yet — Wave 0 |
| MODL-01 | All 4 model classes instantiate | smoke | `uv run python -c "from src.models import ExperimentRun"` | No models.py yet — Wave 0 |
| MODL-02 | Aggregation produces correct scores | smoke | Script instantiating models with known scores and asserting aggregates | No models.py yet — Wave 0 |
| DATA-01 | data/nda.md exists with numbered clauses | manual | `python3 -c "import re; t=open('data/nda.md').read(); assert re.search(r'^\d+\.', t, re.M)"` | No data/ yet — Wave 0 |
| DATA-02 | data/rubric.json has exactly 8 items | smoke | `python3 -c "import json; r=json.load(open('data/rubric.json')); assert len(r)==8"` | No data/ yet — Wave 0 |
| DATA-03 | data/playbook.md exists | manual | `test -f data/playbook.md && echo OK` | No data/ yet — Wave 0 |
| DATA-04 | data/output_a.md exists | manual | `test -f data/output_a.md && echo OK` | No data/ yet — Wave 0 |
| DATA-05 | data/output_b.md exists | manual | `test -f data/output_b.md && echo OK` | No data/ yet — Wave 0 |

### Sampling Rate

- **Per task commit:** Run smoke command for that task's primary deliverable
- **Per wave merge:** Run full set of smoke commands above
- **Phase gate:** All 5 success criteria verified manually before advancing to Phase 2

### Wave 0 Gaps

- [ ] `pyproject.toml` — covers SETP-01
- [ ] `.gitignore` — covers SETP-02
- [ ] `src/__init__.py` — required for package import
- [ ] `src/models.py` — covers MODL-01, MODL-02
- [ ] `src/config.py` — covers CONF-01, CONF-02
- [ ] `data/nda.md` — covers DATA-01
- [ ] `data/rubric.json` — covers DATA-02
- [ ] `data/playbook.md` — covers DATA-03
- [ ] `data/output_a.md` — covers DATA-04
- [ ] `data/output_b.md` — covers DATA-05
- [ ] `results/.gitkeep` — supports SETP-02

---

## Project Constraints (from CLAUDE.md)

| Directive | Source | Impact on Phase 1 |
|-----------|--------|-------------------|
| Use `uv` for project management | CLAUDE.md Tech Stack | pyproject.toml must be uv-compatible |
| OpenAI SDK with configurable `base_url` | CLAUDE.md Tech Stack | config.py must expose `base_url` |
| Pydantic for JSON parsing with retry | CLAUDE.md Tech Stack | models.py uses Pydantic v2 |
| Black for formatting | CLAUDE.md Tech Stack | Dev dependency in pyproject.toml |
| Temperature 0 for all calls | CLAUDE.md Constraints | Config default must be 0 |
| No agent SDK or tool use | CLAUDE.md Key Design Decisions | No additional dependencies in this phase |
| Optimiser does NOT receive NDA | CLAUDE.md Key Design Decisions | Not relevant to Phase 1 but recorded for downstream |
| GSD workflow: use `/gsd-execute-phase` for phase work | CLAUDE.md GSD Workflow Enforcement | Implementation runs through GSD |

---

## Sources

### Primary (HIGH confidence)
- `.planning/research/STACK.md` — full stack specification, pyproject.toml template, Config pattern, Pydantic v2 patterns (verified 2026-04-11)
- `prd.md` section 5 — exact JSON shapes for all data models
- `prd.md` section 3.1–3.3 — NDA issue table, rubric items table, playbook calibration description
- PyPI JSON API — pydantic 2.12.5, openai 2.31.0, black 26.3.1 (verified 2026-04-11)
- `uv --version` on this machine — 0.7.17 (verified 2026-04-11)

### Secondary (MEDIUM confidence)
- `.planning/research/PITFALLS.md` — P12 (Pydantic v1/v2 mismatch), P13 (clause hallucination), P14 (markdown fences), P15 (results gitignore)
- `.planning/phases/01-foundation/01-CONTEXT.md` — locked decisions D-01 through D-09

### Tertiary (LOW confidence)
- None — all material claims are verified or directly locked by user decisions.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified against PyPI 2026-04-11 and STACK.md (itself verified 2026-04-11)
- Architecture: HIGH — directly specified in PRD section 5 and section 6; no invention required
- Data content (NDA/rubric/playbook): MEDIUM — content decisions are locked but actual text authoring quality depends on execution
- Pitfalls: HIGH — sourced from PITFALLS.md and direct analysis of success criteria

**Research date:** 2026-04-11
**Valid until:** 2026-05-11 (stack is stable; dependency versions may drift but are pinned with >= constraints)
