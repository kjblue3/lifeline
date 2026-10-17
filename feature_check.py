"""Browser feature regression checks, using nonmedical fixtures only.

Run: .venv/bin/python feature_check.py localhost8000
Only static files reach the existing server. ALL browser API requests are intercepted;
unknown requests are blocked. No live model, backend startup, or real microphone is used.
Chromium's fake media device exercises MediaRecorder/Blob capture, NOT real hardware or
speech recognition. The explicitly TEST-only local adapter supplies a fixed transcript.
The offline check installs a fresh v6 worker online, closes the page, then reopens and
reloads in the SAME browser context offline so its installed cache survives.
"""

import argparse
import copy
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


STATUS = {
    'mode': 'unavailable',
    'local': {'configured': False, 'ready': False, 'model': 'TEST fixture only',
              'message': 'TEST fixture: no inference connected'},
    'references': {'installed': False, 'count': 0}, 'offline_ready': False,
}
NOTICE = 'TEST FIXTURE ONLY: nonmedical shapes, not model output or guidance.'
ANSWER = 'Fixture blue shape one\n\n2. Fixture green shape two\n003 Fixture circle only'
REPLY = {'answer': ANSWER, 'mode': 'local', 'simulated': False,
         'sources': [], 'notice': NOTICE}
RECORD = {
    'title': 'TEST FIXTURE: Square', 'content': 'Fixture square only',
    'category': 'Fixture shapes', 'completed': True, 'verified': True,
    'locally_available': True,
    'source': {'title': 'TEST fixture source', 'organisation': 'TEST fixture organisation',
               'url': 'https://example.invalid/fixture-square'},
    'warnings': ['TEST FIXTURE ONLY: nonmedical shapes, not guidance.'],
    'published': '2026-01-02', 'updated': '2026-02-03', 'reviewed': '2026-03-04',
}

# Wrap the real Chromium fake-device stream; retain tracks to verify cleanup. This
# never replaces MediaRecorder: successful captures must produce a nonempty Blob.
MEDIA_SPY = """(() => {
  window.testMedia = {calls: 0, streams: [], mode: 'normal', blobs: []};
  window.testUnhandled = [];
  addEventListener('unhandledrejection', e => testUnhandled.push(String(e.reason)));
  if (!navigator.mediaDevices) return;
  const native = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getUserMedia = async constraints => {
    testMedia.calls++;
    if (testMedia.mode === 'denied') throw new DOMException('TEST denial', 'NotAllowedError');
    if (testMedia.mode === 'error') throw new DOMException('TEST unavailable', 'NotFoundError');
    const stream = await native(constraints);
    testMedia.streams.push(stream);
    if (testMedia.mode === 'pending') await new Promise(r => testMedia.release = r);
    return stream;
  };
})();"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', nargs='?', default='localhost8000')
    args = parser.parse_args()
    base = ('http://localhost:8000' if args.target == 'localhost8000' else
            args.target if '://' in args.target else 'http://' + args.target).rstrip('/')
    origin = urlsplit(base)
    if origin.hostname not in ('localhost', '127.0.0.1', '::1') or origin.port != 8000:
        parser.error('Use the existing loopback server on port 8000 only.')
    artifacts = Path(__file__).resolve().parent / 'artifacts'
    if not artifacts.is_dir():
        parser.error('Existing artifacts directory is required.')
    results, calls, blocked, errors = [], [], [], []
    state = {'status': copy.deepcopy(STATUS), 'failure': False,
             'reply': copy.deepcopy(REPLY), 'offline': False}

    def require(value, message):
        if not value:
            raise AssertionError(message)

    def check(name, action):
        try:
            action()
        except Exception as exc:
            results.append({'test': name, 'pass': False, 'error': str(exc)})
            print(f'FAIL {name}: {exc}', flush=True)
        else:
            results.append({'test': name, 'pass': True})
            print(f'PASS {name}', flush=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--use-fake-device-for-media-stream',
                                          '--use-fake-ui-for-media-stream'])

        def guard(route):
            request = route.request
            url = urlsplit(request.url)
            same = (url.scheme, url.netloc) == (origin.scheme, origin.netloc)
            if url.path == '/api' or url.path.startswith('/api/'):
                calls.append({'path': url.path, 'method': request.method,
                              'body': request.post_data, 'offline': state['offline']})
                if not same or state['offline']:
                    route.abort()
                elif url.path == '/api/status' and request.method == 'GET':
                    if state['failure']:
                        route.fulfill(status=503, json={'ok': False, 'error': {'message': 'TEST status failure'}})
                    else:
                        route.fulfill(json={'ok': True, 'data': state['status']})
                elif url.path == '/api/ask' and request.method == 'POST':
                    route.fulfill(json={'ok': True, 'data': state['reply']})
                else:
                    blocked.append(request.url)
                    route.abort()
            elif same and request.method == 'GET' and (url.path == '/' or
                    url.path.startswith('/assets/') or url.path == '/favicon.ico'):
                route.continue_()
            else:
                blocked.append(request.url)
                route.abort()

        def context(workers='block'):
            ctx = browser.new_context(viewport={'width': 1440, 'height': 1000},
                                      permissions=['microphone'], reduced_motion='reduce',
                                      service_workers=workers)
            ctx.route('**/*', guard)
            ctx.add_init_script(MEDIA_SPY)
            ctx.on('page', lambda p: p.on('pageerror', lambda e: errors.append(str(e))))
            return ctx

        ctx = context()
        page = ctx.new_page()
        page.set_default_timeout(6000)
        page.goto(base + '/')
        page.wait_for_function('window.LifeLineVoice && window.LifeLineLibrary')

        def nav(name):
            page.locator(f'[data-screen="{name}"]').click()
            expect(page.locator(f'#screen-{name}')).to_be_visible()
            expect(page.locator(f'[data-screen="{name}"]')).to_have_attribute('aria-current', 'page')
            for other in ('chat', 'library', 'prepared', 'profile'):
                if name != other:
                    expect(page.locator(f'#screen-{other}')).to_be_hidden()

        def refresh():
            page.evaluate("document.querySelector('#refresh-status').click()")
            expect(page.locator('#refresh-status')).to_be_enabled()

        def asks():
            return sum(c['path'] == '/api/ask' for c in calls)

        def records(values):
            return page.evaluate('values => LifeLineLibrary.setRecords(values)', values)

        def shot(name):
            page.screenshot(path=str(artifacts / name), full_page=True)

        def status_checks():
            nav('library')
            expect(page.locator('#library-status')).to_have_text('First-aid library is not installed yet')
            expect(page.locator('.library-card')).to_have_count(0)
            state['status']['references'] = {'installed': True, 'count': 100}
            refresh()
            expect(page.locator('#library-status')).to_contain_text('100 indexed topics reported.')
            expect(page.locator('#library-status')).to_contain_text('browsing is not connected yet')
            expect(page.locator('.library-card')).to_have_count(0)
            state['failure'] = True
            refresh()
            expect(page.locator('#library-status')).to_have_text('First-aid library status is unknown.')
            expect(page.locator('#references-state')).to_have_text('Not verified')
            require('100' not in page.locator('#library-status').inner_text(), 'Stale count remained')
            state['failure'] = False
            refresh()

        check('Status: absent, indexed-not-browsable, failure clears stale state', status_checks)

        def library_checks():
            nav('library')
            invalid = []
            for field, value in [('verified', False), ('completed', False),
                                 ('locally_available', False), ('content', '')]:
                item = copy.deepcopy(RECORD)
                item[field] = value
                invalid.append(item)
            missing = copy.deepcopy(RECORD)
            del missing['content']
            invalid.append(missing)
            for url in ('javascript:alert(1)', 'data:text/html,x', 'https://u:p@example.invalid', 'not a url'):
                item = copy.deepcopy(RECORD)
                item['source']['url'] = url
                invalid.append(item)
            require(records(invalid) == 0, 'Invalid records crossed boundary')
            second = copy.deepcopy(RECORD)
            second.update(title='TEST FIXTURE: Circle', content='Fixture circle only', category='Fixture circles')
            require(records([RECORD, second] + invalid) == 2, 'Expected only two valid records')
            before = len(calls)
            page.get_by_role('button', name='Fixture circles', exact=True).click()
            expect(page.locator('.library-card')).to_have_count(1)
            expect(page.locator('.library-card h2')).to_have_text('TEST FIXTURE: Circle')
            page.get_by_role('button', name='All articles', exact=True).click()
            page.locator('#library-search').fill('square only')
            expect(page.locator('.library-card')).to_have_count(1)
            page.locator('#library-search').fill('fixture no matches purple')
            expect(page.locator('#library-empty')).to_have_text('No matching medical information found')
            page.locator('#library-search').fill('square')
            page.get_by_role('button', name='Read article: TEST FIXTURE: Square', exact=True).click()
            article = page.locator('#library-article')
            for text in ('Fixture square only', 'TEST fixture source', 'TEST fixture organisation',
                         '2026-01-02', '2026-02-03', '2026-03-04', 'nonmedical shapes'):
                expect(article).to_contain_text(text)
            expect(article.locator('a')).to_have_attribute('href', RECORD['source']['url'])
            require(len(calls) == before, 'Local filtering/detail performed an API call')
            shot('lifeline-library.png')
            page.locator('#library-back').click()
            expect(page.get_by_role('button', name='Read article: TEST FIXTURE: Square', exact=True)).to_be_focused()
            nav('chat')
            nav('library')
            # A plausible stored index must not become completed articles on reload.
            page.evaluate("localStorage.setItem('lifeline-library-index', JSON.stringify({count:100,records:[{title:'TEST stale index'}]}))")
            page.reload()
            expect(page.locator('.library-card')).to_have_count(0)
            expect(page.locator('#library-search')).to_be_disabled()
            expect(page.locator('#library-empty')).to_contain_text('No completed')

        check('Library: explicit records, validation, local filters/detail/back, stored index insufficient', library_checks)

        def send(reply):
            state['reply'] = copy.deepcopy(reply)
            nav('chat')
            page.locator('#question').fill('TEST fixture request: shapes only, nonmedical')
            page.locator('#send-button').click()
            expect(page.locator('#question')).to_have_value('')
            expect(page.locator('#question')).not_to_have_attribute('readonly', '')
            expect(page.locator('#ai-loading')).to_be_hidden()
            return page.locator('.message.assistant').last

        def plain_response():
            reply = send(REPLY)
            expect(reply.locator(':scope > p').first).to_have_text(ANSWER, use_inner_text=False)
            require(reply.locator(':scope > p').first.text_content() == ANSWER, 'Answer text altered')
            require(reply.locator(':scope > p').first.evaluate("e => getComputedStyle(e).whiteSpace") in
                    ('pre-wrap', 'pre-line', 'break-spaces'), 'Paragraph whitespace not preserved visually')
            expect(reply.locator('.response-steps')).to_have_count(0)
            expect(reply.locator('.source-list')).to_have_count(0)

        check('Response: actual unstructured text and numbering preserved, no guessed steps/citations', plain_response)

        def structured_response():
            for change in ({'verified': False}, {'source_ids': ['unknown']},
                           {'source_verified': False}, {'source_local': False}):
                data = copy.deepcopy(REPLY)
                source = {'id': 'fixture', 'verified': change.get('source_verified', True),
                          'locally_available': change.get('source_local', True)}
                step = {'number': 7, 'instruction': 'Fixture blue shape one', 'verified': True,
                        'source_ids': ['fixture']}
                step.update({k: v for k, v in change.items() if k in ('verified', 'source_ids')})
                data.update(sources=[source], steps=[step])
                expect(send(data).locator('.response-steps')).to_have_count(0)
            data = copy.deepcopy(REPLY)
            data.update(heading='TEST FIXTURE ONLY: Nonmedical shapes',
                        sources=[{'id': 'fixture', 'title': 'TEST fixture source',
                                  'url': 'https://example.invalid/fixture', 'verified': True,
                                  'locally_available': True}],
                        steps=[{'number': 7, 'instruction': 'Fixture blue shape one <b>literal</b>',
                                'verified': True, 'source_ids': ['fixture']},
                               {'number': 12, 'instruction': 'Fixture square only',
                                'verified': True, 'source_ids': ['fixture']}],
                        warnings=[{'text': 'TEST FIXTURE WARNING: <img src=x onerror=alert(1)> shapes only',
                                   'verified': True, 'source_ids': ['fixture']}])
            reply = send(data)
            expect(reply.locator('summary')).to_have_text(['Step 7', 'Step 12'])
            expect(reply.locator('details').first).to_have_attribute('open', '')
            reply.locator('summary').last.click()
            expect(reply.locator('details').last).to_have_attribute('open', '')
            expect(reply.locator('img, script, b')).to_have_count(0)
            expect(reply.locator('.response-warnings')).to_contain_text('<img src=x')
            require(reply.locator('.response-warnings').evaluate(
                "e => e.compareDocumentPosition(e.parentNode.querySelector('.response-steps')) & Node.DOCUMENT_POSITION_FOLLOWING"),
                'Warnings should precede steps')
            require(reply.locator('.response-warnings').evaluate(
                "e => parseFloat(getComputedStyle(e).borderLeftWidth) >= 3"), 'Warnings lack visual prominence')
            expect(reply.locator('.source-list a')).to_have_count(1)
            shot('lifeline-steps-fixture.png')

        check('Response: verified source gating, actual step numbers/details, prominent safe warnings', structured_response)

        def configure():
            require(page.evaluate("""() => LifeLineVoice.configure({
              name: 'TEST FIXTURE adapter, NOT speech recognition', localOnly:true, ready:true,
              async transcribe(blob) {
                testMedia.blobs.push({isBlob:blob instanceof Blob,size:blob.size,type:blob.type});
                if (testMedia.transcribeError) throw Error('TEST transcription unavailable');
                return {text:testMedia.text || 'Fixture blue shape one'};
              }
            })"""), 'TEST local adapter not available')

        def all_stopped():
            page.wait_for_function("testMedia.streams.every(s => s.getTracks().every(t => t.readyState === 'ended'))")

        def capture():
            page.locator('#voice-start').click()
            expect(page.locator('#voice-dialog')).to_have_attribute('data-listening', 'true')
            page.wait_for_timeout(350)
            page.locator('#voice-stop').click()
            expect(page.locator('#voice-review')).to_be_visible()
            all_stopped()

        def default_voice():
            nav('chat')
            page.locator('#question').fill('TEST manual draft')
            before = len(calls)
            page.locator('#voice-open').click()
            expect(page.locator('#voice-status')).to_have_text('Offline voice input is not ready yet.')
            expect(page.locator('#voice-start')).to_be_disabled()
            page.wait_for_timeout(100)
            require(page.evaluate('testMedia.calls') == 0, 'Default voice requested microphone')
            require(len(calls) == before, 'Default voice requested network')
            shot('lifeline-voice.png')
            page.locator('#voice-close').click()
            page.locator('#question').fill('TEST manual draft still editable')
            for value in ({'localOnly': False, 'ready': True}, {'localOnly': True, 'ready': False}):
                require(not page.evaluate('(v) => LifeLineVoice.configure({...v, transcribe:async()=>({text:"Fixture"})})', value),
                        'Unready/nonlocal adapter accepted')

        check('Voice default: not ready, no microphone/network, disabled start, typing unaffected', default_voice)

        def voice_capture():
            configure()
            page.locator('#question').fill('TEST manual draft')
            count = asks()
            before = len(calls)
            page.locator('#voice-open').click()
            capture()
            expect(page.locator('#question')).to_have_value('TEST manual draft')
            expect(page.locator('#voice-transcript')).to_have_text('Fixture blue shape one')
            blobs = page.evaluate('testMedia.blobs')
            require(blobs and all(b['isBlob'] and b['size'] > 0 for b in blobs), 'No captured Blob reached TEST adapter')
            require(len(calls) == before and asks() == count, 'Capture/transcription sent network request')
            page.locator('#voice-insert').click()
            expect(page.locator('#question')).to_have_value('TEST manual draft\nFixture blue shape one')
            require(asks() == count, 'Transcript automatically submitted')

        check('Voice: Chromium fake-device MediaRecorder Blob to TEST-only adapter, manual append/no submit', voice_capture)

        def voice_cleanup():
            configure()
            count = asks()
            for button in ('#voice-cancel', '#voice-close'):
                page.locator('#voice-open').click()
                page.locator('#voice-start').click()
                expect(page.locator('#voice-dialog')).to_have_attribute('data-listening', 'true')
                require(page.locator('#voice-status').evaluate("e=>getComputedStyle(e).animationName") == 'none',
                        'Reduced motion still pulses')
                page.evaluate("document.querySelector('#chat-form').requestSubmit()")
                require(asks() == count, 'Active recording submitted chat')
                page.locator(button).click()
                all_stopped()
                if button == '#voice-cancel':
                    page.locator('#voice-close').click()
            page.evaluate("testMedia.mode='pending'")
            page.locator('#voice-open').click()
            page.locator('#voice-start').click()
            page.wait_for_function('typeof testMedia.release === "function"')
            page.locator('#voice-close').click()
            page.evaluate("testMedia.release(); testMedia.mode='normal'")
            all_stopped()
            require(not page.evaluate('LifeLineVoice.active'), 'Permission race restarted recording')

        check('Voice: active-submit guard, reduced motion, cancel/close tracks, pending-permission race', voice_cleanup)

        def voice_errors():
            for mode, message in (
                ('denied', 'Microphone access is disabled. You can still type your question'),
                ('error', 'Microphone recording is unavailable. You can still type your question.')):
                page.evaluate('(mode) => testMedia.mode=mode', mode)
                page.locator('#voice-open').click()
                page.locator('#voice-start').click()
                expect(page.locator('#voice-status')).to_have_text(message)
                expect(page.locator('#voice-permission')).to_have_text(message)
                page.locator('#voice-close').click()
            page.evaluate("testMedia.mode='normal'; testMedia.transcribeError=true")
            page.locator('#voice-open').click()
            page.locator('#voice-start').click()
            expect(page.locator('#voice-dialog')).to_have_attribute('data-listening', 'true')
            page.wait_for_timeout(350)
            page.locator('#voice-stop').click()
            expect(page.locator('#voice-status')).to_have_text('Local transcription is unavailable. You can still type your question.')
            all_stopped()
            page.locator('#voice-close').click()
            page.evaluate('testMedia.transcribeError=false')
            # Hide the browser capture API to exercise availability detection.
            page.evaluate("window.testSavedRecorder=MediaRecorder; window.MediaRecorder=undefined")
            require(not page.evaluate("LifeLineVoice.configure({localOnly:true,ready:true,transcribe:async()=>({text:'Fixture'})})"),
                    'Missing capture API reported ready')
            page.locator('#voice-open').click()
            expect(page.locator('#voice-start')).to_be_disabled()
            page.locator('#voice-close').click()
            page.evaluate('() => { window.MediaRecorder=testSavedRecorder; }')
            configure()

        check('Voice: exact denied message, capture/transcription failure, unavailable browser API fallback', voice_errors)

        def voice_busy_length():
            page.locator('#question').fill('TEST draft')
            page.locator('#voice-open').click()
            page.evaluate("document.querySelector('#question').readOnly=true")
            expect(page.locator('#voice-start')).to_be_disabled()
            page.evaluate("document.querySelector('#question').readOnly=false")
            capture()
            page.evaluate("document.querySelector('#question').readOnly=true")
            expect(page.locator('#voice-insert')).to_be_disabled()
            page.evaluate("document.querySelector('#question').readOnly=false; document.querySelector('#question').value='x'.repeat(2000)")
            page.locator('#voice-insert').click()
            expect(page.locator('#voice-status')).to_contain_text('exceed the question length limit')
            require(len(page.locator('#question').input_value()) == 2000, 'Length guard changed draft')
            page.locator('#voice-close').click()
            page.locator('#question').fill('TEST editable draft')
            page.locator('#voice-open').click()
            page.locator('#voice-start').click()
            expect(page.locator('#voice-dialog')).to_have_attribute('data-listening', 'true')
            page.evaluate("document.querySelector('#question').readOnly=true")
            all_stopped()
            page.wait_for_function('!LifeLineVoice.active')
            page.evaluate("document.querySelector('#question').readOnly=false")
            page.locator('#voice-close').click()

        check('Voice: busy/readOnly start/insert/capture cancellation, transcript length guard', voice_busy_length)

        def regression():
            # Close any dialog left by a failed check; retain failures in the report.
            page.evaluate("document.querySelectorAll('dialog[open]').forEach(d=>d.close())")
            before = asks()
            for name in ('chat', 'library', 'prepared', 'profile'):
                nav(name)
            page.locator('#profile-name').fill('TEST Fictional Shape')
            page.locator('#profile-save').click()
            expect(page.locator('#profile-summary')).to_contain_text('memory only')
            page.locator('#profile-clear').click()
            nav('prepared')
            expect(page.locator('#prepared-items > li')).to_have_count(12)
            page.locator('#prepared-form button[type=submit]').click()
            expect(page.locator('#prepared-summary')).not_to_be_empty()
            for opener, title in (('#sign-in-open', 'Sign In'), ('#sign-up-open', 'Sign Up')):
                page.locator(opener).click()
                expect(page.locator('#account-title')).to_have_text(title)
                page.locator('#account-email').fill('fixture@example.invalid')
                page.locator('#account-password').fill('TEST-fictional-only')
                page.locator('#account-submit').click()
                expect(page.locator('#account-feedback')).to_contain_text('no account was created')
                expect(page.locator('#account-password')).to_have_value('')
                page.locator('#account-close').click()
            page.locator('#emergency-open').click()
            expect(page.locator('#emergency-dialog a')).to_have_attribute('href', 'tel:911')
            expect(page.locator('#emergency-dialog')).to_contain_text('does not place calls automatically')
            page.locator('#emergency-library').click()
            expect(page.locator('#screen-library')).to_be_visible()
            expect(page.locator('#emergency-dialog')).to_be_hidden()
            require(asks() == before, 'Navigation/demo features invoked inference')

        check('Regression: all four navigation destinations, profile/account/prepared/emergency/library shortcut', regression)

        def layouts():
            violations = []
            for width in (320, 390, 768, 1440):
                page.set_viewport_size({'width': width, 'height': 1000})
                for name in ('chat', 'library', 'prepared', 'profile'):
                    nav(name)
                    require(page.evaluate('document.documentElement.scrollWidth <= innerWidth'),
                            f'{width}px {name}: horizontal overflow')
                    bad = page.evaluate("""() => [...document.querySelectorAll('button, a[data-screen], summary')]
                      .filter(e=>e.getClientRects().length && !e.disabled && !e.closest('[hidden]'))
                      .flatMap(e=>{
                        const r=e.getBoundingClientRect();
                        const label=e.getAttribute('aria-label')||e.textContent.trim();
                        return (!label || r.height<43.5 || r.width<43.5) ?
                          [{id:e.id||label,width:r.width,height:r.height,label}] : [];
                      })""")
                    if bad:
                        violations.append({'width': width, 'screen': name, 'targets': bad})
                nav('chat')
                # Programmatic focus after mouse clicks does not imply keyboard
                # modality in Chromium. Enter keyboard modality before checking CSS.
                page.keyboard.press('Tab')
                page.locator('#voice-open').focus()
                require(page.locator('#voice-open').evaluate(
                    "e=>e.matches(':focus-visible') && getComputedStyle(e).outlineStyle !== 'none'"),
                    f'{width}px missing visible keyboard focus')
            require(not violations, '44px/label violations: ' + json.dumps(violations))

        check('Responsive/a11y: 320/390/768/1440, no overflow, labels, 44px controls, keyboard focus', layouts)
        check('Main context: no JS exceptions or unhandled promises', lambda: require(
            not errors and not page.evaluate('testUnhandled'), str(errors) + str(page.evaluate('testUnhandled'))))
        ctx.close()

        def offline():
            state['offline'] = False
            state['failure'] = False
            offline_ctx = context('allow')
            try:
                online = offline_ctx.new_page()
                online.goto(base + '/assets/index.html')
                try:
                    online.wait_for_function("navigator.serviceWorker.controller !== null", timeout=15000)
                except Exception as exc:
                    diagnostics = online.evaluate("""async () => {
                      const paths=['/assets/sw.js','/assets/icons/lifeline.svg'];
                      const assets=await Promise.all(paths.map(async path=>{
                        const r=await fetch(path);return {path,status:r.status};
                      }));
                      const registrations=await navigator.serviceWorker.getRegistrations();
                      return {assets,workers:registrations.map(r=>({scope:r.scope,
                        active:r.active?.state,waiting:r.waiting?.state,installing:r.installing?.state}))};
                    }""")
                    raise AssertionError('Fresh v6 worker did not activate; offline reopen/checklist checks blocked. '
                                         + json.dumps(diagnostics)) from exc
                cached = online.evaluate("""async () => {
                    const names=await caches.keys();
                    const c=await caches.open('lifeline-shell-v6');
                    return {names,urls:(await c.keys()).map(r=>new URL(r.url).pathname)};
                }""")
                require('lifeline-shell-v6' in cached['names'], 'Fresh v6 cache missing')
                scripts = online.locator('script[src]').evaluate_all('(els)=>els.map(e=>new URL(e.src).pathname)')
                for script in scripts:
                    require(script in cached['urls'], 'Uncached script: ' + script)
                require(not any('/api/' in u for u in cached['urls']), 'API cached in shell')
                online.close()
                state['offline'] = True
                offline_ctx.set_offline(True)
                off = offline_ctx.new_page()
                off.goto(base + '/assets/index.html')
                off.reload()
                off.wait_for_function('window.LifeLineLibrary && window.LifeLineVoice && window.LifeLineResponse && window.LifeLinePreparednessLibrary')
                off.locator('[data-screen=library]').click()
                expect(off.locator('#library-empty')).to_contain_text('No completed')
                expect(off.locator('.library-card')).to_have_count(0)
                expect(off.locator('#library-status')).to_have_text('First-aid library status is unknown.')
                off.locator('[data-screen=prepared]').click()
                expect(off.locator('#prepared-items > li')).to_have_count(12)
                off.locator('#prepared-items input').first.check()
                expect(off.locator('#prepared-count')).to_contain_text('1 of 12')
                off.locator('[data-screen=chat]').click()
                expect(off.locator('.message.assistant')).to_have_count(0)
                expect(off.locator('#connection-label')).to_have_text('Unable to Check AI Status')
                require(not errors and not off.evaluate('testUnhandled'), 'Offline JavaScript errors: ' + str(errors))
                # Exercise fetch policy: status must fail offline, not return an old fixture.
                require(off.evaluate("async()=>{try {await fetch('/api/status');return false;}catch{return true;}}"),
                        'API was served from cache offline')
                final_urls = off.evaluate("async()=>{const c=await caches.open('lifeline-shell-v6');return (await c.keys()).map(r=>r.url)}")
                require(not any('/api/' in u for u in final_urls), 'API entered cache')
                print('INFO fresh v6 cached scripts: ' + ', '.join(scripts), flush=True)
            finally:
                offline_ctx.close()
                state['offline'] = False

        check('PWA: fresh online v6 install, close/reopen/reload offline, working scripts/checklist, empty library, no API cache', offline)
        check('Isolation: no unexpected network or non-fixture inference payloads', lambda: require(
            not blocked and all(c['body'] and json.loads(c['body']) ==
                {'question': 'TEST fixture request: shapes only, nonmedical'}
                for c in calls if c['path'] == '/api/ask'),
            'Unexpected network/payload: ' + str(blocked)))
        browser.close()

    failed = [r for r in results if not r['pass']]
    print(json.dumps({'passed': len(results) - len(failed), 'failed': failed,
                      'intercepted_api_calls': len(calls),
                      'live_inference_calls': 0,
                      'microphone': 'Chromium fake-device capture only; TEST adapter, no real device or ASR',
                      'screenshots': [str(artifacts / n) for n in
                          ('lifeline-library.png', 'lifeline-voice.png', 'lifeline-steps-fixture.png')]}, indent=2))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
