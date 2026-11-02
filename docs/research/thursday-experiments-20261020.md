# Thursday experiments (20–22 Oct 2026): what limits a small model at learning a game?

Goal: a set of conclusions, each backed by repeated, controlled runs, for Thursday.
Each experiment changes one factor; everything else is fixed.

## Fixed in every run

| setting | value |
|---|---|
| framework | `baseline` (no outer method) unless the experiment says otherwise |
| CLI | OpenCode 1.14.19 in Docker, `output_token_max` 64k (recorded in `session.json`) |
| provider | NanoGPT |
| image input | on, verified per session (`image_input` in `session.json`), except experiment 3 |
| budget | 200 game actions; wall cap 4 h as a safety net only (runs that hit it are reported) |
| game | Modality (`ps_modality-v1`, 4 levels) unless the experiment says otherwise |
| effort | `medium` requested; OpenCode sends no effort for Qwen ids, so Qwen thinking is set by the `:thinking` model id |
| repeats | 3 per cell for the main contrasts, 2 for the costlier ones |

## Experiments

| # | question | cells | runs |
|---|---|---|---|
| 1 | **Who drives the game, and does required note-taking help?** Qwen 3.8 27B-thinking | driver {controller, agent} × notes {off, on} | 4 × 3 = 12 |
| 2 | **Does the driver matter less for stronger models?** | driver {controller, agent} × model {Qwen 3.8 Max-thinking, GPT-6-luna}, notes off | 4 × 2 = 8 |
| 3 | **What does the picture add?** 27B, agent, notes off | image off (grid text only) vs experiment 1's image-on cell | 3 |
| 4 | **Do coach-written harness files help a fresh player?** 27B, agent, notes off | INV harness, DOM harness (from the Harness² run of 20 Oct) vs experiment 1's no-harness cell | 2 × 3 = 6 |
| 5 | **Does it hold beyond Modality?** 27B, notes off | driver {controller, agent} on two more easy push games (Purple, Mowing), plus the INV harness on each | 3 × 2 × 2 = 12 |

Experiments 1–2 run first (tonight); 3–5 need two small options in the code
(`image` on/off and a harness folder for the agent driver) and run Wednesday.

## Measured per run

- levels completed in 200 actions; the action at which each level was completed
- wall time; tokens (fresh input, cached input, output, reasoning) and cost at NanoGPT prices
- the final world model, graded blind against the game's real rules (Modality: action map
  including undo, white/dark/grey movement rule, push rule, goal = crate on target)
- failure mode (e.g. wrong rule kept, budget spent exploring, stuck on one level)

## Cost and time estimate (from 20 Oct runs)

| model | cost per 200-action game | time per game |
|---|---|---|
| Qwen 3.8 27B-thinking | ≈ $0.50 | 1–2.5 h |
| Qwen 3.8 Max-thinking | ≈ $5 | to measure |
| GPT-6-luna | ≈ $0.30 | to measure |

Total ≈ 41 runs, ≈ $40. With 8–10 runs in parallel, experiments 1–2 finish overnight and
3–5 by Wednesday night, leaving Thursday morning for analysis.
