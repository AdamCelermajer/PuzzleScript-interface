from __future__ import annotations

import base64
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from avo.core.framework import Action, AvoLaboratory, Observation, _jsonable
from avo.core.profile import EnvironmentProfile, TaskEvaluation


@dataclass(frozen=True)
class GatewayBudget:
    max_environment_steps: int = 100
    max_wall_seconds: float = 3600


class AvoToolGateway:
    """Environment-neutral tools exposed to one persistent research agent."""

    def __init__(
        self,
        laboratory: AvoLaboratory,
        profile: EnvironmentProfile,
        *,
        budget: GatewayBudget | None = None,
        solver_self_check: Callable[[int, int], Mapping[str, Any]] | None = None,
        max_solver_self_checks: int = 2,
        max_solver_self_check_steps: int = 1_500,
    ) -> None:
        self.laboratory = laboratory
        self.profile = profile
        self.budget = budget or GatewayBudget()
        self.solver_self_check = solver_self_check
        self.max_solver_self_checks = max_solver_self_checks
        self.max_solver_self_check_steps = max_solver_self_check_steps
        self.self_checks: list[dict[str, Any]] = []
        self.started_at = time.monotonic()
        self.environment_steps = 0
        self.finished = False
        self.finish_reason = ""
        self._supervisor_attention: list[dict[str, Any]] = []
        self._checkpoints: dict[str, str] = {}
        self._lock = threading.Lock()

    def initialize(self) -> Observation:
        if self.laboratory.current is None:
            current = self.laboratory.reset()
            self.laboratory.store.append(
                "task_evaluated",
                self._task_evaluation(current),
            )
            return current
        return self.laboratory.current

    def _task_evaluation(self, current: Observation | None = None) -> TaskEvaluation:
        observation = current or self.laboratory.current
        if observation is None:
            observation = self.initialize()
        return self.profile.evaluate(tuple(self.laboratory.history), observation)

    @property
    def terminal(self) -> bool:
        return self._task_evaluation().terminal

    @property
    def success(self) -> bool:
        return self._task_evaluation().success

    def _task_payload(self) -> dict[str, Any]:
        evaluation = self._task_evaluation()
        return {
            "profile_id": self.profile.profile_id,
            "objective": self.profile.objective,
            "terminal": evaluation.terminal,
            "success": evaluation.success,
            "fitness": evaluation.fitness,
            "score": _jsonable(evaluation.score),
        }

    def _budget_payload(self) -> dict[str, Any]:
        return {
            "environment_steps_used": self.environment_steps,
            "environment_steps_remaining": max(
                0, self.budget.max_environment_steps - self.environment_steps
            ),
            "wall_seconds_remaining": max(
                0.0,
                self.budget.max_wall_seconds - (time.monotonic() - self.started_at),
            ),
            "solver_self_checks_used": len(self.self_checks),
            "solver_self_checks_remaining": max(
                0, self.max_solver_self_checks - len(self.self_checks)
            ),
        }

    def _evaluate_solver(self, params: Mapping[str, Any]) -> dict[str, Any]:
        if self.solver_self_check is None:
            raise RuntimeError("Fresh solver self-evaluation is not configured")
        if len(self.self_checks) >= self.max_solver_self_checks:
            raise RuntimeError("Solver self-evaluation limit exhausted")
        max_actions = int(params.get("max_actions", self.max_solver_self_check_steps))
        if max_actions < 1 or max_actions > self.max_solver_self_check_steps:
            raise ValueError(
                f"max_actions must be between 1 and {self.max_solver_self_check_steps}"
            )
        check_number = len(self.self_checks) + 1
        self.laboratory.store.append(
            "solver_self_check_started",
            {"check_number": check_number, "max_actions": max_actions},
        )
        try:
            private_result = dict(self.solver_self_check(check_number, max_actions))
            result = {"fitness": float(private_result["fitness"])}
            record = {
                "check_number": check_number,
                "max_actions": max_actions,
                "result": _jsonable(result),
            }
        except Exception as exc:
            record = {
                "check_number": check_number,
                "max_actions": max_actions,
                "error": f"{type(exc).__name__}: {exc}",
            }
            self.self_checks.append(record)
            self.laboratory.store.append("solver_self_check_failed", record)
            raise
        self.self_checks.append(record)
        self.laboratory.store.append("solver_self_check_completed", record)
        return {
            **record,
            "checks_remaining": max(
                0, self.max_solver_self_checks - len(self.self_checks)
            ),
            "research_budgets": self._budget_payload(),
        }

    def _observation_payload(self) -> dict[str, Any]:
        current = self.initialize()
        return {
            "observation": _jsonable(current),
            "task": self._task_payload(),
            "budgets": self._budget_payload(),
        }

    def _history_payload(self) -> dict[str, Any]:
        return {
            "transitions": _jsonable(self.laboratory.history),
            "count": len(self.laboratory.history),
            "episodes": self.laboratory.episode,
        }

    def _supervisor_payload(self) -> dict[str, Any]:
        return {
            "attention_required": bool(self._supervisor_attention),
            "events": list(self._supervisor_attention),
        }

    def _require_supervisor_clearance(self) -> None:
        if not self._supervisor_attention:
            return
        messages = "; ".join(
            str(event.get("message", "")) for event in self._supervisor_attention
        )
        raise RuntimeError(
            "Supervisor intervention requires acknowledgement before another environment "
            f"action: {messages}. Run `python avo_tool.py acknowledge_supervisor "
            '"revised approach"`.'
        )

    def _check_environment_budget(self) -> None:
        if self.finished:
            raise RuntimeError(f"Run already finished: {self.finish_reason}")
        if self.environment_steps >= self.budget.max_environment_steps:
            raise RuntimeError("Environment step budget exhausted")
        if time.monotonic() - self.started_at >= self.budget.max_wall_seconds:
            raise RuntimeError("Wall-time budget exhausted")

    def _reset(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._check_environment_budget()
        self._require_supervisor_clearance()
        reason = str(params.get("reason", "")).strip()
        if not reason:
            raise ValueError("reset requires a reason")
        self.laboratory.store.append(
            "agent_reset_requested",
            {"episode": self.laboratory.episode, "reason": reason},
        )
        current = self.laboratory.restart_episode(reason)
        self.environment_steps += 1
        task = self._task_payload()
        self.laboratory.store.append("task_evaluated", task)
        return {
            "episode": self.laboratory.episode,
            "observation": _jsonable(current),
            "task": task,
            "budgets": self._budget_payload(),
        }

    def _save_checkpoint(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._check_environment_budget()
        self.initialize()
        method = getattr(self.laboratory.environment, "save_state", None)
        if method is None:
            raise RuntimeError("This environment does not support state checkpoints")
        checkpoint_id = f"cp_{len(self._checkpoints) + 1:03d}"
        token = str(method())
        self._checkpoints[checkpoint_id] = token
        label = str(params.get("label", "")).strip()
        self.laboratory.store.append(
            "checkpoint_saved",
            {
                "checkpoint_id": checkpoint_id,
                "label": label,
                "observation_fingerprint": self.laboratory.current.fingerprint,
            },
        )
        return {"checkpoint_id": checkpoint_id, "label": label}

    def _restore_checkpoint(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._check_environment_budget()
        self._require_supervisor_clearance()
        checkpoint_id = str(params.get("checkpoint_id", "")).strip()
        token = self._checkpoints.get(checkpoint_id)
        if token is None:
            raise ValueError(f"Unknown checkpoint: {checkpoint_id}")
        method = getattr(self.laboratory.environment, "restore_state", None)
        if method is None:
            raise RuntimeError("This environment does not support state checkpoints")
        current = self.laboratory.restore_checkpoint(method(token), checkpoint_id)
        task = self._task_payload()
        self.laboratory.store.append("task_evaluated", task)
        return {
            "episode": self.laboratory.episode,
            "checkpoint_id": checkpoint_id,
            "observation": _jsonable(current),
            "task": task,
            "budgets": self._budget_payload(),
        }

    def _acknowledge_supervisor(self, params: Mapping[str, Any]) -> dict[str, Any]:
        response = str(params.get("response", "")).strip()
        if not response:
            raise ValueError("acknowledge_supervisor requires a revised approach")
        events = list(self._supervisor_attention)
        self._supervisor_attention.clear()
        self.laboratory.store.append(
            "supervisor_acknowledged",
            {"response": response, "events": events},
        )
        return {"acknowledged": True, "response": response, "events": events}

    def _archive_workspace(self, params: Mapping[str, Any]) -> dict[str, Any]:
        raw_files = params.get("files")
        if not isinstance(raw_files, Mapping):
            raise ValueError("archive requires a file mapping")
        if len(raw_files) > 1_000:
            raise ValueError("Workspace archive exceeds 1,000 files")

        decoded: dict[str, bytes] = {}
        total_bytes = 0
        for raw_name, raw_content in raw_files.items():
            name = str(raw_name).replace("\\", "/")
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or not name:
                raise ValueError(f"Unsafe workspace path: {name}")
            content = base64.b64decode(str(raw_content), validate=True)
            total_bytes += len(content)
            if total_bytes > 20_000_000:
                raise ValueError("Workspace archive exceeds 20 MB")
            decoded[name] = content

        destination = self.laboratory.store.root / "workspace"
        destination.mkdir(exist_ok=True)
        archived: list[str] = []
        for name, content in decoded.items():
            path = Path(name)
            target = destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            archived.append(name)

        result = {"archived": sorted(archived), "total_bytes": total_bytes}
        self.laboratory.store.append("workspace_archived", result)
        return result

    def _probe(self, params: Mapping[str, Any]) -> dict[str, Any]:
        self._check_environment_budget()
        self._require_supervisor_clearance()
        if self.terminal:
            raise RuntimeError("Environment is already terminal")

        current = self.initialize()
        action_id = str(params.get("action_id", "")).strip()
        if not action_id:
            raise ValueError("probe requires action_id")
        if current.available_actions and action_id not in current.available_actions:
            raise ValueError(f"Action is not currently available: {action_id}")
        rationale = str(params.get("rationale", "")).strip()

        self.laboratory.store.append(
            "agent_decision",
            {"action": Action(action_id), "rationale": rationale},
        )
        result = self.laboratory.step(Action(action_id, dict(params.get("data", {}))))
        self.environment_steps += 1
        redirects = [
            _jsonable(event)
            for event in result.supervisor_events
            if event.severity == "redirect"
        ]
        if redirects:
            self._supervisor_attention = redirects
            self.laboratory.store.append("supervisor_paused", redirects)
        task = self._task_payload()
        self.laboratory.store.append("task_evaluated", task)
        return {
            "transition": _jsonable(result.transition),
            "evaluations": _jsonable(result.evaluations),
            "supervisor_events": _jsonable(result.supervisor_events),
            "supervisor": self._supervisor_payload(),
            "task": task,
            "budgets": self._budget_payload(),
        }

    def handle(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        params = params or {}
        with self._lock:
            if method == "observe":
                return self._observation_payload()
            if method == "mission":
                self.initialize()
                return self._task_payload()
            if method == "history":
                return self._history_payload()
            if method == "archive":
                return self._archive_workspace(params)
            if method == "evaluate_solver":
                return self._evaluate_solver(params)
            if method == "probe":
                return self._probe(params)
            if method == "reset":
                return self._reset(params)
            if method == "checkpoint":
                return self._save_checkpoint(params)
            if method == "restore":
                return self._restore_checkpoint(params)
            if method == "acknowledge_supervisor":
                return self._acknowledge_supervisor(params)
            if method == "status":
                return {
                    "finished": self.finished,
                    "finish_reason": self.finish_reason,
                    "task": self._task_payload(),
                    "budgets": self._budget_payload(),
                    "episode": self.laboratory.episode,
                    "supervisor": self._supervisor_payload(),
                }
            if method == "finish":
                self.finished = True
                self.finish_reason = str(params.get("reason", "agent requested stop"))
                task = self._task_payload()
                self.laboratory.store.append(
                    "agent_finished",
                    {"reason": self.finish_reason, "task": task},
                )
                return {"finished": True, "reason": self.finish_reason, "task": task}
            raise ValueError(f"Unknown AVO tool: {method}")


AGENT_INTERFACE = """# Agent interface

The environment is unknown. Action IDs are opaque and have no implied meaning.
Use only the evidence returned by these commands.

```text
python avo_tool.py observe
python avo_tool.py mission
python avo_tool.py history
python avo_tool.py archive .
python avo_tool.py evaluate_solver --max-actions N
python avo_tool.py probe ACTION_ID --rationale "why this experiment"
python avo_tool.py reset --reason "why a fresh episode is needed"
python avo_tool.py checkpoint --label "why this state is useful"
python avo_tool.py restore CHECKPOINT_ID
python avo_tool.py acknowledge_supervisor "revised approach"
python avo_tool.py status
python avo_tool.py finish "reason"
```

You own the workspace. Organize notes, programs, simulations, tests, and intermediate
files however you find useful. The required final deliverable is documented by the task
prompt; there is no framework-owned internal hypothesis format.

`evaluate_solver` launches the current `solver.py` alone in a separate fresh game and
returns only its provisional scalar fitness. The evaluation trajectory and detailed score
are withheld from the inner session and retained as framework-owned artifacts. It does not
spend the research action budget or own final fitness. At most two self-checks are available;
revise the solver between them.

Reset starts a new episode without erasing prior evidence. Use it deliberately
when an experiment or strategy must be evaluated from a controlled initial state.
If the environment supports checkpoints, save a promising state and restore it to
test alternative continuations without replaying the whole prefix. Checkpoints are
opaque: they reveal no hidden state and restoration does not count as an action.
If the supervisor pauses environment actions, inspect its evidence and acknowledge
it with a revised approach before probing or resetting again.

The framework owns real execution and evaluation. Calling `finish` stops the
run but does not declare success; only the task evaluator can do that. Do not
edit `.avo_rpc/`. Before returning, archive the workspace so its contents become
part of the run record.
"""


AGENT_CLI = r'''from __future__ import annotations

import argparse
import base64
import json
import os
import time
import uuid
from pathlib import Path


def append_request(path, lock_path, payload):
    encoded = (json.dumps(payload) + "\n").encode("utf-8")
    with lock_path.open("r+b", buffering=0) as lock:
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.01)
            try:
                with path.open("ab", buffering=0) as stream:
                    stream.write(encoded)
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                with path.open("ab", buffering=0) as stream:
                    stream.write(encoded)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def call(method, params=None):
    root = Path(__file__).resolve().parent / ".avo_rpc"
    request_id = uuid.uuid4().hex
    payload = {"id": request_id, "method": method, "params": params or {}}
    append_request(root / "requests.jsonl", root / "requests.lock", payload)
    deadline = time.monotonic() + 3_600
    while time.monotonic() < deadline:
        try:
            lines = (root / "responses.jsonl").read_text(encoding="utf-8").splitlines()
        except OSError:
            time.sleep(0.05)
            continue
        for line in reversed(lines):
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
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
for name in ("observe", "mission", "history", "status"):
    sub.add_parser(name)
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
archive = sub.add_parser("archive")
archive.add_argument("workspace_dir", nargs="?", default=".")
evaluate_solver = sub.add_parser("evaluate_solver")
evaluate_solver.add_argument("--max-actions", type=int, default=1500)
args = parser.parse_args()
params = {}
if args.method == "probe":
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
elif args.method == "evaluate_solver":
    params["max_actions"] = args.max_actions
call(args.method, params)
'''


class FileToolServer:
    """Local filesystem RPC used by sandboxed coding agents without network access."""

    def __init__(self, gateway: AvoToolGateway, workspace: str | Path) -> None:
        from avo.core.model_view import ModelView
        self.gateway = gateway
        self.workspace = Path(workspace).resolve()
        self.model_view = ModelView(self.workspace, (gateway.laboratory.store.root,))
        self.isolation_failure: str | None = None
        self.rpc_root = self.workspace / ".avo_rpc"
        self.request_log = self.rpc_root / "requests.jsonl"
        self.response_log = self.rpc_root / "responses.jsonl"
        self.request_lock = self.rpc_root / "requests.lock"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def install(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.rpc_root.mkdir(parents=True, exist_ok=True)
        self.request_log.write_text("", encoding="utf-8")
        self.response_log.write_text("", encoding="utf-8")
        self.request_lock.write_bytes(b"0")
        (self.workspace / "avo_tool.py").write_text(AGENT_CLI, encoding="utf-8")
        (self.workspace / "AGENT_INTERFACE.md").write_text(
            AGENT_INTERFACE,
            encoding="utf-8",
        )
        (self.workspace / "MISSION.md").write_text(
            "# Mission\n\n"
            f"{self.gateway.profile.objective}\n\n"
            "Only the environment profile's task evaluator determines success.\n",
            encoding="utf-8",
        )

    def start(self) -> None:
        self.install()
        self.gateway.initialize()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _serve(self) -> None:
        processed: set[str] = set()
        offset = 0
        buffered = b""
        while not self._stop.is_set():
            try:
                with self.request_log.open("rb") as stream:
                    stream.seek(offset)
                    chunk = stream.read()
                    offset = stream.tell()
            except OSError:
                chunk = b""
            if not chunk:
                self._stop.wait(0.05)
                continue
            buffered += chunk
            lines = buffered.split(b"\n")
            buffered = lines.pop()
            for raw_line in lines:
                try:
                    request = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                request_id = str(request.get("id", ""))
                if not request_id or request_id in processed:
                    continue
                processed.add(request_id)
                try:
                    if self.isolation_failure:
                        from avo.isolation import IsolationError
                        raise IsolationError(self.isolation_failure)
                    result = self.gateway.handle(
                        str(request.get("method", "")),
                        request.get("params", {}),
                    )
                    response = {"id": request_id, "ok": True, "result": self.model_view.present(result)}
                except Exception as exc:
                    from avo.isolation import IsolationError
                    if isinstance(exc, IsolationError):
                        self.isolation_failure = str(exc)
                    response = {
                        "id": request_id,
                        "ok": False,
                        "error": self.model_view.error(exc),
                    }
                with self.response_log.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(response, default=str) + "\n")
