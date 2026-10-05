"""Verify real Studio workflows and interrupted module downloads without model calls.

Run against the local service. A fresh browser workspace holds all QA boards;
the scientific database is only read through existing deterministic operations.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--output', type=Path, default=Path('docs/implementation/workflow-checks'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'checks': [], 'page_errors': [], 'expected_download_failures': [], 'layouts': []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1366, 'height': 1000}, reduced_motion='reduce')
        page = context.new_page()
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        incoming = 'year=2024&month=7&bbox=-122%2C39.5%2C-121.3%2C40.5&start=2024-07-24&end=2024-08-14&as_of=2024-08-14'
        page.goto(f'{args.base}/studio.html?{incoming}')
        expect(page.get_by_role('button', name='Workflow', exact=True)).to_be_visible(timeout=30000)
        for index, name in enumerate(('01 SENSOR COMPARISON', '02 HISTORICAL EVIDENCE', '03 QUICK WALKTHROUGH')):
            preset = page.get_by_role('button', name=name, exact=False)
            preset.click()
            expect(preset).to_be_enabled(timeout=120000)
            expect(page.get_by_text('Presentation preset prepared.', exact=False)).to_be_visible(timeout=120000)
            board_id = page.evaluate("sessionStorage.getItem('fireatlas-studio-board')")
            page.get_by_role('button', name='Workflow', exact=True).click()
            expect(page.get_by_role('heading', name='Workflow Composer')).to_be_visible(timeout=30000)
            expect(page.locator('.react-flow__node')).to_have_count(7)
            expect(page.locator('.workflow-outline tbody tr')).to_have_count(7)
            page.get_by_role('button', name='Validate graph', exact=True).click()
            expect(page.get_by_text('Valid graph: 7 typed nodes.', exact=True)).to_be_visible()
            report['checks'].append(f'{name}: real seven-node diagram, accessible table and backend validation pass.')
            if index != 0:
                continue
            page.get_by_role('button', name='Edit Daily activity', exact=True).click()
            page.get_by_label('Node label', exact=True).fill('Daily activity · edited QA label')
            page.get_by_role('button', name='Save workflow', exact=True).click()
            expect(page.get_by_text('Saved workflow revision', exact=False)).to_be_visible()
            page.get_by_role('button', name='Run saved revision', exact=True).click()
            expect(page.get_by_text('Run completed; 7 checked node receipts.', exact=True)).to_be_visible(timeout=120000)
            response = context.request.get(f'{args.base}/api/studio/documents/{board_id}/projects')
            assert response.ok, response.text()
            definition = response.json()['workflow']['definition']
            assert len(definition['nodes']) == 7
            assert next(node for node in definition['nodes'] if node['id'] == 'chart')['label'] == 'Daily activity · edited QA label'
            report['checks'].append('Park workflow edit persists and its saved revision completes seven real node receipts without inference.')
            page.screenshot(path=str(args.output / 'workflow-park.png'), full_page=True)
            for width in (360, 390, 768):
                page.set_viewport_size({'width': width, 'height': 1000})
                measurement = page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
                report['layouts'].append(measurement)
                assert measurement['scroll'] <= width + 1, measurement
                expect(page.locator('.workflow-outline')).to_be_visible()
                page.screenshot(path=str(args.output / f'workflow-{width}.png'), full_page=True)
            page.set_viewport_size({'width': 1366, 'height': 1000})

            # A second page can fail fetching the lazy chunk even though the
            # first page has loaded it. This reproduces the original white page.
            broken = context.new_page()
            broken.on('pageerror', lambda error: report['page_errors'].append(str(error)))
            broken.on('requestfailed', lambda request: report['expected_download_failures'].append(urlsplit(request.url).path))
            broken.route('**/assets/WorkflowPanel-*.js', lambda route: route.abort())
            broken.goto(f'{args.base}/studio.html?{incoming}&board={board_id}')
            broken.get_by_role('button', name='Workflow', exact=True).click()
            expect(broken.get_by_role('heading', name='Workflow could not open')).to_be_visible()
            expect(broken.get_by_role('navigation', name='Studio views')).to_be_visible()
            assert broken.locator('#studio-root').evaluate('(root)=>root.childElementCount') > 0
            link = broken.get_by_role('link', name='Refresh Studio and open Workflow')
            assert f'board={board_id}' in link.get_attribute('href') and 'tab=workflow' in link.get_attribute('href')
            broken.screenshot(path=str(args.output / 'workflow-download-recovery.png'), full_page=True)
            broken.get_by_role('button', name='Return to Board', exact=True).click()
            expect(broken.get_by_role('region', name='Evidence canvas', exact=True)).to_be_visible()
            assert broken.evaluate("sessionStorage.getItem('fireatlas-studio-board')") == board_id
            broken.get_by_role('button', name='Workflow', exact=True).click()
            expect(broken.get_by_role('heading', name='Workflow could not open')).to_be_visible()
            broken.unroute('**/assets/WorkflowPanel-*.js')
            broken.get_by_role('link', name='Refresh Studio and open Workflow').click()
            expect(broken.get_by_role('heading', name='Workflow Composer')).to_be_visible(timeout=30000)
            expect(broken.locator('.react-flow__node')).to_have_count(7)
            broken.get_by_role('button', name='Edit Daily activity · edited QA label', exact=True).click()
            expect(broken.get_by_label('Node label', exact=True)).to_have_value('Daily activity · edited QA label')
            assert broken.evaluate("sessionStorage.getItem('fireatlas-studio-board')") == board_id
            broken.screenshot(path=str(args.output / 'workflow-refreshed.png'), full_page=True)
            broken.close()
            report['checks'].append('Interrupted lazy download keeps Studio navigation and Canvas usable; refresh opens the same board and saved workflow.')

        assert not report['page_errors'], report['page_errors']
        assert report['expected_download_failures'], 'Failed download was not exercised.'
        browser.close()
    (args.output / 'browser-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
