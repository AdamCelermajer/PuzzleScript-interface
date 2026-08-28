from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from avo.core.framework import AvoLaboratory, JsonValue, _jsonable
from avo.core.profile import LoadedProfile
from avo.core.run_store import RunStore
from avo.core.theory_package import FilesystemTheoryCandidate
from avo.core.tool_gateway import AvoToolGateway, FileToolServer, GatewayBudget


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

    store = RunStore.create(output)
    package = store.candidates / "fresh_solver_model"
    _copy_solver_package(source, package)
    model = FilesystemTheoryCandidate(package)
    laboratory = AvoLaboratory(
        loaded_profile.implementation.environment,
        [model],
        store.root,
    )
    gateway = AvoToolGateway(
        laboratory,
        loaded_profile.implementation,
        store.candidates,
        budget=GatewayBudget(
            max_environment_steps=max_environment_steps,
            max_candidates=1,
            max_wall_seconds=max_wall_seconds,
        ),
    )

    process_status = "completed"
    return_code: int | None = None
    stdout = ""
    stderr = ""
    with tempfile.TemporaryDirectory(prefix="solver-fresh-", dir=output) as raw:
        controller_workspace = Path(raw).resolve()
        shutil.copytree(source, controller_workspace, dirs_exist_ok=True)
        server = FileToolServer(gateway, controller_workspace)
        server.start()
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "solver.py",
                    "--play",
                    "--max-steps",
                    str(max_environment_steps),
                ],
                cwd=controller_workspace,
                text=True,
                capture_output=True,
                timeout=max_wall_seconds,
                check=False,
            )
            return_code = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
            if return_code:
                process_status = f"solver.py exited {return_code}"
        except subprocess.TimeoutExpired as exc:
            process_status = "solver.py timed out"
            stdout = str(exc.stdout or "")
            stderr = str(exc.stderr or "")
        finally:
            server.stop()

    (output / "solver_stdout.txt").write_text(stdout, encoding="utf-8")
    (output / "solver_stderr.txt").write_text(stderr, encoding="utf-8")

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
        "solver_environment_actions": gateway.environment_steps,
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
        environment_steps=gateway.environment_steps,
    )
    (output / "solver_evaluation.json").write_text(
        json.dumps(_jsonable(result), indent=2), encoding="utf-8"
    )
    return result
