"""Check current local-only UI; one guarded live unavailable ask, then fixtures.

Run: .venv/bin/python frontend_check.py localhost8000
Successful inference is ALWAYS intercepted. Existing preview screenshots are untouched.
"""
import argparse
import copy
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


PROFILE = {
    'name': 'Fictional Frontend Tester', 'age': '37',
    'allergies': 'Fictional allergy marker',
    'medications': 'Fictional medication marker',
    'conditions': 'Fictional condition marker',
    'contact': 'Fictional Contact 555-0100',
}
ANSWER = 'FIXTURE ONLY: blue squares and orange circles. No inference or medical advice.'
NOTICE = 'INTERCEPTED BROWSER FIXTURE, not a model response or medical guidance.'
STATUS = {
    'mode': 'local',
    'cloud': {'enabled': False, 'configured': False, 'ready': False},
    'local': {'configured': True, 'ready': False, 'model': 'FIXTURE-local-model',
              'message': 'FIXTURE ONLY: local readiness test'},
    'references': {'installed': False, 'count': 7}, 'offline_ready': False,
}
REPLY = {
    'answer': ANSWER, 'mode': 'local', 'simulated': False, 'notice': NOTICE,
    'sources': [
        {'title': 'FIXTURE HTTP', 'url': 'http://example.invalid/reference'},
        {'title': 'FIXTURE HTTPS', 'url': 'https://example.invalid/reference'},
        {'title': 'BLOCKED JS', 'url': 'javascript:window.fixtureXss=1'},
        {'title': 'BLOCKED credentials', 'url': 'https://user:pass@example.invalid/'},
        {'title': '<b>Plain fixture title without URL</b>'},
    ],
    'sections': [
        {'title': '<img src=x onerror="window.fixtureXss=1">',
         'content': '<script>window.fixtureXss=1</script> **literal fixture**'},
        {'title': 'FIXTURE text fallback', 'text': '<b>Not HTML</b>'},
    ],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', nargs='?', default='localhost8000')
    parser.add_argument('--base-url')
    parser.add_argument('--artifacts-dir', type=Path, default=Path('artifacts'))
    args = parser.parse_args()
    target = args.base_url or args.target
    base = ('http://localhost:8000' if target == 'localhost8000' else
            target if '://' in target else 'http://' + target).rstrip('/')
    origin = urlsplit(base)
    if origin.hostname not in ('localhost', '127.0.0.1', '::1'):
        parser.error('Live safety checks require a loopback host.')
    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    passed, failed, skipped, screenshots = [], [], [], []
    calls, external, unknown, errors, downloads, payloads = [], [], [], [], [], []
    live = {'status': [], 'ask': [], 'permitted': False}
    state = {'fixture': False, 'status': copy.deepcopy(STATUS), 'abort': False,
             'hold': False, 'held': [], 'reply': copy.deepcopy(REPLY), 'ask_error': False}

    def require(condition, detail):
        if not condition:
            raise AssertionError(detail)

    def check(name, action):
        try:
            skip_reason = action()
        except Exception as exc:
            detail = f'{type(exc).__name__}: {exc}'
            failed.append({'test': name, 'error': detail})
            print(f'FAIL: {name}\n{detail}', flush=True)
        else:
            if isinstance(skip_reason, str):
                skipped.append({'test': name, 'reason': skip_reason})
                print(f'SKIP: {name}: {skip_reason}', flush=True)
                return
            passed.append(name)
            print(f'PASS: {name}', flush=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={'width': 1440, 'height': 1000},
                                      reduced_motion='reduce', service_workers='block')
        context.add_init_script('''window.fixtureUnhandled = [];
            addEventListener('unhandledrejection', e => window.fixtureUnhandled.push(String(e.reason)));''')

        def guard(route):
            request = route.request
            url = urlsplit(request.url)
            same_origin = url[:2] == origin[:2]
            if url.path == '/api' or url.path.startswith('/api/'):
                calls.append({'path': url.path, 'method': request.method,
                              'fixture': state['fixture'], 'time': time.monotonic()})
                if not same_origin:
                    unknown.append(request.url)
                    route.abort()
                elif url.path == '/api/status' and request.method == 'GET':
                    if state['fixture']:
                        if state['abort']:
                            route.abort()
                        elif state['hold']:
                            state['held'].append(route)
                        else:
                            route.fulfill(json={'ok': True, 'data': state['status']})
                    else:
                        response = route.fetch(max_retries=0, max_redirects=0)
                        live['status'].append({'status': response.status, 'body': response.json()})
                        route.fulfill(response=response)
                elif url.path == '/api/ask' and request.method == 'POST':
                    payloads.append(request.post_data_json)
                    if state['fixture']:
                        if state['ask_error']:
                            route.fulfill(status=503, json={'ok': False, 'error': {
                                'code': 'fixture_unavailable', 'message': 'FIXTURE ONLY HTTP 503'}})
                        else:
                            route.fulfill(json={'ok': True, 'data': state['reply']})
                    elif live['permitted'] and not live['ask']:
                        # Recheck immediately before the only live ask. Never ask a ready model.
                        probe = context.request.get(base + '/api/status', max_redirects=0)
                        data = probe.json()
                        live['status'].append({'status': probe.status, 'body': data, 'safety_probe': True})
                        if probe.status != 200 or data.get('ok') is not True or data['data']['local']['ready'] is not False:
                            live['permitted'] = False
                            route.abort()
                            return
                        live['permitted'] = False
                        response = route.fetch(max_retries=0, max_redirects=0)
                        live['ask'].append({'status': response.status, 'body': response.json()})
                        route.fulfill(response=response)
                    else:
                        unknown.append('BLOCKED unsafe live ask: ' + request.url)
                        route.abort()
                else:
                    unknown.append(request.url)
                    route.abort()
            elif same_origin and request.method == 'GET' and url.path in (
                    '/', '/assets/styles.css', '/assets/api.js', '/assets/app.js', '/favicon.ico'):
                route.continue_()
            else:
                external.append(request.url)
                route.abort()

        context.route('**/*', guard)
        page = context.new_page()
        page.set_default_timeout(6500)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('download', lambda download: downloads.append(download.suggested_filename))

        def navigate(screen):
            page.locator(f'[data-screen="{screen}"]').click()
            expect(page.locator(f'#screen-{screen}')).to_be_visible()
            expect(page.locator(f'[data-screen="{screen}"]')).to_have_attribute('aria-current', 'page')
            for other in ('chat', 'trip', 'profile'):
                if other != screen:
                    expect(page.locator(f'#screen-{other}')).not_to_be_visible()

        def count(path):
            return sum(call['path'] == path for call in calls)

        def screenshot(name):
            require(not state['fixture'], 'Actual screenshots must not contain fixtures')
            expect(page.locator('#connection-label')).to_have_text('Local AI Not Ready')
            expect(page.locator('#internet-label')).to_have_text('Internet Connection Unknown')
            expect(page.locator('#connection-state')).to_have_attribute('data-ready', 'false')
            path = args.artifacts_dir / name
            page.screenshot(path=str(path), full_page=True)
            screenshots.append(str(path.resolve()))

        def profile_save(values):
            navigate('profile')
            for field, value in values.items():
                page.locator(f'#profile-{field}').fill(value)
            page.locator('#profile-save').click()
            expect(page.locator('#profile-summary')).to_contain_text('memory only')
            for field, value in values.items():
                expect(page.locator(f'#profile-{field}')).to_have_value(value)
                expect(page.locator(f'#profile-{field}')).to_have_attribute('readonly', '')

        def live_status():
            response = page.goto(base + '/')
            require(response is not None and response.ok, 'Frontend document unavailable')
            expect(page.locator('#connection-label')).not_to_have_text('Checking Local AI Status...')
            require(live['status'], 'No live status response observed')
            result = live['status'][-1]
            require(result['status'] == 200 and result['body']['ok'] is True, result)
            data = result['body']['data']
            require(data['mode'] in ('local', 'unavailable') and data['cloud']['ready'] is False, data)
            if data['local']['ready']:
                return 'Local model ready; not-ready screenshots skipped and live ask forbidden'
            require(data['local']['ready'] is False, data)
            expect(page.locator('#connection-label')).to_have_text('Local AI Not Ready')
            expect(page.locator('#local-state')).to_have_text('Not ready')
            screenshot('lifeline-local-desktop.png')
            page.set_viewport_size({'width': 390, 'height': 844})
            screenshot('lifeline-local-mobile.png')
            page.set_viewport_size({'width': 1440, 'height': 1000})
            live['permitted'] = True

        check('LIVE local-only status and actual not-ready desktop/mobile screenshots', live_status)

        def live_unavailable_ask():
            if not live['permitted']:
                return 'No verified live not-ready status; live ask forbidden'
            question = 'Fictional UI availability check only: blue squares, not a medical question.'
            page.locator('#question').fill(question)
            page.locator('#send-button').click()
            expect(page.locator('#request-error')).to_be_visible()
            if not live['ask']:
                return 'Safety recheck changed; live ask blocked'
            result = live['ask'][0]
            require(result['status'] == 503 and result['body']['ok'] is False, result)
            message = result['body']['error']['message']
            require(isinstance(message, str) and message, result)
            expect(page.locator('#error-detail')).to_contain_text(message)
            expect(page.locator('#question')).to_have_value(question)
            expect(page.locator('.message.user')).to_have_count(1)
            expect(page.locator('.message.assistant')).to_have_count(0)
            expect(page.locator('#retry-question')).to_be_enabled()
            before = count('/api/ask')
            page.wait_for_timeout(5000)
            require(count('/api/ask') == before == 1, 'Automatic live ask retry detected')
            expect(page.locator('#question')).to_have_value(question)
            expect(page.locator('.message.assistant')).to_have_count(0)

        check('LIVE 503 actual backend error, retained user/draft, retry available, no auto asks for 5s', live_unavailable_ask)
        # Every subsequent API response, including successful inference, is intercepted.
        live['permitted'] = False
        state['fixture'] = True

        def fixture_start():
            page.goto(base + '/?preview=1')
            expect(page.locator('#connection-label')).to_have_text('Local AI Not Ready')
            expect(page.locator('#preview-mode, .preview-panel')).to_have_count(0)
            expect(page.locator('.message')).to_have_count(0)
            require(calls[-1]['fixture'], 'preview query bypassed production API')
            expect(page.locator('#model-name')).to_have_text('FIXTURE-local-model')
            expect(page.locator('#references-state')).to_have_text('Not Installed')
            expect(page.locator('#offline-label')).to_have_text('Complete offline system not ready')

        check('Removed preview query uses production status, no simulation or fake messages', fixture_start)

        def polling():
            question = 'FIXTURE draft preserved while typing'
            page.locator('#question').fill(question)
            page.locator('#question').focus()
            before = count('/api/status')
            started = time.monotonic()
            state['status']['local']['ready'] = True
            expect(page.locator('#connection-label')).to_have_text('Local AI Active', timeout=5500)
            elapsed = time.monotonic() - started
            require(count('/api/status') == before + 1 and 3 <= elapsed <= 5.5,
                    {'elapsed': elapsed, 'status_requests': count('/api/status') - before})
            expect(page.locator('#question')).to_be_focused()
            expect(page.locator('#question')).to_have_value(question)
            expect(page.locator('#model-name')).to_have_text('FIXTURE-local-model')
            expect(page.locator('#references-state')).to_have_text('Not Installed')
            expect(page.locator('#offline-label')).to_have_text('Complete offline system not ready')
            state['status']['references']['installed'] = True
            state['status']['offline_ready'] = True
            expect(page.locator('#references-state')).to_have_text('Available \u00b7 7 Reference Topics', timeout=5500)
            expect(page.locator('#library-summary')).to_have_text('Medical Library: Available \u00b7 7 Reference Topics')
            expect(page.locator('#offline-label')).to_have_text('Complete offline system ready')
            expect(page.locator('#question')).to_be_focused()
            expect(page.locator('#question')).to_have_value(question)

        check('Automatic 4s polling: ready false->true, model/count7, installed false/true, offline readiness, focused draft', polling)

        def success_and_sources():
            profile_save(PROFILE)
            navigate('chat')
            question = 'FIXTURE question one: blue squares only.'
            page.locator('#question').fill(question)
            page.locator('#send-button').click()
            expect(page.locator('.message.assistant')).to_have_count(1)
            expect(page.locator('.message.assistant > p').first).to_have_text(ANSWER)
            expect(page.locator('.message-notice')).to_have_text(NOTICE)
            expect(page.locator('.demo-badge').filter(has_text='LOCAL AI')).to_have_count(1)
            expect(page.locator('#question')).to_have_value('')
            require(payloads[-1] == {'question': question}, payloads[-1])
            links = page.locator('.source-list a')
            expect(links).to_have_count(2)
            for index, protocol in enumerate(('http', 'https')):
                expect(links.nth(index)).to_have_attribute('href', protocol + '://example.invalid/reference')
                expect(links.nth(index)).to_have_attribute('target', '_blank')
                expect(links.nth(index)).to_have_attribute('rel', 'noopener noreferrer')
                expect(links.nth(index)).to_have_attribute('referrerpolicy', 'no-referrer')
            expect(page.locator('.source-list')).not_to_contain_text('BLOCKED')
            expect(page.locator('.source-list')).to_contain_text('<b>Plain fixture title without URL</b>')
            expect(page.locator('.message.assistant h3').first).to_have_text(REPLY['sections'][0]['title'])
            expect(page.locator('.message.assistant')).to_contain_text(REPLY['sections'][0]['content'])
            expect(page.locator('.message.assistant')).to_contain_text('<b>Not HTML</b>')
            expect(page.locator('.message.assistant img, .message.assistant script, .message.assistant b')).to_have_count(0)
            require(page.evaluate('window.fixtureXss === undefined'), 'HTML executed')

        check('Intercepted nonmedical local answer, question-only payload with profile; safe sources and literal sections', success_and_sources)

        def rejection_and_retry():
            variants = [dict(REPLY, simulated=True), dict(REPLY, mode='cloud'),
                        dict(REPLY, answer=''), dict(REPLY, answer=42),
                        dict(REPLY, sources=None), dict(REPLY, notice={})]
            for index, reply in enumerate(variants):
                state['reply'] = reply
                question = f'FIXTURE invalid response {index}'
                page.locator('#question').fill(question)
                page.locator('#send-button').click()
                expect(page.locator('#error-detail')).to_contain_text('The backend did not return a valid answer.')
                expect(page.locator('#question')).to_have_value(question)
                expect(page.locator('.message.assistant')).to_have_count(1)
                expect(page.locator('#retry-question')).to_be_enabled()
            state['reply'] = copy.deepcopy(REPLY)
            state['ask_error'] = True
            question = 'FIXTURE explicit retry test, orange circles only.'
            page.locator('#question').fill(question)
            page.locator('#send-button').click()
            expect(page.locator('#error-detail')).to_contain_text('FIXTURE ONLY HTTP 503')
            expect(page.locator('#question')).to_have_value(question)
            users = page.locator('.message.user').count()
            before = count('/api/ask')
            page.wait_for_timeout(5000)
            require(count('/api/ask') == before, 'Automatic fixture ask retry')
            expect(page.locator('.message.assistant')).to_have_count(1)
            state['ask_error'] = False
            page.locator('#retry-question').click()
            expect(page.locator('.message.assistant')).to_have_count(2)
            expect(page.locator('.message.user')).to_have_count(users)
            expect(page.locator('#request-error')).not_to_be_visible()
            expect(page.locator('#question')).to_have_value('')
            require(payloads[-2:] == [{'question': question}] * 2, payloads[-2:])
            require(all(set(payload) == {'question'} for payload in payloads), payloads)

        check('Reject simulated/cloud/malformed answers; HTTP503 no auto retry for 5s, explicit retry no duplicate user/history/profile', rejection_and_retry)

        def outage_recovery():
            history = page.locator('#messages').inner_text()
            draft = 'FIXTURE focused draft during status outage'
            page.locator('#question').fill(draft)
            state['abort'] = True
            page.locator('#status-open').click()
            page.locator('#refresh-status').click()
            expect(page.locator('#connection-label')).to_have_text('Unable to Check AI Status')
            expect(page.locator('#connection-state')).to_have_attribute('data-ready', 'false')
            for selector in ('#local-state', '#model-name', '#references-state'):
                expect(page.locator(selector)).to_have_text('Not verified')
            expect(page.locator('#offline-label')).to_have_text('Offline readiness unverified')
            page.locator('#status-close').click()
            expect(page.locator('#send-button')).to_be_disabled()
            page.locator('#question').focus()
            state['abort'] = False
            expect(page.locator('#connection-label')).to_have_text('Local AI Active', timeout=5500)
            expect(page.locator('#question')).to_be_focused()
            expect(page.locator('#question')).to_have_value(draft)
            require(page.locator('#messages').inner_text() == history, 'History changed across outage/polls')
            expect(page.locator('#send-button')).to_be_enabled()

        check('Status network abort clears stale readiness; automatic recovery without reload preserves focus/draft/history', outage_recovery)

        def no_overlap():
            state['hold'] = True
            # Let the next real poll start, then keep it pending beyond another poll interval.
            deadline = time.monotonic() + 5.5
            while not state['held'] and time.monotonic() < deadline:
                page.wait_for_timeout(50)
            require(len(state['held']) == 1, 'Expected one held automatic status request')
            before = count('/api/status')
            page.locator('#status-open').click()
            page.locator('#refresh-status').click()
            expect(page.locator('#refresh-status')).to_be_disabled()
            page.locator('#refresh-status').dispatch_event('click')
            page.wait_for_timeout(4500)
            require(count('/api/status') == before and len(state['held']) == 1,
                    'Polling/refresh overlapped a held status request')
            state['hold'] = False
            state['held'].pop().fulfill(json={'ok': True, 'data': state['status']})
            expect(page.locator('#refresh-status')).to_be_enabled()
            page.locator('#status-close').click()

        check('Held status >4s plus refresh/repeated refresh share one request with no overlap', no_overlap)
        state['hold'] = False
        for route in state['held']:
            route.fulfill(json={'ok': True, 'data': state['status']})
        state['held'].clear()

        def connectivity():
            history = page.locator('#messages').inner_text()
            for online in (False, True, False, True):
                page.evaluate('''online => {
                    Object.defineProperty(navigator, 'onLine', {configurable: true, get: () => online});
                    dispatchEvent(new Event(online ? 'online' : 'offline'));
                }''', online)
                require(page.evaluate('navigator.onLine') == online, 'navigator fixture not applied')
                expect(page.locator('body')).to_have_attribute('data-connectivity', 'unknown')
                expect(page.locator('#internet-label')).to_have_text('Internet Connection Unknown')
            # DOM-only CSS fixtures, never a product preview or status simulation.
            for ready in (False, True):
                state['status']['local']['ready'] = ready
                page.locator('#status-open').click()
                page.locator('#refresh-status').click()
                expect(page.locator('#connection-state')).to_have_attribute('data-ready', str(ready).lower())
                page.locator('#status-close').click()
                for connectivity, color in (('available', 'rgb(240, 249, 241)'),
                                            ('unavailable', 'rgb(255, 241, 240)'),
                                            ('unknown', 'rgb(243, 244, 246)')):
                    page.evaluate('value => document.body.dataset.connectivity = value', connectivity)
                    require(page.locator('body').evaluate('(el) => getComputedStyle(el).backgroundColor') == color,
                            f'DOM CSS fixture {connectivity}/{ready}')
                    expect(page.locator('#connection-state')).to_have_attribute('data-ready', str(ready).lower())
                    expect(page.locator('#internet-label')).to_have_text('Internet Connection Unknown')
            page.evaluate('document.body.dataset.connectivity = "unknown"')
            require(page.locator('#messages').inner_text() == history, 'Connectivity changed history')

        check('Production connectivity stays unknown under navigator toggles; DOM-only color fixtures independent of AI', connectivity)

        def trip():
            navigate('trip')
            page.locator('#destination').fill('Fictional test destination')
            topics = {
                'Desert': ['Heat and sun exposure', 'Water planning', 'Navigation and communication'],
                'Snow': ['Cold exposure', 'Weather and visibility', 'Traction and equipment'],
                'Mountains': ['Altitude awareness', 'Trail and weather planning', 'Remote communication'],
                'Forest': ['Navigation', 'Bites and stings', 'Weather and shelter'],
                'Beach': ['Water safety', 'Sun exposure', 'Tides and local conditions'],
            }
            for environment, expected in topics.items():
                page.locator(f'input[value="{environment}"]').check()
                expect(page.locator('#topics-list li')).to_have_text(expected)
                expect(page.locator('#prepare-trip')).to_be_disabled()
                expect(page.locator('#trip-status')).to_contain_text('Nothing has been downloaded or saved')
            navigate('chat')
            navigate('trip')
            expect(page.locator('#destination')).to_have_value('Fictional test destination')
            expect(page.locator('input[value="Beach"]')).to_be_checked()

        check('Trip all five environments, exact topics, navigation retention, unavailable preparation/no fake downloads', trip)

        def profile():
            navigate('profile')
            for field, value in PROFILE.items():
                expect(page.locator(f'#profile-{field}')).to_have_value(value)
            page.locator('#profile-edit').click()
            edited = {key: ('38' if key == 'age' else value + ' edited') for key, value in PROFILE.items()}
            profile_save(edited)
            navigate('chat')
            navigate('profile')
            for field, value in edited.items():
                expect(page.locator(f'#profile-{field}')).to_have_value(value)
            require(page.evaluate('localStorage.length === 0 && sessionStorage.length === 0'), 'Profile in web storage')
            page.locator('#profile-clear').click()
            expect(page.locator('#profile-summary')).to_contain_text('Profile removed')
            for field in PROFILE:
                expect(page.locator(f'#profile-{field}')).to_have_value('')
                require(not page.locator(f'#profile-{field}').evaluate('(el) => el.readOnly'), field)
            profile_save(PROFILE)
            page.reload()
            navigate('profile')
            for field in PROFILE:
                expect(page.locator(f'#profile-{field}')).to_have_value('')

        check('All six profile fields save/edit/remove, retention on navigation, memory-only reset on reload', profile)

        def navigation_emergency_chat():
            navigate('chat')
            before = count('/api/ask')
            for button in page.locator('[data-question]').all():
                button.click()
                expect(page.locator('#question')).to_have_value(button.get_attribute('data-question'))
                expect(page.locator('#question')).to_be_focused()
            require(count('/api/ask') == before, 'Starter automatically sent a question')
            page.locator('#trip-shortcut').click()
            expect(page.locator('#screen-trip')).to_be_visible()
            navigate('chat')
            page.once('dialog', lambda dialog: dialog.dismiss())
            page.locator('#clear-chat').click()
            require(page.locator('#question').input_value(), 'Cancel cleared draft')
            page.once('dialog', lambda dialog: dialog.accept())
            page.locator('#clear-chat').click()
            expect(page.locator('#question')).to_have_value('')
            expect(page.locator('.message')).to_have_count(0)
            expect(page.locator('#welcome')).to_be_visible()
            for close in ('button', 'escape'):
                page.locator('#emergency-open').click()
                expect(page.locator('#emergency-dialog')).to_be_visible()
                expect(page.locator('#emergency-dialog a')).to_have_attribute('href', 'tel:911')
                expect(page.locator('#emergency-dialog')).to_contain_text('does not place calls automatically')
                if close == 'button':
                    page.locator('#emergency-close').click()
                else:
                    page.keyboard.press('Escape')
                expect(page.locator('#emergency-dialog')).not_to_be_visible()
            page.locator('#sidebar-toggle').click()
            expect(page.locator('#sidebar-toggle')).to_have_attribute('aria-expanded', 'false')
            navigate('trip')
            page.locator('#sidebar-toggle').click()
            expect(page.locator('#sidebar-toggle')).to_have_attribute('aria-expanded', 'true')

        check('Navigation, starter drafts/no auto-send, trip shortcut, new-chat cancel/clear, emergency close/Escape, sidebar', navigation_emergency_chat)

        def responsive():
            for width in (320, 390, 768, 1440):
                page.set_viewport_size({'width': width, 'height': 1000 if width == 1440 else 844})
                for screen in ('chat', 'trip', 'profile'):
                    navigate(screen)
                    sizes = page.evaluate('''() => ({width: innerWidth,
                        document: document.documentElement.scrollWidth, body: document.body.scrollWidth})''')
                    require(sizes['document'] <= width and sizes['body'] <= width, {screen: sizes})
                for dialog in ('emergency', 'status'):
                    page.locator(f'#{dialog}-open').click()
                    expect(page.locator(f'#{dialog}-dialog')).to_be_visible()
                    bounds = page.locator(f'#{dialog}-dialog').bounding_box()
                    require(bounds and bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width, bounds)
                    require(page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Dialog overflow')
                    page.keyboard.press('Escape')
            require(page.evaluate('matchMedia("(prefers-reduced-motion: reduce)").matches'), 'Motion preference absent')
            for selector in ('body', '.chat-panel', '.connection-state', 'dialog'):
                style = page.locator(selector).first.evaluate('''el => {
                    const s = getComputedStyle(el);
                    return [s.transitionDuration, s.animationName, s.scrollBehavior];
                }''')
                require(style == ['0s', 'none', 'auto'], {selector: style})

        check('Responsive 320/390/768/1440 all screens/dialogs, reduced-motion transitions/animations/scroll', responsive)
        check('No unexpected API/external requests or downloads', lambda: require(
            not unknown and not external and not downloads,
            {'unknown': unknown, 'external': external, 'downloads': downloads}))
        check('No uncaught JS errors or unhandled promise rejections', lambda: require(
            not errors and not page.evaluate('window.fixtureUnhandled'),
            {'page_errors': errors, 'unhandled': page.evaluate('window.fixtureUnhandled')}))
        browser.close()

    report = {'passed': len(passed), 'failed': len(failed), 'failures': failed,
              'skipped': skipped, 'screenshots': screenshots,
              'live_status_responses': live['status'], 'live_ask_responses': live['ask'],
              'fixture_api_requests': sum(call['fixture'] for call in calls),
              'ask_payloads': payloads,
              'note': 'All successful answers are intercepted nonmedical fixtures. No live ready-model ask is permitted.'}
    print(json.dumps(report, indent=2), flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
