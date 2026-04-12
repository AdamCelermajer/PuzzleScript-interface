# Intro Sources for NotebookLM

## Project Overview
This project, **"LLM-Based Rule Induction & Planning in PuzzleScript"**, is an M.Sc. Research project by Adam Celermajer at Bar-Ilan University. The core goal is to determine if Large Language Models (LLMs) can:
1. **Induce Rules:** Infer latent game mechanics purely from observing state transitions in a discrete 2D grid environment (PuzzleScript).
2. **Plan:** Use these inferred rules to generate valid solution trajectories for puzzles they haven't seen before.
3. **Generalize:** Transfer learned dynamics across different levels or game variants.

## System Architecture
The system is divided into three main components:
1. **The Environment (PuzzleScript Interface)**: A Node.js Express server (`puzzlescript_interface/runtime/server.js`) that runs a headless instance of the PuzzleScript engine. A FastAPI adapter (`puzzlescript_interface/api/app.py`) exposes that runtime through an ARC-compatible API.
2. **The Agent (LLM Client)**: A Python client (`client/engine/agent.py`, `client/engine/llm_client.py`, `client/engine/prompts.py`) that communicates with ARC-compatible backends. It receives integer-grid frames, extracts observations, formulates hypotheses about rules, and generates moves.
3. **The Evaluator**: Compares the Agent's internal model against the actual ground truth PuzzleScript rules.

## Key Files & Directories

### Root Directory
*   `README.md`: Explains the two top-level products and how to run the local stack.
*   `CLAUDE.md`: Repository-specific architecture and workflow notes.

### `client/`
Contains the generic ARC-compatible client.
*   `engine/`: Agent logic, environment adapter, prompts, types, and utilities.
*   `run_arc_agent.py`: CLI entrypoint for learning and solving.
*   `play_arc_client.py`: Terminal client for manual play.
*   `rules/`: Client-owned inferred rule files.

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
