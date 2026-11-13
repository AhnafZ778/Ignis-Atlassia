"""Exact regional/annual thermal comparisons; presentation never supplies values."""
from collections import Counter, defaultdict
from datetime import date, timedelta
import math
import re

from .core import GRID_METERS, TO_GRID
from .replay import FROM_GRID

METHOD = {'id': 'firms-common-product-peak-day-comparison-v1', 'unit': 'occupied 1 km cells',
          'filter': 'One FIRMS product; complete query windows; EPSG:6933 centroid grid; UTC daily ranking. No burned-area or causal inference.'}


def narrative_issue(payload, text):
    """Check explicit count relations against frozen panels, without rewriting prose."""
    panels=payload['panels']
    # Explicit weather superlatives need an actual corresponding extremum.
    # This checks bounded panel references, not general climate/causal prose.
    weather_extrema=(('air_temperature_max_c',r'hottest|warmest|highest (?:maximum |air )?temperature',max),
                     ('air_temperature_max_c',r'coolest|coldest|lowest (?:maximum |air )?temperature',min),
                     ('rainfall_7d_mm',r'wettest|highest (?:rainfall|precipitation)',max),
                     ('rainfall_7d_mm',r'driest|lowest (?:rainfall|precipitation)',min),
                     ('wind_max_kmh',r'strongest winds?|highest wind(?: speed)?',max))
    for sentence in re.split(r'(?<=[.!?;])\s+',text.lower()):
        if sentence.endswith('?') or re.search(r'\b(?:hypothesis|may|might|could|possibly|would)\b',sentence):continue
        subjects=list(re.finditer(r'\b(?:20\d{2}|first|earliest|middle|second|latest|last|final|third|most recent)\b',sentence))
        for field,pattern,extreme in weather_extrema:
            for match in re.finditer(r'\b(?:'+pattern+r')\b',sentence):
                preceding=[s for s in subjects if 0<=match.start()-s.end()<=100 and not re.search(r'[,;]',sentence[s.end():match.start()])]
                nearby=preceding or [s for s in subjects if 0<=s.start()-match.end()<=35]
                if not nearby:continue
                subject=(preceding[-1] if preceding else nearby[0]).group()
                if subject.isdigit():indices=[i for i,p in enumerate(panels) if p['year']==int(subject)]
                elif subject in {'first','earliest'}:indices=[0]
                elif subject in {'latest','last','final','third','most recent'}:indices=[2] if subject=='third' else [len(panels)-1]
                elif subject=='second':indices=[1]
                else:indices=[1] if len(panels)==3 else []
                if len(indices)!=1 or indices[0]>=len(panels):continue
                values=[p.get('weather',{}).get(field) for p in panels]
                if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in values):
                    return 'Unavailable weather cannot establish a highest or lowest window.'
                if values[indices[0]]!=extreme(values):return 'The stated weather extremum contradicts the frozen panel summaries; recheck which window has the highest or lowest value.'
    for sentence in re.split(r'(?<=[.!?])\s+', text.lower()):
        if sentence.endswith('?') or not re.search(r'\b(?:counts?|cells?|detections?|records?)\b',sentence):continue
        equality=bool(re.search(r'\b(?:equal|identical|unchanged|same (?:number|counts?)|no (?:difference|change))\b',sentence))
        upward=bool(re.search(r'\bincreas\w*\b',sentence))
        downward=bool(re.search(r'\bdecreas\w*\b',sentence))
        if not any((equality,upward,downward)):continue
        if re.search(r'\b(?:hypothesis|may|might|could|possibly|would)\b',sentence):continue
        years=list(dict.fromkeys(int(value) for value in re.findall(r'\b(20\d{2})\b',sentence)))
        selected=[panel for panel in panels if not years or panel['year'] in years]
        if len(years)>1 and len({panel['year'] for panel in selected})==len(selected):
            selected.sort(key=lambda panel:years.index(panel['year']))
        if len(selected)<2:continue
        if any(panel['state']!='queried' for panel in selected):return 'A missing peak cannot establish an equality or trend.'
        metric='detections' if re.search(r'\b(?:detections?|records?)\b',sentence) and not re.search(r'\bcells?\b',sentence) else 'occupied_cells'
        values=[panel[metric] for panel in selected]
        negated_equality=bool(re.search(r'\bnot\s+(?:all\s+)?(?:equal|identical|unchanged|the same)\b',sentence))
        if equality and (len(set(values))==1)==negated_equality:return 'The equality or no-change statement contradicts the cited frozen panel counts.'
        continuous=bool(re.search(r'\b(?:across|each|every|steadily|throughout)\b',sentence)) and 'overall' not in sentence
        if upward and not downward and (values[-1]<=values[0] or (continuous and any(b<a for a,b in zip(values,values[1:])))):return 'The cited counts do not increase in the stated sequence; retain intermediate decreases.'
        if downward and not upward and (values[-1]>=values[0] or (continuous and any(b>a for a,b in zip(values,values[1:])))):return 'The cited counts do not decrease in the stated sequence; retain intermediate increases.'
    by_year={panel['year']:panel for panel in panels if sum(other['year']==panel['year'] for other in panels)==1}
    for match in re.finditer(r'([+-]?\d+(?:\.\d+)?)\s*(?:cells?\s*)?(over|above|below|vs\.?|versus|more than|fewer than)\s*(20\d{2})\b',text.lower()):
        before=re.findall(r'\b(20\d{2})\b',text[:match.start()])
        if not before:continue
        target,reference=by_year.get(int(before[-1])),by_year.get(int(match[3]))
        if not target or not reference:continue
        amount=float(match[1])*(-1 if match[2] in {'below','fewer than'} else 1)
        if amount!=target['occupied_cells']-reference['occupied_cells']:return 'The stated occupied-cell difference uses the wrong reference year; recheck the two cited panel counts.'
    return None


def cell_key(row):
    x, y = TO_GRID.transform(row['longitude'], row['latitude'])
    return math.floor(x / GRID_METERS), math.floor(y / GRID_METERS)


def daily_counts(records, first, last):
    """A complete successful query can contain zero returned rows on a date."""
    counts, cells = Counter(), defaultdict(set)
    for row in records:
        day = row['acquisition_utc'][:10]
        if not first <= day <= last:
            raise ValueError('A comparison record is outside its requested UTC interval.')
        counts[day] += 1
        cells[day].add(cell_key(row))
    start, end = date.fromisoformat(first), date.fromisoformat(last)
    return [{'date': (start + timedelta(days=i)).isoformat(),
             'detections': counts[(start + timedelta(days=i)).isoformat()],
             'occupied_cells': len(cells[(start + timedelta(days=i)).isoformat()])}
            for i in range((end - start).days + 1)]


def build_comparison(studies, *, mode='regions', rank_by='occupied_cells', top_days=1):
    if mode not in {'regions', 'annual_peaks', 'saved'} or rank_by not in {'occupied_cells', 'detections'}:
        raise ValueError('Choose a regional comparison or annual peaks with one supported ranking metric.')
    if not 1 <= top_days <= 3 or not 1 <= len(studies) <= 6:
        raise ValueError('Compare up to six panels and up to three peak days per year.')
    products = {study['check']['product'] for study in studies}
    if len(products) != 1 or None in products:
        raise ValueError('Every comparison panel must use the same explicit FIRMS product.')
    panels, searches = [], []
    for study in studies:
        check = study['check']
        first, last = study['start'], study['end']
        if check.get('available_start') != first or check.get('available_end') != last:
            raise ValueError('A peak comparison requires source dates covering the entire requested interval.')
        if mode == 'annual_peaks':
            year = date.fromisoformat(first).year
            if first != f'{year}-01-01' or last != f'{year}-12-31':
                raise ValueError('An annual peak requires one complete calendar year, including every UTC date.')
        windows = check.get('source_windows', [])
        if windows:
            cursor = date.fromisoformat(first)
            for window in sorted(windows, key=lambda value: value['start']):
                if window['start'] != cursor.isoformat() or window['end'] < window['start'] or not window.get('sha256'):
                    raise ValueError('Comparison query windows must cover the interval exactly without gaps or overlaps.')
                cursor = date.fromisoformat(window['end']) + timedelta(days=1)
            if cursor != date.fromisoformat(last) + timedelta(days=1):
                raise ValueError('Comparison query windows do not cover the full requested interval.')
        records = check['records']
        west, south, east, north = study['bbox']
        for row in records:
            if not all(isinstance(row.get(k), (int, float)) and not isinstance(row[k], bool) and math.isfinite(row[k]) for k in ('longitude', 'latitude')):
                raise ValueError('Comparison coordinates must be finite.')
            if not west <= row['longitude'] <= east or not south <= row['latitude'] <= north:
                raise ValueError('A comparison record is outside its requested boundary.')
        days = daily_counts(records, first, last)
        positive = sorted((item for item in days if item[rank_by] > 0), key=lambda item: (-item[rank_by], item['date']))
        selected = positive[:top_days] if mode == 'annual_peaks' else [None]
        # All-zero years have no winner; retain the queried interval explicitly.
        if not selected:
            selected = [None]
        searches.append({'label': study['label'], 'start': first, 'end': last, 'bbox': study['bbox'],
                         'product': check['product'], 'source_windows': check.get('source_windows', []),
                         'source_csv_sha256': check.get('source_csv_sha256'), 'days': days,
                         'query_state': 'complete_query', 'records': records})
        for rank, winner in enumerate(selected, 1):
            day = winner['date'] if winner else None
            chosen = [row for row in records if row['acquisition_utc'][:10] == day] if day else ([] if mode == 'annual_peaks' else records)
            by_cell = defaultdict(list)
            for row in chosen:
                by_cell[cell_key(row)].append(row)
            hot = []
            for (gx, gy), rows in sorted(by_cell.items(), key=lambda item: (-len(item[1]), item[0]))[:3]:
                lon, lat = FROM_GRID.transform((gx + .5) * GRID_METERS, (gy + .5) * GRID_METERS)
                hot.append({'longitude': lon, 'latitude': lat, 'detections': len(rows), 'grid_x': gx, 'grid_y': gy})
            tied = [item['date'] for item in positive if winner and item[rank_by] == winner[rank_by]]
            panels.append({'label': study['label'], 'year': int(first[:4]), 'day': day,
                           'start': day or first, 'end': day or last, 'search_start': first, 'search_end': last,
                           'bbox': study['bbox'], 'reference': study.get('reference'), 'product': check['product'],
                           'sensor': check['sensor'], 'records': chosen, 'detections': len(chosen),
                           'occupied_cells': len(by_cell), 'hotspots': hot,
                           'rank': rank if winner else None, 'tied_dates': tied,
                           'state': 'no_positive_day' if mode == 'annual_peaks' and not winner else 'queried',
                           'weather': {'status': 'not_requested'}})
    if len(panels) > 6:
        raise ValueError('This comparison exceeds six panels. Ask for fewer years or peak days.')
    if mode == 'annual_peaks':
        years = sorted({int(study['start'][:4]) for study in studies})
        if len(years) != len(studies):
            raise ValueError('Choose distinct calendar years for an annual peak comparison.')
    baseline = panels[0]
    for index,panel in enumerate(panels):
        valid = panel['state'] == baseline['state'] == 'queried'
        panel['cell_delta'] = panel['occupied_cells'] - baseline['occupied_cells'] if valid else None
        panel['record_delta'] = panel['detections'] - baseline['detections'] if valid else None
        previous=panels[index-1] if index else None
        previous_valid=previous and previous['state']==panel['state']=='queried'
        panel['previous_cell_delta']=panel['occupied_cells']-previous['occupied_cells'] if previous_valid else None
        panel['delta_reference']={'panel_index':0,'label':baseline['label'],'year':baseline['year'],'day':baseline['day']}
        panel['previous_reference']={'panel_index':index-1,'label':previous['label'],'year':previous['year'],'day':previous['day']} if previous else None
    return {'title': 'Peak days across years' if mode == 'annual_peaks' else 'Regional thermal comparison',
            'mode': mode, 'rank_by': rank_by, 'product': next(iter(products)), 'panels': panels,
            'searches': searches, 'baseline_panel_index':0, 'tie_policy': 'Descending requested metric; equal scores ordered by earliest UTC date; all tied dates retained.',
            'note': 'Same-product thermal observations. Peak days rank recorded activity, not fire severity. Different areas and peak dates are not matched fire events. Successful zero-row queries do not establish no fire or clear-sky opportunity.'}
