"""Pre-render game thumbnails (first frame of level 1) into output/thumbnails/.

Uses the same code path as GET /api/workbench/benchmarks/{game_id}/thumbnail.png, in process,
against the local ARC service (default http://localhost:8000; it must be running).

    uv run python -m scripts.build_thumbnails [--backend-url URL] [--force] [--workers 4]
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from workbench.benchmarks import THUMBNAILS, create_router
from workbench.catalog import ROOT, read_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-url", default=None, help="ARC service URL (default: BENCHMARK_PLAY_BACKEND_URL or :8000)")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--force", action="store_true", help="re-render existing thumbnails")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    games = read_json(args.root / "benchmark/games.json").get("games") or {}
    wanted = [g for g, e in games.items() if e.get("status") == "playable" and e.get("arc_catalog", True)]
    if args.force:
        for game_id in wanted:
            (args.root / THUMBNAILS / f"{game_id}.png").unlink(missing_ok=True)
    app = FastAPI()
    app.include_router(create_router(args.root, backend_url=args.backend_url, run_snapshot=lambda: {"runs": []}))
    client = TestClient(app)

    def render(game_id: str) -> tuple[str, int]:
        return game_id, client.get(f"/api/workbench/benchmarks/{game_id}/thumbnail.png").status_code

    with ThreadPoolExecutor(max(1, args.workers)) as pool:
        results = list(pool.map(render, wanted))
    failed = [g for g, status in results if status != 200]
    print(f"{len(wanted) - len(failed)}/{len(wanted)} thumbnails in {args.root / THUMBNAILS}")
    for game_id in failed:
        print(f"  no thumbnail: {game_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
