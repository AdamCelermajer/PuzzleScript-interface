# Agent interface

The environment is unknown. Action IDs are opaque and have no implied meaning.
Use only the evidence returned by these commands.

```text
python avo_tool.py observe
python avo_tool.py history
python avo_tool.py candidates
python avo_tool.py evaluate CANDIDATE_ID
python avo_tool.py probe ACTION_ID --rationale "why this experiment"
python avo_tool.py status
python avo_tool.py finish "reason"
```

You may freely create notes, tools, and executable hypotheses under
`candidates/CANDIDATE_ID/`. A hypothesis is optional; exploratory probes are
allowed before you have enough evidence.

Each candidate directory contains `manifest.json` and an executable command.
The command reads a single JSON request from stdin with protocol
`avo-theory-predict-v1`, history, current observation, and action. It returns:

```json
{
  "protocol": "avo-theory-prediction-v1",
  "expected": {
    "payload": null,
    "status": "PLAYING",
    "progress": null,
    "available_actions": []
  },
  "confidence": 0.5,
  "rationale": "evidence supporting this prediction"
}
```

The framework owns real execution and evaluation. Do not edit `.avo_rpc/`.
