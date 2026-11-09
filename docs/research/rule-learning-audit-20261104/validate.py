"""Validate the partial audit without opening prior labels or the identity key.

Run from repository root with .venv/Scripts/python.exe <this file>.
Uses only the standard library; does not grade text.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
load = lambda name: json.loads((HERE / name).read_text(encoding="utf-8"))
inventory = load("inventory.json")
labels = load("independent-labels.json")
index = {(x["run"], x["cp"]): x for x in inventory}
seen = set()
quotes = 0
for cp in labels:
    key = (cp["run"], cp["cp"])
    assert key not in seen
    seen.add(key)
    entry = index[key]
    assert set(cp["labels"]) == set(entry["rules"])
    for value in cp["labels"].values():
        assert value["belief"] in {"correct", "partial", "wrong", "absent"}
        assert value["notebook"] in {"correct", "partial", "wrong", "absent"}
        assert value["source"] in {"notebook", "thinking", "both", "none"}
        if value["belief"] == "absent":
            assert value["source"] == "none" and value["rationale"]
        else:
            assert value["evidence"]
        for ev in value["evidence"]:
            text = (ROOT / ev["path"]).read_text(encoding="utf-8")
            assert text[ev["start"]:ev["end"]] == ev["quote"]
            assert len(ev["quote"].split()) <= 20
            assert text[:ev["start"]].count("\n") + 1 == ev["line"]
            quotes += 1
for entry in inventory:
    assert hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]
source_quotes = 0
for entry in load("source-review.json"):
    path = ROOT / entry["path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["source_sha256"]
    lines = path.read_text().splitlines()
    for ev in entry["evidence"]:
        assert lines[ev["line"] - 1] == ev["quote"]
        source_quotes += 1
provenance = load("provenance.json")
segments = {a for record in provenance for a in record["assignments"]}
expected = {str(Path(x["path"]).parent.relative_to("docs/research/rule-learning-20261028/grade")).replace("\\", "/") for x in inventory}
assert segments == expected
assert all(set(x["models"]) == {"claude-opus-5-5"} for x in provenance)
result = dict(checkpoints_inventoried=len(inventory), rule_slots=sum(len(x["rules"]) for x in inventory),
              checkpoints_graded=len(labels), labels_graded=sum(len(x["labels"]) for x in labels),
              exact_checkpoint_quotes=quotes, exact_source_quotes=source_quotes,
              provenance_segments=len(segments), complete=len(labels) == len(inventory),
              comparison_performed=False)
(HERE / "validation.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
