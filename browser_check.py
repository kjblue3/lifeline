"""Check real missing credentials, then mock AI responses (not live Gemini)."""
import argparse
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default=os.environ.get('BROWSER_BASE_URL', 'http://127.0.0.1:8000'))
    parser.add_argument('--artifacts-dir', type=Path,
                        default=Path(tempfile.gettempdir()) / 'lifeline-browser')
    args = parser.parse_args()
    base_url = args.base_url.rstrip('/')
    origin = urlsplit(base_url)
    artifacts = args.artifacts_dir
    artifacts.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(base_url + '/')
        expect(page.locator('#connection-label')).to_have_text('Cloud AI · API key required')
        page.screenshot(path=str(artifacts / 'lifeline-desktop.png'), full_page=True)
        page.locator('#resources-open').click()
        expect(page.locator('#resources-dialog')).to_be_visible()
        expect(page.locator('#local-state')).to_have_text('Not installed')
        expect(page.locator('#cloud-state')).to_have_text('GEMINI_API_KEY required')
        expect(page.locator('#references-state')).to_have_text('Not installed')
        expect(page.locator('#offline-label')).to_have_text('Not ready for offline assistance')
        page.locator('#resources-close').click()
        page.locator('#profile-open').click()
        page.locator('#profile-name').fill('Fictional Alex')
        page.locator('#profile-notes').fill('Fictional private notes, never sent')
        page.get_by_role('button', name='Keep for this session').click()
        expect(page.locator('#profile-dialog')).not_to_be_visible()
        question = 'My fictional hiking partner injured an ankle. Where can I find guidance?'
        page.locator('#question').fill(question)
        # No routing is installed yet: this must be the actual server error.
        with page.expect_response('**/api/ask') as response:
            page.locator('#question').press('Enter')
        assert response.value.request.post_data_json == {'question': question}
        assert response.value.status == 503
        failure = response.value.json()
        assert failure['ok'] is False
        assert failure['error']['code'] == 'cloud_not_configured'
        assert 'GEMINI_API_KEY' in failure['error']['message']
        expect(page.locator('#request-error')).to_have_text(failure['error']['message'])
        expect(page.locator('#request-error')).to_be_visible()
        expect(page.locator('.message.assistant')).to_have_count(0)
        expect(page.locator('.message.user')).to_have_count(0)
        expect(page.locator('#question')).to_have_value(question)
        expect(page.locator('#send-button')).to_be_enabled()
        page.screenshot(path=str(artifacts / 'lifeline-missing-credentials.png'), full_page=True)
        print('LIVE SERVER: missing credentials returned HTTP 503 / cloud_not_configured; '
              'GEMINI_API_KEY error visible, question retained, no assistant message.', flush=True)

        # Explicit browser fixtures, not Gemini inference. simulated=False is the
        # API contract required by the UI, not evidence of a real AI response.
        mock_answer = 'MOCK ONLY - not live AI. Fictional cloud answer rendering fixture.'
        mock_notice = 'MOCK ONLY - not medical advice; no live Gemini request was made.'
        mock_source = 'MOCK source <b>plain text, not a verified reference</b>'
        mocked_questions = []

        def mock_cloud_answer(route):
            payload = route.request.post_data_json
            assert route.request.method == 'POST'
            assert set(payload) == {'question'}, payload
            assert 'Fictional Alex' not in payload['question']
            assert 'Fictional private notes' not in payload['question']
            mocked_questions.append(payload['question'])
            route.fulfill(status=200, json={'ok': True, 'data': {
                'answer': mock_answer, 'mode': 'cloud', 'simulated': False,
                'sources': [{'title': mock_source}], 'notice': mock_notice,
            }})

        print('MOCK ONLY: routing /api/ask in Playwright for rendering, retry and mobile; '
              'these are not live AI successes.', flush=True)
        page.route('**/api/ask', mock_cloud_answer)
        page.locator('#question').press('Enter')
        expect(page.locator('.message.assistant')).to_have_count(1)
        expect(page.locator('.message.assistant > p').first).to_have_text(mock_answer)
        expect(page.locator('.message.assistant .demo-badge')).to_have_text('CLOUD AI')
        expect(page.locator('.message-notice')).to_have_text(mock_notice)
        expect(page.locator('.source-heading')).to_contain_text('not independently verified')
        expect(page.locator('.source-list li')).to_have_text(mock_source)
        expect(page.locator('.source-list b')).to_have_count(0)
        expect(page.locator('.message.user')).to_have_text('YOU' + question)
        expect(page.locator('#question')).to_have_value('')
        expect(page.locator('#request-error')).not_to_be_visible()
        expect(page.locator('.welcome')).not_to_be_visible()
        page.screenshot(path=str(artifacts / 'lifeline-chat-mocked-not-live-ai.png'), full_page=True)

        def abort_ask(route):
            route.abort()

        page.route('**/api/ask', abort_ask)
        page.locator('#question').fill('A retryable fictional question')
        page.locator('#question').press('Enter')
        expect(page.locator('#request-error')).to_be_visible()
        expect(page.locator('#question')).to_have_value('A retryable fictional question')
        expect(page.locator('.message.assistant')).to_have_count(1)
        expect(page.locator('#send-button')).to_be_enabled()
        page.unroute('**/api/ask', abort_ask)
        page.locator('#question').press('Enter')
        expect(page.locator('.message.assistant')).to_have_count(2)
        expect(page.locator('.message.user')).to_have_count(2)
        expect(page.locator('#request-error')).not_to_be_visible()
        expect(page.locator('#question')).to_have_value('')

        page.locator('#profile-open').click()
        expect(page.locator('#profile-name')).to_have_value('Fictional Alex')
        expect(page.locator('#profile-notes')).to_have_value('Fictional private notes, never sent')
        expect(page.locator('#profile-summary')).to_contain_text('Not used in answers or sent to the API')
        page.locator('#profile-clear').click()
        page.locator('#profile-open').click()
        expect(page.locator('#profile-name')).to_have_value('')
        expect(page.locator('#profile-notes')).to_have_value('')
        page.locator('#profile-name').fill('Fictional Alex')
        page.get_by_role('button', name='Keep for this session').click()

        # Browser offline mode also applies to localhost. Block external requests
        # instead: the locally served prototype must not depend on any of them.
        page.route('**/*', lambda route: route.fallback()
                   if urlsplit(route.request.url)[:2] == origin[:2]
                   else route.abort())
        page.reload()
        expect(page.locator('#connection-label')).to_have_text('Cloud AI · API key required')
        expect(page.locator('#profile-summary')).to_contain_text('In memory only')
        expect(page.locator('.message')).to_have_count(0)
        page.locator('#profile-open').click()
        expect(page.locator('#profile-name')).to_have_value('')
        expect(page.locator('#profile-notes')).to_have_value('')
        page.keyboard.press('Escape')
        expect(page.locator('#profile-dialog')).not_to_be_visible()

        for width in (390, 768):
            page.set_viewport_size({'width': width, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), width
        page.set_viewport_size({'width': 390, 'height': 844})
        page.screenshot(path=str(artifacts / 'lifeline-mobile.png'), full_page=True)
        page.locator('#question').fill('A fictional mobile demo')
        page.locator('#send-button').click()
        expect(page.locator('.message.assistant')).to_have_count(1)
        expect(page.locator('.message.assistant')).to_contain_text(mock_answer)
        expect(page.locator('#question')).to_have_value('')
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(artifacts / 'lifeline-mobile-chat-mocked-not-live-ai.png'), full_page=True)
        page.locator('#clear-chat').click()
        expect(page.locator('.welcome')).to_be_visible()
        expect(page.locator('.starters')).to_be_visible()
        expect(page.locator('.message')).to_have_count(0)
        expect(page.locator('#request-status')).to_have_text('')
        page.locator('#resources-open').click()
        expect(page.locator('#resources-dialog')).to_be_visible()
        page.keyboard.press('Escape')
        expect(page.locator('#resources-dialog')).not_to_be_visible()
        page.route('**/api/status', lambda route: route.abort())
        page.locator('#resources-open').click()
        expect(page.locator('#connection-label')).to_have_text('Backend unavailable')
        page.unroute('**/api/status')
        page.locator('#refresh-status').click()
        expect(page.locator('#connection-label')).to_have_text('Cloud AI · API key required')
        assert mocked_questions == [question, 'A retryable fictional question', 'A fictional mobile demo']
        assert not errors, errors
        browser.close()
    print('Browser checks passed: real missing-credentials failure; MOCKED (not live AI) '
          'cloud rendering/retry/mobile; profile privacy, clear, local-only assets, status recovery.')
    print(f'Screenshots: {artifacts}')


if __name__ == '__main__':
    main()
