"""Durable bounded batch worker; API restarts do not abandon owned child processes."""
from __future__ import annotations

import subprocess
import os
import re
import sys
import time
from pathlib import Path

from workbench.catalog import ROOT, read_json
from workbench.experiments import write_json


REPORT_GRACE_SECONDS = 600
HARNESS_IDS = {"codex", "claude-code", "opencode", "antigravity", "bare"}
LEGACY_BACKENDS = {"codex", "tools", "raw"}


def batch_deadline(config: dict, started: float) -> float | None:
    """Legacy batches share one `max_hours` cutoff that includes queued runs.
    Harness batches have no batch cutoff: each run owns `max_wall_seconds`
    (0 = unlimited), backstopped per child in `overdue`."""
    if "budget" in config or config.get("launcher") == "harnesses":
        return None
    hours = config.get("max_hours", 0)
    return started + hours * 3600 + REPORT_GRACE_SECONDS if hours > 0 else None


def overdue(row: dict, now: float) -> bool:
    wall = row.get("max_wall_seconds") or 0
    return (row.get("launcher") == "harnesses" and wall > 0
            and now >= row.get("started_at", now) + wall + REPORT_GRACE_SECONDS)


def check_launchable(row: dict, config: dict) -> None:
    if row.get("launcher") == "harnesses":
        if row.get("harness") not in HARNESS_IDS:
            raise ValueError(f"Saved job uses an unknown harness: {row.get('harness')}")
        return
    if row.get("agent_backend", config.get("agent_backend", "codex")) not in LEGACY_BACKENDS:
        raise ValueError("Saved job uses a retired agent backend; create a new Codex experiment")


def stop_child(process, row):
    if process.poll() is not None:
        return
    # Removing this exact container lets its launcher execute credential cleanup.
    launch = read_json(Path(row["output"]) / "launcher.json")
    container = str(launch.get("container", ""))
    owned = (row["kind"] == "avo" and container.startswith("avo-isolated-")) or (
        row.get("launcher") == "harnesses" and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", container))
    if owned:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=20)
        try:
            process.wait(timeout=20)
            return
        except subprocess.TimeoutExpired:
            pass
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=20)
    else:
        import os, signal
        os.killpg(process.pid, signal.SIGTERM)
    process.wait(timeout=20)


def next_rows(rows: list[dict], slots: int, comparison: bool) -> list[dict]:
    pending = [row for row in rows if row["status"] == "queued"]
    if not comparison:
        return pending[:slots]
    ready = []
    pair_order = list(dict.fromkeys(row.get("pair_id") for row in rows))
    if any(not pair_id for pair_id in pair_order):
        raise ValueError("Comparison manifest has an incomplete pair")
    for pair_id in pair_order:
        pair_rows = [row for row in rows if row.get("pair_id") == pair_id]
        if len(pair_rows) != 2:
            raise ValueError("Comparison manifest has an incomplete pair")
        pair = [row for row in pair_rows if row["status"] == "queued"]
        if len(ready) + len(pair) > slots:
            break
        ready.extend(pair)
    return ready


def run_job(directory: Path):
    manifest_path = directory / "job.json"
    job = read_json(manifest_path)
    config = job["config"]
    # Campaigns use max_hours as their search budget; keep room for the final report turn.
    deadline = batch_deadline(config, time.time())
    active = []
    cancelled = False
    paused = False
    job["status"] = "running"
    job["worker_pid"] = os.getpid()
    manifest_blocked = False
    try:
        while True:
            if (directory / "pause.request").exists():
                paused = True
                break
            if (directory / "stop.request").exists() or (deadline is not None and time.time() >= deadline):
                cancelled = True
                break
            for entry in active[:]:
                row, proc, log = entry
                if proc.poll() is None and overdue(row, time.time()):
                    # The harness enforces its own wall budget; this only backstops a hung child.
                    stop_child(proc, row)
                    row["error"] = "Exceeded its wall budget plus grace; stopped by the batch worker"
                code = proc.poll()
                if code is not None:
                    row.update(status="completed" if code == 0 else "failed", returncode=code)
                    log.close()
                    active.remove(entry)
            for row in next_rows(job["runs"], config["parallel"]-len(active), config.get("comparison", False)):
                check_launchable(row, config)
                # The CLI owns creation of a fresh run directory (especially continuation).
                log = (directory / (Path(row["output"]).name + ".log")).open("wb")
                try:
                    proc = subprocess.Popen(row["command"], cwd=ROOT, stdout=log, stderr=log,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                            start_new_session=sys.platform != "win32")
                except OSError:
                    log.close()
                    raise
                row.update(status="running", pid=proc.pid, started_at=time.time())
                active.append((row, proc, log))
            job["heartbeat"] = time.time()
            try:
                write_json(manifest_path, job)
                manifest_blocked = False
            except PermissionError:
                # A status-file lock must not kill an otherwise healthy solver.
                # Stop requests and the deadline are still checked next cycle.
                if not manifest_blocked:
                    print("Manifest replacement is blocked; keeping owned runs alive and retrying.",
                          file=sys.stderr, flush=True)
                manifest_blocked = True
            if not active and all(row["status"] != "queued" for row in job["runs"]):
                break
            time.sleep(1)
    except BaseException as exc:
        job["error"] = str(exc)
    finally:
        for row, proc, log in active:
            try:
                stop_child(proc, row)
                row["status"] = "paused" if paused else "cancelled" if cancelled else "failed"
            except Exception as exc:
                row.update(status="unconfirmed", error=f"Could not confirm child shutdown: {exc}")
                job["error"] = row["error"]
            log.close()
        for row in job["runs"]:
            if row["status"] == "queued":
                row["status"] = "paused" if paused else "cancelled" if cancelled else "failed"
        job.update(status="failed" if job.get("error") or any(r["status"] == "failed" for r in job["runs"]) else "paused" if paused else "cancelled" if cancelled else "completed", heartbeat=time.time())
        write_json(manifest_path, job)


if __name__ == "__main__":
    run_job(Path(sys.argv[1]).resolve())
