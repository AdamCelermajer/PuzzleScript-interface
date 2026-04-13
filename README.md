# PuzzleScript Interface

This repository has two supported workflows:

- Local PuzzleScript: run the bundled PuzzleScript games through the local Node.js runtime and ARC-compatible Python service.
- Official ARC-AGI-3: run the same `client/` agent directly against the hosted ARC backend.

Related docs:

- [`client/README.md`](client/README.md) for the client entry points, dashboard, and rule outputs.
- [`docs/architecture/arc-agi-architecture.svg`](docs/architecture/arc-agi-architecture.svg) for a research-oriented architecture sketch of the LLM-driven workflow.
- [`docs/research/`](docs/research/) for supporting research and specification materials.
- [`examples/basic_client.py`](examples/basic_client.py) for a small standalone client example.

## Install

```bash
npm install
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in the variables you need.

## Local PuzzleScript Workflow

Environment variables for agent runs:

- `GOOGLE_API_KEY` for the Gemini-based agent.
- `ARC_API_KEY` is not required for the local PuzzleScript stack.
- `OPENAI_API_KEY` is legacy and unused.

Manual local play with `client.play_arc_client` does not require these keys.

Start the PuzzleScript runtime:

```bash
npm start
```

Start the local ARC-compatible PuzzleScript service:

```bash
python -m puzzlescript_interface.api.main
```

Run the agent against the local service:

```bash
python -m client.run_arc_agent --backend-url http://localhost:8000 --game-id ps_sokoban_basic-v1 --mode learn --max_steps 50
```

Play a local PuzzleScript game manually from the terminal:

```bash
python -m client.play_arc_client --game-id ps_sokoban_basic-v1
```

## Official ARC-AGI-3 Workflow

Required environment variables:

- `GOOGLE_API_KEY` for the Gemini-based agent.
- `ARC_API_KEY` for the official ARC backend.
- `OPENAI_API_KEY` is legacy and unused.

Run the agent against the official ARC-AGI-3 backend:

```bash
python -m client.run_arc_agent --backend-url https://three.arcprize.org --game-id ls20 --mode learn --max_steps 50
```

## Tests

```bash
npm test
```
