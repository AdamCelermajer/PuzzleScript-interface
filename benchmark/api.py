from __future__ import annotations

from typing import Any

import requests


class BenchmarkApiClient:
    """Client for creating and executing one public benchmark run."""

    def __init__(
        self,
        benchmark_url: str,
        *,
        timeout: float = 45,
        session: requests.Session | None = None,
    ) -> None:
        self.benchmark_url = benchmark_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.run_id: str | None = None
        self.token: str | None = None

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["X-API-Key"] = self.token
        return headers

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self.session.request(
            method,
            f"{self.benchmark_url}{path}",
            json=payload,
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"Expected an object response from {path}")
        return data

    def create_run(
        self,
        *,
        capabilities: list[str],
        sample_size: int | None,
        seed: int,
        selected_games: list[str] | None = None,
        rendered_image: bool = False,
        legend: bool = False,
        action_semantics: bool = False,
    ) -> dict[str, Any]:
        run = self._request(
            "POST",
            "/api/benchmark/runs",
            {
                "capabilities": capabilities,
                "sample_size": sample_size,
                "seed": seed,
                "selected_games": selected_games,
                "representation": {
                    "rendered_image": rendered_image,
                    "legend": legend,
                    "action_semantics": action_semantics,
                },
            },
        )
        self.run_id = str(run["run_id"])
        self.token = str(run["run_token"])
        return run

    def attach(self, run_id: str, run_token: str) -> dict[str, Any]:
        self.run_id = run_id
        self.token = run_token
        try:
            return self._request(
                "GET", f"/api/benchmark/runs/{self.run_id}"
            )
        except Exception:
            self.run_id = None
            self.token = None
            raise

    def reset(self, game_alias: str) -> dict[str, Any]:
        self._require_run()
        return self._request(
            "POST",
            "/api/cmd/RESET",
            {
                "card_id": self.run_id,
                "game_id": game_alias,
            },
        )

    def step(
        self,
        game_alias: str,
        guid: str,
        action: str,
    ) -> dict[str, Any]:
        self._require_run()
        return self._request(
            "POST",
            f"/api/cmd/{action}",
            {
                "game_id": game_alias,
                "guid": guid,
            },
        )

    def submit_rule_challenge(
        self,
        challenge_id: str,
        predictions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self._require_run()
        return self._request(
            "POST",
            (
                f"/api/benchmark/runs/{self.run_id}/rule-challenges/"
                f"{challenge_id}"
            ),
            {"predictions": predictions},
        )

    def close(self) -> dict[str, Any]:
        self._require_run()
        return self._request(
            "POST", f"/api/benchmark/runs/{self.run_id}/close"
        )

    def _require_run(self) -> None:
        if not self.run_id or not self.token:
            raise RuntimeError("Create a benchmark run before using it")
