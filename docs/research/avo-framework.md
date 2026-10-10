# AVO: the framework, NVIDIA's version and ours

Research note. Two halves: what **AVO** means outside this repo, and what
`avo/` in this repo actually implements. Code claims carry `path:line`
references. Artifact claims were read from `avo/output/evolution/*`.

## 1. What AVO is (external)

**AVO = Agentic Variation Operators**, NVIDIA Research, arXiv 2603.24517
(submitted 25 Mar 2026, [abstract](https://arxiv.org/abs/2603.24517)). The paper's
definition is the precise one:

> Agentic Variation Operators (AVO) are a new family of evolutionary variation
> operators that replace the fixed mutation, crossover, and hand-designed
> heuristics of classical evolutionary search with autonomous coding agents.
> Rather than confining a language model to candidate generation within a
> prescribed pipeline, AVO instantiates variation as a self-directed agent loop
> that can consult the **current lineage**, a **domain-specific knowledge base**,
> and **execution feedback** to *propose, repair, critique, and verify*
> implementation edits.

So the paper's target is GPU-kernel evolution on B200 (7 days continuous,
>500 directions, up to +3.5% over cuDNN and +10.5% over FlashAttention-4), and
its claim is specifically that the agent is *elevated from candidate generator
to variation operator*. The four verbs — **propose, repair, critique, verify** —
are the operational content of "variation".

The later [NVIDIA developer blog](https://developer.nvidia.com/blog/nvidia-avo-reaches-100-on-arc-agi-3-demonstrating-a-frontier-level-general-purpose-architecture-for-long-horizon-autonomous-agents/)
reports the transfer to interactive reasoning: **100.00 RHAE on the ARC-AGI-3
public set** (25 environments, 183 levels) with Claude Opus 5, in 6,624
environment actions — about 12% fewer than VISTA on the same levels. The
framing that matters there:

- AVO is a **general-purpose coding agent**, not an ARC system. The same loop
  was pointed at GPU-kernel optimization and at ARC-AGI-3; only the
  environment tools and evaluation changed.
- Two mechanisms carry long horizons:
  - **Persistent memory** — prior implementations, evaluation results,
    compiler/profiler output and accumulated reasoning survive context
    boundaries, so the search resumes instead of being rebuilt.
  - **A supervisor** — watches the *trajectory* for stagnation or repeated
    unproductive cycles and redirects the main agent.
- Observation modality on ARC-AGI-3 was **text-only**: an exact 64x64 text
  grid, no images or image tokens. Available actions were given without any
  description of rules or goals.

The headline claim is a systems claim: **model eval != agent eval**. Opus 5
scores ~30% on ARC Prize's own model-level evaluation; inside the AVO system it
reaches 100% RHAE. The blog is explicit that this is *not* a controlled
ablation (AVO differs from VISTA in backend, observation representation, memory
and context management), and that the results cover the public set only — not
the semi-private or private competition sets.

Sources: [arXiv 2603.24517](https://arxiv.org/abs/2603.24517),
[NVIDIA developer blog](https://developer.nvidia.com/blog/nvidia-avo-reaches-100-on-arc-agi-3-demonstrating-a-frontier-level-general-purpose-architecture-for-long-horizon-autonomous-agents/),
[ARC-AGI-3 methodology](https://docs.arcprize.org/methodology).

## 2. What our `avo/` is

`avo/__init__.py:1` — "Self-contained general-purpose Agentic Variation Operator
framework." It is a **from-scratch reimplementation of the architecture**, not a
port of NVIDIA code, with PuzzleScript as the environment under study.

The contract is stated as prose in `avo/SPEC.md` and as this schema in
`avo/evolution/README.md:9`:

```text
x_i        = STRATEGY.md + inherited seed
R_i        = one fresh, 500-action research run using x_i
V_i        = up to two provisional fresh solver self-checks available to the inner player
S_i        = solver.py alone in a second fresh environment, with its own action budget
f(x_i)     = levels_completed(S_i)
```

The central design decision: **the deliverable is an executable artifact, not a
transcript.** The player researches freely, then must leave behind a
`solver.py` that wins from a fresh reset with no Codex reasoning available.
Research progress is explicitly *diagnostic only* (`avo/evolution/README.md:77`).
That closes the obvious loophole of "the model played well with the harness
helping it."

## 3. Actor topology

Three trust domains, not one agent:

| Actor | Identity | Privileges |
|---|---|---|
| Inner player | persistent Codex session, one per `x_i` | workspace writes, environment actions **only** through the gateway |
| Outer optimizer | separate persistent Codex session | candidate registration/forking/evaluation, inspection of full evidence, **no** environment actions |
| Fresh evaluator | framework subprocess, no Codex | owns the fresh game and all real action execution |
| File tool server | `avo/core/tool_gateway.py:510` | thread inside the controller; serves RPC, projects results through `ModelView` |
| Capture proxy | `avo/analysis/model_proxy.py` | loopback proxy that records exact model requests |

Transport is **atomic files**, not a socket — deliberate, because sandboxed
agents have no network. The agent's `avo_tool.py` writes
`.avo_rpc/<uuid>.request.json`; `FileToolServer._serve` polls the directory,
unlinks the request, dispatches to the gateway, and writes
`.response.json` (`avo/core/tool_gateway.py:549-582`). The CLI is generated as a
string constant and injected into the workspace (`tool_gateway.py:420-526`)
together with `AGENT_INTERFACE.md` and `MISSION.md`.

`ModelView` (`avo/core/model_view.py`) sits on the response path and strips
identity: `game_id`, `game_name`, `legend`, `source_url`, profile settings and
transcript keys are dropped from anything the model sees. Rendered frames are
re-validated (regular file, no symlink/junction in any path component, genuine
PNG signature, inside a permitted root) and staged byte-for-byte under a
sha256 name in `observations/`.

## 4. The agent loop and its tools

The full model-facing surface is `AGENT_INTERFACE`, `avo/core/tool_gateway.py:375`:

```text
observe  mission  history  archive .  evaluate_solver --max-actions N
probe ACTION_ID --rationale "..."     reset --reason "..."
checkpoint --label "..."              restore CHECKPOINT_ID
acknowledge_supervisor "..."          status     finish "reason"
```

Notable properties:

- `probe` accepts an optional `rationale`; it is recorded next to the real
  transition as an `agent_decision` (`tool_gateway.py:305`), but it is **not
  validated** — `--rationale` defaults to `""` (`tool_gateway.py:461`). By
  contrast `reset`'s `--reason` is `required=True` and checked non-empty
  (`:463`, `:186`). So the framework records stated intent where the agent
  offers it, and only forces it for resets.
- `checkpoint`/`restore` exist so the agent can fork a single state and compare
  alternative continuations without replaying a prefix. Checkpoint ids are
  opaque counters (`cp_001`, `tool_gateway.py:210`) and restore does not consume
  an action.
- `reset` requires a reason and starts a new episode **without erasing prior
  evidence**.
- `finish` stops the run but is explicitly not a success claim — only the
  profile's task evaluator decides that (`tool_gateway.py:413`).

Budgets are enforced in one place, `_check_environment_budget`
(`tool_gateway.py:175`): step count and wall clock. `probe` and `reset` both
increment `environment_steps`.

### The inner player's opening instruction is a methodology, not a task

`CodexOAuthAgent` sends one long first turn to an inner session
(`avo/client/codex_oauth_agent.py:23`), which is effectively a research
protocol. It instructs the player to: switch the solver into a *bounded
discovery phase*; reproduce the plateau from the nearest checkpoint or a
replayed action prefix; find the **earliest predicted-versus-observed
transition mismatch**; treat every rule, state key and plan as falsifiable;
build a frontier from real transitions for every legal action and encode
**untried outcomes as unknown, never as walls, no-ops or inferred
equivalences**; preserve histories when identical observations may hide
different latent states, then add the smallest temporal feature or belief-state
distinction that predicts different successors; audit state cloning and
visited-set pruning against that distinction; choose experiments by expected
information gain, prioritising contradiction, unknown-frontier expansion and
state-alias disambiguation over predicted progress; record each experiment
signature and never repeat it unless the model or context changed; invalidate
plans at their first discrepancy; and *"Do not merely explain what you would
do."*

The outer session gets a much shorter opener (`codex_oauth_agent.py:79`). So the
two roles differ in how much method is dictated: the outer is told *what its job
is*, the inner is told *how to run an experiment*.

### The supervisor is deterministic, not an LLM

`DeterministicSupervisor` (`avo/core/framework.py:182`) is described in its own
docstring as a "process watchdog. It detects stagnation without knowing the
hidden task." Three detectors, each with a counter and a threshold:

| Code | Severity | Trigger | Live? |
|---|---|---|---|
| `repeated_no_change` | redirect | 3 consecutive transitions whose before/after fingerprint is identical | yes |
| `repeated_probe` | warning | same action id selected 4 times in a row | yes |
| `hypothesis_collapse` | redirect | 3 cycles where every covered prediction scored 0 prospectively | **dead code** |

`framework.py:206-250`. This is a direct implementation of NVIDIA's
"supervisor monitors the trajectory for stagnation," but with a much cheaper
mechanism than a second model.

`hypothesis_collapse` **can never fire**: the player laboratory is constructed
with `candidates=[]` (`avo/run_once.py:88`), so `evaluations` is always empty and
`_failed_prediction_cycles` never increments (`framework.py:215-217, 240`). The
same emptiness means `Prediction` freezing and prospective scoring are live code
paths that the model-facing contract never triggers, since `probe` passes only
`action_id` + `rationale` (`tool_gateway.py:298-309`). This is the residue of an
earlier theory-package design — see §13.

Critically, a `redirect` is **enforced, not advisory**: the gateway stores it in
`_supervisor_attention`, and `_require_supervisor_clearance`
(`tool_gateway.py:163`) raises before `probe`, `reset` or `restore` until the
agent calls `acknowledge_supervisor` with a non-empty revised approach. The run
cannot silently grind on.

The legacy tree has the heavier version — an independent *LLM* supervisor
session with its own read-only sandbox and a `supervise_after_stalls=3` cadence
(`avo/legacy/session.py:78`, `avo/legacy/runner.py:104-146`) — and it was
superseded.

## 5. Observation encoding

PuzzleScript is reached through `ArcadeEnv` (`avo/environments/puzzlescript/profile.py:45`)
against the local ARC service, default `http://127.0.0.1:8000`.

The adapter (`avo/environments/puzzlescript/adapter.py`) maps `FrameData` into
the generic AVO `Observation`: `payload={"frame": ...}`, `status`,
`progress={levels_completed, win_levels}`, `available_actions`, and
`metadata.projection` plus `metadata.rendered_frame`.

The profile prompt (`avo/environments/puzzlescript/prompt.md:30`) fixes the
default projection at **`visible-cell-v1`**: one grid cell = one visible tile,
identical RGBA textures share an anonymous integer id, hidden object differences
are *not* encoded, and ids can exceed 15. `visible-cell-hex-v2` (2x2 blocks) and
`object-cell-v1` are described as legacy/alternate. This matches the repo-wide
encoding decision in `AGENTS.md`.

Each observation also carries a lossless PNG of the final visible state, and the
prompt tells the agent to inspect those directly when shape, colour or overlay
matters — so AVO here is **not** text-only, unlike NVIDIA's ARC configuration.

Fitness: `PuzzleScriptProfile.evaluate` (`profile.py:22`) returns
`fitness = levels_completed`, `success = (status == "WIN")`, terminal on
`WIN`/`GAME_OVER`.

## 6. The solver contract and fresh evaluation

`solver.py` is a **persistent streaming controller**, not a per-action process:

```text
python solver.py --play --max-steps N
```

One JSON observation on stdin → exactly one `{"action":"ACTION_ID"}` line on
stdout. The evaluator owns all real execution and never resends growing history
(`avo/evolution/README.md:89`).

`evaluate_solver_workspace` (`avo/evolution/solver_evaluation.py:29`) is strict
about provenance: the workspace is copied to a **fresh anonymous workspace**,
after rejecting any symlink or junction anywhere in the tree, ignoring
`.avo_rpc`, `.tmp`, `observations`, `__pycache__`; an `IsolatedRuntime`
preflight runs; failure raises `IsolationError` and writes
`infrastructure_invalid.json` rather than scoring the candidate.

The loop itself (`solver_evaluation.py:138-176`): write observation, read action
with a 60 s timeout, reject an action not in `available_actions`, step, evaluate
terminality. A crash, a timeout, malformed JSON or an illegal action ends the
evaluation with a `finish_reason` and the score achieved so far. Missing
`solver.py` scores 0 with `"solver.py was not produced"`.

Research, self-check and final budgets are **separate by design**: the inner
session gets at most two `evaluate_solver` self-checks (default
`--max-solver-self-checks 2`, `avo/run.py:54`) whose scalar fitness it sees but
whose trace it does not, while the held-out evaluation has its own 1,500-action
allowance. Exhausting the research budget therefore does not reduce the
solver's allowance.

## 7. Evolution

`EvolutionStore` (`avo/evolution/store.py:131`) is framework-owned and holds
`lineage.json`. It supports `register_draft`, `create_seed`,
`prepare_seed_draft`, `record_evaluation`, `fork(parent, child)`, `inspect` and
paged `evidence`. An unsuccessful `x_i` **stays in the lineage** and must become
evidence for the next candidate — it never triggers a replacement top-level `v2`
run (`SPEC.md:49`).

The outer optimizer's actual tool surface is small and game-free
(`avo/evolution/gateway.py:107`): `population`, `initial`, `inspect`, `evidence`
(paged by `phase`/`offset`/`limit`), `fork`, `register`, `evaluate`, `status`,
`finish`. Two enforcement details matter:

- `evaluate` refuses a candidate that already has an evaluation — *"already
  evaluated; fork a child to vary it"* (`gateway.py:137`). Re-rolling a
  candidate until it scores well is structurally impossible.
- `EvolutionBudget` defaults to 10 evaluations / 14,400 s, and `terminal`
  becomes true on success, evaluation exhaustion, or wall clock
  (`gateway.py:14`, `gateway.py:62`).

There is also an optional **world-model probe** (`world_model_mode` ∈ `off`,
`final-only`, `between-hypotheses`). When enabled, the framework asks the outer
session for one extra turn — *"Write world_model.md in your current workspace
describing your understanding of the game's rules"* (`gateway.py:46`) — after
evaluation is closed. This is presented as a request rather than a
budget-checked call, which is why campaigns can end with
`"the wall limit left no time for the optional final world-model call"`
(`avo/docker/README.md:109`). `avo/report_saved_world_model.py` backfills
reports for saved runs.

The outer optimizer's own prompt (`avo/prompts/outer_optimizer.txt`) is the most
interesting artifact in the repo. It is written as a research-method brief, not
a scheduler. It tells the optimizer to:

- reason about *why* a solver plateaued before choosing a change;
- distinguish **bad implementation** from **bad representation** from **bad
  search method** before editing;
- distinguish an incomplete mechanics model from inefficient planning;
- treat board changes without actor displacement as causal until disproven;
- check for a *stale mode, stale goal, missing state-key variable, or control
  path that bypassed perception updates* before blaming representation;
- prefer a bounded counterfactual experiment over one guessed solver action;
- never alter the evaluator, claim unevaluated improvement, repeat a materially
  unchanged variation, or hide a failure by restarting.

The inner prompt (`avo/prompts/base_agent.txt`) is correspondingly constrained:
the outer session owns the hypothesis, the inner implements it with the
smallest coherent change, treats the strategy as **falsifiable rather than
ground truth**, isolates contradictions with controlled comparisons, records
falsifications for the outer loop, and must never silently swap hypotheses.

So the division of labour is explicit: **outer = hypothesis and representation,
inner = implementation and falsification.**

## 8. Model plumbing

Codex is the sole maintained coding-agent runtime. `avo/client/codex_oauth_agent.py`
drives it over the app-server, reuse of the existing Codex OAuth login rather
than an API key. Model and effort are CLI-selectable. The documented evolution
defaults (`avo/evolution/README.md:27`) are:

```text
--player-model gpt-5.3-codex-spark   --player-effort high
--optimizer-model gpt-5.6-sol        --optimizer-effort high
--max-evaluations 10   --player-max-environment-steps 500   --fresh-solver-max-environment-steps 1500
```

Correction worth knowing: that README block calls itself "the defaults" and
passes `--*-service-tier priority`, but the argparse defaults for both service
tiers are `""`, not `priority` (`avo/evolve.py:50`, `:61`). Priority is opt-in.

OpenRouter is supported per role by prefixing the model id
(`openrouter/deepseek/deepseek-v4.1-flash`); the prefix is stripped before
sending, the key comes from `OPENROUTER_API_KEY` or `AVO_OPENROUTER_KEY_FILE`,
and it is never written into Codex config or request captures
(`avo/docker/README.md:88`). OpenRouter players cannot use the `priority`
service tier.

`model_proxy.py` starts a loopback capture proxy inside the AVO process and
points the ordinary Codex session through it, so exact request bodies land in
`analysis/model_requests/` with auth headers forwarded in memory but never
logged. `request_guard.py` is the *rejection* side: it validates every outgoing
Responses request, including incremental WebSocket requests, and rejects
inherited AGENTS context, private/framework paths, unexpected tools and
unrecognized requests (`avo/ISOLATION.md:33`).

## 9. Isolation

`ISOLATION.md` states the intent: fresh anonymous workspaces outside the repo,
private Codex home with explicit config, only the OAuth credential copied and
removed on exit, no personal memories/plugins/history, automatic project
instructions and browsing disabled, a custom root-deny filesystem profile with
network denial, and a **real sandbox probe before each model session or solver
execution**.

The rule that matters operationally: *isolation failure is
infrastructure-invalid, not candidate fitness* — stop, do not retry under
weaker permissions, and do not retroactively certify old runs.

### The isolation config, concretely

`IsolatedRuntime` writes a private Codex config (`avo/isolation.py:146`) rather
than relying on defaults:

```toml
default_permissions = "avo"
sandbox = "elevated"
memories = false
[memories]
use_memories = false
generate_memories = false
[permissions.avo.filesystem]
":root" = "deny"
[permissions.avo.filesystem.":workspace_roots"]   # workspace writes allowed
[permissions.avo.network]                          # network denied
```

Two notes the doc calls out explicitly:

- Do **not** pass legacy `sandbox=workspace_write` / `sandbox_mode` overrides —
  they supersede the custom profile and restore broad read access
  (`ISOLATION.md:24`, `isolation.py:146`).
- `permissions.avo.filesystem.":root" = "deny"` plus a narrow allow-list is the
  whole mechanism; the comment at `isolation.py:146` records the trap.

The preflight (`isolation.py:232`) runs the real sandbox with no model and no
game, asserting via a probe script that Python works, workspace writes work,
network is `False`, and that repo `AGENTS.md`, the personal Codex `config.toml`
and a private canary file are all **unreadable** (`isolation.py:237-276`). A
`CodexSandboxOffline` account and the `avo` permission profile are part of the
native attempt.

**Native Windows fails closed.** The probe shows Python and workspace writes
working but repository/personal-config reads *and* a live loopback connection
succeeding, i.e. not actually contained. Reproduced with Codex 0.153.1; cause
unresolved; the doc explicitly forbids calling it clean, weakening the probe, or
falling back unelevated (`avo/ISOLATION.md:57-64`). The Docker route is the
supported one, and it passes both the original probe and an app-server
command-path probe without touching personal Windows config.

**Docker/Linux is the supported route.** Trusted controller and Codex app-server
run in a clean Linux image; controller code is staged read-only without game
sources, histories or `.env`; model commands and fresh solvers run inside Codex's
Linux Bubblewrap/seccomp sandbox. The container needs SYS_ADMIN, SETUID, SETGID,
SETFCAP and an unconfined *outer* seccomp profile for nested namespaces — but is
not `--privileged`, mounts no host devices, no Docker socket and no personal
home. Agent commands have zero effective capabilities. Model commands must never
run directly in the outer controller. The model gets structured object grids and
PNGs, not game names or object-name legends (`avo/docker/README.md:1-20`).

## 10. Entry points

Native (Windows: controller interface only, isolation fails closed):

```powershell
uv run python -m avo.run --profile puzzlescript --set game_id=ps_sokoban_basic-v1
uv run python -m avo.evolve --profile puzzlescript --set game_id=ps_midas-v1
```

Docker (supported):

```powershell
docker build -t avo-puzzlescript-isolated:local avo/docker
.venv\Scripts\python.exe -m avo.docker.launch --output-dir output/avo-docker-preflight
.venv\Scripts\python.exe -m avo.docker.smoke_host
```

Operator path: `npm run workbench`, then `/runs/avo.html` for one or parallel
campaigns; `/experiments/avo-lab.html?run=...` for lineage, frames, logs and
artifacts; `/runs/submission.html?run=...` reads the best completed evaluation.

Per-run output layout is in `avo/evolution/README.md:49`. Each Codex session
gets its own bundle (`session.json`, `conversation.jsonl`,
`app_server_events.jsonl`, `model_requests/`, `turn_inputs.jsonl`,
`agent_events.jsonl`). `AVO_TRACE_DETAIL=full` restores the duplicate raw event
streams that compact tracing omits. Treat the output directory as private data —
it contains full prompts and reasoning.

## 11. Where we differ from NVIDIA's AVO

Two cautions before the table. First, the paper's AVO is about **kernel
evolution**; the ARC-AGI-3 work is a later blog-reported transfer, and the blog
does not say whether its supervisor is a separate model or a mechanism. Second,
the blog's ARC configuration differs from the paper's in modality and interface.
So "NVIDIA" below means "as publicly described", and some rows are
blog-vs-paper differences rather than disagreements with us.

| Aspect | NVIDIA (as described) | Ours |
|---|---|---|
| Domain | GPU kernels; later ARC-AGI-3 | PuzzleScript grid games |
| Variation operator | one self-directed agent loop that proposes, repairs, critiques, verifies | two roles: outer proposes/falsifies hypotheses, inner implements and verifies; each is its own persistent Codex session |
| Supervisor | agent supervising the search trajectory; intervention mechanism not specified | deterministic watchdog with **enforced** acknowledgement; the LLM supervisor exists only in `legacy/` |
| Observation | ARC-AGI-3: text-only 64x64 grid, no images | symbolic grid **plus** lossless PNGs the agent may inspect |
| Deliverable | optimized kernel / in-environment play | mandatory `solver.py` run alone in a fresh game |
| Selection | evolutionary search; agent is the variation operator | evolutionary lineage `x_i`, but fitness is **held-out solver play**, never research progress |
| Lineage input | current lineage consulted by the variation agent | `lineage.json` + paged `inspect`/`evidence` over full boards and transitions |
| Memory | persistent memory carries reasoning across context; summarization not specified | persistent Codex session + free-form workspace + inherited seed fork, plus an *unused* world-model mode (see below) |
| Knowledge base | domain-specific knowledge base | none — the environment must be learned from transitions; `MISSION.md` is objective-only |
| Environment contract | ARC-AGI-3 REST | local ARC-compatible PuzzleScript service |
| Task interface | ARC-AGI-3 interactive play | mandatory frozen `solver.py`, scored on held-out play |

Two things we deliberately did **not** build at the core: an LLM supervisor in
the maintained path, and any domain knowledge base.

On memory, be precise — "no summarization layer" would be wrong. The maintained
tree *does* ship an explicit cross-context memory path: `--world-model-mode
{off,final-only,between-hypotheses}` with `final-only` as the fresh-campaign
default (`avo/evolve.py:65, 84`), which spends one extra outer turn having the
optimizer write `world_model.md` (`avo/evolution/gateway.py:46`), archives it
(`avo/evolve.py:205`), and in `between-hypotheses` mode seeds it into the next
candidate (`avo/evolve.py:149`); `avo/report_saved_world_model.py` is a
maintained module that replays a saved run's outer history into a fresh session
to have an LLM write one. But it is **not** automatic in-session conversation
summarization (transcripts are kept verbatim) and **it was never exercised** —
none of the 20 recorded campaigns has a `world_model_mode` key in its
`evolution_config.json`, and no `world_model.json` exists under
`avo/output/evolution`. Treat it as implemented-but-unproven.

One thing we added that NVIDIA's public description does not mention:
**provenance enforcement**. The `ModelView` projection, the request guard, the
isolation preflight and the fresh-solver rule together exist to make "the agent
appeared to do well" hard to confuse with "the agent produced a solver that
works." That is a benchmark-integrity concern (see
`docs/notes/benchmark-positioning.md`), not an agent-capability one.

## 12. Residue: the retired theory-package design

Two designs are layered in this code. The older one imposed a **theory package**:
a candidate shipped a `manifest.json` and a `predict` subprocess speaking
`avo-theory-predict-v1` (`avo/core/theory_package.py:26-113`). The current one
(`SPEC.md:20`) explicitly says there is *no required internal theory, hypothesis,
branch, manifest or candidate format*.

The old design was removed from the model-facing contract but not from the code:
`TheoryManifest` and `FilesystemTheoryCandidate` are still exported from
`avo/__init__.py:14-17` and referenced only by `avo/legacy/agentic.py`. In the
live path the corresponding machinery is inert for the reason in §4.

Practical consequence: **adding an environment never requires a theory format**,
but you will read code that talks about predictions and candidates and never
sees them fire. Don't "fix" the emptiness — it is the contract.

Other known-stale spots a newcomer will trip over:

| Thing | Problem |
|---|---|
| `monitor_evolution.py:72-77, 106` | globs `<run>/.sandboxes/avo-player-<id>-*`, a layout nothing creates any more (workspaces live in `~/.avo/isolated/w-*`), so `solver.draft_present` is always false. The test at `tests/test_monitor_evolution.py:15` fabricates the old layout, so it still passes. |
| `evolution/store.py:452-456` | `evidence` accepts only `self_check_01`/`self_check_02`; raising `--player-max-solver-self-checks` past 2 yields self-checks that cannot be paged. |
| `isolation.py:41-49` | `cleanup_private_directory` is a no-op on Windows, so `~/.avo/isolated` accumulates `w-*`/`c-*` directories. |
| `analysis/run_trace.py:51` | `full_trace` defaults to `"full"` — per-event workspace snapshots and a blob store. Docker forces `AVO_TRACE_DETAIL=compact`; native runs are enormous by default. |
| inner vs outer RPC timeout | 3600 s (`tool_gateway.py:439`) vs 86400 s (`evolution/tool_server.py:74`); a slow self-check can outlive the inner call. |
| supervisor gate | while attention is pending, `probe`/`reset`/`restore` all raise. An agent that never acknowledges burns turns until the turn budget forces `finish`. |

Three-way sync requirement: a new gateway method must be added in **three**
places that nothing cross-validates — `AvoToolGateway.handle`
(`tool_gateway.py:330`), the embedded `AGENT_CLI` argparse (`:420`) and the
`AGENT_INTERFACE` prose (`:375`); the outer loop mirrors this in
`EvolutionGateway.handle` (`evolution/gateway.py:107`), `OPTIMIZER_CLI`
(`evolution/tool_server.py:56`) and `OPTIMIZER_INTERFACE` (`:10`).

## 13. Adding a new environment

The pattern is a **profile**, and there are two worked examples plus a sibling
repo. `avo-jericho` (at `../avo-jericho`) adapts Jericho interactive fiction —
read it before writing a new adapter, because it is the template for
non-grid, command-driven environments.

```text
avo/environments/<name>/
  profile.toml   id, factory = "<module>:create_profile", prompt = "prompt.md", [defaults]
  profile.py     <Name>Profile dataclass: environment, profile_id, objective, provenance(), evaluate()
  adapter.py     <Name>Environment: reset() / step(Action) -> Observation, optional save_state/restore_state/compare
  prompt.md      the task prompt the inner player receives
```

Required from the adapter: `reset() -> Observation`, `step(Action) -> Observation`,
and an `Observation(payload, status, progress, available_actions, metadata)`.
Status must use `"WIN"` / `"GAME_OVER"` / anything else for "playing", because
`evaluate()` keys off those strings. `save_state`/`restore_state` are optional
but unlock the agent's counterfactual branching; `compare` is optional and only
feeds the inert prediction machinery.

Required from the profile: `factory` callable taking a settings dict,
`profile_id`, `objective` (rendered into `MISSION.md`), and
`evaluate(history, current) -> TaskEvaluation` returning `terminal`, `success`
and `fitness`.

**Two topologies are possible, and the choice matters.**

1. **In-process backend** (Jericho): the game library is installed in the AVO
   image and `create_profile` constructs it directly. No network, no extra
   service. This is what `avo-jericho` does with `FrotzEnv`.
2. **Controller-side HTTP** (PuzzleScript): the profile constructs a client
   (`ArcadeEnv`) that speaks HTTP to a service. This is safe under the isolation
   contract **because the network denial applies to the agent's and solver's
   sandboxes, not to the controller process** — the controller is documented as
   needing to reach the ARC backend and model service
   (`docker/README.md:8`). The solver still never touches the network: it
   exchanges JSON with the controller over stdin/stdout.

Option 2 means an existing HTTP game server needs no rewrite — it needs a
profile, an adapter and a prompt, and it must be reachable from the container.

## 14. Contracts the test suite locks down

Useful as a map of "what breaks if I change this" (`avo/tests/`, 82 tests):

| Contract | Test |
|---|---|
| fresh self-checks are separate and limited to two | `test_avo_tool_gateway.py:63` |
| supervisor redirect blocks actions until acknowledged | `test_avo_tool_gateway.py:224` |
| checkpoint restore spends no environment step | `test_avo_tool_gateway.py:274` |
| `finish` does not claim task success | `test_avo_tool_gateway.py:209` |
| the workspace has **no** theory-package workflow | `test_avo_tool_gateway.py:148` |
| the player run has no internal theory budget | `test_run_once.py:140` |
| outer RPC exposes candidate tools but no gameplay tools | `test_evolution.py:289` |
| the evaluator reloads the profile for every fresh run | `test_evolution.py:381` |
| clean generation layout + separate fresh solver budget | `test_evolution.py:453` |
| outer designs `x_0001` from a frozen initial observation | `test_evolution.py:117` |
| one persistent workspace-write thread, no memories | `test_avo_codex_oauth_agent.py:171` |
| world-model report is one extra turn in the same thread | `test_avo_codex_oauth_agent.py:131` |
| request guard blocks late AGENTS injection and escaped paths | `test_isolation.py:120` |
| guard does **not** censor model guesses or learned controls | `test_isolation.py:139` |
| successful command with leaky permissions is still rejected | `test_isolation.py:99` |
| failed native preflight fails closed | `test_isolation.py:112` |
| capture failure latches invalid state; unknown WS messages fail closed | `test_isolation.py:244` |
| staging excludes game sources, rules, credentials, histories | `test_docker_launch.py:43` |

The pair at `test_isolation.py:139` and `:120` is the sharpest statement of
intent in the suite: the guard must block *context leakage* while explicitly
**not** censoring what the model hypothesised or learned from observations.

## 15. What the experiments actually show

Re-derived from all 20 campaigns under `avo/output/evolution/` (note: recent
campaigns write `lineage.json` only; the eight `midas-solver-*` /
`midas-model-first-*` generations keep evaluations in a legacy `population.json`,
including the `midas-live` row):

| Campaign | Candidates / evals | Best fitness | Note |
|---|---|---|---|
| `midas-live-v01-20260825` | 5 / 5 | **8 / 15** | pre-solver generation; live research only |
| `midas-luna-medium-sol-high-20260828T200612` | 7 / 6 | 2 / 15 | |
| `midas-luna-medium-sol-high-20260828T144003` | 10 / 10 | 3 / 15 | held-out `solver.py` evaluation |
| `midas-outer-evidence-luna-medium-sol-high-...210529` | 30 / 30 | 6 / 15 | plateau at 4, then 6 |
| `midas-outer-sol-high-inner-sol-high-x20-budget300-...013257` | 12 / 11 | 4 / 15 | solver budget 300 |
| `midas-outer-...-research500-eval1500-...031836` | 4 / 3 | 4 / 15 | |
| `midas-outer-...-discovery-research500-eval1500-...042951` | 4 / 3 | 4 / 15 | |
| `midas-spark-high-sol-high-20260828` | 1 / 0 | — | aborted: Spark exhausted context during remote compaction; retry blocked by a model usage limit until after the run's wall budget |

Also worth stating plainly, because it is easy to misread: the two "luna-medium"
campaigns ran only **300** research actions, not the 500 in the README example.
The campaigns that actually used 500/1500 are the omitted 08-31 ones.

**Corrections to an earlier reading of this data** (these claims were wrong and
the artifacts contradict them):

- Inner research does **not** out-reach the held-out solver. Across all 63
  evaluations carrying the field, `research_fitness ∈ {0,1,2,3,4}` — never 5 or
  6. The 4-6 band is the *solver* range. "8 live" applies only to the
  pre-solver `midas-live` campaign, which has no solver stage at all.
- Research/held-out **divergence is real but not dominant**: over 63 paired
  evaluations, research > solver in 11, equal in 35, research < solver in 17.
  Equality dominates. Exactly 7 candidates show the stark pattern
  (`research_fitness` 3-4 with `solver_levels_completed` 1-2).
- The `x_0013`-`x_0027` stretch does *not* show the outer loop idling on a
  frozen artifact. Research actions there are
  `0,5,0,0,4,4,3,4,3,3,3,5,6,111,6` — **x_0026 ran 111 actions** and reached
  `research_fitness` 4.0. Fourteen of the fifteen are ≤6 actions, but "no new
  evidence" is false. (The solver holding at 4 for all fifteen is correct.)

What survives as the interesting finding: **fitness is flat across a long
lineage.** The 30-candidate campaign moves 1→4 over eleven candidates and then
sits at 4 for fourteen more, ending on 6. That is a search-dynamics result worth
understanding, and it is the thing to fix before raising the budget.

### Open questions worth attacking

1. **Representation vs. search.** The outer prompt already tells the optimizer
   to separate these; the lineage suggests it mostly patches implementation.
   There is no measurement of which it actually did.
2. **Why a 14-candidate plateau at fitness 4.** The three late 4→6 hops
   (x_0026, x_0028) are the only evidence of progress in 20 evaluations. What
   distinguished them warrants a read of their `STRATEGY.md` and parent diffs.
3. **Budget allocation.** Neither summarized campaign used the stated budget, so
   no recorded run has tested the 500/1500 configuration end to end. Any claim
   about budget sufficiency is currently unsupported by artifacts.
4. **Supervisor effectiveness.** This one is answerable from existing data:
   `supervisor_event` appears in 184 `evidence.jsonl` files (26,915 records;
   16,954 redirects, 9,961 warnings), `supervisor_paused` in 55 (489) and
   `supervisor_acknowledged` in 55 (503) — including the maintained campaigns
   (T144003: 32 acknowledgements; T210529: 27). So enforcement demonstrably fired
   in real runs; what is unmeasured is whether acknowledging improved fitness.

## 16. File map

| Path | Role |
|---|---|
| `avo/SPEC.md` | runtime contract: actors, `x_i`, fresh evaluation, authority |
| `avo/LAB.md` | operator entry, layout, session-log contract |
| `avo/ISOLATION.md` | isolation intent, Windows failure, verification bar |
| `avo/run.py` | one player run (native) |
| `avo/run_once.py` | `execute_player_run`, player run settings |
| `avo/evolve.py` | outer sequence of player runs |
| `avo/monitor_evolution.py` | campaign monitoring |
| `avo/isolation.py` | `IsolatedRuntime`, workspace creation, preflight |
| `avo/core/framework.py` | `AvoLaboratory`, `EvidenceStore`, `DeterministicSupervisor`, observation/transition types |
| `avo/core/tool_gateway.py` | gateway commands, budgets, supervisor enforcement, generated CLI + `AGENT_INTERFACE` |
| `avo/core/model_view.py` | model-facing projection and identity stripping |
| `avo/core/profile.py` | environment profile loading |
| `avo/core/run_store.py`, `theory_package.py` | run records, filesystem theory candidates |
| `avo/client/codex_oauth_agent.py` | persistent Codex session over app-server |
| `avo/environments/puzzlescript/` | adapter, profile, fitness, task prompt |
| `avo/evolution/README.md` | `x_i` layout and budget separation |
| `avo/evolution/store.py` | `EvolutionStore`, lineage, fork, inspect, paged evidence |
| `avo/evolution/solver_evaluation.py` | held-out streaming solver evaluation |
| `avo/evolution/gateway.py`, `tool_server.py` | outer optimizer tooling |
| `avo/analysis/model_proxy.py`, `request_guard.py`, `run_trace.py` | request capture, context rejection, session bundles |
| `avo/docker/` | supported Linux isolation, launcher, batch, smoke |
| `avo/prompts/base_agent.txt` | inner player instructions |
| `avo/prompts/outer_optimizer.txt` | outer optimizer research method |
| `avo/legacy/` | superseded LLM-supervisor and OpenRouter experiments |
| `avo/tests/` | maintained regression suite, including isolation and supervisor contracts |
