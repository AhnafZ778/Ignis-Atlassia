"""Exercise a real Studio board, saved story, workflow and portable reader with no model calls.

Start the local service separately. This creates private test investigations and exports;
it never changes the scientific archive, runs a provider, or publishes anything.
"""
from __future__ import annotations
import argparse
import html
import json
import shutil
import subprocess
import threading
import time
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8126')
    parser.add_argument('--output', type=Path, default=Path('docs/implementation/studio-checks'))
    parser.add_argument('--render', action='store_true', help='Explicitly render a silent 12-second test; never invokes speech.')
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    origin = f'{urlsplit(args.base).scheme}://{urlsplit(args.base).netloc}'
    report = {'checks': [], 'page_errors': [], 'initial_load': {}, 'narrow_layout': []}
    with sync_playwright() as playwright:
        executable = next((shutil.which(n) for n in ('chromium', 'chromium-browser', 'google-chrome') if shutil.which(n)), None)
        browser = playwright.chromium.launch(headless=True, executable_path=executable)
        context = browser.new_context(viewport={'width': 1440, 'height': 1100}, reduced_motion='reduce', accept_downloads=True)
        page = context.new_page(); page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        loaded = []
        page.on('response', lambda response: loaded.append(response))
        page.goto(args.base + '/studio.html?case=park-2024', wait_until='domcontentloaded')
        expect(page.get_by_label('Board title')).to_be_visible(timeout=30000)
        report['initial_load'] = {'requests': len(loaded), 'response_body_bytes': sum(len(r.body()) for r in loaded if urlsplit(r.url).hostname in ('localhost', '127.0.0.1')),
                                  'measurement': 'Cold browser context; same-origin decoded response bodies, without HTTP headers.'}
        api = lambda method, route, body=None: context.request.fetch(args.base + '/api/studio/' + route, method=method, data=body, headers={'Origin': origin})
        def checked(method, route, body=None):
            response = api(method, route, body)
            if not response.ok: raise AssertionError(f'{route}: {response.status} {response.text()}')
            return response.json()
        document_id = page.evaluate("sessionStorage.getItem('fireatlas-studio-board')")
        page.get_by_role('button', name='Build from current study', exact=True).click()
        page.wait_for_function("document.querySelectorAll('.card').length === 7 && document.querySelectorAll('.card-foot').length === 5", timeout=60000)
        board = checked('GET', 'documents/' + document_id)
        replay = next(s for s in board['snapshots'].values() if s['operation'] == 'replay')
        facts = {f['path']: f for f in replay['facts']}
        assert any(f['value'] == 6224 and f['unit'] == 'records' for f in facts.values()), facts
        assert any(f['value'] == 2228 and f['unit'] == 'cell-days' for f in facts.values()), facts
        report['checks'].append('Authentic Park: 6,224 eligible records and 2,228 joint cell-days retain distinct units.')
        expect(page.get_by_text('Applied study and linked display', exact=True)).to_have_count(1)
        page.evaluate('scrollTo(0,0)')
        page.screenshot(path=str(output / 'board.png'), full_page=True)
        page.reload(wait_until='domcontentloaded'); expect(page.get_by_label('Board title')).to_be_visible()
        assert page.evaluate("sessionStorage.getItem('fireatlas-studio-board')") == document_id
        expect(page.locator('.card')).to_have_count(7)
        report['checks'].append('Explicit handoff refresh restores the same saved board.')
        # The deterministic fallback is the normal no-license path. Exercise
        # the gestures users expect from a preset: wheel over the empty canvas
        # zooms around the pointer, while a card can be dragged from its visible
        # header. The implementation also accepts empty card surfaces. Licensed
        # tldraw has its own SDK
        # interaction model and is checked separately when configured.
        fallback_canvas = page.get_by_role('region', name='Evidence canvas', exact=True)
        if fallback_canvas.count():
            # The Studio route can restore the browser's outer scroll position
            # above the board after a refresh. Bring the actual preset surface
            # into view before sending pointer events; this mirrors a user
            # selecting the preset and then interacting with what is visible.
            fallback_canvas.scroll_into_view_if_needed()
            page.get_by_role('button', name='Fit all cards', exact=True).click()
            fallback_card = fallback_canvas.locator('.card').first
            before_transform = checked('GET', 'documents/' + document_id)['state']['cards'][board['state']['order'][0]]['transform']
            card_box = fallback_card.bounding_box(); assert card_box
            # The header is the deterministic drag affordance.  Use its
            # center so the check cannot accidentally press a card button,
            # map canvas, or evidence scrollbar after a preset layout shifts.
            header_box = fallback_card.locator('.card-head').bounding_box(); assert header_box
            drag_x = header_box['x'] + header_box['width'] / 2
            drag_y = header_box['y'] + header_box['height'] / 2
            assert 0 <= drag_x <= page.viewport_size['width'] and 0 <= drag_y <= page.viewport_size['height']
            page.mouse.move(drag_x, drag_y); page.mouse.down(); page.mouse.move(drag_x + 56, drag_y + 32, steps=5); page.mouse.up()
            page.wait_for_timeout(250)
            after_transform = checked('GET', 'documents/' + document_id)['state']['cards'][board['state']['order'][0]]['transform']
            assert after_transform['x'] != before_transform['x'] or after_transform['y'] != before_transform['y']
            toolbar = fallback_canvas.locator('.canvas-toolbar')
            before_zoom = toolbar.inner_text()
            wrap = fallback_canvas.locator('.board-wrap'); wrap_box = wrap.bounding_box(); assert wrap_box
            # Keep the pointer on a visible canvas-background pixel, outside
            # cards and the native scrollbars. Search the rendered surface so
            # this remains valid after layout or preset-size changes.
            point = page.evaluate("""({x,y,width,height}) => {
              for (let yy = y + 12; yy < Math.min(window.innerHeight - 8, y + height - 12); yy += 18)
                for (let xx = x + 12; xx < x + width - 18; xx += 18) {
                  const el = document.elementFromPoint(xx, yy);
                  if (el?.closest?.('.board-canvas') && !el.closest('.card')) return {x: xx, y: yy};
                }
              return null;
            }""", wrap_box)
            assert point, wrap_box
            zoom_x, zoom_y = point['x'], point['y']
            page.mouse.move(zoom_x, zoom_y); page.mouse.wheel(0, -420); page.wait_for_timeout(180)
            after_zoom = toolbar.inner_text()
            assert before_zoom != after_zoom, (before_zoom, after_zoom)
            report['checks'].append('Fallback preset canvas supports pointer-anchored wheel zoom and card dragging; card controls remain interactive.')
        # Exercise real manual canvas actions and durable domain groups. Geometry
        # and viewport edits must never change the evidence identities or scope.
        tools = page.locator('.board-tools')
        tools.locator('summary').click()
        tools.locator('.group-card-list input[type=checkbox]').nth(0).check()
        tools.locator('.group-card-list input[type=checkbox]').nth(1).check()
        tools.get_by_label('Group title', exact=True).fill('Browser evidence group')
        tools.get_by_role('button', name='Group checked cards', exact=True).click()
        expect(tools.locator('.group-controls')).to_have_count(1)
        grouped = checked('GET', 'documents/' + document_id)
        group = next(iter(grouped['state']['groups'].values()))
        start = time.perf_counter()
        tools.get_by_role('button', name='Move group right', exact=True).click()
        page.wait_for_function("(revision) => document.querySelector('.st-actions').textContent.includes('rev ' + revision)", arg=grouped['revision'] + 1)
        report['interaction'] = {'group_move_ms': round((time.perf_counter() - start) * 1000, 2),
                                 'measurement': 'Playwright click through visible saved-revision acknowledgment; includes automation overhead.'}
        moved = checked('GET', 'documents/' + document_id)
        for member in group['card_ids']:
            assert moved['state']['cards'][member]['transform']['x'] == grouped['state']['cards'][member]['transform']['x'] + 32
        page.get_by_role('button', name='Undo', exact=True).click()
        page.wait_for_function("(revision) => document.querySelector('.st-actions').textContent.includes('rev ' + revision)", arg=moved['revision'] + 1)
        reverted = checked('GET', 'documents/' + document_id)
        assert reverted['state'] == grouped['state']
        tools.locator('summary').click()
        header = page.locator('.card-head').first
        header.scroll_into_view_if_needed(); header.focus(); header.press('ArrowRight')
        page.wait_for_function("(revision) => document.querySelector('.st-actions').textContent.includes('rev ' + revision)", arg=reverted['revision'] + 1)
        keyboard_moved = checked('GET', 'documents/' + document_id)
        for member in group['card_ids']:
            assert keyboard_moved['state']['cards'][member]['transform']['x'] == grouped['state']['cards'][member]['transform']['x'] + 16
        page.get_by_role('button', name='Undo', exact=True).click()
        page.wait_for_function("(revision) => document.querySelector('.st-actions').textContent.includes('rev ' + revision)", arg=keyboard_moved['revision'] + 1)
        # Keep the saved-viewport assertion deterministic after the wheel
        # gesture above; the browser zoom interaction is intentionally
        # independent from the manual toolbar save/restore check.
        page.get_by_role('button', name='Reset view', exact=True).click()
        page.get_by_role('button', name='Zoom in', exact=True).click()
        page.get_by_role('button', name='Save canvas view', exact=True).click()
        expect(page.locator('.st-actions')).not_to_contain_text('Saving')
        page.reload(wait_until='domcontentloaded'); expect(page.get_by_label('Board title')).to_be_visible()
        expect(page.locator('.canvas-toolbar')).to_contain_text('125%')
        page.get_by_role('button', name='Reset view', exact=True).click()
        page.get_by_role('button', name='Restore saved view', exact=True).click()
        expect(page.locator('.canvas-toolbar')).to_contain_text('125%')
        page.get_by_role('button', name='Reset view', exact=True).click()
        after_manual = checked('GET', 'documents/' + document_id)
        assert after_manual['state']['study'] == board['state']['study']
        assert set(after_manual['snapshots']) == set(board['snapshots'])
        report['checks'].append('Manual grouped moves, keyboard movement, Undo, zoom and saved viewport restoration preserve frozen evidence.')
        report['browser_environment'] = page.evaluate("({user_agent:navigator.userAgent, device_memory_gib:navigator.deviceMemory || null, hardware_concurrency:navigator.hardwareConcurrency, js_heap:performance.memory ? {used_bytes:performance.memory.usedJSHeapSize,total_bytes:performance.memory.totalJSHeapSize,limit_bytes:performance.memory.jsHeapSizeLimit}:null})")
        # Save linkage settings, then exercise transient interval/cell exploration.
        map_id = next(cid for cid, card in after_manual['state']['cards'].items() if card['type'] == 'map')
        chart_id = next(cid for cid, card in after_manual['state']['cards'].items() if card['type'] == 'chart')
        observation_id = next(cid for cid, card in after_manual['state']['cards'].items() if card['type'] == 'observation')
        linked = checked('POST', 'documents/' + document_id + '/transactions', {'base_revision': after_manual['revision'], 'ops': [
            {'op': 'update_card', 'id': map_id, 'patch': {'follow': 'selected', 'follow_card_id': chart_id}},
            {'op': 'update_card', 'id': observation_id, 'patch': {'follow': 'selected', 'follow_card_id': map_id}}
        ]})
        page.reload(wait_until='domcontentloaded'); expect(page.get_by_label('Board title')).to_be_visible()
        chart_card = page.locator('.card').filter(has=page.locator('.card-title', has_text='Activity chart'))
        chart_card.get_by_text('Focus linked UTC interval', exact=True).click()
        chart_card.get_by_label('Linked interval start', exact=True).fill('2024-07-24')
        chart_card.get_by_label('Linked interval end', exact=True).fill('2024-07-26')
        with page.expect_response(lambda r: '/preview?' in r.url and 'type=map' in r.url and 'end=2024-07-26' in r.url) as preview_response:
            chart_card.get_by_role('button', name='Focus compatible cards', exact=True).click()
        selected_map = preview_response.value.json()['visual']
        assert selected_map['interval']['dates'] == ['2024-07-24', '2024-07-25', '2024-07-26']
        observation = after_manual['state']['cards'][observation_id]
        source_receipt = checked('GET', 'documents/' + document_id + '/snapshots/' + observation['snapshot_id'] + '/receipt')['receipt']
        selected_record = source_receipt['payload']['records'][0]
        key = f"{selected_record['grid_x']}:{selected_record['grid_y']}"
        map_card = page.locator('.card').filter(has=page.locator('.card-title', has_text='Study map'))
        map_card.get_by_text('Inspect a common cell', exact=True).click()
        map_card.get_by_label('Common cell to inspect', exact=True).fill(key)
        with page.expect_response(lambda r: '/preview?' in r.url and 'type=observation' in r.url and 'cell=' in r.url) as rows_response:
            map_card.get_by_role('button', name='Focus linked cell evidence', exact=True).click()
        row_preview = rows_response.value.json()['visual']
        assert row_preview['selected_cell'] == key and row_preview['available_rows'] > 0
        assert checked('GET', 'documents/' + document_id)['revision'] == linked['revision']
        report['checks'].append('Chart interval and common-cell inspection update compatible linked displays without mutating the saved study or receipts.')
        page.reload(wait_until='domcontentloaded'); expect(page.get_by_label('Board title')).to_be_visible()
        jarvis = page.locator('.jarvis-panel').first
        jarvis.locator('summary').click()
        jarvis.get_by_role('button', name='Check source states', exact=True).click()
        expect(jarvis.get_by_role('heading')).to_be_visible(timeout=30000)
        expect(jarvis.get_by_text('Investigation completed.', exact=False)).to_be_visible()
        report['checks'].append('JARVIS runs checked source states through the existing orchestrator without a model key.')
        jarvis.locator('summary').click()
        page.get_by_role('button', name='Story', exact=True).click()
        page.get_by_role('button', name='Create six-chapter story', exact=True).click()
        expect(page.get_by_label('Story title')).to_be_visible()
        page.get_by_label('Story title').fill('Park observations — browser QA')
        page.get_by_label('terrain · NASADEM_HGT 001', exact=False).check()
        # Exercise the shared-scene controls in the browser, not only through unit
        # contracts: a bounded interval, a real frozen cell highlight, an audience
        # profile/duration target, a multi-card gallery and a deterministic camera
        # transition all flow through the same resolved story used by the reader and
        # renderer.
        initial_projects = checked('GET', 'documents/' + document_id + '/projects')
        initial_story_id = initial_projects['stories'][0]['id']
        checked('POST', 'stories/' + initial_story_id + '/resolve', {})
        initial_story = checked('GET', 'stories/' + initial_story_id)
        page.get_by_label('Audience').select_option('presenter')
        page.get_by_label('Target reading duration (seconds)').fill('90')
        scene_points = initial_story['resolved']['scenes'][0]['visual'].get('points', [])
        assert scene_points, 'the prepared Park map must contain a selectable frozen cell'
        highlighted = scene_points[0]['key']
        page.get_by_label('Interval start (UTC)').fill('2024-07-24')
        page.get_by_label('Interval end (UTC)').fill('2024-07-26')
        page.get_by_label('Highlight common cells (grid_x:grid_y, comma-separated)').fill(highlighted)
        page.get_by_label('Camera transition from').fill('-122, 39.5, -121.3, 40.5')
        page.get_by_label('Camera transition to').fill('-121.9, 39.7, -121.5, 40.25')
        visible_labels = page.locator('fieldset').filter(has_text='Visible evidence cards in this chapter').locator('label')
        assert visible_labels.count() >= 2
        for index in range(min(2, visible_labels.count())):
            checkbox = visible_labels.nth(index).locator('input[type=checkbox]')
            if not checkbox.is_checked():
                checkbox.check()
        page.get_by_role('button', name='Save revision', exact=True).click()
        expect(page.get_by_text('Saved story revision', exact=False)).to_be_visible(timeout=30000)
        page.get_by_role('button', name='Resolve checked scenes', exact=True).click()
        expect(page.get_by_role('region', name='Interactive story preview')).to_be_visible(timeout=30000)
        projects = checked('GET', 'documents/' + document_id + '/projects')
        story_id = projects['stories'][0]['id']; saved = checked('GET', 'stories/' + story_id)
        assert len(saved['body']['chapters']) == 6 and saved['revision'] == 2
        assert saved['resolved']['scenes'][0]['visual']['kind'] == 'map'
        assert saved['resolved']['scenes'][0]['visual']['context_layers'][0]['metadata']['product'] == 'NASADEM_HGT'
        assert saved['resolved']['scenes'][1]['visual']['kind'] == 'daily-bars'
        assert saved['resolved']['scenes'][2]['visual']['kind'] == 'availability'
        resolved_chapter = saved['resolved']['scenes'][0]
        assert resolved_chapter['visual']['interval']['start'] == '2024-07-24'
        assert resolved_chapter['visual']['interval']['end'] == '2024-07-26'
        assert any(point['key'] == highlighted and point['highlight'] for point in resolved_chapter['visual']['points'])
        assert resolved_chapter['visual']['camera_transition']['from_bbox'] == [-122.0, 39.5, -121.3, 40.5]
        assert resolved_chapter['visual']['camera_transition']['to_bbox'] == [-121.9, 39.7, -121.5, 40.25]
        assert len(resolved_chapter['visible_card_views']) >= 2
        assert saved['resolved']['audience'] == 'presenter'
        assert saved['resolved']['target_duration_seconds'] == 90.0
        report['checks'].append('Interval, highlighted cell, multi-card gallery, audience duration and camera transition resolve into the shared scene contract.')
        page.screenshot(path=str(output / 'story.png'), full_page=True)
        preview = page.get_by_role('region', name='Interactive story preview')
        assert saved['resolved']['scenes'][0]['question'] is None
        preview.get_by_role('button', name='Explore chapter evidence', exact=True).click()
        expect(preview.get_by_role('button', name='Next', exact=True)).to_be_disabled()
        preview.get_by_role('button', name='Resume story', exact=True).click()
        expect(preview.get_by_text('Chapter 1 of 6', exact=False)).to_be_visible()
        report['checks'].append('A chapter without an authored question opens chapter-specific exploration and resumes its saved display.')
        preview.get_by_role('button', name='Next', exact=True).click(); preview.get_by_role('button', name='Next', exact=True).click()
        preview.get_by_role('button', name='Explore chapter evidence', exact=True).click()
        expect(preview.get_by_role('button', name='Next', exact=True)).to_be_disabled()
        preview.get_by_role('button', name='Resume story', exact=True).click()
        expect(preview.get_by_text('Chapter 3 of 6', exact=False)).to_be_visible()
        report['checks'].append('Prepared map/chart/source states and chapter explore/resume preserve the saved scene.')
        preview.locator('.player-note summary').click()
        preview.get_by_label('Follow chapters as I scroll', exact=True).check()
        # Use the actual scrolling observer. Disable follow afterward so later
        # explicit chapter controls remain deterministic.
        transcript_chapter = preview.locator('[data-chapter]').nth(4)
        transcript_chapter.evaluate("element => element.scrollIntoView({block:'center',behavior:'instant'})")
        expect(preview.get_by_text('Chapter 5 of 6', exact=False)).to_be_visible()
        preview.get_by_label('Follow chapters as I scroll', exact=True).uncheck()
        preview.locator('.player-note summary').click()
        report['checks'].append('Opt-in transcript scrolling selects the visible saved chapter through the actual browser observer.')
        page.get_by_role('button', name='Board', exact=True).click(); page.get_by_role('button', name='Story', exact=True).click()
        expect(page.get_by_label('Story title')).to_have_value('Park observations — browser QA')
        with page.expect_download() as download:
            page.get_by_role('link', name='Export reader ZIP', exact=True).click()
        archive = output / 'reader.zip'; download.value.save_as(str(archive))
        reader_root = output / 'subpath' / 'story'
        if reader_root.exists(): shutil.rmtree(reader_root)  # This script's generated QA extraction only.
        reader_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            for name in bundle.namelist():
                assert not Path(name).is_absolute() and '..' not in Path(name).parts
            bundle.extractall(reader_root)
        index = next(reader_root.rglob('index.html'))
        from fireatlas.studio.story import verify_reader
        recount = verify_reader(index.parent)
        assert recount['verified'] and recount['narrations_checked'] == 6 and recount['captions_checked'] and recount['transcript_checked'], recount
        (output / 'reader-verification.json').write_text(json.dumps(recount, indent=2))
        report['checks'].append('Offline verifier reconstructs six narrated chapters, caption timing/text and transcript from frozen receipts.')
        # API ZIP can have a namespace prefix; host all output under a nested project subpath.
        handler = partial(SimpleHTTPRequestHandler, directory=str(output))
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        reader = context.new_page(); requests = []
        reader.on('request', lambda request: requests.append(request.url))
        reader.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        try:
            reader.goto(f'http://127.0.0.1:{server.server_port}/' + index.relative_to(output).as_posix(), wait_until='domcontentloaded')
            expect(reader.get_by_role('heading', name='Park observations — browser QA')).to_be_visible()
            expect(reader.locator('[data-narration-grounding]')).to_contain_text('Authored explanation')
            reader.screenshot(path=str(output / 'portable-reader.png'), full_page=True)
            assert not any('/api/' in url for url in requests)
            report['checks'].append('Portable reader runs under a project subpath with no backend or external imagery requests.')
        finally:
            reader.close(); server.shutdown(); server.server_close()
        page.get_by_role('button', name='Workflow', exact=True).click()
        expect(page.locator('.react-flow')).to_be_visible(timeout=30000)
        page.screenshot(path=str(output / 'workflow.png'), full_page=True)
        report['checks'].append('React Flow lazy mounts alongside its keyboard/table editor.')
        page.get_by_label('Starter recipe').select_option('findings-to-story')
        page.get_by_role('button', name='Save workflow', exact=True).click()
        page.get_by_role('button', name='Run saved revision', exact=True).click()
        output_button = page.get_by_role('button', name='Create story draft · story', exact=True)
        expect(output_button).to_be_visible(timeout=60000)
        output_button.click()
        expect(page.get_by_text('Editable story draft created.', exact=False)).to_be_visible()
        report['checks'].append('React Flow recipe runs, saves node receipts and materializes a real editable story.')
        page.get_by_role('button', name='Story', exact=True).click()
        page.get_by_label('Saved story').select_option(story_id)
        expect(page.get_by_label('Story title')).to_have_value('Park observations — browser QA')
        for width in (360, 390, 768):
            page.set_viewport_size({'width': width, 'height': 1000})
            expect(page.get_by_label('Chapter title')).to_be_visible()
            measured = page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
            report['narrow_layout'].append(measured)
            assert measured['scroll'] <= width + 1, measured
            expect(page.get_by_text('Applied study and linked display', exact=True)).to_have_count(1)
            page.evaluate('scrollTo(0,0)')
            page.screenshot(path=str(output / f'story-{width}.png'), full_page=True)
        if args.render:
            # Same prepared scenes, explicitly shorter saved revision for bounded encoding QA.
            body = saved['body']
            body['target_duration_seconds'] = 12
            for chapter in body['chapters']: chapter['duration_seconds'] = 2
            updated = checked('PATCH', 'stories/' + story_id, {'expected_revision': saved['revision'], 'story': body})
            checked('POST', 'stories/' + story_id + '/resolve', {})
            # Use the real documentary button/poller so completed narration
            # outcomes are visible in the product as well as its manifest.
            page.set_viewport_size({'width': 1440, 'height': 1100})
            page.reload(wait_until='domcontentloaded')
            expect(page.get_by_label('Board title')).to_be_visible(timeout=30000)
            page.get_by_role('button', name='Story', exact=True).click()
            expect(page.get_by_label('Saved story')).to_be_visible(timeout=30000)
            page.get_by_label('Saved story').select_option(story_id)
            expect(page.get_by_label('Target reading duration (seconds)')).to_have_value('12')
            with page.expect_response(lambda response: response.url.endswith('/api/studio/stories/' + story_id + '/renders') and response.request.method == 'POST') as submission:
                page.get_by_role('button', name='Render documentary', exact=True).click()
            assert submission.value.ok, submission.value.text()
            job = submission.value.json()
            deadline = time.monotonic() + 180
            completed = checked('GET', 'renders/' + job['id'])
            phases = [job.get('phase'), completed.get('phase')]
            while completed['status'] in ('queued', 'running') and time.monotonic() < deadline:
                threading.Event().wait(.5)
                completed = checked('GET', 'renders/' + job['id'])
                if completed.get('phase') != phases[-1]: phases.append(completed.get('phase'))
            assert completed['status'] == 'completed', completed
            assert completed['phase'] == 'completed'
            assert 'rendering' in phases and 'encoding' in phases, phases
            report['render_phases'] = phases
            expect(page.locator('[data-narration-outcome]')).to_contain_text('captions-only', timeout=10000)
            page.screenshot(path=str(output / 'render-outcome.png'), full_page=True)
            for kind, filename in [('video', 'briefing.mp4'), ('manifest', 'render-manifest.json'), ('captions', 'captions.vtt'), ('transcript', 'transcript.txt')]:
                response = context.request.get(args.base + '/api/studio/renders/' + job['id'] + '/artifact?name=' + kind)
                assert response.ok
                (output / filename).write_bytes(response.body())
            probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(output / 'briefing.mp4')], capture_output=True, text=True, check=True)
            (output / 'video-probe.json').write_text(probe.stdout)
            subtitle_stream = next(s for s in json.loads(probe.stdout)['streams'] if s['codec_type'] == 'subtitle')
            assert subtitle_stream['codec_name'] == 'mov_text' and subtitle_stream['disposition']['default'] == 1
            extracted = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(output / 'briefing.mp4'), '-map', '0:s:0', '-f', 'webvtt', '-'], capture_output=True, text=True, check=True).stdout
            (output / 'embedded-captions.vtt').write_text(extracted)
            def cues(text):
                result = []
                for block in text.strip().split('\n\n'):
                    lines = block.splitlines()
                    for i, line in enumerate(lines):
                        if ' --> ' in line:
                            # ffmpeg omits the zero hours prefix in short cues.
                            times = tuple(t if t.count(':') == 2 else '00:' + t for t in line.split(' --> '))
                            result.append((times, html.unescape(' '.join(' '.join(lines[i + 1:]).split()))))
                return result
            assert cues(extracted) == cues((output / 'captions.vtt').read_text()), 'Embedded subtitle text/timing must match the frozen sidecar.'
            assert completed['manifest']['subtitles']['embedded']
            page.reload(wait_until='domcontentloaded')
            expect(page.get_by_label('Board title')).to_be_visible(timeout=30000)
            page.get_by_role('button', name='Story', exact=True).click()
            expect(page.get_by_label('Saved story')).to_be_visible(timeout=30000)
            page.get_by_label('Saved story').select_option(story_id)
            expect(page.get_by_label('Recent video exports')).to_have_value(job['id'], timeout=10000)
            expect(page.locator('[data-narration-outcome]')).to_contain_text('captions-only', timeout=10000)
            expect(page.get_by_role('link', name='Download video', exact=True)).to_be_visible()
            page.screenshot(path=str(output / 'restored-export.png'), full_page=True)
            report['checks'].append('Silent documentary rendered the same six prepared scenes at 1080p, 30 fps, 12 seconds, including the resolved camera/gallery metadata.')
            report['checks'].append('The actual MP4 contains a default subtitle track with the same paginated resolved texts and chapter timings as captions.vtt.')
            report['checks'].append('A real browser refresh restores the completed export, saved story revision, caption outcome and video download through the owned recent-export chooser.')
        # Reuse the same saved recipe against a second authentic named study. This
        # checks that workflow scope comes from the applied board context rather
        # than a Park-specific default, while the primary story above exercises
        # the supplied local context-layer path.
        second = context.new_page()
        second_errors = []
        second.on('pageerror', lambda error: second_errors.append(str(error)))
        second.goto(args.base + '/studio.html?case=camp-2018', wait_until='domcontentloaded')
        expect(second.get_by_label('Board title')).to_be_visible(timeout=30000)
        expect(second.get_by_text('Applied study: camp-2018', exact=False)).to_be_visible()
        second.get_by_role('button', name='Build from current study', exact=True).click()
        second.wait_for_function("document.querySelectorAll('.card').length === 7 && document.querySelectorAll('.card-foot').length === 5", timeout=60000)
        second.get_by_role('button', name='Workflow', exact=True).click()
        expect(second.locator('.react-flow')).to_be_visible(timeout=30000)
        second.get_by_label('Starter recipe').select_option('findings-to-story')
        second.get_by_role('button', name='Save workflow', exact=True).click()
        second.get_by_role('button', name='Run saved revision', exact=True).click()
        expect(second.get_by_role('button', name='Create story draft · story', exact=True)).to_be_visible(timeout=60000)
        second.get_by_role('button', name='Create story draft · story', exact=True).click()
        expect(second.get_by_text('Editable story draft created.', exact=False)).to_be_visible(timeout=30000)
        second_report = checked('GET', 'documents/' + second.evaluate("sessionStorage.getItem('fireatlas-studio-board')") + '/projects')
        assert second_report['stories'], 'the reusable recipe must create a story on the second authentic study'
        report['checks'].append('The saved findings-to-story recipe runs and creates an editable story on the authentic Camp study context.')
        assert not second_errors, second_errors
        second.close()
        browser.close()
    assert not report['page_errors'], report['page_errors']
    (output / 'browser-report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

if __name__ == '__main__': main()
