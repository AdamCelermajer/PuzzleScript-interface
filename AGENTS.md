# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

A research framework for LLM agents that learn puzzle game mechanics by observing state transitions. Supports two environments:
1. **PuzzleScript** – local games stored as `puzzlescript_interface/games/<name>/script.txt`, run via a local Node.js runtime plus ARC-compatible Python service
2. **ARC-AGI-3** – official benchmark tasks accessed through a remote REST API

## Repo Layout

The maintained workflows are the frameworks `avo` (campaigns), `baseline` (the minimal harness, no outer method; `--driver controller|agent` sets who drives the game; the controller always gives the agent a `notes/` folder to keep its working memory in), and `harness2` (score-aware Harness²: a coach edits the harness of an agent that plays through a game command). The browser homepage is a run catalog, not the historical rule agent.

- `website/app/` and `workbench/` — the workbench single-page app (React) and its FastAPI backend: runs, launch, benchmarks, diary, tools. Code and studies no longer used are kept in `archive/` (not imported, not tested).
- `frameworks/` — agent methods, one folder each (`baseline/`: the player without an outer method, `run.py` when our controller drives and `agent.py` when the agent drives through `game.py`, continuation and batches; `avo/`: AVO research/evolution, prompts and evaluation), declared through `Framework`/`Option` in `base.py` and listed in `registry.py`. Adding a framework = one folder with `framework.py` + one line in `registry.py`. See `frameworks/README.md`.
- `harnesses/` — agent harnesses (codex, claude-code, opencode, antigravity, bare) and `python -m harnesses.launch --framework <id> --harness <id> ...`, which runs every run in one Docker container. See `harnesses/README.md`.
- Run outputs: new CLI runs default to `output/<framework>/<run>`, workbench launches to `output/workbench/<job>/run-NNNN`; older runs stay in `avo/output/` and `studies/codex_agent/output/` (archives the catalog still reads).

Shared environment code and historical client:

- `client/` — shared ARC adapter/types plus the historical rule-learning agent, utilities and manual-play display. Do not move this folder wholesale: maintained runners import from it.
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

**Environment variables** — each harness has one provider: Codex uses the existing Codex OAuth login (`~/.codex/auth.json`), Claude Code uses `CLAUDE_CODE_OAUTH_TOKEN`, OpenCode and bare use `OPENROUTER_API_KEY` / `NANOGPT_API_KEY`, Antigravity uses the `puzzlescript-agy-home` Docker volume (`uv run python -m harnesses.launch login antigravity`). Optional `.env.example` settings:
- `OPENROUTER_API_KEY` — OpenRouter API (AVO OpenRouter models and the historical rule agent)
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

**Historical rule-agent CLI:**
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
| `client/engine/agent.py` | Historical agent — rule learning, rule-based solving |
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
3. `FrameData.frame` is a `list[list[list[int]]]`. Local PuzzleScript globally defaults to `visible-cell-v1`: one ID per rendered tile texture, values 0–65535. Identical visible pixels share an ID even when hidden objects differ. Official ARC retains its own 0–15 contract. `PUZZLESCRIPT_GRID_ENCODING=visible-cell-hex-v2` explicitly enables the legacy 2×2 hexadecimal encoding; never select encoding by game title.
4. `FrameData.legend` is not currently populated by the ARC adapter and should not be relied on by ARC-compatible code

## Historical Rule-Agent Learning Loop

- In **learn** mode: agent perceives `FrameData`, records `(before_state, action, after_state)` evidence, and asks the LLM for executable logical rules that can be checked against the timeline.
- In **solve** mode: the planner simulates with known logical rules. If no rule plan exists, the LLM proposes a subgoal and short legal action plan; the engine executes it and records the real transition as evidence.
- Rule artifacts are stored under `client/rules/<game-id>/` as `timeline.jsonl` and `rules.json`. Use `client.inspect_rules` for a readable debug view.

## Historical Rule-Agent LLM Configuration

`llm_client.py` routes calls through OpenRouter. The default model is `anthropic/claude-opus-4.8` with low reasoning effort disabled unless configured. Calls carry a `purpose` label so routing can be customized later without reintroducing model tiers.

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

## Current workbench

`npm run workbench` starts or reuses the local services and serves the SPA (`website/app/`) on port 5173 (any hostname, e.g. Tailscale). Sections: Runs, Launch, Run detail, Compare, Benchmarks, Diary, Tools. Every launch goes through `POST /api/workbench/runs` (`frameworks: [{id, options}]`, framework list from `GET /api/workbench/frameworks`) → `python -m harnesses.launch --framework ...`. `workbench/catalog.py` discovers existing output paths without moving them; Docker process status and worker heartbeats are distinct from recorded solver success. `workbench/experiment_job.py` runs bounded subprocess batches with persistent manifests and exact ownership for stops. Never restart shared game services as part of a website refresh. See `docs/architecture/workbench.md`.

## Diary

At the end of a substantial work session (new results, decisions, experiments or a feature), add or update one entry in `docs/diary/` (`YYYY-MM-DD-<slug>.md`, sections `## Did`, `## Found`, `## Decided`, `## Next`), following `docs/diary/README.md`. Keep it terse and factual, cite commits, docs and runs, and register any new thread in the README's thread table. Runs started that day are linked automatically by `workbench/diary.py`.
