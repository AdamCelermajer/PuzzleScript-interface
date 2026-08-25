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
reset = sub.add_parser("reset")
reset.add_argument("--reason", required=True)
checkpoint = sub.add_parser("checkpoint")
checkpoint.add_argument("--label", default="")
restore = sub.add_parser("restore")
restore.add_argument("checkpoint_id")
acknowledge = sub.add_parser("acknowledge_supervisor")
acknowledge.add_argument("response")
finish = sub.add_parser("finish")
finish.add_argument("reason")
publish = sub.add_parser("publish")
publish.add_argument("draft_dir")
archive = sub.add_parser("archive")
archive.add_argument("workspace_dir", nargs="?", default=".")
args = parser.parse_args()
params = {}
if args.method == "evaluate":
    params["candidate_id"] = args.candidate_id
elif args.method == "probe":
    params.update(action_id=args.action_id, rationale=args.rationale)
elif args.method == "reset":
    params["reason"] = args.reason
elif args.method == "checkpoint":
    params["label"] = args.label
elif args.method == "restore":
    params["checkpoint_id"] = args.checkpoint_id
elif args.method == "acknowledge_supervisor":
    params["response"] = args.response
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
elif args.method == "archive":
    workspace = Path(args.workspace_dir).resolve()
    if not workspace.is_dir():
        raise SystemExit(f"Workspace directory does not exist: {workspace}")
    files = {}
    for path in sorted(workspace.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(workspace)
        if ".avo_rpc" in relative_path.parts or "__pycache__" in relative_path.parts:
            continue
        relative = relative_path.as_posix()
        files[relative] = base64.b64encode(path.read_bytes()).decode("ascii")
    params["files"] = files
call(args.method, params)
