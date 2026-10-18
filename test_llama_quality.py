"""Test diagnostic tooling with synthetic responses, never model correctness."""

from contextlib import redirect_stdout
import ast
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from offline_ai import probe_llama_quality as probe


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.output = Path(self.directory) / 'probe.jsonl'
        self.requests = []
        self.status = 200
        self.raw_body = None
        self.body = {'choices': [{'message': {'content': 'TEST ONLY: blue square orange'}}],
                     'usage': {'prompt_tokens': 20, 'completion_tokens': 6},
                     'timings': {'predicted_per_second': 12.3}}
        test = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                test.requests.append((self.path, None))
                self.respond({'status': 'ok'})

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                test.requests.append((self.path, payload))
                self.respond({'id_slot': 0, 'n_erased': 42} if self.path.startswith('/slots/') else test.body)

            def respond(self, body):
                self.send_response(test.status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Location', 'https://example.invalid/do-not-follow')
                self.end_headers()
                self.wfile.write(test.raw_body if test.raw_body is not None else json.dumps(body).encode())

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def run_probe(self, *extra):
        argv = ['--port', str(self.server.server_port), '--label', 'TEST DOUBLE NOT INFERENCE',
                '--rounds', '1', '--output', str(self.output), *extra]
        with redirect_stdout(io.StringIO()):
            code = probe.main(argv)
        return code, [json.loads(line) for line in self.output.read_text().splitlines()]

    def test_five_prompts_default_matches_adapter_and_retains_raw_metrics(self):
        with patch.dict('os.environ', {'HTTP_PROXY': 'http://example.invalid:1'}):
            code, events = self.run_probe()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.requests), 6)
        completions = [event for event in events if event['event'] == 'completion']
        self.assertEqual(len(completions), 5)
        self.assertIn('No verified medical references', events[0]['system_instruction'])
        for event in completions:
            payload = event['request']
            self.assertEqual(set(payload), {'model', 'messages', 'temperature', 'max_tokens', 'stream'})
            self.assertEqual(len(payload['messages']), 2)
            self.assertEqual(payload['messages'][0]['content'], events[0]['system_instruction'])
            self.assertEqual(json.loads(event['raw_response']), self.body)
            self.assertEqual(event['completion_tokens'], 6)
            self.assertGreater(event['latency_seconds'], 0)
            self.assertGreater(event['wall_output_tokens_per_second'], 0)
            self.assertEqual(event['manual_quality'], 'not_reviewed')
            self.assertEqual(event['quality_triage']['review'], 'REQUIRED')

    def test_cache_off_and_erase_are_explicit(self):
        code, events = self.run_probe('--cache', 'off', '--erase-between')
        self.assertEqual(code, 0)
        self.assertEqual(len([event for event in events if event['event'] == 'erase']), 5)
        for _, payload in self.requests:
            if payload and 'messages' in payload:
                self.assertIs(payload['cache_prompt'], False)
                self.assertEqual(payload['id_slot'], 0)
                self.assertEqual(payload['n_cache_reuse'], 0)

    def test_runtime_regression_suite_preserves_full_safety_and_long_context(self):
        code, events = self.run_probe('--suite', 'runtime', '--rounds', '2')
        self.assertEqual(code, 0)
        completions = [event for event in events if event['event'] == 'completion']
        self.assertEqual([event['prompt_id'] for event in completions],
                         ['short', 'long-ordinary', 'full-lifeline-safety'] * 2)
        # Actual source instruction, not a paraphrase or weakened replacement.
        tree = ast.parse((Path(probe.__file__).resolve().parents[1] / 'inference.py').read_text())
        instruction = next(ast.literal_eval(node.value) for node in tree.body
                           if isinstance(node, ast.Assign) and any(
                               isinstance(target, ast.Name) and target.id == 'SYSTEM_INSTRUCTION'
                               for target in node.targets))
        for offset in (0, 3):
            short, long, safety = [event['request'] for event in completions[offset:offset + 3]]
            self.assertGreater(len(long['messages'][1]['content']), 2000)
            self.assertLess(len(short['messages'][1]['content']), 150)
            self.assertEqual(long['messages'][1], safety['messages'][1])
            self.assertEqual(long['messages'][0]['content'], probe.SIMPLE_SYSTEM)
            self.assertEqual(safety['messages'][0]['content'], instruction)
            self.assertNotEqual(long['messages'][0], safety['messages'][0])
            self.assertEqual(len(safety['messages']), 2)
            self.assertEqual(safety['temperature'], 0)
            self.assertEqual(safety['max_tokens'], 160)
            self.assertIs(safety['stream'], False)
            self.assertNotIn('cache_prompt', safety)

    def test_missing_usage_not_fabricated_and_human_judgment_separate(self):
        self.body.pop('usage')
        with patch('builtins.input', return_value='corrupted'):
            code, events = self.run_probe('--review', '--cache', 'on')
        self.assertEqual(code, 0)  # Collection success is NOT a quality pass.
        for event in events:
            if event['event'] == 'completion':
                self.assertIsNone(event['completion_tokens'])
                self.assertIsNone(event['wall_output_tokens_per_second'])
                self.assertTrue(event['request']['cache_prompt'])
            if event['event'] == 'review':
                self.assertEqual(event['manual_quality'], 'corrupted')

    def test_body_saved_before_interrupted_manual_review(self):
        with patch('builtins.input', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_probe('--review')
        events = [json.loads(line) for line in self.output.read_text().splitlines()]
        self.assertEqual(events[-1]['event'], 'completion')
        self.assertIn('TEST ONLY', events[-1]['raw_response'])

    def test_unhealthy_or_redirect_stops_without_generation_or_retry(self):
        self.status = 302
        code, events = self.run_probe()
        self.assertEqual(code, 2)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(events[-1]['http_status'], 302)

    def test_completion_http_failure_recorded_then_stops(self):
        native = probe.request

        def fail_post(port, method, path, timeout, payload=None):
            if method == 'POST':
                self.status = 503
            return native(port, method, path, timeout, payload)

        with patch.object(probe, 'request', side_effect=fail_post):
            code, events = self.run_probe()
        self.assertEqual(code, 2)
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(events[-1]['http_status'], 503)

    def test_transport_failure_saved_and_no_retry(self):
        with patch.object(probe, 'request', side_effect=TimeoutError('TEST timeout')) as request:
            code, events = self.run_probe()
        self.assertEqual(code, 2)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(events[-1]['event'], 'transport_error')

    def test_existing_output_not_overwritten(self):
        self.output.write_text('DO NOT OVERWRITE')
        with redirect_stdout(io.StringIO()), patch('sys.stderr', io.StringIO()):
            with self.assertRaises(SystemExit):
                self.run_probe()
        self.assertEqual(self.output.read_text(), 'DO NOT OVERWRITE')
        self.assertEqual(self.requests, [])

    def test_heuristics_never_certify_quality(self):
        result = probe.assess('blue square orange ' * 20)
        self.assertIn('repeated_three_word_sequence', result['flags'])
        self.assertIn('many_non_ascii_letters_in_english_test', probe.assess('\u4e2d\u6587' * 20)['flags'])
        self.assertEqual(probe.assess('A coherent looking TEST sentence.')['review'], 'REQUIRED')
        self.assertEqual(probe.assess(None)['flags'], ['empty_or_nontext'])

    def test_invalid_utf8_original_bytes_preserved(self):
        self.raw_body = b'{"choices":[{"message":{"content":"TEST \xff"}}]}'
        result = probe.request(self.server.server_port, 'POST', '/v1/chat/completions', 1, {})
        self.assertTrue(result['utf8_decode_error'])
        self.assertEqual(base64.b64decode(result['raw_response_base64']), self.raw_body)
        self.assertIn('\ufffd', result['raw_response'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
