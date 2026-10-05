"""Prepared schematic views shared by web stories and video.

Only frozen receipts supply observations and values. No tiles, screenshots,
executable model output, or additional scientific estimation is used here.
"""
from __future__ import annotations

import datetime
import html
import math
import textwrap

from .errors import LimitExceeded, StudioError
from . import heat

SOURCES = ("MODIS_SP", "VIIRS_SNPP_SP")
COLORS = {"MODIS_SP": "#aa6500", "VIIRS_SNPP_SP": "#087b99", "shared": "#237745"}


def gallery_view(card, snapshot, receipt, chapter):
    """Freeze each visible card's actual display, with its own cited receipt.

    A chapter's explicit date/interval wins over a card's preview date; a
    sensor-pinned card retains its sensor. No new data or boundary is inferred.
    """
    display = card.get('display') or {}
    selection = {**({'day': display['day']} if display.get('day') else {}), **(chapter.get('selection') or {})}
    source = display.get('source') or chapter.get('source_filter') or 'joint'
    view = {'id': card['id'], 'type': card['type'], 'title': card['title'], 'text': card['text'],
            'snapshot_id': snapshot['id'] if snapshot else None, 'frozen': bool(snapshot),
            'display': display, 'selection': selection, 'source_filter': source}
    view['visual'] = None
    if snapshot and receipt:
        if card['type'] == 'map' and display.get('preview') == 'heat' and not (selection.get('start') or selection.get('end')):
            view['visual'] = heat.prepare(snapshot, receipt, selection, source)
        else:
            view['visual'] = prepared(card, [snapshot], {snapshot['id']: receipt}, {'selection': selection, 'source_filter': source})
    return view


def selected_dates(scope, chapter):
    selection = chapter.get('selection') or {}
    day = selection.get('day') or scope.get('day')
    interval = bool(selection.get('start') or selection.get('end'))
    start, end = (selection.get('start'), selection.get('end')) if interval else (scope['start'], scope['end'])
    try:
        first, last = datetime.date.fromisoformat(start), datetime.date.fromisoformat(end)
        if day:
            datetime.date.fromisoformat(day)
        for highlighted in selection.get('highlight_dates') or []:
            datetime.date.fromisoformat(highlighted)
            if not start <= highlighted <= end:
                raise ValueError('highlight outside interval')
    except (TypeError, ValueError):
        raise StudioError('Use valid UTC dates and both endpoints of a chapter interval.', code='scene-context') from None
    if first > last or not scope['start'] <= start <= end <= scope['end'] or (day and not start <= day <= end):
        raise StudioError('The chapter date and interval must stay inside its frozen evidence.', code='scene-context')
    return day, start, end, interval


def prepared(card, snapshots, receipts, chapter):
    """Keep selection explicit and bounded within the frozen study."""
    source = chapter.get("source_filter") or "joint"
    if source not in ("joint", *SOURCES):
        raise StudioError("Prepared scenes support both sensors or one standard sensor.", code="scene-context")
    for snapshot in snapshots:
        receipt = (receipts or {}).get(snapshot["id"])
        if not receipt:
            continue
        scope, payload = snapshot["scope"], receipt["payload"]
        requested = chapter.get("study") or {}
        if requested.get("bbox") is not None and requested["bbox"] != scope["bbox"]:
            raise StudioError("A chapter cannot change the boundary of its frozen evidence.", code="scene-context")
        selection = chapter.get("selection") or {}
        day, interval_start, interval_end, has_interval = selected_dates(scope, chapter)
        frames = payload.get("frames", [])
        if card and card['type'] in ('calendar', 'chart') and payload.get('days') and 'value' in payload['days'][0]:
            days = [{k: d.get(k) for k in ('date', 'value', 'evidence_state', 'estimate_type', 'coverage_state')}
                    for d in payload['days'] if interval_start <= d['date'] <= interval_end]
            return {'kind': 'calendar', 'scope': scope, 'day': day, 'days': days,
                    'interval': {'start': interval_start, 'end': interval_end}, 'highlight_dates': selection.get('highlight_dates') or [],
                    'unit': snapshot['method']['unit'], 'domain': [0, max((d['value'] for d in days if d['value'] is not None), default=0)],
                    'label': 'Harmonized values retain observed, estimated and unknown evidence states. Source visibility does not change this metric.'}
        if card and card['type'] in ('observation', 'source-evidence', 'table'):
            records = payload.get('observations') or payload.get('records') or []
            if records:
                selected = [r for r in records if interval_start <= (r.get('date') or r.get('acquisition_utc', '')[:10]) <= interval_end
                            and (has_interval or not day or (r.get('date') or r.get('acquisition_utc', '')[:10]) == day)
                            and (source == 'joint' or r.get('source_id') == source)]
                if selection.get('cell'):
                    if any(r.get('grid_x') is None or r.get('grid_y') is None for r in records):
                        raise StudioError('This frozen row receipt has no common-cell assignments for selection.', code='scene-context')
                    selected = [r for r in selected if f"{r['grid_x']}:{r['grid_y']}" == selection['cell']]
                return {'kind': 'source-rows', 'scope': scope, 'day': day, 'source': source, 'unit': 'original source records',
                        'rows': [{k: r.get(k) for k in ('source_id', 'acquisition_utc', 'longitude', 'latitude', 'lon', 'lat', 'confidence', 'confidence_raw', 'frp_mw', 'frp_raw', 'product_version')}
                                 for r in selected[:8]], 'available_rows': len(selected),
                        **({'selected_cell': selection['cell']} if selection.get('cell') else {}),
                        'label': 'First source rows in this frozen receipt; bounded preview. Full records and raw-field scope are retained in the cited evidence.'}
        if card and card["type"] == "map" and frames:
            selected_frames = ([f for f in frames if interval_start <= f['date_utc'] <= interval_end] if has_interval
                               else [f for f in frames if f['date_utc'] == (day or frames[0]['date_utc'])])
            frame = next((f for f in selected_frames if f["date_utc"] == day), None) if day else (selected_frames[0] if selected_frames else None)
            if frame is None:
                raise StudioError("This frozen receipt has no frame for the selected UTC interval.", code="scene-context")
            # An interval is a union of the frozen cell-days. We retain exact
            # dates/state membership while drawing each common cell once.
            point_by_key = {}
            for selected_frame in selected_frames or [frame]:
                for cell in selected_frame["cells"]:
                    if source != "joint" and source not in cell["sources"]:
                        continue
                    key = f"{cell.get('grid_x')}:{cell.get('grid_y')}"
                    current = point_by_key.setdefault(key, {**cell, "sources": [], "observed_dates": [], "source_dates": {s: [] for s in SOURCES}})
                    current['sources'] = sorted(set(current['sources']) | set(cell['sources']))
                    current["observed_dates"].append(selected_frame["date_utc"])
                    for sensor in cell['sources']:
                        current['source_dates'][sensor].append(selected_frame['date_utc'])
            points = list(point_by_key.values())
            cell_days = sum(sum(1 for c in selected_frame["cells"] if source == "joint" or source in c["sources"]) for selected_frame in selected_frames or [frame])
            if cell_days > 10000:
                raise LimitExceeded("A scene draws at most 10,000 frozen common cells without sampling.", code="scene-limit")
            camera = chapter.get('camera') or {}
            viewport = camera.get('bbox') or scope['bbox']
            if (not isinstance(viewport, list) or len(viewport) != 4 or
                    any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in viewport)):
                raise StudioError('A map camera uses four finite west/south/east/north coordinates.', code='scene-context')
            w, s, e, n = viewport
            a, b, c, d = scope['bbox']
            if not (a <= w < e <= c and b <= s < n <= d):
                raise StudioError('Camera focus must stay inside the frozen study boundary; it does not redefine the calculation.', code='scene-context')
            transition = None
            if camera.get('from_bbox') is not None or camera.get('to_bbox') is not None:
                start_box, end_box = camera.get('from_bbox'), camera.get('to_bbox')
                if not (isinstance(start_box, list) and isinstance(end_box, list) and len(start_box) == 4 and len(end_box) == 4):
                    raise StudioError('Animated camera focus needs two four-coordinate bounds.', code='scene-context')
                for box in (start_box, end_box):
                    if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in box):
                        raise StudioError('Animated camera coordinates must be finite.', code='scene-context')
                    bw, bs, be, bn = box
                    if not (a <= bw < be <= c and b <= bs < bn <= d):
                        raise StudioError('Animated camera focus must stay inside the frozen study boundary.', code='scene-context')
                transition = {'from_bbox': start_box, 'to_bbox': end_box, 'duration_seconds': chapter.get('duration_seconds', 20)}
            highlights = set(selection.get("highlight_cells") or [])
            highlight_dates = set(selection.get("highlight_dates") or [])
            if highlights - set(point_by_key):
                raise StudioError('A highlighted cell is absent from the selected frozen date/interval and sensor.', code='scene-context')
            point_views = [{"lon": c["longitude"], "lat": c["latitude"], "sources": c["sources"], "key": f"{c.get('grid_x')}:{c.get('grid_y')}",
                            "observed_dates": c['observed_dates'], 'source_dates': c['source_dates'],
                            "highlight": f"{c.get('grid_x')}:{c.get('grid_y')}" in highlights or bool(highlight_dates.intersection(c['observed_dates']))} for c in points]
            visual = {"kind": "map", "scope": scope, "day": frame["date_utc"], "source": source,
                    "viewport": viewport, "camera_transition": transition,
                    "points": point_views,
                    "products": frame["products"], 'date_states': [{'date': f['date_utc'], 'products': f['products']} for f in selected_frames],
                    "unit": "occupied common cell-days in the UTC interval" if has_interval else "occupied common cells on this UTC date", "count": cell_days,
                    "label": "Schematic common-cell centers; no basemap, perimeter or exposure footprint"}
            if has_interval:
                visual["interval"] = {"start": interval_start, "end": interval_end, "dates": [f["date_utc"] for f in selected_frames or [frame]], "cell_days": cell_days}
            if transition is None:
                visual.pop("camera_transition", None)
            return visual
        if card and card["type"] == "chart" and frames:
            # These integer counts already exist in replay. Drawing them does
            # not change completeness, deduplication or the analysis metric.
            values = [{"date": f["date_utc"], "value": f["joint_cell_days"] if source == "joint" else f["products"][source]["cell_days"],
                       "states": {s: f["products"][s]["state"] for s in SOURCES}} for f in frames if interval_start <= f['date_utc'] <= interval_end]
            return {"kind": "daily-bars", "scope": scope, "values": values, "domain": [0, max((f["joint_cell_days"] for f in frames), default=0)],
                    'interval': {'start': interval_start, 'end': interval_end}, 'highlight_dates': selection.get('highlight_dates') or [],
                    "day": day, "source": source, "unit": "occupied common cells per UTC date",
                    "label": "Recorded replay counts; positive partial records are not complete daily coverage"}
        if card and card["type"] == "timeline" and payload.get("days"):
            return {"kind": "availability", "scope": scope, "day": day,
                    "days": [{"date": d["date"], "products": d["products"]} for d in payload["days"] if interval_start <= d['date'] <= interval_end],
                    'interval': {'start': interval_start, 'end': interval_end}, 'highlight_dates': selection.get('highlight_dates') or [],
                    "unit": "collected-export state", "label": "Export completeness does not establish observation opportunity"}
    return None


def camera_matrix(visual, progress=0):
    """Map-only affine crop in SVG coordinates; headings and units never move."""
    camera = visual.get('camera_transition')
    if not camera:
        return [1, 0, 0, 1, 0, 0]
    w, s, e, n = visual['scope']['bbox']
    t = max(0, min(1, progress))
    a, b, c, d = [first + (last - first) * t for first, last in zip(camera['from_bbox'], camera['to_bbox'])]
    sx, sy = (e - w) / (c - a), (n - s) / (d - b)
    return [sx, 0, 0, sy, 90 * (1 - sx) + 770 * (w - a) / (c - a), 105 * (1 - sy) + 330 * (d - n) / (d - b)]


def svg(scene):
    """Designed, escaped SVG. Its exact bytes can be consumed in every player."""
    visual = scene.get("visual") or {}
    paired = [view for view in scene.get('visible_card_views', []) if (view.get('visual') or {}).get('kind') == 'heat']
    if (scene.get('gallery_version') in (1, 2) and visual.get('kind') == 'map' and len(paired) == 2
            and {view['visual']['source'] for view in paired} == set(SOURCES)
            and not visual.get('camera_transition') and not visual.get('interval') and not visual.get('context_layers')):
        return heat_comparison(scene, paired)
    map_camera = scene.get('figure_version', 1) >= 2
    fb = scene.get("fallback") or {}
    escape = lambda text: html.escape(str(text))
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" role="img"',
           f' aria-label="{escape(scene["title"])}">', '<rect width="960" height="540" fill="#fbf7ef"/>',
           '<defs><pattern id="unknown" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#edf1ea"/><path d="M-2 2L2-2M0 8L8 0M6 10L10 6" stroke="#7c8689" fill="none"/></pattern></defs>']

    def text(x, y, value, size=15, color="#172b31"):
        out.append(f'<text x="{x}" y="{y}" font-family="sans-serif" font-size="{size}" fill="{color}">{escape(value)}</text>')

    text(32, 42, scene["title"][:62], 26)
    visible_views = scene.get("visible_card_views") or []
    if len(visible_views) > 0:
        # Visible cards are a resolved composition, not an instruction to
        # fetch more data. The same compact gallery is embedded in the SVG
        # consumed by the reader, Remotion and the local renderer.
        for index, view in enumerate(visible_views[:4]):
            x = 650 + (index % 2) * 145
            y = 22 + (index // 2) * 31
            out.append(f'<rect x="{x}" y="{y}" width="134" height="24" rx="4" fill="#e7f0ed" stroke="#9aaca5"/>')
            text(x + 7, y + 16, f'{view.get("type", "card")}: {view.get("title", "")}'[:22], 10, "#24414a")
    scope = visual.get("scope") or fb.get("scope")
    if scope:
        text(32, 72, f'UTC {scope["start"]} – {scope["end"]}', 16, "#46606a")
    kind = visual.get("kind")
    if kind == 'image':
        out.append(f'<image x="60" y="88" width="840" height="350" preserveAspectRatio="xMidYMid meet" href="data:{visual["mime"]};base64,{visual["data"]}"/>')
        for index, line in enumerate(textwrap.wrap('Attribution: ' + visual['attribution'] + ' · License: ' + visual['license'], 100)[:3]):
            text(32, 463+index*19, line, 13)
        text(32, 526, 'Uploaded authored illustration · not a scientific measurement', 13)
    elif kind == "map":
        w, s, e, n = scope['bbox'] if map_camera and visual.get('camera_transition') else (visual.get('viewport') or scope["bbox"])
        out.append('<rect x="90" y="105" width="770" height="330" fill="#e9efed" stroke="#8e9c9a"/>')
        out.append('<defs><clipPath id="map-crop"><rect x="90" y="105" width="770" height="330"/></clipPath></defs>')
        if map_camera:
            matrix = ' '.join(f'{v:.12g}' for v in camera_matrix(visual))
            out.append(f'<g clip-path="url(#map-crop)"><g data-map-camera="true" transform="matrix({matrix})">')
        for layer in visual.get('context_layers', []):
            a,b,c,d = layer['metadata']['bounds']
            x, y = 90+770*(a-w)/(e-w), 435-330*(d-s)/(n-s)
            width, height = 770*(c-a)/(e-w), 330*(d-b)/(n-s)
            crop = '' if map_camera else ' clip-path="url(#map-crop)"'
            out.append(f'<image x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" preserveAspectRatio="none" opacity="0.65"{crop} href="data:{layer["mime"]};base64,{layer["data"]}"/>')
        for point in visual["points"]:
            if not w <= point['lon'] <= e or not s <= point['lat'] <= n:
                continue  # Display crop only. Count and evidence scope retain the full study frame.
            x = 90 + 770 * (point["lon"] - w) / (e - w)
            y = 435 - 330 * (point["lat"] - s) / (n - s)
            sources = point["sources"]
            stroke = '#d14b30' if point.get('highlight') else 'none'
            if visual["source"] == "joint" and len(sources) == 2:
                out.append(f'<rect x="{x-2.5:.2f}" y="{y-2.5:.2f}" width="5" height="5" fill="{COLORS["shared"]}" stroke="{stroke}" stroke-width="2"/>')
            elif visual["source"] == "VIIRS_SNPP_SP" or (visual["source"] == "joint" and "MODIS_SP" not in sources):
                out.append(f'<path d="M{x:.2f} {y-3:.2f}l3 3-3 3-3-3Z" fill="{COLORS["VIIRS_SNPP_SP"]}" stroke="{stroke}" stroke-width="2"/>')
            else:
                out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" fill="{COLORS["MODIS_SP"]}" stroke="{stroke}" stroke-width="2"/>')
        if map_camera:
            out.append('</g></g>')
        interval = visual.get('interval') or {}
        interval_label = f'{interval.get("start")}–{interval.get("end")} UTC' if interval.get('start') != interval.get('end') else f'{visual["day"]} UTC'
        count_unit = 'occupied common cell-days' if interval and map_camera else 'occupied common cells'
        text(90, 458, f'{interval_label} · {visual["count"]} {count_unit} · {visual["source"]}', 16)
        text(32, 491, '● MODIS   ◆ VIIRS S-NPP   ■ Shared common cell', 16)
        if visual.get('context_layers'):
            labels = [f'{l["metadata"]["product"]} {l["metadata"]["version"]} · {l["metadata"].get("composite_start") or l["metadata"].get("product_year") or ",".join(l["metadata"].get("date_range", [])) or "static terrain"}' for l in visual['context_layers']]
            text(32, 507, 'Dated context: ' + ' / '.join(labels), 10)
        text(32, 518, visual["label"] + (' · camera crop; count retains full study' if list(scope['bbox']) != list(visual.get('viewport') or scope['bbox']) else ''), 11, "#46606a")
        text(90, 97, 'Animated display crop within the frozen study' if map_camera and visual.get('camera_transition') else f'{n}°N', 13)
        if not map_camera or not visual.get('camera_transition'):
            text(90, 478, f'{w}° longitude → {e}°', 12)
    elif kind == 'calendar':
        days = visual['days']
        offset = datetime.date.fromisoformat(days[0]['date']).weekday() if days else 0
        for index, value in enumerate(days[:42]):
            x, y = 55 + ((index + offset) % 7) * 123, 130 + ((index + offset) // 7) * 55
            unknown = value['value'] is None
            out.append(f'<rect x="{x}" y="{y}" width="115" height="48" rx="4" fill="{"url(#unknown)" if unknown else "#edf1ea"}" stroke="#83948e"/>')
            text(x+7, y+17, value['date'][5:], 12)
            text(x+7, y+35, 'unknown' if unknown else f'{value["value"]:.2f}', 13)
            if value.get('estimate_type') in ('scaled', 'estimated') or value.get('evidence_state') == 'scaled':
                out.append(f'<path d="M{x+2} {y+44}h111" stroke="#a65c00" stroke-width="3" stroke-dasharray="4 3"/>')
        text(32, 104, visual['unit'] + (f' · bounded preview: first 42 of {len(days)} dates' if len(days) > 42 else ''), 14)
        text(32, 489, 'Hatch: unknown · dashed amber edge: estimate · labeled values preserve UTC dates', 13)
        for index, line in enumerate(textwrap.wrap(visual['label'], 105)[:2]): text(32, 511+index*17, line, 12)
    elif kind == 'source-rows':
        text(32, 111, f'Previewing {len(visual["rows"])} of {visual["available_rows"]} records available in this receipt', 17)
        text(32, 148, 'Source / acquisition UTC                       lon, lat                 confidence / FRP MW / version', 14)
        for index, row in enumerate(visual['rows']):
            source_name = str(row['source_id']).replace('_SP', '')
            coords = f'{row.get("longitude") if row.get("longitude") is not None else row.get("lon")}, {row.get("latitude") if row.get("latitude") is not None else row.get("lat")}'
            details = f'{row.get("confidence") if row.get("confidence") is not None else row.get("confidence_raw")} / {row.get("frp_mw") if row.get("frp_mw") is not None else row.get("frp_raw")} / {row.get("product_version")}'
            text(32, 184+index*32, f'{source_name} {row["acquisition_utc"]}', 13)
            text(420, 184+index*32, coords[:28], 13)
            text(720, 184+index*32, details[:29], 13)
        for index, line in enumerate(textwrap.wrap(visual['label'], 100)[:2]): text(32, 500+index*18, line, 12)
    elif kind == "daily-bars":
        values, maximum = visual["values"], visual["domain"][1] or 1
        spacing = 800 / max(1, len(values))
        out.append('<path d="M80 110V420H880" stroke="#46606a" fill="none"/>')
        for index, value in enumerate(values):
            x, height = 82 + index * spacing, 280 * value["value"] / maximum
            incomplete = any(state != "complete_export" for state in value["states"].values())
            out.append(f'<rect x="{x:.2f}" y="{420-height:.2f}" width="{max(2, spacing-5):.2f}" height="{max(1,height):.2f}" fill="{COLORS.get(visual["source"], "#2b59c3")}"/>' )
            if incomplete:
                out.append(f'<rect x="{x:.2f}" y="430" width="{max(2,spacing-5):.2f}" height="9" fill="url(#unknown)"/>')
            if index % max(1, len(values)//7) == 0:
                text(round(x), 460, value["date"][5:], 13)
        text(80, 98, f'Study-fixed domain 0–{visual["domain"][1]} {visual["unit"]}', 15)
        text(32, 495, visual["label"], 13, "#46606a")
        text(32, 518, 'Hatched strip: at least one incomplete source export. Zero is a stored count, not proof of no fire.', 12)
    elif kind == "availability":
        days = visual["days"]
        spacing = 690 / max(1, len(days))
        for row, source in enumerate(SOURCES):
            y = 160 + row * 120
            text(32, y+28, source, 16)
            for index, day in enumerate(days):
                product = day["products"][source]
                complete = product["state"] == "complete_export"
                color = COLORS[source] if product["detections"] else "#cbd6d2"
                out.append(f'<rect x="{230+index*spacing:.2f}" y="{y}" width="{max(2,spacing-3):.2f}" height="60" fill="{color if complete else "url(#unknown)"}" stroke="#82918e"/>')
                if row == 1 and index % max(1, len(days)//7) == 0:
                    text(round(230+index*spacing), y+90, day["date"][5:], 13)
        text(32, 435, 'Sensor color: complete export with detections · pale: complete export with zero detections', 14)
        text(32, 466, 'Hatch: incomplete or unknown export. Processing notices remain in the cited evidence.', 14)
        text(32, 512, visual["label"], 13, "#46606a")
    else:
        rows = fb.get("rows") or fb.get("bars") or []
        for index, row in enumerate(rows[:10]):
            value = "unknown" if row["value"] is None else row["value"]
            text(32, 120+index*32, f'{row["label"][:45]}: {value} {row.get("unit", fb.get("unit")) or ""} · {row["state"]}', 15)
        if not rows:
            card = scene.get('card') or {}
            prose = card.get('text') if card.get('type') in ('quote', 'text', 'note-question', 'method-note', 'chapter-frame') else None
            for index, line in enumerate(textwrap.wrap(prose or scene.get("narration_text") or scene.get("caption", ""), 80)[:10]):
                text(32, 120+index*30, line, 20)
        text(32, 514, 'Frozen evidence schematic · see transcript and source receipts', 14, "#46606a")
    out.append('</svg>')
    return ''.join(out)


def heat_comparison(scene, views):
    """The same readable paired figure is used by Story, reader and film."""
    escape = lambda value: html.escape(str(value))
    scope = views[0]['visual']['scope']
    compatible = all(view['visual']['scope']['bbox'] == scope['bbox']
                     and view['visual']['day'] == views[0]['visual']['day']
                     and view['visual']['domain'] == views[0]['visual']['domain']
                     and view['visual']['receipt_sha256'] == views[0]['visual']['receipt_sha256']
                     and view['visual']['release_id'] == views[0]['visual']['release_id'] for view in views)
    if not compatible:
        raise StudioError('Paired heat images require the same frozen boundary, date and scale.', code='scene-context')
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" role="img"',
           f' aria-label="{escape(scene["title"])} — paired frozen heat maps">',
           '<rect width="960" height="540" fill="#fbf7ef"/>']
    def text(x, y, value, size=15, color='#172b31'):
        out.append(f'<text x="{x}" y="{y}" font-family="sans-serif" font-size="{size}" fill="{color}">{escape(value)}</text>')
    text(32, 40, scene['title'][:62], 26)
    if scene.get('gallery_version') == 1:
        text(32, 67, f"{views[0]['visual']['day']} UTC · two sensors, one frozen study", 17, '#46606a')
    else:
        study = {'park-2024': 'Park study', 'camp-2018': 'Camp study', 'grove-2025': 'Grove study'}.get(scope.get('case'), scope.get('region') or 'Custom study')
        text(32, 67, f"{study} · {views[0]['visual']['day']} UTC · two sensors, one frozen study", 17, '#46606a')
    for index, view in enumerate(views):
        heat_view = view['visual']
        x = 32 + index * 464
        label = '● MODIS' if heat_view['source'] == 'MODIS_SP' else '◆ S-NPP VIIRS' if heat_view['source'] == 'VIIRS_SNPP_SP' else '■ Combined detections'
        text(x, 102, label, 22)
        out.append(f'<rect x="{x}" y="116" width="432" height="260" rx="8" fill="#102b35" stroke="#8bb0b4"/>')
        out.append(f'<image x="{x+10}" y="126" width="412" height="240" preserveAspectRatio="none" href="data:image/png;base64,{heat_view["data"]}"/>')
        text(x, 403, f"{heat_view['count']} occupied common cells", 17)
        relevant = [heat_view['source']] if heat_view['source'] in SOURCES else list(SOURCES)
        states = ' / '.join(heat_view['products'][source]['state'] for source in relevant)
        for line, value in enumerate(textwrap.wrap(states.replace('_', ' '), 42)[:2]):
            text(x, 424 + line * 16, value, 13, '#46606a')
    domain = views[0]['visual']['domain'][1]
    text(32, 467, f'0–{domain:.2f} Gaussian occupied-cell concentration · 1 km sigma · 3 sigma support', 15)
    for index in range(96):
        position = index / 95 * 4
        at = min(3, math.floor(position))
        fraction = position - at
        rgb = [math.floor(a + (b-a)*fraction+.5) for a,b in zip(heat.STOPS[at], heat.STOPS[at+1])]
        out.append(f'<rect x="{32+index*2}" y="478" width="2" height="9" fill="rgb({rgb[0]},{rgb[1]},{rgb[2]})"/>')
    text(237, 488, 'Scale fixed across all study dates and both sensors', 13)
    text(32, 513, heat_view['label'], 13, '#46606a')
    if scene.get('gallery_version') == 1:
        text(32, 532, f"Study UTC {scope['start']}–{scope['end']} · full boundaries retained · heat is a display statistic", 12, '#46606a')
    else:
        bounds = ', '.join(f'{coordinate:g}' for coordinate in scope['bbox'])
        text(32, 532, f"Study UTC {scope['start']}–{scope['end']} · bounds W,S,E,N [{bounds}]", 12, '#46606a')
    out.append('</svg>')
    return ''.join(out)
