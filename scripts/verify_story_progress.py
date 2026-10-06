"""Exercise story checkpoint recovery using an existing owned acceptance job.

--identity is a private JSON file containing recovery, board and generation.
No authoring or render submission is performed; never commit that file.
"""
import argparse
import json
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--identity', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-narration', action='store_true')
    args = parser.parse_args()
    identity = json.loads(args.identity.read_text())
    base = args.base.rstrip('/')
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'checks': [], 'page_errors': [], 'generation_posts': 0}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=shutil.which('chromium'), args=['--autoplay-policy=no-user-gesture-required'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
        response = context.request.post(base + '/api/studio/recover', data={'recovery': identity['recovery']}, headers={'Origin': base})
        assert response.ok, 'The private acceptance identity could not be recovered.'
        endpoint = base + '/api/studio/story-generations/' + identity['generation']
        response = context.request.get(endpoint)
        assert response.ok
        job = response.json()
        assert job['status'] == 'completed' and job['progress'] == 1
        assert job['render']['status'] == 'completed' and job['render']['artifacts']['video']
        page = context.new_page()
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        def request_seen(request):
            if request.method == 'POST' and '/story-generations' in request.url:
                report['generation_posts'] += 1
        page.on('request', request_seen)
        projects_seen = []
        def projects(route):
            response = route.fetch()
            payload = response.json()
            if not projects_seen:
                projects_seen.append(True)
                payload['renders'] = []
            route.fulfill(response=response, json=payload)
        page.route('**/api/studio/documents/*/projects', projects)
        intercepted = []
        def checkpoint(route):
            if not intercepted:
                intercepted.append(True)
                route.fulfill(json={**job, 'status': 'completed', 'phase': 'saved', 'progress': .65,
                                    'render_id': None, 'render': None})
            else:
                route.continue_()
        page.route(endpoint, checkpoint)
        page.goto(base + '/studio.html?board=' + identity['board'] + '&tab=story', wait_until='domcontentloaded')
        bar = page.get_by_role('progressbar', name='Story creation progress')
        expect(bar).to_have_attribute('aria-valuenow', '65')
        expect(page.get_by_text('Storyboard saved · preparing your film', exact=True)).to_be_visible()
        expect(bar).to_have_attribute('aria-valuenow', '100', timeout=30000)
        expect(page.get_by_role('link', name='Download film', exact=True)).to_be_visible()
        page.wait_for_function("document.querySelector('.story-film video')?.readyState >= 1")
        assert page.locator('.story-film video').evaluate('v => v.duration') > 0
        if args.expect_narration:
            expect(page.get_by_text('Voice narration is included in this film.', exact=False)).to_be_visible()
            video = page.locator('.story-film video')
            video.evaluate('async v => { v.currentTime = 4; await v.play(); }')
            page.wait_for_function("document.querySelector('.story-film video')?.currentTime > 4.25")
            assert video.evaluate('v => !v.muted && v.volume > 0')
            video.evaluate('v => v.pause()')
            expect(page.get_by_role('button', name='Refresh film & voice', exact=True)).to_be_visible()
            report['checks'].append('Narrated film plays with sound enabled; saved-story refresh action is visible.')
        page.locator('.story-panel').screenshot(path=str(args.output / 'story-completed-desktop.png'))
        report['checks'].append('Real saved film restores after simulated legacy 65% checkpoint; valid video metadata and download visible.')
        page.reload(wait_until='domcontentloaded')
        expect(bar).to_have_attribute('aria-valuenow', '100', timeout=30000)
        expect(page.get_by_role('link', name='Download film', exact=True)).to_be_visible()
        report['checks'].append('Refresh restores completed progress and film without another AI request.')
        for width in (360, 390, 768):
            page.set_viewport_size({'width': width, 'height': 950})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), width
            expect(page.get_by_role('link', name='Download film', exact=True)).to_be_visible()
        report['checks'].append('360, 390 and 768 pixel layouts have no horizontal page overflow.')
        assert report['generation_posts'] == 0 and not report['page_errors'], report
        browser.close()
    (args.output / 'browser-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
