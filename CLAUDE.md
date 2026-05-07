# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A research framework for LLM agents that learn puzzle game mechanics by observing state transitions. Supports two environments:
1. **PuzzleScript** - local games stored as `puzzlescript_interface/games/<name>/script.txt`, run via a local Node.js runtime plus ARC-compatible Python service
2. **ARC-AGI-3** - official benchmark tasks accessed through a remote REST API

## Repo Layout

The repository is organized into two product folders:

- `client/` - the generic ARC-compatible client. This includes the agent, ARC toolkit adapter, terminal dashboard, and inferred rules in `client/rules/`.
- `puzzlescript_interface/` - the local PuzzleScript implementation of an ARC-compatible challenge surface. This includes the PuzzleScript games, Node.js runtime, and FastAPI adapter.

## Runtime Architecture

The project has a deliberate split: the PuzzleScript game engine only exists as an npm package, so a **Node.js Express server** wraps it and exposes an internal REST API. A separate **Python ARC-compatible service** adapts that runtime into the public ARC-AGI-3 contract, and the **Python agent** talks only to that ARC surface.

```
Python Agent (client/engine/)
    -> ARC toolkit / ARC REST
PuzzleScript ARC Service (puzzlescript_interface/api/app.py)
    -> internal HTTP REST
Node.js Server (puzzlescript_interface/runtime/server.js) <-> PuzzleScript npm package
```

For official ARC-AGI-3 tasks, the Python agent communicates directly with the remote API through the same ARC toolkit path.

## Setup & Running

**Install dependencies (once):**
```bash
npm install
pip install -r requirements.txt
```

**Environment variables** - copy `.env.example` and fill in:
- `OPENROUTER_API_KEY` - OpenRouter API, required for agent LLM calls
- `ARC_API_KEY` - ARC-AGI-3 official API, required only for official ARC-AGI-3 runs
- `OPENAI_API_KEY` - legacy, unused
- `PORT` - optional port override for the Node.js PuzzleScript runtime
- `ARC_PROXY_PORT` - optional port override for the local ARC-compatible Python service
- `PUZZLESCRIPT_SERVER_URL` - optional URL override for the Python service to reach the Node.js runtime

**Start the local PuzzleScript stack**:
```bash
npm run local
```

Closing that terminal or pressing Ctrl+C stops both owned child processes.

**Run the Python agent:**
```bash
python -m client.run_arc_agent --backend-url http://localhost:8000 --game-id ps_sokoban_basic-v1 --mode learn --max_steps 50
```

**Interactive human play:**
```bash
python -m client.play_arc_client --game-id ps_sokoban_basic-v1
```

## Key Source Files

| File | Role |
|------|------|
| `puzzlescript_interface/runtime/server.js` | Node.js PuzzleScript runtime |
| `puzzlescript_interface/api/app.py` | ARC-compatible PuzzleScript service |
| `client/engine/agent.py` | Main LLM engine orchestrator |
| `client/engine/arcade_env.py` | ARC toolkit adapter |
| `client/engine/llm_client.py` | LLM abstraction via `litellm` and OpenRouter |
| `client/engine/prompts.py` | Prompt template for LLM rule-hypothesis induction |
| `client/engine/types.py` | Shared types: `GameAction`, `GameState`, `FrameData` |
| `client/engine/base_env.py` | Abstract `BaseEnv` interface |
| `client/run_arc_agent.py` | Generic CLI runner for ARC-compatible backends |

## Agent Learning Loop

- In **learn** mode: agent perceives `FrameData`, records `(before_state, action, after_state)` evidence, creates executable transition memory from observed transitions, and periodically asks the LLM for non-executable rule hypotheses.
- In **solve** mode: the planner searches over verified executable transition memory. If no verified plan exists, the LLM proposes a subgoal and short legal action plan; the engine executes it and records the real transition as evidence.
- Rule artifacts are stored under `client/rules/<game-id>/` as `transitions.jsonl`, `rules.json`, `rules.md`, and `journal.md`.

## LLM Configuration

`client/engine/llm_client.py` routes calls through OpenRouter with `deepseek/deepseek-v4-pro` for both flash and pro paths.

## Coding Guidelines

- State assumptions before implementing; surface tradeoffs rather than picking silently.
- Minimum code that solves the problem; no speculative abstractions.
- Touch only what the task requires; do not refactor adjacent code.
- Respect existing naming and architectural patterns exactly.
