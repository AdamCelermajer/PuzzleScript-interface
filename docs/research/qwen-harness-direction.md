# Research direction: why Qwen 3.8-27B fails at PuzzleScript, and what fixes it

Recorded 2026-10-04 from Adam's notes. This doc supersedes nothing; it sets the
main thread of work and the M.Sc proposal.

## The shift

Main goal: make **Qwen 3.8-27B**, which currently does not solve the games,
solve them through a better harness. Do this by first *understanding why it
fails*. Three candidate explanations, studied together:

1. **Harness**: the 27B does not follow instructions or use the AVO tool
   protocol correctly. The failure may be the interface, not the reasoning.
2. **Size**: more parameters and compute may be what's required.
3. **Pretraining**: newer small models may have trained on similar
   environments.

### Pretraining hypothesis

Small models (GPT-6 Luna, DeepSeek V4.1 Flash) solve these games. That became
visible at the same time ARC-AGI-3 became popular, and these small models do
far better on ARC-AGI-3 than earlier large flagship models. A likely cause is
pretraining or post-training on similar interactive grid environments.
Question: was the Qwen 3.8 family trained on such environments? Proposed probe:
run **other Qwen 3.8 family models** and see whether *they* solve the games.

### Size hypothesis

If **Qwen 3.8 Max (~2T parameters)** solves them, compare its reasoning traces
with the 27B's. That shows whether success comes from size and compute, or
whether Max finds an easy route the small model misses.

### Harness hypothesis

Qwen 27B does not follow instructions correctly or use the AVO framework
properly. That alone may explain the failure. Run it on **baseline+** (the
simpler direct-player harness) as well as AVO.

## Repository evidence so far (as of 2026-10-04)

- Qwen 3.8-27B runs, 2026-09-30 → 2026-10-01, Modality + IceCrates, via
  OpenRouter (DeepInfra), AVO and then baseline-plus:
  - `output/workbench/20260930T172544-*`: AVO; Docker daemon was down (infra).
  - `20260930T183705-*`, `20260930T214729-*`: AVO; cancelled after
    `ClientConnectionResetError` (transport).
  - `20260930T224046-*`: baseline-plus; aborted with
    `IsolationError: Unapproved model tool: get_goal`. Corrected 2026-10-08:
    this was **not** a model hallucination. The Codex CLI began offering its
    own `get_goal/create_goal/update_goal` tools in the request's tool list,
    and the guard rejected them. The cause is infrastructure, not Qwen. The
    guard allow-list (`avo/analysis/request_guard.py`) has since been updated.
  - `20261001T000258-*`: baseline-plus; the model plays sensibly (coordinates,
    routing plans) for 36+ decisions, then fails. Needs a failure-reason read.
  - `20261001T084700-*`: baseline-plus recovery; cancelled (transport reset).
- Controlled tool-format probe, `output/diagnostics/qwen-notes-20260930T235031/`
  (`verdict.json`, `comparison.json`). Qwen 3.8-27B via OpenRouter:
  - With a JSON action **output schema enforced**: 0/2 note-tool calls. The
    model puts the note inside the JSON answer instead of calling the tool.
  - **Without** the schema: 2/2 calls, both namespaced and flat tool names.
  - Without the schema, note tools work end to end through the same SDK.

  So a harness choice (structured-output enforcement) silently disables tool
  use for this model. This is early evidence for the harness hypothesis and a
  ready-made "Initial Results" item for the proposal.
- Correction (2026-10-05): most "cancelled" runs were **stopped by Adam by
  hand** because they were going nowhere and costing money. The
  `ClientConnectionResetError` at the end of those logs is a side effect of
  the stop, not the cause. So the runs are real capability evidence:
  - Every 27B run cleared Modality level 1 and then stalled on level 2. That
    includes `20260930T224156`, which used max effort and 124 actions.
  - `20261001T000258` ended on a *harness* error both times:
    `Codex returned invalid action JSON`. The model wrote prose before a valid
    JSON object. On Modality it said "I've been stuck in a note loop"; on
    IceCrates it failed after 2 actions. The parser in
    `studies/codex_agent/session.py` (edited Oct 1 afternoon) now accepts both
    replies (verified 2026-10-08), and a bad reply triggers a correction turn
    instead of ending the run.
- Cost per run (from `codex_session.jsonl` usage): the 124-action max-effort
  run used about 10.4M input tokens (83% cached) and 0.11M output tokens.
  Input dominates, so price per input token matters most:
  - DeepInfra: about $1.8 per run.
  - Cerebras direct ($0.99 in / $1.49 out): about $10 per run. Its context is
    also 65k on OpenRouter, and late turns already reach ~70k.
  - Qwen Max ($2 in / $6 out): roughly $20 per run of this length, before
    cache discounts.
  - Only Modality has been tried properly; IceCrates and Knightoban have not.
  - Level-2 failure analysis vs GPT-5.5: `qwen27b-modality-failure-analysis.md`.
    The failure is hypothesis formation and revision, not protocol:
    - 27B never identifies undo or crate pushing;
    - it invents jump/trampoline/decoy theories;
    - it credits its accidental level-1 win to the wrong cause.
- 2026-10-08 runs pinned to DeepInfra all ended at exactly 30 actions with
  `Too many images in request: 31 > 30`, because the harness attaches one PNG
  per turn. Older unpinned runs reached 124 actions, so **they were not
  served by DeepInfra**; their provider and quantization are unknown.
  - Before the cap: IceCrates reached 2/6 levels and Knightoban 0/6 in 30
    actions (`output/codex_agent/qwen27b-deepinfra-*-20261008`).
  - Modality rerun: 0/4 in 30 actions.
  - The Modality precision rerun moved to Alibaba (first-party, no image cap):
    `output/workbench/20261008T112945-f705fa9a`.
- Providers: DeepInfra (wrongly assumed above to be the provider used so far) serves the 27B at **bf16**
  (not quantized), at $0.15/M in and $1.88/M out. That is already among the
  cheapest full-precision options on OpenRouter. Family models on OpenRouter:
  `qwen3.8-flash` ($0.47/M out), `qwen3.8-27b`, `qwen3.8-2.4t-a95b` (open Max
  weights, $6/M out), `qwen3.8-max-0902` ($6/M out), `qwen3.8-max-prime`.
- Comparison successes: DeepSeek V4.1 Flash (Modality/Knightoban/IceCrates,
  Enqueue), GPT-6 Luna (Enqueue), GPT-5.6 Luna (six-game pairs), GPT-6 Astra
  (three-game mechanics doc: `three-game-mechanics-demo.md`).

## Recommended plan of action

### Step 1: Failure taxonomy for Qwen 27B (now, ~1 week)

Get clean runs, then classify every failure.

- Make invalid tool calls *recoverable*: return an error observation and
  count it, rather than aborting. Keep the isolation guard for real escapes.
  Make sure transport resets retry instead of cancelling the run.
- Run 27B × {baseline+, AVO} × {Modality, IceCrates, Knightoban} × 3 repeats.
- Label each run's failure: *protocol* (bad tool / format), *perception*
  (misreads grid), *hypothesis* (wrong rule), *planning* (right rule, bad
  plan), *budget*. Use an LLM labeller, then hand-check a sample and report
  agreement.

Output: "where 27B breaks", which drives everything else.

### Step 2: Model sweep with a fixed harness (size × family)

Same harness, games and budgets for every model:

- Qwen 3.8 family: small → 27B → largest open → **Max**.
- Controls: DeepSeek V4.1 Flash, GPT-6 Luna (small and successful), a large
  older flagship (big but pre-ARC-AGI-3).

How to read the results:

- Success rises smoothly with size inside Qwen: **size** matters.
- Small non-Qwen models succeed where same-size Qwen fails: **training data /
  recipe** matters, not size.
- Qwen Max succeeds: compare its traces with 27B's (Step 4).

### Step 3: Pretraining probe (indirect; Qwen data is closed)

- Correlational: per model, compare PuzzleScript success with ARC-AGI-3
  score and release date relative to ARC-AGI-3's rise.
- Familiarity probes without play: ask models to describe or write
  PuzzleScript, and to predict the next frame of a grid transition. High
  zero-shot transition accuracy suggests prior exposure.
- Optional causal step: fine-tune a small Qwen (LoRA) on game trajectories
  from a successful model and measure the gain. Optionally use an open-data
  model (e.g. OLMo) to search the pretraining corpus for grid-game traces.

### Step 4: Harness interventions for 27B (the main contribution)

Ablate one component at a time, guided by the Step 1 taxonomy:

- Tool interface: fewer tools, strict schemas, recoverable errors.
- Observation format: ASCII or compact grid vs `visible-cell-v1` IDs; diffs
  between frames.
- Scaffolded memory and an explicit hypothesis ledger.
- Forced experiment loop: predict → act → compare.
- Code-tool support: the harness runs BFS and simulation for the model.
- Budget and turn structure.

Success metric: levels solved by 27B, plus protocol-error rate per turn.

### Step 5: Trace comparison (Max vs 27B, successful vs failed)

Apply the Step 1 behaviour taxonomy to all traces, including: controlled
experiments, falsification, solver writing, and repeating the same
hypothesis. This explains *why* success happens.

## M.Sc proposal

BIU CS format (department guideline PDF):

- Title page in Hebrew + English, with department, student and supervisor.
- Table of contents.
- Introduction: 1 page.
- Related Work: 2–3 pages.
- Research Goal: 1–3 pages.
- Hypotheses (optional): ≤ 2/3 page.
- **Initial Results: required**, 2–3 pages.
- Work Plan: 1–3 pages.
- Bibliography.
- Numbered pages, **≤ 10 pages excluding the bibliography**, written in LaTeX
  (Overleaf).

Reference example: Arbel Tepper's proposal (supervised by Yanai Elazar). It
uses a two-stage *correlational → causal intervention* structure, a taxonomy
annotated by an LLM classifier and validated by human agreement (Cohen's κ),
and preliminary results presented as tables. The plan above maps onto the same
pattern: Step 1–2 correlational, Step 3–4 interventional, Step 1/5 taxonomy.

Draft outline:

1. **Introduction.** LLM agents learning unknown game mechanics from
   interaction. Small models recently succeed while a capable 27B open model
   fails. Why?
2. **Related work.**
   - ARC-AGI-3; interactive reasoning benchmarks; PuzzleScript.
   - NVIDIA AVO; RSIAgent (arXiv 2609.15364).
   - Agent harness/scaffold studies; scaling laws for agents.
   - Data contamination and training-data attribution.
3. **Research goal.** Decompose small-model failure into harness, size and
   pretraining factors. Build a harness that makes the 27B succeed.
4. **Hypotheses.**
   - H1: protocol failures dominate.
   - H2: success within a family is size-monotone.
   - H3: cross-family gaps at fixed size reflect training exposure.
5. **Initial results.**
   - The PuzzleScript ARC-compatible environment and AVO framework.
   - Three-game mechanics recovery (Modality 4/4, Knightoban 6/6, IceCrates
     6/6).
   - Luna / DeepSeek-Flash successes.
   - Qwen 27B failure analysis (Step 1).
6. **Work plan.** Steps 1–5 with timeline.
7. **Bibliography.**

An older conference-style draft exists at
`tmp/pdfs/overleaf-conference-package/main.tex` (benchmark-focused); reuse its
environment and related-work text.
