# PuzzleScript Interface

`puzzlescript_interface/` contains the local PuzzleScript implementation of the
ARC-compatible challenge surface used by the client.

## Contents

- `runtime/` contains the Node.js PuzzleScript runtime wrapper.
- `api/` contains the FastAPI ARC-compatible adapter.
- `games/` contains the local PuzzleScript `.txt` sources.
- `manifest.json` is the starting point for catalog metadata and future benchmark curation.

## Run Locally

Start the PuzzleScript runtime:

```bash
node puzzlescript_interface/runtime/server.js
```

Start the ARC-compatible adapter:

```bash
python -m puzzlescript_interface.api.main
```

The runtime writes session history under the ignored `puzzlescript_interface/.runtime/` directory.
