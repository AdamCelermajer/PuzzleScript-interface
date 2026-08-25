from __future__ import annotations

import tempfile
from pathlib import Path

from avo.core.run_store import RunStore


def test_archive_agent_workspace_preserves_research_and_excludes_rpc() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        workspace = root / "agent"
        workspace.mkdir()
        (workspace / "notes.md").write_text("finding", encoding="utf-8")
        (workspace / "drafts").mkdir()
        (workspace / "drafts" / "experiment.py").write_text("pass", encoding="utf-8")
        (workspace / ".avo_rpc").mkdir()
        (workspace / ".avo_rpc" / "request.json").write_text("{}", encoding="utf-8")

        store = RunStore.create(root / "run")
        report = store.archive_agent_workspace(workspace)

        assert (store.root / "workspace" / "notes.md").read_text() == "finding"
        assert (store.root / "workspace" / "drafts" / "experiment.py").is_file()
        assert not (store.root / "workspace" / ".avo_rpc").exists()
        assert "notes.md" in report["copied"]
        assert ".avo_rpc/request.json" in report["skipped"]
