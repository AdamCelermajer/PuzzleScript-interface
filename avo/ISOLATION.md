# AVO experiment isolation (version 1)

Docker/Linux alternative: see [docker/README.md](docker/README.md). The native
Windows limitation below remains; the Docker launcher passes the original probe
and an app-server command-path probe without editing personal Windows config.
The Docker README records subsequent model-free and authenticated verification.
The Windows findings below are historical native-backend diagnostics; they do
not describe the newer Docker campaign route.

This boundary applies to AVO's Codex outer optimizer, inner players, and generated
solver evaluations. It does not change the separate `studies.codex_agent` run.

## Launch contract

- Use fresh anonymous workspaces outside the repository. Both Codex process cwd
  and thread cwd point there. Trusted archives remain outside model read access.
- Create a private Codex home with explicit config. Copy only an existing
  ChatGPT OAuth credential file after preflight; remove that copy on exit. Never
  copy personal configuration, memories, plugins, or histories.
- Disable automatic project instructions, memories, browsing, and extra tools.
  Preserve shell/Python, editing, image inspection, experiment prompts, budgets,
  supervisory behavior, and legitimate parent-to-child research inheritance.
- Use a custom root-deny filesystem permission profile, workspace writes,
  minimal runtime/Python reads, and network denial. Do not supply legacy
  `sandbox=workspace_write` / `sandbox_mode` overrides: these override the custom
  profile and permit broader reads.
- Before each model session or generated solver execution, run a real native
  sandbox probe. Python and workspace writes must work; repository, personal
  config, and private canary reads and a live loopback connection must fail.
- Stage visible PNGs byte-for-byte under anonymous hash names. Project trusted
  tool responses without game identifiers, private configuration, or archive
  paths. Keep evaluation scores and model-authored research intact.
- Capture and validate every outgoing Responses request before forwarding,
  including incremental WebSocket requests. Reject inherited AGENTS context,
  private/framework paths, unexpected tools, unrecognized requests, and failed
  capture. Do not censor model hypotheses or controls learned from observations.
- Treat isolation failures as infrastructure-invalid, not candidate fitness.
  Stop rather than retrying under weaker permissions. Start a fresh campaign;
  old runs and inherited notes are not retroactively certified.

## Verification and current limitation

`uv run pytest avo/tests -q` includes regression tests for late AGENTS injection,
tool inventories, escaped paths, sanitized results, capture failures, and blocked
launches. Solver protocol unit tests mock the native sandbox explicitly; passing
those tests is not proof of OS isolation.

The initial Windows setup failure (`orchestrator_helper_incomplete`) was traced
to clearing `USERNAME`/`USERDOMAIN`: the elevated helper then assigned setup-file
permissions without the correct caller identity. Preserve these OS identity
variables, while still clearing secrets and inherited Codex/tool configuration.
New runtime directories also grant the caller's Windows SID explicit inheritable
access: owner-relative permissions alone break access to helper-owned state.
Runtime directories now live under `~/.avo/isolated`, outside LocalAppData's
desktop-package redirection. Personal Codex configuration is unchanged.

With setup repaired, the real Windows probe **still fails isolation**: Python and
workspace writes work, but repository/personal config reads and the loopback
connection succeed. This was reproduced with Codex 0.153.1, the `avo` permission
profile selected, the `CodexSandboxOffline` account, and enabled Windows firewall
profiles. See `output/avo-isolation-preflight-repaired/isolation_preflight.json`.
The precise cause of that enforcement failure remains unresolved. Do not call
this clean, weaken the probe, use an unelevated fallback, or start a campaign.
An independently verified isolation backend is required before proceeding.
That native Windows patch did not certify a clean end-to-end model campaign.
Subsequent Docker evidence and launch instructions are in `docker/README.md`.

Request checks are a regression barrier, not a claim about model training data
or a complete adversarial security proof. OS enforcement and a real captured
outer/inner smoke run are both required before reporting clean results.
