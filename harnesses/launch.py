"""Host-side launcher: one plain Docker container per run (revamp contract section 3).

    uv run python -m harnesses.launch --mode baseline-plus --harness claude-code \\
        --model claude-haiku-5-5 --effort low --game-id ps_modality-v1 \\
        --backend-url http://host.docker.internal:8000 --output-dir DIR --max-steps 3
    uv run python -m harnesses.launch login antigravity
    uv run python -m harnesses.launch check [--harness H] [--deep]

The container gets the staged controller code read-only at /controller (no games,
no .env, no outputs), the output directory at /results, and only the chosen
harness's credentials. It runs as the non-root user ``agent`` with all capabilities
dropped and normal network access. The launcher writes ``run_spec.json`` and
``launcher.json`` (container name) into the output directory and removes its own
container on exit.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harnesses.base import EFFORTS, HarnessError
from harnesses.registry import (AGY_VOLUME, HARNESS_IDS, IMAGE, ROOT, codex_auth_path, credentials_for,
                                docker_object_exists, env_values, list_harnesses, resolve_model_for)

MODES = ("baseline", "baseline-plus", "campaign")
WORLD_MODEL_MODES = ("final-only", "between-hypotheses")
# Recorded harness names of runs launched before this package existed.
LEGACY_HARNESS = {"tools": "bare"}
DEFAULT_ROOTS = {"campaign": ROOT / "avo" / "output" / "runs", "baseline": ROOT / "studies" / "codex_agent" / "output",
                 "baseline-plus": ROOT / "studies" / "codex_agent" / "output"}
CONTROLLER_TREES = ("avo", "client", "harnesses", "studies/codex_agent")
CONTROLLER_FILES = ("studies/__init__.py",)
SKIPPED_PARTS = {"output", "outputs", "__pycache__", ".venv", "rules", "tests", "legacy", "games", "docker",
                 "node_modules", "codex_request_capture"}
SUFFIXES = {".py", ".md", ".txt", ".toml"}
CONTAINER_GEMINI = "/home/agent/.gemini"
LOGIN_MARKER = ".puzzlescript-login-ok"
# Default: print mode (verified to show the sign-in URL and read a pasted code, but
# agy gives it only 60 s). --tui runs the interactive CLI instead (no such timeout;
# quit it with /quit). Afterwards a probe verifies the login and marks the volume.
LOGIN_PRINT = "agy -p 'Reply with the single word READY.' --model gemini-3.8-flash-low --output-format text"


def login_script(tui: bool = False) -> str:
    return (f"mkdir -p ~/.gemini/xdg-antigravity && cd /tmp && {'agy' if tui else LOGIN_PRINT}; "
            f"rm -f ~/.gemini/{LOGIN_MARKER}; "
            f"if timeout 60 agy models </dev/null 2>&1 | grep -v 'TLS handshake' | grep -qi gemini; then "
            f"touch ~/.gemini/{LOGIN_MARKER} && echo 'Antigravity login verified.'; "
            f"else echo 'Antigravity login NOT verified: run login again.'; exit 1; fi")


def stage_controller(destination: Path, root: Path = ROOT) -> None:
    """Copy controller source only: no games, .env, outputs, histories or credentials."""
    files = [root / name for name in CONTROLLER_FILES]
    for tree in CONTROLLER_TREES:
        files += [path for path in (root / tree).rglob("*") if path.is_file()]
    for source in files:
        relative = source.relative_to(root)
        if any(part in SKIPPED_PARTS for part in relative.parts) or source.suffix not in SUFFIXES:
            continue
        if source.name.startswith(".env"):
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def container_backend_url(url: str) -> str:
    """localhost inside the container is the container: point it at the host instead."""
    parts = urlsplit(url)
    if parts.hostname in {"localhost", "127.0.0.1", "0.0.0.0"}:
        netloc = "host.docker.internal" + (f":{parts.port}" if parts.port else "")
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    return url


def run_spec(options: argparse.Namespace) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "schema": "run-spec-v1", "mode": options.mode, "harness": options.harness, "model": options.model,
        "effort": options.effort, "game_id": options.game_id, "backend_url": options.backend_url,
        "budget": {"max_wall_seconds": int(options.max_wall_seconds)},
        "provider": options.provider or "",
        "continued_from": str(Path(options.continue_from).resolve()) if options.continue_from else None,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if options.mode == "campaign":
        spec["optimizer_model"] = options.optimizer_model or options.model
        spec["optimizer_effort"] = options.optimizer_effort or options.effort
        spec["world_model_mode"] = options.world_model_mode
        spec["budget"].update(max_evaluations=options.max_evaluations, research_moves=options.research_moves,
                              solver_moves=options.solver_moves)
    else:
        spec["budget"]["max_steps"] = options.max_steps
    return spec


def validate(options: argparse.Namespace) -> None:
    models = [options.model] + ([options.optimizer_model] if options.mode == "campaign" and options.optimizer_model else [])
    for model in models:
        provider, _ = resolve_model_for(options.harness, model)
        if options.provider and provider != "openrouter":
            raise HarnessError("--provider pins an OpenRouter upstream; it needs openrouter/... models")
    if options.provider and options.harness not in {"opencode", "bare"}:
        raise HarnessError("--provider applies to the opencode and bare harnesses only")
    if options.max_wall_seconds < 0:
        raise HarnessError("--max-wall-seconds must be >= 0 (0 = unlimited)")
    if options.mode == "campaign":
        if options.continue_from:
            raise HarnessError("--continue-from is for baseline modes; campaigns use --resume")
        for name in ("max_evaluations", "research_moves", "solver_moves"):
            if getattr(options, name) is None or getattr(options, name) <= 0:
                raise HarnessError(f"campaign requires a positive --{name.replace('_', '-')}")
    else:
        if options.resume:
            raise HarnessError("--resume is for campaigns; baseline modes use --continue-from PARENT_DIR")
        if options.max_steps is None or options.max_steps <= 0:
            raise HarnessError("baseline modes require a positive --max-steps")


def check_resume(options: argparse.Namespace, output: Path) -> None:
    """A resumed campaign keeps its game, harness, provider and world-model condition."""
    saved_path = output / "campaign" / "evolution_config.json"
    if not saved_path.is_file() or not (output / "campaign" / "lineage.json").is_file():
        raise HarnessError(f"--resume needs a saved campaign at {output / 'campaign'}")
    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    harness = saved.get("harness", "codex")
    harness = LEGACY_HARNESS.get(harness, harness)
    if harness != options.harness or saved.get("provider", "") != (options.provider or ""):
        raise HarnessError(f"Cannot change the harness while resuming (saved: {harness}, requested: {options.harness})")
    if (saved.get("profile_settings") or {}).get("game_id") not in {None, options.game_id}:
        raise HarnessError("Cannot change the game while resuming a campaign")
    if saved.get("world_model_mode", options.world_model_mode) != options.world_model_mode:
        raise HarnessError("Cannot change the world-model condition while resuming a campaign")


def stage_credentials(harness: str, models: list[str], credentials: Path,
                      env: dict[str, str] | None = None) -> tuple[list[str], dict[str, str]]:
    """Docker options and child-process env for the chosen harness's credentials only.

    Secrets are passed as ``--env NAME`` (value from the launcher's environment), so
    they never appear in the command line or launcher.json.
    """
    values = env if env is not None else env_values()
    options: list[str] = []
    child_env: dict[str, str] = {}
    for need in credentials_for(harness, models):
        if need == "codex-auth":
            source = codex_auth_path()
            payload = json.loads(source.read_text(encoding="utf-8")) if source.is_file() else {}
            if not payload.get("tokens"):
                raise HarnessError(f"codex needs a ChatGPT login in {source} (run `codex login`)")
            shutil.copyfile(source, credentials / "auth.json")
            options += ["--mount", f"type=bind,src={credentials},dst=/credentials,readonly"]
        elif need == "agy-volume":
            # Never let `docker run` silently create an empty (logged-out) volume.
            if docker_object_exists("volume", AGY_VOLUME) is False:
                raise HarnessError(f"antigravity needs the {AGY_VOLUME} volume: run "
                                   "`uv run python -m harnesses.launch login antigravity` first")
            options += ["--mount", f"type=volume,src={AGY_VOLUME},dst={CONTAINER_GEMINI}"]
        else:
            if not values.get(need):
                raise HarnessError(f"{harness} needs {need} in .env or the environment")
            child_env[need] = values[need]
            options += ["--env", need]
    return options, child_env


def docker_command(name: str, controller: Path, output: Path, extra: list[str], arguments: list[str], *,
                   memory: str = "4g", cpus: str = "2", interactive: bool = False) -> list[str]:
    command = ["docker", "run", "--name", name, "--rm", "--init",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--memory", memory, "--cpus", cpus, "--pids-limit", "1024",
               "--tmpfs", "/tmp:rw,exec,nosuid,size=1g",
               "--add-host", "host.docker.internal:host-gateway", "--env", "HARNESS_CONTAINER=1"]
    if interactive:
        command.append("-it")
    if controller is not None:
        command += ["--mount", f"type=bind,src={controller},dst=/controller,readonly"]
    if output is not None:
        command += ["--mount", f"type=bind,src={output},dst=/results"]
    return command + extra + [IMAGE, *arguments]


def _remove(name: str) -> None:
    # Exact launcher-owned name, never a sweep over other containers.
    subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)


def _run_owned(command: list[str], name: str, env: dict[str, str] | None = None) -> int:
    def stop(signum, frame):  # make SIGTERM run the finally block
        raise SystemExit(128 + signum)

    previous = signal.signal(signal.SIGTERM, stop)
    try:
        return subprocess.run(command, cwd=ROOT, env={**os.environ, **(env or {})}).returncode
    finally:
        signal.signal(signal.SIGTERM, previous)
        _remove(name)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m harnesses.launch", description=__doc__.split("\n\n")[0])
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--harness", required=True, choices=HARNESS_IDS)
    parser.add_argument("--model", required=True)
    parser.add_argument("--optimizer-model", default="")
    parser.add_argument("--optimizer-effort", default="", choices=("",) + EFFORTS)
    parser.add_argument("--effort", required=True, choices=EFFORTS)
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--max-wall-seconds", type=int, default=0, help="0 = unlimited")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--max-evaluations", type=int, default=None)
    parser.add_argument("--research-moves", type=int, default=None)
    parser.add_argument("--solver-moves", type=int, default=None)
    parser.add_argument("--world-model-mode", choices=WORLD_MODEL_MODES, default="final-only")
    parser.add_argument("--provider", default="", help="OpenRouter upstream pin (opencode/bare only)")
    parser.add_argument("--resume", action="store_true", help="campaign: continue the campaign saved in DIR")
    parser.add_argument("--continue-from", default="", help="baseline modes: replay PARENT_DIR into a new DIR")
    parser.add_argument("--memory", default="4g")
    parser.add_argument("--cpus", default="2")
    parser.add_argument("--dry-run", action="store_true", help="print the docker command and exit")
    return parser


def launch(argv: list[str]) -> int:
    parser = build_parser()
    options = parser.parse_args(argv)
    options.backend_url = container_backend_url(options.backend_url)
    try:
        validate(options)
    except HarnessError as exc:
        parser.error(str(exc))
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:6]
    output = Path(options.output_dir or DEFAULT_ROOTS[options.mode] / f"{run_id}-{options.game_id}").resolve()
    if options.resume:
        check_resume(options, output)
    elif options.mode == "campaign" and output.exists() and any(output.iterdir()):
        parser.error("A new campaign needs a fresh --output-dir (use --resume to continue one)")
    elif options.mode != "campaign" and (output / "run_config.json").exists():
        parser.error("Output directory already holds a run; use a new --output-dir")
    if options.continue_from:
        parent = Path(options.continue_from).resolve()
        if parent == output or not (parent / "run_config.json").is_file():
            parser.error("--continue-from needs a finished parent run directory, different from --output-dir")
    spec = run_spec(options)
    name = "ps-agent-" + uuid4().hex[:12]
    entry_args = ["-m", "harnesses.entry", "--spec", "/results/run_spec.json"] + (["--resume"] if options.resume else [])
    models = [options.model] + ([spec["optimizer_model"]] if options.mode == "campaign" else [])
    with tempfile.TemporaryDirectory(prefix="ps-controller-") as controller, \
            tempfile.TemporaryDirectory(prefix="ps-credentials-") as credentials:
        extra, child_env = stage_credentials(options.harness, models, Path(credentials))
        if options.continue_from:
            extra += ["--mount", f"type=bind,src={Path(options.continue_from).resolve()},dst=/parent,readonly"]
        command = docker_command(name, Path(controller), output, extra, entry_args,
                                 memory=options.memory, cpus=options.cpus)
        if options.dry_run:
            print(json.dumps({"command": command, "run_spec": spec}, indent=2))
            return 0
        output.mkdir(parents=True, exist_ok=True)
        if options.resume and (output / "run_spec.json").is_file():
            previous = json.loads((output / "run_spec.json").read_text(encoding="utf-8"))
            spec["created_at"] = previous.get("created_at", spec["created_at"])
            spec["resumed_at"] = previous.get("resumed_at", []) + [datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")]
        (output / "run_spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
        (output / "launcher.json").write_text(json.dumps({
            "container": name, "image": IMAGE, "launcher": "harnesses", "pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "command": command,
        }, indent=2), encoding="utf-8")
        stage_controller(Path(controller))
        print(f"[harnesses.launch] {options.mode} {options.harness} {options.model} -> {output} (container {name})",
              flush=True)
        return _run_owned(command, name, child_env)


def login(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m harnesses.launch login")
    parser.add_argument("harness", choices=["antigravity"])
    parser.add_argument("--tui", action="store_true", help="interactive agy instead of print mode (no 60 s limit)")
    options = parser.parse_args(argv)
    print(f"Signing Antigravity into the Docker volume {AGY_VOLUME}.\n"
          "agy prints a Google sign-in URL: open it in a browser, approve, and paste the code back here"
          + (" (then type /quit)." if options.tui else " within 60 seconds (or rerun with --tui)."),
          flush=True)
    name = "ps-agy-login-" + uuid4().hex[:8]
    command = docker_command(name, None, None, ["--mount", f"type=volume,src={AGY_VOLUME},dst={CONTAINER_GEMINI}",
                                                "--entrypoint", "bash"],
                             ["-lc", login_script(options.tui)], interactive=True)
    return _run_owned(command, name)


def check(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m harnesses.launch check")
    parser.add_argument("--harness", choices=HARNESS_IDS)
    parser.add_argument("--deep", action="store_true", help="also probe the agy login inside a container")
    options = parser.parse_args(argv)
    image = docker_object_exists("image", IMAGE)
    harnesses = [entry for entry in list_harnesses(check_docker=True)
                 if not options.harness or entry["id"] == options.harness]
    for entry in harnesses:
        entry.pop("models", None)
    result: dict[str, Any] = {"docker": image is not None, "image": IMAGE, "image_present": bool(image),
                              "agy_volume": docker_object_exists("volume", AGY_VOLUME), "harnesses": harnesses}
    if options.deep and result["agy_volume"] and (not options.harness or options.harness == "antigravity"):
        name = "ps-agy-check-" + uuid4().hex[:8]
        command = docker_command(name, None, None, ["--mount", f"type=volume,src={AGY_VOLUME},dst={CONTAINER_GEMINI}",
                                                    "--entrypoint", "bash"],
                                 ["-lc", f"test -f ~/.gemini/{LOGIN_MARKER} && cd /tmp && timeout 40 agy models </dev/null"])
        try:
            probe = subprocess.run(command, capture_output=True, text=True, timeout=90)
            text = probe.stdout + probe.stderr
            result["agy_logged_in"] = probe.returncode == 0 and "Authentication required" not in text
        finally:
            _remove(name)
    print(json.dumps(result, indent=2))
    return 0 if all(entry["ready"] for entry in harnesses) else 1


def smoke(argv: list[str]) -> int:
    """Two tiny real turns of one harness inside the image (costs one cheap model call pair)."""
    parser = argparse.ArgumentParser(prog="python -m harnesses.launch smoke")
    parser.add_argument("--harness", required=True, choices=HARNESS_IDS)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", default="low", choices=EFFORTS)
    parser.add_argument("--output-dir", default=str(ROOT / "output" / "harness-smoke"))
    options = parser.parse_args(argv)
    resolve_model_for(options.harness, options.model)
    output = Path(options.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    name = "ps-agent-smoke-" + uuid4().hex[:8]
    with tempfile.TemporaryDirectory(prefix="ps-controller-") as controller, \
            tempfile.TemporaryDirectory(prefix="ps-credentials-") as credentials:
        stage_controller(Path(controller))
        extra, child_env = stage_credentials(options.harness, [options.model], Path(credentials))
        command = docker_command(name, Path(controller), output, extra,
                                 ["-m", "harnesses.smoke", "--harness", options.harness, "--model", options.model,
                                  "--effort", options.effort, "--analysis-dir", "/results"])
        return _run_owned(command, name, child_env)


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["login"]:
        raise SystemExit(login(argv[1:]))
    if argv[:1] == ["check"]:
        raise SystemExit(check(argv[1:]))
    if argv[:1] == ["smoke"]:
        raise SystemExit(smoke(argv[1:]))
    try:
        code = launch(argv)
    except HarnessError as exc:
        print(f"harnesses.launch: {exc}", file=sys.stderr)
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
