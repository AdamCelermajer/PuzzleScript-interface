#!/bin/bash
# On the rented 4xRTX 5090: download Qwen3.8 27B FP8 and serve it on all 4 GPUs.
# The 21 Oct setup with MTP 2 (docs/research/vast-setup-20261021.md).
# Safe to run again: the download resumes, and a running server is replaced.
set -euo pipefail

MODEL=Qwen/Qwen3.8-27B-FP8
MODELS=/workspace/models
WEIGHTS=$MODELS/Qwen3.8-27B-FP8
LOGS=/workspace/logs
PORT=18000
mkdir -p "$MODELS" "$LOGS"

gpus=$(nvidia-smi -L | wc -l)
if [ "$gpus" -ne 4 ]; then
    echo "expected 4 GPUs, found $gpus" >&2
    exit 1
fi
nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader

# The template's own server would hold the GPUs.
supervisorctl stop vllm ray >/dev/null 2>&1 || true
for pid in $(ps -eo pid,args | grep -E '[V]LLM|[r]ay::|[v]llm serve|[h]f download|[a]ria2c' | awk '{print $1}'); do
    kill -9 "$pid" 2>/dev/null || true
done
sleep 3

PATH=/venv/main/bin:$PATH
# Some hosts cap each connection (about 250 KB/s on 4 Nov, where `hf download` took hours), so this opens many.
# Every weight file is checked against the SHA-256 that Hugging Face lists, so a mirror cannot change a byte.
start=$(date +%s)
command -v aria2c >/dev/null || { apt-get update -qq; apt-get install -y -qq aria2; }
/venv/main/bin/python - "$MODEL" > "$WEIGHTS.list" <<'LIST'
import json, sys, urllib.request
model = sys.argv[1]
with urllib.request.urlopen(f"https://huggingface.co/api/models/{model}/tree/main?recursive=true", timeout=60) as response:
    files = [item for item in json.load(response) if item["type"] == "file"]
for item in files:
    name = item["path"]
    sources = [f"https://huggingface.co/{model}/resolve/main/{name}"]
    if item.get("lfs"):
        sources += [f"https://hf-mirror.com/{model}/resolve/main/{name}", f"https://www.modelscope.ai/models/{model}/resolve/master/{name}"]
    print("\t".join(sources))
    print(f"  out={name}")
    if item.get("lfs"):
        print(f"  checksum=sha-256={item['lfs']['oid']}")
LIST
aria2c --input-file="$WEIGHTS.list" --dir="$WEIGHTS" --continue=true --auto-file-renaming=false --allow-overwrite=true \
    --max-concurrent-downloads=8 --max-connection-per-server=16 --split=32 --min-split-size=20M --max-tries=0 --retry-wait=5 \
    --timeout=60 --connect-timeout=30 --uri-selector=adaptive --summary-interval=120 --console-log-level=warn --file-allocation=none
echo "download took $(($(date +%s) - start)) s: $(du -sh "$WEIGHTS" | cut -f1)"

nohup /venv/main/bin/vllm serve "$WEIGHTS" \
    --served-model-name q3.8-27b-fp8 \
    --host 127.0.0.1 --port "$PORT" \
    --tensor-parallel-size 4 --distributed-executor-backend mp \
    --max-model-len 262144 --max-num-seqs 16 --gpu-memory-utilization 0.95 --kv-cache-dtype fp8 \
    --enable-chunked-prefill --max-num-batched-tokens 8192 \
    --enable-prefix-caching --mamba-cache-mode align --enable-prompt-tokens-details \
    --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3 \
    --mm-encoder-tp-mode data \
    --default-chat-template-kwargs '{"enable_thinking": true, "reasoning_effort": "xhigh"}' \
    --speculative-config '{"method":"mtp","num_speculative_tokens":2}' \
    --enable-log-requests --max-log-len 120 \
    >"$LOGS/vllm.log" 2>&1 &
echo "started the server on port $PORT, pid $!"

for _ in $(seq 1 180); do
    if curl -fs "127.0.0.1:$PORT/v1/models" | grep -q q3.8-27b-fp8; then
        # A container can lose NVML while the running server keeps its GPUs: report it, do not fail for it.
        nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader || true
        echo SERVER_READY
        exit 0
    fi
    sleep 5
done
echo "the server did not come up in 15 minutes; log tail:" >&2
tail -n 30 "$LOGS/vllm.log" >&2
exit 1
