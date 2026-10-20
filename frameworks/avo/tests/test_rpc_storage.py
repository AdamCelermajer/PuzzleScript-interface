import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from frameworks.avo.core.tool_gateway import FileToolServer
from frameworks.avo.evolution.tool_server import EvolutionFileToolServer


@pytest.mark.parametrize("outer", [False, True])
def test_concurrent_calls_consume_requests_and_responses(tmp_path, outer):
    class Gateway:
        mission = "test"
        profile = SimpleNamespace(objective="test")
        store = SimpleNamespace(root=tmp_path / "results")

        def initialize(self):
            pass

        def handle(self, method, params):
            if method == "status":
                raise ValueError("expected failure")
            return {"method": method, "data": "x" * 100_000}

    gateway = Gateway()
    gateway.laboratory = SimpleNamespace(store=gateway.store)
    workspace = tmp_path / "workspace"
    server = (EvolutionFileToolServer if outer else FileToolServer)(gateway, workspace)
    server.start()
    script = workspace / ("avo_evolve_tool.py" if outer else "avo_tool.py")

    def call(method):
        return subprocess.run([sys.executable, str(script), method], cwd=workspace,
                              capture_output=True, text=True, timeout=15)

    try:
        # Archive repeatedly sends a large upload; outer requests return large responses.
        if not outer:
            (workspace / "data.txt").write_text("a" * 2_000_000)
        method = "population" if outer else "archive"
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(call, [method] * 8))
        for result in results:
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout)["method"] == method
        failure = call("status")
        assert failure.returncode != 0
        assert "expected failure" in failure.stderr
        assert list(server.rpc_root.iterdir()) == []
        assert server._thread.is_alive()
    finally:
        server.stop()
