# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

A research framework for LLM agents that learn puzzle game mechanics by observing state transitions. Supports two environments:
1. **PuzzleScript** – local games stored as `puzzlescript_interface/games/<name>/script.txt`, run via a local Node.js runtime plus ARC-compatible Python service
2. **ARC-AGI-3** – official benchmark tasks accessed through a remote REST API

## Repo Layout

The repository is organized into two product folders:

- `client/` — the generic ARC-compatible client. This includes the agent, ARC toolkit adapter, terminal dashboard, and inferred rules in `client/rules/`.
- `puzzlescript_interface/` — the local PuzzleScript implementation of an ARC-compatible challenge surface. This includes the PuzzleScript games, Node.js runtime, and FastAPI adapter.

## Runtime Architecture

The project has a deliberate split: the PuzzleScript game engine only exists as an npm package, so a **Node.js Express server** wraps it and exposes an internal REST API. A separate **Python ARC-compatible service** adapts that runtime into the public ARC-AGI-3 contract, and the **Python agent** talks only to that ARC surface.

```
Python Agent (client/engine/)
    ↓ ARC toolkit / ARC REST
PuzzleScript ARC Service (puzzlescript_interface/api/app.py)
    ↓ internal HTTP REST
Node.js Server (puzzlescript_interface/runtime/server.js)  ←→  PuzzleScript npm package
```

For official ARC-AGI-3 tasks, the Python agent communicates directly with the remote API through the same ARC toolkit path.

## Setup & Running

**Install dependencies (once):**
```bash
npm install        # Node.js deps
uv sync            # Python deps (pip fallback: `pip install -r requirements.txt`)
```

**Environment variables** — copy `.env.example` and fill in:
- `OPENROUTER_API_KEY` — OpenRouter API (required for default agent runs)
- `ARC_API_KEY` — ARC-AGI-3 official API (required only for official ARC-AGI-3 runs)
- `OPENAI_API_KEY` — legacy, unused
- `PORT` — optional port override for the Node.js PuzzleScript runtime (default `3000`)
- `ARC_PROXY_PORT` — optional port override for the local ARC-compatible Python service (default `8000`)
- `PUZZLESCRIPT_SERVER_URL` — optional URL override for the Python service to reach the Node.js runtime

**Start the local PuzzleScript stack** (runtime + ARC service, one terminal):
```bash
npm run local
```

Closing that terminal or pressing Ctrl+C stops both owned child processes.

**Start only the Node.js PuzzleScript runtime**:
```bash
npm start          # production
npm run dev        # dev mode with auto-restart (nodemon)
```

**Start only the local PuzzleScript ARC service**:
```bash
uv run python -m puzzlescript_interface.api.main
```

**Run the Python agent:**
```bash
# Local PuzzleScript via the ARC-compatible service
uv run python -m client.run_arc_agent --backend-url http://localhost:8000 --game-id ps_sokoban_basic-v1 --mode learn --max_steps 50

# Official ARC-AGI-3
uv run python -m client.run_arc_agent --backend-url https://three.arcprize.org --game-id ls20 --mode learn --max_steps 50
```

**Interactive human play (CLI client):**
```bash
uv run python -m client.play_arc_client --game-id ps_sokoban_basic-v1
```

## Key Source Files

| File | Role |
|------|------|
| `puzzlescript_interface/runtime/server.js` | Node.js PuzzleScript runtime — session management, game execution, internal REST API |
| `puzzlescript_interface/api/app.py` | ARC-compatible PuzzleScript service — game catalog, scorecards, `/api/...` routes |
| `client/engine/agent.py` | Main agent — rule learning, rule-based solving |
| `client/arc/arcade_env.py` | ARC toolkit adapter used by the engine for both local PuzzleScript and official ARC |
| `client/engine/llm_client.py` | LLM abstraction via `litellm` and OpenRouter |
| `client/engine/goal_manager.py` | Game goal and subgoal prompt ownership |
| `client/engine/induction.py` | Rule-induction prompt and candidate verification entrypoint |
| `client/arc/types.py` | Shared ARC types: `GameAction`, `GameState`, `FrameData` |
| `client/arc/base_env.py` | Abstract `BaseEnv` interface (`reset()` / `step()`) |
| `client/runtime/runner.py` | Runtime action execution and rule-reasoning loop |
| `client/run_arc_agent.py` | Generic CLI runner for ARC-compatible backends |

## Data Flow

1. `env.reset()` → ARC toolkit RESET → local service `/api/cmd/RESET` → PuzzleScript service loads `puzzlescript_interface/games/<game-id>/script.txt` internally
2. `env.step(action)` → ARC toolkit ACTION → local service `/api/cmd/ACTION...` → FastAPI adapter forwards the action to the PuzzleScript runtime and returns `FrameData`
3. `FrameData.frame` is a `list[list[list[int]]]` — a sequence of 2D integer grids (values 0–15)
4. `FrameData.legend` is not currently populated by the ARC adapter and should not be relied on by ARC-compatible code

## Agent Learning Loop

- In **learn** mode: agent perceives `FrameData`, records `(before_state, action, after_state)` evidence, creates executable transition rules from verified observations, and periodically asks the LLM for non-executable rule hypotheses.
- In **solve** mode: the planner searches over verified executable rules. If no verified plan exists, the LLM proposes a subgoal and short legal action plan; the engine executes it and records the real transition as evidence.
- Rule artifacts are stored under `client/rules/<game-id>/` as `transitions.jsonl`, `rules.json`, `rules.md`, and `journal.md`.

## LLM Configuration

`llm_client.py` uses `litellm` to route calls through OpenRouter. The default model is `openai/gpt-5.5` with low reasoning effort. Calls carry a `purpose` label so routing can be customized later without reintroducing model tiers.

## Server REST API (internal behavior)

The real request/response shapes used by `puzzlescript_interface/api/client.py`:

```
POST /init    body: { gameName: "ps_sokoban_basic-v1" } OR { gameSource: "<raw text>" }
POST /action  body: { sessionId, action: "ACTION1"|"ACTION2"|...|"RESET" }
GET  /observe query: ?sessionId=...
```

Actions map to: `ACTION1`=Up, `ACTION2`=Down, `ACTION3`=Left, `ACTION4`=Right, `ACTION5`=Space/Action, `ACTION7`=Undo. `ACTION6` is not supported by the ARC-compatible adapter.

### ARC-compatible adapter endpoints

For ARC-AGI-3-style agents, use the dedicated FastAPI service `puzzlescript_interface/api/app.py` via `puzzlescript_interface/api/main.py` (default port `8000`), which forwards requests to the PuzzleScript runtime in `puzzlescript_interface/runtime/server.js`.

Proxy routes:

```
GET  /api/games
GET  /api/games/{game_id}
POST /api/scorecard/open
GET  /api/scorecard/{card_id}
POST /api/scorecard/close
POST /api/cmd/RESET      body: { game_id, card_id } OR { game_id, card_id, guid }
POST /api/cmd/ACTION1..5 body: { game_id, guid }
POST /api/cmd/ACTION7    body: { game_id, guid }
```

The public ARC surface returns ARC fields (`frame`, `state`, `levels_completed`, `game_id`, `win_levels`, `guid`, `available_actions`, `action_input`).

## Coding Guidelines

- State assumptions before implementing; surface tradeoffs rather than picking silently
- Minimum code that solves the problem — no speculative abstractions
- Touch only what the task requires; do not refactor adjacent code
- Respect existing naming and architectural patterns exactly
