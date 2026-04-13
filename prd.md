# PRD: Auto-Optimising Legal Agent Experiment

**Author:** Ang Hou Fu
**Date:** 11 April 2026
**Status:** Planning

---

## 1. Purpose

Build an experiment that runs an auto-optimising agent loop on an NDA review task, captures all artifacts (prompts, outputs, judge scores, reasoning, feedback), and writes them to structured output files. A separate Streamlit app will consume these files for presentation.

---

## 2. Thesis Under Test

The LLM judge cannot reliably distinguish between extraction (finding information) and judgment (assessing significance). The optimisation loop therefore converges on outputs that score well on both but are only substantively correct on extraction tasks.

The deeper insight: the loop can only learn what its evaluation playbook teaches it to look for. Writing a playbook that captures legal judgment requires the legal judgment the system is supposed to replace. The system's ceiling is the playbook author's foresight.

---

## 3. Components

### 3.1 The NDA (Static Input)

A synthetic commercial NDA in markdown or plain text. Mostly market-standard with four embedded issues:

| # | Issue | Category | What's Wrong |
|---|-------|----------|-------------|
| 1 | Confidentiality period | Extraction | 7-year term (market standard 2–3 years) |
| 2 | Definition scope | Extraction | Overbroad — captures all information relating to business, operations, customers, technology, strategy |
| 3 | Non-solicitation in remedies | Judgment | 24-month employee non-solicitation buried in remedies section |
| 4 | Gutted carve-out | Judgment | Independently-developed-information exception modified with requirements so onerous it's functionally unusable |

The rest of the NDA should be genuinely standard so the issues don't stand out structurally. Generic common-law jurisdiction — no Singapore-specific provisions.

Stored as a text file loaded at runtime.

### 3.2 The Rubric (Static Input)

Eight rubric items — each issue gets an (a) extraction item and a (b) judgment item:

| Item | Type | Question |
|------|------|----------|
| 1a | Extraction | Did it identify the 7-year confidentiality period? |
| 1b | Judgment | Did it flag the duration as unusual relative to market norms? |
| 2a | Extraction | Did it locate the definition of Confidential Information? |
| 2b | Judgment | Did it assess the breadth as a negotiation risk? |
| 3a | Extraction | Did it identify the non-solicitation obligation? |
| 3b | Judgment | Did it flag the placement in remedies as unusual and the obligation as beyond NDA scope? |
| 4a | Extraction | Did it identify the independently-developed-information exception? |
| 4b | Judgment | Did it recognise the additional requirements make the exception functionally unusable? |

Scoring: 0 (not addressed), 1 (partially addressed), 2 (fully addressed).

### 3.3 The Playbook (Static Input)

Guidance document given to the judge describing what a 0, 1, and 2 looks like for each rubric item.

**Extraction items:** Precise descriptions. E.g., "Score 0 if the confidentiality period is not mentioned. Score 1 if a duration is mentioned but not the specific 7-year term. Score 2 if the 7-year term is explicitly identified."

**Judgment items:** Deliberately vague descriptions. E.g., "Score 0 if the exception is not discussed. Score 1 if the exception is mentioned but not assessed. Score 2 if the agent provides a substantive assessment of the exception's practical effect."

The vagueness on judgment items is a design choice — it's more realistic and produces the predicted failure mode.

Stored as a text file or inline in the judge prompt template.

### 3.4 The Agent

**Input:** System prompt + NDA text.

**Iteration zero system prompt:**
```
You are reviewing a Non-Disclosure Agreement. Identify all issues
and assess their significance. Output your findings as a structured
list. For each issue provide: the clause reference, a description
of the issue, and your risk assessment.
```

**Output:** Structured text — the NDA review.

### 3.5 The Judge

**Input:** NDA text + agent output + rubric + playbook.

**Output:** A JSON response with, for each of the 8 rubric items:
- `item_id`: e.g. "1a", "3b"
- `score`: 0, 1, or 2
- `evidence`: quote or reference from the agent's output
- `reasoning`: why this score was given
- `feedback`: specific instruction for what to improve

**The judge prompt must instruct the model to return only valid JSON, no preamble, no markdown fences.** Parse with Pydantic. On validation failure, retry up to 3 times by sending the output back with the error message and asking for correction.

### 3.6 The Optimiser

Takes the judge's feedback across all 8 items and the current system prompt. Rewrites the system prompt for the next iteration.

**Prompt:**
```
You are improving an NDA review agent. Below is its current system
prompt and feedback from an evaluation. Rewrite the system prompt
to address the feedback. Keep all existing instructions that are
working. Add specific guidance to address the gaps identified.
Do not remove instructions that led to correct results.
Return only the new system prompt, nothing else.
```

**Input:** Current system prompt + judge feedback. Does not receive the NDA — it works from the feedback only, mirroring Harvey's setup where the coding agent works from failure analysis rather than re-reading source documents.

**Output:** The new system prompt (string).

### 3.7 The Loop

```
for iteration in range(num_iterations):
    agent_output = run_agent(system_prompt, nda_text)
    judge_result = run_judge(nda_text, agent_output, rubric, playbook)
    log(iteration, system_prompt, agent_output, judge_result)
    system_prompt = run_optimiser(system_prompt, judge_result)
```

Default: 5 iterations.

---

## 4. Pre-Loop Judge Test

Before running the loop, test the judge in isolation.

### Inputs
- **Output A:** A model NDA review written by the author. Correctly identifies all four issues including judgment calls.
- **Output B:** A plausible-but-flawed review. Nails extraction, misses judgment. Describes the carve-out accurately but concludes it's standard. Finds the non-solicitation text but doesn't flag placement or scope.

Both stored as text files.

### Process
Run each output through the judge with the same rubric and playbook. Log results in the same format as the loop.

### Purpose
Establishes whether the judge can distinguish quality on judgment items before the loop introduces confounding variables.

---

## 5. Data Model

All outputs are JSON. The Streamlit app reads these files.

### Experiment Run

```json
{
  "experiment_id": "run_001",
  "timestamp": "2026-04-12T14:30:00Z",
  "config": {
    "model": "qwen2.5:32b",
    "base_url": "http://localhost:11434/v1",
    "temperature": 0,
    "num_iterations": 5
  },
  "nda_file": "nda.md",
  "rubric_file": "rubric.json",
  "playbook_file": "playbook.md",
  "pre_loop_test": { ... },
  "iterations": [ ... ]
}
```

### Pre-Loop Test Result

```json
{
  "output_a": {
    "source_file": "output_a.md",
    "scores": [
      {
        "item_id": "1a",
        "item_type": "extraction",
        "issue_number": 1,
        "score": 2,
        "evidence": "...",
        "reasoning": "...",
        "feedback": "..."
      }
    ]
  },
  "output_b": { ... }
}
```

### Iteration Result

```json
{
  "iteration": 0,
  "system_prompt": "You are reviewing a Non-Disclosure Agreement...",
  "agent_output": "...",
  "scores": [
    {
      "item_id": "1a",
      "item_type": "extraction",
      "issue_number": 1,
      "score": 2,
      "evidence": "...",
      "reasoning": "...",
      "feedback": "..."
    }
  ],
  "total_score": 12,
  "extraction_score": 8,
  "judgment_score": 4
}
```

### Human Review (Manual, Post-Experiment)

```json
{
  "iteration_reviewed": 4,
  "human_scores": [
    {
      "item_id": "3b",
      "judge_score": 2,
      "human_score": 0,
      "judge_reasoning": "The agent identified the non-solicitation and noted...",
      "human_reasoning": "The agent found the clause but failed to recognise..."
    }
  ]
}
```

---

## 6. File Structure

```
nda-judge-experiment/
├── pyproject.toml
├── README.md
├── data/
│   ├── nda.md                  # The synthetic NDA
│   ├── rubric.json             # 8 rubric items with metadata
│   ├── playbook.md             # Judge guidance document
│   ├── output_a.md             # Good review (author-written)
│   └── output_b.md             # Flawed review (author-written)
├── src/
│   ├── agent.py                # run_agent(system_prompt, nda_text) → str
│   ├── judge.py                # run_judge(nda_text, agent_output, rubric, playbook) → JudgeResult
│   ├── optimiser.py            # run_optimiser(system_prompt, judge_result) → str
│   ├── loop.py                 # Main loop: ties agent, judge, optimiser together
│   ├── pre_loop_test.py        # Runs Output A and B through the judge
│   ├── config.py               # Model name, base URL, temperature, iteration count
│   └── models.py               # Pydantic models for JudgeResult, IterationResult, ExperimentRun
├── results/
│   ├── pre_loop_test.json      # Judge test results
│   ├── run_001.json            # Full experiment run
│   └── human_review.json       # Manual post-experiment review
└── streamlit_app/
    └── (separate — reads from results/)
```

---

## 7. Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python | Author's preference |
| Environment | `uv` | Author's standard |
| Code style | Black | Author's preference |
| LLM SDK | `openai` Python SDK with configurable `base_url` | OpenAI-compatible API works with Ollama; no provider lock-in; readers can swap in any compatible endpoint |
| LLM runtime | Ollama (local) | No API costs; full control; reproducible |
| Model | Configurable via `config.py`. Default TBD — needs decent context window for ~10-page NDA + rubric + playbook | Same model for agent, judge, and optimiser |
| Temperature | 0 for all calls | Reproducibility; Ollama supports this |
| JSON parsing | Pydantic validation with retry | Instruct model to return only JSON, no preamble, no fences. On validation failure, send output + error back to model, retry up to 3 times. Log failures and move on after 3 retries. |
| Data output | JSON files in `results/` | Simple, portable, Streamlit reads directly |
| Agent harness | Prompt rewriting only | Simplicity is the argument — no agent SDK, no code generation, no tools |
| Optimiser context | Current system prompt + judge feedback only (no NDA) | Mirrors Harvey's setup; keeps context window smaller for local model |

---

## 8. Sequence of Work

1. **Set up project.** `uv init`, add dependencies (`openai`, `pydantic`), create file structure.
2. **Write the NDA.** Full synthetic NDA with four embedded issues. Store in `data/nda.md`.
3. **Write the rubric.** 8 items with metadata (item_id, type, issue_number, question, scoring guidance). Store in `data/rubric.json`.
4. **Write the playbook.** Judge guidance with precise descriptions for extraction items, vague descriptions for judgment items. Store in `data/playbook.md`.
5. **Write Output A and Output B.** The good and flawed reviews. Store in `data/`.
6. **Build `models.py`.** Pydantic models for all data structures.
7. **Build `config.py`.** Model name, base URL, temperature, iteration count. Read from environment variables or defaults.
8. **Build `agent.py`.** System prompt + NDA text → OpenAI chat completion → output string.
9. **Build `judge.py`.** Judge prompt construction, API call, JSON parsing with Pydantic validation, retry logic.
10. **Build `pre_loop_test.py`.** Run Output A and B through judge. Write results to `results/pre_loop_test.json`.
11. **Run pre-loop test.** Evaluate results. Decision point — if the judge reliably distinguishes A from B on judgment items, reconsider thesis before proceeding.
12. **Build `optimiser.py`.** Current prompt + judge feedback → API call → new prompt string.
13. **Build `loop.py`.** Tie together agent → judge → log → optimiser → repeat. Write results to `results/run_001.json`.
14. **Run the loop.** 5 iterations. Inspect results.
15. **Human review.** Author reads converged output, scores judgment items independently, writes `results/human_review.json`.
16. **Streamlit app.** Separate task — reads from `results/` and presents findings.
