# Diary figures: the Qwen 3.8 period (30 Sep – 21 Oct 2026)

Six slide figures (13.33 × 7.5 in, 150 dpi) for the diary entries of this period. Rebuild from the repo root:

```
uv run --no-project --with matplotlib python -I docs/research/diary-figures-20261029/qwen-era/make_figures.py
```

`make_figures.py` reads the run outputs (read-only) and writes `data.json` (every number plotted) and the PNGs.
Token conventions used throughout:

- **processed** = fresh + cached input tokens summed over every model request of the run; **generated** = output
  tokens including reasoning.
- OpenCode runs: every `step_finish` part in `raw/*.jsonl`. Codex runs: the last cumulative usage per thread
  (`codex_session.jsonl` for Baseline+, `app_server_events.jsonl` for AVO). Codex `inputTokens` already include
  cached tokens.
- No paid calls or grading were made for these figures; rule grades come from the existing `grading.json` files.

Rule-learning curves for the 21 Oct runs are in `docs/research/rule-learning-20261028/` and are not repeated here.

## fig1_quantization.png

- **Diary entry:** `2026-10-21-premise-revised` (Q2, quantization).
- **Numbers:** rules correct of 21 (3 games × 7): 16-bit (DeepInfra) 17, 8-bit (Chutes) 11, 4-bit (ModelRun) 12; wrong
  rules held at the stop 2 / 5 / 3. Tokens processed per game 2.48M / 2.42M / 10.19M (4-bit 4.1× the 16-bit arm),
  generated 75k / 54k / 225k. Cost per game at host list price $0.34 / $0.14 / $1.51; levels 3·2·2, 1·2·1, 2·1·1;
  reasoning collapsed into a repeated word in 3 of 3 4-bit games, 0 elsewhere.
- **Caveats:** host and precision are confounded (one host per arm), 3 games per arm, all stopped by hand at ~35 min.
  The 4-bit cost is the Thursday page's figure (`docs/research/thursday-20261022.html`): ModelRun's list price is not
  stored in the repo, so it was not recomputed. 16-bit/8-bit costs recomputed from tokens with the DeepInfra and
  Chutes prices of the Thursday notes and match the page. At NanoGPT's own 27B price the per-game costs would be
  $0.26 / $0.33 / $0.60 (in `data.json`). The 16-bit row says 3·2·2 levels, not the page's 2·2·2: game 1's 172nd
  action completed level 3 and ended the game before `transitions.jsonl` recorded it (`grading.json` notes).

## fig2_qwen_family_modality.png

- **Diary entry:** `2026-10-13-qwen-family-modality` (the NanoGPT rows are from `2026-10-15-qwen-modality-claim-audit`).
- **Numbers:** Baseline+ on OpenRouter/Alibaba, 100 actions: 27B 0/4 (11.9M tokens processed, 285k generated),
  Flash 1/4 (16.6M, 169k), Max 1/4 (7.6M, 56k). Baseline+ on NanoGPT: 27B 1/4 in 386 actions (43.3M), Flash 2/4 in
  296 (29.3M, 1.2M generated). AVO final solvers: Max 4/4 in 265 actions on 7.3M tokens; 27B 2/4 (33.8M); Flash 1/4
  (22.2M); NanoGPT 27B solver errored, 0/4 (26.0M).
- **Caveats:** one run per row; Baseline+ and AVO differ in tools, budgets and instructions (claim audit), so rows are
  not a matched comparison. All rows ran the old Codex harness. The 27B OpenRouter Baseline+ row is the 8 Oct
  Alibaba run (`20261008T112945`), the same setup as the 13 Oct Flash/Max runs. AVO tokens include the research and
  optimizer sessions; the Flash AVO row is the recovery campaign (`20261013T173422`).

## fig3_vast_frameworks_games.png

- **Diary entry:** `2026-10-21-premise-revised` (3 frameworks × 3 games); also fits `2026-10-21-vast-self-hosted-qwen`.
- **Numbers:** agent-driven player (Harness² base1): Modality 3/4 in 1000 moves (30.3M processed, 784k generated),
  IceCrates 6/6 in 320 (19.6M), Knightoban 6/6 in 326 (18.9M). Turn-based Baseline v4: 3/4 in 226 (25.0M), 3/6 in
  271 (37.3M), 0/6 in 451 (56.6M, the largest run of the period). AVO v2 research sessions: 2/4 in 93 (14.8M), 5/6 in
  101 (18.4M), 4/6 in 415 (24.7M); no AVO solver was scored.
- **Caveats:** one run per cell; everything was stopped at 18:14, so Baseline v4 and AVO lines end at the stop, not
  at a budget. AVO levels are the research session's running score (`evidence.jsonl` task_evaluated), not a solver
  score. base1 tokens are the player rollout only (coach tokens are in fig4). Shortest totals 263 / 90 / 164 are the
  sums of the per-level BFS references in `premise-review-20261021.md`.

## fig4_same_game_coaching.png

- **Diary entry:** `2026-10-21-premise-revised` (same-game coaching).
- **Numbers:** IceCrates: base1 6/6 in 320 moves (19.58M tokens), inv1 6/6 in 90 (= shortest 90, 1.37M), dom1 3/6 in
  27 when cut (0.21M); coach sessions 7.6M. Knightoban: base1 326 (18.94M), inv1 177 (1.75M), dom1 163 (0.75M,
  reference shortest 164); coach sessions 18.9M. Per level, base1's excess sits in IceCrates levels 4–5 (113 and 144
  moves vs 29 and 8) and Knightoban levels 1–3 (109/55/62 vs 20/10/33).
- **Caveats:** coached rollouts replay the same game, so they measure reuse of base1's knowledge, not transfer (DOM
  copied base1's model and solver, including its wrong undo rule). One rollout per arm. Coach tokens are summed over
  all improver sessions of the run, not split INV vs DOM. Modality's coaching produced no harness before the stop and
  is omitted.

## fig5_toolcall_probe.png

- **Diary entry:** `2026-10-21-premise-revised` (Q1, OpenCode vs Codex).
- **Numbers:** plain tool declarations: 27B 48/48 proper calls (Chat 16/16, Responses 16/16, flat 16/16), Flash 8/8;
  namespaced (as Codex declares MCP tools): 27B 0/16 (4 written as text, 12 no call), Flash 0/8 (5 text, 3 no call).
  Codex's real 15 Oct request replayed on Responses: 0/8 (7 malformed-call errors, 1 no call); the same conversation
  on Chat: 6/8. 96 calls, 542k tokens, $0.11 in total.
- **Caveats:** counts are straight from `output/thursday/q1/probes.jsonl`; the Thursday notes report the replays as
  0/7 and 6/6 (they leave out the no-call replies). NanoGPT behaviour changed over October (namespaced calls half-
  worked earlier), so this is a 21 Oct snapshot.

## fig6_period_27b_modality_tokens.png

- **Diary entry:** `2026-10-20-harness2` (turn-by-turn vs self-driven player); also usable on
  `2026-10-04-qwen-research-direction` (token cost) or `2026-10-21-premise-revised` (context bloat).
- **Numbers:** 27B on Modality, tokens processed per move: turn by turn 84k (30 Sep, 1/4 in 124), 119k (8 Oct, 0/4 in
  100), 112k (15 Oct, 1/4 in 386), 84k (20 Oct OpenCode, 1/4 in 97), 110k (21 Oct v4, 3/4 in 226); agent-driven 28k
  (20 Oct, 3/4 in 200), 19k / 23k / 45k (21 Oct quant 16/8/4-bit), 30k (21 Oct self-hosted, 3/4 in 1000). Right panel:
  65 Qwen 3.8 runs with recorded usage, 901M tokens processed and 17.8M generated in total (OpenRouter 22 runs 314M,
  NanoGPT 19 runs 221M, self-hosted 24 runs 366M).
- **Caveats:** runs differ in harness, provider, budget and stop time, so this is a descriptive timeline, not a
  controlled comparison; the 21 Oct v4 turn-based run also reached level 3. The right panel covers
  `output/workbench/<job>/run-NNNN` folders dated 30 Sep – 21 Oct plus the 8 Oct `output/codex_agent/qwen*` runs;
  smoke folders are left out, and the 30 Sep AVO campaigns recorded no usage, so they are missing.

## Not built

- **Self-hosted server throughput** (MTP 816 vs 572 tok/s, prefix reuse 15.9 s → 2.8 s, in
  `output/thursday/vast/checks-*.json`) for `2026-10-21-vast-self-hosted-qwen`: not one of the requested result
  figures, left out to stay within six.
- **Harness² per level** (`20261021T235821`, `2026-10-21-harness2-per-level`): the run was stopped early; nothing to
  plot yet.
- **4-bit cost from tokens:** needs ModelRun's list price, which is not in the repo (see fig1).
