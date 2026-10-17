"""Browser-only preparedness checks. All API and external requests are intercepted.

Run: .venv/bin/python preparedness_check.py http://localhost:8000
The bundled NPS source attribution is checked, not clinical validity.
"""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

from frontend_check import PROFILE, STATUS


KEY = 'lifeline.preparedness.v1'
VERSION = 'nps-ten-essentials-2026-05-28-v1'
IDS = ['navigation', 'sun', 'layers', 'light', 'first-aid', 'repair',
       'food', 'water', 'shelter', 'life-jacket', 'insects', 'communication']
STATIC = {'/', '/assets/styles.css', '/assets/api.js', '/assets/app.js',
          '/assets/preparedness-library.js', '/assets/preparedness.js', '/favicon.ico',
          '/assets/medical-library.js', '/assets/voice.js', '/assets/response.js',
          '/assets/pwa.js', '/assets/manifest.webmanifest', '/assets/icons/lifeline.svg'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', nargs='?', default='http://localhost:8000')
    args = parser.parse_args()
    base = args.base.rstrip('/')
    origin = urlsplit(base)
    if origin.hostname not in ('localhost', '127.0.0.1', '::1'):
        parser.error('Only loopback static servers are allowed')
    Path('artifacts').mkdir(exist_ok=True)
    passed, failures, screenshots = [], [], []
    requests, blocked_external, unexpected, errors = [], [], [], []
    state = {'backend': 'unavailable', 'external': 'abort'}

    def require(condition, detail):
        if not condition:
            raise AssertionError(detail)

    def check(name, action):
        try:
            action()
        except Exception as exc:
            failures.append({'test': name, 'error': f'{type(exc).__name__}: {exc}'})
            print(f'FAIL: {name}\n{exc}', flush=True)
        else:
            passed.append(name)
            print(f'PASS: {name}', flush=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={'width': 1440, 'height': 1000},
                                      reduced_motion='reduce', service_workers='block')
        context.add_init_script('''window.testUnhandled = [];
            addEventListener('unhandledrejection', e => testUnhandled.push(String(e.reason)));''')

        def guard(route):
            request = route.request
            url = urlsplit(request.url)
            requests.append({'url': request.url, 'method': request.method})
            if url[:2] != origin[:2]:
                blocked_external.append(request.url)
                if state['external'] == '503':
                    route.fulfill(status=503, body='EXTERNAL BLOCKED TEST FIXTURE')
                else:
                    route.abort()
            elif url.path == '/api/status' and request.method == 'GET':
                if state['backend'] == 'abort':
                    route.abort()
                elif state['backend'] == '503':
                    route.fulfill(status=503, json={'ok': False, 'error': {'message': 'FIXTURE status unavailable'}})
                else:
                    route.fulfill(json={'ok': True, 'data': STATUS})
            elif request.method == 'GET' and url.path in STATIC:
                route.continue_()
            else:
                unexpected.append(request.url)
                route.abort()

        context.route('**/*', guard)
        page = context.new_page()
        page.set_default_timeout(5000)
        page.on('pageerror', lambda error: errors.append(str(error)))

        def navigate(screen):
            page.locator(f'[data-screen="{screen}"]').click()
            expect(page.locator(f'#screen-{screen}')).to_be_visible()

        def baseline():
            expect(page.locator('#screen-prepared')).to_be_visible()
            boxes = page.locator('#prepared-items input[type="checkbox"]')
            expect(boxes).to_have_count(12)
            require(boxes.evaluate_all('(els) => els.map(el => el.id)') ==
                    ['prepared-item-' + item for item in IDS], 'Baseline IDs changed')
            for row in page.locator('#prepared-items > li').all():
                expect(row).to_be_visible()
                require(row.locator('p').inner_text().strip(), 'Missing rationale')
                expect(row.get_by_role('button')).to_have_text('Source: NPS Ten Essentials')
            expect(page.locator('#prepared-source-detail')).to_have_text(
                'National Park Service: Ten Essentials. Last updated May 28, 2026. Accessed October 17, 2026.')
            link = page.locator('#prepared-source-link a')
            expect(link).to_have_attribute('href', 'https://www.nps.gov/articles/10essentials.htm')
            expect(link).to_have_attribute('target', '_blank')
            expect(link).to_have_attribute('rel', 'noopener noreferrer')
            expect(link).to_have_attribute('referrerpolicy', 'no-referrer')
            expect(page.locator('#prepared-source')).to_contain_text('not clinical verification')
            expect(page.get_by_role('button', name='Personalize with local AI')).to_be_disabled()

        def storage():
            return page.evaluate('Object.fromEntries(Object.entries(localStorage))')

        def load():
            response = page.goto(base + '/#prepared')
            require(response is not None and response.ok, 'Local document failed')
            baseline()

        def unavailable_baseline():
            load()
            expect(page.locator('#connection-label')).to_have_text('Local AI Not Ready')
            expect(page.locator('#references-state')).to_have_text('Not Installed')
            page.locator('#prepared-items button').first.click()
            expect(page.locator('#prepared-source')).to_be_focused()
            require(page.evaluate('location.hash') == '#prepared', 'Source changed screen hash')

        check('Bundled baseline12, per-item rationale/NPS source and limits, unavailable AI/library', unavailable_baseline)

        def planning():
            description = '<img src=x onerror="window.preparedXss=1"> & custom terrain'
            activity = '<script>window.preparedXss=1</script> walking'
            page.locator('#prepared-description').fill(description)
            page.locator('#prepared-activity').fill(activity)
            page.locator('#prepared-days').fill('7')
            for environment in ('Desert', 'Snow', 'Mountains', 'Forest', 'Beach'):
                page.locator(f'#prepared-form input[value="{environment}"]').check()
                page.locator('#prepared-form button[type="submit"]').click()
                expect(page.locator('#prepared-summary')).to_have_text(
                    f'Environment: {environment} ({description}). Activity: {activity}. Duration: 7 days. '
                    'Context only; the complete baseline checklist is unchanged. Choices are not saved.')
                baseline()
            expect(page.locator('#prepared-summary *')).to_have_count(0)
            require(page.evaluate('window.preparedXss === undefined'), 'Injected code executed')
            require(storage() == {}, 'Planning choices persisted')
            navigate('chat')
            navigate('profile')
            navigate('prepared')
            expect(page.locator('#prepared-description')).to_have_value(description)
            expect(page.locator('#prepared-activity')).to_have_value(activity)
            expect(page.locator('#prepared-days')).to_have_value('7')
            expect(page.locator('input[value="Beach"]')).to_be_checked()
            expect(page.locator('#prepared-summary')).to_contain_text(description)

        check('Custom environment/activity/duration summary literal text, all environments, navigation retention', planning)

        def invalid_duration():
            before = page.locator('#prepared-summary').inner_text()
            for value in ('', '0', '-1', '1.5', '366'):
                page.locator('#prepared-days').fill(value)
                require(not page.locator('#prepared-days').evaluate('el => el.checkValidity()'), value)
                page.locator('#prepared-form button[type="submit"]').click()
                expect(page.locator('#prepared-summary')).to_have_text(before)
                # Also verify the submit handler's guard without native browser validation.
                page.locator('#prepared-form').dispatch_event('submit')
                expect(page.locator('#prepared-summary')).to_have_text(before)
            for value, phrase in (('1', 'Duration: 1 day.'), ('365', 'Duration: 365 days.')):
                page.locator('#prepared-days').fill(value)
                page.locator('#prepared-form button[type="submit"]').click()
                expect(page.locator('#prepared-summary')).to_contain_text(phrase)

        check('Invalid empty/zero/negative/fractional/over365 duration rejected; valid boundaries', invalid_duration)

        def persistence():
            navigate('profile')
            for field, value in PROFILE.items():
                page.locator(f'#profile-{field}').fill(value)
            page.locator('#profile-save').click()
            navigate('prepared')
            for index, item in enumerate(IDS):
                page.locator('#prepared-item-' + item).check()
                expect(page.locator('#prepared-count')).to_have_text(f'{index + 1} of 12 packed')
                require(storage() == {}, 'Checkbox autosaved before explicit Save')
            navigate('chat')
            navigate('prepared')
            expect(page.locator('#prepared-items input:checked')).to_have_count(12)
            page.locator('#prepared-save').click()
            expect(page.locator('#prepared-storage-status')).to_contain_text('Progress saved on this browser')
            require(storage() == {KEY: json.dumps({'libraryVersion': VERSION, 'checked': IDS}, separators=(',', ':'))}, storage())
            page.locator('#prepared-item-navigation').uncheck()
            page.reload()
            baseline()
            expect(page.locator('#prepared-items input:checked')).to_have_count(12)
            expect(page.locator('#prepared-storage-status')).to_contain_text('Saved checkmarks restored')
            expect(page.locator('#prepared-description')).to_have_value('')
            expect(page.locator('#prepared-activity')).to_have_value('')
            expect(page.locator('#prepared-days')).to_have_value('1')
            expect(page.locator('#prepared-form input[name="environment"]:checked')).to_have_count(0)
            expect(page.locator('#prepared-summary')).to_have_text('Baseline checklist. No planning choices applied.')
            navigate('profile')
            for field in PROFILE:
                expect(page.locator(f'#profile-{field}')).to_have_value('')
            require(page.evaluate('sessionStorage.length') == 0, 'Session storage used')
            navigate('prepared')
            # Save all unchecked, then a subset, to exercise both boolean directions.
            for box in page.locator('#prepared-items input').all():
                box.uncheck()
            page.locator('#prepared-save').click()
            page.reload()
            expect(page.locator('#prepared-items input:checked')).to_have_count(0)
            page.locator('#prepared-item-water').check()
            page.locator('#prepared-save').click()
            page.reload()
            expect(page.locator('#prepared-items input:checked')).to_have_count(1)
            expect(page.locator('#prepared-item-water')).to_be_checked()
            require(json.loads(storage()[KEY]) == {'libraryVersion': VERSION, 'checked': ['water']}, storage())

        check('All checkboxes explicit save only IDs/version; reload restores saved state, not form/profile; subset and empty save', persistence)

        def clear():
            page.evaluate('localStorage.setItem("unrelated.fixture", "keep me")')
            before = storage()
            page.once('dialog', lambda dialog: dialog.dismiss())
            page.locator('#prepared-clear').click()
            require(storage() == before, 'Cancel removed data')
            page.once('dialog', lambda dialog: dialog.accept())
            page.locator('#prepared-clear').click()
            require(storage() == {'unrelated.fixture': 'keep me'}, storage())
            expect(page.locator('#prepared-item-water')).to_be_checked()
            expect(page.locator('#prepared-storage-status')).to_contain_text('Current checkmarks remain in memory')
            page.reload()
            expect(page.locator('#prepared-items input:checked')).to_have_count(0)
            require(storage() == {'unrelated.fixture': 'keep me'}, storage())

        check('Clear cancel/confirm removes only own key, preserves unrelated data and in-memory checks', clear)

        def corrupt_storage():
            valid = {'libraryVersion': VERSION, 'checked': ['water']}
            variants = ['{bad json', 'null', '[]', '42',
                        json.dumps(dict(valid, libraryVersion='old')),
                        json.dumps(dict(valid, checked=['unknown'])),
                        json.dumps(dict(valid, checked=['water', 'water'])),
                        json.dumps(dict(valid, checked='water')),
                        json.dumps(dict(valid, checked=[1])),
                        json.dumps(dict(valid, checked=IDS + ['water'])),
                        json.dumps(dict(valid, profile='must not restore')),
                        json.dumps({'checked': []})]
            for raw in variants:
                page.evaluate('([key, raw]) => localStorage.setItem(key, raw)', [KEY, raw])
                page.reload()
                baseline()
                expect(page.locator('#prepared-items input:checked')).to_have_count(0)
                expect(page.locator('#prepared-storage-status')).to_contain_text('could not be read or validated')
                require(storage()[KEY] == raw, 'Corrupt saved data silently overwritten')
            page.locator('#prepared-item-food').check()
            page.locator('#prepared-save').click()
            page.reload()
            expect(page.locator('#prepared-item-food')).to_be_checked()
            expect(page.locator('#prepared-storage-status')).to_contain_text('Saved checkmarks restored')

        check('Corrupt JSON/schema/version/IDs/duplicates safely rejected; explicit save recovers', corrupt_storage)

        def blocked_storage():
            before = storage()
            page.evaluate('''() => {
                window.originalStorage = Object.fromEntries(['getItem', 'setItem', 'removeItem'].map(
                    name => [name, Storage.prototype[name]]));
                for (const name of Object.keys(originalStorage)) Storage.prototype[name] = () => {
                    throw new DOMException('TEST blocked storage', 'SecurityError');
                };
            }''')
            try:
                page.locator('#prepared-item-water').check()
                page.locator('#prepared-save').click()
                expect(page.locator('#prepared-storage-status')).to_contain_text('Progress not saved')
                expect(page.locator('#prepared-item-water')).to_be_checked()
                page.once('dialog', lambda dialog: dialog.accept())
                page.locator('#prepared-clear').click()
                expect(page.locator('#prepared-storage-status')).to_contain_text('Could not remove saved progress')
            finally:
                page.evaluate('Object.assign(Storage.prototype, originalStorage)')
            require(storage() == before, 'Blocked save/clear altered earlier data')
            # Fresh document: deny storage before any bundled scripts execute.
            denied = context.new_page()
            denied.on('pageerror', lambda error: errors.append(str(error)))
            denied.add_init_script('''Storage.prototype.getItem = () => {
                throw new DOMException('TEST denied read', 'SecurityError');
            };''')
            try:
                denied.goto(base + '/#prepared')
                expect(denied.locator('#prepared-items input')).to_have_count(12)
                expect(denied.locator('#prepared-items input:checked')).to_have_count(0)
                expect(denied.locator('#prepared-storage-status')).to_contain_text('could not be read or validated')
            finally:
                denied.close()

        check('Blocked storage read/write/remove shows safe errors, baseline and memory checks survive', blocked_storage)

        def no_ai():
            before = len(requests)
            result = page.evaluate('''async () => {
                try { await LifeLineAPI.prepareSupplies(); return {resolved: true}; }
                catch (error) { return {resolved: false, message: error.message}; }
            }''')
            require(result == {'resolved': False, 'message':
                    'Local AI preparedness is not connected. Use the bundled supply checklist.'}, result)
            require(len(requests) == before, 'prepareSupplies made a network request')
            expect(page.get_by_role('button', name='Personalize with local AI')).to_be_disabled()
            page.get_by_role('button', name='Personalize with local AI').dispatch_event('click')
            require(len(requests) == before, 'Disabled AI button made a request')

        check('prepareSupplies rejects without network and AI button disabled/no request', no_ai)

        def loss_and_reload():
            # Not context.set_offline(): the localhost document/assets remain reachable.
            for backend in ('503', 'abort'):
                state['backend'] = backend
                state['external'] = backend
                for fresh in (False, True):
                    if fresh:
                        page.goto('about:blank')
                        load()
                    else:
                        page.reload()
                        baseline()
                    expect(page.locator('#connection-label')).to_have_text('Unable to Check AI Status')
                    require(page.evaluate('!!window.LifeLinePreparednessLibrary && !!window.LifeLineAPI'),
                            'Bundled scripts did not load')
                    # A deliberate probe verifies the external guard in both failure modes.
                    result = page.evaluate('''async () => {
                        try { return (await fetch('https://example.invalid/blocked-probe', {mode:'no-cors'})).status; }
                        catch { return 'aborted'; }
                    }''')
                    require(result in (0, 503) if backend == '503' else result == 'aborted', result)
                    baseline()
                    page.locator('#prepared-item-navigation').check()
                    page.locator('#prepared-save').click()
                    page.reload()
                    baseline()
                    expect(page.locator('#prepared-item-navigation')).to_be_checked()
            require(not unexpected, unexpected)

        check('Fresh load/reload with external 503/abort and separate backend 503/abort; localhost scripts/baseline/save work', loss_and_reload)

        def responsive_screenshots():
            for width in (320, 390, 768, 1440):
                page.set_viewport_size({'width': width, 'height': 1000 if width == 1440 else 844})
                baseline()
                require(page.evaluate('document.documentElement.scrollWidth <= innerWidth && document.body.scrollWidth <= innerWidth'),
                        f'Preparedness horizontal overflow at {width}')
                if width in (390, 1440):
                    name = 'desktop' if width == 1440 else 'mobile'
                    path = Path('artifacts') / f'lifeline-get-prepared-{name}.png'
                    page.evaluate('scrollTo(0, 0)')
                    page.screenshot(path=str(path), full_page=True)
                    screenshots.append(str(path))

        check('Preparedness widths320/390/768/1440 and desktop/mobile screenshots under network failure', responsive_screenshots)
        check('No unexpected requests, page errors or unhandled rejections', lambda: require(
            not unexpected and not errors and not page.evaluate('testUnhandled'),
            {'unexpected': unexpected, 'errors': errors, 'unhandled': page.evaluate('testUnhandled')}))
        browser.close()

    print(json.dumps({'passed': len(passed), 'failed': len(failures), 'failures': failures,
                      'screenshots': screenshots, 'blocked_external_requests': blocked_external,
                      'note': 'All APIs intercepted; no live inference. NPS attribution is not clinical validation.'}, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
