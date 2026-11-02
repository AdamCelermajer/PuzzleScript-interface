"""Record what a client (OpenCode) sends to the vast.ai vLLM: a logging pass-through proxy.

Listens on 127.0.0.1:<port> (Docker reaches it as host.docker.internal), forwards to --upstream,
streams replies back, and appends each request body to --out with message contents shortened.

    uv run python -m studies.thursday.capture_requests --port 18101 --upstream http://127.0.0.1:18100
    # then point the harness at it: VAST_LLM_BASE_URL=http://host.docker.internal:18101/v1
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def shorten(body: dict) -> dict:
    def clip(value):
        if isinstance(value, str):
            return value if len(value) <= 300 else value[:300] + f"... [{len(value)} chars]"
        if isinstance(value, list):
            return [clip(item) for item in value]
        if isinstance(value, dict):
            return {key: clip(item) for key, item in value.items()}
        return value
    return {**body, "messages": clip(body.get("messages")), "tools": [t.get("function", {}).get("name") for t in body.get("tools") or []]}


def handler(upstream: str, out: Path):
    class Proxy(BaseHTTPRequestHandler):
        def forward(self, method: str) -> None:
            data = self.rfile.read(int(self.headers.get("Content-Length") or 0)) if method == "POST" else None
            if data:
                try:
                    record = {"path": self.path, "body": shorten(json.loads(data))}
                except ValueError:
                    record = {"path": self.path, "raw_bytes": len(data)}
                with out.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            request = urllib.request.Request(upstream + self.path, data=data, method=method,
                                             headers={"Content-Type": self.headers.get("Content-Type", "application/json")})
            try:
                response = urllib.request.urlopen(request, timeout=3600)
            except urllib.error.HTTPError as error:
                response = error
            self.send_response(response.status)
            for key in ("Content-Type",):
                if response.headers.get(key):
                    self.send_header(key, response.headers[key])
            self.end_headers()
            while chunk := response.read1(65536) if hasattr(response, "read1") else response.read(65536):
                self.wfile.write(chunk)
                self.wfile.flush()

        def do_GET(self) -> None:
            self.forward("GET")

        def do_POST(self) -> None:
            self.forward("POST")

        def log_message(self, *args) -> None:
            pass
    return Proxy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18101)
    parser.add_argument("--upstream", default="http://127.0.0.1:18100")
    parser.add_argument("--out", default="output/thursday/vast/opencode-requests.jsonl")
    args = parser.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), handler(args.upstream.rstrip("/"), out)).serve_forever()


if __name__ == "__main__":
    main()
