import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

from avo.analysis.model_proxy import CodexRequestProxy


class UpstreamHandler(BaseHTTPRequestHandler):
    received_body = b""
    received_authorization = ""
    received_path = ""

    def do_POST(self):
        type(self).received_path = self.path
        length = int(self.headers.get("Content-Length", "0"))
        type(self).received_body = self.rfile.read(length)
        type(self).received_authorization = self.headers.get("Authorization", "")
        payload = b'data: {"type":"response.completed"}\n\n'
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


class CodexRequestProxyTests(unittest.TestCase):
    def test_openrouter_path_is_forwarded_without_rewriting_payload(self):
        upstream = ThreadingHTTPServer(('127.0.0.1', 0), UpstreamHandler)
        worker = threading.Thread(target=upstream.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                proxy = CodexRequestProxy(Path(folder), session_id='test', session_role='test',
                    upstream_origin=f'http://127.0.0.1:{upstream.server_port}', base_path='/api/v1')
                proxy.start()
                try:
                    payload = {'model': 'vendor/model', 'input': [], 'tools': []}
                    response = requests.post(proxy.model_base_url+'/responses', json=payload, timeout=10)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(UpstreamHandler.received_path, '/api/v1/responses')
                    self.assertEqual(json.loads(UpstreamHandler.received_body), payload)
                finally:
                    proxy.stop()
        finally:
            upstream.shutdown(); upstream.server_close(); worker.join(timeout=5)

    def test_records_request_body_and_streams_through_without_logging_auth(self):
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        upstream_thread.start()
        try:
            with tempfile.TemporaryDirectory() as root:
                proxy = CodexRequestProxy(
                    Path(root) / "model_requests",
                    session_id="session-1",
                    session_role="inner_player",
                    upstream_origin=f"http://127.0.0.1:{upstream.server_port}",
                )
                proxy.start()
                try:
                    request = {"model": "test", "input": [{"role": "user"}]}
                    response = requests.post(
                        proxy.model_base_url + "/responses",
                        json=request,
                        headers={"Authorization": "Bearer secret-token"},
                        timeout=10,
                    )
                finally:
                    proxy.stop()

                self.assertEqual(response.status_code, 200)
                self.assertIn("response.completed", response.text)
                self.assertEqual(json.loads(UpstreamHandler.received_body), request)
                self.assertEqual(
                    UpstreamHandler.received_authorization,
                    "Bearer secret-token",
                )
                captures = list((Path(root) / "model_requests").glob("request-*.json"))
                self.assertEqual(len(captures), 1)
                capture = json.loads(captures[0].read_text())
                self.assertEqual(capture["request"], request)
                self.assertEqual(capture["transport"], "responses_http")
                self.assertNotIn("secret-token", captures[0].read_text())
        finally:
            upstream.shutdown()
            upstream.server_close()
            upstream_thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
