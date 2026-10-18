"""Check bundled medical summaries on port 8000 without invoking inference."""
import argparse
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://localhost:8000')
    args = parser.parse_args()
    base = args.base_url.rstrip('/')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        # Block APIs, not static reference data: the library must not depend on them.
        context.route('**/api/**', lambda route: route.abort())
        page.goto(base + '/#library')
        expect(page.locator('.library-card')).to_have_count(10)
        expect(page.locator('#library-status')).to_have_text('10 medical information summaries loaded locally.')
        data = page.request.get(base + '/assets/official_first_aid.json').json()
        titles = sorted(topic['title'] for topic in data['topics'])
        assert page.locator('.library-title-button').all_text_contents() == titles
        for topic in data['topics']:
            page.get_by_role('button', name=topic['title'], exact=True).click()
            expect(page.locator('#library-article h2')).to_have_text(topic['title'])
            assert page.locator('#library-article .library-body').text_content() == topic['summary']
            expect(page.locator('#library-article a')).to_have_attribute('href', topic['url'])
            page.locator('#library-back').click()
        page.locator('#library-search').fill('dizziness')
        assert page.locator('.library-card').count() > 0
        page.locator('#library-search').fill('no-such-reference-xyz')
        expect(page.locator('#library-empty')).to_have_text('No matching medical information found.')
        page.locator('#library-search').fill('')
        page.locator('#library-alphabet').get_by_role('button', name='B', exact=True).click()
        assert page.locator('.library-title-button').all_text_contents() == ['Bleeding', 'Burns']
        page.locator('#library-alphabet').get_by_role('button', name='All', exact=True).click()
        page.locator('#library-categories').get_by_role('button', name='Injuries', exact=True).click()
        expect(page.locator('.library-card')).to_have_count(4)
        page.locator('#library-categories').get_by_role('button', name='All', exact=True).click()
        for width in (320, 390, 768, 1440):
            page.set_viewport_size({'width': width, 'height': 900})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        # The root page is not SW-controlled. Test true offline reload at the installed entry.
        page.goto(base + '/assets/index.html#library')
        page.evaluate('''async () => {
            await navigator.serviceWorker.ready;
            if (!navigator.serviceWorker.controller) await new Promise(resolve =>
              navigator.serviceWorker.addEventListener('controllerchange', resolve, {once:true}));
        }''')
        context.set_offline(True)
        page.reload()
        expect(page.locator('.library-card')).to_have_count(10)
        page.locator('#library-search').fill('frostbite')
        expect(page.get_by_role('button', name='Frostbite', exact=True)).to_be_visible()
        page.get_by_role('button', name='Frostbite', exact=True).click()
        expect(page.locator('#library-article .library-body')).to_contain_text('freezing')
        page.locator('#library-back').click()
        page.locator('#library-search').fill('')
        page.screenshot(path='artifacts/lifeline-library-offline.png', full_page=True)
        assert not errors, errors
        browser.close()
    print('PASS: all 10 actual summaries match bundled JSON, open correctly, search, A-Z, categories, mobile layout, API-independent use and true offline refresh.')


if __name__ == '__main__':
    main()
