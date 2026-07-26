# PuzzleScript World Benchmark

## General Aim

The aim is to benchmark how well a complete agent system can enter a novel interactive environment, discover what task it is facing, learn how the environment works, and use that knowledge to act successfully.

PuzzleScript is the experimental substrate, not the research target.

## What Are the Games?

The benchmark would use a curated set of small, human-authored, turn-based grid games with different mechanics:

- Navigation and reaching targets
- Pushing and arranging objects
- Switches, doors, and conditional interactions
- Object transformations
- Directional and movement constraints
- Mechanics that must be combined over multiple steps

A game would normally contain several levels governed by the same underlying rules. The agent first encounters the mechanics in an early level and must transfer what it learns to later levels with new layouts and longer plans.

The initial benchmark should use deterministic games that run reliably and whose solutions can be verified.

## What Does an Evaluation Look Like?

At the beginning of a game, the agent receives:

- The current game state
- The available actions
- No game title or semantic hints
- No instructions explaining the objective
- No description of the environment rules

The agent selects one action at a time and observes the resulting state. Its memory persists across levels of the same game.

The evaluated system is the complete agent harness:

- Foundation model
- State representation
- Memory and context management
- Goal and rule hypotheses
- Exploration strategy
- Planner and controller
- Verifiers, tools, and subagents

## Score

Each game and level needs a verified reference solution. When the state space is tractable, the shortest path can be computed by search. Otherwise, the reference path must be produced and validated manually or by a trusted solver.

For a successful run:

```text
score = optimal_actions / agent_actions
```

All environment actions count, including exploratory actions, mistakes, reset, and undo. The score therefore measures how efficiently the agent both learns and solves the game.

An optimal successful run receives `1.0`. A successful run using twice as many actions receives `0.5`. An unsuccessful run receives `0` on the main completion score.

When an exact state graph is available, reduction in optimal distance to a winning state can also be reported for unsuccessful runs. This should remain a diagnostic measure because progress is not always monotonic.

The benchmark should also report separate capability scores:

- Goal-recognition accuracy
- Transition-prediction accuracy of the learned rules
- Exploration efficiency
- Belief revision after contradictions
- Planning efficiency when the goal and rules are provided
- Transfer to later levels
- Tokens, model calls, tool use, time, and cost

## Goal Difficulty

Goal-recognition difficulty should be based on how much evidence is needed:

- **Easy:** The goal can usually be identified from the initial state.
- **Medium:** The goal becomes identifiable after a short trajectory or a few observed interactions.
- **Hard:** The agent must choose diagnostic actions or complete a multistep interaction before the goal becomes clear.

This allows us to measure goal-recognition accuracy as a function of evidence rather than assigning difficulty only by intuition.

## Configurability

The same games can be run under controlled diagnostic conditions:

- **Goal and rules hidden:** Complete skill acquisition
- **Goal provided, rules hidden:** World-model learning
- **Rules provided, goal hidden:** Goal recognition
- **Goal and rules provided:** Planning and execution
- **Rendered or symbolic state:** Dependence on representation

The harness can also be ablated:

```text
base model
    -> + memory
    -> + explicit rule learning
    -> + rule verifier
    -> + planner
    -> + tools or subagents
```

For every addition, we can measure what improved, where it improved, and what computational cost it introduced.

## What Does the Benchmark Bring?

The benchmark is not useful if it only reports completion over another game collection.

Its value is that it evaluates the complete agent architecture and separates skill acquisition into measurable capabilities. When an agent fails, we can determine whether it:

- Inferred the wrong goal
- Learned incorrect dynamics
- Explored poorly
- Failed to revise a contradicted belief
- Knew the game but could not plan

The central research question is:

> **Which capabilities and architectural components allow an agent to efficiently acquire a new interactive skill, and which missing capability causes it to fail?**

## Comparison with ARC-AGI-3

[ARC-AGI-3](https://arcprize.org/media/ARC_AGI_3_Technical_Report.pdf) has a similar high-level challenge: the agent must understand its actions, infer the objective and mechanics, and solve a novel interactive environment.

Its official evaluation uses the same minimal system prompt for every model and does not provide external harness tools. It primarily evaluates a frontier model as a black box through completion and human-relative action efficiency.

Our benchmark instead makes the complete model-plus-harness system the object of evaluation. Memory, explicit rule learning, verification, planning, tools, and subagents are experimental variables.

ARC-AGI-3 provides a canonical `64 x 64` grid of color values or frame sequence. A harness can render or transform those observations, so the ability to create an image or symbolic representation is not unique to our benchmark.

Our difference is that rendered, anonymous symbolic, and object-level representations are standardized benchmark conditions. This allows the effect of representation to be measured while keeping the underlying game fixed.

The main distinction is:

> **ARC-AGI-3 evaluates whether a model can acquire and execute a skill. This benchmark evaluates how a complete agent architecture acquires that skill, which components help, and where it fails.**

## Comparison with PuzzleJAX

[PuzzleJAX](https://arxiv.org/abs/2508.16821) provides a fast JAX environment for hundreds of PuzzleScript-style games. It benchmarks:

- Tree search
- Reinforcement learning
- LLM puzzle solving
- Environment speed and scalability
- Win rate and level completion

Its LLM baseline receives:

- An ASCII state
- An object mapping
- The game rules
- The available actions and their meanings

PuzzleJAX primarily asks whether search, RL, and LLM methods can solve many puzzle games efficiently.

Our primary condition hides the goal and dynamics. The agent must discover them through interaction. We then evaluate goal inference, rule learning, exploration, belief revision, planning, harness components, and transfer across levels.

The relationship is:

```text
PuzzleJAX:
fast environment for benchmarking puzzle-solving methods

PuzzleScript World Benchmark:
diagnostic protocol for benchmarking agent skill acquisition
```

Our contribution is the evaluation protocol and capability decomposition, not a faster game engine. In principle, the protocol could also be implemented on top of PuzzleJAX.
