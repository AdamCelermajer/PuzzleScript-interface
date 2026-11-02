"""Offline integration check: no agent or model calls. Runs on host or in Docker."""
import json
import sys
from urllib.request import Request, urlopen


def check(base_url: str) -> None:
    def request(path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = Request(base_url.rstrip("/") + path, data=data,
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=30) as response:
            return json.load(response)

    games = request("/api/games")
    game_id = "ps_sokoban_basic-v1"
    assert any(game["game_id"] == game_id for game in games), "Missing smoke-test game"
    card_id = request("/api/scorecard/open", {"tags": ["backend-smoke-test"]})["card_id"]
    try:
        initial = request("/api/cmd/RESET", {"game_id": game_id, "card_id": card_id})
        assert initial["frame"] and initial["guid"], "Reset did not return a game frame"
        session = {"game_id": game_id, "guid": initial["guid"]}
        snapshot = request("/api/state/save", session)
        moved = request("/api/cmd/ACTION1", session)
        assert moved["guid"] == initial["guid"] and moved["frame"]
        restored = request("/api/state/restore", {**session, **snapshot})
        assert restored["frame"] == initial["frame"], "Snapshot did not restore initial frame"
    finally:
        request("/api/scorecard/close", {"card_id": card_id})
    print(f"PASS {base_url}: {len(games)} games; reset, action, snapshot, restore, close")


if __name__ == "__main__":
    check(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000")
