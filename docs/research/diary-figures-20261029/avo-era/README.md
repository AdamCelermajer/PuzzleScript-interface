# Diary figures: the AVO era (July to late September 2026)

Five slide figures (13.33 × 7.5 in, 150 dpi) for the Codex direct-player baselines and the AVO campaigns.

Rebuild everything from the run folders (read-only) with:

```
uv run --no-project --with matplotlib python -I docs/research/diary-figures-20261029/avo-era/make_figures.py
```

`--plot-only` redraws from `data.json` without rereading the runs. `data.json` holds every extracted number: per-evaluation levels, cumulative tokens and hours for each campaign, the per-run results of the direct player, and the deduplicated token overview.

**Tokens.** "Tokens" means total tokens: input tokens, including cache hits, plus output tokens (reasoning included). The count covers every model session found in a run folder, which means the outer optimizer and all of the inner research agents. Sources: Codex app-server `thread/tokenUsage/updated` events, taking the last cumulative value per thread (`app_server_events.jsonl` or `agent_events.jsonl`); `turn.usage.total` in the direct player's `codex_session.jsonl`; OpenCode `message.updated` usage in `opencode_events.jsonl`; and `provider_usage.json` for the Aug 23 OpenRouter runs. Resumed campaigns copy earlier sessions, so threads are deduplicated by thread id. In the cumulative-token curves, the token count at an evaluation is the sum, over all threads, of the last usage recorded before that evaluation's `recorded_at`.

---

## fig1_midas_levels_vs_tokens.png

**Diary entry:** `2026-08-28-solver-evaluation` (it also fits `2026-08-25-midas-and-outer-loop`).

**Key numbers.** When the agent played Midas itself, it reached 8/15 levels. The Aug 25 Sol/Sol campaign `midas-live-v01` got there after 5 whole-run evaluations and 44.5M tokens; Aug 27 `midas-solver-v04` got there in one evaluation and 13.4M tokens. Once the score became the learned solver replayed from a fresh reset, the best result was 6/15. That was `midas-outer-evidence-luna-medium-sol-high-20260828T210529` (Luna medium inner, Sol high outer): 30 evaluations, 82.5M tokens at the last evaluation (82.9M in total), about 4.1 h. The other five fresh-solver campaigns ended at 2 to 4 of 15 levels after 13.6M to 39.6M tokens. The single-agent runs and the 1-evaluation campaigns sat at 4/15 with 6.0M to 24.3M tokens. All Midas runs together logged 389.8M tokens.

**Caveats.**
- Orange (Aug 25 to 27) scores the agent's own play with its tools, using the `TaskEvaluation.fitness` owner. Blue (Aug 28 to 31) scores only the learned solver. The two measure different things.
- `midas-full-v01` (4/15) has no token log, so it is not drawn.
- Eleven Aug 27 and 28 campaigns recorded no evaluation: `midas-solver-v01/v02`, `clean-v05..v07`, the model-first runs, and Spark. They appear only in fig5.

## fig2_games_levels_vs_tokens.png

**Diary entry:** `2026-09-22-astra-deepseek-campaigns` (it also fits `2026-09-08-six-game-avo`).

**Key numbers.**
- **Sep 8, Astra low outer and Luna high inner.** Modality 4/4 at 16.5M tokens (3 evaluations), Purple 4/4 at 25.4M (4), Magnetic 4/4 at 14.7M (2), and Knightoban 6/6 at 72.0M (8). Atlas Shrank reached 4/12 at 57.7M (68.9M total) and Enqueue 2/14 at 45.8M (85.0M total).
- **DeepSeek V4.1 Flash.** Modality 4/4 at 29.4M (1 evaluation), Knightoban 6/6 at 72.2M (1), IceCrates 6/6 at 39.6M (1), and Enqueue 8/14 at 212.4M (3). The Enqueue campaign totals 247.3M, and 312.1M including the unique sessions of the first attempt, `20260924T010548-df1831ea`.
- **OpenCode muse-spark.** Modality 3/4 after 9 evaluations and 82.4M tokens.
- **No token log.** Astra/Astra (Sep 22) reached IceCrates 6/6, Portal Ban 5/5, Enqueue 8/14 and Atlas 6/12. GPT-6 Luna/Sol (Sep 24) reached Enqueue 8/14 after 20 evaluations.
- **Comparison.** On every game both played, DeepSeek matched the best GPT level. Only two games have token logs for both: on those DeepSeek used 1.8× the tokens on Modality (29.4M vs 16.5M) and 1.0× on Knightoban (72.2M vs 72.0M).

**Caveats.**
- The Sep 8 curves follow the final folder of each chain: `r7/repairs/*-04` for Modality, Purple and Magnetic, and continuation `r3` for Knightoban, Atlas and Enqueue. The continuation cumulative tokens include the copied earlier sessions. Tokens from aborted attempts r1 to r6 are not in the curves.
- Sep 8 Enqueue spent 39M tokens after its last evaluation; the diary notes evaluation-service errors.
- The DeepSeek Knightoban result is the rerun only. The first attempt, `40bfa276/run-0002` (21.2M tokens), failed on the isolation guard.
- The DeepSeek Enqueue resume ran its inner agent at medium effort, not max.
- Two of the DeepSeek jobs are marked failed in the catalog only because the final report is missing; their evaluations solved the game.

## fig3_sep14_world_model_modes.png

**Diary entry:** `2026-09-14-consolidation-and-astra-luna`.

**Key numbers.** Evaluations until the fresh solver first won, final-only vs between-hypotheses:

| Game | final-only | between-hypotheses |
|---|---|---|
| Feeling like filling | 4 (7.5M tokens) | 4 (7.3M) |
| Mowing | 7 (13.5M) | 4 (8.3M) |
| Fatigued square maze | 5 (6.7M) | 3 (6.9M) |
| 2D whale world | 10 (≥13.6M) | 9 (≥15.2M) |
| Compressed, Luna xhigh rerun | 6 | 10 |
| Using pushers, Luna xhigh rerun | 9 | not won (3/4 after 8) |

Between-hypotheses was faster on 3 games, final-only on 2, and one game was a tie.

**Caveats.**
- Compressed and Using pushers first ran with Luna medium and stayed unsolved after 10 evaluations per mode: Compressed 0/4 in both modes, Using pushers 1/4 in both. The bars show the separate Luna xhigh / Astra xhigh rerun, which is not the same setting.
- Tokens exist only for the first batch. The storage-recovery and usage-recovery resumes ran with compact tracing (`app_server_events: disabled`), so the whale-world figures are lower bounds from the first segment only, and Compressed and Using pushers have none.

## fig4_direct_player.png

**Diary entry:** `2026-09-04-direct-player-baselines` (the Modality row belongs to `2026-09-07-game-selection-and-modality`).

**Key numbers.**
- **Sokoban, Sep 4.** Three of the ten complete runs won the whole 2-level game. Luna high baseline cleared level 1 at action 33 and won at 49; Luna high baseline+ cleared it at 42 and won at 58; GPT-5.5 medium baseline+ with fixed notes cleared it at 58 and won at 74. The other four GPT-5.5 medium runs ended 0/2 at 100 or 200 actions.
- **Sokoban, Sep 5.** GPT-5.5 xhigh baseline+ cleared level 1 at action 86 and ended 1/2 at 100 actions, using 13.3M tokens. Both Luna medium arms ended 0/2 at 150 actions, with 6.8M (baseline) and 6.4M (baseline+) tokens.
- **Modality, Sep 7.** GPT-5.5 high baseline+ cleared levels at actions 17, 56 and 126, and stopped at 3/4 after 293 of its 1,000 actions, using 43.5M tokens.

**Caveats.**
- **This changes what the diary says.** The runtime did not count the final level when a game was won until `c6a701a` (Sep 14; `completedLevels()` now returns `winLevels` on win). The catalog and the Sep 4 diary entry report the three winning runs as "1/2 levels, task goal reached". Their transcripts show level 1 cleared mid-run, followed by a `WIN` state on level 2, so the figure counts them as 2/2. The same applies to the Aug 24 AVO Sokoban runs, which were `success: true` with "1/2".
- Token usage exists only for runs from Sep 4 23:37 onward. Earlier Codex SDK transcripts did not store usage.
- Eleven attempts are left out: 9 aborted on the isolation guard or SDK start-up (`exec`, `tool_search` and `update_plan` were flagged as unapproved tools), and 2 stopped without a result. The diary's "Selected model is at capacity" error is not in any of these folders.
- The Modality run has no `result.json`, so its numbers come from the last line of `transitions.jsonl`.

## fig5_tokens_overview.png

**Diary entry:** `2026-09-22-astra-deepseek-campaigns`, the entry that closes the period. It works as an overview slide for any entry in the period.

**Key numbers.** 1.476B tokens were logged across the 72 runs and campaigns that have usage records. 1.409B of those (95.5%) were cache hits; output was only 14.2M tokens (1.0%). By group:

| Group | Tokens | Runs | Won |
|---|---|---|---|
| DeepSeek Flash | 484.7M | 9 | 3 |
| Luna/Astra, Sep 8 to 14 | 435.1M | 27 | 10 |
| Midas evolution | 356.6M | 21 | 0 |
| OpenCode | 87.2M | 1 | 0 |
| Direct player | 78.5M | 6 | 0 |
| Sol single-agent, Midas | 33.2M | 5 | 0 |
| Opus 5 fast, Aug 23 | 0.31M | 3 | 0 |

The largest single campaign is the DeepSeek Enqueue resume, at 247.3M tokens.

**Caveats.**
- Each model session (thread) is counted once, assigned to the final campaign of its chain first. Aborted segments and earlier attempts of a chain are separate dots, holding only their unique sessions.
- "Won" means the fresh solver solved the game (AVO) or the game was won (direct player). The three Sokoban runs that won (Sep 4) have no token log, so they are missing here.
- Runs with no usage records at all are left out: the Jul 16 smoke runs, the Aug 23 Sol runs, the Aug 24 Sokoban runs, the Sep 4 runs before 23:00, the Sep 14 recoveries, Sep 22 Astra and Sep 24 GPT-6 Luna. Those last ones ran with compact tracing. Their `model_requests` captures hold only request deltas (`previous_response_id`), so tokens cannot be rebuilt from them.

---

## What could not be built

- **Tokens for the Sep 22 Astra/Astra and Sep 24 GPT-6 Luna/Sol campaigns, and the Sep 14 recoveries.** No usage was recorded. Compact tracing disabled the app-server events, and the request captures do not contain context sizes.
- **Tokens for the Jul 16 smoke runs, the Aug 23 Sol runs, the Aug 24 Sokoban runs and most Sep 4 direct runs.** Their logs predate usage capture.
- **A wall-time axis.** Resumed chains include long pauses (Sep 8 Knightoban spans 14.9 h, including the break between r7 and the continuation), so cumulative tokens are the x axis instead. Hours since the first logged request are still stored per evaluation in `data.json`.
- **The Jul 26 BFS reference solutions.** These are not agent runs; `experiement/bfs_solver/REPORT.md` already has the numbers.
