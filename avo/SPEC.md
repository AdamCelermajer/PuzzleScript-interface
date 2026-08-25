# General-purpose AVO framework specification

Status: v0.4 implemented prototype. This file is authoritative for the intended framework.

## 1. Definition

An AVO run is a persistent autonomous research agent operating inside a trusted
experimental laboratory. The agent is the variation operator: it decides what
theories to create, which parent to revise, which tools to use, which experiment
to request, and when to stop. The laboratory never supplies a domain ontology.

This is the distinguishing condition:

```text
EVO: framework chooses parent -> LLM produces one variation -> framework scores
AVO: autonomous agent owns the entire candidate-creation and testing process
```

Prediction freezing, evidence storage, and a supervisor are useful scaffolding,
but they do not by themselves make a system AVO.

## 2. Trust boundary

### The environment owns

- `reset()` and `step(action)`
- the observation returned after an action
- available action IDs and parameter schemas
- progress signals
- the authoritative observation comparator

### The environment profile owns

- construction and configuration of the environment adapter
- the external objective supplied to the agent
- the environment-specific prompt fragment
- terminal and success determination
- task fitness $f$ and its score vector

### The agent owns

- its ontology and internal representation
- concrete goal and win-condition hypotheses
- candidate lineage and parent selection
- when and how to use code, search, visualization, or other tools
- proposed experiments and their rationale
- candidate repair, branching, retirement, and commit timing
- voluntary termination

### The laboratory owns

- immutable event ordering and timestamps
- Theory Package admission checks
- freezing predictions before environment execution
- executing legal actions exactly once
- comparing all candidates against the same actual result
- framework metrics, budgets, and termination enforcement
- deterministic supervisor triggers

### The supervisor owns

- warnings and redirects based on process evidence
- no environment semantics and no hidden solution
- no authority to change observations, scores, or candidate code

## 3. Environment contract

The environment adapter assumes only:

```python
reset() -> Observation
step(Action) -> Observation
compare(expected, actual) -> Comparison
```

The specialization is one `EnvironmentProfile`:

```python
profile_id: str
objective: str
environment: EnvironmentContract
evaluate(history, current) -> TaskEvaluation
```

`TaskEvaluation` returns `terminal`, `success`, and an environment-owned score
vector. The generic kernel never checks for strings such as `WIN`.

`Observation.payload` is opaque JSON. An adapter may expose status, progress,
legal actions, and metadata, but it must not add semantic labels that are not
part of the real environment interface.

The same contract can wrap PuzzleScript, ARC-AGI-3, a simulator, a robot, a web
task, or any other interactive system with discrete experiments.

## 4. Theory Package x_i

Every candidate is an agent-authored directory:

```text
candidates/x_001/
  manifest.json
  predict.py       # or another executable named by the manifest
  notes.md         # optional, ignored by the trusted kernel
  tests/           # optional, agent-owned diagnostics
```

Required `manifest.json` fields:

```json
{
  "schema_version": 1,
  "candidate_id": "x_001",
  "parent_id": null,
  "claim": "ACTION1 increments the latent counter",
  "complexity": 0.1,
  "command": ["$PYTHON", "predict.py"]
}
```

The command receives one JSON request on standard input:

```json
{
  "protocol": "avo-theory-predict-v1",
  "history": [],
  "current": {},
  "action": {"id": "ACTION1", "data": {}}
}
```

It must return exactly one JSON object:

```json
{
  "protocol": "avo-theory-prediction-v1",
  "expected": {
    "payload": {},
    "status": "PLAYING",
    "progress": null,
    "available_actions": []
  },
  "confidence": 0.7,
  "rationale": "replays transitions 3 and 8"
}
```

The package may use any internal representation or programming language. The
subprocess boundary isolates crashes and enforces a timeout, but is not yet a
security sandbox.

## 5. Agent decision protocol

Through the generic tool gateway, the persistent agent can request:

- the profile-supplied mission and current task score
- current opaque observation
- immutable transition history
- summaries of admitted candidates
- legal action IDs
- recent supervisor events
- remaining decision, action, candidate, and wall-time budgets
- a writable research workspace and explicit Theory Package publication
- explicit archival of notes, tools, and unpublished drafts into the run record

During the persistent session the agent may inspect evidence, write diagnostics,
create multiple branches, publish candidates, or do nothing. It eventually
requests either:

```text
Probe(action, rationale)
Stop(reason)
```

Candidate creation is not a framework phase and a probe requires no candidate.
On Windows, the agent authors under `drafts/` and explicitly calls `publish` so
the framework can copy the exact package across the Codex sandbox ACL boundary.
The framework does not prompt `now mutate x_17` or choose the parent.

## 6. One authoritative cycle

```text
1. Agent inspects evidence and works freely in its persistent workspace.
2. Registry admits newly created Theory Packages.
3. Agent requests one legal probe and records why.
4. Laboratory invokes every candidate for a prospective prediction.
5. Laboratory freezes all predictions and timestamps them.
6. Environment executes the action exactly once.
7. Laboratory appends the real transition.
8. Environment comparator scores every frozen prediction.
9. Supervisor inspects process signals.
10. The profile evaluates task success and fitness.
11. Agent receives the result and chooses what follows.
```

## 7. Evaluators

Task fitness is owned by the environment profile. For PuzzleScript:

```text
f(run) = (success, levels_completed, -environment_actions)
success = environment state is WIN
```

The hypothesis evaluator is separate. It preserves a vector rather than hiding
tradeoffs in one number:

The evaluator preserves a vector rather than hiding tradeoffs in one number:

- contract validity
- replay consistency on prior transitions
- prospective observation accuracy
- terminal/goal prediction accuracy
- coverage versus abstention
- planning usefulness
- complexity cost
- runtime and tool cost

Agent-authored tests are diagnostic evidence. They cannot replace framework
comparison against the actual environment result.

## 8. Experiment selection

The laboratory may report disagreement for every legal action as advice. The
agent retains the final choice and must record its rationale. A default
information score can combine:

```text
candidate disagreement + uncertainty reduction - action cost - irreversible risk
```

The framework must not silently execute its preferred action; doing so would
move experiment ownership back into an EVO-style outer loop.

## 9. Supervisor

Deterministic triggers include:

- repeated no-change probes
- repeated action families without an information rationale
- collective prospective failure
- contradictions that never cause candidate revision
- improvements only on agent-authored metrics
- budget exhaustion risk

The supervisor returns `warning`, `redirect`, or `stop`. Its message becomes
evidence for the agent; it does not write candidate code.

## 10. Budgets and termination

Every environment profile evaluates terminal and success states. The run also has explicit
limits for agent decisions, environment steps, candidates, Theory Package
runtime, total wall time, and optionally tokens/cost. A run stops on:

- environment terminal state
- agent-declared stop, which does not imply success
- enforced budget exhaustion
- unrecoverable contract violation
- supervisor stop policy

## 11. Required artifacts

```text
run/
  run_config.json
  evidence.jsonl
  candidates/
  workspace/
  final_summary.json
```

`evidence.jsonl` is append-only and records candidate admission, agent decision,
prediction freezing, transition, evaluation, and supervisor events in their
actual order.

## 12. Current implementation status

Implemented:

- generic observation/action/environment contracts
- append-only evidence
- prospective prediction freezing and evaluation
- filesystem Theory Package manifest and subprocess protocol
- agent-owned probe decision protocol
- candidate discovery after agent workspace activity
- budgets and terminal enforcement
- deterministic supervisor
- PuzzleScript adapter
- environment-neutral file tool gateway
- agent-owned Theory Package publication
- historical replay score aggregation
- persistent Codex OAuth controller
- self-contained top-level `avo/` package
- manifest-loaded environment profiles
- profile-owned objective, task fitness, and terminal/success semantics
- composed base and environment prompts
- one generic run store and evidence history
- agent-side workspace archival across the Windows sandbox boundary

Not yet implemented:

- secure OS sandbox for untrusted candidate processes
- token/cost budgets
- supervisor stop policy

The full PuzzleScript integration run at
`avo/output/sokoban-basic-full-v04-20260824/` ended with the profile-authoritative
`WIN` signal after 84 opaque actions. Codex used one persistent turn, crossed
from level one to level two, and received no action meanings, legend, game
source, win condition, or solution. It created and archived its own BFS solver,
plan executor, compact probe utility, and notes. It published no Theory Package in that
trajectory, so live candidate scoring still needs a separate autonomous run;
candidate publication, replay scoring, and prospective scoring are covered by
the framework tests.
