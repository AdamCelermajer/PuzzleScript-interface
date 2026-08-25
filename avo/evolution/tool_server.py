from __future__ import annotations

import json
import threading
from pathlib import Path

from avo.evolution.gateway import EvolutionGateway


OPTIMIZER_INTERFACE = """# Outer AVO optimizer interface

You vary and evaluate complete player-agent packages named RunCandidates (`x_i`).
You do not control the environment and have no gameplay actions.

```text
python avo_evolve_tool.py population
python avo_evolve_tool.py inspect CANDIDATE_ID
python avo_evolve_tool.py fork PARENT_ID CHILD_ID
python avo_evolve_tool.py register CANDIDATE_ID
python avo_evolve_tool.py evaluate CANDIDATE_ID
python avo_evolve_tool.py status
python avo_evolve_tool.py finish "reason"
```

Workflow:

1. Evaluate an unevaluated registered candidate.
2. Inspect its trusted result.
3. Fork it. The child draft inherits the final notes and helper programs produced
   by the parent's evaluated run.
4. Edit only `drafts/CHILD_ID/STRATEGY.md` and files below its `workspace/`.
5. Register the child, making it immutable.
6. Evaluate it from a fresh environment.

Fitness and success come only from the environment profile. Never report an
improvement before evaluation. Equal-fitness candidates remain in the population.
Registered candidates, evaluation artifacts, `population.json`, and `.avo_evolution_rpc/`
are framework-owned and must not be edited.
"""


OPTIMIZER_CLI = r'''from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path


def call(method, params=None):
    root = Path(__file__).resolve().parent / ".avo_evolution_rpc"
    request_file = root / "request.json"
    response_file = root / "response.json"
    request_id = uuid.uuid4().hex
    request_file.write_text(
        json.dumps({"id": request_id, "method": method, "params": params or {}}),
        encoding="utf-8",
    )
    deadline = time.monotonic() + 86_400
    while time.monotonic() < deadline:
        try:
            data = json.loads(response_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            time.sleep(0.05)
            continue
        if data.get("id") == request_id:
            if not data.get("ok"):
                raise SystemExit(data.get("error", "AVO evolution tool failed"))
            print(json.dumps(data["result"], indent=2))
            return
        time.sleep(0.05)
    raise SystemExit("AVO evolution tool timed out")


parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest="method", required=True)
for name in ("population", "status"):
    sub.add_parser(name)
inspect = sub.add_parser("inspect")
inspect.add_argument("candidate_id")
fork = sub.add_parser("fork")
fork.add_argument("parent_id")
fork.add_argument("child_id")
register = sub.add_parser("register")
register.add_argument("candidate_id")
evaluate = sub.add_parser("evaluate")
evaluate.add_argument("candidate_id")
finish = sub.add_parser("finish")
finish.add_argument("reason")
args = parser.parse_args()
params = {}
if args.method in {"inspect", "register", "evaluate"}:
    params["candidate_id"] = args.candidate_id
elif args.method == "fork":
    params.update(parent_id=args.parent_id, child_id=args.child_id)
elif args.method == "finish":
    params["reason"] = args.reason
call(args.method, params)
'''


class EvolutionFileToolServer:
    """Filesystem RPC exposing only outer candidate-management operations."""

    def __init__(self, gateway: EvolutionGateway, workspace: str | Path) -> None:
        self.gateway = gateway
        self.workspace = Path(workspace).resolve()
        self.rpc_root = self.workspace / ".avo_evolution_rpc"
        self.request_file = self.rpc_root / "request.json"
        self.response_file = self.rpc_root / "response.json"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def install(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.rpc_root.mkdir(parents=True, exist_ok=True)
        self.request_file.write_text("{}", encoding="utf-8")
        self.response_file.write_text("{}", encoding="utf-8")
        (self.workspace / "avo_evolve_tool.py").write_text(
            OPTIMIZER_CLI,
            encoding="utf-8",
        )
        (self.workspace / "AGENT_INTERFACE.md").write_text(
            OPTIMIZER_INTERFACE,
            encoding="utf-8",
        )
        (self.workspace / "MISSION.md").write_text(
            "# Mission\n\n" + self.gateway.mission.strip() + "\n",
            encoding="utf-8",
        )
        (self.workspace / "drafts").mkdir(exist_ok=True)

    def start(self) -> None:
        self.install()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _serve(self) -> None:
        last_request_id = ""
        while not self._stop.is_set():
            try:
                request = json.loads(self.request_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._stop.wait(0.05)
                continue
            request_id = str(request.get("id", ""))
            if not request_id or request_id == last_request_id:
                self._stop.wait(0.05)
                continue
            last_request_id = request_id
            try:
                result = self.gateway.handle(
                    str(request.get("method", "")),
                    request.get("params", {}),
                )
                response = {"id": request_id, "ok": True, "result": result}
            except Exception as exc:
                response = {
                    "id": request_id,
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            self.response_file.write_text(
                json.dumps(response, default=str),
                encoding="utf-8",
            )
