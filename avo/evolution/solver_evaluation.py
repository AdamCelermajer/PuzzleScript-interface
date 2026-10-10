from __future__ import annotations

import json
import queue
import subprocess
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from avo.core.framework import Action, AvoLaboratory, JsonValue, _jsonable
from avo.core.profile import LoadedProfile
from avo.core.model_view import ModelView
from avo.isolation import IsolatedRuntime, IsolationError, new_workspace, cleanup_private_directory
from studies.codex_agent.session import _find_codex_bin


@dataclass(frozen=True)
class SolverEvaluation:
    fitness: float
    success: bool
    terminal: bool
    score: dict[str, JsonValue]
    finish_reason: str
    environment_steps: int


def evaluate_solver_workspace(
    *,
    loaded_profile: LoadedProfile,
    workspace: str | Path,
    output_dir: str | Path,
    max_environment_steps: int,
    max_wall_seconds: float,
) -> SolverEvaluation:
    """Run solver.py alone in a fresh game and score completed levels."""
    source = Path(workspace).resolve()
    if not (source / "solver.py").is_file():
        return _evaluate_solver(loaded_profile=loaded_profile, workspace=source,
                                output_dir=output_dir, max_environment_steps=max_environment_steps,
                                max_wall_seconds=max_wall_seconds, runtime=None)
    staged = new_workspace()
    if any(path.is_symlink() or path.is_junction() for path in source.rglob("*")):
        raise IsolationError("Solver archive contains a link or junction")
    shutil.copytree(source, staged, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".avo_rpc", ".tmp", "observations", "__pycache__"))
    binary = _find_codex_bin()
    if not binary:
        raise IsolationError("Codex sandbox runtime is required for fresh solver evaluation")
    runtime = IsolatedRuntime(staged, Path(output_dir), binary)
    try:
        return _evaluate_solver(loaded_profile=loaded_profile, workspace=staged,
                                output_dir=output_dir, max_environment_steps=max_environment_steps,
                                max_wall_seconds=max_wall_seconds, runtime=runtime)
    except IsolationError as exc:
        (runtime.artifacts / "infrastructure_invalid.json").write_text(
            json.dumps({"status": "infrastructure_invalid", "reason": str(exc)}), encoding="utf-8"
        )
        raise
    finally:
        runtime.close()
        cleanup_private_directory(staged)


def _evaluate_solver(*, loaded_profile: LoadedProfile, workspace: str | Path,
                     output_dir: str | Path, max_environment_steps: int,
                     max_wall_seconds: float, runtime: IsolatedRuntime | None) -> SolverEvaluation:

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
            },
            finish_reason="solver.py was not produced",
            environment_steps=0,
        )
        (output / "solver_evaluation.json").write_text(
            json.dumps(_jsonable(result), indent=2), encoding="utf-8"
        )
        return result

    laboratory = AvoLaboratory(
        loaded_profile.implementation.environment,
        [],
        output,
    )
    process_status = "completed"
    return_code: int | None = None
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    response_lines: queue.Queue[str | None] = queue.Queue()

    assert runtime is not None
    model_view = ModelView(source, (output,))
    process = subprocess.Popen(
        runtime.command(
            str(runtime.python),
            "solver.py",
            "--play",
            "--max-steps",
            str(max_environment_steps),
        ),
        cwd=source,
        env=runtime.env,
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
                "observation": model_view.present(_jsonable(laboratory.current)),
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
    if "windows sandbox failed:" in "".join(stderr_lines).lower():
        raise IsolationError("Native sandbox failed during solver evaluation")
    current = laboratory.current
    if current is None:
        raise RuntimeError("Fresh solver evaluation did not initialize the environment")
    task = loaded_profile.implementation.evaluate(tuple(laboratory.history), current)

    total = len(laboratory.history)
    levels_completed = int((current.progress or {}).get("levels_completed", 0))
    fitness = float(levels_completed)
    success = bool(task.success)
    score: dict[str, JsonValue] = {
        "solver_available": 1,
        "solver_levels_completed": levels_completed,
        "solver_environment_actions": total,
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
    return result
