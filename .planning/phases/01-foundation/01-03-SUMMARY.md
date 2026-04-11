---
phase: 01-foundation
plan: "03"
subsystem: data
tags: [nda-review, output-a, output-b, rubric, playbook, experiment-data]
dependency_graph:
  requires:
    - "01-02 (nda.md, rubric.json, playbook.md)"
  provides:
    - "data/output_a.md — model NDA review scoring 2/2 on all 8 rubric items"
    - "data/output_b.md — flawed NDA review nailing extraction, missing judgment"
  affects:
    - "Phase 3 pre-loop judge test (consumes both outputs)"
tech_stack:
  added: []
  patterns:
    - "Static markdown files as experiment data inputs"
key_files:
  created:
    - data/output_a.md
    - data/output_b.md
  modified: []
decisions:
  - "Output A uses substantive judgment analysis — market norms, negotiation risk, unusual placement, functionally unusable — to score 2/2 on all 8 rubric items"
  - "Output B deliberately omits judgment depth: calls non-solicitation 'standard', treats exception as 'available with adequate protection', and gives no market norm comparison — targeting 0-1 on judgment items while correctly extracting all 4 issues"
  - "Both outputs take the neutral perspective (D-05) and reference actual NDA clause numbers"
metrics:
  duration_minutes: 5
  completed_date: "2026-04-11"
  tasks_completed: 1
  tasks_total: 1
  files_created: 2
  files_modified: 0
---

# Phase 1 Plan 03: Author Output A and Output B Summary

**One-liner:** Model NDA review (Output A) and extraction-only flawed review (Output B) authored against clauses 4.1, 1.1, 7.2, and 3.2 to produce a measurable judgment gap in the pre-loop judge test.

---

## What Was Built

Two pre-written NDA reviews for use in the Phase 3 pre-loop judge calibration test.

**data/output_a.md** — Model review (~1,050 words). Scores 2/2 on all 8 rubric items:
- **Issue 1 (Clause 4.1):** Identifies 7-year term, compares to 2-3 year market norm, addresses practical implications (compliance overhead, extended liability exposure, interaction with exception requirements)
- **Issue 2 (Clause 1.1):** Quotes the full overbroad definition (business, operations, customers, technology, strategy), analyses negotiation risk (no materiality threshold, no designation requirement, open-ended catch-all, affiliate coverage), recommends specific carve-outs
- **Issue 3 (Clause 7.2):** Identifies 24-month non-solicitation in the remedies section, flags unusual placement as a structural problem, explains how embedding it in remedies obscures the obligation, and articulates why this extends beyond NDA scope into territory for separate employment agreements
- **Issue 4 (Clause 3.2):** Identifies all three onerous requirements (contemporaneous records, third-party audit at Receiving Party's cost, prior written notice), analyses why each requirement is practically impossible in commercial settings, concludes the exception is functionally unusable

**data/output_b.md** — Flawed review (~750 words). Scores 2/2 on extraction (1a, 2a, 3a, 4a), 0-1 on judgment (1b, 2b, 3b, 4b):
- **Issue 1:** Correctly states 7-year term; no market norm comparison; calls it "on the longer end" without analysis (Score 1b: 0)
- **Issue 2:** Correctly describes the broad definition categories; calls it "comprehensive" and "typical"; no negotiation risk analysis (Score 2b: 0)
- **Issue 3:** Correctly identifies 24-month non-solicitation; calls it "standard feature of commercial agreements"; does not flag unusual placement or scope concern (Score 3b: 0)
- **Issue 4:** Correctly describes all three requirements; concludes they "reflect the Disclosing Party's interest" and the exception is "available"; no analysis of practical impossibility (Score 4b: 0-1)

---

## Verification

All acceptance criteria met:
- Output A: contains "market norm", "negotiation risk", "unusual", "unusable" — confirmed
- Output B: contains no instances of "unusable", "beyond nda scope", or "unusual placement" — confirmed
- Both files reference actual clause numbers (4.1, 1.1, 7.2, 3.2)
- Both files reference the 7-year confidentiality period, the definition, non-solicitation, and the independently-developed-information exception
- Both files are substantially above the 300-word minimum

---

## Deviations from Plan

None — plan executed exactly as written.

---

## Known Stubs

None. Both files are complete static inputs with no placeholder content.

---

## Threat Flags

None. Static content files with no runtime trust boundaries (per plan's threat model).

---

## Self-Check

- [x] data/output_a.md exists and contains all 4 judgment signals
- [x] data/output_b.md exists and contains no prohibited judgment signals
- [x] Both files reference actual NDA clause numbers
- [x] Output B nails extraction: all 4 issues correctly identified at extraction level
