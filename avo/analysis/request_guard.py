"""Fail closed on unapproved context at the actual model transport boundary."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from avo.isolation import IsolationError, REPOSITORY


ALLOWED_TOOLS = {"exec_command", "write_stdin", "apply_patch", "view_image", "update_plan"}


class RequestGuard:
    def __init__(self, *, forbidden_roots: tuple[Path, ...], canaries: tuple[str, ...] = (),
                 allowed_tools: set[str] | None = None,
                 public_helper_root: Path | None = None) -> None:
        self.roots = tuple(str(path.resolve()).replace("\\", "/").casefold() for path in (REPOSITORY, *forbidden_roots))
        self.canaries = canaries
        self.requests_checked = 0
        self.tools_seen: set[str] = set()
        self.failure: str | None = None
        self.allowed_tools = ALLOWED_TOOLS if allowed_tools is None else set(allowed_tools)
        self.public_helper_root = str(public_helper_root.resolve()).replace("\\", "/").casefold() if public_helper_root else None

    def _tools(self, tools: list) -> None:
        if not isinstance(tools, list):
            raise IsolationError("Unrecognized tool inventory")
        for tool in tools:
            if not isinstance(tool, dict):
                raise IsolationError("Unrecognized tool definition")
            if tool.get("type") == "namespace":
                self._tools(tool.get("tools", []))
                continue
            name = tool.get("name") or tool.get("function", {}).get("name")
            # Native client-side discovery is unnamed in newer CLI requests.
            # It still requires explicit opt-in; discovered tools are checked below.
            if tool.get("type") == "tool_search" and tool.get("execution") == "client":
                name = "tool_search"
            if name not in self.allowed_tools:
                raise IsolationError(f"Unapproved model tool: {name or tool.get('type')}")
            self.tools_seen.add(name)

    def _strings(self, value: Any):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for item in value:
                yield from self._strings(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key not in {"encrypted_content", "data", "image_url"}:
                    yield from self._strings(item)

    def check(self, request: Any) -> None:
        if self.failure:
            raise IsolationError(self.failure)
        try:
            if not isinstance(request, dict) or not isinstance(request.get("input"), list):
                raise IsolationError("Unrecognized model request schema")
            self._tools(request.get("tools", []))
            context = list(request["input"])
            if request.get("instructions"):
                context.append({"content": request["instructions"]})
            for item in context:
                if not isinstance(item, dict):
                    raise IsolationError("Unrecognized model input item")
                if item.get("type") in {"additional_tools", "tool_search_output"}:
                    self._tools(item.get("tools", []))
                    continue
                # Never censor guesses, learned mechanics, or the assistant's
                # reasoning. Check externally supplied context and tool outputs.
                if item.get("role") == "assistant" or item.get("type") in {"reasoning", "function_call"}:
                    continue
                for text in self._strings(item):
                    normalized = text
                    while "\\\\" in normalized:
                        normalized = normalized.replace("\\\\", "\\")
                    normalized = normalized.replace("\\", "/").casefold()
                    # The native sandbox advertises its executable-only alias
                    # directory. Its parent remains private and unreadable.
                    if self.public_helper_root:
                        normalized = re.sub(re.escape(self.public_helper_root) + r'(?=[\s<>"\']|$)', '<public-sandbox-helper>', normalized)
                    if "# agents.md instructions for" in normalized:
                        raise IsolationError("Automatically injected AGENTS instructions")
                    if any(re.search(r'(?<![\w/.-])' + re.escape(root) + r'(?=[/\s<>"\']|$)', normalized) for root in self.roots):
                        raise IsolationError("Framework/private path reached model context")
                    if any(marker in text for marker in self.canaries):
                        raise IsolationError("Isolation canary reached model context")
            self.requests_checked += 1
        except IsolationError as exc:
            self.failure = str(exc)
            raise

    def report(self) -> dict:
        return {"requests_checked": self.requests_checked, "tools_seen": sorted(self.tools_seen), "failure": self.failure}
