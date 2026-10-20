# OpenCode vs Codex CLI as harnesses for Qwen 3.8 (focus: 27B), 2026-10-20

Scope: what each CLI adds or changes between our prompt and the model, which Qwen runs exist on each, and what a
controlled comparison would need. No runs or paid calls were made. Labels: **[C]** confirmed from code, binaries,
captured requests or run files; **[H]** hypothesis or unverified.

Main sources:
- Current harness code: `harnesses/codex.py`, `harnesses/opencode.py`, `harnesses/base.py`,
  `harnesses/registry.py`, `harnesses/docker/Dockerfile`.
- Old Codex route, deleted in `951ced8`: `git show 94086fe:avo/analysis/model_proxy.py`,
  `git show 94086fe:studies/codex_agent/session.py`, `git show 94086fe:avo/client/model_provider.py`.
- Captured requests: `<run>/model_requests/request-*.json` (old Codex), and the OpenCode request in
  `output/harness2-seed-smoke-20261020/offline_prompt_capture.json`.
- Binaries in `puzzlescript-agents:local`: `opencode-ai` 1.14.19 (`bin/.opencode`) and `@openai/codex` 0.162.1
  (`codex-linux-x64/.../bin/codex`). I read them as `grep -a` string dumps.

Helper scripts are in `%TEMP%\ovc\` (not committed).

## 0. The two "Codex" harnesses

"Codex" in the Qwen runs is **not** the Codex harness that exists today.

| | Old Codex route (30 Sep–15 Oct) | Current `harnesses/codex.py` (since `9bfd741`, 15 Oct) |
|---|---|---|
| Driver | Python `openai-codex` SDK (app-server), lock 0.159.2 (`git show 94086fe:uv.lock`). Baseline ran on the **Windows host** and preferred the Codex desktop app's `codex.exe` (`_find_codex_bin`). AVO ran in Docker with `@openai/codex@0.156.1` (`git show 94086fe:avo/docker/Dockerfile`). | `codex exec --json` 0.162.1 in Docker |
| Model route | `model_providers.<openrouter\|nanogpt>` with `wire_api="responses"`, `requires_openai_auth=false`, base_url = a loopback proxy (`CodexRequestProxy`) that recorded every request and forwarded it to `https://openrouter.ai/api/v1/responses` or `https://nano-gpt.com/api/v1/responses` (`codex_provider_overrides`, `model_proxy.py`) | ChatGPT login, OpenAI models only; `resolve_model_for` rejects other ids (`registry.py`) |
| Body patches | OpenRouter: `provider={"order":[slug],"allow_fallbacks":false}` merged in (`body_patch`). NanoGPT: Codex `namespace` tools flattened to `ns__name` and restored in the SSE stream (`_flatten_namespaces`, added in `94086fe`) | none |
| System prompt | `base_instructions` = **our text only**. Codex's built-in prompt is replaced: 8 Oct request `instructions` is 852 chars (`20261008T112945-f705fa9a/run-0001/model_requests/request-…-000001.json`). On 15 Oct NanoGPT the same text arrives as a developer message and `instructions` is empty. | Codex's built-in per-model template (the binary bundles GPT-5/GPT-6 `instructions_template` strings of about 18–22 k chars) **plus** our text as `developer_instructions` (`codex.py`) **[C, string dump; which template applies to which slug not resolved]** |
| Tools | Baseline(+): shell off (`features.shell_tool=false`, `unified_exec=false`), sandbox read-only, approvals `deny_all`. The model saw `list_mcp_resources`, `list_mcp_resource_templates`, `read_mcp_resource`, `request_user_input`, `view_image` and the notes MCP (`list/read/write_note`). AVO: `exec_command`, `write_stdin`, `view_image`, `get/create/update_goal`, and **no apply_patch** (`20261013T165330-avo-27b-modality/.../x_0001/research/analysis/model_requests`). | Full Codex tool set with `--dangerously-bypass-approvals-and-sandbox`; web, browser, apps, plugins, memories and multi-agent off (`DISABLED_CONFIG`). No requests captured. |
| Leaks from the host | Baseline on Windows: a developer message listed the host's `~/.codex/skills` (~4 k chars; imagegen, openai-docs, …), `<shell>powershell</shell>` and a Windows cwd. From about 13 Oct, host MCP servers appeared as tools: `mcp__node_repl__js` (used 28× by Flash on 15 Oct) and `mcp__comfy_mcp__*` (`…714e64/run-0002`, tool count in §B.3). | none (Docker, private `$CODEX_HOME`) |

**Removal [C].** `9bfd741` (15 Oct) "Replaces the Codex sandbox, request proxy and OpenRouter loops", and `951ced8`
deleted `model_proxy.py`, `codex_oauth_agent.py`, `openrouter_session.py` and related files. The rationale is recorded
in `docs/diary/2026-10-15-workbench-harness-revamp.md` ("OpenCode replaces the custom OpenRouter loop for Qwen runs")
and `docs/diary/2026-10-15-capability-scorecard-realtime-board.md` ("Codex stays OpenAI-only. Results from the old
Codex/OpenRouter Qwen runs are reported with a harness note rather than re-run"). The motive was simplification: the
isolation and proxy machinery was Codex-specific. No technical failure forced the removal.

**Can Codex run Qwen today? [C] technically yes, [C] blocked by our code.** Codex 0.162.1 still accepts custom
`model_providers`, but only `wire_api="responses"`. The binary contains: "`wire_api = "chat"` is no longer supported.
How to fix: set `wire_api = "responses"`". It also knows `model_instructions_file`, `base_instructions`,
`model_context_window`, `model_auto_compact_token_limit`, `tool_output_token_limit` and `request/stream_max_retries`.
OpenRouter documents `/api/v1/responses` as a stateless beta that rejects `store:true` and `previous_response_id`; Codex
sent `store:false` and the full history each time, so this matches ([OpenRouter Responses API beta](https://openrouter.ai/docs/responses)).
NanoGPT's `/api/v1/responses` served the 15 Oct runs. What blocks it today: `resolve_model_for("codex", …)` raises,
`credentials_for("codex")` passes only `codex-auth`, and the namespace-flattening shim for NanoGPT is deleted.

## A. Static differences: old Codex route vs current OpenCode, for Qwen

| Aspect | Old Codex route (all Qwen "codex" runs) | OpenCode 1.14.19 (`harnesses/opencode.py`) |
|---|---|---|
| Wire format to provider | OpenAI **Responses** (`input` items, `function_call` / `function_call_output`, `reasoning` items, `input_image`). The provider (OpenRouter / NanoGPT) translates to the upstream's chat format **[C request shape; translation is provider-side, unobserved]** | **Chat Completions** via AI SDK (`@openrouter/ai-sdk-provider`, or `@ai-sdk/openai-compatible` for NanoGPT). Captured body keys: `model, max_tokens(32000), messages, tools, tool_choice, stream, stream_options` (`offline_prompt_capture.json`) |
| CLI system prompt | none. Only our text, plus Codex's permissions/env developer and user messages and (baseline on host) the skills list | OpenCode's fallback prompt `nM`, ~9.7 k chars ("You are opencode, an interactive CLI tool… fewer than 4 lines… One word answers are best…"), then env block, skills list if any, then "Instructions from: …/SYSTEM_PROMPT.md" + our text. Selection `VB()`: `gpt-4/o1/o3`→beast, `gpt*codex`→codex, `gpt`→gpt, `gemini-`, `claude`, `trinity`, `kimi`, **else (Qwen)→`nM`** **[C binary; the capture used model "offline", which takes the same branch]** |
| Tool set | see §0 (no shell in baseline; PTY `exec_command` in AVO) | `bash`, `read`, `glob`, `grep`, `edit`, `write`, `task` (subagents), `todowrite`, `skill`; `webfetch/websearch/codesearch` denied (capture + `opencode.py`) |
| Tool schemas | Codex JSON schemas, `strict:false`, MCP tools as `namespace` | JSON-schema-2020-12 tools, camelCase args (`filePath`, `oldString`) |
| Image delivery | `input_image` data URL in the user message every turn, plus a `view_image` tool returning an image in `function_call_output`. **All past frames stay in history**: 51 images in the last pre-compaction request on 8 Oct, 166 on 15 Oct (`scan.py` over `model_requests`) | `-f frame.png` becomes a file part, forwarded **only if** `capabilities.input.image`; otherwise replaced by text "ERROR: Cannot read … (this model does not support image input). **Inform the user.**" (binary). Declared since `e81541c`. Pre-fix evidence: Flash reasoning "Cannot see the image (model doesn't support image input)" (`20261020T104612-0bf1b65d/.../base1/agent_events.jsonl`) |
| Reasoning effort | `reasoning:{effort:E, summary:"auto"}` sent, plus `include:["reasoning.encrypted_content"]` (all requests; `max` sent as-is from run 20260930T224046 on). Whether OpenRouter/Alibaba or NanoGPT map effort to a thinking budget for Qwen is **[H]** | **Nothing is sent for Qwen.** `dJ()` (variants) returns `{}` if `!capabilities.reasoning` or if the id contains `qwen` (also deepseek, glm, kimi, minimax, mistral), and `--variant` looks up `model.variants[variant]`, so `--variant high` is a silent no-op **[C binary]**. Reasoning on/off is decided by the provider default (OpenRouter 27B produced reasoning at "low", `output/harness-smoke/opencode/opencode`) or the model id (`nanogpt/…27b` gave 0 reasoning events, `…27b:thinking` gave 102; `rows.json`). `session.json` "effort" is therefore not what was sent |
| Sampling | none sent (provider defaults) | `temperature 0.55` (`lq0`: qwen→0.55, applied if the model has the temperature capability) and `top_p 1` (`cq0`: qwen→1) **[C binary]** |
| Past reasoning | re-sent as `reasoning` items with `reasoning_text` (e.g. a 14,034-char item in the 8 Oct request #176) | re-sent as `reasoning_content` only if `capabilities.interleaved.field` is set; our config does not set it, so it is likely dropped for NanoGPT **[C condition; drop-through unverified, H]** |
| Context management | Codex auto-compaction: the model writes a "CONTEXT CHECKPOINT COMPACTION" handoff summary, and history is replaced by summary + old user messages (images stripped) + new turn. SDK reports `modelContextWindow: 258400` for Qwen. Observed: 1 compaction at ~956 kB body (8 Oct 27B, request 95), 4 in the 15 Oct 27B run, 2–3 per AVO research session | Auto-compaction disabled when `model.limit.context===0` (`Gf()`), which is the case for models declared only in our config **[C binary; whether models.dev gives OpenRouter Qwen a limit is H]**. Tool-output pruning keeps the last 40 k tokens of tool output and clears older ones to "[Old tool result content cleared]" (`PRUNE_PROTECT=40000`, `PRUNE_MINIMUM=20000`). No compaction seen; the turn-by-turn 27B session reached ~279 k cached input tokens by turn 96 (`20261020T123325…/base1/agent_events.jsonl`) |
| Tool-output truncation | `exec_command` `max_output_tokens` default 10,000 tokens (schema in AVO request) | 2,000 lines / 51,200 bytes, full output saved to a file (`fo=2000, eo=51200`) |
| Turn end | model message with no tool call; wrapper takes the last `agent_message` (`codex.py` / SDK `final_response`) | step with no tool call; wrapper takes the text parts **after the last tool call** (`OpenCodeSession.normalize`) |
| Step limits | none in CLI; our turn timeout (baseline 1800 s) | none for the player (`opencode run`); Harness² improver capped at 120 steps (`frameworks/README.md`) |
| Retries | SDK retry loop on transient errors, 4 attempts (`_run_with_retry`); Codex internal retries ended in "exceeded retry limit, last status: 429" | OpenCode `SessionRetry`; NanoGPT "Service temporarily unavailable" still failed the turn (`20261020T123325…/base1/error.json`) |
| Sandbox | baseline read-only + deny-all on the host; AVO workspace-write in the Codex sandbox inside Docker | Docker only, `permission:{"*":"allow"}`, `--dangerously-skip-permissions` |

## B. Empirical: every Qwen run, by harness

Columns: route = provider and pin. img = frame image reached the model (Codex: `input_image` in request 1; OpenCode:
`session.json image_input`). rej = replies rejected by our parser ("Your last reply could not be used"). comp = Codex
compactions. Levels for Modality are out of 4. Data comes from `rows.json`, built by `runs.py` from the catalog
`GET /api/workbench/catalog` plus run files.

### B.1 Qwen 27B

| Run (`output/workbench/` unless noted) | Harness | Framework | Route | Effort (sent) | img | Game | Actions / budget | Levels (L1@action) | rej | comp | Failure / note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 20260930T223453-a4f14472, 223650-99bbfda7 (r1, r2) | old Codex | Baseline+ | OR, no pin | max | – | modality, icecrates | 0 | – | – | – | SDK pydantic rejects effort `max` |
| 20260930T224046-e0106ace (r1, r2) | old Codex | Baseline+ | OR | max | yes | modality, icecrates | 0 | – | – | – | "Unapproved model tool: get_goal" (Codex's own tool, isolation guard) |
| 20260930T224156-3572b5fe/run-0001 | old Codex | Baseline+ | OR | max | yes | modality | 124/500 | 1 (L1@28) | 0 | 0 | cancelled |
| 20260930T235825-d0dcefa8/run-0001 | old Codex | Baseline+ | OR | max | yes | modality | 3/10 | 0 | 0 | 0 | cancelled |
| 20261001T000258-18c731e5/run-0001 | old Codex | Baseline+ | OR | high | yes | modality | 36/300 | 1 (L1@31) | – | 0 | "Codex returned invalid action JSON" (old parser aborted) |
| 20261001T000258-18c731e5/run-0002 | old Codex | Baseline+ | OR | high | yes | icecrates | 2/300 | 0 | – | 0 | same abort |
| 20261001T084700-f1d4ebb7/run-0001 | old Codex | Baseline+ (continuation of 000258) | OR | high | yes | modality | 53/264 | 1 (carried) | 0 | 0 | cancelled |
| 20261008T105709-39676ef0/run-0001 | old Codex | Baseline+ | OR→DeepInfra | high | yes | modality | 30/100 | 0 | 0 | 0 | DeepInfra 400 "Too many images in request: 31 > 30" |
| `output/codex_agent/qwen27b-deepinfra-{icecrates,knightoban}-bp150-20261008` | old Codex | Baseline+ | OR→DeepInfra | high | yes | icecrates / knightoban | 30/150 each | 2 / 0 | 0 | 0 | same 31>30 image error |
| 20261008T112945-f705fa9a/run-0001 | old Codex | Baseline+ | OR→Alibaba | high | yes | modality | 100/100 | 0 | 1 | 1 | "ACTION1  note: …" format |
| 20261008T113734-5cfc3536/run-0001 | old Codex | Baseline+ | OR→Alibaba | high | yes | icecrates | 120/120 | 3 (L1@7, L2@12, L3@28) | 0 | 2 | 52× `list_mcp_resources`, 1× `request_user_input` |
| 20261008T113734-5cfc3536/run-0002 | old Codex | Baseline+ | OR→Alibaba | high | yes | knightoban | 120/120 | 0 | 0 | 0 | |
| 20260930T181429-174d62d9 (r1, r2) | old Codex | AVO | OR | medium / high | no | modality, icecrates | – | – | – | – | "Framework/private path reached model context" (guard) |
| 20260930T183705-133bda45/run-0001 | old Codex | AVO | OR | medium + high | no | modality | – | – | – | 2 | cancelled |
| 20260930T214729-8d56ea93/run-0001 | old Codex | AVO | OR | max | no | modality | – | – | – | 0 | cancelled |
| 20261013T165330-avo-27b-modality | old Codex | AVO | OR→Alibaba | high | no | modality | research 234 | research 1, solver **2** | – | 2 | stale `frame[0]` parser (`docs/research/board-claim-verification-20261019.md` #25) |
| 20261015T011847-nano-modality-baseline-plus-9da287/run-0001 | old Codex | Baseline+ | NanoGPT `27b:thinking` | high | yes | modality | 9/1000 | 0 | 0 | 0 | paused |
| **20261015T012502-…-714e64/run-0001** | old Codex | Baseline+ | NanoGPT `27b:thinking` | high | yes | modality | 386/1000 | 1 (L1@30) | **9** | **4** | all 9 rejections are leaked native Qwen tool calls (`<tool_call><function=…>` as text) |
| 20261015T011847-nano-modality-avo-27b-thinking-e8ea89 | old Codex | AVO | NanoGPT `27b:thinking` | high | no | modality | research 11 in 95 min | 0, solver exit 1 | – | 1 | leaked `<tool_call>` text in optimizer and research sessions (19 occurrences) |
| `avo/output/runs/harness-smoke-opencode-campaign` | OpenCode (pre-fix) | AVO smoke | OR | (none sent) | no | modality | 1 | 0 | – | – | smoke |
| `output/harness-smoke/opencode/opencode` | OpenCode | smoke | OR | (none) | no | – | – | – | – | – | 1 correct tool call; reasoning present |
| `output/harness2-seed-smoke-20261020` | OpenCode | Baseline (H² seed) | OR | (none) | no | modality | 0/1 | 0 | 1 | – | API 402; 0-action "completed" |
| 20261020T122910-…-27b-image-0d5815ae | OpenCode | H² base1, turn-by-turn | NanoGPT `27b` (non-thinking) | (none) | yes | modality | 8/200 | 0 | 0 | – | cancelled; **0 reasoning events**, 63 bash + 9 read in 8 turns |
| `output/image-input-smoke-27b-20261020` | OpenCode | Baseline | NanoGPT `27b` | (none) | yes | modality | 1/1 | 0 | 0 | – | describes frame correctly |
| **20261020T123325-…-27b-thinking-image-245dcdb8** | OpenCode | H² base1, turn-by-turn (no notes) | NanoGPT `27b:thinking` | (none) | yes | modality | 97/200 | 1 (L1@55) | **0** | none seen | NanoGPT 503 ended it |
| `output/h2-player-smoke-20261020` | OpenCode | H² self-driven smoke | NanoGPT `27b:thinking` | (none) | yes | modality | 12 | 0 | – | – | |
| **20261020T142237-…-27b-agent-d099cb74** | OpenCode | H² base1, self-driven `game.py` | NanoGPT `27b:thinking` | (none) | yes | modality | 200/200 | **3** (L1@17, L2@63, L3@183) | n/a | none seen | 8 transient NanoGPT 503 errors; still running at catalog time |

The catalog also lists cancelled or empty AVO/Baseline+ entries with no data: 20260930T172544 (r1, r2), 183705/r2,
214729/r2, 224156/r2, 235825/r2, 20261001T084700/r2, and 20261013T165330-avo-27b-{enqueue,icecrates,knightoban}.

### B.2 Flash and Max (context)

| Run | Harness | Framework | Route | Effort | img | Game | Actions | Levels | rej | comp | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 20261008T173758-0517f701 (r1, r2), `codex_agent/qwenflash-alibaba-modality-bp150-20261008`, `diagnostics/codex-0160-smoke-20261008` | old Codex | Baseline+ | OR→Alibaba | high | yes | modality / icecrates | 0–1 | – | – | – | 429 "exceeded retry limit" |
| 20261013T150241-d07d5558 (Flash) | old Codex | Baseline+ | OR→Alibaba | high | yes | modality | 100/100 | 1 (L1@23) | 0 | 0 | 3× `mcp__node_repl__js` |
| 20261013T150245-989f6c8b (Max) | old Codex | Baseline+ | OR→Alibaba | high | yes | modality | 100/100 | 1 (L1@17) | 0 | 0 | |
| 20261013T152559-avo-max-92c30e52 | old Codex | AVO | OR→Alibaba | high | no | modality | – | solver **4** | – | 0 | |
| 20261013T173422-avo-flash-modality-recovery | old Codex | AVO | OR→Alibaba | high | no | modality | – | research 3, solver 1 | – | 3 | |
| 20261013T152559-avo-flash-efcb5dc3 | old Codex | AVO | OR→Alibaba | high | no | modality | – | – | – | 1 | failed |
| 20261013T165330-avo-flash-knightoban | old Codex | AVO | OR→Alibaba | high | no | knightoban | – | 0 | – | 3 | cancelled |
| 20261015T012502-…-714e64/run-0002 (Flash) | old Codex | Baseline+ | NanoGPT | high | yes | modality | 296/1000 | 2 (L1@27, L2@92) | 1 | 4 | used `node_repl` 28×, `comfy_mcp` 2× |
| 20261015T011847-…-9da287/run-0002, 20261015T011847-…-avo-flash-91ad77 | old Codex | Baseline+ / AVO | NanoGPT | high | yes / no | modality | 11 / – | 0 | 1 | 0 | paused / cancelled |
| 20261020T104612-0bf1b65d (Flash) | OpenCode (pre-fix) | H² base1, turn-by-turn | NanoGPT | (none) | **no** (blind; also NanoGPT drops Flash images) | modality | 129/200 | 1 (L1@58) | 0 | none seen | cancelled |
| `output/image-input-smoke-20261020` (Flash) | OpenCode | Baseline | NanoGPT | (none) | declared; provider blind | modality | 2 | 0 | 0 | – | |

### B.3 Protocol-level failures by route (Qwen, all sizes)

| Failure | Where seen | Cause | Harness-specific? |
|---|---|---|---|
| Leaked native tool call (`<tool_call><function=…><parameter=…>` returned as assistant text) | Only Codex→NanoGPT `27b:thinking`: 9/9 rejections in `714e64/run-0001`, 19 occurrences in `avo-27b-thinking-e8ea89`. 0 in OpenCode→NanoGPT `27b:thinking` runs (123325, 142237, h2 smoke), 0 in Codex→OpenRouter/Alibaba runs (grep `<tool_call>`) | The provider's Qwen tool parser failed on the Responses path **[H: NanoGPT Responses endpoint, maybe interacting with flattened MCP names]** | route × harness |
| Too many images (31 > 30) | Codex→OpenRouter→DeepInfra, 3 runs at exactly 30 actions | Codex re-sends every past `input_image` | harness × provider |
| Reply format rejects (`ACTION1  note: …`, JSON + extra text) | Codex 8 Oct (1), Flash 15 Oct (1) | our parser (`frameworks/baseline/session.py`) | parser is shared; the reply extraction rule differs per harness (§A) |
| Effort `max` rejected | Codex SDK, 30 Sep | pydantic enum | old harness |
| Codex's own tools (`get_goal`, `request_user_input`, `list_mcp_resources`) called | 30 Sep guard abort; 52× `list_mcp_resources` (8 Oct icecrates) | Codex exposes them to any model | Codex |
| 429 / 503 transport | Codex→OR Alibaba Flash (429); OpenCode→NanoGPT (503) | provider capacity | no |

### B.4 Comparable pairs

**No pair of Qwen runs differs only by harness.** Before 15 Oct every Qwen run used the old Codex route. After 15 Oct
every one used OpenCode, and the only real OpenCode Qwen game runs are Harness² base rollouts from 20 Oct.

| Pair | Same | Different (confounds) | Use |
|---|---|---|---|
| Codex 714e64/r1 vs OpenCode 123325 (both NanoGPT `27b:thinking`, Modality, image on) | model id, provider, game, image, one action per turn, persistent session | harness, notes on vs off (Baseline+ vs files wiped), effort high sent vs none sent, budget 1000 vs 200, framework wrapper (baseline vs H² base1), host Windows vs Docker Linux, tool set (notes MCP + host MCP vs bash/edit/…), compaction (4 vs none), our prompt text | Closest available. Codex L1@30, then 386 actions without L2, 9 tool-call leaks. OpenCode L1@55 in 97, 0 rejections. Not a harness effect estimate |
| Codex 20261008T112945 vs OpenCode 123325 | Modality, 27B, image | provider and model id (OR→Alibaba `27b` vs NanoGPT `27b:thinking`), notes, effort, budget | weaker |
| OpenCode 123325 vs OpenCode 142237 | harness, model, provider, image, game, budget | player design only | already reported in `docs/diary/2026-10-20-harness2.md`. It is a framework effect (1 vs 3 levels by 200), larger than anything attributable to harness here |
| Any AVO Codex vs OpenCode | – | no OpenCode Qwen AVO run beyond a 1-candidate smoke | none |

## C. Mechanisms that plausibly change Qwen 27B's behaviour

| # | Mechanism | Direction | Evidence | Status |
|---|---|---|---|---|
| 1 | **Effort not delivered on OpenCode**: `--variant` is ignored for any id containing `qwen`. Thinking is set only by the model id (`:thinking`) or the provider default | OpenCode runs labelled "medium/high" are really provider-default thinking. `nanogpt/…27b` ran with **no reasoning at all** | `dJ()` in the binary; 0 vs 102 reasoning events (122910 vs 123325) | [C] mechanism; effect on outcomes [H] |
| 2 | **Image delivery**: OpenCode blind before `e81541c` (with an "Inform the user." instruction injected); Codex sent every frame and kept all past frames | pre-fix OpenCode = grid-only play; Codex = growing image context, enough to break DeepInfra at 31 images | binary string; Flash reasoning "Cannot see the image"; DeepInfra 400s | [C] |
| 3 | **System-prompt framing**: OpenCode prepends ~9.7 k chars of coding-agent rules ("fewer than 4 lines", "One word answers are best", lint and commit rules). Old Codex sent only our text, plus on the Windows host ~4 k chars of irrelevant skills | OpenCode pushes toward terse replies and coding tools; effect on game reasoning unknown | capture; 8 Oct request | [C] content, [H] effect |
| 4 | **Tool-call reliability on the route**: NanoGPT via Codex Responses leaked Qwen's XML tool calls as text. Each leak ends the turn as an unparseable reply (baseline) or ends the agent turn early (AVO) | Codex→NanoGPT 27B lost 9 decisions and AVO research nearly stalled (11 actions in 95 min) | transcripts, `rej.py` | [C] occurrence; cause on provider side [H] |
| 5 | **Context handling**: Codex compacts (summary written by Qwen itself, old images and reasoning dropped; 4 compactions in 386 actions). OpenCode does not compact a config-declared model and prunes tool output older than 40 k tokens | Codex: lossy self-summaries mid-game (the 8 Oct handoff summary asserted wrong "confirmed" mechanics, e.g. "A7=JUMP"). OpenCode: very long raw contexts (~279 k tokens by turn 96) and a risk of context overflow | `model_requests` scan, request 96 item 50; OpenCode usage | [C] mechanism, [H] effect |
| 6 | **Reasoning replay**: Codex re-sends prior `reasoning_text`; OpenCode/NanoGPT likely drops it (no `interleaved` field) | different memory of own reasoning across turns | request input items; binary condition | [C] Codex side, [H] OpenCode side |
| 7 | **Sampling**: OpenCode forces temperature 0.55 and top_p 1 for Qwen; Codex sends none | small | binary `lq0/cq0` | [C] |
| 8 | **Tool surface noise**: Codex exposed plan-mode, MCP-resource and host MCP tools to Qwen, and Qwen called them (52× `list_mcp_resources`, `request_user_input`, `node_repl`, `comfy_mcp`). OpenCode exposes coding tools (`bash`, `task`, `todowrite`) that the turn-by-turn player does not need; the non-thinking 27B made 72 tool calls in 8 turns | wasted turns and tokens; off-task exploration | tool counts (`calls.py`), `rows.json` | [C] occurrence, [H] effect size |
| 9 | **Reply extraction**: Codex takes the last message, OpenCode the text after the last tool call; both then go through the same JSON/action parser | can change rejection rates when the model mixes text and tools | `codex.py`, `opencode.py`, `frameworks/baseline/runner.py:116` | [C] |

Per-turn reasoning tokens give a weak signal only, because the measurements differ: the Codex SDK reports "last"
request usage, OpenCode a per-turn sum. Codex 714e64/r1 (27B): median 31, mean 503. OpenCode 123325: median 57, mean
1012 (`usage.py`). Thinking depth is not obviously different between the two harnesses for the same NanoGPT
`27b:thinking` id, which fits mechanism 1 (the id controls thinking, the effort flag does not).

## D. What a clean OpenCode-vs-Codex comparison for Qwen 27B would need (design only)

1. **Re-enable Codex for non-OpenAI models** in the current harness (it is not possible today without code):
   - allow `openrouter/`/`nanogpt/` ids for `codex` in `registry.py`;
   - pass `-c model_provider=… model_providers.X.{base_url,env_key,wire_api="responses",requires_openai_auth=false}` and the API key env;
   - set `model_context_window` / `model_auto_compact_token_limit` explicitly;
   - for OpenRouter, pin the upstream (the deleted proxy did this as a body patch; without a proxy check whether Codex
     can add `provider` to the body, **[H]** likely needs a shim).

   Prefer OpenRouter pinned to one upstream over NanoGPT, because NanoGPT Responses leaked tool calls and drops Flash
   images.
2. **Hold fixed**:
   - model id and upstream: OpenRouter `qwen/qwen3.8-27b` pinned, e.g. `alibaba`, `allow_fallbacks:false`;
   - thinking: the same mode in both arms. Because OpenCode cannot send effort for Qwen, either (a) send no effort in
     Codex either (`model_reasoning_effort` unset), or (b) force it in OpenCode through `provider.<p>.models.<m>.options`
     (e.g. `reasoning:{effort}`) and verify it in a captured body;
   - sampling: set temperature/top_p explicitly in both arms, or record that only OpenCode sends 0.55/1;
   - image: on in both, verified per run (`image_input`, the model's first description of the frame);
   - framework: the same framework, budget, game set and our prompt text. Baseline (no notes) is cleanest because it
     needs no harness-specific tools;
   - system prompt: decide whether the CLI's built-in prompt is part of the "harness" treatment. If yes, keep Codex's
     GPT template (it would be applied to Qwen) and OpenCode's `nM`. If no, override Codex with
     `model_instructions_file` and OpenCode with a custom agent prompt. Record both;
   - context policy: record or align compaction (Codex token limit vs OpenCode `limit.context` in config, which
     enables OpenCode compaction);
   - container, OS, CLI versions (Codex 0.162.1, OpenCode 1.14.19).
3. **Capture requests in both arms**. Rebuild a recording proxy, or use OpenCode's own capture as in
   `harness2-seed-smoke`, so that effort, temperature, images and tool lists are verified from bodies, not flags.
4. **Measure**:
   - levels and action index of each level, actions per level;
   - rejected replies and their type (leaked tool calls, format);
   - tool calls by name, and tool calls per action;
   - reasoning and output tokens per action, cost and wall time;
   - compactions and context size over time;
   - transport errors and retries;
   - deadlock/loop rate (repeated states);
   - for AVO-style frameworks, whether the solver reads the current frame (known 27B stale-`frame[0]` failure,
     which is a framework observation-format issue, not a harness issue).
5. **Replicates**: at least 3 seeds per arm per game. Level 1 on Modality was "partly luck in every run"
   (`docs/diary/2026-10-20-harness2.md`); single runs cannot separate harness from noise.

## Open questions

- Whether the earlier OpenCode runs were blind only because of our config, or whether models.dev listed image input
  for OpenRouter `qwen/qwen3.8-27b`. The 20 Oct Flash run is confirmed blind; the other pre-fix runs are inferred.
- Whether OpenRouter/Alibaba honours `reasoning.effort` for Qwen 3.8 (the Codex runs sent it; no A/B exists).
- Which bundled Codex 0.162.1 instruction template would be applied to an unknown (Qwen) slug.
