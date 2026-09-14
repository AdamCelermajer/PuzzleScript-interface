"""Trusted AVO launch boundary. Never copy this module into agent workspaces."""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4


ISOLATION_VERSION = 1
REPOSITORY = Path(__file__).resolve().parents[1]


class IsolationError(RuntimeError):
    """Infrastructure failure, not a solver score or an experimental outcome."""


def runtime_root() -> Path:
    # The packaged Windows desktop app virtualizes LocalAppData, but its
    # elevated setup helper does not. Keep their setup state on the same real
    # path, outside both the package cache and the personal Codex home.
    root = (Path.home() / ".avo" / "isolated").resolve()
    if root == REPOSITORY or REPOSITORY in root.parents:
        raise IsolationError("AVO runtime root must be outside the repository")
    root.mkdir(parents=True, exist_ok=True)
    return root


def new_workspace() -> Path:
    # Retain agent-created files: synchronous removal of restricted-token files
    # caused Windows ACL hangs. Trusted archives remain separate from this root.
    return _new_private_directory("w-")


def _new_private_directory(prefix: str) -> Path:
    path = Path(tempfile.mkdtemp(prefix=prefix, dir=runtime_root())).resolve()
    if os.name == "nt":
        # OWNER RIGHTS alone does not preserve caller access to state files
        # subsequently created by the elevated helper (a different owner).
        # Grant only this user's SID, on this new directory; never Everyone.
        system = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32"
        try:
            identity = subprocess.run([str(system / "whoami.exe"), "/user", "/fo", "csv", "/nh"],
                                      capture_output=True, text=True, timeout=10, check=True)
            match = re.search(r"S-1-\d+(?:-\d+)+", identity.stdout)
            if not match:
                raise IsolationError("Cannot determine the dedicated runtime owner's Windows SID")
            subprocess.run([str(system / "icacls.exe"), str(path), "/grant:r",
                            f"*{match.group(0)}:(OI)(CI)F", "/q"],
                           capture_output=True, text=True, timeout=10, check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            raise IsolationError("Cannot establish private runtime owner access") from exc
    return path


def assert_workspace(workspace: Path) -> None:
    workspace = workspace.resolve()
    if workspace == REPOSITORY or REPOSITORY in workspace.parents:
        raise IsolationError("Model workspace is inside the repository")
    for path in workspace.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise IsolationError("Model workspace contains a link or junction")
        if path.name.lower() in {"agents.md", "agents.override.md", ".codex", ".agents"}:
            # Bubblewrap creates empty mount-point directories in the host
            # workspace. Empty directories contain no instructions/config.
            if path.name.lower() in {'.codex', '.agents'} and path.is_dir() and not any(path.iterdir()):
                continue
            raise IsolationError("Model workspace contains an instruction/config injection")


class IsolatedRuntime:
    def __init__(self, workspace: Path, artifacts: Path, codex_bin: str) -> None:
        self.workspace = workspace.resolve()
        self.artifacts = artifacts.resolve()
        self.codex_bin = str(Path(codex_bin).resolve())
        assert_workspace(self.workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.private = _new_private_directory("c-")
        self.python = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
        self.personal_codex = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self.env = self._environment()
        self._write_config()

    def _environment(self) -> dict[str, str]:
        # SDK merges env with os.environ. Clear inherited entries explicitly,
        # then supply only runtime plumbing; never inherit API keys/PYTHONPATH.
        env = {key: "" for key in os.environ}
        # The elevated helper uses Windows account identity when assigning ACLs
        # to its setup marker and credentials. Empty USERNAME/USERDOMAIN can
        # resolve the wrong SID and make setup state unreadable to this process.
        for key in ("SystemRoot", "SYSTEMROOT", "SystemDrive", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT",
                    "USERNAME", "USERDOMAIN", "USERDOMAIN_ROAMINGPROFILE", "USERPROFILE", "LOCALAPPDATA", "APPDATA"):
            if key in os.environ:
                env[key] = os.environ[key]
        system = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32"
        env.update({
            "CODEX_HOME": str(self.private),
            "PATH": os.pathsep.join((str(self.python.parent), str(system), str(system / "WindowsPowerShell/v1.0"))),
            "TEMP": str(self.workspace / ".tmp"),
            "TMP": str(self.workspace / ".tmp"),
            "TMPDIR": str(self.workspace / ".tmp"),
            "PYTHONNOUSERSITE": "1",
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        if os.name != "nt":
            env["PATH"] = os.pathsep.join((str(self.python.parent), "/usr/local/bin", "/usr/bin", "/bin"))
            env["HOME"] = str(self.private)
            env["LANG"] = "C.UTF-8"
        (self.workspace / ".tmp").mkdir(exist_ok=True)
        return env

    def _write_config(self) -> None:
        quote = json.dumps
        catalog_config = []
        if os.name != 'nt':
            catalog_result = subprocess.run([self.codex_bin, 'debug', 'models'],
                env=self.env, capture_output=True, text=True, timeout=20, check=True)
            catalog = json.loads(catalog_result.stdout)
            for model in catalog['models']:
                model['tool_mode'] = None
                model['multi_agent_version'] = None
                model['experimental_supported_tools'] = []
            catalog_path = self.private / 'models.json'
            catalog_path.write_text(json.dumps(catalog), encoding='utf8')
            catalog_config = [f'model_catalog_json = {quote(str(catalog_path))}']
        # Do NOT pass Sandbox.workspace_write at thread_start: that legacy
        # override supersedes default_permissions and restores broad read access.
        config = '\n'.join([
            'default_permissions = "avo"',
            'approval_policy = "never"',
            'project_doc_max_bytes = 0',
            'project_doc_fallback_filenames = []',
            'web_search = "disabled"',
            'cli_auth_credentials_store = "file"',
            *catalog_config,
            '[windows]',
            'sandbox = "elevated"',
            '[features]',
            'memories = false',
            'multi_agent = false',
            'browser_use = false',
            'computer_use = false',
            'js_repl = false',
            'code_mode = false',
            'code_mode_host = false',
            'skill_search = false',
            'skip_host_skill_discovery = true',
            'tool_suggest = false',
            'tool_search = false',
            'unavailable_dummy_tools = false',
            'default_mode_request_user_input = false',
            'apps = false',
            'connectors = false',
            'plugins = false',
            'recommended_plugins = false',
            'sleep_tool = false',
            'image_generation = false',
            '[tools.experimental_request_user_input]',
            'enabled = false',
            '[skills]',
            'include_instructions = false',
            '[skills.bundled]',
            'enabled = false',
            '[memories]',
            'use_memories = false',
            'generate_memories = false',
            '[permissions.avo.filesystem]',
            '":root" = "deny"',
            '":minimal" = "read"',
            f'{quote(str(self.python.parent))} = "read"',
            # Linux app-server invokes its public helper through an absolute
            # alias under CODEX_HOME. Expose only that helper directory, never
            # the private config/auth parent.
            *([f'{quote(str(self.private / "tmp" / "arg0"))} = "read"'] if os.name != "nt" else []),
            '[permissions.avo.filesystem.":workspace_roots"]',
            '"." = "write"',
            '[permissions.avo.network]',
            'enabled = false',
            '[shell_environment_policy]',
            'inherit = "none"',
            '[shell_environment_policy.set]',
            *[f'{quote(k)} = {quote(v)}' for k, v in self.env.items() if v and k != "CODEX_HOME"],
        ]) + '\n'
        (self.private / "config.toml").write_text(config, encoding="utf-8")

    def authenticate(self) -> None:
        # Only the credential file, never personal config, instructions, plugins,
        # histories or memory. The command sandbox must deny this private root.
        source = self.personal_codex / "auth.json"
        if not source.is_file():
            raise IsolationError("Existing file-based Codex login unavailable; isolated login setup is required")
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not payload.get("tokens"):
            raise IsolationError("A ChatGPT OAuth login is required; API keys are not reused")
        target = self.private / "auth.json"
        shutil.copyfile(source, target)
        target.chmod(0o600)

    def authenticate_openrouter(self) -> None:
        key_file = os.environ.get("AVO_OPENROUTER_KEY_FILE", "")
        key = (Path(key_file).read_text(encoding="utf-8").strip() if key_file
               else os.environ.get("OPENROUTER_API_KEY", "").strip())
        if not key:
            raise IsolationError("OpenRouter requires OPENROUTER_API_KEY or AVO_OPENROUTER_KEY_FILE")
        # _write_config already fixed the shell's explicit allowlist. The key
        # belongs only to the trusted Codex process, never shell tools or TOML.
        self.env["OPENROUTER_API_KEY"] = key

    def command(self, *args: str) -> list[str]:
        return [self.codex_bin, "sandbox", "--permission-profile", "avo", "--cd", str(self.workspace), "--", *args]

    def preflight(self) -> dict:
        """Exercise the real sandbox without a model or game interaction."""
        marker = self.private / "private-canary.txt"
        marker.write_text(uuid4().hex, encoding="utf-8")
        probe = self.workspace / "_isolation_probe.py"
        output = self.workspace / "_isolation_probe.json"
        forbidden = [marker, REPOSITORY / "AGENTS.md", self.personal_codex / "config.toml"]
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        probe.write_text(
            'import json, pathlib, socket\n'
            f'targets = {list(map(str, forbidden))!r}\n'
            'readable = []\n'
            'for name in targets:\n'
            '    try:\n'
            '        with open(name, "rb") as f: f.read(1)\n'
            '        readable.append(True)\n'
            '    except (PermissionError, FileNotFoundError, OSError): readable.append(False)\n'
            'network = False\n'
            'try:\n'
            f'    s = socket.create_connection(("127.0.0.1", {listener.getsockname()[1]}), timeout=1)\n'
            '    network = True; s.close()\n'
            'except OSError: pass\n'
            'pathlib.Path("_isolation_probe.json").write_text(json.dumps({"python": True, "write": True, "readable": readable, "network": network}))\n',
            encoding="utf-8",
        )
        try:
            result = subprocess.run(self.command(str(self.python), str(probe)), cwd=self.workspace,
                                    env=self.env, capture_output=True, text=True, timeout=45)
            report = json.loads(output.read_text()) if output.exists() else {}
            report.update(return_code=result.returncode, isolation_version=ISOLATION_VERSION)
            report["read_targets"] = ["private_canary", "repository_instructions", "personal_codex_config"]
            passed = result.returncode == 0 and report.get("python") and report.get("write") and report.get("readable") == [False] * len(forbidden) and report.get("network") is False
            report["passed"] = bool(passed)
            # Diagnostics are trusted artifacts, never model-facing tool errors.
            report["stderr"] = result.stderr[-4000:]
            (self.artifacts / "isolation_preflight.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            if not passed:
                raise IsolationError("Native sandbox isolation preflight failed; no model/game run is permitted")
            return report
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            report = {"passed": False, "isolation_version": ISOLATION_VERSION,
                      "error": f"{type(exc).__name__}: {exc}"}
            (self.artifacts / "isolation_preflight.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            raise IsolationError("Native sandbox preflight could not complete") from exc
        finally:
            listener.close()
            for path in (probe, output, marker):
                path.unlink(missing_ok=True)

    def close(self) -> None:
        # Exact private credential target, not recursive cleanup of restricted
        # agent workspaces. Preserve non-secret config for reproducibility.
        (self.private / "auth.json").unlink(missing_ok=True)
        self.env.pop("OPENROUTER_API_KEY", None)
