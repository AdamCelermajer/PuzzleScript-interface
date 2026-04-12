# PuzzleScript Interface

This repository is organized around two top-level products:

- `client/` is the generic ARC-compatible client. It contains the agent, ARC environment adapter, terminal UI, and inferred rules stored in `client/rules/`.
- `puzzlescript_interface/` is the local PuzzleScript implementation of an ARC-compatible challenge surface. It contains the PuzzleScript games, the Node runtime, and the FastAPI adapter.

## Structure

```text
client/
  engine/
  run_arc_agent.py
  play_arc_client.py
  terminal_dashboard.py
  rules/

puzzlescript_interface/
  api/
  runtime/
  games/
  manifest.json
```

## Setup

```bash
npm install
pip install -r requirements.txt
```

## Run The Local PuzzleScript Stack

Start the PuzzleScript runtime:

```bash
npm start
```

Start the ARC-compatible adapter:

```bash
python -m puzzlescript_interface.api.main
```

Run the learning agent against the local stack:

```bash
python -m client.run_arc_agent --backend-url http://localhost:8000 --game-id sokoban-basic-v1 --mode learn --max_steps 50
```

Play manually from the terminal:

```bash
python -m client.play_arc_client --game-id sokoban-basic-v1
```

## Official ARC-AGI-3

The same `client/` code can talk directly to the official ARC-AGI-3 backend:

```bash
python -m client.run_arc_agent --backend-url https://three.arcprize.org --game-id ls20 --mode learn --max_steps 50
```

## Tests

```bash
npm test
```
