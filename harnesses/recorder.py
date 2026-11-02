"""Call recorder: every model request and response, exactly as they crossed the wire.

One recorder per agent session, for every harness (``CliSession.start`` creates it). It is a local
HTTP proxy: the harness points its CLI's API base URL at it, and each call is forwarded unchanged to
the real endpoint and streamed back. Each call is saved in ``<analysis>/calls/``:

- ``NNNN.json``: the request body as sent, its non-secret headers, the reply reassembled into one
  message, the harness turn, the time;
- ``NNNN.response.txt``: the reply bytes as received;
- ``NNNN-image-K.png``: each image in the request, replaced in the saved copy by its file name.

Credentials (authorization, API-key, cookie headers) are never saved. ``view`` turns a saved request
of any of the three API dialects (Chat Completions, Anthropic Messages, OpenAI Responses) into one
shape for the workbench: system text, messages made of parts, tools, settings.
"""
from __future__ import annotations

import base64
import gzip
import json
import threading
import time
import urllib.error
import urllib.request
import zlib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

HOP_HEADERS = {"host", "content-length", "connection", "accept-encoding", "transfer-encoding", "keep-alive"}
SECRET_HEADERS = ("authorization", "api-key", "x-api-key", "cookie", "token", "secret")
IMAGE_NOTE = "[image saved as {}]"


def _decoded(body: bytes, encoding: str) -> bytes | None:
    """The request body without its content encoding; None when it cannot be decoded here."""
    encoding = encoding.strip().lower()
    if encoding in ("", "identity"):
        return body
    if encoding == "gzip":
        return gzip.decompress(body)
    if encoding == "deflate":
        return zlib.decompress(body)
    try:
        import zstandard
    except ImportError:
        return None
    return zstandard.ZstdDecompressor().decompressobj().decompress(body) if encoding == "zstd" else None


def _save_images(value: Any, save: Callable[[bytes, str], str]) -> Any:
    """The request with every inline image (data URL or base64 source) replaced by its file name."""
    if isinstance(value, str) and value.startswith("data:image/"):
        kind, _, data = value.partition(";base64,")
        return save(base64.b64decode(data), kind.removeprefix("data:image/"))
    if isinstance(value, list):
        return [_save_images(item, save) for item in value]
    if isinstance(value, dict):
        if value.get("type") == "base64" and isinstance(value.get("data"), str):  # Anthropic image source
            media = str(value.get("media_type") or "image/png")
            return {**value, "data": save(base64.b64decode(value["data"]), media.removeprefix("image/"))}
        return {key: _save_images(item, save) for key, item in value.items()}
    return value


def _events(text: str) -> list[dict]:
    if text.lstrip().startswith("{"):
        try:
            return [json.loads(text)]
        except ValueError:
            return []
    events = []
    for line in text.splitlines():
        if line.startswith("data:") and line[5:].strip() not in ("", "[DONE]"):
            try:
                events.append(json.loads(line[5:]))
            except ValueError:
                continue
    return [event for event in events if isinstance(event, dict)]


def assemble(raw: bytes) -> dict[str, Any]:
    """The reply as one message (reasoning, text, tool calls, finish reason, usage), in any dialect."""
    reply: dict[str, Any] = {"reasoning": "", "content": "", "tool_calls": [], "finish_reason": None}
    calls: dict[Any, dict] = {}

    def call(key: Any) -> dict:
        return calls.setdefault(key, {"id": "", "name": "", "arguments": ""})

    for event in _events(raw.decode("utf-8", errors="replace")):
        kind = str(event.get("type") or "")
        for key in ("model", "provider", "error"):
            if event.get(key) and isinstance(event[key], (str, dict)):
                reply[key] = event[key]
        if event.get("usage") and kind != "message_delta":  # Anthropic's delta adds to message_start's
            reply["usage"] = event["usage"]
        # Chat Completions (streamed chunks or one JSON body)
        for choice in event.get("choices") or []:
            part = choice.get("delta") or choice.get("message") or {}
            reply["finish_reason"] = choice.get("finish_reason") or reply["finish_reason"]
            reply["content"] += part.get("content") or ""
            reply["reasoning"] += part.get("reasoning") or part.get("reasoning_content") or ""
            for item in part.get("tool_calls") or []:
                entry, function = call(item.get("index", len(calls))), item.get("function") or {}
                entry["id"] = item.get("id") or entry["id"]
                entry["name"] += function.get("name") or ""
                entry["arguments"] += function.get("arguments") or ""
        # Anthropic Messages
        if kind == "message_start":
            message = event.get("message") or {}
            reply["model"] = message.get("model") or reply.get("model")
            reply["usage"] = message.get("usage") or reply.get("usage")
        elif kind == "content_block_start":
            block = event.get("content_block") or {}
            if block.get("type") in ("tool_use", "server_tool_use"):
                entry = call(event.get("index"))
                entry["id"], entry["name"] = block.get("id") or "", block.get("name") or ""
        elif kind == "content_block_delta":
            delta = event.get("delta") or {}
            reply["content"] += delta.get("text") or ""
            reply["reasoning"] += delta.get("thinking") or ""
            if delta.get("partial_json"):
                call(event.get("index"))["arguments"] += delta["partial_json"]
        elif kind == "message_delta":
            reply["finish_reason"] = (event.get("delta") or {}).get("stop_reason") or reply["finish_reason"]
            reply["usage"] = {**(reply.get("usage") or {}), **(event.get("usage") or {})}
        elif kind == "message" and event.get("content"):  # Anthropic, not streamed
            for block in event["content"]:
                reply["content"] += block.get("text") or ""
                reply["reasoning"] += block.get("thinking") or ""
                if block.get("type") == "tool_use":
                    calls[len(calls)] = {"id": block.get("id") or "", "name": block.get("name") or "",
                                         "arguments": json.dumps(block.get("input"))}
            reply["finish_reason"] = event.get("stop_reason")
        # OpenAI Responses
        elif kind == "response.output_text.delta":
            reply["content"] += event.get("delta") or ""
        elif kind in ("response.reasoning_summary_text.delta", "response.reasoning_text.delta"):
            reply["reasoning"] += event.get("delta") or ""
        elif kind == "response.output_item.added":
            item = event.get("item") or {}
            if item.get("type") in ("function_call", "custom_tool_call", "local_shell_call"):
                entry = call(item.get("id"))
                entry["id"], entry["name"] = item.get("call_id") or item.get("id") or "", item.get("name") or item["type"]
        elif kind in ("response.function_call_arguments.delta", "response.custom_tool_call_input.delta"):
            call(event.get("item_id"))["arguments"] += event.get("delta") or ""
        elif kind == "response.output_item.done":
            item = event.get("item") or {}
            if item.get("type") == "local_shell_call":
                call(item.get("id"))["arguments"] = json.dumps(item.get("action"))
        elif kind in ("response.completed", "response.incomplete", "response.failed"):
            response = event.get("response") or {}
            reply["model"] = response.get("model") or reply.get("model")
            reply["usage"] = response.get("usage") or reply.get("usage")
            reply["finish_reason"] = response.get("status")
            if response.get("error"):
                reply["error"] = response["error"]
    reply["tool_calls"] = list(calls.values())
    return reply


class CallRecorder:
    """``start()`` returns the base URL the CLI calls instead of the real API; set ``upstream`` before
    the first call. ``turn`` and ``session`` give the harness turn and session id of each call."""

    def __init__(self, directory: Path, *, turn: Callable[[], int], session: Callable[[], str] = lambda: "",
                 upstream: str = "") -> None:
        self.directory = Path(directory)
        self.upstream = upstream
        self.turn, self.session = turn, session
        self.count = 0
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None

    def start(self) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        # Continue numbering after calls an earlier session of this run already saved.
        self.count = max((int(p.name[:4]) for p in self.directory.glob("[0-9][0-9][0-9][0-9].json")), default=0)
        recorder = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"  # the reply ends when the connection closes

            def log_message(self, *args: Any) -> None:
                pass

            def do_GET(self) -> None:
                recorder._forward(self, None)

            def do_POST(self) -> None:
                recorder._forward(self, self.rfile.read(int(self.headers.get("Content-Length") or 0)))

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def _forward(self, handler: BaseHTTPRequestHandler, body: bytes | None) -> None:
        with self._lock:
            self.count += 1
            number = self.count
        started, clock = datetime.now(timezone.utc), time.monotonic()
        headers = {k: v for k, v in handler.headers.items() if k.lower() not in HOP_HEADERS}
        received = bytearray()
        status, error = 0, ""
        try:
            request = urllib.request.Request(self.upstream.rstrip("/") + handler.path, data=body, headers=headers,
                                             method=handler.command)
            try:
                response = urllib.request.urlopen(request, timeout=900)
            except urllib.error.HTTPError as exc:
                response = exc
            status = response.status if hasattr(response, "status") else response.code
            handler.send_response(status)
            for key, value in response.headers.items():
                if key.lower() not in HOP_HEADERS:
                    handler.send_header(key, value)
            handler.send_header("Connection", "close")
            handler.end_headers()
            while True:
                chunk = response.read1(65536) if hasattr(response, "read1") else response.read(65536)
                if not chunk:
                    break
                received += chunk
                handler.wfile.write(chunk)
                handler.wfile.flush()
        except Exception as exc:  # the CLI sees a failed call; the record says why
            error = f"{type(exc).__name__}: {exc}"
            if not status:
                try:
                    handler.send_error(502, error[:200])
                except OSError:
                    pass
        finally:
            self._save(number, handler, headers, body, bytes(received), status, error, started,
                       time.monotonic() - clock)

    def _save(self, number: int, handler: BaseHTTPRequestHandler, headers: dict[str, str], body: bytes | None,
              received: bytes, status: int, error: str, started: datetime, seconds: float) -> None:
        stem = f"{number:04d}"
        images: list[str] = []

        def save_image(data: bytes, kind: str) -> str:
            name = f"{stem}-image-{len(images) + 1}.{kind or 'png'}"
            (self.directory / name).write_bytes(data)
            images.append(name)
            return IMAGE_NOTE.format(name)

        sent: Any = None
        if body:
            plain = _decoded(body, headers.get("Content-Encoding") or headers.get("content-encoding") or "")
            if plain is None:  # kept as sent; the workbench decodes it
                (self.directory / f"{stem}.request.bin").write_bytes(body)
                sent = f"[encoded request body saved as {stem}.request.bin]"
            else:
                try:
                    sent = _save_images(json.loads(plain), save_image)
                except ValueError:
                    sent = plain.decode("utf-8", errors="replace")
        record = {"call": number, "turn": self.turn(), "session": self.session(),
                  "started": started.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "seconds": round(seconds, 2),
                  "method": handler.command, "url": self.upstream.rstrip("/") + handler.path, "status": status,
                  "error": error or None,
                  "headers": {k: v for k, v in headers.items() if not any(s in k.lower() for s in SECRET_HEADERS)},
                  "request": sent, "images": images, "response": assemble(received),
                  "response_raw": f"{stem}.response.txt"}
        (self.directory / f"{stem}.response.txt").write_bytes(received)
        (self.directory / f"{stem}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False),
                                                     encoding="utf-8")


# ---------------------------------------------------------------- one view of any dialect

def _text_of(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_text_of(item) for item in value)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("content") or json.dumps(value, ensure_ascii=False))
    return json.dumps(value, ensure_ascii=False)


def _image(value: Any) -> dict | None:
    text = value if isinstance(value, str) else ""
    if isinstance(value, dict):
        text = str((value.get("image_url") or {}).get("url") if isinstance(value.get("image_url"), dict)
                   else value.get("image_url") or (value.get("source") or {}).get("data") or "")
    if text.startswith("[image saved as ") and text.endswith("]"):
        return {"kind": "image", "file": text[len("[image saved as "):-1]}
    return None


def _parts(content: Any) -> list[dict]:
    """Message content of any dialect as parts: text, image, reasoning, tool_call, tool_result, other."""
    if content is None or content == "":
        return []
    if isinstance(content, str):
        return [{"kind": "text", "text": content}]
    if not isinstance(content, list):
        return [{"kind": "other", "data": content}]
    parts = []
    for block in content:
        if not isinstance(block, dict):
            parts.append({"kind": "text", "text": str(block)})
            continue
        kind = block.get("type")
        image = _image(block) if kind in ("image_url", "image", "input_image") else None
        if image:
            parts.append(image)
        elif kind in ("text", "input_text", "output_text"):
            parts.append({"kind": "text", "text": block.get("text") or ""})
        elif kind in ("thinking", "redacted_thinking"):
            parts.append({"kind": "reasoning", "text": block.get("thinking") or "[redacted thinking]"})
        elif kind == "tool_use":
            parts.append({"kind": "tool_call", "id": block.get("id"), "name": block.get("name"),
                          "arguments": json.dumps(block.get("input"), ensure_ascii=False, indent=1)})
        elif kind == "tool_result":
            inner = _parts(block.get("content"))
            parts.append({"kind": "tool_result", "id": block.get("tool_use_id"),
                          "text": "\n".join(p.get("text", "") for p in inner if p["kind"] == "text"),
                          "images": [p["file"] for p in inner if p["kind"] == "image"]})
        else:
            parts.append({"kind": "other", "data": block})
    return parts


def _chat_message(message: dict) -> dict:
    parts = []
    for key in ("reasoning", "reasoning_content"):
        if message.get(key):
            parts.append({"kind": "reasoning", "text": _text_of(message[key]), "field": key})
    if message.get("reasoning_details"):
        parts.append({"kind": "reasoning", "field": "reasoning_details",
                      "text": "\n".join(str(d.get("text") or d.get("summary") or "[encrypted]")
                                        for d in message["reasoning_details"] if isinstance(d, dict))})
    if message.get("role") == "tool":
        parts.append({"kind": "tool_result", "id": message.get("tool_call_id"), "text": _text_of(message.get("content")),
                      "images": []})
    else:
        parts += _parts(message.get("content"))
    for item in message.get("tool_calls") or []:
        function = item.get("function") or {}
        parts.append({"kind": "tool_call", "id": item.get("id"), "name": function.get("name"),
                      "arguments": function.get("arguments")})
    known = {"role", "content", "tool_calls", "tool_call_id", "reasoning", "reasoning_content", "reasoning_details"}
    extra = {k: v for k, v in message.items() if k not in known}
    if extra:
        parts.append({"kind": "other", "data": extra})
    return {"role": message.get("role"), "parts": parts}


def _responses_item(item: dict) -> dict:
    kind = item.get("type") or "message"
    if kind == "message":
        return {"role": item.get("role"), "parts": _parts(item.get("content"))}
    if kind == "reasoning":
        summary = "\n".join(str(s.get("text") or "") for s in item.get("summary") or [] if isinstance(s, dict))
        text = summary or ("[encrypted reasoning]" if item.get("encrypted_content") else "")
        return {"role": "assistant", "parts": [{"kind": "reasoning", "text": text}]}
    if kind in ("function_call", "custom_tool_call", "local_shell_call"):
        arguments = item.get("arguments") or item.get("input") or json.dumps(item.get("action"))
        return {"role": "assistant", "parts": [{"kind": "tool_call", "id": item.get("call_id"),
                                                "name": item.get("name") or kind, "arguments": arguments}]}
    if kind in ("function_call_output", "custom_tool_call_output", "local_shell_call_output"):
        output = item.get("output")
        return {"role": "tool", "parts": [{"kind": "tool_result", "id": item.get("call_id"), "text": _text_of(output),
                                           "images": []}]}
    return {"role": item.get("role") or kind, "parts": [{"kind": "other", "data": item}]}


def view(request: Any) -> dict:
    """A saved request of any dialect as {dialect, system, messages, tools, settings}."""
    if not isinstance(request, dict):
        return {"dialect": "unknown", "system": [], "messages": [], "tools": [], "settings": {"body": request}}
    tools = []
    for tool in request.get("tools") or []:
        name = (tool.get("function") or {}).get("name") or tool.get("name") or tool.get("type")
        tools.append({"name": name, "definition": tool})
    if "input" in request or "instructions" in request:
        items = request.get("input") or []
        items = [{"role": "user", "content": items}] if isinstance(items, str) else items
        system = [request["instructions"]] if request.get("instructions") else []
        messages = [_responses_item(item) for item in items if isinstance(item, dict)]
        dialect, skip = "openai-responses", {"input", "instructions", "tools"}
    elif "system" in request and "messages" in request or "anthropic_version" in request:
        system = [_text_of(request.get("system"))] if request.get("system") else []
        messages = [{"role": m.get("role"), "parts": _parts(m.get("content"))} for m in request.get("messages") or []]
        dialect, skip = "anthropic-messages", {"system", "messages", "tools"}
    else:
        chat = [m for m in request.get("messages") or [] if isinstance(m, dict)]
        system = [_text_of(m.get("content")) for m in chat if m.get("role") in ("system", "developer")]
        messages = [_chat_message(m) for m in chat if m.get("role") not in ("system", "developer")]
        dialect, skip = "chat-completions", {"messages", "tools"}
    return {"dialect": dialect, "system": system, "messages": messages, "tools": tools,
            "settings": {k: v for k, v in request.items() if k not in skip}}
