"""Exercise curated presentation selection and exports against real stored studies, without inference."""
import argparse
import base64
import hashlib
import io
import json
import math
import shutil
import subprocess
import threading
import time
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8133')
    parser.add_argument('--output', type=Path, default=Path('docs/implementation/studio-checks/presentation-presets'))
    parser.add_argument('--render', action='store_true', help='Render a separate ten-second paired-map QA revision, with narration disabled.')
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    report = {'checks': [], 'presets': [], 'page_errors': []}
    with sync_playwright() as pw:
        executable = next((shutil.which(n) for n in ('chromium', 'chromium-browser', 'google-chrome') if shutil.which(n)), None)
        browser = pw.chromium.launch(headless=True, executable_path=executable)
        context = browser.new_context(viewport={'width': 1600, 'height': 1050}, accept_downloads=True, reduced_motion='reduce')
        page = context.new_page(); page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        page.goto(args.base + '/studio.html?case=park-2024'); expect(page.get_by_label('Board title')).to_be_visible(timeout=30000)
        page.screenshot(path=str(args.output / 'preset-gallery.png'), full_page=True)
        for case, label, records, cells, scenes in [('park-2024', 'Park · two sensors, one study', 6224, 2228, 6), ('camp-2018', 'Camp · read the archive honestly', 5644, 1375, 6), ('grove-2025', 'Grove · a small, inspectable example', 7, 4, 3)]:
            page.get_by_role('button').filter(has_text=label).click()
            expect(page.get_by_role('button', name='1 · Inspect linked heat maps', exact=True)).to_be_visible(timeout=90000)
            expect(page.locator('.preset-status')).to_contain_text('Ready · heat maps show')
            expect(page.locator('.board-wrap')).to_have_count(1)
            expect(page.get_by_text('Your board is empty', exact=True)).to_have_count(0)
            document_id = page.evaluate("sessionStorage.getItem('fireatlas-studio-board')")
            board = context.request.get(args.base + '/api/studio/documents/' + document_id).json()
            assert board['state']['study']['context']['case'] == case
            assert len(board['state']['cards']) == 8 and len(board['state']['connections']) == 5
            replay = next(s for s in board['snapshots'].values() if s['operation'] == 'replay')
            assert any(f['value'] == records and f['unit'] == 'records' for f in replay['facts'])
            assert any(f['value'] == cells and f['unit'] == 'cell-days' for f in replay['facts'])
            maps = page.locator('.card').filter(has=page.locator('canvas[role=img]'))
            # Scroll second sensor into view so its lazy frozen preview mounts.
            page.locator('.card').filter(has_text='S-NPP VIIRS · occupied-cell heat').scroll_into_view_if_needed()
            expect(maps).to_have_count(2)
            expect(maps.locator('.map-note')).to_contain_text(['Scale fixed', 'Scale fixed'], timeout=30000)
            assert len(set(maps.locator('canvas').evaluate_all('cs => cs.map(c => c.dataset.maximum)'))) == 1
            board_maximum = float(maps.locator('canvas').first.get_attribute('data-maximum'))
            with page.expect_download() as download:
                maps.get_by_role('button', name='Download heat map PNG').first.click()
            download.value.save_as(args.output / (case + '-heat.png'))
            # Pixel data contains rendered heat, rather than a blank decorative placeholder.
            assert maps.locator('canvas').first.evaluate("c => {const a=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;for(let i=0;i<a.length;i+=4)if(a[i]>100&&a[i+1]>40&&a[i+1]<200&&a[i+2]<100)n++;return n;}") > 0
            chart = page.locator('.card').filter(has_text='Activity chart')
            chart.scroll_into_view_if_needed(); chart.get_by_text('Numeric table and chart downloads', exact=True).click()
            expect(chart.locator('table caption')).to_contain_text('occupied common cells')
            with page.expect_download() as download: chart.get_by_role('button', name='Download chart values CSV', exact=True).click()
            download.value.save_as(args.output / (case + '-chart.csv'))
            maps.first.get_by_role('button', name='Open details', exact=True).click()
            expect(page.get_by_label('Inspector', exact=True)).to_be_focused()
            maps.first.get_by_role('button', name='Expand map', exact=True).click()
            dialog = page.get_by_role('dialog'); expect(dialog).to_be_visible()
            expect(dialog.locator('.map-note')).to_contain_text('study-fixed', timeout=30000)
            dialog.get_by_label('Visible source').select_option('VIIRS_SNPP_SP')
            dialog.get_by_label('Map statistic').select_option('persistence')
            expect(dialog.locator('.map-note')).to_contain_text('distinct observed UTC dates', timeout=30000)
            page.keyboard.press('Escape'); expect(dialog).to_have_count(0)
            if case == 'park-2024':
                page.get_by_role('button', name='Fit all cards', exact=True).click()
                page.get_by_role('region', name='Evidence canvas', exact=True).screenshot(path=str(args.output / 'park-linked-board.png'))
            page.get_by_role('button', name='2 · See the workflow', exact=True).click()
            expect(page.get_by_role('region', name='Typed workflow diagram')).to_be_visible()
            expect(page.locator('.react-flow__node')).to_have_count(7)
            page.get_by_role('button', name='Validate graph', exact=True).click()
            expect(page.get_by_role('status').filter(has_text='Valid graph: 7')).to_be_visible()
            if case == 'park-2024':
                page.get_by_role('button', name='Run saved revision', exact=True).click()
                expect(page.get_by_role('status').filter(has_text='Run completed; 7 checked node receipts.')).to_be_visible(timeout=60000)
                expect(page.locator('.react-flow__node .chip.ok')).to_have_count(7)
                page.get_by_role('button', name='Fit entire workflow', exact=True).click()
                page.get_by_role('region', name='Typed workflow diagram').screenshot(path=str(args.output / 'park-workflow.png'))
            projects = context.request.get(args.base + '/api/studio/documents/' + document_id + '/projects').json()
            assert projects['workflow'] and len(projects['workflow']['definition']['nodes']) == 7
            story = context.request.get(args.base + '/api/studio/stories/' + projects['stories'][0]['id']).json()
            assert story['body']['audience'] == 'presenter' and len(story['body']['chapters']) == scenes
            assert story['resolved']
            pair = story['resolved']['scenes'][0]
            assert pair['gallery_version'] == 2
            images = [view['visual'] for view in pair['visible_card_views']]
            assert len(images) == 2 and all(image['kind'] == 'heat' for image in images)
            assert images[0]['domain'] == images[1]['domain']
            assert math.isclose(board_maximum, images[0]['domain'][1], rel_tol=1e-12, abs_tol=1e-12)
            report.setdefault('shared_heat_scales', {})[case] = {'board': board_maximum, 'story': images[0]['domain'][1]}
            assert images[0]['receipt_sha256'] == images[1]['receipt_sha256'] == replay['receipt_sha256']
            assert pair['visual_svg'].count('href="data:image/png;base64,') == 2
            for image in images:
                data = base64.b64decode(image['data'], validate=True)
                assert hashlib.sha256(data).hexdigest() == image['sha256']
                (args.output / (case + '-' + image['source'] + '-story-heat.png')).write_bytes(data)
            (args.output / (case + '-paired-story.svg')).write_text(pair['visual_svg'])
            exported = context.request.get(args.base + '/api/studio/stories/' + story['id'] + '/export')
            assert exported.ok, exported.text()
            (args.output / (case + '-reader.zip')).write_bytes(exported.body())
            reader_path = args.output / (case + '-reader')
            with zipfile.ZipFile(io.BytesIO(exported.body())) as archive:
                roots = [reader_path / name for name in archive.namelist() if name.endswith('/story.json') or name == 'story.json']
                archive.extractall(reader_path)
            from fireatlas.studio.story import verify_reader
            assert len(roots) == 1
            verified = verify_reader(roots[0].parent)
            assert verified['verified'], verified
            (args.output / (case + '-reader-verification.json')).write_text(json.dumps(verified, indent=2))
            page.get_by_role('button', name='3 · Play the curated story', exact=True).click()
            expect(page.get_by_text('Story Director', exact=True)).to_be_visible()
            expect(page.locator('.player .scene-schematic')).to_be_visible()
            page.wait_for_function("(() => {const image=document.querySelector('.player .scene-schematic'); return image?.complete && image.naturalWidth > 0;})()")
            table = page.locator('[data-heat-table]')
            expect(table.locator('tbody tr')).to_have_count(2)
            for index, image in enumerate(images):
                expect(table.locator('tbody tr').nth(index).locator('td').nth(1)).to_have_text(str(image['count']))
            page.locator('.player .scene-schematic').screenshot(path=str(args.output / (case + '-paired-story.png')))
            # Exercise the exported reader without the scientific/private API.
            reader_server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(reader_path)))
            reader_thread = threading.Thread(target=reader_server.serve_forever, daemon=True); reader_thread.start()
            reader_context = browser.new_context(viewport={'width': 390, 'height': 900}, reduced_motion='reduce')
            try:
                reader_page = reader_context.new_page()
                reader_page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
                reader_page.goto(f'http://127.0.0.1:{reader_server.server_port}/' + roots[0].parent.relative_to(reader_path).as_posix() + '/index.html')
                expect(reader_page.locator('[data-heat-table] tbody tr')).to_have_count(2)
                reader_page.wait_for_function("document.querySelector('[data-fallback]')?.naturalWidth > 0")
                contrast = reader_page.evaluate("""() => {
                  const note = document.querySelector('[data-narration-grounding]');
                  const rgb = (value) => value.match(/[\\d.]+/g).slice(0, 3).map(Number);
                  const luminance = (values) => values.map(v => {const s=v/255; return s<=.04045?s/12.92:((s+.055)/1.055)**2.4;}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
                  const a=luminance(rgb(getComputedStyle(note).color)), b=luminance(rgb(getComputedStyle(document.querySelector('.scene')).backgroundColor));
                  return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
                }""")
                assert contrast >= 4.5, contrast
                report.setdefault('reader_grounding_contrast', {})[case] = round(contrast, 2)
                for index, image in enumerate(images):
                    expect(reader_page.locator('[data-heat-table] tbody tr').nth(index).locator('td').nth(1)).to_have_text(str(image['count']))
                position = reader_page.locator('[data-position]').inner_text()
                reader_page.get_by_role('button', name='Explore chapter evidence', exact=True).click()
                expect(reader_page.get_by_role('button', name='Next', exact=True)).to_be_disabled()
                reader_page.get_by_role('button', name='Resume story', exact=True).click()
                expect(reader_page.locator('[data-position]')).to_have_text(position)
                reader_page.locator('[data-heat-table]').focus()
                reader_page.keyboard.press('ArrowRight')
                expect(reader_page.locator('[data-position]')).to_have_text(position)
                assert reader_page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                reader_page.screenshot(path=str(args.output / (case + '-portable-reader-390.png')), full_page=True)
            finally:
                reader_context.close(); reader_server.shutdown(); reader_server.server_close(); reader_thread.join(timeout=2)
            if case == 'park-2024' and args.render:
                # A distinct saved QA story leaves the original 90-second
                # presentation untouched and never invokes paid narration.
                body = {**story['body'], 'title': 'Paired heat · ten-second render QA',
                        'target_duration_seconds': 10, 'chapters': [story['body']['chapters'][0]]}
                created = context.request.post(args.base + '/api/studio/documents/' + document_id + '/stories', data=body,
                    headers={'Origin': args.base})
                assert created.ok, created.text()
                rendered_story = created.json()
                frozen = context.request.post(args.base + '/api/studio/stories/' + rendered_story['id'] + '/resolve', data={}, headers={'Origin': args.base})
                assert frozen.ok, frozen.text()
                started = context.request.post(args.base + '/api/studio/stories/' + rendered_story['id'] + '/renders', data={'narration': False}, headers={'Origin': args.base})
                assert started.ok, started.text()
                job = started.json(); deadline = time.monotonic() + 180
                while job['status'] in ('queued', 'running') and time.monotonic() < deadline:
                    threading.Event().wait(.5)
                    result = context.request.get(args.base + '/api/studio/renders/' + job['id'])
                    assert result.ok, result.text()
                    job = result.json()
                assert job['status'] == 'completed', job
                observed = job['manifest']['resource_observation']
                limits = job['manifest']['execution_limits']
                assert 0 < observed['peak_summed_resident_bytes'] <= limits['summed_resident_bytes'], observed
                assert 0 < observed['sampled_cpu_seconds'] <= limits['sampled_cpu_seconds'], observed
                assert observed['tracked_process_identities'] >= 2, observed
                report['render_resource_observation'] = observed
                for kind, filename in [('video', 'paired-heat.mp4'), ('manifest', 'paired-heat-render-manifest.json'), ('captions', 'paired-heat-captions.vtt')]:
                    artifact = context.request.get(args.base + '/api/studio/renders/' + job['id'] + '/artifact?name=' + kind)
                    assert artifact.ok
                    (args.output / filename).write_bytes(artifact.body())
                probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(args.output / 'paired-heat.mp4')], capture_output=True, text=True, check=True)
                (args.output / 'paired-heat-probe.json').write_text(probe.stdout)
                report['paired_video'] = {'seconds': 10, 'narration': 'disabled; no provider call', 'artifact': 'paired-heat.mp4', 'story_revision': job['story_revision']}
            if case == 'grove-2025': page.screenshot(path=str(args.output / 'grove-short-story.png'), full_page=True)
            report['presets'].append({'case': case, 'document_id': document_id, 'records': records, 'joint_cell_days': cells, 'cards': 8, 'links': 5, 'workflow_nodes': 7, 'chapters': scenes})
        for width in [360, 390, 768]:
            page.set_viewport_size({'width': width, 'height': 900})
            page.screenshot(path=str(args.output / f'presets-{width}.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        report['checks'] = ['All three preset selections create separate saved boards with authentic counts.', 'Paired geographic heat images and PNG exports contain real frozen occupied-cell heat.', 'Curated stories preserve both frozen heat images and one shared domain; all three portable readers recount successfully.', 'Authoring and standalone readers expose matching heat-frame count/state tables; reader keyboard focus and 390-pixel width retain the same chapter.', 'Chart CSV and numeric table use the frozen series.', 'Card details receive focus; expanded map source/statistic controls and Escape dispose it.', 'Saved seven-node typed workflows validate; Park executes all seven nodes with checked receipts and no invented measurements.', 'Presenter prose and resolved stories remain scoped; Grove uses three short scenes.', '360, 390 and 768 pixel layouts fit.']
        assert not report['page_errors'], report['page_errors']
        browser.close()
    (args.output / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
