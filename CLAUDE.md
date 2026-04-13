# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A research framework for LLM agents that learn puzzle game mechanics by observing state transitions. Supports two environments:
1. **PuzzleScript** – local games stored as `games/<name>/script.txt`, run via a local Node.js server
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
pip install -r requirements.txt   # Python deps
```

**Environment variables** — copy `.env.example` and fill in:
- `GOOGLE_API_KEY` — Gemini API (primary LLM)
- `ARC_API_KEY` — ARC-AGI-3 official API
- `OPENAI_API_KEY` — legacy, unused

**Start the Node.js PuzzleScript runtime** (required for local PuzzleScript only):
```bash
npm start          # production
npm run dev        # dev mode with auto-restart (nodemon)
```

**Start the local PuzzleScript ARC service** (required for local PuzzleScript only):
```bash
python -m puzzlescript_interface.api.main
```

**Run the Python agent:**
```bash
# Local PuzzleScript via the ARC-compatible service
python -m client.run_arc_agent --backend-url http://localhost:8000 --game-id sokoban-basic --mode learn --max_steps 50

# Official ARC-AGI-3
python -m client.run_arc_agent --backend-url https://three.arcprize.org --game-id ls20 --mode learn --max_steps 50
```

**Interactive human play (CLI client):**
```bash
python -m client.play_arc_client --game-id sokoban-basic
```

## Key Source Files

| File | Role |
|------|------|
| `puzzlescript_interface/runtime/server.js` | Node.js PuzzleScript runtime — session management, game execution, internal REST API |
| `puzzlescript_interface/api/app.py` | ARC-compatible PuzzleScript service — game catalog, scorecards, `/api/...` routes |
| `client/engine/agent.py` | Main agent — rule learning, rule-based solving |
| `client/engine/arcade_env.py` | ARC toolkit adapter used by the engine for both local PuzzleScript and official ARC |
| `client/engine/llm_client.py` | LLM abstraction via `litellm` (Gemini Flash/Pro) |
| `client/engine/prompts.py` | Prompt templates for legend inference, rule deduction, rule compression |
| `client/engine/types.py` | Shared types: `GameAction`, `GameState`, `FrameData` |
| `client/engine/base_env.py` | Abstract `BaseEnv` interface (`reset()` / `step()`) |
| `client/run_arc_agent.py` | Generic CLI runner for ARC-compatible backends |

## Data Flow

1. `env.reset()` → ARC toolkit RESET → local service `/api/cmd/RESET` → PuzzleScript service loads `games/<game-id>/script.txt` internally
2. `env.step(action)` → ARC toolkit ACTION → local service `/api/cmd/ACTION...` → PuzzleScript runtime executes and returns `FrameData`
3. `FrameData.frame` is a `list[list[list[int]]]` — a sequence of 2D integer grids (values 0–15)
4. `FrameData.legend` is optional debug metadata only and should not be relied on by ARC-compatible code

## Agent Learning Loop

- In **learn** mode: agent collects `(before_frame, action, after_frame)` tuples, periodically calls LLM to infer legend and deduce rules, saves results to `client/rules/<game>_rules.txt`
- In **solve** mode: agent loads existing rules and asks LLM to plan an action sequence toward the WIN state
- Rules are plain text with a structured format — see any file in `client/rules/` for the schema

## LLM Configuration

`llm_client.py` uses `litellm` to route calls. Default model is `gemini-3-flash-preview` (low thinking budget). Pro reasoning uses `gemini-3.1-pro-preview` with `thinkingLevel: "high"`. Switch models by editing `llm_client.py` — the abstraction makes swapping providers straightforward.

## Server REST API (internal behavior)

The real request/response shapes used by `puzzlescript_env.py`:

```
POST /init    body: { gameName: "sokoban-basic" } OR { gameSource: "<raw text>" }
POST /action  body: { sessionId, action: "ACTION1"|"ACTION2"|...|"RESET" }
GET  /observe query: ?sessionId=...
```

Actions map to: `ACTION1`=Up, `ACTION2`=Down, `ACTION3`=Left, `ACTION4`=Right, `ACTION5`=Space, `ACTION6`=Click.

### ARC-compatible adapter endpoints

For ARC-AGI-3-style agents, use the dedicated FastAPI service `puzzlescript_interface/api/app.py` via `puzzlescript_interface/api/main.py` (default port `8000`), which forwards requests to the PuzzleScript runtime in `puzzlescript_interface/runtime/server.js`.

Proxy routes:

```
GET  /api/games
POST /api/scorecard/open
GET  /api/scorecard/{card_id}
POST /api/scorecard/close
POST /api/cmd/RESET      body: { game_id, card_id } OR { game_id, card_id, guid }
POST /api/cmd/ACTION1..5 body: { game_id, guid }
```

The public ARC surface returns ARC fields (`frame`, `state`, `levels_completed`, `game_id`, `win_levels`, `guid`, `available_actions`, `action_input`).

## Coding Guidelines (from GEMINI.md)

- State assumptions before implementing; surface tradeoffs rather than picking silently
- Minimum code that solves the problem — no speculative abstractions
- Touch only what the task requires; do not refactor adjacent code
- Respect existing naming and architectural patterns exactly
