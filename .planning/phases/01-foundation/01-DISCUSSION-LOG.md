# Phase 1: Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-11
**Phase:** 01-foundation
**Areas discussed:** NDA design, Rubric calibration

---

## NDA Design

### NDA Length

| Option | Description | Selected |
|--------|-------------|----------|
| Short (~1000 words) | 4-5 pages, maximises context headroom | |
| Medium (~1500 words) | 6-8 pages, room for issues to feel natural | ✓ |
| Realistic (~2500 words) | 10+ pages, closer to real NDA | |

**User's choice:** Medium (~1500 words)

### Issue Hiding Depth

| Option | Description | Selected |
|--------|-------------|----------|
| Lightly hidden | Standard clause headings, detectable by careful reading | ✓ |
| Structurally buried | Non-solicitation under Remedies, carve-out nested in exceptions | |
| You decide | Claude uses legal judgment | |

**User's choice:** Lightly hidden

### Clause Format

| Option | Description | Selected |
|--------|-------------|----------|
| Numbered sections | 1. Definitions, 2. Obligations — standard commercial format | ✓ |
| Numbered with subs | 1.1, 1.2, 2.1 — more granular | |
| You decide | Claude picks | |

**User's choice:** Numbered sections

### Jurisdiction

| Option | Description | Selected |
|--------|-------------|----------|
| Unnamed jurisdiction | "Laws of [Jurisdiction]" placeholder | |
| England & Wales | Common law, well-understood | |
| Singapore | User's custom choice | ✓ |

**User's choice:** Singapore (custom input — overrides PRD's "no Singapore-specific provisions" with Singapore governing law but generic NDA content)

### NDA Parties / Review Perspective

| Option | Description | Selected |
|--------|-------------|----------|
| Receiving party | More issues to flag | |
| Disclosing party | Fewer issues to flag | |
| Neutral review | Identifies issues for either side | ✓ |

**User's choice:** Neutral review

### Standard Clause Realism

| Option | Description | Selected |
|--------|-------------|----------|
| Boilerplate-realistic | Real commercial NDA patterns, feels like a real agreement | ✓ |
| Minimal scaffolding | Only enough to blend issues in | |
| You decide | Claude judges needed amount | |

**User's choice:** Boilerplate-realistic

---

## Rubric Calibration

### Playbook Vagueness Level

| Option | Description | Selected |
|--------|-------------|----------|
| Minimally vague | General direction but lacks specifics | ✓ |
| Maximally vague | Almost content-free descriptions | |
| Realistic vague | Natural imprecision, tried to be precise but couldn't | |

**User's choice:** Minimally vague

### Partial Credit (Score=1) Definition

| Option | Description | Selected |
|--------|-------------|----------|
| Clear partial credit | Well-defined for both extraction and judgment | |
| Vague partial credit | Score 1 for judgment items is deliberately fuzzy | ✓ |
| You decide | Claude calibrates | |

**User's choice:** Vague partial credit — mirrors judgment vagueness

### Rubric JSON Format

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal | item_id, item_type, issue_number, question, max_score. Scoring guidance in playbook only | ✓ |
| Self-contained | Scoring guidance embedded in rubric.json alongside each item | |
| You decide | Claude picks cleanest format | |

**User's choice:** Minimal — scoring guidance lives in playbook only

---

## Claude's Discretion

- Data model schema design
- Sample review content (Output A and B) — Claude drafts, author edits
- Config module structure
- Project layout

## Deferred Ideas

None
