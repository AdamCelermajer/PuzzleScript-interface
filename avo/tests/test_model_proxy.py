import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import requests

from avo.analysis.model_proxy import CodexRequestProxy


class UpstreamHandler(BaseHTTPRequestHandler):
    received_body = b""
    received_authorization = ""
    received_path = ""
    payload = b'data: {"type":"response.completed"}\n\n'

    def do_POST(self):
        type(self).received_path = self.path
        length = int(self.headers.get("Content-Length", "0"))
        type(self).received_body = self.rfile.read(length)
        type(self).received_authorization = self.headers.get("Authorization", "")
        payload = type(self).payload
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


class CodexRequestProxyTests(unittest.TestCase):
    def test_nanogpt_namespace_translation_restores_calls_and_keeps_both_requests(self):
        upstream = ThreadingHTTPServer(('127.0.0.1', 0), UpstreamHandler)
        worker = threading.Thread(target=upstream.serve_forever, daemon=True)
        worker.start()
        call = {'type': 'function_call', 'name': 'mcp__codex_notes__write_note', 'call_id': 'test', 'arguments': '{}'}
        event = {'type': 'response.output_item.added', 'item': call}
        raw = ('data: ' + json.dumps(event) + '\n\n').encode()
        try:
            with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'AVO_TRACE_DETAIL': 'full'}), patch.object(UpstreamHandler, 'payload', raw):
                proxy = CodexRequestProxy(folder, session_id='test', session_role='test', namespace_compat=True,
                    upstream_origin=f'http://127.0.0.1:{upstream.server_port}', base_path='/api/v1')
                proxy.start()
                request = {'model': 'm', 'tools': [{'type': 'namespace', 'name': 'mcp__codex_notes',
                    'tools': [{'type': 'function', 'name': 'write_note', 'parameters': {'type': 'object'}}]}],
                    'input': [{'type': 'function_call', 'name': 'write_note', 'namespace': 'mcp__codex_notes', 'arguments': '{}'}]}
                try:
                    response = requests.post(proxy.model_base_url+'/responses', json=request, timeout=10)
                finally:
                    proxy.stop()
                forwarded = json.loads(UpstreamHandler.received_body)
                self.assertEqual(forwarded['tools'][0]['name'], 'mcp__codex_notes__write_note')
                self.assertEqual(forwarded['tools'][0]['type'], 'function')
                self.assertNotIn('namespace', forwarded['input'][0])
                restored = json.loads(response.text.split('data: ', 1)[1])['item']
                self.assertEqual(restored['name'], 'write_note')
                self.assertEqual(restored['namespace'], 'mcp__codex_notes')
                capture, = Path(folder).glob('request-*.json')
                saved = json.loads(capture.read_text())
                self.assertEqual(saved['request'], forwarded)
                self.assertEqual(saved['codex_request'], request)
                body, = Path(folder).glob('response-*.body')
                self.assertEqual(body.read_bytes(), raw)
        finally:
            upstream.shutdown(); upstream.server_close(); worker.join(timeout=5)

    def test_full_capture_preserves_reasoning_stream_and_omits_auth(self):
        upstream = ThreadingHTTPServer(('127.0.0.1', 0), UpstreamHandler)
        worker = threading.Thread(target=upstream.serve_forever, daemon=True)
        worker.start()
        payload = b'data: {"type":"response.reasoning_text.delta","delta":"test rationale"}\n\ndata: {"type":"response.completed"}\n\n'
        try:
            with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'AVO_TRACE_DETAIL': 'full'}), patch.object(UpstreamHandler, 'payload', payload):
                proxy = CodexRequestProxy(folder, session_id='test', session_role='test',
                    upstream_origin=f'http://127.0.0.1:{upstream.server_port}', base_path='/api/v1')
                proxy.start()
                try:
                    response = requests.post(proxy.model_base_url+'/responses', json={'model': 'm', 'input': []},
                        headers={'Authorization': 'Bearer secret-token'}, timeout=10)
                finally:
                    proxy.stop()
                self.assertEqual(response.content, payload)
                saved, = Path(folder).glob('response-*.body')
                self.assertEqual(saved.read_bytes(), payload)
                metadata = json.loads(saved.with_suffix('.json').read_text())
                self.assertTrue(metadata['complete'])
                self.assertEqual(metadata['request_sequence'], 1)
                self.assertEqual(metadata['status'], 200)
                self.assertFalse(any('secret-token' in p.read_text() for p in Path(folder).iterdir()))
        finally:
            upstream.shutdown(); upstream.server_close(); worker.join(timeout=5)

    def test_capture_write_failure_is_nonfatal_without_an_explicit_audit_guard(self):
        with tempfile.TemporaryDirectory() as root:
            proxy = CodexRequestProxy(root, session_id="test", session_role="test")
            with patch.object(Path, "write_text", side_effect=OSError("log unavailable")):
                proxy._record_request("responses_http", b'{"input": [], "tools": []}')

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
                    payload = {'model': 'vendor/model', 'input': [], 'tools': [{'type': 'function', 'name': 'new_cli_tool'}]}
                    response = requests.post(proxy.model_base_url+'/responses', json=payload, timeout=10)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(UpstreamHandler.received_path, '/api/v1/responses')
                    self.assertEqual(json.loads(UpstreamHandler.received_body), payload)
                finally:
                    proxy.stop()
        finally:
            upstream.shutdown(); upstream.server_close(); worker.join(timeout=5)

    def test_provider_pin_is_merged_into_forwarded_and_recorded_requests(self):
        upstream = ThreadingHTTPServer(('127.0.0.1', 0), UpstreamHandler)
        worker = threading.Thread(target=upstream.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                pin = {'provider': {'order': ['deepinfra'], 'allow_fallbacks': False}}
                proxy = CodexRequestProxy(Path(folder), session_id='test', session_role='test', body_patch=pin,
                    upstream_origin=f'http://127.0.0.1:{upstream.server_port}', base_path='/api/v1')
                proxy.start()
                try:
                    requests.post(proxy.model_base_url+'/responses', json={'model': 'm', 'input': []}, timeout=10)
                    self.assertEqual(json.loads(UpstreamHandler.received_body), {'model': 'm', 'input': [], **pin})
                    recorded, = Path(folder).glob('request-*.json')
                    self.assertEqual(json.loads(recorded.read_text(encoding='utf-8'))['request']['provider'], pin['provider'])
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
