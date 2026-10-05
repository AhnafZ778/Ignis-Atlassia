"""Browser acceptance for confirmed investigation deletion and an empty Studio."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--output', type=Path, default=Path('docs/implementation/investigation-deletion'))
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    report = {'checks': [], 'page_errors': [], 'layouts': []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
        page = context.new_page(); page.on('pageerror', lambda e: report['page_errors'].append(str(e)))
        page.goto(args.base + '/studio.html')
        expect(page.get_by_role('heading', name='No investigation open')).to_be_visible(timeout=30000)
        assert context.request.get(args.base + '/api/studio/documents').json()['documents'] == []
        for button in page.locator('.preset-option').all(): expect(button).to_be_enabled()
        report['checks'].append('An empty workspace creates no unwanted board; all curated presets remain selectable.')

        def create(name):
            page.get_by_role('button', name='Blank investigation', exact=True).click()
            modal = page.get_by_role('dialog', name='Name your investigation')
            modal.get_by_label('Investigation name', exact=True).fill(name)
            modal.get_by_role('button', name='Create investigation', exact=True).click()
            expect(modal).not_to_be_visible(timeout=15000)
            expect(page.get_by_label('Board title')).to_have_value(name)
            return context.request.get(args.base + '/api/studio/documents').json()['documents'][0]['id']

        first = create('Keep this investigation'); second = create('Delete this investigation')
        page.get_by_role('button', name='Delete investigation', exact=True).click()
        modal = page.get_by_role('dialog', name='Delete this investigation?')
        expect(modal).to_be_visible(); expect(modal.locator('.delete-title')).to_have_text('Delete this investigation')
        expect(modal.get_by_role('button', name='Keep investigation')).to_be_focused()
        modal.get_by_role('button', name='Keep investigation').click()
        expect(modal).not_to_be_visible(); expect(page.get_by_role('button', name='Delete investigation', exact=True)).to_be_focused()
        assert len(context.request.get(args.base + '/api/studio/documents').json()['documents']) == 2
        page.get_by_role('button', name='Delete investigation', exact=True).click(); page.keyboard.press('Escape')
        expect(modal).not_to_be_visible(); assert context.request.get(args.base + '/api/studio/documents/' + second).ok
        report['checks'].append('Keep and Escape preserve the investigation and return keyboard focus.')
        page.get_by_role('button', name='Delete investigation', exact=True).click()
        for width in (360, 390, 768):
            page.set_viewport_size({'width': width, 'height': 1000})
            expect(modal).to_be_visible(); expect(modal.get_by_role('button', name='Delete investigation', exact=True)).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            report['layouts'].append(width)
        page.screenshot(path=str(args.output / 'confirmation-narrow.png'))
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.screenshot(path=str(args.output / 'confirmation-desktop.png'))
        modal.get_by_role('button', name='Delete investigation', exact=True).click()
        expect(modal).not_to_be_visible(timeout=15000)
        expect(page.get_by_label('Board title')).to_have_value('Keep this investigation')
        assert context.request.get(args.base + '/api/studio/documents/' + second).status == 404
        page.reload(); expect(page.get_by_label('Board title')).to_have_value('Keep this investigation', timeout=30000)
        report['checks'].append('Confirmed deletion removes only the selected investigation, opens the remaining board and survives refresh.')
        page.get_by_role('button', name='Delete investigation', exact=True).click()
        modal.get_by_role('button', name='Delete investigation', exact=True).click()
        expect(modal).not_to_be_visible(timeout=15000)
        expect(page.get_by_role('heading', name='No investigation open')).to_be_visible()
        assert context.request.get(args.base + '/api/studio/documents').json()['documents'] == []
        page.goto(args.base + '/studio.html?board=' + first + '&case=park-2024')
        expect(page.get_by_role('heading', name='No investigation open')).to_be_visible(timeout=30000)
        page.reload(); expect(page.get_by_role('heading', name='No investigation open')).to_be_visible(timeout=30000)
        assert context.request.get(args.base + '/api/studio/documents').json()['documents'] == []
        report['checks'].append('Deleting the last investigation stays empty after refresh and a stale board link; no replacement is created.')
        assert not report['page_errors'], report['page_errors']; browser.close()
    (args.output / 'browser-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
