from __future__ import annotations

import json
import threading
from pathlib import Path

from frameworks.avo.evolution.gateway import EvolutionGateway


OPTIMIZER_INTERFACE = """# Outer AVO optimizer interface

You are the hypothesis and experiment owner. You vary and evaluate complete
player-agent packages named RunCandidates (`x_i`). You can read the frozen initial
observation and every saved event from evaluated candidates. You do not control a
game and have no gameplay actions.

```text
python avo_evolve_tool.py population
python avo_evolve_tool.py initial
python avo_evolve_tool.py inspect CANDIDATE_ID
python avo_evolve_tool.py evidence CANDIDATE_ID research --offset N --limit N
python avo_evolve_tool.py fork PARENT_ID CHILD_ID
python avo_evolve_tool.py register CANDIDATE_ID
python avo_evolve_tool.py evaluate CANDIDATE_ID
python avo_evolve_tool.py status
python avo_evolve_tool.py finish "reason"
```

Workflow:

1. If the population is empty, read `initial`, design x_0001 in the prepared
   `drafts/x_0001/`, then register and evaluate it.
2. Inspect an evaluated candidate's trusted result, notes,
   and trace summary. Page through research `evidence` whenever
   boards or transitions matter.
3. State one falsifiable hypothesis, then fork it. The child draft inherits the final notes, world_model.md, and helper programs
   produced by the parent's evaluated run.
4. Edit only `drafts/CHILD_ID/STRATEGY.md` and files below its `seed/`. Specify
   the observed failure, research question, bounded experiment, pass/fail evidence,
   and what must remain unchanged. Do not delegate the high-level hypothesis to the
   player. Prescribe a strategy change only when existing evidence already supports it.
5. Register the child, making it immutable.
6. Evaluate it from a fresh environment.

Fitness and success come only from the environment profile. Never report an
improvement before evaluation. A failed evaluation is still a completed x_i result:
inspect it and fork x_(i+1); never restart the whole experiment to erase the failure.
PuzzleScript observations in initial state and evidence may include
`metadata.rendered_frame.path`, which points to the final visible PNG for direct inspection.
Equal-fitness candidates remain in the population. Registered candidates, evaluation
artifacts, `lineage.json`, and `.avo_evolution_rpc/` are framework-owned and must not
be edited.
"""

OPTIMIZER_CLI = r'''from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path


def call(method, params=None):
    root = Path(__file__).resolve().parent / ".avo_evolution_rpc"
    request_id = uuid.uuid4().hex
    request = root / (request_id + ".request.json")
    temporary = root / (request_id + ".tmp")
    temporary.write_text(json.dumps({"id": request_id, "method": method, "params": params or {}}), encoding="utf-8")
    temporary.replace(request)
    response = root / (request_id + ".response.json")
    deadline = time.monotonic() + 86_400
    while time.monotonic() < deadline:
        try:
            data = json.loads(response.read_text(encoding="utf-8"))
            response.unlink()
        except (FileNotFoundError, PermissionError):
            # Windows may briefly deny access while an atomic rename completes.
            time.sleep(0.05)
            continue
        if not data.get("ok"):
            raise SystemExit(data.get("error", "AVO evolution tool failed"))
        print(json.dumps(data["result"], indent=2))
        return
    raise SystemExit("AVO evolution tool timed out")


parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest="method", required=True)
for name in ("population", "initial", "status"):
    sub.add_parser(name)
inspect = sub.add_parser("inspect")
inspect.add_argument("candidate_id")
evidence = sub.add_parser("evidence")
evidence.add_argument("candidate_id")
evidence.add_argument("phase", choices=("research",))
evidence.add_argument("--offset", type=int, default=0)
evidence.add_argument("--limit", type=int, default=20)
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
elif args.method == "evidence":
    params.update(
        candidate_id=args.candidate_id,
        phase=args.phase,
        offset=args.offset,
        limit=args.limit,
    )
elif args.method == "fork":
    params.update(parent_id=args.parent_id, child_id=args.child_id)
elif args.method == "finish":
    params["reason"] = args.reason
call(args.method, params)
'''


class EvolutionFileToolServer:
    """Filesystem RPC exposing only outer candidate-management operations."""

    def __init__(self, gateway: EvolutionGateway, workspace: str | Path) -> None:
        from frameworks.avo.core.model_view import ModelView
        self.gateway = gateway
        self.workspace = Path(workspace).resolve()
        self.model_view = ModelView(self.workspace, (gateway.store.root,))
        self.rpc_root = self.workspace / ".avo_evolution_rpc"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def install(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.rpc_root.mkdir(parents=True, exist_ok=True)
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
        while not self._stop.is_set():
            requests = sorted(self.rpc_root.glob("*.request.json"))
            if not requests:
                self._stop.wait(0.05)
                continue
            for request_path in requests:
                request_id = request_path.name.removesuffix(".request.json")
                try:
                    try:
                        request = json.loads(request_path.read_text(encoding="utf-8"))
                    finally:
                        # The complete payload is now in memory; never retain uploads.
                        request_path.unlink(missing_ok=True)
                    result = self.gateway.handle(
                        str(request.get("method", "")),
                        request.get("params", {}),
                    )
                    response = {"id": request_id, "ok": True, "result": self.model_view.present(result)}
                except Exception as exc:
                    response = {
                        "id": request_id,
                        "ok": False,
                        "error": self.model_view.error(exc),
                    }
                temporary = self.rpc_root / (request_id + ".response.tmp")
                temporary.write_text(json.dumps(response, default=str), encoding="utf-8")
                temporary.replace(self.rpc_root / (request_id + ".response.json"))
