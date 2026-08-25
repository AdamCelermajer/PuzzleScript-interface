from __future__ import annotations

import os

import uvicorn

from benchmark.app import app


def main() -> None:
    uvicorn.run(
        app,
        host=os.getenv("BENCHMARK_HOST", "127.0.0.1"),
        port=int(os.getenv("BENCHMARK_PORT", "9000")),
    )


if __name__ == "__main__":
    main()

