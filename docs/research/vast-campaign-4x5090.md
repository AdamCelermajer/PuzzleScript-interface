# 800-move campaign on a rented 4×RTX 5090

Six runs as one workbench batch: OpenCode, Qwen3.8 27B FP8, 800 moves, both baselines, on Modality, IceCrates and
Knightoban. Everything is driven by `scripts/vast/campaign.py`. The server settings and their reasons are in
`vast-setup-20261021.md`; this page only adds what differs.

## Steps

Run from the repository root, with the game service and the workbench API up. `rent` starts billing, and from then
on the machine costs money until it stops.

```powershell
uv run python scripts/vast/campaign.py offers                # recheck prices (read-only)
uv run python scripts/vast/campaign.py rent <OFFER> --yes    # billing starts
uv run python scripts/vast/campaign.py setup                 # model download, the server: ~15 min
uv run python scripts/vast/campaign.py tunnels               # connects this PC to the server
uv run python scripts/vast/campaign.py check                 # a real call, then a 3-move batch
uv run python scripts/vast/campaign.py launch --yes          # the 6-run batch, plus the watcher
uv run python scripts/vast/campaign.py status                # any time: health, recording, the machine's cost so far
uv run python scripts/vast/campaign.py resume <RUN FOLDER>   # by hand; the watcher does this itself
uv run python scripts/vast/campaign.py destroy --yes         # ends the rental; the watcher does this itself
```

The batch goes through `POST /api/workbench/runs`, so it appears in the workbench like any other (`vast-check` and
`vast-4x5090-800-xhigh`). Stop it there or with the script.

The watcher runs on this PC, apart from any chat, and every 2 minutes:

- Resumes a run that stopped early or made no move and no model call for 20 minutes, at most 20 times per game and
  driver, and only while the workbench, game service and model server answer. A resume is a new run in its own batch:
  the same board (the moves are replayed and checked), the same files and the same move count, in a new conversation,
  so what the model had in mind is lost. The first message says so. `--restore-context` is not used: its session did
  not exit in testing.
- Ends the rental when every run is done or out of resumes, after 40 minutes with nothing running, or after
  `--max-hours` (default 14). It copies the server's log to `output/vast/logs`, destroys the instance, checks that the
  account no longer lists it and closes the tunnel. Results are on this PC throughout. Destroying leaves no storage
  charge, and the model must be downloaded again for another campaign.

## What is set

| | Value |
|---|---|
| Image | `vastai/vllm:v0.31.0-cuda-13.0`, 150 GB disk |
| Weights | `Qwen/Qwen3.8-27B-FP8` (public, 29 GB) |
| Server | all 4 GPUs on port 18000, the 21 Oct flags: FP8 KV cache, MTP 2, prefix caching, 262,144 context, up to 16 sequences |
| This PC | `localhost:18100`, by SSH with `~/.ssh/vastai_ed25519`, reconnecting by itself |
| OpenCode | `vast/q3.8-27b-fp8`, reached at `host.docker.internal:18100`; the harness writes its provider, limits and thinking at session start |
| Thinking | xhigh, set by the server and sent by the harness in every request |
| Sampling | temperature 1.0, top_p 0.95, top_k 20: the server's defaults, as on 21 Oct |
| Compaction | OpenCode's own, at 198,144 tokens |
| Turn limit | 7,200 s for turn-based (1,800 s ended two runs on 4 Nov); agentic turns have no limit |
| Early stop | none: runs go to 800 moves or the end of the game |
| Budget number | shown to the player |

## Not tested until a machine is rented

Checked without renting: the batch against the workbench's own validation, each run's launch command (dry run), the
script syntax, the rental request's fields against vast's own CLI, the image tag, the model and the SSH key on the
account. The first real test of these is `setup` and `check`:

- The rental request itself.
- This machine's speed. On 21 Oct a 4×5090 in Texas gave 816 tok/s total with 10 games; the time estimates scale from that.
- The workbench's price column: it reads usage from each model call, which a self-hosted server does not price, so
  `status` is where the machine's cost shows.
