---
date: 2026-10-21
title: 3 frameworks × 3 games on the self-hosted 27B; the premise changed
threads: [qwen-harness, harness-revamp]
runs: [output/workbench/20261021T144508-vast-fp8-harness2-153a4dc2, output/workbench/20261021T162323-vast-fp8-baseline-v4-6767db38, output/workbench/20261021T160936-vast-fp8-avo-v2-b994ed09, output/workbench/20261021T130008-thu-quant-bf16-deepinfra, output/workbench/20261021T130008-thu-quant-fp8-chutes-036, output/workbench/20261021T130008-thu-quant-fp4-modelrun-6]
commits: []
docs: [docs/research/diary-figures-20261029/qwen-era/fig3_vast_frameworks_games.png, docs/research/diary-figures-20261029/qwen-era/fig4_same_game_coaching.png, docs/research/diary-figures-20261029/qwen-era/fig5_toolcall_probe.png, docs/research/thursday-20261022.html, docs/research/premise-review-20261021.md, docs/research/harness2-per-level-feasibility.md, docs/research/experiment-spec-20261021.md, docs/research/thursday-20261022-realtime.html, docs/research/diary-figures-20261029/qwen-era/README.md]
reconstructed: false
---
## Did
- Q1 (OpenCode vs Codex): traced Codex's 15 Oct failure to NanoGPT dropping namespaced tool calls (11/25 returned as text; direct probes 48/48 plain vs 0/24 namespaced; `studies/thursday/probe_tool_calls.py`).
- Q2 (quantization): 3 pinned hosts × 3 Modality games, graded rule by rule (`output/thursday/quant/*/grading.json`): 16-bit 17/21 rules, 8-bit cheapest per correct rule but most wrong, 4-bit 6–10× costlier with broken text. Moved to one self-hosted model to remove the host variable.
- Ran 3 frameworks × 3 games on `vast/q3.8-27b-fp8` (1000 moves, max thinking, 9 sessions): Harness² (base1 = agent-driven player, empty harness), turn-based Baseline v4, AVO v2 (solver-scored). Stopped everything at 18:14 and stopped the vast instance (not destroyed).
- Fixed on the way: Baseline turn protocol (action+note in one reply never ended the turn, then a note loop) → `act.py` action tool ends the turn; simplified Baseline prompt; `world_model.md` requested every 100 moves and at each level; AVO player sees one current board (`history --move N` keeps all engine-step boards); AVO optimizer told not to write simulators, first candidates may hold notes only; NanoGPT body pinning; per-run Stop + "stopped" label, Failed/stopped tab, Runs page defaults to Active, run-page prompts and file diffs, Harness² coach-session diffs, Remove on paused Results rows.
- Graded rules per run with Haiku (`output/thursday/vast/watch/`); wrote the premise review and the per-level feasibility study.
## Found
- Agent-driven 27B: Knightoban 6/6 in 326 (109/55/62/41/31/28 vs shortest 20/10/33/41/32/28), IceCrates 6/6 in 320, Modality 3/4 in 1000. It writes its own BFS solver and plays near-optimally once its rule model is right. Turn-based v4: Modality 3/4 in 226 (155 for L1–3 vs 404 agent-driven), IceCrates 3/6, Knightoban 0/6 in 451. AVO: no attempt scored in 2 h (Knightoban solver self-check: 500×ACTION5).
- Modality's floor-colour rule (rules 3/4/6) was never found by any run; it is encoded as per-edge "hidden walls". Wrong beliefs persist untested (Knightoban undo, IceCrates water). Agent-driven players don't keep `world_model.md` current; the turn-based one does when asked at fixed points.
- Same-game coaching: Knightoban dom1 163 (optimal) / inv1 177 vs 326; IceCrates inv1 90 (optimal) vs 320. DOM wrote base1's model + solver into a skill, including base1's wrong undo rule. Modality coaches hit the 64k reply cap; nothing was played before the stop.
- OpenCode context overflow (compaction ignores thinking tokens) killed one AVO attempt and hit 7 other sessions, which recovered. Not fixed.
- The 27B coach at max thinking takes 40–60 min per session; one turn-based step took 63k tokens / 15 min.
## Decided
- The premise "the 27B fails" is dropped; the question is under which conditions it learns a game and how a hidden rule can be revised (hypotheses H1–H6 in the Thursday page).
- Harness² runs per level with an escalating budget inside each level (Adam); two sessions build it (shared per-level infrastructure; Harness² loop). Baseline stays turn-based with `act.py`.
- 8-bit weights + 8-bit KV for all self-hosted runs. The levels-scored AVO variant is built but unlaunched.
## Next
- Review the Thursday page, the real-time Jev+LLM page and the refocused proposal draft (`docs/proposal/CHANGES-20261021.md`); commit the day's work.
- Per-level infrastructure, then Harness² per level; H2/H1 on Modality; repeats (3 per cell).
- Decide whether to destroy vast instance 57041133 (storage still charged).
