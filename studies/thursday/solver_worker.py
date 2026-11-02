"""Runs a model-written solver.py in its own process for solver_eval.

One JSON request per line on stdin, {"grid": [[...]], "levels": n}; one JSON reply per line on
stdout, {"action": "..."} or {"error": "..."}. The solver's own prints go to stderr so they
cannot corrupt the replies. Usage: python -I solver_worker.py PATH/TO/solver.py
"""
import importlib.util
import json
import sys
from pathlib import Path


def main() -> None:
    path = Path(sys.argv[1]).resolve()
    replies = sys.stdout
    sys.stdout = sys.stderr
    sys.path.insert(0, str(path.parent))
    module, failure = None, ""
    try:
        spec = importlib.util.spec_from_file_location("solver", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except BaseException as exc:  # the solver is untrusted model code; report, never crash
        failure = f"import failed: {type(exc).__name__}: {exc}"
    for line in sys.stdin:
        request = json.loads(line)
        if failure:
            reply = {"error": failure}
        else:
            try:
                reply = {"action": str(module.next_action(request["grid"], request["levels"]))}
            except BaseException as exc:
                reply = {"error": f"{type(exc).__name__}: {exc}"}
        replies.write(json.dumps(reply) + "\n")
        replies.flush()


if __name__ == "__main__":
    main()
