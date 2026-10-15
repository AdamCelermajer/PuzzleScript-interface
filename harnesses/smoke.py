"""In-container two-turn harness smoke: one shell tool call, then a resumed turn.

    uv run python -m harnesses.launch smoke --harness claude-code --model claude-haiku-5-5 --effort low
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from harnesses.registry import HARNESS_IDS, create_session

FIRST = ("Use your shell tool to run exactly this command: echo smoke-ok > smoke.txt\n"
         "Then reply with exactly the word DONE.")
SECOND = "What is the name of the file you created in the previous turn? Reply with only the file name."


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--harness", required=True, choices=HARNESS_IDS)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", default="low")
    parser.add_argument("--analysis-dir", default="/results/smoke")
    parser.add_argument("--timeout", type=float, default=300)
    options = parser.parse_args(argv)
    if options.harness == "codex":
        from harnesses.entry import prepare_credentials
        prepare_credentials("codex")
    elif options.harness == "antigravity":
        from harnesses.entry import prepare_credentials
        prepare_credentials("antigravity")
    workspace = Path(tempfile.mkdtemp(prefix="smoke-"))
    session = create_session(options.harness)
    session.start(workspace, "You are a careful assistant in a test harness.", options.model, options.effort,
                  "player", Path(options.analysis_dir) / options.harness)
    first = session.turn(FIRST, timeout=options.timeout)
    second = session.turn(SECOND, timeout=options.timeout) if first.session_id and not first.error else None
    session.close()
    file_text = (workspace / "smoke.txt").read_text().strip() if (workspace / "smoke.txt").is_file() else None
    summary = {
        "harness": options.harness, "model": options.model, "session_id": first.session_id,
        "turn1": {"text": first.text, "error": first.error, "usage": first.usage,
                  "events": [event["type"] for event in first.events]},
        "turn2": None if second is None else {"text": second.text, "error": second.error,
                                              "same_session": second.session_id == first.session_id},
        "smoke_file": file_text,
        "passed": bool(file_text == "smoke-ok" and second and "smoke" in second.text.lower()
                       and second.session_id == first.session_id),
    }
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
