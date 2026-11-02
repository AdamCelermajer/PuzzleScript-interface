# Section 4.5 (the self-hosted experiment): keep it in the proposal?

For the meeting with Gal and Yoav.

## What it is
- 21 Oct 2026, one day, about $25 of GPU time.
- Qwen 3.8 27B, 8-bit weights, 4×RTX 5090, OpenCode.
- Three conditions (agent-driven, turn-based, AVO) × three development games; 1000-move budget; one run per cell.
- About 2 pages and 3 tables (Tables 5–7). With it, Initial Results runs 4 pages; the limit is 2–3.

## What it shows
1. Agent-driven play solved Knightoban 6/6 and IceCrates 6/6, and Modality 3/4.
2. How: the model wrote a breadth-first solver over its own rules and played its plans. Where its rules were right, play was optimal or one move off.
3. Extra moves come from learning (early levels) or a wrong belief (IceCrates water).
4. The failure is the hidden rule: on Modality it encoded the floor-colour rule as 49 local walls, and its planner found no path on level 4.
5. Turn-based play used fewer moves on Modality 1–3, but never found Knightoban's lift mechanic in 451 moves.
6. Harness² coaching halved the moves on the solved games, by copying the found answer into a skill. It produced no edit on Modality.
7. AVO: no attempt was scored in 2 hours; the solver requirement, not the play, limited it.

## For keeping it
- It is the only evidence that the premise holds: the small model learns visible mechanics and solves whole games.
- It pins down the open problem (hidden rule) and motivates H1 (the solver), H2 (the Modality impasse) and H3.
- It shows the platform works end to end.

## Against
- Single runs from one day, with several cells stopped: a pilot, not a result.
- It puts Initial Results over the page limit.
- The coaching and AVO parts belong to a framing the objective no longer has.
- Moves per level and run folders are thesis-level detail.

## Options
- A. Keep it as is, and cut elsewhere.
- B. One paragraph plus Table 5; the rules and coaching tables move to the thesis.
- C. Three sentences of findings that motivate the hypotheses, cited as a pilot.

## Questions
- Is a one-day, single-run pilot acceptable as Initial Results?
- Is coaching still part of the thesis?
- Which table, if any, stays?
