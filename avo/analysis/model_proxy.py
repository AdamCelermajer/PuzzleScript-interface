from __future__ import annotations

import asyncio
import base64
import json
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
        if request.method == "POST" and request.path.endswith("/responses") and self.body_patch:
            try:
                parsed = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed = None
            if isinstance(parsed, dict):
                body = json.dumps({**parsed, **self.body_patch}).encode("utf-8")
        if request.method == "POST" and request.path.endswith("/responses"):
            try:
                self._record_request("responses_http", body)
            except (IsolationError, OSError):
                return web.json_response({"error": {"message": "AVO isolation validation failed", "type": "isolation_error"}}, status=400)
        headers = self._forward_headers(request.headers)
        upstream_url = self.upstream_origin + request.path_qs
        async with self._session.request(
            request.method,
            upstream_url,
            headers=headers,
            data=body or None,
            allow_redirects=False,
        ) as upstream:
            response = web.StreamResponse(
                status=upstream.status,
                reason=upstream.reason,
                headers=self._response_headers(upstream.headers),
            )
            await response.prepare(request)
            async for chunk in upstream.content.iter_any():
                await response.write(chunk)
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
                    await downstream.send_str(message.data)
                elif message.type == WSMsgType.BINARY:
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

    def _record_request(self, transport: str, body: bytes) -> None:
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
