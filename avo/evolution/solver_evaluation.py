from __future__ import annotations

import json
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from avo.core.framework import Action, AvoLaboratory, JsonValue, _jsonable
from avo.core.profile import LoadedProfile
from avo.core.theory_package import FilesystemTheoryCandidate


@dataclass(frozen=True)
class SolverEvaluation:
    fitness: float
    success: bool
    terminal: bool
    score: dict[str, JsonValue]
    finish_reason: str
    environment_steps: int


def _copy_solver_package(workspace: Path, package: Path) -> None:
    shutil.copytree(
        workspace,
        package,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            ".avo_rpc", "avo_tool.py", "AGENT_INTERFACE.md", "MISSION.md"
        ),
    )
    (package / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_id": "fresh_solver_model",
                "claim": "Top-level solver.py transition model evaluated prospectively.",
                "complexity": 1.0,
                "command": ["$PYTHON", "solver.py"],
            }
        ),
        encoding="utf-8",
    )


def evaluate_solver_workspace(
    *,
    loaded_profile: LoadedProfile,
    workspace: str | Path,
    output_dir: str | Path,
    max_environment_steps: int,
    max_wall_seconds: float,
) -> SolverEvaluation:
    """Run solver.py alone in a fresh game and score its held-out predictions."""

    source = Path(workspace).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    solver = source / "solver.py"
    if not solver.is_file():
        result = SolverEvaluation(
            fitness=0.0,
            success=False,
            terminal=False,
            score={
                "solver_available": 0,
                "solver_levels_completed": 0,
                "model_score": 0.0,
                "model_exact_rate": 0.0,
                "model_observation_accuracy": 0.0,
                "model_coverage": 0.0,
            },
            finish_reason="solver.py was not produced",
            environment_steps=0,
        )
        (output / "solver_evaluation.json").write_text(
            json.dumps(_jsonable(result), indent=2), encoding="utf-8"
        )
        return result

    package_root = tempfile.TemporaryDirectory(prefix="fresh-solver-model-")
    package = Path(package_root.name) / "fresh_solver_model"
    _copy_solver_package(source, package)
    model = FilesystemTheoryCandidate(package)
    laboratory = AvoLaboratory(
        loaded_profile.implementation.environment,
        [model],
        output,
    )
    process_status = "completed"
    return_code: int | None = None
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    response_lines: queue.Queue[str | None] = queue.Queue()

    process = subprocess.Popen(
        [
            sys.executable,
            "solver.py",
            "--play",
            "--max-steps",
            str(max_environment_steps),
        ],
        cwd=source,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    def read_stdout() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            stdout_lines.append(line)
            response_lines.put(line)
        response_lines.put(None)

    def read_stderr() -> None:
        assert process.stderr is not None
        stderr_lines.extend(process.stderr.readlines())

    threading.Thread(target=read_stdout, daemon=True).start()
    threading.Thread(target=read_stderr, daemon=True).start()
    laboratory.reset()
    deadline = time.monotonic() + max_wall_seconds
    try:
        for _ in range(max_environment_steps):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process_status = "solver.py timed out"
                break
            assert process.stdin is not None
            request = {
                "observation": _jsonable(laboratory.current),
                "history": _jsonable(laboratory.history),
            }
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            try:
                line = response_lines.get(timeout=min(60.0, remaining))
            except queue.Empty:
                process_status = "solver.py did not return an action within 60 seconds"
                break
            if line is None:
                return_code = process.poll()
                process_status = f"solver.py exited {return_code} before task completion"
                break
            try:
                response = json.loads(line)
                action_id = str(response["action"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                process_status = "solver.py returned an invalid action response"
                break
            current = laboratory.current
            assert current is not None
            if current.available_actions and action_id not in current.available_actions:
                process_status = f"solver.py returned unavailable action {action_id}"
                break
            laboratory.step(Action(action_id))
            current = laboratory.current
            assert current is not None
            task = loaded_profile.implementation.evaluate(
                tuple(laboratory.history), current
            )
            if task.terminal:
                break
    finally:
        if process.stdin is not None:
            process.stdin.close()
        if process.poll() is None:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.terminate()
        try:
            return_code = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            return_code = process.wait(timeout=5)
        if return_code and process_status == "completed":
            process_status = f"solver.py exited {return_code}"

    (output / "solver_stdout.txt").write_text(
        "".join(stdout_lines), encoding="utf-8"
    )
    (output / "solver_stderr.txt").write_text(
        "".join(stderr_lines), encoding="utf-8"
    )

    current = laboratory.current
    if current is None:
        raise RuntimeError("Fresh solver evaluation did not initialize the environment")
    task = loaded_profile.implementation.evaluate(tuple(laboratory.history), current)

    total = len(laboratory.history)
    covered = 0
    exact = 0
    observation_total = 0.0
    prediction_errors: list[dict[str, Any]] = []
    for index, transition in enumerate(laboratory.history):
        try:
            prediction = model.predict(
                tuple(laboratory.history[:index]),
                transition.before,
                transition.action,
            )
            if prediction.expected is None:
                continue
            covered += 1
            comparison = loaded_profile.implementation.environment.compare(
                prediction.expected, transition.after
            )
            exact += int(comparison.exact)
            observation_total += comparison.prospective_accuracy
        except Exception as exc:
            prediction_errors.append(
                {
                    "transition": transition.sequence,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    denominator = total or 1
    exact_rate = exact / denominator
    observation_accuracy = observation_total / denominator
    coverage = covered / denominator
    model_score = (3 * exact_rate + observation_accuracy) / 4
    levels_completed = int((current.progress or {}).get("levels_completed", 0))
    fitness = float(levels_completed) * model_score
    success = bool(task.success and total and exact == total)
    score: dict[str, JsonValue] = {
        "solver_available": 1,
        "solver_levels_completed": levels_completed,
        "solver_environment_actions": total,
        "model_score": model_score,
        "model_exact_rate": exact_rate,
        "model_observation_accuracy": observation_accuracy,
        "model_coverage": coverage,
        "model_predictions_exact": exact,
        "model_transitions_tested": total,
        "model_prediction_errors": _jsonable(prediction_errors),
        "environment_task": _jsonable(task),
        "solver_return_code": return_code,
    }
    result = SolverEvaluation(
        fitness=fitness,
        success=success,
        terminal=task.terminal,
        score=score,
        finish_reason=process_status,
        environment_steps=total,
    )
    (output / "solver_evaluation.json").write_text(
        json.dumps(_jsonable(result), indent=2), encoding="utf-8"
    )
    package_root.cleanup()
    return result
