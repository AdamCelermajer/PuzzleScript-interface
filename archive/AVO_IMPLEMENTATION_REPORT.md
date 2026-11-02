# How this repo implements NVIDIA's AVO (Agentic Variation Operators)

Evidence is `path:line`; `avo/output/**` was not traversed (artifacts only).

## 1. Actor topology

Actors (`avo/SPEC.md:3-8`): inner player, environment gateway, fresh evaluator, optional outer optimizer — plus a model-capture proxy and an outer tool gateway.

| Actor | Mechanism |
|---|---|
| Inner player | one persistent Codex thread, `ephemeral=True` (`avo/client/codex_oauth_agent.py:196-206`) |
| Outer optimizer | same class, `session_role="outer_optimizer"` (`avo/evolve.py:182-198`) |
| Environment gateway | in-process `AvoToolGateway` (`avo/core/tool_gateway.py:21-47`) |
| Outer gateway | `EvolutionGateway`, no game controls (`avo/evolution/gateway.py:19-45`) |
| Fresh evaluator | plain `subprocess.Popen`, **no model session** (`avo/evolution/solver_evaluation.py:105-120`) |
| Capture proxy | loopback `aiohttp` server in the AVO process (`avo/analysis/model_proxy.py:30-62`), wired at `avo/client/codex_oauth_agent.py:147-166` |

**Sessions per run.** A player run = **1** model session. A fresh evaluation = **0** model sessions but still **1** `codex sandbox` subprocess, since the solver's Python must run sandboxed (`avo/evolution/solver_evaluation.py:48-51`; `avo/isolation.py:228-229`). A campaign = **1 outer + 1 inner per `x_i`**; with defaults (`--max-evaluations 10`, `avo/evolve.py:48,63`) that is up to **11** sessions, each with its own private `CODEX_HOME`, proxy and bundle.

**Transport.** The agent has no network (`avo/isolation.py:196-197`), so tools are atomic JSON files:

- Inner CLI `python avo_tool.py <method>` writes `<uuid>.request.json` into `<ws>/.avo_rpc/` and polls for `<uuid>.response.json` (`avo/core/tool_gateway.py:420-506`); `FileToolServer._serve` unlinks the request, dispatches, and writes `.response.tmp`→`.response.json` (`:549-582`).
- Outer: same protocol in `.avo_evolution_rpc/` with `avo_evolve_tool.py` (`avo/evolution/tool_server.py:56-129, 172-205`).
- Model transport: the `openai_codex` SDK spawns `codex app-server --listen stdio://` and speaks typed JSON-RPC over stdio (`.venv/Lib/site-packages/openai_codex/client.py:193,230,237-241`).

## 2. The agent loop

**Prompt.** `base_instructions` = `prompts/base_agent.txt` + `task_instructions` (`avo/client/codex_oauth_agent.py:69-74`), where task instructions = `environments/puzzlescript/prompt.md` plus, in campaigns, a `# Run candidate strategy` block carrying `STRATEGY.md` (`avo/run_once.py:131-145`). Passed at `thread_start` (`avo/client/codex_oauth_agent.py:198`).

**MISSION / AGENT_INTERFACE** are written into the workspace at server start (`avo/core/tool_gateway.py:523-536`): `MISSION.md` = `"# Mission\n\n" + profile.objective + "\n\nOnly the environment profile's task evaluator determines success.\n"`, with the objective from `avo/environments/puzzlescript/profile.py:17-20`. `AGENT_INTERFACE.md` is the constant at `avo/core/tool_gateway.py:375-417`. Outer equivalents: `OPTIMIZER_INTERFACE` (`avo/evolution/tool_server.py:10-53`), mission built at `avo/evolve.py:136-141`.

**Turn loop.** `for turn_number in range(1, max_turns + 2)` (`avo/client/codex_oauth_agent.py:213`). Turn 1 gets `INNER_RUN_INSTRUCTION`, a ~250-word research protocol only for `session_role == "inner_player"` (`:23-43, 76-78`); later turns get the fixed continuation text (`:290-295`). After each turn: append `agent_transcript.jsonl`, check isolation, read `status`, then break / force `finish` / continue (`:255-289`). The `+2` is the world-model finalizer turn (`:211, 283-289`; `avo/evolution/gateway.py:46-55`).

**Allowed tools** (`avo/analysis/request_guard.py:11, 26-42`): `exec_command`, `write_stdin`, `apply_patch`, `view_image`, `update_plan` — enforced at the model transport, not by prompt. Environment actions are therefore shell commands: `python avo_tool.py probe ACTION_ID --rationale "why this experiment"` (`avo/core/tool_gateway.py:386`) is the only method that advances the game. The action must appear in `available_actions` (`avo/core/tool_gateway.py:301-302`; re-checked `avo/core/framework.py:422-423`).

**Three independent caps.** Environment actions: default 200 (`avo/run.py:51`) / 500 (evolution player, `avo/evolve.py:51`), enforced at `avo/core/tool_gateway.py:15-19, 175-181`, counter incremented only in `_reset` (`:194`) and `_probe` (`:310`). Wall time: 3600 s (`:180-181`) plus a `threading.Timer` that calls `turn.interrupt` with the remaining budget (`avo/client/codex_oauth_agent.py:226-233, 274-277`). Codex turns: 4 player / 30 optimizer (`avo/client/codex_oauth_agent.py:281-282, 296-300`; defaults `avo/run.py:53`, `avo/evolve.py:54,62`). Remaining budgets are returned on every call (`avo/core/tool_gateway.py:84-98`).

## 3. The environment gateway

**Commands** (`avo/core/tool_gateway.py:330-372`): `observe`, `mission`, `history`, `archive`, `evaluate_solver`, `probe`, `reset`, `checkpoint`, `restore`, `acknowledge_supervisor`, `status`, `finish`; unknown → `ValueError` (`:372`).

**Execution.** `probe` (`:291-328`) logs an `agent_decision`, then `AvoLaboratory.step` (`avo/core/framework.py:419-475`) → `PuzzleScriptEnvironment.step` → `GameAction[action.id]` (`avo/environments/puzzlescript/adapter.py:99-104`) → `ArcadeEnv.step` → ARC REST `POST /api/cmd/ACTIONn`. Evidence rows are appended by `EvidenceStore.append` (`avo/core/framework.py:169-179`).

**Return.** `probe` → `{transition, evaluations, supervisor_events, supervisor, task, budgets}` (`:321-328`); `observe` → `{observation, task, budgets}` (`:142-148`). Observation = `{payload:{"frame":[[[...]]]}, status, progress:{levels_completed,win_levels}, available_actions, metadata}` (`avo/environments/puzzlescript/adapter.py:82-91`).

**Rendering for the LLM: raw JSON, not art, and no legend.** The CLI prints `json.dumps(result, indent=2)` (`avo/core/tool_gateway.py:450`) over `_jsonable(current)`. `legend` is on a denylist and never populated (`avo/core/model_view.py:11-16`); `metadata` is whitelisted to `projection` and `rendered_frame` (`:73-74`). The grid is the nested int list `payload.frame` (`client/arc/types.py:39`), which the prompt says to treat as the current board (`avo/environments/puzzlescript/prompt.md:26`). Colors reach the model two ways: integer IDs in `payload.frame`, and RGBA pixels in `metadata.projection.patterns` (`prompt.md:33-35`). Every observation also carries `metadata.rendered_frame.path`, a byte-identical PNG staged at `<ws>/observations/<sha256>.png` under an anonymous hash (`avo/core/model_view.py:26-49`) and opened with `view_image`.

**Opaque action id.** The gateway never interprets IDs; it validates membership only (`avo/core/tool_gateway.py:301-302`, `avo/core/framework.py:422-423`) and the adapter performs the single name→enum mapping (`adapter.py:101`). "Action IDs are opaque and have no implied meaning" (`avo/core/tool_gateway.py:377`).

**Checkpoints.** `checkpoint` calls `environment.save_state()`, stores the opaque token in an in-process dict under `cp_{n:03d}`, and returns only `{checkpoint_id, label}` (`avo/core/tool_gateway.py:204-222`); `restore` looks it up and calls `restore_state` (`:224-243`; adapter `:106-116`). Restore bumps the episode and resets the supervisor but **does not** consume an environment step — it is absent from the two increment sites (`:194, 310`), pinned by `avo/tests/test_avo_tool_gateway.py:274-286`. Purpose: counterfactual branching from a controlled state without replaying the prefix or spending research budget, with no hidden-state leakage (`avo/SPEC.md:55-56`; `avo/core/tool_gateway.py:405-409`).

## 4. Solver contract + fresh evaluation

Deliverable is `solver.py` (`avo/SPEC.md:23-25`) speaking one persistent streaming protocol (`avo/environments/puzzlescript/prompt.md:6-19`):

```
python solver.py --play --max-steps N
stdin : one JSON line per step   {"observation": {...}}
stdout: exactly one JSON line    {"action":"ACTION_ID"}
```

Hidden state may persist in-process; no history is resent and no per-action subprocess is started (`avo/evolution/README.md:89-92`).

**Driver** (`avo/evolution/solver_evaluation.py:105-176`): `Popen(runtime.command(python,"solver.py","--play","--max-steps",N), stdin/stdout/stderr=PIPE, text=True)` where `runtime.command` = `codex sandbox --permission-profile avo --cd <ws> -- <cmd>` (`avo/isolation.py:228-229`). Each step writes `{"observation": model_view.present(current)}` (`:144-147`), waits ≤60 s for one line (`:150-153`), validates against `available_actions` (`:166-168`), steps the framework's own laboratory (`:169`), and stops on `task.terminal` (`:175-176`). Missing `solver.py` → silent `fitness=0` with `score["solver_available"]=0` (`:75-90`).

**Fitness** (`:206-216`): `levels_completed` from `current.progress`; `success = task.success` = `status == "WIN"` (`avo/environments/puzzlescript/profile.py:30`). Score also carries `solver_environment_actions`, `environment_task`, `solver_return_code`.

**Budget separation.** `evaluate_solver` runs the same driver into `research/self_check/check_NN/` against a **freshly loaded profile** (new environment/session) and returns only `{"fitness": float}` — trajectory and detailed score are withheld from the inner session (`avo/run_once.py:99-117`; contract `avo/core/tool_gateway.py:399-403`), and it does not touch `environment_steps` (`:100-140`). Limit 2 by default (`avo/run_once.py:25`; `avo/core/tool_gateway.py:103-109`). The held-out final evaluation loads a **third** fresh profile with its own 1500-action budget (`avo/evolution/evaluator.py:96-105`). Research progress is explicitly not fitness (`avo/evolution/evaluator.py:81-83`).

## 5. Outer evolution

`x_i` = `STRATEGY.md` + inherited workspace seed, validated as `RunCandidate` (`avo/evolution/README.md:9-15`; `avo/evolution/candidate.py:32-94`): `manifest.json` `schema_version: 1`, id matching `[A-Za-z0-9][A-Za-z0-9_.-]{0,79}`, unique non-self parents, no symlinks/junctions or reserved paths.

**Register:** the outer writes `drafts/<id>/{STRATEGY.md,seed/**}`; `register_draft` copies to `.tmp`, renames into the immutable candidate dir, requires all parents registered, rejects re-registration, then deletes the draft (`avo/evolution/store.py:196-231`).

**Evaluate:** `gateway.handle("evaluate")` refuses an already-evaluated candidate (`avo/evolution/gateway.py:134-141`). `CandidateEvaluator.evaluate` (`avo/evolution/evaluator.py:40-157`) loads a fresh profile, creates a new workspace and copies the seed (`:60-63`), runs the Codex player as *research* (`:64-72`), moves the archived workspace to `<run>/solver/` (`:88-91`), then runs the held-out solver (`:96-105`) and writes `summary.json` (`:139-143`).

**Fork/inheritance:** `store.fork` requires the parent to be evaluated, copies `<parent_run>/solver/**` minus `_INHERITANCE_EXCLUDES` (`avo/evolution/store.py:21-35`: `.codex`, `.agents`, `.tmp`, `observations`, `AGENTS.md`, `.avo_rpc`, `__pycache__`, `AGENT_INTERFACE.md`, `MISSION.md`, `agent_transcript.jsonl`, `avo_tool.py`, `drafts`) and symlinks, copies `STRATEGY.md`, and writes `manifest.json` with `parent_ids` (`:313-358`). This file copy is the only cross-context-window memory channel.

**`lineage.json`** (`schema_version 1`): `candidates[]` = `{candidate_id, parent_ids, path, registered_at}`; `evaluations[]` = `{evaluation_id, candidate_id, fitness, success, terminal, score, finish_reason, environment_steps, agent_turns, run_dir, recorded_at}` (`avo/evolution/store.py:156-157, 221-229, 289-311`; `candidate.py:111-124`). Atomic writes (`store.py:179-183`); legacy `population.json` layouts are auto-detected (`:137-154`).

**Stop conditions:** success **or** evaluations ≥ `max_evaluations` **or** wall ≥ `max_wall_seconds` (`avo/evolution/gateway.py:57-67, 80-89`), plus the outer turn cap (30, `avo/evolve.py:62,190`). All knobs are CLI flags (`avo/evolve.py:41-66`) persisted with profile/prompt hashes into `evolution_config.json` (`:154-179`).

**Distinct roles:** `store.py` = immutable artifacts, lineage, evidence paging (`:443-503`), `inspect` payload (`:360-441`); `candidate.py` = the `x_i` value object, validation, record; `evaluator.py` = trusted executor producing a score; `gateway.py` = outer tool surface, budget, terminality — policy without environment access.

## 6. Model / backend plumbing

**Invocation** is the `openai_codex` SDK (`Codex`, `CodexConfig`, `ApprovalMode`, `TextInput`; `avo/client/codex_oauth_agent.py:120-123`) with `CodexConfig(codex_bin, config_overrides, cwd, env)` using the scrubbed runtime env (`:186-191`). Binary discovery: `--codex-bin` → `$CODEX_BIN` → newest `%LOCALAPPDATA%/OpenAI/Codex/bin/*/codex.exe` → `which("codex")` (`studies/codex_agent/session.py:70-87`).

**Auth.** OAuth: personal `~/.codex/auth.json` copied into the private `CODEX_HOME` only when it contains `tokens`; API keys refused; deleted on `close()` (`avo/isolation.py:205-216, 282-286`). OpenRouter: `OPENROUTER_API_KEY` or `AVO_OPENROUTER_KEY_FILE`, injected into the Codex process env *after* the shell allowlist is fixed so shell tools never see it (`:218-226`).

**Provider/defaults.** `resolve_model`: `openrouter/vendor/model` → `openrouter`, else `openai`; `opencode/` retired (`avo/client/model_provider.py:5-13`). Defaults: player `gpt-5.6-sol`/`high` (`avo/client/codex_oauth_agent.py:48-49`, `avo/run.py:48-49`); evolution player `gpt-5.3-codex-spark`, optimizer `gpt-5.6-sol`, both `high` (`avo/evolve.py:48-49,59-60`); batch `gpt-6-astra` low / `gpt-5.6-luna` high+`priority` (`avo/docker/batch.py:81-82`). `service_tier` is rejected for OpenRouter (`avo/client/codex_oauth_agent.py:66-67`).

**`model_proxy.py`.** Binds `127.0.0.1:0` in a background asyncio thread (`avo/analysis/model_proxy.py:104-118`); Codex is pointed at it either by rewriting `openai_base_url` (`avo/client/codex_oauth_agent.py:183-185`) or by registering an `openrouter` provider whose `base_url` is the proxy (`:174-181`). Every `POST .../responses` and every websocket `response.create` is recorded with parsed JSON, raw UTF-8, base64 body, transport, sequence and guard report into `model_requests/request-<ns>-<seq>.json` (`model_proxy.py:136-140, 183-199, 224-272`). Auth headers are forwarded in memory only (`:274-282`). If the capture write fails the guard latches and the run is infrastructure-invalid (`:266-269`; `avo/client/codex_oauth_agent.py:321-322`).

**`request_guard.py` guards** (before forwarding; first failure latches, `avo/analysis/request_guard.py:56-57`): unapproved tool inventories and unnamed client-side tool discovery (`:11, 26-42`); auto-injected `# AGENTS.md instructions` (`:84-85`); any reference to the repository root, private `CODEX_HOME`, or artifacts root via path-boundary regexes with backslash normalization (`:76-87`); canary strings (`:88-89`). It deliberately skips assistant messages, `reasoning` and `function_call` so learned mechanics are never censored (`:71-74`).

**Config keys.** Model/effort/service-tier come from `--model`/`--player-model`/`--optimizer-model`, `--effort`/`--player-effort`/`--optimizer-effort`, `--player-service-tier`/`--optimizer-service-tier`; binary from `CODEX_BIN`; tracing from `AVO_TRACE_DETAIL`; credentials from `CODEX_HOME`, `OPENROUTER_API_KEY`, `AVO_OPENROUTER_KEY_FILE`; grid from `PUZZLESCRIPT_GRID_ENCODING` (`puzzlescript_interface/runtime/server.js:13`). **Sandbox is not a CLI knob**: it comes entirely from the generated private `config.toml` (`avo/isolation.py:147-203`) — `default_permissions = "avo"`, `approval_policy = "never"`, `project_doc_max_bytes = 0`, `web_search = "disabled"`, `[windows] sandbox = "elevated"`, `[permissions.avo.filesystem] ":root" = "deny"`, `":workspace_roots" "." = "write"`, `[permissions.avo.network] enabled = false`, `[shell_environment_policy] inherit = "none"`.

## 7. Isolation & safety

`ISOLATION.md:14-40` states the contract: fresh anonymous workspaces outside the repo (both process and thread cwd); a private Codex home holding only a copied OAuth file; project instructions, memories and browsing disabled; a custom root-deny filesystem profile with network denial; a real native sandbox probe before **each** model session *and* each generated solver execution; PNGs staged byte-for-byte under anonymous hashes; every outgoing Responses request validated; isolation failures treated as infrastructure-invalid, never as fitness.

`isolation.py` implements it: `runtime_root()` = `~/.avo/isolated`, hard-rejecting repo-internal paths (`:24-38`); `assert_workspace` rejects repo paths, links/junctions and `AGENTS.md`/`.codex`/`.agents` (empty Bubblewrap mount points tolerated) (`:73-85`); `preflight()` requires Python working, writes working, all three forbidden reads denied (private canary, `AGENTS.md`, personal Codex config) and a loopback connect failing (`:231-276`).

**Why native Windows fails closed.** The probe really runs; on Windows the forbidden reads and the loopback connection **succeed**, so `preflight` records `passed:false` and raises, `CodexOAuthAgent.run` writes `analysis/infrastructure_invalid.json`, and no authentication or model session is started (`avo/ISOLATION.md:57-64`; `avo/client/codex_oauth_agent.py:97-110`; `avo/tests/test_isolation.py:261-270`). The earlier `orchestrator_helper_incomplete` bug (cleared `USERNAME`/`USERDOMAIN` → wrong SID for ACL assignment) is fixed by preserving OS identity variables (`avo/isolation.py:107-112`) and granting the caller's SID inheritable access on new runtime dirs (`:52-70`); the sandbox failure itself is unresolved.

**Docker.** `avo/docker/Dockerfile` (10 lines): `python:3.12.14-slim-bookworm`, venv and Linux musl `codex` copied from a local `avo-jericho:local` image, `codex-linux-sandbox` symlinked to it, `bubblewrap` installed, `arc-agi`/`fastapi`/`uvicorn`/`python-dotenv`/`backports.zstd` added. `docker_command` (`avo/docker/launch.py:34-44`): `--rm --init --read-only`, `--cap-drop ALL` plus `SYS_ADMIN, SETUID, SETGID, SETFCAP`, `no-new-privileges`, `seccomp=unconfined` for the **outer container only** (nested namespaces), `--pids-limit 256`, `--memory 2g`, `--cpus 2`, 256 MiB `/tmp` tmpfs, anonymous volume at `/home/controller`, controller bind-mounted **read-only** at `/controller`, results rw at `/results`. Network is *not* denied at container level (the controller must reach the ARC backend and model service); the **agent's** sandbox denies network and preflight asserts it (`avo/isolation.py:196-197, 264`; `avo/docker/preflight.py:25-44`, which also exercises the app-server `command/exec` path and requires `CapEff == 0`). Secrets: `auth.json` and a `chmod 600` OpenRouter key are staged into a `tempfile` dir bound at `/credentials` with `CODEX_HOME=/credentials`, deleted on exit (`avo/docker/launch.py:47-69, 114-146`; `avo/docker/batch.py:48-51, 132`); personal config is never mounted (`avo/docker/README.md:1-4, 83-86`).

**Sandbox mode for the agent:** the custom `avo` permission profile, `approval_policy="never"` in config plus `ApprovalMode.deny_all` at thread creation (`avo/client/codex_oauth_agent.py:199-201`), and `--permission-profile avo` for every subprocess (`avo/isolation.py:228-229`). The code repeatedly warns not to pass the legacy `Sandbox.workspace_write`/`sandbox_mode` override, which supersedes `default_permissions` and restores broad reads (`avo/isolation.py:145-146`; pinned by `avo/tests/test_isolation.py:58-67`).

## 8. PuzzleScript specifics

**Adapter deltas** (`avo/environments/puzzlescript/adapter.py`): decodes the ARC `rendered_frame` data URL per observation, validating MIME and PNG magic bytes (`:41-72`); derives `progress` and `available_actions` from the frame (`:82-91`); exposes `save_state`/`restore_state` by delegation (`:106-116`); implements `compare` as recursive positional list similarity plus status/progress equality (`:15-26, 118-131`).

**Fitness** (`avo/environments/puzzlescript/profile.py:22-41`): `fitness = levels_completed`, `success = status == "WIN"`, `terminal = status in {"WIN","GAME_OVER"}`, score adding `success`, `levels_completed`, `win_levels`, `environment_actions`.

**`profile.toml`** (7 lines): `id`, `factory = "avo.environments.puzzlescript.profile:create_profile"`, `prompt = "prompt.md"`, `[defaults] backend_url = "http://127.0.0.1:8000"`, `game_id = "ps_sokoban_basic-v1"`; loaded and hash-pinned by `avo/core/profile.py:58-86`; `--set KEY=VALUE` is JSON-parsed (`avo/run.py:22-30`).

**`prompt.md`** (48 lines): the task ("Build `solver.py` for this unknown game. Interaction is research; manually completed levels do not count as fitness."), the streaming protocol, the two-self-check limit, the opacity rule, the three projection modes with decoding rules, and the `rendered_frame` pointer.

**Reaching the stack.** `create_profile` builds `ArcadeEnv(game_id, backend_url, api_key)` (`avo/environments/puzzlescript/profile.py:44-49`) via `client/arc/arcade_env.py`, so AVO speaks only the ARC REST surface (`POST /api/cmd/RESET`, `POST /api/cmd/ACTIONn`). Start with `npm run local` (Node `:3000`, FastAPI ARC service `:8000`; overridable by `PORT`/`ARC_PROXY_PORT`/`PUZZLESCRIPT_SERVER_URL`). From Docker the backend must be `http://host.docker.internal:PORT` (`avo/docker/README.md:80-81`); `api_key` matters only for official ARC.

**Grid encoding.** AVO does not select it: each profile load constructs a new `ArcadeEnv`, and the Node runtime defaults `PUZZLESCRIPT_GRID_ENCODING` to **`visible-cell-v1`**, failing at startup on unknown modes (`puzzlescript_interface/runtime/server.js:13-16`; `puzzlescript_interface/README.md:57-59`). Semantics: one integer per visible tile, IDs 0–65535 assigned to final rendered RGBA pixels, identical textures sharing an ID even when hidden engine objects differ, `projection.patterns` containing only textures already observed (`puzzlescript_interface/README.md:35-43`). `prompt.md:30-35` documents exactly this; `:37-45` documents legacy `visible-cell-hex-v2` and `object-cell-v1`. Frame shape is `list[list[list[int]]]` (`client/arc/types.py:39`), passed through from the service (`puzzlescript_interface/api/app.py:109`).

## 9. Divergences from NVIDIA's described AVO

**Present:** persistent workspace surviving context windows (workspace + fork seed, §5); autonomous inspect→plan→implement→evaluate-through-execution loop (§2); a stagnation supervisor that gates the agent; the outer optimizer as variation operator instead of a predefined mutation; a task-interface abstraction for retargeting (`profile.toml` `factory` + the `EnvironmentProfile` protocol, `avo/core/profile.py:21-30`).

**The supervisor exists but is deterministic and partly dead code.** `DeterministicSupervisor` (`avo/core/framework.py:182-250`) detects `repeated_no_change` (3 identical observation fingerprints), `repeated_probe` (4 identical action IDs) and `hypothesis_collapse` (3 cycles where every participating theory failed prospectively). `redirect` events are stored and **hard-block** `probe`/`reset`/`restore` until `acknowledge_supervisor` is called with a revised approach (`avo/core/tool_gateway.py:163-173, 185, 226, 293, 316-318`). But `hypothesis_collapse` can never fire in production: the player lab is built with `candidates=[]` (`avo/run_once.py:88`), so `evaluations` is always empty and `_failed_prediction_cycles` never increments (`avo/core/framework.py:215-217, 240`). There is **no LLM supervisor** on the maintained path — that lives only in the superseded `avo/legacy/session.py:78-83` + `avo/legacy/runner.py:46-60`.

**Theory format is not imposed.** `avo/SPEC.md:20-21` and `avo/LAB.md:11-13` explicitly state there is no required internal theory, hypothesis, branch, manifest or candidate format, repeated in `AGENT_INTERFACE` (`avo/core/tool_gateway.py:395-397`). Yet the machinery survives: `TheoryManifest` + `FilesystemTheoryCandidate` (a `manifest.json` plus a `predict` subprocess speaking `avo-theory-predict-v1`, `avo/core/theory_package.py:26-113`) is still exported from `avo/__init__.py:14-17` but referenced only by `avo/legacy/agentic.py:16,88`. Likewise `Prediction`/`choose_experiment`/`compare`-based prospective scoring is live code (`avo/core/framework.py:72-103, 348-417`) that the model-facing contract never triggers: `probe` passes only `action_id` + `rationale` (`avo/core/tool_gateway.py:298-309`) and `_freeze_predictions` iterates zero candidates. The only mandatory artifact formats are `STRATEGY.md` per `x_i` (`avo/evolution/tool_server.py:38-40`) and `solver.py`.

**It is a lineage, not a population.** Candidates are immutable and evaluated exactly once (`avo/evolution/store.py:205-206, 283-284`; `avo/evolution/gateway.py:137-140`). There is no mutation operator, crossover, selection sampling, replacement, or fitness-proportional parent choice — `fork` accepts any evaluated parent and the prompt merely says "Fork the best parent" (`avo/prompts/outer_optimizer.txt:14`). Equal-fitness candidates stay in `lineage.json` but are never sampled (`avo/evolution/tool_server.py:50-51`). A failed `x_i` may not be retried or replaced by a new top-level run (`avo/SPEC.md:49-50`; `avo/prompts/outer_optimizer.txt:46-47`).

**No automatic memory summarization.** Transcripts and the raw app-server stream are appended verbatim (`avo/analysis/run_trace.py:163-199, 220-272`). The only summary artifact is an optional single final outer turn writing `world_model.md` (`avo/evolution/gateway.py:46-55`), default mode `final-only` (`avo/evolve.py:84-85`), archived at `avo/evolve.py:204-215`; it is free-form and reaches inner players only in `between-hypotheses` mode, and then only as a `seed/world_model.md` file that travels by ordinary inheritance (`avo/evolve.py:149-153`). Context survival comes from **re-reading frozen artifacts**: `evidence` pages complete research/self-check/evaluation event streams (`avo/evolution/store.py:443-503`) and `inspect` returns solver source, parent diff, learned `.md` notes and a trace summary (`:360-441`). `avo/report_saved_world_model.py:23-39, 61-98` goes further, reconstructing a whole saved outer session from `app_server_events.jsonl` into `OUTER_HISTORY.jsonl` in a fresh container with workspace paths remapped and observation PNGs restored by SHA-256.

**Absent.** No official ARC-AGI-3 action space or profile — only the PuzzleScript ARC-compatible surface; no 25-environment/183-level harness, no RHAE metric, no per-level difficulty accounting. Fitness is purely `levels_completed` in one fresh game. There is no GPU/kernel task interface, and `AgentBackend` is a one-implementation protocol (`avo/core/agent_backend.py:36-43`). Trajectory analytics beyond `_trace_summary` (`avo/evolution/store.py:46-128`) and the monitor's counters do not exist.

## 10. Entry points & how to run

**One player run** (native — on Windows controller-interface only, see §7):

```powershell
npm run local
uv run python -m avo.run --profile puzzlescript --set game_id=ps_sokoban_basic-v1 `
  --model gpt-5.6-sol --effort high --max-environment-steps 200 `
  --max-wall-seconds 3600 --max-agent-turns 4
```

Output defaults to `avo/output/<YYYYmmddTHHMMSS>/` (`avo/run.py:19, 61-62`): `run_config.json` (profile hashes, model, budgets), `evidence.jsonl`, `workspace/`, `workspace_archive.json`, `final_summary.json`, `analysis/` (session bundle), `self_check/check_0N/` (evidence + `solver_evaluation.json` + stdout/stderr).

**Evolution campaign:**

```powershell
uv run python -m avo.evolve --profile puzzlescript --set game_id=ps_midas-v1 `
  --max-evaluations 10 --player-model gpt-5.3-codex-spark --player-effort high `
  --player-service-tier priority --player-max-environment-steps 500 `
  --fresh-solver-max-environment-steps 1500 --optimizer-model gpt-5.6-sol `
  --optimizer-effort high --optimizer-service-tier priority --optimizer-max-agent-turns 30
```

(`avo/evolution/README.md:26-40`; flags `avo/evolve.py:41-66`.) Output `avo/output/evolution/<run>/` (`avo/evolution/README.md:49-75`): `evolution_config.json`, `initial_observation.json` + `initial_frames/`, `lineage.json`, `optimizer_analysis/` (outer bundle incl. `model_requests/`), `outer/drafts/`, `world_model.md`/`world_model.json`, `evolution_summary.json`, plus per candidate `x_NNNN/{manifest.json, STRATEGY.md, seed/, research/{evidence.jsonl, run_config.json, workspace/, summary.json, self_check/check_NN/, analysis/}, solver/, evaluation/{evidence.jsonl, solver_evaluation.json, solver_stdout.txt, solver_stderr.txt}, summary.json}`. The output dir must be fresh; continuation requires `--resume-saved-campaign` (`avo/evolve.py:74-83`).

**Monitor:** `uv run python -m avo.monitor_evolution --run-dir <run> --watch --interval 3` (add `--json`) — reports phase (`initializing`/`pending`/`research`/`starting_fresh_evaluation`/`fresh_evaluation`/`finishing_evaluation`/`evaluated`), hypotheses registered/evaluated, actions vs budgets, last activity (`avo/monitor_evolution.py:79-140, 177-192`).

**Docker (supported on Windows):** `docker build -t avo-puzzlescript-isolated:local avo/docker` → `python -m avo.docker.launch --output-dir output/avo-docker-preflight` → `python -m avo.docker.smoke_host` (`avo/docker/README.md:45-49`). Campaign: `python -m avo.docker.launch --campaign --game-id ... --backend-url http://host.docker.internal:PORT --optimizer-model ... --player-model ... --max-evaluations N --research-moves N --solver-moves N --output-dir <fresh>` (`avo/docker/launch.py:71-150`). Batch `python -m avo.docker.batch` (`avo/docker/batch.py`); recovery `python -m avo.docker.repairs`; browser entry `npm run workbench` → `/runs/avo.html`.

**Maintained vs legacy.** Maintained: `avo/run.py`, `avo/evolve.py`, `avo/monitor_evolution.py`, `avo/docker/*`, `avo/core/*` (except `theory_package.py`), `avo/client/*`, `avo/evolution/*`, `avo/analysis/*`, `avo/environments/puzzlescript/*`. Legacy (`avo/legacy/*`): the old design where the model returned batches of ≤20 actions against a fixed `PLAN_OUTPUT_SCHEMA` with a separate LLM supervisor returning `SUPERVISOR_OUTPUT_SCHEMA` (`avo/legacy/session.py:21-49, 52-83`), driven by `AvoAgentRunner` (`avo/legacy/runner.py:46-60`) with per-file workspace helper tools (`avo/legacy/openrouter_session.py:30-55`); CLI `avo/legacy/run_avo_agent.py`. Also legacy: `avo/legacy/run_avo_lab_demo.py` + `avo/legacy/agentic.py`, a deterministic stand-in exercising the Theory-Package contract.

## 11. Notable gotchas

- **Three-way sync.** A new gateway method needs `AvoToolGateway.handle` (`avo/core/tool_gateway.py:330-372`), the embedded `AGENT_CLI` argparse (`:420-507`) and the `AGENT_INTERFACE` prose (`:375-417`); the outer needs `EvolutionGateway.handle` (`avo/evolution/gateway.py:107-157`), `OPTIMIZER_CLI` (`avo/evolution/tool_server.py:56-129`) and `OPTIMIZER_INTERFACE` (`:10-53`). Nothing validates them against each other.
- **Two overlapping denylists.** `EvolutionStore._INHERITANCE_EXCLUDES` (`avo/evolution/store.py:21-35`) and `RunCandidate._RESERVED_WORKSPACE_*` (`avo/evolution/candidate.py:13-21, 66-74`) must agree, or `fork()` will copy what `register_draft` rejects.
- **Hardcoded self-check arity.** `EvolutionStore.evidence` accepts only `research|evaluation|self_check_01|self_check_02` (`avo/evolution/store.py:452-456`) while `avo/run_once.py:102` writes `self_check/check_{n:02d}`; raising `--player-max-solver-self-checks` past 2 makes extra self-checks unpaginable.
- **Asymmetric RPC timeouts:** 3600 s inner (`avo/core/tool_gateway.py:439`) vs 86400 s outer (`avo/evolution/tool_server.py:74`); a long self-check can outlive the inner call.
- **Stale monitor path.** `avo/monitor_evolution.py:72-77, 106` globs `<run>/.sandboxes/avo-player-<id>-*`, which no current code creates — workspaces live in `~/.avo/isolated/w-*` (`avo/isolation.py:35-38`) — so `solver.draft_present` is effectively always `False`; `avo/tests/test_monitor_evolution.py:15` fabricates the old layout, so the test still passes.
- **Tracing defaults differ:** `full_trace` defaults to `"full"` (`avo/analysis/run_trace.py:51`), enabling per-event workspace snapshots and a blob store (`:179-189, 220-272`) — enormous output. Docker forces `AVO_TRACE_DETAIL=compact` (`avo/docker/launch.py:41`); `avo/tests/test_run_trace.py:19` pins compact.
- **The supervisor gate can deadlock a session:** while attention is pending, `probe`/`reset`/`restore` raise (`avo/core/tool_gateway.py:163-173, 185, 226, 293`), so an agent that never acknowledges burns its turns until the turn budget forces `finish`.
- **Model-visible surface is a whitelist** (`avo/core/model_view.py:51-76`): observation → `{payload, status, progress, available_actions, metadata}`, `metadata` → `{projection, rendered_frame}`, and `_PRIVATE_KEYS` strips `game_id`, `legend`, `profile_settings`, `run_config`, `analysis`, `output_dir`. `progress.win_levels` **is** visible; new fields need an explicit visibility decision.
- **Silent zero fitness and a binary dependency:** a missing `solver.py` returns `fitness=0.0` without raising (`avo/evolution/solver_evaluation.py:75-90`, distinguishable only via `score["solver_available"]`), and the held-out evaluator needs the Codex binary even though it never calls a model (`:48-51`); `codex sandbox` failures become `IsolationError` when stderr contains `windows sandbox failed:` (`:199-200`) and count as infrastructure-invalid, not as a score.
- **Windows hygiene.** `cleanup_private_directory` is a no-op on nt (`avo/isolation.py:41-49`), so `~/.avo/isolated` accumulates `w-*`/`c-*` dirs; `_new_private_directory` shells out to `whoami.exe`/`icacls.exe` and raises `IsolationError` if the SID cannot be parsed (`:58-69`), so PATH corruption looks like an isolation failure.
- **Immutable decisions.** A candidate cannot be evaluated twice (`avo/evolution/gateway.py:137-140`); failure can only be superseded by a fork. `--world-model-mode` is frozen mid-campaign (`avo/evolve.py:80-83`; `avo/docker/launch.py:104-110`). `avo/run.py`'s 200 env steps / 4 turns is not equivalent to an evolution `x_i`'s 500 steps + 2 self-checks.
- **Tests encoding contracts:** `avo/tests/test_isolation.py` (workspace rejection, guard path-boundary/AGENTS/canary rules, ModelView anonymity, fail-closed preflight, capture latching), `test_avo_tool_gateway.py` (opaque actions, two-self-check limit and budget separation, supervisor ack gate, checkpoint costs no step, finish≠success, no theory-package workflow `:148-180`), `test_evolution.py` (lineage, inheritance, world-model modes), `test_rpc_storage.py` (concurrent RPC, no leaked files), plus `test_run_trace.py`, `test_model_proxy.py`, `test_docker_launch.py`, `test_run_once.py`, `test_profile.py`.

## File map

| Path | Role |
|---|---|
| `avo/SPEC.md` | Normative runtime contract |
| `avo/LAB.md` | Operator entry point, layout, session logs |
| `avo/ISOLATION.md` | Isolation contract + Windows failure record |
| `avo/run.py` | CLI: one player run |
| `avo/run_once.py` | Wires store/laboratory/gateway/self-check/agent |
| `avo/evolve.py` | CLI: outer evolution campaign |
| `avo/monitor_evolution.py` | Run-directory snapshot |
| `avo/isolation.py` | Workspaces, private home, config, auth, preflight |
| `avo/report_saved_world_model.py` | Rebuild saved outer session → world model |
| `avo/core/framework.py` | Core types, `EvidenceStore`, `DeterministicSupervisor`, `AvoLaboratory` |
| `avo/core/tool_gateway.py` | Gateway methods, budgets, checkpoints, agent CLI/interface |
| `avo/core/profile.py` | Profile loading, overrides, hashing |
| `avo/core/model_view.py` | Model-facing projection and sanitizing |
| `avo/core/run_store.py` | Run layout, evidence, verified archiving |
| `avo/core/agent_backend.py` | Agent protocols |
| `avo/core/theory_package.py` | Legacy theory-package protocol |
| `avo/client/codex_oauth_agent.py` | Persistent Codex session and turn loop |
| `avo/client/model_provider.py` | Provider-qualified model resolution |
| `avo/environments/puzzlescript/profile.toml` | Profile id/factory/prompt/defaults |
| `avo/environments/puzzlescript/profile.py` | Objective and fitness evaluation |
| `avo/environments/puzzlescript/adapter.py` | ARC→AVO mapping, PNGs, checkpoints |
| `avo/environments/puzzlescript/prompt.md` | Inner task prompt |
| `avo/evolution/store.py` | Candidates, lineage, fork, inspect, evidence |
| `avo/evolution/candidate.py` | `x_i` value object and validation |
| `avo/evolution/evaluator.py` | Executes one `x_i` end to end |
| `avo/evolution/gateway.py` | Outer tools, budgets, terminality |
| `avo/evolution/solver_evaluation.py` | Held-out solver driver and fitness |
| `avo/evolution/tool_server.py` | Outer interface/CLI/RPC server |
| `avo/analysis/model_proxy.py` | Captures exact model requests |
| `avo/analysis/request_guard.py` | Fail-closed request validation |
| `avo/analysis/run_trace.py` | Session bundles and event streams |
| `avo/prompts/base_agent.txt` | Inner system prompt |
| `avo/prompts/outer_optimizer.txt` | Outer system prompt |
| `avo/docker/launch.py` | Container launch, staging, credentials |
| `avo/docker/campaign.py` | Container entry: preflight → evolve |
| `avo/docker/preflight.py` | In-container isolation checks |
| `avo/docker/batch.py` | Six campaigns + monitor + watchdog |
| `avo/docker/repairs.py` | Replacement campaigns for failures |
| `avo/docker/batch_stack.py` | Owns the Node/FastAPI stack |
| `avo/docker/smoke.py`, `smoke_host.py` | Model-free smoke tests |
| `avo/docker/Dockerfile` | Linux controller image |
| `avo/legacy/*` | Superseded batched-action session + LLM supervisor |
