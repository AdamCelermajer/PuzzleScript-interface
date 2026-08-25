import json, sys
request = json.load(sys.stdin)
expected = request["current"]
expected["status"] = "WIN"
json.dump({
    "protocol": "avo-theory-prediction-v1",
    "expected": expected,
    "confidence": 0.25,
    "rationale": "competing terminal hypothesis"
}, sys.stdout)
