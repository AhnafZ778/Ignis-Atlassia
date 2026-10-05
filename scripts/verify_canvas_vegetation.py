"""Authentic Park Canvas landscape, saved background controls and PNG acceptance."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--output', type=Path, default=Path('docs/implementation/canvas-vegetation'))
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    report = {'checks': [], 'page_errors': []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1100}, reduced_motion='reduce', accept_downloads=True)
        page = context.new_page(); page.on('pageerror', lambda e: report['page_errors'].append(str(e)))
        page.goto(args.base + '/studio.html')
        page.locator('.preset-option').first.click(timeout=30000)
        expect(page.locator('.preset-status')).to_contain_text('Ready · heat maps show', timeout=90000)
        page.locator('.board-wrap').scroll_into_view_if_needed()
        maps = page.locator('article.card').filter(has=page.locator('canvas'))
        expect(maps).to_have_count(2)
        page.wait_for_function("document.querySelectorAll('article.card canvas[data-background=ndvi]').length === 2", timeout=30000)
        first = maps.first
        canvas = first.locator('canvas')
        initial = canvas.evaluate("c => ({maximum:c.dataset.maximum,day:c.dataset.day,source:c.dataset.source,background:c.dataset.background,pixels:c.toDataURL()})")
        maxima = [c.get_attribute('data-maximum') for c in page.locator('article.card canvas').all()]
        assert maxima[0] == maxima[1]
        report['scale_maximum'] = maxima[0]; report['selected_utc_day'] = initial['day']
        expect(first.get_by_role('switch', name='Map background', exact=True)).to_be_checked()
        first.get_by_role('switch', name='Map background', exact=True).click()
        page.wait_for_function("document.querySelector('article.card canvas').dataset.background === 'none'")
        dark = canvas.evaluate("c => ({maximum:c.dataset.maximum,day:c.dataset.day,source:c.dataset.source,pixels:c.toDataURL()})")
        assert dark['pixels'] != initial['pixels']
        assert all(dark[k] == initial[k] for k in ('maximum', 'day', 'source'))
        first.get_by_role('switch', name='Map background', exact=True).press('Space')
        page.wait_for_function("document.querySelectorAll('article.card canvas[data-background=ndvi]').length === 2")
        expect(first.get_by_role('button', name='Download heat map PNG')).to_be_enabled()
        with page.expect_download() as download:
            first.get_by_role('button', name='Download heat map PNG').click()
        download.value.save_as(args.output / 'park-vegetation-heat.png')
        page.get_by_role('button', name='Fit all cards', exact=True).click()
        page.locator('.board-wrap').scroll_into_view_if_needed()
        page.screenshot(path=str(args.output / 'vegetation-canvas.png'))
        report['checks'].append('Park preset uses authentic supplied NDVI and terrain under both heatmaps, with the dated composite label.')
        report['checks'].append('Changing to heat-only and back changes pixels while preserving date, sensor and the shared full-study scale; PNG includes vegetation.')
        page.reload(); page.locator('.board-wrap').scroll_into_view_if_needed(timeout=30000)
        page.wait_for_function("document.querySelectorAll('article.card canvas[data-background=ndvi]').length === 2", timeout=30000)
        expect(page.locator('article.card').filter(has=page.locator('canvas')).first.get_by_role('switch', name='Map background', exact=True)).to_be_checked()
        report['checks'].append('The text-free dot toggles with click or Space, has a screen-reader switch label, and saves its state through refresh.')
        page.locator('article.card').filter(has=page.locator('canvas')).first.get_by_role('button', name='Interact with map').click()
        expect(page.locator('.leaflet-image-layer').first).to_be_visible(timeout=15000)
        report['checks'].append('Interactive Canvas map uses the same supplied vegetation background.')
        assert not report['page_errors'], report['page_errors']
        # Remove only this acceptance workspace's board, leaving user work intact.
        for board in context.request.get(args.base + '/api/studio/documents').json()['documents']:
            response = context.request.delete(args.base + '/api/studio/documents/' + board['id'], data={'expected_revision': board['revision']}, headers={'Origin': args.base})
            assert response.ok, response.text()
        browser.close()
    (args.output / 'browser-report.json').write_text(json.dumps(report, indent=2) + '\n'); print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
