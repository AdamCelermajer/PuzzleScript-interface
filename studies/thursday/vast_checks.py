"""Checks for the self-hosted Qwen3.8 27B endpoint (vLLM on vast.ai) before experiments.

- ``prefix``: a ~100k-token shared start sent cold, then with a different ending, then as a
  continued conversation. The model has linear-attention layers, so reuse is not a given.
- ``tools``: the probe_tool_calls synthetic chat requests (write_note, short and long note);
  every reply must carry a structured ``tool_calls`` entry.
- ``image``: a generated PNG with known colours.
- ``reasoning``: thinking must arrive in the reasoning field, not in ``content``.
- ``speed``: decode tokens/s for 1 and for N parallel streams (short prompt, no thinking).
- ``long``: N games at once: each request continues its own cached 50k-100k context and
  thinks at length; then the same with 1 request.

    uv run python -m studies.thursday.vast_checks --base-url http://localhost:18100/v1
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import random
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from studies.thursday.probe_tool_calls import TASKS, read, synthetic

OUT = Path("output/thursday/vast")


def post(base: str, body: dict, timeout: float = 1800) -> tuple[list[dict], float | None, float]:
    """Stream one chat request; return (events, seconds to first token, total seconds)."""
    body = {**body, "stream": True, "stream_options": {"include_usage": True}}
    request = urllib.request.Request(f"{base}/chat/completions", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer unused"})
    started, first, events = time.time(), None, []
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                continue
            event = json.loads(line[5:].strip())
            delta = ((event.get("choices") or [{}])[0].get("delta") or {}) if event.get("choices") else {}
            if first is None and any(delta.get(k) for k in ("content", "reasoning", "reasoning_content", "tool_calls")):
                first = time.time() - started
            events.append(event)
    return events, first, time.time() - started


def usage(events: list[dict]) -> dict:
    return next((e["usage"] for e in reversed(events) if e.get("usage")), {}) or {}


def spec_counters(base: str) -> dict[str, float]:
    """vLLM speculative-decoding counters (empty without a draft model)."""
    text = urllib.request.urlopen(base.removesuffix("/v1") + "/metrics", timeout=20).read().decode()
    totals: dict[str, float] = {}
    for line in text.splitlines():
        for name in ("num_drafts", "num_draft_tokens", "num_accepted_tokens"):
            if line.startswith(f"vllm:spec_decode_{name}_total"):
                totals[name] = totals.get(name, 0) + float(line.rsplit(" ", 1)[1])
    return totals


def acceptance(before: dict, after: dict) -> dict:
    drafts = after.get("num_drafts", 0) - before.get("num_drafts", 0)
    proposed = after.get("num_draft_tokens", 0) - before.get("num_draft_tokens", 0)
    accepted = after.get("num_accepted_tokens", 0) - before.get("num_accepted_tokens", 0)
    if not proposed:
        return {}
    return {"acceptance_rate": round(accepted / proposed, 3), "mean_accepted_length": round(1 + accepted / drafts, 2)}


def game_log(lines: int, seed: int = 7) -> str:
    """About 26 tokens per line."""
    rng = random.Random(seed)
    words = "box wall goal player crate door key ice hole switch lava gem".split()
    return "\n".join(f"step {i}: ACTION{rng.randint(1, 5)} -> player ({rng.randint(0, 15)},{rng.randint(0, 15)}), "
                     f"{rng.choice(words)} near {rng.choice(words)}, score {rng.randint(0, 999)}" for i in range(lines))


def check_prefix(base: str, model: str, lines: int) -> dict:
    log = game_log(lines)
    start = [{"role": "system", "content": "You read game logs and answer briefly."},
             {"role": "user", "content": f"Game log:\n{log}\n\nQuestion: "}]

    def ask(messages: list[dict], label: str) -> dict:
        events, first, total = post(base, {"model": model, "messages": messages, "max_tokens": 64,
                                           "chat_template_kwargs": {"enable_thinking": False}})
        text, _, _, _, _ = read("chat", events)
        used = usage(events)
        row = {"label": label, "prompt_tokens": used.get("prompt_tokens"),
               "cached_tokens": (used.get("prompt_tokens_details") or {}).get("cached_tokens"),
               "ttft_s": round(first or total, 2), "total_s": round(total, 2), "answer": text[:80]}
        print(f"  {label:34s} prompt {row['prompt_tokens']:>7} cached {row['cached_tokens']!s:>7} "
              f"ttft {row['ttft_s']:6.2f}s", flush=True)
        return row

    def question(text: str) -> list[dict]:
        return start[:1] + [{"role": "user", "content": start[1]["content"] + text}]

    first = ask(question("which action number appears in the last step?"), "cold: shared start + question A")
    other = ask(question("what is the score in step 10?"), "warm: same start + question B")
    again = ask(question("which action number appears in the last step?"), "repeat of A")
    follow = ask(question("which action number appears in the last step?")
                 + [{"role": "assistant", "content": first["answer"]},
                    {"role": "user", "content": "And in the step before it?"}], "continued conversation after A")
    return {"rows": [first, other, again, follow]}


def check_tools(base: str, model: str, repeats: int, parallel: int) -> dict:
    jobs = [task for task in TASKS for _ in range(repeats)]

    def one(task: str) -> dict:
        _, body = synthetic("chat", task, model)
        events, _, total = post(base, body)
        text, reasoning, calls, _, error = read("chat", events)
        outcome = ("tool call" if calls else "text leak" if "<tool_call>" in text or "<function=" in text
                   else "error" if error else "no call")
        valid = all(_json_ok(call["arguments"]) for call in calls)
        return {"task": task, "outcome": outcome, "names": [c["name"] for c in calls], "args_json": valid,
                "reasoning_chars": len(reasoning), "seconds": round(total, 1), "text": text[:200]}

    with ThreadPoolExecutor(parallel) as pool:
        rows = list(pool.map(one, jobs))
    good = sum(r["outcome"] == "tool call" and r["args_json"] and r["names"] == ["write_note"] for r in rows)
    print(f"  structured write_note calls with valid JSON: {good}/{len(rows)}", flush=True)
    for row in rows:
        if row["outcome"] != "tool call":
            print(f"    {row['task']}: {row['outcome']} {row['text'][:120]!r}", flush=True)
    return {"good": good, "total": len(rows), "rows": rows}


def _json_ok(text: str) -> bool:
    try:
        return isinstance(json.loads(text), dict)
    except ValueError:
        return False


def check_image(base: str, model: str) -> dict:
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (96, 96), (0, 0, 255))
    ImageDraw.Draw(image).rectangle((24, 24, 71, 71), fill=(255, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    messages = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": url}},
        {"type": "text", "text": "Name the colour of the square in the middle and the colour of the background."}]}]
    events, _, total = post(base, {"model": model, "messages": messages, "max_tokens": 64,
                                   "chat_template_kwargs": {"enable_thinking": False}})
    text = read("chat", events)[0]
    ok = "red" in text.lower() and "blue" in text.lower()
    print(f"  image answer ({'ok' if ok else 'WRONG'}, {total:.1f}s, {usage(events).get('prompt_tokens')} prompt tokens): "
          f"{text.strip()[:120]!r}", flush=True)
    return {"ok": ok, "answer": text, "prompt_tokens": usage(events).get("prompt_tokens")}


def check_reasoning(base: str, model: str) -> dict:
    events, _, _ = post(base, {"model": model, "max_tokens": 4000, "messages": [
        {"role": "user", "content": "A box is at (2,3). The player pushes it right twice. Where is it? Answer with the coordinates only."}]})
    fields = {key for e in events for c in e.get("choices") or [] for key, value in (c.get("delta") or {}).items() if value}
    text, reasoning, _, _, _ = read("chat", events)
    ok = bool(reasoning.strip()) and "<think>" not in text and "</think>" not in text
    print(f"  reasoning {len(reasoning)} chars in {sorted(fields - {'role', 'content'})}, answer {text.strip()[:60]!r}: "
          f"{'separate' if ok else 'NOT separate'}", flush=True)
    return {"ok": ok, "delta_fields": sorted(fields), "reasoning_chars": len(reasoning), "answer": text}


def check_speed(base: str, model: str, streams: int, tokens: int) -> dict:
    body = {"model": model, "max_tokens": tokens, "messages": [{"role": "user", "content":
            "Write a long, detailed guide to solving Sokoban puzzles: deadlocks, corridors, goal ordering and examples."}],
            "chat_template_kwargs": {"enable_thinking": False}}

    def one(_: int) -> dict:
        events, first, total = post(base, body)
        produced = usage(events).get("completion_tokens") or 0
        return {"tokens": produced, "decode_s": total - (first or 0), "total_s": total}

    result = {}
    for count in streams:
        counters, started = spec_counters(base), time.time()
        with ThreadPoolExecutor(count) as pool:
            rows = list(pool.map(one, range(count)))
        wall = time.time() - started
        per_stream = sum(r["tokens"] / r["decode_s"] for r in rows) / count
        result[f"{count}_streams"] = {"per_stream_tok_s": round(per_stream, 1),
                                      "aggregate_tok_s": round(sum(r["tokens"] for r in rows) / wall, 1),
                                      "tokens_each": [r["tokens"] for r in rows], **acceptance(counters, spec_counters(base))}
        print(f"  {count:2d} stream(s): {per_stream:6.1f} tok/s per stream, "
              f"{result[f'{count}_streams']['aggregate_tok_s']:7.1f} tok/s total "
              f"{result[f'{count}_streams'].get('acceptance_rate', '')}", flush=True)
    return result


def check_long(base: str, model: str, games: int, tokens: int) -> dict:
    """Each game has its own log (50k-100k tokens), cached by a first request, then continued."""
    logs = [game_log(1900 + i * 1900 // max(games - 1, 1), seed=100 + i) for i in range(games)]
    task = ("Assume ACTION1=up (y-1), ACTION2=down (y+1), ACTION3=left (x-1), ACTION4=right (x+1), ACTION5=no move. "
            "Starting from the player position in the 40th-to-last step, predict the position after each of the "
            "last 40 steps, compare every prediction with the log, and explain each mismatch.")

    def one(index: int, question: str, max_tokens: int) -> dict:
        messages = [{"role": "system", "content": "You analyse game logs carefully."},
                    {"role": "user", "content": f"Game log:\n{logs[index]}\n\nQuestion: {question}"}]
        events, first, total = post(base, {"model": model, "messages": messages, "max_tokens": max_tokens})
        used = usage(events)
        produced = used.get("completion_tokens") or 0
        return {"game": index, "prompt_tokens": used.get("prompt_tokens"),
                "cached_tokens": (used.get("prompt_tokens_details") or {}).get("cached_tokens"),
                "ttft_s": round(first or total, 2), "tokens": produced, "total_s": round(total, 1),
                "tok_s": round(produced / max(total - (first or 0), 1e-6), 1)}

    def batch(label: str, indexes: list[int], question: str, max_tokens: int) -> dict:
        counters, started = spec_counters(base), time.time()
        with ThreadPoolExecutor(len(indexes)) as pool:
            rows = list(pool.map(lambda i: one(i, question, max_tokens), indexes))
        wall = time.time() - started
        summary = {"requests": len(rows), "wall_s": round(wall, 1), **acceptance(counters, spec_counters(base)),
                   "ttft_s": [r["ttft_s"] for r in rows], "prompt_tokens": [r["prompt_tokens"] for r in rows],
                   "cached_tokens": [r["cached_tokens"] for r in rows], "tokens": [r["tokens"] for r in rows],
                   "tok_s_per_request": [r["tok_s"] for r in rows],
                   "total_tok_s": round(sum(r["tokens"] for r in rows) / wall, 1)}
        print(f"  {label}: wall {wall:.0f}s, ttft {min(summary['ttft_s']):.1f}-{max(summary['ttft_s']):.1f}s, "
              f"prompt {min(summary['prompt_tokens'])}-{max(summary['prompt_tokens'])}, "
              f"cached {min(c or 0 for c in summary['cached_tokens'])}-{max(c or 0 for c in summary['cached_tokens'])}, "
              f"reply {min(summary['tokens'])}-{max(summary['tokens'])} tok, per request "
              f"{min(summary['tok_s_per_request'])}-{max(summary['tok_s_per_request'])} tok/s, "
              f"total {summary['total_tok_s']} tok/s"
              + (f", acceptance {summary['acceptance_rate']} (mean length {summary['mean_accepted_length']})"
                 if "acceptance_rate" in summary else ""), flush=True)
        return summary

    indexes = list(range(games))
    return {"cold_start": batch(f"{games} cold contexts at once (max_tokens 1)", indexes, "Reply OK.", 1),
            "parallel": batch(f"{games} cached contexts + long thinking", indexes, task, tokens),
            "single": batch("1 cached context + long thinking", [0], task + " Be thorough.", tokens)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:18100/v1")
    parser.add_argument("--model", default="q3.8-27b-fp8")
    parser.add_argument("--only", default="prefix,tools,image,reasoning,speed,long")
    parser.add_argument("--prefix-lines", type=int, default=3300, help="about 26 tokens per line")
    parser.add_argument("--repeats", type=int, default=8, help="tool probes per task (2 tasks)")
    parser.add_argument("--streams", default="1,8,16")
    parser.add_argument("--tokens", type=int, default=1500)
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--long-tokens", type=int, default=8000)
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    served = json.load(urllib.request.urlopen(f"{base}/models", timeout=20))["data"]
    print(f"{base}: {[(m['id'], m.get('root'), m.get('max_model_len')) for m in served]}", flush=True)
    results: dict = {"base_url": base, "served": [(m["id"], m.get("root")) for m in served], "label": args.label}
    checks = {"prefix": lambda: check_prefix(base, args.model, args.prefix_lines),
              "tools": lambda: check_tools(base, args.model, args.repeats, 8),
              "image": lambda: check_image(base, args.model),
              "reasoning": lambda: check_reasoning(base, args.model),
              "speed": lambda: check_speed(base, args.model, [int(n) for n in args.streams.split(",")], args.tokens),
              "long": lambda: check_long(base, args.model, args.games, args.long_tokens)}
    for name in args.only.split(","):
        print(f"[{name}]", flush=True)
        results[name] = checks[name]()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"checks-{time.strftime('%Y%m%dT%H%M%S')}{'-' + args.label if args.label else ''}.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"saved {path}")


if __name__ == "__main__":
    main()
