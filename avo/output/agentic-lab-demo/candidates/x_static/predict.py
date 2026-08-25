import json, sys
request = json.load(sys.stdin)
json.dump({
    "protocol": "avo-theory-prediction-v1",
    "expected": request["current"],
    "confidence": 0.55,
    "rationale": "minimal null model"
}, sys.stdout)
