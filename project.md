# Project: LLM-Based Rule Induction & Planning in PuzzleScript

**Student:** Adam Celermajer  
**Supervisors:** Prof. Yoav Goldberg, Prof. Gal Kaminka  
**Institution:** Bar-Ilan University (M.Sc. Research)

## 1. Research Goal
To determine if Large Language Models (LLMs) can:
1.  **Induce Rules:** Infer latent game mechanics (physics/rules) purely from observing state transitions in a discrete 2D grid environment (PuzzleScript).
2.  **Plan:** Use these inferred rules to generate valid solution trajectories for puzzles they have never seen before.
3.  **Generalize:** Transfer learned dynamics across levels or similar game variants.

## 2. Motivation
Current LLMs excel at code generation and static reasoning but struggle with:
* **Grounded Dynamics:** Understanding the causal consequences of actions in a specific, consistent environment without prior training on that specific environment's rules.
* **Consistent Planning:** Maintaining a valid world model over long-horizon tasks.
* **Interpretability:** Differentiating between "hallucinated" physics and actual environment constraints.

PuzzleScript is the ideal testbed because:
* It has discrete, deterministic logic (Sokoban-style).
* The state space is small but the planning complexity is high.
* The "physics" are defined by explicit rewrite rules (e.g., `[ > Player | Crate ] -> [ > Player | > Crate ]`), which serves as a ground truth to measure the agent's inference accuracy.

## 3. Architecture
The system consists of three main components:

### A. The Environment (PuzzleScript Engine Wrapper)
* **Core:** A headless instance of the PuzzleScript engine (JS/HTML5) running locally.
* **Interface:** A Python wrapper (`PuzzleScript-interface`) that communicates with the engine.
    * *Input:* Sends actions (`UP`, `DOWN`, `LEFT`, `RIGHT`, `ACTION`).
    * *Output:* Receives the game state.
* **Rendering:** Converts the raw game state (objects/layers) into a token-efficient ASCII/Text representation for the LLM.

### B. The Agent (LLM)
* **Observation:** Receives the ASCII grid and a history of (Action, Result) pairs.
* **Inference Module:** Formulates hypotheses about object interactions (e.g., "If I move into `*`, it pushes `*`").
* **Planner:** Generates a sequence of moves to reach the `WIN` condition based on the inferred rules.

### C. The Evaluator
* Compares the Agent's *internal model* (the rules it claims exist) against the *ground truth* PuzzleScript source code.
* Measures success rate on novel levels.

## 4. Current Status
* [x] **Infrastructure:** Python interface for PuzzleScript engine acts as a Gym-like environment.
* [x] **State Representation:** Raw object extraction implemented.
* [ ] **Observation Space:** Refining the ASCII/Text rendering to ensure the LLM can "see" objects defined only by color (current blocker).
* [ ] **Agent Loop:** Implementing the Iterative Prompting / ReAct loop for rule testing.

## 5. Roadmap
1.  **Fix ASCII Rendering:** Map color-only objects to distinct characters/IDs so the LLM is not blind to them.
2.  **Zero-Shot Baseline:** Test LLM performance on standard Sokoban without rule-learning (pure reasoning).
3.  **Few-Shot Rule Learning:** Implement the feedback loop where the agent proposes a move, observes the outcome, and updates its rule set.
4.  **Evaluation:** Benchmark on the PuzzleScript dataset (variety of mechanics beyond pushing).