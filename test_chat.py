"""Local-only API contract tests; no real or simulated model is installed.

Run: python -m unittest -v test_chat
Network connections are forbidden, and SQLite initialization uses memory only.
Frontend files and Kiran's model files are never opened by these tests.
"""
import os
import sqlite3
import sys
import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

_connect = sqlite3.connect
with patch('socket.socket.connect', side_effect=AssertionError('Network forbidden')):
    with patch('sqlite3.connect', side_effect=lambda *args, **kwargs: _connect(':memory:')):
        from app import app

import chat
from inference import Answer, InferenceError, SAFETY_NOTICE
from local_adapter import LocalAIAdapter


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.network = self.enterContext(patch(
            'socket.socket.connect', side_effect=AssertionError('Network forbidden')))
        self.enterContext(patch('socket.create_connection',
                                side_effect=AssertionError('Network forbidden')))
        self.enterContext(patch('socket.getaddrinfo',
                                side_effect=AssertionError('DNS forbidden')))
        self.enterContext(patch('sqlite3.connect',
                                side_effect=AssertionError('On-disk database forbidden')))
        self.provider = LocalAIAdapter()
        self.enterContext(patch.object(chat, 'provider', self.provider))
        self.client = self.enterContext(TestClient(app))

    def test_health_without_network(self):
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'ok': True, 'data': {'status': 'ok', 'service': 'lifeline'}})
        self.network.assert_not_called()

    def test_status_reports_local_not_connected(self):
        self.assertEqual(self.client.get('/api/status').json(), {'ok': True, 'data': {
            'mode': 'unavailable',
            'cloud': {'enabled': False, 'configured': False, 'ready': False},
            'local': {'configured': False, 'ready': False, 'model': None,
                      'message': 'Local AI not connected'},
            'references': {'installed': False, 'count': 0},
            'offline_ready': False,
        }})

    def test_question_returns_unavailable_not_fake_answer(self):
        response = self.client.post('/api/ask', json={'question': 'A fictional scenario'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'ok': False, 'error': {
            'code': 'local_not_connected',
            'message': 'Local AI not connected. The ExecuTorch model has not been integrated. '
                       + SAFETY_NOTICE,
        }})
        self.assertNotIn('data', response.json())
        self.network.assert_not_called()

    def test_gemini_environment_cannot_enable_cloud(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-only-unused',
                                     'GEMINI_MODEL': 'unused'}):
            self.assertEqual(self.client.post('/api/ask', json={'question': 'Test'}).status_code, 503)
            self.assertFalse(self.client.get('/api/status').json()['data']['cloud']['enabled'])
        self.assertNotIn('cloud_ai', sys.modules)
        self.network.assert_not_called()

    def test_invalid_questions(self):
        for payload in ({}, {'question': ''}, {'question': '   '},
                        {'question': 'x' * 2001}, {'question': 123}):
            with self.subTest(payload=payload):
                response = self.client.post('/api/ask', json=payload)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()['error']['code'], 'invalid_request')
                self.assertFalse(response.json()['ok'])

    def test_future_adapter_contract_with_explicit_test_fixture(self):
        # This fixture tests serialization only. It is not actual AI inference.
        self.provider.configured = True
        self.provider.ready = True
        self.provider.model = 'test-fixture-not-a-real-model'
        self.provider.answer = AsyncMock(return_value=Answer(
            answer='TEST FIXTURE ONLY, not model output.', notice=SAFETY_NOTICE))
        response = self.client.post('/api/ask', json={
            'question': '  Test question  ', 'profile': {'name': 'Not forwarded'},
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        UUID(data['id'])
        self.assertEqual(data['mode'], 'local')
        self.assertIs(data['simulated'], False)
        self.assertEqual(data['sources'], [])
        self.assertEqual(data['notice'], SAFETY_NOTICE)
        self.provider.answer.assert_awaited_once_with('Test question')
        status = self.client.get('/api/status').json()['data']
        self.assertEqual(status['mode'], 'local')
        self.assertTrue(status['local']['ready'])
        self.assertFalse(status['cloud']['enabled'])
        self.assertFalse(status['offline_ready'])  # References are still absent.

    def test_answer_contract_rejects_cloud_and_fake_modes(self):
        for invalid in ({'mode': 'cloud'}, {'mode': 'mock'}, {'simulated': True}, {'answer': ''}):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                Answer(**({'answer': 'Test', 'notice': SAFETY_NOTICE} | invalid))

    def test_adapter_errors_remain_structured(self):
        self.provider.answer = AsyncMock(side_effect=InferenceError(
            'local_not_ready', 'Local model is not ready. ' + SAFETY_NOTICE))
        response = self.client.post('/api/ask', json={'question': 'Test'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'local_not_ready')
        self.provider.answer.side_effect = RuntimeError('Private runtime detail')
        response = self.client.post('/api/ask', json={'question': 'Test'})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()['error']['code'], 'local_inference_failed')
        self.assertNotIn('Private runtime detail', response.text)

    def test_chat_router_is_independent_of_database_and_frontend(self):
        isolated = FastAPI()
        isolated.include_router(chat.router)
        with TestClient(isolated) as client:
            self.assertEqual(client.get('/api/health').status_code, 200)
            self.assertEqual(client.get('/api/status').status_code, 200)
            self.assertEqual(client.post('/api/ask', json={'question': 'Test'}).status_code, 503)

    def test_legacy_database_routes_remain_registered(self):
        self.assertTrue({'/status', '/reports', '/sync', '/cloud-reports', '/legacy'} <=
                        {getattr(route, 'path', None) for route in app.routes})


if __name__ == '__main__':
    unittest.main()
