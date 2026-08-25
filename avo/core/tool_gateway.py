from __future__ import annotations

import base64
import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from avo.core.framework import Action, AvoLaboratory, Observation, _jsonable
from avo.core.profile import EnvironmentProfile, TaskEvaluation
from avo.core.theory_package import TheoryPackageRegistry


@dataclass(frozen=True)
class GatewayBudget:
    max_environment_steps: int = 100
    max_candidates: int = 50
    max_wall_seconds: float = 3600


class AvoToolGateway:
    """Environment-neutral tools exposed to one persistent research agent."""

    def __init__(
        self,
        laboratory: AvoLaboratory,
        profile: EnvironmentProfile,
        candidate_workspace: str | Path,
        *,
        budget: GatewayBudget | None = None,
    ) -> None:
        self.laboratory = laboratory
        self.profile = profile
        self.registry = TheoryPackageRegistry(candidate_workspace)
        self.budget = budget or GatewayBudget()
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

    def _sync_candidates(self) -> None:
        for candidate in self.registry.discover():
            if candidate.candidate_id in self.laboratory._candidate_ids:
                continue
            if len(self.laboratory.candidates) >= self.budget.max_candidates:
                raise RuntimeError("Candidate budget exhausted")
            self.laboratory.register_candidate(candidate)

    def _budget_payload(self) -> dict[str, Any]:
        return {
            "environment_steps_used": self.environment_steps,
            "environment_steps_remaining": max(
                0, self.budget.max_environment_steps - self.environment_steps
            ),
            "candidates_used": len(self.laboratory.candidates),
            "candidate_slots_remaining": max(
                0, self.budget.max_candidates - len(self.laboratory.candidates)
            ),
            "wall_seconds_remaining": max(
                0.0,
                self.budget.max_wall_seconds - (time.monotonic() - self.started_at),
            ),
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

    def _candidates_payload(self) -> dict[str, Any]:
        self._sync_candidates()
        return {
            "candidates": [
                {
                    "candidate_id": candidate.candidate_id,
                    "parent_id": candidate.parent_id,
                    "claim": candidate.claim,
                    "complexity": candidate.complexity,
                }
                for candidate in self.laboratory.candidates
            ]
        }

    def _evaluate_candidate(self, candidate_id: str) -> dict[str, Any]:
        self._sync_candidates()
        candidate = next(
            (item for item in self.laboratory.candidates if item.candidate_id == candidate_id),
            None,
        )
        if candidate is None:
            raise ValueError(f"Unknown candidate: {candidate_id}")

        exact = 0
        covered = 0
        prospective_total = 0.0
        status_total = 0.0
        progress_total = 0.0
        errors: list[dict[str, Any]] = []
        started = time.perf_counter()
        for index, transition in enumerate(self.laboratory.history):
            try:
                prediction = candidate.predict(
                    tuple(self.laboratory.history[:index]),
                    transition.before,
                    transition.action,
                )
                if prediction.expected is None:
                    continue
                covered += 1
                comparison = self.laboratory.environment.compare(
                    prediction.expected,
                    transition.after,
                )
                exact += int(comparison.exact)
                prospective_total += comparison.prospective_accuracy
                status_total += comparison.status_accuracy
                progress_total += comparison.progress_accuracy
            except Exception as exc:
                errors.append(
                    {
                        "transition": transition.sequence,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        elapsed_ms = (time.perf_counter() - started) * 1000
        tested = len(self.laboratory.history)
        denominator = covered or 1
        scorecard = {
            "candidate_id": candidate_id,
            "valid": not errors,
            "replay": {
                "transitions_available": tested,
                "predictions_made": covered,
                "exact": exact,
                "exact_rate": exact / denominator,
                "mean_observation_accuracy": prospective_total / denominator,
                "mean_status_accuracy": status_total / denominator,
                "mean_progress_accuracy": progress_total / denominator,
                "coverage": covered / (tested or 1),
            },
            "runtime_ms": elapsed_ms,
            "errors": errors,
        }
        self.laboratory.store.append("candidate_replay_evaluated", scorecard)
        return scorecard

    def _publish_candidate(self, params: Mapping[str, Any]) -> dict[str, Any]:
        raw_files = params.get("files")
        if not isinstance(raw_files, Mapping) or "manifest.json" not in raw_files:
            raise ValueError("publish requires a package containing manifest.json")
        if len(raw_files) > 100:
            raise ValueError("Theory Package exceeds 100 files")

        decoded: dict[str, bytes] = {}
        total_bytes = 0
        for raw_name, raw_content in raw_files.items():
            name = str(raw_name).replace("\\", "/")
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or not name:
                raise ValueError(f"Unsafe Theory Package path: {name}")
            content = base64.b64decode(str(raw_content), validate=True)
            total_bytes += len(content)
            if total_bytes > 2_000_000:
                raise ValueError("Theory Package exceeds 2 MB")
            decoded[name] = content

        try:
            manifest = json.loads(decoded["manifest.json"].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("manifest.json must be valid UTF-8 JSON") from exc
        candidate_id = str(manifest.get("candidate_id", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", candidate_id):
            raise ValueError("candidate_id must be a safe 1-80 character identifier")
        target = self.registry.root / candidate_id
        if target.exists():
            raise ValueError(f"Candidate already published: {candidate_id}")
        if len(self.laboratory.candidates) >= self.budget.max_candidates:
            raise RuntimeError("Candidate budget exhausted")

        required = {"schema_version", "candidate_id", "claim", "complexity", "command"}
        missing = sorted(required - set(manifest))
        if missing:
            raise ValueError(f"manifest.json is missing: {', '.join(missing)}")
        if manifest.get("schema_version") != 1:
            raise ValueError("manifest.json schema_version must be 1")

        target.mkdir(parents=True)
        try:
            for name, content in decoded.items():
                destination = target / Path(name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
            self._sync_candidates()
        except Exception:
            for path in sorted(target.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            target.rmdir()
            raise
        candidate = next(
            item for item in self.laboratory.candidates if item.candidate_id == candidate_id
        )
        return {
            "published": True,
            "candidate": {
                "candidate_id": candidate.candidate_id,
                "parent_id": candidate.parent_id,
                "claim": candidate.claim,
                "complexity": candidate.complexity,
            },
        }

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

        self._sync_candidates()
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
            if method == "candidates":
                return self._candidates_payload()
            if method == "evaluate":
                return self._evaluate_candidate(str(params.get("candidate_id", "")))
            if method == "publish":
                return self._publish_candidate(params)
            if method == "archive":
                return self._archive_workspace(params)
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
python avo_tool.py candidates
python avo_tool.py publish drafts/CANDIDATE_DIRECTORY
python avo_tool.py evaluate CANDIDATE_ID
python avo_tool.py archive .
python avo_tool.py probe ACTION_ID --rationale "why this experiment"
python avo_tool.py reset --reason "why a fresh episode is needed"
python avo_tool.py checkpoint --label "why this state is useful"
python avo_tool.py restore CHECKPOINT_ID
python avo_tool.py acknowledge_supervisor "revised approach"
python avo_tool.py status
python avo_tool.py finish "reason"
```

You may freely create notes and tools. Author executable hypotheses under
`drafts/CANDIDATE_ID/`, then publish them with the command above. Publication
moves the agent-authored package across the trust boundary for admission and
evaluation. A hypothesis is optional; exploratory probes are allowed first.

Reset starts a new episode without erasing prior evidence. Use it deliberately
when an experiment or strategy must be evaluated from a controlled initial state.
If the environment supports checkpoints, save a promising state and restore it to
test alternative continuations without replaying the whole prefix. Checkpoints are
opaque: they reveal no hidden state and restoration does not count as an action.
If the supervisor pauses environment actions, inspect its evidence and acknowledge
it with a revised approach before probing or resetting again.

Each candidate directory contains `manifest.json` and an executable command.
The command reads a single JSON request from stdin with protocol
`avo-theory-predict-v1`, history, current observation, and action. It returns:

```json
{
  "protocol": "avo-theory-prediction-v1",
  "expected": {
    "payload": null,
    "status": "PLAYING",
    "progress": null,
    "available_actions": []
  },
  "confidence": 0.5,
  "rationale": "evidence supporting this prediction"
}
```

The framework owns real execution and evaluation. Calling `finish` stops the
run but does not declare success; only the task evaluator can do that. Do not
edit `.avo_rpc/`. Before returning, archive the workspace so notes, tools, and
unpublished drafts become part of the run record.
"""


AGENT_CLI = r'''from __future__ import annotations

import argparse
import base64
import json
import time
import uuid
from pathlib import Path


def call(method, params=None):
    root = Path(__file__).resolve().parent / ".avo_rpc"
    request_id = uuid.uuid4().hex
    request_file = root / "requests" / f"{request_id}.json"
    response_file = root / "responses" / f"{request_id}.json"
    request_file.parent.mkdir(parents=True, exist_ok=True)
    response_file.parent.mkdir(parents=True, exist_ok=True)
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
            response_file.unlink(missing_ok=True)
            request_file.unlink(missing_ok=True)
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
'''


class FileToolServer:
    """Local filesystem RPC used by sandboxed coding agents without network access."""

    def __init__(self, gateway: AvoToolGateway, workspace: str | Path) -> None:
        self.gateway = gateway
        self.workspace = Path(workspace).resolve()
        self.rpc_root = self.workspace / ".avo_rpc"
        self.request_dir = self.rpc_root / "requests"
        self.response_dir = self.rpc_root / "responses"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def install(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.request_dir.mkdir(parents=True, exist_ok=True)
        self.response_dir.mkdir(parents=True, exist_ok=True)
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
        (self.workspace / "drafts").mkdir(exist_ok=True)

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
        while not self._stop.is_set():
            pending = [
                path
                for path in sorted(self.request_dir.glob("*.json"))
                if path.stem not in processed
            ]
            if not pending:
                self._stop.wait(0.05)
                continue
            for request_file in pending:
                try:
                    request = json.loads(request_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                request_id = str(request.get("id", ""))
                if not request_id:
                    continue
                processed.add(request_id)
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
                (self.response_dir / f"{request_id}.json").write_text(
                    json.dumps(response, default=str),
                    encoding="utf-8",
                )
