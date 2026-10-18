"""Mock loopback llama-server tests; no weights or real inference."""

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from inference import InferenceError, SAFETY_NOTICE, SYSTEM_INSTRUCTION

connect = sqlite3.connect
with patch('sqlite3.connect', side_effect=lambda *a, **kw: connect(':memory:')):
    from offline_ai.llama_adapter import LlamaCPUProvider, app


class LlamaTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(self.temp) / 'fixture.gguf'
        self.path.touch()  # Path fixture only, not model weights.
        self.calls = []
        self.status = 200
        self.body = {'choices': [{'message': {'content': ' TEST ONLY: blue squares. '}}]}
        self.health = {'status': 'ok'}
        self.hold = False
        self.entered = threading.Event()
        self.release = threading.Event()
        test = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                test.calls.append((self.path, None))
                self.reply(test.health)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                test.calls.append((self.path, body))
                test.entered.set()
                if test.hold:
                    test.release.wait(3)
                self.reply(test.body)

            def reply(self, body):
                self.send_response(test.status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Location', 'https://example.invalid/never-follow')
                self.end_headers()
                try:
                    self.wfile.write(json.dumps(body).encode())
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.cleanup_server)
        self.provider = LlamaCPUProvider(self.path, port=self.server.server_port, timeout=1)
        self.enterContext(patch('chat.provider', self.provider))
        self.client = self.enterContext(TestClient(app))
        # Forbid every connection except this mock's numeric loopback address.
        native = socket.socket.connect

        def guarded(sock, address):
            if address != ('127.0.0.1', self.server.server_port):
                raise AssertionError(f'Unexpected network destination: {address}')
            return native(sock, address)

        self.enterContext(patch('socket.socket.connect', guarded))

    def cleanup_server(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def ask(self):
        return self.client.post('/api/ask', json={'question': 'Fictional shapes only'})

    def test_real_routes_contract_and_offline_proxy_bypass(self):
        self.assertTrue(self.provider.configured)
        self.assertFalse(self.provider.ready)
        self.assertEqual(self.calls, [])
        with patch.dict('os.environ', {'HTTP_PROXY': 'http://example.invalid:9',
                                       'ALL_PROXY': 'http://example.invalid:9'}):
            response = self.ask()
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['answer'], 'TEST ONLY: blue squares.')
        self.assertEqual(data['notice'], SAFETY_NOTICE)
        self.assertEqual(data['sources'], [])
        self.assertEqual(data['mode'], 'local')
        self.assertIs(data['simulated'], False)
        self.assertTrue(self.provider.ready)
        path, payload = self.calls[1]
        self.assertEqual(path, '/v1/chat/completions')
        self.assertEqual(payload, {
            'model': 'lifeline-qwen', 'temperature': 0, 'max_tokens': 160, 'stream': False,
            'messages': [{'role': 'system', 'content': SYSTEM_INSTRUCTION},
                         {'role': 'user', 'content': 'Fictional shapes only'}],
        })
        self.assertTrue(self.client.get('/api/status').json()['data']['local']['ready'])

    def test_missing_model_no_network(self):
        self.path.unlink()
        response = self.ask()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'local_model_missing')
        self.assertEqual(self.calls, [])

    def test_missing_server(self):
        self.server.shutdown()
        self.server.server_close()
        response = self.ask()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'local_server_unavailable')

    def test_http_errors_and_redirects_are_not_followed(self):
        for status in (503, 500, 404, 302):
            with self.subTest(status=status):
                self.status = status
                response = self.ask()
                self.assertEqual(response.status_code, 503)
                self.assertFalse(self.provider.ready)

    def test_invalid_and_empty_output(self):
        for body in ({}, {'choices': []}, {'choices': [{'message': {'content': ' '}}]},
                     {'choices': [{'message': {'content': None}}]}, []):
            with self.subTest(body=body):
                self.body = body
                self.assertEqual(self.ask().status_code, 503)
                self.assertFalse(self.provider.ready)

    def test_loading_health_never_generates(self):
        self.health = {'status': 'loading'}
        self.assertEqual(self.ask().status_code, 503)
        self.assertEqual(len(self.calls), 1)

    def test_timeout(self):
        self.provider._timeout = 0.05
        self.hold = True
        response = self.ask()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'local_inference_timeout')

    def test_cancelled_client_keeps_lock_and_event_loop_responsive(self):
        self.hold = True

        async def scenario():
            task = asyncio.create_task(self.provider.answer('TEST ONLY'))
            try:
                for _ in range(500):
                    if self.entered.is_set():
                        break
                    await asyncio.sleep(0.001)
                self.assertTrue(self.entered.is_set())
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                with self.assertRaises(InferenceError) as caught:
                    await self.provider.answer('SECOND TEST ONLY')
                self.assertEqual(caught.exception.code, 'local_model_busy')
                self.assertEqual(len(self.calls), 2)
            finally:
                self.release.set()

        asyncio.run(scenario())
        self.assertFalse(self.provider._lock.locked())

    def test_config_limits_and_overrides(self):
        with patch.dict('os.environ', {'LIFELINE_GGUF_PATH': str(self.path),
                                       'LIFELINE_LLAMA_MAX_TOKENS': '170'}):
            self.assertEqual(LlamaCPUProvider()._max_tokens, 170)
        for kwargs in ({'port': 0}, {'max_tokens': -1}, {'timeout': float('nan')},
                       {'timeout': 151}):
            with self.assertRaises(ValueError):
                LlamaCPUProvider(self.path, **kwargs)


if __name__ == '__main__':
    unittest.main(verbosity=2)
