# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A research framework for LLM agents that learn puzzle game mechanics by observing state transitions. Supports two environments:
1. **PuzzleScript** – custom games defined in `.txt` files, run via a local Node.js server
2. **ARC-AGI-3** – official benchmark tasks accessed through a remote REST API

## Two-Runtime Architecture

The project has a deliberate split: the PuzzleScript game engine only exists as an npm package, so a **Node.js Express server** wraps it and exposes an internal REST API. A separate **Python ARC-compatible service** adapts that runtime into the public ARC-AGI-3 contract, and the **Python agent** talks only to that ARC surface.

```
Python Agent (src/engine/)
    ↓ ARC toolkit / ARC REST
PuzzleScript ARC Service (src/puzzlescript_arc/app.py)
    ↓ internal HTTP REST
Node.js Server (src/server.js)  ←→  PuzzleScript npm package
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
python src/arc_agi_endpoint.py
```

**Run the Python agent:**
```bash
# Local PuzzleScript via the ARC-compatible service
python src/run_arc_agent.py --backend-url http://localhost:8000 --game-id sokoban-basic-v1 --mode learn --max_steps 50

# Official ARC-AGI-3
python src/run_arc_agent.py --backend-url https://three.arcprize.org --game-id ls20 --mode learn --max_steps 50
```

**Interactive human play (CLI client):**
```bash
python src/play_arc_client.py --game-id sokoban-basic-v1
```

## Key Source Files

| File | Role |
|------|------|
| `src/server.js` | Node.js PuzzleScript runtime — session management, game execution, internal REST API |
| `src/puzzlescript_arc/app.py` | ARC-compatible PuzzleScript service — game catalog, scorecards, `/api/...` routes |
| `src/engine/agent.py` | Main agent — rule learning, rule-based solving |
| `src/engine/arcade_env.py` | ARC toolkit adapter used by the engine for both local PuzzleScript and official ARC |
| `src/engine/llm_client.py` | LLM abstraction via `litellm` (Gemini Flash/Pro) |
| `src/engine/prompts.py` | Prompt templates for legend inference, rule deduction, rule compression |
| `src/engine/types.py` | Shared types: `GameAction`, `GameState`, `FrameData` |
| `src/engine/base_env.py` | Abstract `BaseEnv` interface (`reset()` / `step()`) |
| `src/run_arc_agent.py` | Generic CLI runner for ARC-compatible backends |

## Data Flow

1. `env.reset()` → ARC toolkit RESET → local service `/api/cmd/RESET` → PuzzleScript service loads the `.txt` game internally
2. `env.step(action)` → ARC toolkit ACTION → local service `/api/cmd/ACTION...` → PuzzleScript runtime executes and returns `FrameData`
3. `FrameData.frame` is a `list[list[list[int]]]` — a sequence of 2D integer grids (values 0–15)
4. `FrameData.legend` is optional debug metadata only and should not be relied on by ARC-compatible code

## Agent Learning Loop

- In **learn** mode: agent collects `(before_frame, action, after_frame)` tuples, periodically calls LLM to infer legend and deduce rules, saves results to `rules/<game>_rules.txt`
- In **solve** mode: agent loads existing rules and asks LLM to plan an action sequence toward the WIN state
- Rules are plain text with a structured format — see any file in `rules/` for the schema

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

For ARC-AGI-3-style agents, use the dedicated FastAPI service `src/puzzlescript_arc/app.py` via `src/arc_agi_endpoint.py` (default port `8000`), which forwards requests to PuzzleScript `server.js`.

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
