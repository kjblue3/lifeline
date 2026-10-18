"""Check a running LifeLine PWA, not physical Android/WebAPK installation.

Usage: python pwa_check.py https://your-preview.trycloudflare.com/assets/index.html
No model inference, medical database access, server startup, or real profile data.
"""
import argparse
import json
import struct
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    args = parser.parse_args()
    origin = '{0.scheme}://{0.netloc}'.format(urlsplit(args.url))
    private_marker = 'PWA-FICTIONAL-PRIVATE-TEST-ONLY'
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, mobile in ((1440, False), (412, True)):
            context = browser.new_context(
                viewport={'width': width, 'height': 915},
                is_mobile=mobile, has_touch=mobile,
            )
            page = context.new_page()
            errors = []
            requests = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: requests.append(request))
            response = page.goto(args.url, wait_until='networkidle', timeout=60000)
            assert response.status == 200
            assert page.url == origin + '/assets/index.html'
            assert page.evaluate('window.isSecureContext')
            expect(page.locator('#welcome-title')).to_be_visible()
            page.evaluate('async () => { await navigator.serviceWorker.ready; }')
            page.wait_for_function('navigator.serviceWorker.controller !== null')
            session = context.new_cdp_session(page)
            manifest_result = session.send('Page.getAppManifest')
            assert not manifest_result['errors'], manifest_result['errors']
            manifest = json.loads(manifest_result['data'])
            assert manifest['name'] == 'LifeLine'
            assert manifest['display'] == 'standalone'
            assert manifest['id'] == manifest['scope'] == '/assets/'
            assert manifest['start_url'] == '/assets/index.html'
            assert not manifest.get('prefer_related_applications', False)
            for size in (192, 512):
                icon = next(icon for icon in manifest['icons']
                            if icon['sizes'] == f'{size}x{size}' and icon['purpose'] == 'any')
                result = context.request.get(urljoin(manifest_result['url'], icon['src']))
                assert result.status == 200
                assert result.headers['content-type'] == 'image/png'
                png = result.body()
                assert png[:8] == b'\x89PNG\r\n\x1a\n'
                assert struct.unpack('>II', png[16:24]) == (size, size)
            install_errors = session.send('Page.getInstallabilityErrors')['installabilityErrors']
            assert not install_errors, install_errors
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')

            # Only fictional in-memory data; verify it cannot enter Cache Storage.
            page.locator('.nav-item[data-screen=profile]').click()
            page.locator('#profile-name').fill(private_marker)
            page.locator('#profile-save').click()
            page.evaluate('async () => { await fetch("/api/status", {cache: "no-store"}); }')
            cache_audit = page.evaluate(r'''async (marker) => {
              const urls = [];
              let leaked = false;
              for (const name of await caches.keys()) {
                if (!name.startsWith('lifeline-')) continue;
                const cache = await caches.open(name);
                for (const request of await cache.keys()) {
                  const url = new URL(request.url);
                  urls.push(url.pathname);
                  const response = await cache.match(request);
                  if ((response.headers.get('content-type') || '').includes('text') ||
                      /\.(js|webmanifest)$/.test(url.pathname)) {
                    if ((await response.text()).includes(marker)) leaked = true;
                  }
                }
              }
              return {urls, leaked};
            }''', private_marker)
            assert cache_audit['urls'] and not cache_audit['leaked']
            assert all(url.startswith('/assets/') for url in cache_audit['urls'])
            assert '/assets/icons/lifeline-192.png' in cache_audit['urls']
            assert '/assets/icons/lifeline-512.png' in cache_audit['urls']
            assert all(private_marker not in (request.post_data or '') for request in requests)

            # Reopen in a new page with the network disabled, not just a DOM check.
            context.set_offline(True)
            page.close()
            offline_page = context.new_page()
            offline_page.on('pageerror', lambda error: errors.append(str(error)))
            response = offline_page.goto(args.url, wait_until='load', timeout=30000)
            assert response.status == 200
            expect(offline_page.locator('#welcome-title')).to_be_visible()
            offline_page.locator('.nav-item[data-screen=prepared]').click()
            expect(offline_page.locator('#screen-prepared')).to_be_visible()
            assert offline_page.locator('#prepared-items li').count() > 0
            offline_page.locator('.nav-item[data-screen=profile]').click()
            expect(offline_page.locator('#profile-name')).to_have_value('')
            offline_page.locator('#emergency-open').click()
            expect(offline_page.locator('#emergency-dialog')).to_be_visible()
            assert not errors, errors
            context.set_offline(False)
            offline_page.reload(wait_until='networkidle')
            print(f'PASS width={width}, mobile={mobile}: HTTPS, PNGs, manifest, '
                  'zero Chromium installability errors, service worker, cold-page '
                  'offline interface, checklist, profile cleared, no private/API cache.')
            context.close()
        browser.close()
    print('Physical Android install, launcher icon and standalone window still require device confirmation.')


if __name__ == '__main__':
    main()
