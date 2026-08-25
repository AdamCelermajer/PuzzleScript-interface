import copy, json, sys

req = json.load(sys.stdin)
obs = req["current_observation"]
action = req["action"]["id"] if isinstance(req["action"], dict) else req["action"]
frames = obs.get("payload", {}).get("frame", [])
board = copy.deepcopy(frames[-1]) if frames else []
after = copy.deepcopy(board)

# The sole real transition establishes ACTION1 as moving the unique 2 one row up
# when that destination is traversable. Other opaque actions remain conservatively
# predicted as no-ops rather than assigning meanings unsupported by evidence.
if action == "ACTION1":
    pos = next(((r, c) for r, row in enumerate(board) for c, v in enumerate(row) if v == 2), None)
    if pos:
        r, c = pos
        nr, nc = r - 1, c
        if 0 <= nr < len(board) and 0 <= nc < len(board[nr]) and board[nr][nc] in (0, 3):
            after[r][c] = 0
            after[nr][nc] = 2 if board[nr][nc] == 0 else 6

expected = {
    "payload": {"frame": [board, after]},
    "status": obs.get("status", "PLAYING"),
    "progress": obs.get("progress"),
    "available_actions": obs.get("available_actions", [])
}
print(json.dumps({
    "protocol": "avo-theory-prediction-v1",
    "expected": expected,
    "confidence": 0.98 if action == "ACTION1" else 0.2,
    "rationale": "ACTION1 up is directly observed; unobserved opaque actions are left as conservative no-ops."
}))
