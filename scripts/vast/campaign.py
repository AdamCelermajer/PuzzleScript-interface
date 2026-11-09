"""The 800-move campaign on a rented 4xRTX 5090: rent, serve, connect, check, run as a workbench batch, shut down.

    uv run python scripts/vast/campaign.py offers         # read-only
    uv run python scripts/vast/campaign.py rent OFFER --yes    # starts billing
    uv run python scripts/vast/campaign.py setup          # download the model, start the server
    uv run python scripts/vast/campaign.py tunnels        # localhost:18100 -> the server
    uv run python scripts/vast/campaign.py check          # the server answers, then a 3-move batch
    uv run python scripts/vast/campaign.py launch --yes   # the 6-run batch, and the watcher that tends it
    uv run python scripts/vast/campaign.py status         # health, recording and cost: read-only
    uv run python scripts/vast/campaign.py resume OUTPUT  # one stopped or hung run, by its output folder
    uv run python scripts/vast/campaign.py destroy --yes  # ends the rental and all billing

Runbook and choices: docs/research/vast-campaign-4x5090.md. VAST_API_KEY stays in .env and is never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "output" / "vast" / "instance.json"
LOGS = ROOT / "output" / "vast" / "logs"
SSH_KEY = Path.home() / ".ssh" / "vastai_ed25519"
API = "https://console.vast.ai/api/v0"
WORKBENCH = "http://127.0.0.1:8010/api/workbench"
GAME_API = "http://127.0.0.1:8000/api/games"
SERVER_LOG = "/workspace/logs/vllm.log"
IMAGE = "vastai/vllm:v0.31.0-cuda-13.0"
GPUS = 4
DISK_GB = 150
MODEL = "vast/q3.8-27b-fp8"
SERVED = "q3.8-27b-fp8"
EFFORT = "xhigh"  # the server applies it to every request; recorded here so the run says so
GAMES = ("ps_modality-v1", "ps_icecrates-v1", "ps_knightoban-v1")
MAX_STEPS = 800
TURN_TIMEOUT = 7200  # a slow server must not end a run, as 1800 s did on 4 Nov
LABEL = "vast-4x5090-800-xhigh"
LOCAL_PORT = 18100  # the harness's default for vast/ models
REMOTE_PORT = 18000
MIN_RELIABILITY = 0.97
ENDED = {"completed", "failed", "cancelled", "paused"}
HUNG_MINUTES = 20  # a long thinking call takes ~10 min on this server; a compaction less
MAX_RESUMES = 20  # for one game and driver
GRACE_MINUTES = 40  # after everything ended with a run unfinished and not resumable, before the rental ends
DETACHED = 0x00000008 | 0x00000200 | 0x01000000  # DETACHED_PROCESS, NEW_PROCESS_GROUP, BREAKAWAY_FROM_JOB


def batch_request(steps: int = MAX_STEPS, games: tuple[str, ...] = GAMES, label: str = LABEL) -> dict:
    """One workbench batch (POST /api/workbench/runs): every game with both drivers, all at once."""
    return {"frameworks": [{"id": "baseline", "options": {"max_steps": steps, "driver": "agent"}},
                           {"id": "baseline", "options": {"max_steps": steps, "driver": "controller", "turn_timeout": TURN_TIMEOUT}}],
            "harnesses": ["opencode"], "models": [MODEL], "efforts": [EFFORT], "games": list(games), "repeats": 1,
            "parallel": len(games) * 2, "max_wall_seconds": 0, "label": label}


def api_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("VAST_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("VAST_API_KEY is not in .env")


def request(method: str, path: str, body: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {api_key()}", "Accept": "application/json", "User-Agent": "workbench",
               "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    call = urllib.request.Request(f"{API}/{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(call, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"vast.ai {method} {path}: {exc.code} {exc.read()[:300].decode(errors='replace')}") from None


def post(path: str, body: dict | None = None) -> dict:
    call = urllib.request.Request(f"{WORKBENCH}/{path}", data=json.dumps(body or {}).encode(),
                                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(call, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"The workbench refused {path}: {exc.code} {exc.read()[:500].decode(errors='replace')}") from None


def start_batch(body: dict) -> Path:
    return ROOT / post("runs", body)["job_id"]


def load_state() -> dict:
    if not STATE.is_file():
        raise SystemExit(f"No rented instance recorded ({STATE}); run rent first")
    return json.loads(STATE.read_text(encoding="utf-8"))


def save_state(**fields) -> dict:
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else {}
    state.update(fields)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def instance(instance_id: int) -> dict:
    found = request("GET", f"instances/{instance_id}/").get("instances")
    if isinstance(found, list):
        found = found[0] if found else None
    return found or {}


def ssh_address(info: dict) -> tuple[str, int] | None:
    """The direct port when there is one: on 21 Oct the proxy refused connections after boot."""
    direct = ((info.get("ports") or {}).get("22/tcp") or [{}])[0].get("HostPort")
    if direct and info.get("public_ipaddr"):
        return str(info["public_ipaddr"]).strip(), int(direct)
    if info.get("ssh_host") and info.get("ssh_port"):
        return str(info["ssh_host"]), int(info["ssh_port"])
    return None


def ssh_options(port: int) -> list[str]:
    return ["-i", str(SSH_KEY), "-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=15", "-p", str(port)]


def job_state(directory: Path) -> dict:
    return json.loads((directory / "job.json").read_text(encoding="utf-8"))


def job_ended(job: dict) -> bool:
    return job.get("status") in ENDED


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def finished(result: dict, moves: int, max_steps: int = MAX_STEPS) -> bool:
    """Played to the end: the game is won or its moves are used up. Anything else can go on."""
    return bool(result) and result.get("status") != "error" and (bool(result.get("solved")) or moves >= max_steps)


def verdict(row: dict, minutes_idle: float | None) -> str:
    """done, running, hung or stopped (= ended early, resume it)."""
    if row["done"]:
        return "done"
    if row["status"] in {"queued", "starting", "running"}:
        return "hung" if minutes_idle is not None and minutes_idle >= HUNG_MINUTES else "running"
    return "stopped"


def run_rows(job: dict) -> list[dict]:
    rows = []
    for run in job.get("runs", []):
        folder = Path(run["output"])
        path = folder / "transitions.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        last = json.loads(lines[-1]) if lines else {}
        calls = sorted((folder / "calls").glob("[0-9][0-9][0-9][0-9].json")) if (folder / "calls").is_dir() else []
        frames = list((folder / "frames").glob("*.png")) if (folder / "frames").is_dir() else []
        times = [run.get("started_at") or 0, *(p.stat().st_mtime for p in [path, *calls[-3:]] if p.is_file())]
        idle = (time.time() - max(times)) / 60 if max(times) else None
        result = read_json(folder / "result.json")
        row = {"game": run["game_id"], "driver": run["options"]["driver"], "status": run["status"], "moves": len(lines),
               "levels": (last.get("after") or {}).get("levels_completed", 0), "result": bool(result),
               "done": finished(result, len(lines), run["options"]["max_steps"]), "calls": len(calls), "frames": len(frames),
               "served": read_json(folder / "session.json").get("served_model"), "idle": idle,
               "error": read_json(folder / "error.json").get("message") or result.get("error") or "",
               "output": str(folder), "id": run["id"], "job": str(Path(run["output"]).parent.relative_to(ROOT).as_posix()),
               "name": folder.name}
        row["verdict"] = verdict(row, idle)
        rows.append(row)
    return rows


def latest_rows(state: dict) -> tuple[list[dict], dict]:
    """The newest run of each game and driver across the batch and its resumes, and how often each was resumed."""
    latest, counts = {}, {}
    for job_id in state.get("jobs", []):
        for row in run_rows(job_state(ROOT / job_id)):
            key = (row["game"], row["driver"])
            counts[key] = counts.get(key, -1) + 1
            latest[key] = row
    return list(latest.values()), counts


def healthy() -> str:
    """Empty when the batch's services answer, else what is wrong."""
    try:
        preflight()
    except SystemExit as exc:
        return str(exc)
    return ""


def resume_run(row: dict, state: dict) -> str:
    """Stop the run if it is hung, then continue it: same board, files and move count, new conversation."""
    if row["status"] in {"queued", "starting", "running"}:
        post(f"experiments/stop-run?job={urllib.parse.quote(row['job'], safe='')}&run={row['name']}")
        deadline = time.time() + 90
        while time.time() < deadline:
            if next((r for r in run_rows(job_state(ROOT / row["job"])) if r["id"] == row["id"]), row)["status"] not in {"queued", "starting", "running"}:
                break
            time.sleep(5)
    folder = Path(row["output"])
    if not (folder / "result.json").is_file() and not (folder / "error.json").is_file():
        (folder / "error.json").write_text(json.dumps({"type": "Interrupted", "message": "Stopped by the campaign's watcher: "
                                                       f"{row['verdict']} after {row['moves']} moves"}, indent=2), encoding="utf-8")
    job_id = post("runs/resume", {"run_id": row["id"], "carry_moves": True})["job_id"]
    save_state(jobs=[*load_state().get("jobs", []), job_id])
    return job_id


def tend(state: dict, log=print) -> list[dict]:
    """One round of the watcher: resume what stopped or hung, while the services are there to serve it."""
    rows, counts = latest_rows(state)
    pending = [row for row in rows if row["verdict"] in {"hung", "stopped"}]
    if not pending:
        return rows
    problem = healthy()
    if problem:
        log(f"Not resuming {len(pending)} run(s) yet: {problem}")
        return rows
    for row in pending:
        key = (row["game"], row["driver"])
        if counts.get(key, 0) >= MAX_RESUMES:
            log(f"{key} was resumed {counts[key]} times; leaving it")
            continue
        try:
            log(f"Resuming {key} ({row['verdict']}, {row['moves']} moves, error: {row['error'][:200]}): {resume_run(row, state)}")
        except (OSError, SystemExit, KeyError, ValueError) as exc:
            log(f"Could not resume {key}: {exc}")
    return latest_rows(load_state())[0]


def campaign_over(rows: list[dict], counts: dict) -> bool:
    """Every run is done, or has used its resumes and has stopped."""
    return bool(rows) and all(r["verdict"] == "done" or (r["verdict"] == "stopped" and counts.get((r["game"], r["driver"]), 0) >= MAX_RESUMES)
                              for r in rows)


def preflight() -> None:
    """Everything a batch needs on this PC, before it can waste billed hours."""
    for name, url, expected in (("the workbench API", f"{WORKBENCH}/health", '"ok"'), ("the game service", GAME_API, "game_id"),
                                ("the model server", f"http://127.0.0.1:{LOCAL_PORT}/v1/models", SERVED)):
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                if expected in response.read().decode():
                    continue
        except OSError as exc:
            raise SystemExit(f"{name} does not answer at {url}: {exc}") from None
        raise SystemExit(f"{name} at {url} gave an unexpected answer")


# -- commands -------------------------------------------------------------------------------------
def offers(_: argparse.Namespace) -> None:
    query = {"verified": {"eq": True}, "rentable": {"eq": True}, "rented": {"eq": False}, "gpu_name": {"eq": "RTX 5090"},
             "num_gpus": {"eq": GPUS}, "disk_space": {"gte": DISK_GB}, "reliability2": {"gte": MIN_RELIABILITY},
             "cuda_max_good": {"gte": 13.0}, "order": [["dph_total", "asc"]], "limit": 10, "type": "on-demand"}
    found = request("GET", "bundles/?" + urllib.parse.urlencode({"q": json.dumps(query)})).get("offers", [])
    # Mainland China: Hugging Face is often unreachable, and the tunnel has to hold all night.
    found = [o for o in found if not str(o.get("geolocation") or "").endswith("CN")]
    if not found:
        raise SystemExit(f"No {GPUS}xRTX 5090 offer passes the filters right now")
    for o in found:
        print(f"#{o['id']}  ${o['dph_total']:.2f}/h  reliability {o.get('reliability2', 0):.3f}  "
              f"down {o.get('inet_down', 0):.0f} Mbps (${o.get('inet_down_cost') or 0:.4f}/GB)  "
              f"PCIe {o.get('pci_gen')}  max {o.get('duration', 0) / 86400:.0f} days  {o.get('geolocation')}")


def rent(args: argparse.Namespace) -> None:
    if not args.yes:
        raise SystemExit(f"This starts billing on offer {args.offer}. Add --yes to go.")
    if STATE.is_file() and not load_state().get("stopped"):
        raise SystemExit(f"{STATE} already holds a running instance; stop it first")
    if not SSH_KEY.is_file():
        raise SystemExit(f"Missing SSH key {SSH_KEY}")
    made = request("PUT", f"asks/{args.offer}/", {"client_id": "me", "image": IMAGE, "disk": DISK_GB, "runtype": "ssh_direc ssh_proxy",
                                                  "label": "qwen-800-campaign"})
    instance_id = made.get("new_contract")
    if not instance_id:
        raise SystemExit(f"Renting failed: {made}")
    STATE.unlink(missing_ok=True)
    save_state(id=instance_id, offer=args.offer, rented_at=datetime.now(timezone.utc).isoformat(), stopped=False)
    print(f"Rented instance {instance_id}; billing has started. Next: setup")


def wait_for_ssh(instance_id: int, minutes: int = 60) -> tuple[str, int]:
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        info = instance(instance_id)
        address = ssh_address(info)
        if info.get("actual_status") == "running" and address:
            host, port = address
            done = subprocess.run(["ssh", *ssh_options(port), f"root@{host}", "true"], capture_output=True)
            if done.returncode == 0:
                return host, port
        print(f"waiting for the machine: {info.get('actual_status')}", flush=True)
        time.sleep(15)
    raise SystemExit("The machine did not accept SSH in time; it is still billing. Check it, or run stop --yes")


def setup(_: argparse.Namespace) -> None:
    state = load_state()
    host, port = wait_for_ssh(state["id"])
    save_state(host=host, port=port)
    script = ROOT / "scripts" / "vast" / "setup_server.sh"
    subprocess.run(["ssh", *ssh_options(port), f"root@{host}", "mkdir -p /workspace"], check=True)
    subprocess.run(["scp", "-i", str(SSH_KEY), "-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes", "-P", str(port),
                    str(script), f"root@{host}:/workspace/setup_server.sh"], check=True)
    done = subprocess.run(["ssh", *ssh_options(port), f"root@{host}", "tr -d '\\r' < /workspace/setup_server.sh | bash -s"])
    if done.returncode != 0:
        raise SystemExit("Setup failed; the machine is still billing. Fix it, or run stop --yes")
    print("The server is up. Next: tunnels")


def tunnels(_: argparse.Namespace) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    log = (LOGS / "tunnel.log").open("a", encoding="utf-8")
    process = subprocess.Popen([sys.executable, __file__, "tunnel"], cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=DETACHED)
    save_state(tunnel=process.pid)
    for _attempt in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{LOCAL_PORT}/v1/models", timeout=5) as response:
                if SERVED in response.read().decode():
                    print(f"localhost:{LOCAL_PORT} ok")
                    return
        except OSError:
            time.sleep(2)
    raise SystemExit(f"localhost:{LOCAL_PORT} does not reach the server")


def tunnel(_: argparse.Namespace) -> None:
    """Runs detached: this PC's port to the server, reconnecting for as long as the rental lasts."""
    while not load_state().get("destroyed"):
        state = load_state()
        print(datetime.now().isoformat(timespec="seconds"), "connecting", flush=True)
        subprocess.run(["ssh", *ssh_options(state["port"]), "-N", "-L", f"127.0.0.1:{LOCAL_PORT}:127.0.0.1:{REMOTE_PORT}", "-o", "ExitOnForwardFailure=yes",
                        "-o", "ServerAliveCountMax=3", f"root@{state['host']}"], stdin=subprocess.DEVNULL)
        print(datetime.now().isoformat(timespec="seconds"), "disconnected", flush=True)
        time.sleep(5)


def reboot(args: argparse.Namespace) -> None:
    """For a machine whose container lost the GPUs (`Failed to initialize NVML`): restart it, then run setup."""
    if not args.yes:
        raise SystemExit("This restarts the container, and any run using the server loses it for some minutes. Add --yes to go.")
    state = load_state()
    print(request("PUT", f"instances/reboot/{state['id']}/"))
    time.sleep(30)
    print("back at", wait_for_ssh(state["id"]), "; next: setup")


def ask() -> dict:
    """One real call through the tunnel: a tool call with thinking, timed."""
    body = {"model": SERVED, "max_tokens": 600, "stream": False,
            "messages": [{"role": "user", "content": "Call the note tool with the text 'ready'."}],
            "tools": [{"type": "function", "function": {"name": "note", "description": "Write a note",
                       "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}}]}
    call = urllib.request.Request(f"http://127.0.0.1:{LOCAL_PORT}/v1/chat/completions", data=json.dumps(body).encode(),
                                  headers={"Content-Type": "application/json"})
    start = time.time()
    with urllib.request.urlopen(call, timeout=300) as response:
        answer = json.load(response)
    used = answer.get("usage") or {}
    message = answer["choices"][0]["message"]
    return {"seconds": round(time.time() - start, 1), "output_tokens": used.get("completion_tokens"),
            "tool_call": bool(message.get("tool_calls")), "thinking": bool(message.get("reasoning") or message.get("reasoning_content"))}


def check(_: argparse.Namespace) -> None:
    preflight()
    result = ask()
    print(f"localhost:{LOCAL_PORT}: {result}")
    if not result["tool_call"]:
        print("  warning: no structured tool call in 600 tokens (long thinking can use them all); the 3-move runs below decide")
    directory = start_batch(batch_request(steps=3, games=GAMES[:1], label="vast-check"))
    print(f"Check batch: {directory.relative_to(ROOT).as_posix()}", flush=True)
    deadline = time.time() + 25 * 60
    while not job_ended(job := job_state(directory)):
        if time.time() > deadline:
            raise SystemExit("The 3-move batch did not end in 25 minutes; do not launch yet")
        time.sleep(10)
    failed = job.get("status") != "completed"
    for row in run_rows(job):
        good = row["moves"] >= 1 and row["result"] and row["served"] == SERVED
        failed = failed or not good
        print(f"{row['driver']}: {row['moves']}/3 moves, served {row['served']} -> {'ok' if good else 'FAILED, see ' + row['output']}")
    if failed:
        raise SystemExit("The check batch failed; do not launch yet")
    print("Ready. Next: launch --yes")


def launch(args: argparse.Namespace) -> None:
    if not args.yes:
        raise SystemExit("This starts the 6 long runs. Add --yes to go.")
    state = load_state()
    if any(not job_ended(job_state(ROOT / job)) for job in state.get("jobs", [])):
        raise SystemExit("A batch of this campaign has not ended")
    preflight()
    directory = start_batch(batch_request())
    save_state(jobs=[directory.relative_to(ROOT).as_posix()], launched_at=datetime.now(timezone.utc).isoformat())
    print(f"Batch started, visible in the workbench: {directory.relative_to(ROOT).as_posix()}")
    LOGS.mkdir(parents=True, exist_ok=True)
    log = (LOGS / "watch.log").open("a", encoding="utf-8")
    subprocess.Popen([sys.executable, __file__, "watch", "--max-hours", str(args.max_hours)], cwd=ROOT, stdin=subprocess.DEVNULL,
                     stdout=log, stderr=log, creationflags=DETACHED)
    print(f"Watcher started: it resumes runs that stop or hang, and ends the rental when all are done, or after {args.max_hours} h "
          "(output/vast/logs/watch.log).")


def status(_: argparse.Namespace) -> None:
    state = load_state()
    info = instance(state["id"])
    hours = (datetime.now(timezone.utc) - datetime.fromisoformat(state["rented_at"])).total_seconds() / 3600
    rate = info.get("dph_total") or 0
    print(f"instance {state['id']}: {info.get('actual_status') or 'gone'}, ${rate:.2f}/h, rented {hours:.1f} h ago, about ${rate * hours:.2f} so far"
          + (" (destroyed)" if state.get("destroyed") else ""))
    print("services:", healthy() or "workbench, game service and model server answer")
    log = LOGS / "watch.log"
    if log.is_file():
        print(f"watcher: last line {(time.time() - log.stat().st_mtime) / 60:.0f} min ago, pid {state.get('watcher')}, "
              f"alive: {pid_alive(state.get('watcher'))}")
    if state.get("host") and not state.get("destroyed"):
        print("gpus:", remote(state, "nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader | tr '\\n' ';'"))
        print("server:", remote(state, f"grep 'throughput' {SERVER_LOG} | tail -n 1 | cut -c1-200"))
    rows, counts = latest_rows(state)
    for row in rows:
        idle = f"{row['idle']:.0f}" if row["idle"] is not None else "?"
        print(f"{row['game'][3:-3]:11} {row['driver']:10} {row['verdict']:8} moves {row['moves']:3} levels {row['levels']} calls {row['calls']:4} "
              f"frames {row['frames']:4} idle {idle} min, resumes {counts.get((row['game'], row['driver']), 0)}, {row['job'].split('/')[-1]}/{row['name']}"
              + (f" | {row['error'][:160]}" if row["error"] else ""))


def stop_machine(instance_id: int) -> str:
    request("PUT", f"instances/{instance_id}/", {"state": "stopped"})
    for _ in range(12):
        time.sleep(10)
        actual = instance(instance_id).get("actual_status")
        if actual != "running":
            save_state(stopped=True, stopped_at=datetime.now(timezone.utc).isoformat())
            return str(actual)
    return "running"


def stop(args: argparse.Namespace) -> None:
    if not args.yes:
        raise SystemExit("This stops the machine, and any run still using it fails. Add --yes to go.")
    print("instance is now:", stop_machine(load_state()["id"]))


def remote(state: dict, command: str) -> str:
    """Best effort: a slow or gone machine must not stop the caller."""
    try:
        done = subprocess.run(["ssh", *ssh_options(state["port"]), f"root@{state['host']}", command], capture_output=True, text=True, timeout=45)
        return done.stdout.strip() or done.stderr.strip()[:200]
    except (OSError, subprocess.SubprocessError) as exc:
        return f"unreachable: {exc}"


def pid_alive(pid) -> bool:
    if not pid:
        return False
    done = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
    return str(pid) in done.stdout


def on_account(instance_id: int) -> bool:
    call = urllib.request.Request("https://console.vast.ai/api/v1/instances/",
                                  headers={"Authorization": f"Bearer {api_key()}", "User-Agent": "workbench"})
    with urllib.request.urlopen(call, timeout=60) as response:
        return any(item.get("id") == instance_id for item in json.load(response).get("instances") or [])


def destroy_machine(state: dict, log=print) -> bool:
    """End the rental, with no storage left behind. Results are on this PC; the server's log is copied first.
    True once the account no longer lists the instance."""
    if state.get("host"):
        LOGS.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["scp", "-i", str(SSH_KEY), "-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                            "-P", str(state["port"]), f"root@{state['host']}:{SERVER_LOG}", str(LOGS / f"vllm-{state['id']}.log")],
                           capture_output=True, timeout=600)
        except (OSError, subprocess.SubprocessError) as exc:
            log(f"The server log was not copied: {exc}")
    request("DELETE", f"instances/{state['id']}/")
    for _ in range(18):
        time.sleep(10)
        if not on_account(state["id"]):
            save_state(stopped=True, destroyed=True, destroyed_at=datetime.now(timezone.utc).isoformat())
            subprocess.run(["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Process | ? CommandLine -match "
                            "'campaign.py\" tunnel|18100:127.0.0.1:18000' | % { Stop-Process -Id $_.ProcessId -Force }"], capture_output=True)
            return True
    return False


def destroy(args: argparse.Namespace) -> None:
    if not args.yes:
        raise SystemExit("This ends the rental for good, and any run still using it fails. Add --yes to go.")
    state = load_state()
    print("gone from the account, billing ended" if destroy_machine(state) else "STILL ON THE ACCOUNT: it may be billing")


def resume(args: argparse.Namespace) -> None:
    state = load_state()
    target = str(Path(args.output).resolve()).casefold()
    row = next((r for r in latest_rows(state)[0] if str(Path(r["output"]).resolve()).casefold() == target), None)
    if row is None:
        raise SystemExit(f"{args.output} is not the latest run of any game and driver in this campaign")
    print("resumed as batch", resume_run(row, state))


def watch(args: argparse.Namespace) -> None:
    save_state(watcher=os.getpid())
    deadline = time.time() + args.max_hours * 3600
    over_since = None
    say = lambda text: print(datetime.now().isoformat(timespec="seconds"), text, flush=True)
    while True:
        try:
            tend(load_state(), say)
            state = load_state()
            rows, counts = latest_rows(state)
            active = any(not job_ended(job_state(ROOT / job)) for job in state.get("jobs", []))
            say([(r["game"][3:-3], r["driver"], r["moves"], r["levels"], r["verdict"]) for r in rows])
            if not active and campaign_over(rows, counts):
                say("Every run has ended")
                break
            # Nothing runs and nothing could be resumed for a while (a service stayed down): stop paying.
            over_since = (over_since or time.time()) if not active else None
            if over_since and time.time() - over_since > GRACE_MINUTES * 60:
                say(f"Nothing has run for {GRACE_MINUTES} min; ending the rental with runs unfinished")
                break
        except Exception as exc:  # the watcher is what ends the billing: it must outlive any one bad round
            say(f"Round failed: {type(exc).__name__}: {exc}")
        if time.time() > deadline:
            say(f"The {args.max_hours} h limit passed; stopping the runs and ending the rental")
            for job in load_state().get("jobs", []):
                (ROOT / job / "stop.request").touch()
            break
        time.sleep(120)
    for attempt in range(10):
        try:
            if destroy_machine(load_state(), say):
                say("The rental has ended: the instance is gone from the account")
                return
            say("The instance is still listed")
        except (OSError, SystemExit) as exc:
            say(f"Destroy attempt {attempt + 1} failed: {exc}")
        time.sleep(60)
    say("COULD NOT END THE RENTAL: it is still billing")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("offers").set_defaults(func=offers)
    command = commands.add_parser("rent")
    command.add_argument("offer", type=int)
    command.add_argument("--yes", action="store_true")
    command.set_defaults(func=rent)
    commands.add_parser("setup").set_defaults(func=setup)
    commands.add_parser("tunnels").set_defaults(func=tunnels)
    commands.add_parser("tunnel").set_defaults(func=tunnel)
    command = commands.add_parser("reboot")
    command.add_argument("--yes", action="store_true")
    command.set_defaults(func=reboot)
    commands.add_parser("check").set_defaults(func=check)
    command = commands.add_parser("launch")
    command.add_argument("--yes", action="store_true")
    command.add_argument("--max-hours", type=float, default=14)
    command.set_defaults(func=launch)
    commands.add_parser("status").set_defaults(func=status)
    command = commands.add_parser("stop")
    command.add_argument("--yes", action="store_true")
    command.set_defaults(func=stop)
    command = commands.add_parser("destroy")
    command.add_argument("--yes", action="store_true")
    command.set_defaults(func=destroy)
    command = commands.add_parser("resume")
    command.add_argument("output")
    command.set_defaults(func=resume)
    command = commands.add_parser("watch")
    command.add_argument("--max-hours", type=float, default=14)
    command.set_defaults(func=watch)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
