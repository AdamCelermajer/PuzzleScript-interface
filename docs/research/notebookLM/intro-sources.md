# Intro Sources for NotebookLM

## Project Overview
This repository supports two related workflows around ARC-compatible puzzle interaction:
1. **Local PuzzleScript:** Run bundled PuzzleScript games through a local Node.js runtime and ARC-compatible Python service.
2. **Official ARC-AGI-3:** Run the same Python client against the hosted ARC backend.

Within that setup, the research focus is whether Large Language Models (LLMs) can:
1. **Induce Rules:** Infer latent game mechanics from observed state transitions in discrete 2D grid environments.
2. **Plan:** Use inferred rules to generate valid solution trajectories.
3. **Generalize:** Transfer learned dynamics across different levels or task variants.

## System Architecture
The repository is organized around two runtime stacks and their supporting docs:
1. **The ARC-Compatible Client (`client/`)**: Python entrypoints and agent code for learning, solving, terminal play, and rule persistence against ARC-compatible backends.
2. **The PuzzleScript Interface (`puzzlescript_interface/`)**: A Node.js PuzzleScript runtime (`puzzlescript_interface/runtime/server.js`) plus a FastAPI ARC-compatible adapter (`puzzlescript_interface/api/app.py`) for local PuzzleScript-backed runs.
3. **Supporting Docs (`docs/` and `examples/`)**: Architecture, research/spec materials, and small reference examples that document the system without being part of the main runtime path.

## Key Files & Directories

### Root Directory
*   `README.md`: Explains the two supported workflows, architecture diagram, research docs, and key entry points.
*   `CLAUDE.md`: Repository-specific architecture and workflow notes.
*   `examples/basic_client.py`: Small standalone client example.

### `client/`
Contains the generic ARC-compatible client.
*   `engine/`: Agent logic, environment adapter, prompts, types, and utilities.
*   `run_arc_agent.py`: CLI entrypoint for learning and solving.
*   `play_arc_client.py`: Terminal client for manual play.
*   `rules/`: Client-owned inferred rule files.

### `docs/`
Contains supporting documentation rather than runtime code.
*   `architecture/arc-agi-architecture.svg`: Repository architecture diagram.
*   `research/`: Supporting research and prompt-spec materials.

### `puzzlescript_interface/`
Contains the local PuzzleScript-backed ARC-compatible challenge surface.
*   `runtime/server.js`: The Node.js PuzzleScript runtime.
*   `api/app.py`: The FastAPI ARC-compatible adapter.
*   `games/`: PuzzleScript source files.

## Instructions for NotebookLM

NotebookLM, when you answer questions about this codebase:
1. **Focus on the Core Objective**: Always keep in mind that the Python code is an "Agent" attempting to act as a scientific explorer (learning and solving), while the Node JS code acts as an objective, strict "Environment".
2. **Differentiate the Stacks**: Carefully distinguish between the deterministic environment logic in Node.js (parsing, physics execution, REST API) and the stochastic reasoning logic in Python (prompting, zero-shot/few-shot learning loops).
3. **Prompting is Key**: Pay close attention to `client/engine/prompts.py` as it defines the Agent's observation formatting and reasoning capabilities. Adjustments to prompts often yield the biggest improvements in LLM performance for task solving.
4. **State Representations**: A key technical challenge is rendering the 2D grid (which relies on color in raw PuzzleScript) into a character-based ASCII representation that the LLM can properly "see" and reason about.

*Context created: March 2026*
