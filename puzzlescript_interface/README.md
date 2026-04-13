# PuzzleScript Interface

`puzzlescript_interface/` contains the local PuzzleScript workflow used by the root README:

- `runtime/` contains the Node.js PuzzleScript runtime.
- `api/` contains the ARC-compatible Python service.
- `games/` contains PuzzleScript game folders in the `name/script.txt` layout.

## Run Locally

From the repository root, start the PuzzleScript runtime:

```bash
npm start
```

Start the local ARC-compatible PuzzleScript service:

```bash
python -m puzzlescript_interface.api.main
```

Then run the client from the repository root:

```bash
python -m client.run_arc_agent --backend-url http://localhost:8000 --game-id ps_sokoban_basic-v1 --mode learn --max_steps 50
```

This agent command requires `GOOGLE_API_KEY`.

The runtime writes session history under the ignored `puzzlescript_interface/.runtime/` directory.
