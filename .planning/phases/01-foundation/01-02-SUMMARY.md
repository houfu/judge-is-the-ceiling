---
plan: 01-02
phase: 01-foundation
status: complete
started: 2026-04-11
completed: 2026-04-11
---

# Plan 01-02: NDA + Rubric + Playbook — Summary

## What Was Built

Authored the three core static data files for the experiment: synthetic NDA with 4 embedded issues, 8-item rubric, and judge playbook with deliberately-calibrated vagueness on judgment items.

## Key Files

### Created
- `data/nda.md` — ~1878-word synthetic NDA with 12 numbered clauses, Singapore governing law, neutral review perspective
- `data/rubric.json` — 8-item rubric (1a, 1b, 2a, 2b, 3a, 3b, 4a, 4b) with minimal metadata per D-09
- `data/playbook.md` — Scoring guidance: precise for extraction items, deliberately vague for judgment items per D-07, D-08

## NDA Issue Placement

| # | Issue | Clause | Category |
|---|-------|--------|----------|
| 1 | 7-year confidentiality term | 4.1 | Extraction (1a) + Judgment (1b) |
| 2 | Overbroad definition of Confidential Information | 1.1 | Extraction (2a) + Judgment (2b) |
| 3 | 24-month non-solicitation buried in Remedies | 7.2 | Extraction (3a) + Judgment (3b) |
| 4 | Gutted independently-developed-info exception | 3.2 | Extraction (4a) + Judgment (4b) |

## Decisions Honored

- **D-01:** NDA length ~1878 words (close to 1500 target, room for boilerplate realism)
- **D-02:** Lightly hidden issues — standard headings, detectable by careful reading
- **D-03:** Numbered sections (1-12) to prevent clause hallucination
- **D-04:** Singapore governing law (clause 12)
- **D-05:** Neutral review perspective (no stated party)
- **D-06:** Boilerplate-realistic — entire agreement, severability, notices, assignment, waiver all present
- **D-07:** Playbook minimally vague for judgment items — "intentionally soft" boundary language
- **D-08:** Partial credit (score=1) deliberately fuzzy for judgment items
- **D-09:** Rubric JSON minimal — only item_id, item_type, issue_number, question, max_score; scoring guidance in playbook only

## Verification

- Rubric has exactly 8 items in order 1a, 1b, 2a, 2b, 3a, 3b, 4a, 4b
- Each rubric item has exactly 5 keys (no scoring guidance)
- All 4 NDA issues grep-verified present
- 12 numbered clauses in NDA (sections 1-12)

## Deviations

NDA word count is 1878 vs 1500 target — slightly over. Driven by the need to include boilerplate-realistic standard clauses per D-06. Still within context window headroom for local Ollama models.

## Self-Check: PASSED
