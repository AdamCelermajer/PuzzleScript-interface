import os
from typing import Any

from fastapi import HTTPException
import requests


REQUEST_TIMEOUT = 30


class PuzzleScriptClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (
            base_url or os.getenv("PUZZLESCRIPT_SERVER_URL", "http://localhost:3000")
        ).rstrip("/")

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            if method.upper() == "GET":
                response = requests.request(
                    method, url, params=payload, timeout=REQUEST_TIMEOUT
                )
            else:
                response = requests.request(
                    method, url, json=payload, timeout=REQUEST_TIMEOUT
                )
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail=f"PuzzleScript backend request failed: {exc}",
            ) from exc

        if response.status_code >= 400:
            detail = response.text
            try:
                data = response.json()
                if isinstance(data, dict) and "error" in data:
                    detail = str(data["error"])
            except ValueError:
                pass
            raise HTTPException(status_code=response.status_code, detail=detail)

        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("PuzzleScript server returned a non-object response")
        return data

    def start_game(self, source_name: str) -> dict[str, Any]:
        return self._request("POST", "/init", {"gameName": source_name})

    def reset_session(self, session_id: str) -> dict[str, Any]:
        return self._request(
            "POST", "/action", {"sessionId": session_id, "action": "RESET"}
        )

    def apply_action(self, session_id: str, action_name: str) -> dict[str, Any]:
        return self._request(
            "POST", "/action", {"sessionId": session_id, "action": action_name}
        )

    def observe(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", "/observe", {"sessionId": session_id})
