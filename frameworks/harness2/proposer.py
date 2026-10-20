"""Keep upstream caching/harvesting, but use our installed, privately configured CLI."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from harness2.core.proposer import Proposer
from harnesses.opencode import OpenCodeSession


@dataclass
class InstalledProposer(Proposer):
    pin_provider: str = ""

    def _opencode(self, cwd: Path, mission: str, system: str, wall: int) -> tuple[str, float, str]:
        (cwd / "MISSION.md").write_text(mission, encoding="utf-8")
        (cwd / "output").mkdir(exist_ok=True)
        base_environment = self.env()  # retains OPENROUTER_API_KEY / NANOGPT_API_KEY

        class ImproverSession(OpenCodeSession):
            def base_env(self):
                return dict(base_environment)

        analysis = (self.audit_dir / "sessions" / cwd.name) if self.audit_dir else cwd / "analysis"
        analysis.mkdir(parents=True, exist_ok=True)
        (analysis / "mission.md").write_text(mission, encoding="utf-8")  # the run page labels the stage from it
        with ImproverSession().start(cwd, system, self.spec.model, self.spec.effort,
                                     "optimizer", analysis, provider=self.pin_provider) as session:
            config_path = Path(session.env["OPENCODE_CONFIG"])
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["agent"] = {"build": {"steps": self.spec.steps}}
            config_path.write_text(json.dumps(config), encoding="utf-8")
            reply = session.turn("Read MISSION.md first. Do what it asks. Edit context/harness/ in place. "
                                 "Save your final response to output/answer.md and return it.", timeout=wall)
        answer = cwd / "output/answer.md"
        text = answer.read_text(encoding="utf-8") if answer.is_file() else reply.text
        return "" if reply.error else text, float(reply.usage.get("cost_usd", 0)), reply.error
