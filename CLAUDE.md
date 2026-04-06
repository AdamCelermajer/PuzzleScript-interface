# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A research framework for LLM agents that learn puzzle game mechanics by observing state transitions. Supports two environments:
1. **PuzzleScript** – custom games defined in `.txt` files, run via a local Node.js server
2. **ARC-AGI-3** – official benchmark tasks accessed through a remote REST API

## Two-Runtime Architecture

The project has a deliberate split: the PuzzleScript game engine only exists as an npm package, so a **Node.js Express server** wraps it and exposes a REST API. The **Python agent** communicates with that server over HTTP. Both processes must be running simultaneously for PuzzleScript tasks.

```
Python Agent (src/engine/)
    ↓ HTTP REST
Node.js Server (src/server.js)  ←→  PuzzleScript npm package
```

For ARC-AGI-3 tasks, the Python agent communicates directly with the remote API — no local server needed.

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

**Start the Node.js game server** (required for PuzzleScript only):
```bash
npm start          # production
npm run dev        # dev mode with auto-restart (nodemon)
```

**Run the Python agent:**
```bash
# PuzzleScript — learn game rules
python src/puzzlescript.py --game sokoban-basic --mode learn --max_steps 50

# PuzzleScript — solve using previously learned rules
python src/puzzlescript.py --game sokoban-basic --mode solve --max_steps 50

# ARC-AGI-3
python src/arc_agi.py --task task_001 --mode learn --max_steps 50
```

**Interactive human play (CLI client):**
```bash
npm run client     # loads sokoban-basic.txt by default
```

## Key Source Files

| File | Role |
|------|------|
| `src/server.js` | Node.js server — session management, game execution, REST API |
| `src/engine/agent.py` | Main agent — rule learning, rule-based solving |
| `src/engine/llm_client.py` | LLM abstraction via `litellm` (Gemini Flash/Pro) |
| `src/engine/prompts.py` | Prompt templates for legend inference, rule deduction, rule compression |
| `src/engine/types.py` | Shared types: `GameAction`, `GameState`, `FrameData` |
| `src/envs/puzzlescript_env.py` | HTTP adapter for the local Node.js server |
| `src/envs/arc_env.py` | HTTP adapter for the ARC-AGI-3 remote API |
| `src/envs/base_env.py` | Abstract `BaseEnv` interface (`reset()` / `step()`) |

## Data Flow

1. `env.reset()` → POST `/init` → server loads `.txt` game → returns `FrameData`
2. `env.step(action)` → POST `/action` → engine executes → returns `FrameData` (may contain multiple frames for animated rules)
3. `FrameData.frame` is a `list[list[list[int]]]` — a sequence of 2D integer grids (values 0–15)
4. `FrameData.legend` maps integers → object names (e.g. `{1: "player", 2: "wall"}`)

## Agent Learning Loop

- In **learn** mode: agent collects `(before_frame, action, after_frame)` tuples, periodically calls LLM to infer legend and deduce rules, saves results to `rules/<game>_rules.txt`
- In **solve** mode: agent loads existing rules and asks LLM to plan an action sequence toward the WIN state
- Rules are plain text with a structured format — see any file in `rules/` for the schema

## LLM Configuration

`llm_client.py` uses `litellm` to route calls. Default model is `gemini-3-flash-preview` (low thinking budget). Pro reasoning uses `gemini-3.1-pro-preview` with `thinkingLevel: "high"`. Switch models by editing `llm_client.py` — the abstraction makes swapping providers straightforward.

## Server REST API (actual behavior)

The real request/response shapes used by `puzzlescript_env.py`:

```
POST /init    body: { gameName: "sokoban-basic" } OR { gameSource: "<raw text>" }
POST /action  body: { sessionId, action: "ACTION1"|"ACTION2"|...|"RESET" }
GET  /observe query: ?sessionId=...
```

Actions map to: `ACTION1`=Up, `ACTION2`=Down, `ACTION3`=Left, `ACTION4`=Right, `ACTION5`=Space, `ACTION6`=Click.

### ARC-compatible adapter endpoints

For external ARC-AGI-3-style agents, use the dedicated FastAPI proxy `src/arc_agi_endpoint.py` (default port `8000`), which forwards requests to PuzzleScript `server.js`.

Proxy routes:

```
GET  /games
POST /scorecard/open
POST /cmd/RESET          body: { game_id, card_id } OR { game_id, card_id, guid }
POST /cmd/ACTION1..5     body: { game_id, guid }
GET  /observe            query: ?guid=...
GET  /health
```

Both surfaces return ARC-like fields (`frame`, `state`, `levels_completed`, `game_id`, `win_levels`, `guid`, `available_actions`, `action_input`).

## Coding Guidelines (from GEMINI.md)

- State assumptions before implementing; surface tradeoffs rather than picking silently
- Minimum code that solves the problem — no speculative abstractions
- Touch only what the task requires; do not refactor adjacent code
- Respect existing naming and architectural patterns exactly
