"""Render the OpenCode c1..c8 surface into a baseline workspace seed."""
from pathlib import Path
import shutil

from harness2.substrate.opencode import OPENCODE_SURFACE


def render_workspace(staged: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    body = "\n\n".join((staged / name).read_text(encoding="utf-8").strip()
                         for name in OPENCODE_SURFACE.always_on if (staged / name).is_file()).strip()
    if body:
        (destination / "AGENTS.md").write_text(body + "\n", encoding="utf-8")
    for source in sorted((staged / "skills").glob("*/SKILL.md")):
        shutil.copytree(source.parent, destination / ".opencode/skills" / source.parent.name)
    for source in sorted((staged / "sub_agents").glob("*/AGENT.md")):
        target = destination / ".opencode/agents" / f"{source.parent.name}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for pattern, folder in (("scripts/*.py", "scripts"), ("plugin/*.ts", ".opencode/plugins")):
        for source in sorted(staged.glob(pattern)):
            target = destination / folder / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    return destination
