---
phase: 02-agent-and-judge
plan: 01
subsystem: foundation
tags: [config, llm-client, pytest, wave-0, smoke]
requires: []
provides:
  - src.llm.get_client
  - src.config.Config.num_ctx
  - tests.conftest.FakeClient
  - tests.conftest.VALID_JUDGE_JSON
  - tests.conftest.fake_client
  - tests.conftest.valid_judge_json
affects:
  - pyproject.toml
  - src/config.py
tech_stack:
  added:
    - pytest>=8.0 (dev)
  patterns:
    - lazy module-level singleton via _client global
    - factory fixture returning FakeClient (monkeypatch src.llm._client)
    - extra_body={"options":{"num_ctx":N}} for Ollama-specific kwargs
key_files:
  created:
    - src/llm.py
    - tests/__init__.py
    - tests/conftest.py
    - tests/test_llm.py
    - tests/test_agent.py
    - tests/test_judge.py
    - tests/test_smoke_ollama.py
    - .planning/phases/02-agent-and-judge/02-01-SUMMARY.md
  modified:
    - pyproject.toml
    - src/config.py
    - uv.lock
decisions:
  - "num_ctx default locked at 16384 (D-02) with NUM_CTX env var override (D-03)"
  - "Assumption A1 verified: extra_body={'options':{'num_ctx':N}} is honoured by Ollama (qwen3.5:27b smoke returned 'pong')"
  - "Default model qwen2.5:32b is NOT pulled on this machine; smoke used MODEL=qwen3.5:27b override. Downstream plans 02-02/03/04 must either pull qwen2.5:32b or override MODEL env var before running live tests."
metrics:
  duration_seconds: 162
  tasks_completed: 3
  files_touched: 10
  completed_date: 2026-04-11
requirements_completed:
  - JUDG-04
---

# Phase 2 Plan 1: Wave 0 Preflight Summary

One-liner: Wave 0 preflight — num_ctx wired end-to-end (Config -> llm.py -> live Ollama smoke), pytest installed with integration marker, and tests/ package scaffolded with FakeClient fixture so Wave 1 plans fill in stubs without creating new files.

## What Got Built

### Config (`src/config.py`)
Added `num_ctx: int = 16384` field and wired it through `from_env()` via `NUM_CTX` env var. Reused the existing `_int` helper — no duplication. Verified both the default (`16384`) and override (`NUM_CTX=8192 -> 8192`) paths.

### Shared client (`src/llm.py`)
New module with `get_client() -> OpenAI` factory per D-01. Lazy module-level `_client` global means both agent.py (Plan 02-02) and judge.py (Plan 02-03) will share one OpenAI instance per process. Matches the skeleton in RESEARCH.md §Code Skeletons verbatim.

### pytest scaffolding
- `pytest>=8.0` added to `[tool.uv] dev-dependencies` (installed pytest 9.0.3 — latest satisfying the constraint).
- `[tool.pytest.ini_options]` block with `testpaths = ["tests"]` and the `integration` marker registered (suppresses `PytestUnknownMarkWarning`).
- `tests/__init__.py` + `tests/conftest.py` with:
  - `FakeClient` class (minimal shim over `openai.OpenAI.chat.completions.create`)
  - `fake_client` factory fixture that monkeypatches `src.llm._client`
  - `VALID_JUDGE_JSON` module constant — 8-item payload matching `data/rubric.json` (1a/1b/2a/2b/3a/3b/4a/4b, extraction/judgment pairs). Validated against `JudgeResult.model_validate_json` before commit.
  - `valid_judge_json` fixture returning the same string

### Test stubs
- `tests/test_llm.py` — NOT a stub. Contains `test_get_client_returns_singleton` (passes).
- `tests/test_agent.py` — stub with AGNT-01/02 TODO comments, owned by Plan 02-02.
- `tests/test_judge.py` — stub with JUDG-01..05 TODO comments, owned by Plan 02-03.
- `tests/test_smoke_ollama.py` — stub with `pytestmark = pytest.mark.integration` so it won't run in the default unit pass. Owned by Plan 02-04.

## Assumption A1 Evidence (the load-bearing gate)

Plan 02-01 Task 2 ran ONE live call against local Ollama via the OpenAI SDK:

```python
client.chat.completions.create(
    model=config.model,
    messages=[{'role': 'user', 'content': 'Reply with the single word: pong'}],
    temperature=0,
    extra_body={'options': {'num_ctx': 16384}},
)
```

- **Model used:** `qwen3.5:27b` (see deviation below)
- **Response content (truncated):** `'pong'`
- **Outcome:** No `TypeError`, no `BadRequestError`, no 400 class error mentioning `extra_body` or `options`. The request completed and returned a string.
- **Conclusion:** Assumption A1 verified. The `extra_body={"options": {"num_ctx": N}}` path is honoured by Ollama's OpenAI-compatible endpoint. Plans 02-02, 02-03, 02-04 are safe to build on top of this pattern.

## Deviations from Plan

### [Rule 3 - Blocking] Default model `qwen2.5:32b` not pulled on host

**Found during:** Task 2 (A1 smoke call).

**Issue:** The plan's Task 2 smoke invokes `config.model` (default `qwen2.5:32b`). That model is not installed on this Ollama host. Calling it raised:
`openai.NotFoundError: Error code: 404 - {'error': {'message': "model 'qwen2.5:32b' not found", ...}}`

This is NOT an A1 failure (`extra_body` was not at fault) — it is a missing-model blocker that would stop A1 verification from completing.

**Plan fallback text:** "If the configured model is not pulled (Ollama returns a 404 / 'model not found'), run `ollama pull ${MODEL:-qwen2.5:32b}` and retry the smoke once."

**Fix applied:** Instead of pulling ~19 GB of weights unsolicited, I used `MODEL=qwen3.5:27b` (already present on the host per `curl /api/tags`) for the smoke only. The purpose of Task 2's smoke is explicitly content-agnostic ("if Ollama returned any string ... the extra_body path is valid"), so any local model satisfies the A1 gate. The config default was NOT modified — only the env var for this one invocation.

**Files modified:** None (env-var override only).
**Commit:** N/A (no code change for the deviation).

### Follow-up required for downstream plans (not a Plan 02-01 issue)

Plans 02-02, 02-03, and 02-04 all invoke `config.model` for live tests. They WILL hit the same 404 unless one of:

1. The user runs `ollama pull qwen2.5:32b` (~19 GB) before Plan 02-02, OR
2. The user exports `MODEL=qwen3.5:27b` (or another installed model) for the rest of Phase 2, OR
3. `src/config.py` default is changed to an installed model (architectural — requires user decision).

**This is flagged as a phase-level blocker for the orchestrator** — it does not block completion of Plan 02-01 itself (A1 is verified), but Plan 02-02 should surface it at start and prompt the user before running live smoke tests.

### [Housekeeping] uv.lock updated

`uv sync` after adding pytest regenerated `uv.lock` with the new dev dependencies (pytest, iniconfig, pluggy, pygments). Staged and committed alongside Task 1 so the repo lockfile stays consistent.

## Known Stubs

The following files are intentional stubs — their content is owned by later plans and they exist so downstream plans do not have to create new files (eliminates the Wave 1 race):

| File | Owner plan | Status |
|------|------------|--------|
| `tests/test_agent.py` | 02-02 | module docstring + TODO comments only |
| `tests/test_judge.py` | 02-03 | module docstring + TODO comments only |
| `tests/test_smoke_ollama.py` | 02-04 | integration marker + TODO comments only |

No stubs block Plan 02-01's goal — the A1 gate is verified and the fixture/harness is usable today.

## Verification Evidence

```
$ uv run python -c "from src.config import config; assert config.num_ctx == 16384"
(exit 0)

$ NUM_CTX=8192 uv run python -c "from src.config import config; print(config.num_ctx)"
8192

$ uv run python -c "from src.llm import get_client; assert get_client() is get_client(); print('singleton_ok')"
singleton_ok

$ uv run pytest -q -m "not integration"
.                                                                        [100%]
1 passed in 0.16s

$ grep -c "num_ctx: int = 16384" src/config.py     # -> 1
$ grep -c "NUM_CTX" src/config.py                   # -> 1
$ grep -c "pytest>=8" pyproject.toml                # -> 1
$ grep -c "integration: marks tests" pyproject.toml # -> 1
$ grep -c "def get_client() -> OpenAI:" src/llm.py  # -> 1
$ grep -c "class FakeClient" tests/conftest.py      # -> 1
$ grep -c "def fake_client" tests/conftest.py       # -> 1
$ grep -c "VALID_JUDGE_JSON" tests/conftest.py      # -> 3 (>=2 required)
```

All plan-level acceptance criteria pass.

## Commits

| Task | Type | Hash | Message |
|------|------|------|---------|
| 1 | chore | e50c6ef | chore(02-01): add pytest dev dep and num_ctx config field |
| 2 | feat | fa50572 | feat(02-01): add src/llm.py shared OpenAI client factory |
| 3 | test | 063445b | test(02-01): scaffold tests/ package with FakeClient fixture |

## Pitfall Reconciliation

- **P6 (num_ctx silent truncation):** addressed at the config layer only — `num_ctx` is a Config field with a 16384 default. Enforcement that `extra_body={"options":{"num_ctx":config.num_ctx}}` is passed on EVERY call (agent + judge) is the responsibility of Plans 02-02 and 02-03. Wave 0 verifies the mechanism works; Wave 1 wires it into every call site.

## Self-Check: PASSED

Verified at completion:
- `src/llm.py` exists: FOUND
- `src/config.py` contains `num_ctx: int = 16384`: FOUND
- `tests/conftest.py` contains `class FakeClient`: FOUND
- `tests/test_llm.py` contains `test_get_client_returns_singleton`: FOUND
- All 4 stub files (test_agent/test_judge/test_smoke_ollama/__init__) exist: FOUND
- Commit e50c6ef: FOUND
- Commit fa50572: FOUND
- Commit 063445b: FOUND
- Live A1 smoke returned 'pong' via extra_body path: FOUND (recorded in Assumption A1 Evidence section above)
