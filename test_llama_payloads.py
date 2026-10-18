"""Payload/SSE diagnostic tests only. No real model inference."""

import base64
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import unittest

from offline_ai import compare_llama_payloads as ab


UI = {
    'model': 'captured-test-model',
    'messages': [{'role': 'system', 'content': 'TEST original system'},
                 {'role': 'user', 'content': 'TEST earlier question'},
                 {'role': 'assistant', 'content': 'TEST earlier answer'},
                 {'role': 'user', 'content': 'TEST final question'}],
    'stream': True, 'return_progress': True, 'sse_ping_interval': 1,
    'reasoning_format': 'auto', 'reasoning_control': True,
    'backend_sampling': False, 'timings_per_token': True,
    'tools': [{'type': 'function', 'function': {'name': 'test_only_tool'}}],
}


class VariantTests(unittest.TestCase):
    def test_baseline_exact_and_variants_change_only_intended_dimension(self):
        original = copy.deepcopy(UI)
        cases = ab.variants(UI)
        self.assertEqual(cases['ui'], original)
        self.assertEqual(UI, original)
        for name, payload in cases.items():
            if name in ('adapter', 'ui'):
                continue
            changed = [key for key in set(original) | set(payload)
                       if (key in original) != (key in payload) or original.get(key) != payload.get(key)]
            self.assertEqual(len(changed), 1, name)
        self.assertEqual(cases['history-last']['messages'], [original['messages'][0], original['messages'][-1]])
        self.assertEqual(cases['system-lifeline']['messages'][1:], original['messages'][1:])
        self.assertEqual(cases['system-lifeline']['messages'][0]['content'], ab.safety_instruction())

    def test_adapter_extracted_from_source_and_matches_current_contract(self):
        payload = ab.adapter_payload('TEST final question', 170)
        self.assertEqual(payload, {
            'model': 'lifeline-qwen', 'temperature': 0, 'max_tokens': 170, 'stream': False,
            'messages': [{'role': 'system', 'content': ab.safety_instruction()},
                         {'role': 'user', 'content': 'TEST final question'}],
        })

    def test_invalid_capture_rejected(self):
        for ui in ({}, {'messages': []}, dict(UI, stream=False),
                   dict(UI, messages=[{'role': 'tool', 'content': 'TEST'}])):
            with self.assertRaises(ValueError):
                ab.variants(ui)


class SSETests(unittest.TestCase):
    def test_every_byte_fragmentation_utf8_crlf_comments_multiline(self):
        source = ': ping\r\nevent: custom\r\ndata: {"x":\r\ndata: "caf\u00e9"}\r\n\r\ndata: [DONE]\n\n'.encode()
        parser = ab.SSE()
        events = []
        for byte in source:
            events.extend(parser.feed(bytes([byte])))
        self.assertEqual(events, [
            {'event': 'custom', 'data': '{"x":\n"caf\u00e9"}'},
            {'event': 'message', 'data': '[DONE]'},
        ])


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.payloads = []
        self.status = 200
        self.mime = 'text/event-stream'
        self.events = []
        self.tail = b''
        self.body = self.stream([
            {'prompt_progress': {'processed': 3}, 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': None}}]},
            {'choices': [{'index': 0, 'delta': {'reasoning_content': 'TEST reasoning'}}]},
            {'choices': [{'index': 0, 'delta': {'content': 'TEST caf\u00e9 '}}]},
            {'choices': [{'index': 0, 'delta': {'content': 'answer'}}]},
            {'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]},
            {'choices': [], 'usage': {'completion_tokens': 4}},
        ])
        test = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                test.payloads.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(test.status)
                self.send_header('Content-Type', test.mime)
                self.send_header('Location', 'https://example.invalid/do-not-follow')
                self.end_headers()
                self.wfile.write(test.body)
                self.wfile.flush()
                if test.tail:
                    time.sleep(0.03)
                    self.wfile.write(test.tail)
                    self.wfile.flush()

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @staticmethod
    def stream(events, done=True):
        return (':\n\n' + ''.join('data: ' + json.dumps(e, ensure_ascii=False) + '\n\n' for e in events)
                + ('data: [DONE]\n\n' if done else '')).encode()

    def capture(self, payload=None):
        return ab.capture(self.server.server_port, payload or UI, 2, self.events.append)

    def test_full_sse_reconstruction_and_wire_payload(self):
        result = self.capture()
        self.assertEqual(self.payloads, [UI])
        self.assertEqual(result['answer'], 'TEST caf\u00e9 answer')
        self.assertEqual(result['reasoning'], 'TEST reasoning')
        self.assertEqual(result['finish_reasons'], {'0': 'stop'})
        self.assertEqual(result['usage'], {'completion_tokens': 4})
        self.assertTrue(result['done'])
        self.assertEqual(result['errors'], [])
        self.assertIsNotNone(result['first_content_seconds'])
        raw = b''.join(base64.b64decode(e['base64']) for e in self.events if e['event'] == 'raw_chunk')
        self.assertEqual(raw, self.body)

    def test_nonstreamed_response_preserves_unicode_and_usage(self):
        self.mime = 'application/json'
        data = {'choices': [{'message': {'content': 'TEST caf\u00e9', 'reasoning_content': 'TEST reasoning'},
                             'finish_reason': 'length'}], 'usage': {'completion_tokens': 160}}
        self.body = json.dumps(data).encode()
        result = self.capture(dict(UI, stream=False))
        self.assertTrue(result['done'])
        self.assertEqual(result['answer'], 'TEST caf\u00e9')
        self.assertEqual(result['finish_reasons']['0'], 'length')
        self.assertEqual(result['usage']['completion_tokens'], 160)
        self.assertIsNone(result['first_content_seconds'])

    def test_tool_and_reasoning_only_not_answer_and_never_executed(self):
        delta = {'tool_calls': [{'index': 0, 'function': {'name': 'test_only_tool', 'arguments': '{}'}}]}
        self.body = self.stream([{'choices': [{'index': 0, 'delta': delta, 'finish_reason': 'tool_calls'}]}])
        result = self.capture()
        self.assertEqual(result['answer'], '')
        self.assertEqual(result['tool_call_deltas'], delta['tool_calls'])
        self.assertEqual(result['finish_reasons']['0'], 'tool_calls')
        self.assertEqual(len(self.payloads), 1)

    def test_error_and_incomplete_stream_not_success(self):
        self.body = self.stream([{'error': {'message': 'TEST failure'}}], done=False)
        result = self.capture()
        self.assertFalse(result['done'])
        self.assertIn({'message': 'TEST failure'}, result['errors'])
        self.assertTrue(any('Premature EOF' in str(e) for e in result['errors']))

    def test_malformed_stream_preserves_evidence(self):
        self.body = b'data: {"invalid":\xff}\n\n'
        self.tail = b'data: {"later":"TEST retained after parser failure"}\n\ndata: [DONE]\n\n'
        result = self.capture()
        self.assertTrue(result['errors'])
        raw = b''.join(base64.b64decode(e['base64']) for e in self.events if e['event'] == 'raw_chunk')
        self.assertEqual(raw, self.body + self.tail)

    def test_bad_response_shapes_are_diagnostic_failures(self):
        for mime, body in (
            ('text/event-stream', self.stream([{'choices': [{'delta': None}]}])),
            ('text/event-stream', self.stream([{'choices': [None]}])),
            ('application/json', b'[]'),
            ('application/json', b'{"choices":[{"message":null}]}'),
            ('application/json', b'{"choices":[{},{}]}'),
        ):
            with self.subTest(body=body):
                self.mime, self.body = mime, body
                result = self.capture(dict(UI, stream=mime == 'text/event-stream'))
                self.assertTrue(result['errors'])
                self.assertFalse(result['done'])

    def test_redirect_not_followed(self):
        self.status = 302
        self.mime = 'application/json'
        self.body = b'{"error":"TEST redirect"}'
        result = self.capture()
        self.assertFalse(result['done'])
        self.assertEqual(result['http_status'], 302)
        self.assertEqual(len(self.payloads), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
