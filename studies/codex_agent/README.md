# Codex SDK Agent

This experiment replaces the custom ReAct loop with one persistent Codex SDK
session.

The first turn says "solve the game" and includes the initial ARC frame. Every
later turn sends the result of the previous action plus the new frame. Codex
returns exactly one next action. There are no experiment-owned tools, notes,
probe trees, rule languages, or separate planning loop.

The SDK reuses the Codex OAuth sign-in on this machine. It does not use
`OPENAI_API_KEY`, `OPENROUTER_API_KEY`, or a Kimi key.

On Windows, the runner automatically uses the newest Codex CLI bundled with the
installed Codex desktop app so current models work with the same OAuth session.
Use `--codex-bin` only if you want to override that executable.

## Run

Start the local PuzzleScript stack:

```powershell
npm run local
```

In another terminal:

```powershell
uv run python -m studies.codex_agent.run --game-id ps_sokoban_basic-v1 --max-steps 50
```

The defaults are `gpt-5.6-sol` with `low` reasoning effort, which corresponds
to Sol with Light reasoning in the Codex app.

Use `--no-window` for a headless run. Outputs are written under
`studies/codex_agent/output/<run-id>/`.

The same runner is available on the local workbench homepage. Run
`npm run workbench`, open `http://127.0.0.1:5173`, select **Codex Live**, choose
the game and step limit, and press **Start**.

## Boundaries

- One Codex SDK thread is kept alive for the whole game episode.
- Each turn receives the integer grid and, when available, the rendered PNG.
- The ARC environment is the authority on whether the game is solved.
- Codex runs read-only with approvals denied and is instructed not to inspect
  files or use coding tools.
