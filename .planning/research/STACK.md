# Stack Research: Judge Is The Ceiling

**Confidence:** HIGH (stack is largely pre-decided; research confirms choices and resolves open patterns)

## Recommended Stack

**Runtime:**
- Python 3.11+ — best Pydantic v2 performance, full type annotation support
- uv 0.7.x — `uv sync` + `uv run python src/loop.py`, no venv activation

**Core dependencies (runtime):**
- `openai>=2.0` (current: 2.31.0) — OpenAI Python SDK with `base_url` for Ollama
- `pydantic>=2.0` (current: 2.12.5) — structured output validation with retry

**Dev dependencies:**
- `black>=26.0` (current: 26.3.1) — formatting

## Key Patterns

### Ollama Client Configuration

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",  # from config
    api_key="ollama",  # required by SDK, ignored by Ollama
)
```

### Pydantic v2 Models

```python
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

### Retry Pattern (3 attempts)

```python
import json
from pydantic import ValidationError

def call_judge_with_retry(client, messages, max_retries=3):
    for attempt in range(max_retries):
        response = client.chat.completions.create(...)
        raw = response.choices[0].message.content
        try:
            return JudgeResult.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as e:
            if attempt == max_retries - 1:
                raise
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"Parsing error: {e}\n\nReturn only valid JSON. No preamble. No markdown fences.",
            })
```

### Config Pattern (stdlib only)

```python
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

### pyproject.toml

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
