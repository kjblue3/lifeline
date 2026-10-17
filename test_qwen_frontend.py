"""Browser -> real FastAPI routes -> TEST DOUBLE, not real Qwen inference.

Run: python -m unittest -v test_qwen_frontend
Requires installed Playwright Chromium. No weights, downloads, or cloud APIs.
"""

import asyncio
import socket
import sqlite3
import threading
import time
import unittest
from urllib.parse import urlsplit
from unittest.mock import patch

import uvicorn
from playwright.sync_api import expect, sync_playwright

from inference import Answer, InferenceError, SAFETY_NOTICE


class TestProvider:
    """Explicit nonmedical integration fixture; never used by the application."""

    configured = True
    ready = False
    model = 'TEST DOUBLE ONLY, not Qwen'

    def __init__(self):
        self.calls = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.error = None

    async def answer(self, question):
        self.calls.append(question)
        self.entered.set()
        await asyncio.to_thread(self.release.wait, 15)
        if self.error:
            raise self.error
        self.ready = True
        return Answer(
            answer='TEST DOUBLE ONLY: <b>blue squares</b>, not model output.',
            sources=[], notice=SAFETY_NOTICE,
        )


class QwenFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Import the existing application without creating its legacy database.
        connect = sqlite3.connect
        with patch('sqlite3.connect', side_effect=lambda *a, **kw: connect(':memory:')):
            from offline_ai.qwen_adapter import app
        cls.app = app
        cls.sock = socket.socket()
        cls.sock.bind(('127.0.0.1', 0))
        cls.base = f'http://127.0.0.1:{cls.sock.getsockname()[1]}'
        cls.server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
        cls.thread = threading.Thread(
            target=cls.server.run, kwargs={'sockets': [cls.sock]}, daemon=True)
        cls.thread.start()
        for _ in range(500):
            if cls.server.started:
                break
            time.sleep(0.01)
        if not cls.server.started:
            raise RuntimeError('Existing FastAPI application did not start')
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.should_exit = True
        cls.thread.join(timeout=10)
        cls.sock.close()

    def setUp(self):
        self.provider = TestProvider()
        self.enterContext(patch('chat.provider', self.provider))
        self.context = self.browser.new_context(service_workers='block')
        self.addCleanup(self.context.close)
        self.addCleanup(self.provider.release.set)
        self.external = []
        self.errors = []
        self.payloads = []

        def guard(route):
            if urlsplit(route.request.url).netloc != urlsplit(self.base).netloc:
                self.external.append(route.request.url)
                route.abort()
            else:
                # Never intercept/fulfill API responses: exercise the real routes.
                route.continue_()

        self.context.route('**/*', guard)
        self.page = self.context.new_page()
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('request', lambda request: self.payloads.append(request.post_data_json)
                     if request.url == self.base + '/api/ask' else None)

    def open_chat(self):
        self.page.goto(self.base)
        self.page.locator('#question').fill('  Fictional blue squares test  ')
        expect(self.page.locator('#send-button')).to_be_enabled()

    def tearDown(self):
        self.assertEqual(self.external, [])
        self.assertEqual(self.errors, [])

    def test_real_route_renders_answer_notice_and_empty_sources(self):
        self.open_chat()
        expect(self.page.locator('#availability-detail')).to_contain_text('first question loads')
        self.page.locator('#question').press('Enter')
        expect(self.page.locator('.message.assistant > p').first).to_have_text(
            'TEST DOUBLE ONLY: <b>blue squares</b>, not model output.')
        expect(self.page.locator('.message-notice')).to_have_text(SAFETY_NOTICE)
        expect(self.page.locator('.message.assistant b')).to_have_count(0)
        expect(self.page.locator('.source-list')).to_have_count(0)
        expect(self.page.locator('#question')).to_have_value('')
        expect(self.page.locator('#references-state')).to_have_text('Not Installed')
        self.assertEqual(self.payloads, [{'question': 'Fictional blue squares test'}])
        self.assertEqual(self.provider.calls, ['Fictional blue squares test'])

    def test_slow_cpu_response_survives_old_30_second_timeout(self):
        self.provider.release.clear()
        self.open_chat()
        self.page.clock.install()
        self.page.locator('#send-button').click()
        self.assertTrue(self.provider.entered.wait(5))
        expect(self.page.locator('#request-status')).to_contain_text('first question also loads')
        expect(self.page.locator('#chat-form')).to_have_attribute('aria-busy', 'true')
        expect(self.page.locator('#send-button')).to_be_disabled()
        expect(self.page.locator('#question')).to_have_attribute('readonly', '')
        self.page.clock.fast_forward(35000)
        expect(self.page.locator('#request-error')).not_to_be_visible()
        expect(self.page.locator('#chat-form')).to_have_attribute('aria-busy', 'true')
        self.provider.release.set()
        expect(self.page.locator('.message.assistant')).to_have_count(1)
        expect(self.page.locator('#chat-form')).to_have_attribute('aria-busy', 'false')
        self.assertEqual(len(self.provider.calls), 1)

    def test_timeout_keeps_draft_without_automatic_retry(self):
        self.provider.release.clear()
        self.open_chat()
        self.page.clock.install()
        self.page.locator('#send-button').click()
        self.assertTrue(self.provider.entered.wait(5))
        self.page.clock.fast_forward(180001)
        expect(self.page.locator('#error-detail')).to_contain_text('timed out after 3 minutes')
        expect(self.page.locator('#error-detail')).to_contain_text('may still be loading or generating')
        expect(self.page.locator('#question')).to_have_value('  Fictional blue squares test  ')
        expect(self.page.locator('.message.assistant')).to_have_count(0)
        self.page.clock.fast_forward(10000)
        self.assertEqual(len(self.provider.calls), 1)

    def test_structured_503_and_generation_failure_allow_manual_retry(self):
        self.open_chat()
        for code in ('local_model_missing', 'local_model_load_failed',
                     'local_model_busy', 'local_inference_failed'):
            with self.subTest(code=code):
                self.provider.error = InferenceError(code, 'TEST DOUBLE ERROR: ' + code)
                self.page.locator('#send-button').click()
                expect(self.page.locator('#error-detail')).to_contain_text(code)
                expect(self.page.locator('#question')).to_have_value('  Fictional blue squares test  ')
                expect(self.page.locator('.message.assistant')).to_have_count(0)
                expect(self.page.locator('#retry-question')).to_be_enabled()
        self.provider.error = RuntimeError('PRIVATE DETAIL MUST NOT LEAK')
        self.page.locator('#retry-question').click()
        expect(self.page.locator('#error-detail')).to_contain_text('Local AI could not complete')
        expect(self.page.locator('#error-detail')).not_to_contain_text('PRIVATE DETAIL')
        self.provider.error = None
        self.page.locator('#retry-question').click()
        expect(self.page.locator('.message.assistant')).to_have_count(1)
        self.assertEqual(len(self.provider.calls), 6)

    def test_actual_qwen_provider_reports_missing_local_weights(self):
        from offline_ai.qwen_adapter import QwenCPUProvider
        provider = QwenCPUProvider()
        if provider.configured:
            self.skipTest('Real weights found; this test must not load or run Qwen')
        with patch('chat.provider', provider):
            self.open_chat()
            self.page.locator('#send-button').click()
            expect(self.page.locator('#error-detail')).to_contain_text(
                'offline_ai/models/qwen2.5-3b')
            expect(self.page.locator('.message.assistant')).to_have_count(0)
            expect(self.page.locator('#retry-question')).to_be_enabled()


if __name__ == '__main__':
    unittest.main(verbosity=2)
