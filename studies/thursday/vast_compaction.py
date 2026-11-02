"""Does OpenCode compact a vast.ai session that outgrows its declared limit? Runs in the agents image.

The harness declares the real limit (262144 context / 64000 output, so compaction at 198144 tokens).
This test lowers it to 32000 / 12000 (compaction at 20000) and makes the agent read a large file
twice, then asks about the first answer, and reports turn errors and compaction records.

    docker run --rm --add-host host.docker.internal:host-gateway -e HARNESS_CONTAINER=1 \
      --mount type=bind,src=$PWD/harnesses,dst=/controller/harnesses,readonly \
      --mount type=bind,src=$PWD/studies,dst=/controller/studies,readonly \
      --mount type=bind,src=$PWD/output/thursday/vast/compaction,dst=/results \
      puzzlescript-agents:local -m studies.thursday.vast_compaction
"""
from __future__ import annotations

import json
from pathlib import Path

from harnesses.registry import create_session

OUT = Path("/results")
MODEL = "vast/q3.8-27b-fp8"
LIMIT = {"context": 32000, "output": 12000}
PROMPTS = ["Run `cat big.txt` with the bash tool, then tell me its last line.",
           "Run `cat big.txt` again with the bash tool and tell me its first line.",
           "Without running anything: which last line did you report in your first answer?"]


def main() -> None:
    session = create_session("opencode").start(OUT / "workspace", "You are a careful assistant.", MODEL, "medium",
                                               "player", OUT / "analysis")
    config_path = Path(session.env["OPENCODE_CONFIG"])
    config = json.loads(config_path.read_text())
    config["provider"]["vast"]["models"][MODEL.split("/", 1)[1]]["limit"] = LIMIT
    config_path.write_text(json.dumps(config, indent=2))
    colours = ("red", "blue", "green")
    (session.workspace / "big.txt").write_text("\n".join(
        f"line {i}: the {colours[i % 3]} box sits at ({i % 17},{i % 13}) next to wall {i * 7 % 101}" for i in range(1200)))
    turns = []
    for prompt in PROMPTS:
        result = session.turn(prompt, timeout=1200)
        turns.append({"prompt": prompt, "answer": result.text[-300:], "error": result.error, "usage": result.usage})
        print(json.dumps(turns[-1]), flush=True)
    records = sorted(str(path.relative_to(session.private)) for path in session.private.rglob("*")
                     if path.is_file() and b'"compaction"' in path.read_bytes())
    summary = {"limit": LIMIT, "turn_errors": [t["error"] for t in turns if t["error"]],
               "files_with_compaction_records": records,
               "events": [json.loads(line)["type"] for line in (OUT / "analysis" / "agent_events.jsonl").read_text().splitlines()]}
    print(json.dumps(summary, indent=2), flush=True)
    (OUT / "summary.json").write_text(json.dumps({"turns": turns, **summary}, indent=2))


if __name__ == "__main__":
    main()
