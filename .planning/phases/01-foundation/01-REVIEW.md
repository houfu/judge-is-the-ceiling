---
phase: 01-foundation
reviewed: 2026-04-11T00:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - .gitignore
  - data/nda.md
  - data/output_a.md
  - data/output_b.md
  - data/playbook.md
  - data/rubric.json
  - pyproject.toml
  - results/.gitkeep
  - src/__init__.py
  - src/config.py
  - src/models.py
findings:
  critical: 0
  warning: 3
  info: 7
  total: 10
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-04-11
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Phase 1 delivers the foundation for "Judge Is The Ceiling": a project skeleton,
two Pydantic v2 data model modules, a `Config` dataclass, and five static data
files (NDA, rubric, playbook, Output A, Output B). The data artefacts are
well-constructed and align with the experiment's intentional design: Output A
is a substantive neutral review, Output B is plausible-but-flawed (each issue
assessed at Low/Moderate risk with no meaningful negotiation analysis), and the
playbook explicitly distinguishes mechanical extraction items (1a–4a) from
deliberately softer judgment items (1b–4b). The rubric JSON and playbook markdown
stay in sync on item IDs, item types, and questions.

The Python code is small and correct in its core logic, but there are several
robustness issues worth addressing before Phase 2 wires this up to LLM calls:

- `Config` reads environment variables at **class-definition time** (not instance
  construction), and performs unguarded `float()`/`int()` casts that can raise
  `ValueError` during import with a confusing traceback.
- `src/models.py` uses `list[IterationResult] = []` as a Pydantic field default;
  Pydantic v2 handles this safely, but `Field(default_factory=list)` is the
  idiomatic and less surprising form.
- Several fields on `ExperimentRun` and `IterationResult` are loosely typed
  (`dict`, `str` for timestamp) in a codebase that otherwise invests in
  Pydantic models for type safety.
- `.gitignore` does not ignore `.env`, despite the project reading API keys and
  base URLs from environment variables — a secret-leak foot-gun.

No critical security issues were found. No hardcoded production secrets. The
`"ollama"` default API key in `src/config.py` is the documented placeholder for
a local Ollama server and is not a live credential. The data files are
documentation/fixture content and are out of scope for bug/security review.

## Warnings

### WR-01: `Config` reads env vars at class-definition time, not instance construction

**File:** `src/config.py:5-14`
**Issue:** The `@dataclass` decorator evaluates default-value expressions once
when the class body executes (at module import). That means
`os.getenv("MODEL", "qwen2.5:32b")`, `float(os.getenv("TEMPERATURE", "0"))`,
etc., all run exactly once — when `src.config` is first imported. Any test
fixture, CLI wrapper, or Phase 2 harness that sets env vars **after** import
and then constructs a new `Config()` will silently get the stale values from
import time. This is a common and confusing footgun that will bite during
testing and when constructing `ExperimentRun.config` dicts from per-run
overrides.

Additionally, if `TEMPERATURE` or `NUM_ITERATIONS` is set to an unparseable
value, the `float()`/`int()` call raises `ValueError` during `import src.config`,
producing a traceback that points at the class body rather than at the bad
env var.

**Fix:** Move env reads into `__post_init__` or (preferred) a `from_env`
classmethod, and wrap the numeric casts with a clear error message:

```python
import os
from dataclasses import dataclass


@dataclass
class Config:
    model: str = "qwen2.5:32b"
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    temperature: float = 0.0
    num_iterations: int = 5

    @classmethod
    def from_env(cls) -> "Config":
        def _float(key: str, default: float) -> float:
            raw = os.getenv(key)
            if raw is None:
                return default
            try:
                return float(raw)
            except ValueError as exc:
                raise ValueError(f"Invalid {key}={raw!r}; expected float") from exc

        def _int(key: str, default: int) -> int:
            raw = os.getenv(key)
            if raw is None:
                return default
            try:
                return int(raw)
            except ValueError as exc:
                raise ValueError(f"Invalid {key}={raw!r}; expected int") from exc

        return cls(
            model=os.getenv("MODEL", "qwen2.5:32b"),
            base_url=os.getenv("BASE_URL", "http://localhost:11434/v1"),
            api_key=os.getenv("API_KEY", "ollama"),
            temperature=_float("TEMPERATURE", 0.0),
            num_iterations=_int("NUM_ITERATIONS", 5),
        )


config = Config.from_env()
```

This preserves the module-level `config` singleton convenience while allowing
tests to construct fresh `Config()` or `Config.from_env()` instances whenever
they need to.

---

### WR-02: `.gitignore` does not ignore `.env`, risking API key leakage

**File:** `.gitignore:1-5`
**Issue:** `src/config.py` reads `MODEL`, `BASE_URL`, `API_KEY`, `TEMPERATURE`,
and `NUM_ITERATIONS` from environment variables. The conventional developer
workflow for this is a `.env` file committed to `.gitignore`. Today, a
developer who creates `.env` with a real API key (e.g., when pointing the
OpenAI SDK at a hosted endpoint instead of local Ollama) would silently stage
it on the next `git add .`. For an experiment that is explicitly designed to
be portable between Ollama and other OpenAI-compatible backends, this is a
realistic risk.

**Fix:** Add to `.gitignore`:

```
# Environment
.env
.env.*
!.env.example

# Python caches
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.egg-info/

# OS
.DS_Store
```

---

### WR-03: `IterationResult` denormalizes score totals without a validator

**File:** `src/models.py:19-26`
**Issue:** `IterationResult` stores `scores` alongside three derived totals —
`total_score`, `extraction_score`, `judgment_score` — but there is no validator
enforcing that the totals match the contents of `scores`. A caller that
constructs an `IterationResult` manually, or that mutates `scores` after
construction, can produce an inconsistent record. Since these records are
written to disk in `results/` and later analysed, inconsistency is a
correctness risk for the experiment itself.

Separately, `compute_category_scores` in the same file computes extraction and
judgment sums but does not expose a matching helper for `total_score`, so
different call sites could compute the total differently.

**Fix:** Use a Pydantic v2 `model_validator` to enforce the invariant (and let
callers optionally omit the derived fields):

```python
from pydantic import BaseModel, Field, model_validator


class IterationResult(BaseModel):
    iteration: int
    system_prompt: str
    agent_output: str
    scores: list[RubricScore]
    total_score: int = 0
    extraction_score: int = 0
    judgment_score: int = 0

    @model_validator(mode="after")
    def _check_totals(self) -> "IterationResult":
        extraction, judgment = compute_category_scores(self.scores)
        total = extraction + judgment
        # If caller left defaults, fill them in; otherwise enforce consistency.
        if self.extraction_score == 0 and self.judgment_score == 0 and self.total_score == 0:
            object.__setattr__(self, "extraction_score", extraction)
            object.__setattr__(self, "judgment_score", judgment)
            object.__setattr__(self, "total_score", total)
            return self
        if (self.extraction_score, self.judgment_score, self.total_score) != (extraction, judgment, total):
            raise ValueError(
                f"IterationResult totals inconsistent with scores: "
                f"got ({self.extraction_score}, {self.judgment_score}, {self.total_score}), "
                f"expected ({extraction}, {judgment}, {total})"
            )
        return self
```

## Info

### IN-01: Use `Field(default_factory=list)` instead of mutable default `[]`

**File:** `src/models.py:37`
**Issue:** `iterations: list[IterationResult] = []` relies on Pydantic v2's
(correct) deep-copy-of-default behaviour. It will not cause shared-state bugs
the way a plain dataclass would, but the idiomatic and self-documenting form
for a Pydantic model is to use `Field(default_factory=list)`. This also
signals intent to future readers who have been trained to flag bare-list
defaults on sight.
**Fix:**
```python
from pydantic import BaseModel, Field

class ExperimentRun(BaseModel):
    ...
    iterations: list[IterationResult] = Field(default_factory=list)
```

---

### IN-02: Loose typing for `ExperimentRun.config` and `pre_loop_test`

**File:** `src/models.py:32,36`
**Issue:** `config: dict` and `pre_loop_test: dict | None` accept any dict
shape. In a Pydantic-first codebase where the rest of the models are tightly
typed, this throws away schema guarantees exactly at the places where they
matter most for reproducibility (run config) and analysis (pre-loop baseline).
**Fix:** Replace with explicit models, or at minimum parameterize:

```python
from typing import Any

class ExperimentRun(BaseModel):
    ...
    config: dict[str, Any]
    pre_loop_test: dict[str, Any] | None = None
```

A dedicated `PreLoopTest` BaseModel would be even better once Phase 2 pins
down its shape.

---

### IN-03: `ExperimentRun.timestamp` typed as `str` rather than `datetime`

**File:** `src/models.py:31`
**Issue:** Using `str` for timestamps defers format validation to every
downstream consumer and makes sorting/comparison error-prone. Pydantic v2
serialises `datetime` to ISO-8601 strings automatically.
**Fix:**
```python
from datetime import datetime

class ExperimentRun(BaseModel):
    experiment_id: str
    timestamp: datetime
    ...
```

---

### IN-04: No validator enforcing `RubricScore.item_id` format

**File:** `src/models.py:5-12`
**Issue:** The rubric and playbook define exactly eight item IDs matching
`^[1-4][ab]$`. A Pydantic field validator (or `Literal`) would catch typos like
`"1A"` or `"5a"` at construction time instead of at analysis time.
**Fix:** Use a `Literal` union, which also documents the rubric in code:
```python
from typing import Literal

ItemId = Literal["1a", "1b", "2a", "2b", "3a", "3b", "4a", "4b"]

class RubricScore(BaseModel):
    item_id: ItemId
    ...
```

Consider also validating that `issue_number` is in `1..4` and matches the
leading digit of `item_id`.

---

### IN-05: `pyproject.toml` missing `[build-system]` and lint tooling

**File:** `pyproject.toml:1-17`
**Issue:** The file declares `[project]` and dev dependencies but no
`[build-system]` table. For a pure `uv`-managed script layout this works
today, but adding a build backend (e.g., `hatchling`) is a small upfront cost
that avoids surprises if Phase 2+ wants to `pip install -e .` for editable
installs or tests. Additionally, the only dev tool is `black`; a Python 3.11+
project that ships Pydantic models would benefit from `ruff` and `mypy` (or
`pyright`) to catch the kinds of typing issues flagged in IN-02 through IN-04.
**Fix:** Optional — add when the project grows past Phase 1:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
dev-dependencies = [
    "black>=26.0",
    "ruff>=0.6",
    "mypy>=1.11",
    "pytest>=8",
]
```

---

### IN-06: `src/__init__.py` is empty; no package-level exports

**File:** `src/__init__.py:1`
**Issue:** The file exists but is empty. That is perfectly valid for a
namespace-style package, but given the project will soon expose a small
surface (`Config`, `RubricScore`, `JudgeResult`, `IterationResult`,
`ExperimentRun`, `compute_category_scores`), a lightweight re-export makes
downstream imports more ergonomic and documents the public API.
**Fix:**
```python
from src.config import Config, config
from src.models import (
    RubricScore,
    JudgeResult,
    IterationResult,
    ExperimentRun,
    compute_category_scores,
)

__all__ = [
    "Config",
    "config",
    "RubricScore",
    "JudgeResult",
    "IterationResult",
    "ExperimentRun",
    "compute_category_scores",
]
```

Skip this if the project prefers fully-qualified imports throughout — it is
purely a style/ergonomics call.

---

### IN-07: `compute_category_scores` return tuple is positional-only

**File:** `src/models.py:40-44`
**Issue:** Returning `tuple[int, int]` forces every caller to remember that
position 0 is extraction and position 1 is judgment. A `NamedTuple` or small
dataclass makes the contract self-documenting and eliminates a whole class of
"I swapped the tuple elements" bugs in downstream aggregation code.
**Fix:**
```python
from typing import NamedTuple

class CategoryScores(NamedTuple):
    extraction: int
    judgment: int

def compute_category_scores(scores: list[RubricScore]) -> CategoryScores:
    extraction = sum(s.score for s in scores if s.item_type == "extraction")
    judgment = sum(s.score for s in scores if s.item_type == "judgment")
    return CategoryScores(extraction=extraction, judgment=judgment)
```

This remains tuple-unpacking compatible for existing callers.

---

_Reviewed: 2026-04-11_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
