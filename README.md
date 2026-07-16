# PuzzleScript Interface

This repository has two core runtime workflows and two research studies:

- Local PuzzleScript: run the bundled PuzzleScript games through the local Node.js runtime and ARC-compatible Python service.
- Official ARC-AGI-3: run the same `client/` agent directly against the hosted ARC backend.
- Goal recognition study: see `studies/goal_recognition/` for the dataset, prompts, model outputs, review tools, and static results website.
- LIVE framework study: see `studies/LIVE_framework/` for the LIVE-style Sokoban rule-learning POC.

Related docs:

- [`client/README.md`](client/README.md) for the client entry points, dashboard, and rule outputs.
- [`docs/architecture/arc-agi-architecture.svg`](docs/architecture/arc-agi-architecture.svg) for a research-oriented architecture sketch of the LLM-driven workflow.
- [`docs/research/`](docs/research/) for supporting research and specification materials.
- [`examples/basic_client.py`](examples/basic_client.py) for a small standalone client example.
- [`studies/goal_recognition/README.md`](studies/goal_recognition/README.md) for goal-recognition study commands and artifacts.
- [`studies/LIVE_framework/README.md`](studies/LIVE_framework/README.md) for LIVE framework study commands and artifacts.

## Install

```bash
npm install
uv sync
```

> Pip fallback: if you are not using uv, you can still run `pip install -r requirements.txt` and use `python` directly.

Copy `.env.example` to `.env` and fill in the variables you need.

## Local PuzzleScript Workflow

Environment variables for agent runs:

- `OPENROUTER_API_KEY` for the default OpenRouter-backed agent model.
- `ARC_API_KEY` is not required for the local PuzzleScript stack.
- `OPENAI_API_KEY` is legacy and unused.

Manual local play with `client.play_arc_client` does not require these keys.

Start the local stack in one terminal:

```bash
npm run local
```

This starts both the PuzzleScript runtime and the ARC-compatible Python service.
Closing the terminal or pressing Ctrl+C stops both owned child processes.

Start the professor demo workbench and all local services:

```bash
npm run workbench
```

Open `http://127.0.0.1:5173`. The home page runs the main client agent with
Fresh/Resume controls, local PuzzleScript or official ARC selection, and live
views of frames, plans, natural hypotheses, verified rules, failures, and logs.
The Settings tab identifies OpenRouter as the LLM provider and offers Claude
Opus 4.8 (default), GPT-5.6 Luna, Grok 4.5, and MiMo-V2.5. A reasoning-effort
selector appears only for models that expose supported effort levels. It also
checks the current OpenRouter key, displays its usage and remaining limit, and
can validate and replace `OPENROUTER_API_KEY` in the local `.env`. The key is
shown as plain text in this local-only workbench.

If you only need the PuzzleScript runtime:

```bash
npm start
```

Run the agent against the local service:

```bash
uv run python -m client.run_arc_agent --backend-url http://localhost:8000 --game-id ps_sokoban_basic-v1 --max_steps 50
```

The CLI runner is headless and prints ordinary progress logs. The browser
workbench is the primary agent interface.

Play a local PuzzleScript game manually from the terminal:

```bash
uv run python -m client.play_arc_client --game-id ps_sokoban_basic-v1
```

## Official ARC-AGI-3 Workflow

Required environment variables:

- `OPENROUTER_API_KEY` for the default OpenRouter-backed agent model.
- `ARC_API_KEY` for the official ARC backend.
- `OPENAI_API_KEY` is legacy and unused.

Run the agent against the official ARC-AGI-3 backend:

```bash
uv run python -m client.run_arc_agent --backend-url https://three.arcprize.org --game-id ls20 --max_steps 50
```

## Tests

```bash
npm test
```
