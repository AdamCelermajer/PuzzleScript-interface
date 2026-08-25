import json, sys

req = json.load(sys.stdin)
obs = req.get("current_observation", req.get("observation", req.get("current")))
action = req["action"]["id"] if isinstance(req["action"], dict) else req["action"]
payload = obs.get("payload")
expected_payload = payload
confidence = 0.2
rationale = "Only ACTION2 has transition evidence; other opaque actions are left unchanged rather than guessed."

if action == "ACTION2" and payload and payload.get("frame"):
    frames = payload["frame"]
    grid = [row[:] for row in frames[-1]]
    player = next(((r,c) for r,row in enumerate(grid) for c,v in enumerate(row) if v == 2), None)
    if player:
        r,c = player
        nr,nc = r+1,c
        if nr < len(grid) and grid[nr][nc] in (0,3,5):
            grid[r][c] = 0
            grid[nr][nc] = 2
        expected_payload = {**payload, "frame": frames + [grid]}
        confidence = 0.93
        rationale = "The sole observed ACTION2 transition moved cell 2 exactly one row downward and appended the resulting grid to frame."

print(json.dumps({
  "protocol": "avo-theory-prediction-v1",
  "expected": {
    "payload": expected_payload,
    "status": obs["status"],
    "progress": obs.get("progress"),
    "available_actions": obs.get("available_actions", [])
  },
  "confidence": confidence,
  "rationale": rationale
}))

