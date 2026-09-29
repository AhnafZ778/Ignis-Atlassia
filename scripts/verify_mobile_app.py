"""Check PWA metadata and its offline reconnect page against a running server.

Run with Playwright and local Chrome installed. This emulates a mobile viewport;
it does not replace an installation test on a physical phone.
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
        page.goto(base + '/offline.html', wait_until='domcontentloaded')
        expect(page.get_by_role('heading', name='Reconnect to explore the observations.')).to_be_visible()
        context.set_offline(True)
        page.reload(wait_until='domcontentloaded')
        expect(page.get_by_role('heading', name='Reconnect to explore the observations.')).to_be_visible()
        assert not errors, errors
        context.close()
    print(json.dumps({
        'manifest': 'passed', 'installability_metadata': 'passed',
        'offline_reconnect_page': 'passed', 'javascript_errors': [],
        'physical_phone_test': 'not performed',
    }, indent=2))


if __name__ == '__main__':
    main()
