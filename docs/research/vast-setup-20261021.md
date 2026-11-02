# Self-hosted Qwen3.8 27B FP8 on vast.ai (21 Oct 2026)

Exact commands, so the setup can be repeated. Results are in the last section.

## Machine

- vast.ai instance 57041133: 4× RTX 5090 (32 GB each), 150 GB disk, Texas, about $5.76/h.
- Image `vastai/vllm:v0.31.0-cuda-13.0` (vLLM 0.31.0, CUDA 13.0).
- SSH: the vast proxy (`ssh3.vast.ai:34426`) refused connections after boot. Direct SSH works:
  `ssh -i C:\Users\adamc\.ssh\vastai_ed25519 -p 18609 root@99.148.65.9`
  (public IP and port from `GET https://console.vast.ai/api/v0/instances/57041133/`, field `ports["22/tcp"]`).

## 1. Stop the template's own server

The template's supervisor starts `vllm serve Qwen/Qwen3.5-9B` (with Ray) on boot.

```bash
supervisorctl stop vllm ray
ps -eo pid,args | grep -E '[V]LLM|[r]ay'    # then: kill -9 <pid> ...
```

Do not use `pkill -f VLLM` inside `ssh host '...'`: the pattern also matches the
remote shell's own command line and kills it. Anchored patterns are safe (`start.sh` uses them).

## 2. Weights (FP8 only)

```bash
hf download Qwen/Qwen3.8-27B-FP8 --cache-dir /workspace/models     # 29 GB in 53 s
```

The 16-bit weights and the template's Qwen3.5-9B blobs were deleted (the cache keeps blobs in a
shared `/workspace/models/blobs`; only blobs not referenced by the FP8 snapshot were removed).
Disk after the deletion: 30 GB used, 121 GB free.

## 3. Serve

`/workspace/serve.sh` (copied from the host with `scp -P 18609`):

```bash
#!/bin/bash
MODEL=$1; shift
exec /venv/main/bin/vllm serve "$MODEL" \
  --served-model-name q3.8-27b-fp8 \
  --download-dir /workspace/models \
  --host 127.0.0.1 --port 18000 \
  --tensor-parallel-size 4 --distributed-executor-backend mp \
  --max-model-len 262144 --max-num-seqs 16 --gpu-memory-utilization 0.95 --kv-cache-dtype fp8 \
  --enable-chunked-prefill --max-num-batched-tokens 8192 \
  --enable-prefix-caching --mamba-cache-mode align --enable-prompt-tokens-details \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3 \
  --mm-encoder-tp-mode data \
  --default-chat-template-kwargs '{"enable_thinking": true, "reasoning_effort": "xhigh"}' \
  --enable-log-requests --max-log-len 120 \
  "$@"
```

`/workspace/start.sh <log-name> [extra args]` stops the running server and starts `serve.sh` in the
background (log in `/workspace/logs/<log-name>.log`). Startup takes about 3 minutes. Example:

```bash
/workspace/start.sh vllm-fp8kv-mtp2 --speculative-config '{"method":"mtp","num_speculative_tokens":2}'
curl -s 127.0.0.1:18000/v1/models
```

Choices:

- Served name `q3.8-27b-fp8` has no "qwen" on purpose. OpenCode 1.14.19 sends temperature 0.55
  and top_p 1 for model ids containing "qwen" and sends neither otherwise, so the server's
  defaults from the model's `generation_config.json` apply: temperature 1.0, top_p 0.95, top_k 20
  (the model card's thinking-mode setting).
- Thinking: the Qwen3.8 chat template has `enable_thinking` (default on) and `reasoning_effort`
  in `xhigh` (default), `medium` or `low`. `xhigh` adds "Reasoning effort is set to xhigh. Please think
  carefully ..." to the system prompt, `low` asks for brief thinking, and `medium` adds nothing.
  "Max" is `xhigh`. The server sets it as the default, and the harness also sends it in every request.
- KV cache in FP8 (Adam's call, to fit 9–12 long conversations). vLLM warns that the checkpoint has
  no calibrated k/v/q scales (it uses 1.0).
- Prefix caching on the hybrid model: `--mamba-cache-mode align`, so the linear-attention state
  is checkpointed at block boundaries.

## 4. Tunnel (Windows host)

`scripts/vast-tunnel.ps1` forwards `127.0.0.1:18100` to the instance's `127.0.0.1:18000` and
reconnects until stopped. Docker containers reach it as `host.docker.internal:18100`.

```powershell
# start (hidden, survives this terminal)
Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','scripts\vast-tunnel.ps1'
# stop
Get-CimInstance Win32_Process | ? CommandLine -match 'vast-tunnel|18100:127.0.0.1:18000' | % { Stop-Process -Id $_.ProcessId -Force }
# check
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:18100/v1/models
```

## 5. Harness

Model id `vast/q3.8-27b-fp8`, opencode harness only. `VAST_LLM_BASE_URL` (default
`http://host.docker.internal:18100/v1`) is passed into the container. The vast.ai account key
`VAST_API_KEY` is never passed. At session start the harness reads `/v1/models`, fails fast if the
tunnel is down or the name is not served, and writes OpenCode's provider `vast`
(`@ai-sdk/openai-compatible`, dummy key, image input, `limit` = server context 262144 and
output 64000, `chat_template_kwargs` = xhigh thinking). `session.json` records `endpoint`,
`served_model`, `served_weights`, `opencode_limit`, `thinking` and `sampling`.

OpenCode compacts automatically only when the model declares `limit.context`. It compacts once a step
reaches `context - min(limit.output, 64000)` tokens, which is 198,144 here.

## 6. Checks

```bash
uv run python -m studies.thursday.vast_checks --only prefix,tools,image,reasoning,speed,long --label <label>
uv run python -m studies.thursday.capture_requests --port 18101        # what OpenCode sends
docker run --rm --add-host host.docker.internal:host-gateway -e HARNESS_CONTAINER=1 \
  --mount type=bind,src=$PWD/harnesses,dst=/controller/harnesses,readonly \
  --mount type=bind,src=$PWD/studies,dst=/controller/studies,readonly \
  --mount type=bind,src=$PWD/output/thursday/vast/compaction,dst=/results \
  puzzlescript-agents:local -m studies.thursday.vast_compaction
uv run python -m harnesses.launch --framework baseline --driver agent --harness opencode \
  --model vast/q3.8-27b-fp8 --effort medium --game-id ps_modality-v1 --backend-url http://localhost:8000 \
  --max-steps 3 --output-dir output/smoke-thu/vast-agent
```

Results: `output/thursday/vast/checks-*.json`.

## 7. Results

The final configuration is FP8 weights, FP8 KV cache and MTP with 2 draft tokens
(`/workspace/logs/vllm-fp8kv-mtp2.log`). It went live at 11:38 UTC and has not been restarted since
the batch started.

| | FP8, no MTP | FP8 + MTP 2 (kept) |
|---|---|---|
| GPU KV cache | 2,366,828 tokens (9.03× 262k) | 2,086,725 tokens (7.96× 262k) |
| 10 parallel, cached 50k–100k contexts, long thinking: total | 572 tok/s | 816 tok/s |
| same, per request | 58–59 tok/s | 91–119 tok/s |
| same, time to first token | 2.9–4.7 s | 3.1–11.4 s |
| 1 request, cached 50k context | 104 tok/s | 213 tok/s |
| MTP acceptance (10 parallel / 1) | — | 0.70 / 0.90 (mean length 2.39 / 2.79) |
| 10 cold contexts at once (750k tokens prefill) | 113 s (~6.6k tok/s) | 116 s |
| short prompt, 1 / 8 / 16 streams per stream | 108 / 88 / 76 tok/s | not measured |
| short prompt, 8 / 16 streams total | 605 / 1,079 tok/s | not measured |

The no-MTP replies were 8,000 tokens and the MTP replies 4,000 (cut for time). Rates are per token.

- Prefix reuse on the hybrid layers: an 87k-token shared start takes 15.9 s cold and 2.8 s warm
  (86,240 tokens cached), with a different ending, an exact repeat, or a continued conversation.
  The bf16 trial gave the same result (19.2 s / 3.0 s).
- Tool calls (MTP on): 16/16 structured `write_note` calls with valid JSON. Reasoning arrives in the
  `reasoning` field, apart from `content`. Image: correct colours.
- What OpenCode sends (captured through `capture_requests.py`, `output/thursday/vast/opencode-requests.jsonl`):
  `model`, `max_tokens` (= the declared `limit.output`), `chat_template_kwargs`
  `{"enable_thinking": true, "reasoning_effort": "xhigh"}`, `tool_choice: auto`, `stream`. It sends no temperature,
  top_p or reasoning_effort, so vLLM applies 1.0 / 0.95 / top_k 20. The first request of a
  session is OpenCode's title request (no tools).
- Compaction (`output/thursday/vast/compaction/summary.json`, limit lowered to 32000/12000): OpenCode
  compacted twice (summary requests 3 and 9 in the capture), each time continuing from a 4-message
  context, with no turn errors. Turn 3 still recalled the first answer. After a compaction OpenCode
  streams the summary, then a synthetic "Continue …" text part, then the answer. The harness now drops
  the first two from the final text (`test_opencode_compaction_summary_is_not_part_of_the_answer`).
- Per-reply cap: `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX` stays 64000. A larger cap is safe for vLLM
  (prompt + max_tokens is checked against 262144), but every token added is taken from the usable
  context: compaction starts at 262144 − cap. The model card suggests far larger budgets only for 1M contexts.
- vLLM warns that the FP8 KV cache uses uncalibrated scales (1.0); no quality effect was visible
  in these checks.
