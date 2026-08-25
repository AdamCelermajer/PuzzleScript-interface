from __future__ import annotations

import argparse
import base64
import json
import time
import uuid
from pathlib import Path


def call(method, params=None):
    root = Path(__file__).resolve().parent / ".avo_rpc"
    request_file = root / "request.json"
    response_file = root / "response.json"
    request_id = uuid.uuid4().hex
    payload = {"id": request_id, "method": method, "params": params or {}}
    request_file.write_text(json.dumps(payload), encoding="utf-8")
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            data = json.loads(response_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            time.sleep(0.05)
            continue
        if data.get("id") == request_id:
            if not data.get("ok"):
                raise SystemExit(data.get("error", "AVO tool failed"))
            print(json.dumps(data["result"], indent=2))
            return
        time.sleep(0.05)
    raise SystemExit("AVO tool timed out")


parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest="method", required=True)
for name in ("observe", "mission", "history", "candidates", "status"):
    sub.add_parser(name)
evaluate = sub.add_parser("evaluate")
evaluate.add_argument("candidate_id")
probe = sub.add_parser("probe")
probe.add_argument("action_id")
probe.add_argument("--rationale", default="")
finish = sub.add_parser("finish")
finish.add_argument("reason")
publish = sub.add_parser("publish")
publish.add_argument("draft_dir")
args = parser.parse_args()
params = {}
if args.method == "evaluate":
    params["candidate_id"] = args.candidate_id
elif args.method == "probe":
    params.update(action_id=args.action_id, rationale=args.rationale)
elif args.method == "finish":
    params["reason"] = args.reason
elif args.method == "publish":
    draft = Path(args.draft_dir).resolve()
    if not draft.is_dir():
        raise SystemExit(f"Draft directory does not exist: {draft}")
    files = {}
    for path in sorted(draft.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            relative = path.relative_to(draft).as_posix()
            files[relative] = base64.b64encode(path.read_bytes()).decode("ascii")
    params["files"] = files
call(args.method, params)
