"""Check PWA installation metadata and actual browser-offline exercise recovery.

Run against a running FireAtlas server. This is browser verification, not a
physical-phone installation test. Playwright and local Chrome are required.
"""
import argparse
import json
import tempfile
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--chrome', default='/usr/bin/google-chrome')
    args = parser.parse_args()
    base = args.base.rstrip('/')
    with sync_playwright() as playwright, tempfile.TemporaryDirectory(prefix='fireatlas-mobile-') as profile:
        # A persistent profile avoids Chrome's expected incognito install restriction.
        context = playwright.chromium.launch_persistent_context(
            profile, executable_path=args.chrome, headless=True,
            viewport={'width': 390, 'height': 844}, is_mobile=True,
            has_touch=True, reduced_motion='reduce')
        page = context.pages[0]
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(base + '/install.html', wait_until='domcontentloaded')
        page.wait_for_function('navigator.serviceWorker.controller !== null')
        cdp = context.new_cdp_session(page)
        manifest = cdp.send('Page.getAppManifest')
        assert not manifest['errors'], manifest['errors']
        installability = cdp.send('Page.getInstallabilityErrors')
        assert not installability['installabilityErrors'], installability
        assert page.request.get(base + '/manifest.webmanifest').json()['display'] == 'standalone'
        context.set_offline(True)
        page.goto(base + '/?launch=app', wait_until='domcontentloaded')
        expect(page.get_by_role('heading', name='Reconnect to explore the observations.')).to_be_visible()
        context.set_offline(False)
        page.goto(base + '/training.html', wait_until='domcontentloaded')
        expect(page.locator('#offline-pack-status')).to_contain_text('Offline page ready', timeout=20000)
        page.wait_for_function("navigator.serviceWorker.controller?.scriptURL.endsWith('/training-sw.js')")
        expect(page.locator('#step-replay')).to_be_enabled()
        page.locator('#step-replay').click()
        expect(page.locator('#replay-clock')).to_have_text('12:05:00')
        page.locator('#crew-view').click()
        page.locator('#selected-crew').select_option('bravo')
        context.set_offline(True)
        page.reload(wait_until='domcontentloaded')
        expect(page.locator('#replay-clock')).to_have_text('12:05:00', timeout=15000)
        expect(page.locator('#connection-banner')).to_be_visible()
        expect(page.locator('#selected-crew')).to_have_value('bravo')
        with page.expect_download() as download:
            page.locator('#export-exercise').click()
        export_path = download.value.path()
        assert json.loads(export_path.read_text()), 'Empty exercise export'
        assert not errors, errors
        context.close()
    print(json.dumps({
        'chrome_installability_errors': [], 'manifest': 'passed',
        'offline_app_launch': 'passed', 'training_worker_scope': 'passed',
        'offline_saved_clock_and_crew': 'passed', 'offline_export': 'passed',
        'javascript_errors': [], 'physical_phone_test': 'not performed',
    }, indent=2))


if __name__ == '__main__':
    main()
