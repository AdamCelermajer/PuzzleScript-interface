# Harnesses and the agents container

Every run (baseline, baseline-plus, campaign) is **one plain Docker container**
started by `python -m harnesses.launch`. Inside it, each agent role (direct player,
AVO optimizer, AVO player) is one persistent session of one harness:

| id | how a turn runs | resume | system prompt | images | web tools disabled by |
|---|---|---|---|---|---|
| `codex` | `codex exec --json --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox -m M -c model_reasoning_effort=E` | `codex exec ... resume -- <thread_id> <prompt>` | `-c developer_instructions=...` (every process) | `-i file` | `web_search="disabled"`, `features.browser_use/computer_use/apps/plugins=false` |
| `claude-code` | `claude -p <prompt> --output-format stream-json --verbose --model M --effort E --dangerously-skip-permissions` | `--session-id <uuid>` then `--resume <uuid>` | `--append-system-prompt` | base64 blocks via `--input-format stream-json` on stdin | `--disallowedTools WebSearch WebFetch` |
| `opencode` | `opencode run <prompt> --format json --thinking --dangerously-skip-permissions -m provider/model --variant E` | `--session <id>` | `instructions` file in a private `opencode.json` (`OPENCODE_CONFIG`) | `-f file` | `permission.webfetch/websearch/codesearch = "deny"` |
| `antigravity` | `agy -p <prompt> --output-format stream-json --dangerously-skip-permissions --model M --effort E` | `--conversation <id>` | prefixed to the first turn (no flag exists) | workspace path named in the prompt (no flag exists) | global `PreToolUse` hook in `~/.gemini/config/hooks.json` answering `{"decision":"deny"}` for `search_web`, `read_url_content`, `view_content_chunk`, `browser_*`, ... |
| `bare` | in-process chat-completions loop (OpenRouter/NanoGPT) with `shell`, `read_file`, `write_file`, `view_image` | same message list | system message | image parts | no web tools exist |

Effort is one of `low|medium|high|xhigh|max` (opencode/bare send `max` as `xhigh`).
Model ids: codex = bare OpenAI ids (`gpt-5.6-sol`); claude-code = `claude-*`;
opencode/bare = `openrouter/<vendor>/<model>` or `nanogpt/<model>` (opencode declares
the model in its config, NanoGPT as an OpenAI-compatible provider); antigravity =
ids from `agy models` (`gemini-3.8-flash-high`). `--provider SLUG` pins one
OpenRouter upstream (opencode/bare only).

Code: `base.py` (`CliSession.start/turn/close`, `TurnResult`, event log, subprocess
handling: stdin closed, timeout kills the process tree), one module per harness,
`chat.py` (bare transport), `registry.py` (ids, model validation, credentials,
`list_harnesses()` for the workbench), `launch.py` (host), `entry.py` (container),
`smoke.py`, `docker/Dockerfile`.

## Logs (every session)

`<analysis>/agent_events.jsonl` (schema `agent-event-v1`: message, reasoning,
command, file_change, tool, image, usage, error, turn_end), `<analysis>/raw/turn-<n>.jsonl`
(raw CLI stdout) and `.stderr.txt`, `session.json`, `system_prompt.txt`. Direct
runs use the run directory as `<analysis>`; campaigns use
`campaign/optimizer_analysis/` and `campaign/x_*/research/analysis/`.

## Launch

```powershell
docker build -t puzzlescript-agents:local harnesses/docker   # once, ~1.4 GB

uv run python -m harnesses.launch --mode baseline-plus --harness claude-code --model claude-haiku-5-5 `
  --effort low --game-id ps_modality-v1 --backend-url http://host.docker.internal:8000 --max-steps 50
uv run python -m harnesses.launch --mode campaign --harness opencode --model openrouter/qwen/qwen3.8-27b `
  --effort high --game-id ps_modality-v1 --backend-url http://host.docker.internal:8000 `
  --max-evaluations 8 --research-moves 400 --solver-moves 400 --world-model-mode final-only
uv run python -m harnesses.launch check [--harness H] [--deep]     # JSON readiness
uv run python -m harnesses.launch smoke --harness codex --model gpt-5.6-sol   # two tiny real turns
uv run python -m harnesses.launch login antigravity [--tui]       # once, interactive
```

Full options (contract §3): `--optimizer-model`, `--optimizer-effort`,
`--max-wall-seconds` (0 = unlimited), `--max-steps`, `--max-evaluations`,
`--research-moves`, `--solver-moves`, `--world-model-mode`, `--provider`,
`--resume` (campaign in DIR; refuses a different harness/provider/game/condition),
`--continue-from PARENT` (baseline modes; new DIR), `--dry-run`.
`localhost` backend URLs are rewritten to `host.docker.internal`.

Output layout is unchanged: campaigns default to `avo/output/runs/<id>/` with the
campaign in `<dir>/campaign/`; direct runs default to `studies/codex_agent/output/<id>/`.
The launcher writes `<dir>/run_spec.json` (also copied to `<dir>/campaign/` for
campaigns) and `<dir>/launcher.json` (`{"container": ...}`), and runs
`docker rm -f <container>` on exit.

## The container

Image `puzzlescript-agents:local` (`harnesses/docker/Dockerfile`, self-contained:
python 3.12 venv with the controller deps, node 22, `@openai/codex` 0.162.1,
`@anthropic-ai/claude-code` 2.1.299, `opencode-ai` 1.14.19, `agy` 1.3.5). Per run:

- controller source staged read-only at `/controller` (`avo`, `client`,
  `harnesses`, `studies/codex_agent`; only .py/.md/.txt/.toml; no games, no `.env`,
  no outputs, no tests);
- the output directory bound at `/results` (and a continuation parent at `/parent`, read-only);
- non-root user `agent`, `--cap-drop ALL`, `no-new-privileges`, memory/cpu/pids
  limits, normal network;
- only the chosen harness's credentials: codex copies `~/.codex/auth.json` (ChatGPT
  login) through a temporary read-only `/credentials` mount into a writable
  `$CODEX_HOME`; claude-code gets `CLAUDE_CODE_OAUTH_TOKEN`, opencode/bare get
  `OPENROUTER_API_KEY` / `NANOGPT_API_KEY`, all as `--env NAME` so values never
  appear in the command or `launcher.json`; antigravity mounts the volume
  `puzzlescript-agy-home` at `/home/agent/.gemini`.

Permission prompts are disabled in every CLI: the container is the sandbox, so
`CliSession.start` refuses to run outside a container (`HARNESS_CONTAINER=1`, set by
the launcher, or `/.dockerenv`) unless `HARNESS_ALLOW_HOST=1` is set. There
is no Codex sandbox, request proxy, request guard or ACL handling any more.
AVO solver evaluation runs `solver.py` as a plain subprocess in its own scratch
copy (no credentials in its environment, timeout per action and wall budget).

## Honest limits (accepted)

- The agent can read everything inside its container: the controller code in
  `/controller`, `/results` (its own run's outputs, including `run_spec.json`
  with the game id), and its own credentials (env vars, `~/.codex/auth.json`,
  `~/.gemini`). It never sees other runs, games sources or the host `.env`.
- Web search / fetch / browser tools are disabled **at the tool level only**. The
  shell has normal network access, so `curl` to the internet works.
- Containers can reach host services through `host.docker.internal` (on Docker
  Desktop even services bound to 127.0.0.1), e.g. the workbench API on 8010 or the
  Vite server on 5173. This is accepted for simplicity; nothing blocks it.
- `bare` keeps the API key in the controller process and strips credentials from
  its shell commands, but the same container also holds the key in the
  controller's environment.

## Antigravity login

`agy` stores its Google login under the user's home; on headless Linux it falls
back to file-based token storage (keyring unavailable). The image links
`~/.config/antigravity` into `~/.gemini/xdg-antigravity`, so whatever agy writes
under either path lands in the `puzzlescript-agy-home` volume.

1. `uv run python -m harnesses.launch login antigravity` in a real terminal.
2. agy prints a Google sign-in URL. Open it, approve, paste the code back within
   60 s (print mode's hard limit; `--tui` runs interactive agy without that limit,
   then type `/quit`).
3. The script then runs `agy models`; on success it writes
   `~/.gemini/.puzzlescript-login-ok` and prints "Antigravity login verified."
   `check --deep` re-probes it.

Runs refuse to start if the volume does not exist (so `docker run` cannot create
an empty, logged-out one). Concurrent agy runs share the volume.

Unverified until a login exists (2026-10-15): whether the token store really lands
in the volume, the exact `step_update` event fields (the normalizer is tolerant;
only the `result` event was observed), whether the deny hook fires under
`--dangerously-skip-permissions`, and agy's print-mode "terminal sandbox" (it
prints "Print mode: enabling terminal sandbox for this session") working without
capabilities. Run `smoke --harness antigravity --model gemini-3.8-flash-low` after
logging in.

## OpenCode on the host

Never install, upgrade or configure the host `opencode` (T3 Code depends on it).
Runs use the OpenCode inside the image. `OpenCodeSession` always sets private
`OPENCODE_CONFIG` and `XDG_*` directories, so even a host-side test touches no
real OpenCode state.
