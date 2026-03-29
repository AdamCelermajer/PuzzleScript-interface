# Intro Sources for NotebookLM

## Project Overview
This project, **"LLM-Based Rule Induction & Planning in PuzzleScript"**, is an M.Sc. Research project by Adam Celermajer at Bar-Ilan University. The core goal is to determine if Large Language Models (LLMs) can:
1. **Induce Rules:** Infer latent game mechanics purely from observing state transitions in a discrete 2D grid environment (PuzzleScript).
2. **Plan:** Use these inferred rules to generate valid solution trajectories for puzzles they haven't seen before.
3. **Generalize:** Transfer learned dynamics across different levels or game variants.

## System Architecture
The system is divided into three main components:
1. **The Environment (PuzzleScript Engine Wrapper)**: A Node.js Express server (`src/server.js`) that runs a headless instance of the PuzzleScript engine. It parses PuzzleScript files, manages sessions, and enforces rules, exposing game states via a REST API.
2. **The Agent (LLM)**: A Python interface (`src/llm_client.py`, `src/learning_mode.py`, `src/solving_mode.py`, `src/prompts.py`) that communicates with the `server.js` engine. It receives ASCII/Text representations of the grid, extracts observations, formulates hypotheses about rules, and generates moves.
3. **The Evaluator**: Compares the Agent's internal model against the actual ground truth PuzzleScript rules.

## Key Files & Directories

### Root Directory
*   `project.md`: Contains the research goals, motivation, architecture, and roadmap.
*   `README.md`: Explains the Node.js server setup, API, and how to run the components.
*   `SERVER_EXPLANATION.md`: Deep dive into `server.js` logic, structure, and API endpoints.

### `src/` Directory
Contains the actual source code for both the backend engine and the Python LLM interface.
*   `server.js`: The Node.js Express game engine and server.
*   `client.js`: A CLI client that acts as a manual tester to visually play the games.
*   `llm_client.py`: The Python client logic connecting to the LLM.
*   `learning_mode.py`: The phase where the LLM interacts with the environment, tests hypotheses, and builds an internal rule model.
*   `solving_mode.py`: The evaluation phase where the LLM plans and generates a solution using the rules it has inferred.
*   `prompts.py`: Contains the carefully crafted structured prompts used to communicate with the LLM agent.
*   `rules/`: Contains rule representations (e.g., `midas_rules.txt`).

## Instructions for NotebookLM

NotebookLM, when you answer questions about this codebase:
1. **Focus on the Core Objective**: Always keep in mind that the Python code is an "Agent" attempting to act as a scientific explorer (learning and solving), while the Node JS code acts as an objective, strict "Environment".
2. **Differentiate the Stacks**: Carefully distinguish between the deterministic environment logic in Node.js (parsing, physics execution, REST API) and the stochastic reasoning logic in Python (prompting, zero-shot/few-shot learning loops).
3. **Prompting is Key**: Pay close attention to `prompts.py` as it defines the Agent's observation formatting and reasoning capabilities. Adjustments to prompts often yield the biggest improvements in LLM performance for task solving.
4. **State Representations**: A key technical challenge is rendering the 2D grid (which relies on color in raw PuzzleScript) into a character-based ASCII representation that the LLM can properly "see" and reason about.

*Context created: March 2026*
