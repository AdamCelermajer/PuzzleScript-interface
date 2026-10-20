"""In-container dispatcher: ``python -m harnesses.entry --spec /results/run_spec.json [--resume]``.

Prepares the harness credentials staged by ``harnesses.launch``, then runs the
framework named in the run spec (``frameworks/<id>/framework.py`` builds its command).
"""
from __future__ import annotations

import argparse
import json
import os
import runpy
import shutil
import sys
from pathlib import Path

from frameworks.registry import get_framework

RESULTS = Path("/results")
PARENT = Path("/parent")


def prepare_credentials(harness: str, credentials: Path = Path("/credentials"), home: Path | None = None) -> None:
    home = home or Path(os.environ.get("HOME", str(Path.home())))
    os.environ.setdefault("HARNESS_PRIVATE_ROOT", str(home / ".harness"))
    if harness == "codex":
        codex_home = home / ".codex"
        codex_home.mkdir(parents=True, exist_ok=True)
        source = credentials / "auth.json"
        if not source.is_file():
            raise SystemExit("codex harness: /credentials/auth.json was not staged")
        # Codex refreshes tokens in place, so it needs a writable copy.
        shutil.copyfile(source, codex_home / "auth.json")
        (codex_home / "auth.json").chmod(0o600)
        os.environ["CODEX_HOME"] = str(codex_home)
    if harness == "antigravity":
        from harnesses.antigravity import install_web_deny_hook
        install_web_deny_hook(home / ".gemini")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--spec", default=str(RESULTS / "run_spec.json"))
    parser.add_argument("--resume", action="store_true")
    options = parser.parse_args(argv)
    spec = json.loads(Path(options.spec).read_text(encoding="utf-8"))
    prepare_credentials(spec["harness"])
    framework = get_framework(spec["framework"])
    module_argv = framework.entry(spec, options.resume, RESULTS, PARENT)
    if framework.artifact:
        # The catalog reads DIR/<artifact>; it gets the spec too.
        artifact = RESULTS / framework.artifact
        artifact.mkdir(parents=True, exist_ok=True)
        (artifact / "run_spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    sys.argv = [module_argv[0], *module_argv[1:]]
    runpy.run_module(module_argv[0], run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
