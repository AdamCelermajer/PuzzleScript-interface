---
title: Present the research proposal
status: in-progress
order: 7
due: 2026-10-22
threads: [proposal]
links:
  - "Proposal source | docs/proposal/main.tex"
  - "Proposal draft (PDF) | docs/proposal/proposal-draft.pdf"
  - "Committee review (19 Oct) | docs/proposal/committee-review-20261019.md"
runs: []
---
## Question
What is the proposal's current state, ready to present at the Thursday 22 October meeting?

## Current answer
Mock committee review done on 19 Oct: `docs/proposal/committee-review-20261019.md` (format check, 15 ranked questions, 19 proposed edits, 12-slide outline).
- Format: 9 body pages and a TOC pass, but Related Work is 0.6 page against 2–3 required, §2 makes the introduction 2.2 pages, and the title page names unconfirmed supervisors.
- Top risks: the harness/size/pretraining split is not identifiable as designed; Initial Results has no result on the thesis model and every number is n = 1 from a retired harness; §6.1 describes a Codex-via-OpenRouter comparison that can no longer be run.
- Most important fix: add the audited Qwen family Modality pilot (Max 1/4 → 4/4, Flash 1/4 → 1/4, 27B 0/4 → 2/4, single runs) to Initial Results, label n = 1, and rewrite §6.1 and H4.
- Real-time/Jev direction: keep out of the proposal; one reserve slide only.

## Evidence
- Draft proposal: docs/proposal/main.tex and docs/proposal/proposal-draft.pdf.
- Review: docs/proposal/committee-review-20261019.md. Board and scorecard claims were checked against raw traces in docs/research/board-claim-verification-20261019.md (run outcomes confirmed; corrections on Flash, Max's rule, the new harness and costs are folded into the review).

## Next
- Adam decides which of edits E1–E19 to apply to main.tex; E1, E3, E4, E5, E7, E8, E9 are marked must.
- Build the 11 slides from section 4 of the review.
