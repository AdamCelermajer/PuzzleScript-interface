from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web
from avo.analysis.request_guard import RequestGuard
from avo.isolation import IsolationError


_HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class CodexRequestProxy:
    """Loopback proxy that records exact Codex Responses payloads."""

    def __init__(
        self,
        output_dir: str | Path,
        *,
        session_id: str,
        session_role: str,
        upstream_origin: str = "https://chatgpt.com",
        base_path: str = "/backend-api/codex",
        guard: RequestGuard | None = None,
        body_patch: dict[str, Any] | None = None,
        namespace_compat: bool | None = None,
    ) -> None:
        self.output_dir = Path(output_dir).resolve()
        self.session_id = session_id
        self.session_role = session_role
        self.upstream_origin = upstream_origin.rstrip("/")
        self.base_path = base_path.rstrip("/")
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._runner: web.AppRunner | None = None
        self._session: ClientSession | None = None
        self._error: BaseException | None = None
        self._port = 0
        self._sequence = 0
        self.guard = guard
        # Top-level fields merged into every Responses request (e.g. provider pinning).
        self.body_patch = dict(body_patch or {})
        self.capture_responses = os.environ.get("AVO_TRACE_DETAIL") == "full"
        self.namespace_compat = self.upstream_origin == "https://nano-gpt.com" if namespace_compat is None else namespace_compat

    @property
    def model_base_url(self) -> str:
        if not self._port:
            raise RuntimeError("The Codex request proxy has not started")
        return f"http://127.0.0.1:{self._port}{self.base_path}"

    def start(self) -> None:
        if self._thread is not None:
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(
            target=self._thread_main,
            name=f"avo-model-proxy-{self.session_id}",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=15):
            raise RuntimeError("Timed out while starting the Codex request proxy")
        if self._error is not None:
            raise RuntimeError("Could not start the Codex request proxy") from self._error

    def stop(self) -> None:
        if self._loop is None or self._thread is None:
            return
        future = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        try:
            future.result(timeout=15)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=15)
            self._thread = None

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._start_async())
        except BaseException as exc:
            self._error = exc
            self._ready.set()
            return
        self._ready.set()
        loop.run_forever()
        loop.close()

    async def _start_async(self) -> None:
        self._session = ClientSession(
            auto_decompress=False,
            timeout=ClientTimeout(total=None),
        )
        application = web.Application(client_max_size=256 * 1024**2)
        application.router.add_route("*", "/{path:.*}", self._handle)
        self._runner = web.AppRunner(application, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        sockets = site._server.sockets if site._server is not None else ()
        if not sockets:
            raise RuntimeError("The Codex request proxy did not bind a socket")
        self._port = int(sockets[0].getsockname()[1])

    async def _shutdown(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return await self._handle_websocket(request)
        return await self._handle_http(request)

    async def _handle_http(self, request: web.Request) -> web.StreamResponse:
        assert self._session is not None
        body = await request.read()
        original_body = body
        aliases: dict[str, tuple[str, str]] = {}
        if request.method == "POST" and request.path.endswith("/responses") and self.body_patch:
            try:
                parsed = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed = None
            if isinstance(parsed, dict):
                body = json.dumps({**parsed, **self.body_patch}).encode("utf-8")
        if request.method == "POST" and request.path.endswith("/responses") and self.namespace_compat:
            parsed = json.loads(body)
            parsed, aliases = self._flatten_namespaces(parsed)
            body = json.dumps(parsed).encode("utf-8")
        if request.method == "POST" and request.path.endswith("/responses"):
            try:
                self._record_request("responses_http", body, original_body=original_body if aliases else None)
            except (IsolationError, OSError):
                return web.json_response({"error": {"message": "AVO isolation validation failed", "type": "isolation_error"}}, status=400)
        request_sequence = self._sequence
        headers = self._forward_headers(request.headers)
        if aliases:
            headers["Accept-Encoding"] = "identity"
        upstream_url = self.upstream_origin + request.path_qs
        async with self._session.request(
            request.method,
            upstream_url,
            headers=headers,
            data=body or None,
            allow_redirects=False,
        ) as upstream:
            response_headers = self._response_headers(upstream.headers)
            if aliases:
                response_headers = {k: v for k, v in response_headers.items() if k.lower() != "content-encoding"}
            response = web.StreamResponse(
                status=upstream.status,
                reason=upstream.reason,
                headers=response_headers,
            )
            await response.prepare(request)
            capture = None
            capture_path = self.output_dir / f"response-{time.time_ns()}-{request_sequence:06d}.body"
            metadata = {"request_sequence": request_sequence, "status": upstream.status,
                        "content_type": upstream.headers.get("Content-Type", ""),
                        "content_encoding": upstream.headers.get("Content-Encoding", ""),
                        "complete": False}
            pending = b""
            is_sse = "text/event-stream" in upstream.headers.get("Content-Type", "")
            decoder = None
            if aliases and upstream.headers.get("Content-Encoding", "").lower() == "gzip":
                import zlib
                decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
            try:
                if self.capture_responses and request.path.endswith("/responses"):
                    try:
                        capture = capture_path.open("wb")
                    except OSError as exc:
                        metadata["capture_error"] = str(exc)
                async for chunk in upstream.content.iter_any():
                    if capture is not None:
                        try:
                            capture.write(chunk)
                            capture.flush()
                        except OSError as exc:
                            metadata["capture_error"] = str(exc)
                            capture.close()
                            capture = None
                    if aliases:
                        pending += decoder.decompress(chunk) if decoder else chunk
                        if is_sse:
                            pending = pending.replace(b"\r\n", b"\n")
                            while b"\n\n" in pending:
                                event, pending = pending.split(b"\n\n", 1)
                                await response.write(self._restore_namespace_event(event, aliases) + b"\n\n")
                    else:
                        await response.write(chunk)
                if aliases and pending:
                    if is_sse:
                        await response.write(self._restore_namespace_event(pending, aliases))
                    else:
                        payload = json.loads(pending)
                        self._restore_namespace_calls(payload, aliases)
                        await response.write(json.dumps(payload).encode("utf-8"))
                metadata["complete"] = True
            finally:
                if capture is not None:
                    capture.close()
                if self.capture_responses and request.path.endswith("/responses"):
                    try:
                        capture_path.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
                    except OSError:
                        pass
            await response.write_eof()
            return response

    async def _handle_websocket(self, request: web.Request) -> web.StreamResponse:
        assert self._session is not None
        upstream_url = "wss://" + self.upstream_origin.split("://", 1)[-1] + request.path_qs
        protocols = tuple(
            part.strip()
            for part in request.headers.get("Sec-WebSocket-Protocol", "").split(",")
            if part.strip()
        )
        upstream = await self._session.ws_connect(
            upstream_url,
            headers=self._websocket_headers(request.headers),
            protocols=protocols,
            autoping=True,
            heartbeat=30,
        )
        downstream = web.WebSocketResponse(
            protocols=([upstream.protocol] if upstream.protocol else ()),
            autoping=True,
            heartbeat=30,
        )
        await downstream.prepare(request)

        async def client_to_upstream() -> None:
            async for message in downstream:
                if message.type == WSMsgType.TEXT:
                    encoded = message.data.encode("utf-8")
                    try:
                        self._record_request("responses_websocket", encoded)
                    except (IsolationError, OSError):
                        await downstream.close(code=1008, message=b"AVO isolation validation failed")
                        break
                    await upstream.send_str(message.data)
                elif message.type == WSMsgType.BINARY:
                    try:
                        self._record_request("responses_websocket", message.data)
                    except (IsolationError, OSError):
                        await downstream.close(code=1008, message=b"AVO isolation validation failed")
                        break
                    await upstream.send_bytes(message.data)
                elif message.type == WSMsgType.ERROR:
                    break
            await upstream.close()

        async def upstream_to_client() -> None:
            async for message in upstream:
                if message.type == WSMsgType.TEXT:
                    self._record_response_message("text", message.data)
                    await downstream.send_str(message.data)
                elif message.type == WSMsgType.BINARY:
                    self._record_response_message("binary", base64.b64encode(message.data).decode("ascii"))
                    await downstream.send_bytes(message.data)
                elif message.type == WSMsgType.ERROR:
                    break
            await downstream.close()

        tasks = [
            asyncio.create_task(client_to_upstream()),
            asyncio.create_task(upstream_to_client()),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*done, *pending, return_exceptions=True)
        return downstream

    @staticmethod
    def _flatten_namespaces(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, tuple[str, str]]]:
        """Translate Codex namespace tools to standard function tools for NanoGPT."""
        aliases = {}
        tools = []
        for tool in payload.get("tools", []):
            if tool.get("type") != "namespace":
                tools.append(tool)
                continue
            namespace = tool["name"]
            for function in tool.get("tools", []):
                name = function["name"]
                alias = namespace + "__" + name
                aliases[alias] = (namespace, name)
                tools.append({**function, "name": alias})
        if aliases:
            payload["tools"] = tools
            for item in payload.get("input", []):
                if isinstance(item, dict) and item.get("type") == "function_call" and item.get("namespace"):
                    alias = item["namespace"] + "__" + item["name"]
                    if alias in aliases:
                        item["name"] = alias
                        item.pop("namespace")
        return payload, aliases

    @classmethod
    def _restore_namespace_calls(cls, value: Any, aliases: dict[str, tuple[str, str]]) -> None:
        if isinstance(value, list):
            for item in value:
                cls._restore_namespace_calls(item, aliases)
        elif isinstance(value, dict):
            if value.get("type") == "function_call" and value.get("name") in aliases:
                value["namespace"], value["name"] = aliases[value["name"]]
            for item in value.values():
                cls._restore_namespace_calls(item, aliases)

    @classmethod
    def _restore_namespace_event(cls, event: bytes, aliases: dict[str, tuple[str, str]]) -> bytes:
        lines = event.split(b"\n")
        for index, line in enumerate(lines):
            if line.startswith(b"data: ") and line[6:] != b"[DONE]":
                try:
                    value = json.loads(line[6:])
                except (ValueError, UnicodeError):
                    continue
                cls._restore_namespace_calls(value, aliases)
                lines[index] = b"data: " + json.dumps(value, ensure_ascii=False).encode("utf-8")
        return b"\n".join(lines)

    def _record_response_message(self, message_type: str, data: str) -> None:
        if not self.capture_responses:
            return
        try:
            with (self.output_dir / "responses-websocket.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"recorded_at_unix_ns": time.time_ns(),
                                         "request_sequence": self._sequence,
                                         "message_type": message_type, "data": data}) + "\n")
        except OSError:
            pass

    def _record_request(self, transport: str, body: bytes, *, original_body: bytes | None = None) -> None:
        try:
            text = body.decode("utf-8")
            parsed: Any = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            text = None
            parsed = None
        if transport == "responses_websocket" and isinstance(parsed, dict):
            if parsed.get("type") != "response.create":
                if self.guard is None:
                    return
                self.guard.failure = "Unrecognized model websocket message"
                raise IsolationError(self.guard.failure)
        failure = None
        if self.guard is not None:
            try:
                self.guard.check(parsed)
            except IsolationError as exc:
                failure = exc
        self._sequence += 1
        timestamp = time.time_ns()
        payload = {
            "schema_version": 1,
            "recorded_at_unix_ns": timestamp,
            "session_id": self.session_id,
            "session_role": self.session_role,
            "sequence": self._sequence,
            "transport": transport,
            "request": parsed,
            "raw_body_utf8": text,
            "raw_body_base64": base64.b64encode(body).decode("ascii"),
            "isolation": self.guard.report() if self.guard else None,
            "forwarding_allowed": failure is None,
        }
        if original_body is not None:
            payload["codex_request"] = json.loads(original_body)
        destination = self.output_dir / f"request-{timestamp}-{self._sequence:06d}.json"
        temporary = destination.with_suffix(".json.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(destination)
        except OSError as exc:
            if self.guard is not None:
                self.guard.failure = "Mandatory model request capture failed"
                raise IsolationError(self.guard.failure) from exc
            # Recording is diagnostic in normal runs; a log write must not
            # block the model request. Explicit isolation audits stay strict.
            return
        if failure is not None:
            raise failure

    @staticmethod
    def _forward_headers(headers: Any) -> dict[str, str]:
        return {
            key: value
            for key, value in headers.items()
            if key.lower() not in _HOP_BY_HOP_HEADERS
            and key.lower() != "content-encoding"
            and not key.lower().startswith("sec-websocket-")
        }

    @classmethod
    def _websocket_headers(cls, headers: Any) -> dict[str, str]:
        return cls._forward_headers(headers)

    @staticmethod
    def _response_headers(headers: Any) -> dict[str, str]:
        return {
            key: value
            for key, value in headers.items()
            if key.lower() not in _HOP_BY_HOP_HEADERS
        }
