---
date: 2026-10-21
title: Self-hosted Qwen3.8 27B FP8 on vast.ai
threads: [qwen-harness, harness-revamp]
runs: [output/thursday/vast]
commits: []
docs: [docs/research/diary-figures-20261029/qwen-era/fig1_quantization.png, docs/research/vast-setup-20261021.md, harnesses/README.md, docs/research/diary-figures-20261029/qwen-era/README.md]
reconstructed: false
---
## Did
- Served `Qwen/Qwen3.8-27B-FP8` on vast.ai instance 57041133 (4× RTX 5090) with vLLM 0.31.0: FP8 KV cache, TP4, 262,144 context, prefix caching (`--mamba-cache-mode align`), MTP with 2 draft tokens, served name `q3.8-27b-fp8`. An SSH tunnel serves it at `localhost:18100` (`scripts/vast-tunnel.ps1`).
- Added the `vast/<served-name>` provider to the opencode harness, the launcher and the workbench checks. It reads `/v1/models`, declares OpenCode's `limit`, asks for xhigh thinking, and records endpoint, weights, limit, thinking and sampling in `session.json`.
- Fixed the opencode harness after a compaction: the summary text no longer ends up in the turn's final answer.
## Found
- Prefix reuse works on the hybrid layers: an 87k-token shared start takes 15.9 s cold and 2.8 s warm (`output/thursday/vast/checks-20261021T143414-fp8kv-nomtp.json`).
- With 10 parallel cached 50k–100k contexts, MTP gave 816 tok/s total vs 572 without (+43%). A single request ran at 213 vs 104 tok/s. Acceptance was 0.70 at 10 streams and 0.90 single (`checks-20261021T144205-fp8kv-mtp2.json`).
- KV cache with MTP: 2,086,725 tokens (7.96 full contexts; 2,366,828 without MTP). Tool calls: 16/16 structured.
- OpenCode compacts only when the model declares `limit.context`, at `context − min(output, 64000)` (198,144 here). It sends temperature 0.55 / top_p 1 for ids containing "qwen", and nothing otherwise.
## Decided
- FP8 weights and FP8 KV cache only (Adam). MTP on. The served name has no "qwen", so the model's own sampling applies (1.0 / 0.95 / top_k 20). Thinking at xhigh (the maximum) everywhere.
- No restarts of the server while the batch runs.
## Next
- The main thread runs the 9-run batch on `vast/q3.8-27b-fp8`. The harness changes are still uncommitted.
