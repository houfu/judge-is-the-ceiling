# Judge Is The Ceiling

An experiment testing whether an LLM judge can distinguish extraction tasks (finding information) from judgment tasks (assessing significance) in NDA review.

## Thesis

The LLM judge cannot reliably distinguish between extraction and judgment. An auto-optimising loop therefore converges on outputs that score well on extraction but plateau on judgment, because the playbook cannot teach what its author did not foresee. The system's ceiling is the playbook author's foresight.

See `prd.md` for the full thesis and design rationale.

## How It Works

The experiment runs a loop: an agent reviews an NDA, a judge scores the review against a rubric, an optimiser rewrites the agent's system prompt based on feedback, and the loop repeats.

```
Pre-loop gate (go / no-go)
    |
    v
for N iterations:
    Agent  (system prompt + NDA)           --> free-text review
    Judge  (NDA + review + rubric + playbook) --> per-item scores (0/1/2)
    Optimiser (system prompt + feedback)   --> rewritten prompt
        ^                                        |
        |________________________________________|
```

**Key design choices:**

- **Same model** for agent, judge, and optimiser (default: `gemma4:26b` on local Ollama)
- **Temperature 0** on all calls for reproducibility
- **Optimiser never sees the NDA** — it works from judge feedback only, mirroring Harvey's approach where the coding agent works from failure analysis
- **Playbook is deliberately vague for judgment items** — precise for extraction, vague for judgment. This is the design choice that produces the predicted failure mode
- **Pre-loop gate** runs two reference reviews (good + flawed) through the judge before the loop starts. If the judge cannot distinguish them by a gap of at least 2.0 points with a positive judgment gap, the experiment aborts

## Project Structure

```
src/
  config.py         Config from env vars (model, base_url, temperature, iterations, num_ctx)
  llm.py            Shared OpenAI client singleton (Ollama-compatible)
  models.py         Pydantic models: RubricScore, JudgeResult, IterationResult, ExperimentRun, etc.
  agent.py          run_agent() — takes system prompt + NDA, returns free-text review
  judge.py          run_judge() — scores review against rubric, retries up to 3x on parse failure
  optimiser.py      run_optimiser() — rewrites system prompt, enforces 300-word limit
  pre_loop_test.py  run_pre_loop_test() — go/no-go gate before the loop
  loop.py           run_experiment() — main loop, writes results/run_001.json

data/
  nda.md            Synthetic NDA with 4 embedded issues (2 extraction, 2 judgment)
  rubric.json       8 rubric items (see below)
  playbook.md       Judge guidance — precise for extraction, vague for judgment
  output_a.md       Reference review (correct) — used by pre-loop gate
  output_b.md       Reference review (flawed) — used by pre-loop gate

tests/              Unit tests with FakeClient mocking; integration tests require live Ollama
results/            Runtime output (gitignored)
```

## Quick Start

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/), Ollama running locally with a model pulled (default: `gemma4:26b`).

```bash
# Install dependencies
uv sync

# Run the pre-loop calibration test (recommended first)
uv run python src/pre_loop_test.py

# Run the full experiment (5 iterations by default)
uv run python src/loop.py
```

### Configuration

All settings are read from environment variables with sensible defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL` | `gemma4:26b` | Ollama model name (with quantisation tag) |
| `BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible API endpoint |
| `API_KEY` | `ollama` | API key (Ollama ignores this) |
| `TEMPERATURE` | `0.0` | LLM temperature (0 = deterministic) |
| `NUM_ITERATIONS` | `5` | Number of loop iterations |
| `NUM_CTX` | `16384` | Context window size passed to Ollama |

Example: `NUM_ITERATIONS=2 uv run python src/loop.py` for a quick 2-iteration test run.

## The Rubric

The NDA contains 4 embedded issues. Each issue has an extraction item (find the information) and a judgment item (assess its significance). Scores are 0 (not addressed), 1 (partially addressed), or 2 (fully addressed).

| Item | Type | Question |
|------|------|----------|
| 1a | Extraction | Did the review identify the 7-year confidentiality period? |
| 1b | Judgment | Did the review flag the 7-year duration as unusual relative to market norms? |
| 2a | Extraction | Did the review locate the definition of Confidential Information? |
| 2b | Judgment | Did the review assess the breadth of the definition as a negotiation risk? |
| 3a | Extraction | Did the review identify the non-solicitation obligation? |
| 3b | Judgment | Did the review flag the placement in remedies as unusual and the obligation as beyond NDA scope? |
| 4a | Extraction | Did the review identify the independently-developed-information exception? |
| 4b | Judgment | Did the review recognise that the additional requirements make the exception functionally unusable? |

The thesis predicts that extraction scores (a items) converge toward 2 across iterations while judgment scores (b items) plateau.

## Reading the Results

### `results/pre_loop_test.json`

The go/no-go gate result. Key fields:
- `decision` — `"go"` or `"no-go"`
- `gap` — total score difference between the good and flawed reference reviews (must be >= 2.0)
- `judgment_gap` — judgment-specific gap (must be > 0)
- `variance_warning` — whether scores varied significantly between duplicate runs

### `results/run_001.json`

The full experiment run. Key fields:
- `iterations[]` — one entry per iteration, each containing:
  - `system_prompt` — the prompt used for that iteration
  - `agent_output` — the agent's review text
  - `scores[]` — per-item judge scores with evidence and reasoning
  - `extraction_score`, `judgment_score` — category totals
  - `optimiser_feedback_seen` — what feedback the optimiser received
  - `prompt_diff` — unified diff of the prompt rewrite
  - `prompt_word_count` — tracks prompt growth (P11 signal)
- `deltas[]` — per-item score changes between consecutive iterations (`null` for iteration 0)
- `config` — model name, temperature, Ollama version, iteration count

To test the thesis, compare `extraction_score` and `judgment_score` trajectories across iterations. If extraction climbs while judgment stays flat, the ceiling held.

## Further Reading

See `prd.md` for the full product specification, thesis details, and component design.
