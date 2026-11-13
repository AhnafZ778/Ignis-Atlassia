"""Read-only, bounded verification of retained qualification transfer provenance.

This checks the recorded processing chain, not NASA origin authentication or
independent scientific validity. Frozen transfer methods are not changed.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, timedelta
import hashlib
import io
import json
from pathlib import Path
import sqlite3

from . import acquisition, transfer
from .core import _normalized_row, calendar_row_included
from .qualification import digest
from .regions import REGIONS

MAX_PLANS = 10000
MAX_PLAN_BYTES = 2_000_000
MAX_MERGED_BYTES = 64_000_000
MAX_REQUESTS = 31
MAX_DETECTIONS = 1_000_000
# Verified batches are retained for one role at a time. Bound each role's
# resident set separately, while retaining a finite bound on total work.
MAX_ROLE_DETECTIONS = 2_000_000
MAX_CAPTURE_DETECTIONS = 4_000_000


def _hash(path):
    with path.open('rb') as f:
        result=hashlib.sha256()
        for chunk in iter(lambda:f.read(1024*1024),b''):result.update(chunk)
        return result.hexdigest()


def _inside(root, path):
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError('Evidence path escapes the campaign root.')
    return resolved


@contextmanager
def campaign_read_lock(root):
    """Coordinate standalone checks with cooperating acquisition writers."""
    import fcntl
    root = Path(root).resolve(strict=True)
    with (root/'.acquisition.lock').open('a') as guard:
        try: fcntl.flock(guard, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Campaign acquisition is active; retry source verification after it releases the lock.') from None
        yield


def _record(fingerprints, path, expected):
    if path in fingerprints and fingerprints[path] != expected:
        raise ValueError('Original evidence changed between reads.')
    fingerprints[path] = expected


def _plans(root, fingerprints):
    directory = root / 'plans'
    if not directory.is_dir():
        return {}
    paths = sorted(directory.glob('*.json'))
    if len(paths) > MAX_PLANS:
        raise ValueError('Plan inventory exceeds the verifier bound.')
    result = defaultdict(list)
    for p in paths:
        path = _inside(root, p)
        if path.stat().st_size > MAX_PLAN_BYTES:
            raise ValueError('Plan exceeds the verifier bound.')
        body_bytes = path.read_bytes()
        _record(fingerprints, path, hashlib.sha256(body_bytes).hexdigest())
        plan = json.loads(body_bytes)
        body = {k: v for k, v in plan.items() if k != 'plan_sha256'}
        if plan.get('schema') != 'fireatlas-acquisition-plan-v1' or digest(body) != plan.get('plan_sha256'):
            raise ValueError('Acquisition plan identity differs.')
        groups = defaultdict(list)
        for request in plan.get('requests', []):
            groups[(request.get('region'), request.get('source'), str(request.get('start', ''))[:7])].append(request)
        for key, reqs in groups.items():
            if len(reqs) > MAX_REQUESTS:
                raise ValueError('Monthly request count exceeds the verifier bound.')
            result[(*key, digest(reqs))].append(reqs)
    return result


def _month(root, batch, reqs, version, *, remaining_role, remaining_total, fingerprints):
    region, source, month = batch['region_id'], batch['source_id'], batch['month']
    first = date.fromisoformat(month + '-01')
    next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    expected = {first + timedelta(days=i) for i in range((next_month-first).days)}
    covered, receipts, versions = set(), [], set()
    merged_hash = hashlib.sha256()
    class Sink:
        def write(self, value):
            merged_hash.update(value.encode('utf-8'))
            return len(value)
    writer = None
    detections = {}
    all_paths = []
    for req in reqs:
        if (req.get('region') != region or req.get('source') != source or req.get('bbox') != list(REGIONS[region]['bbox'])
            or req.get('id') != digest({k: req[k] for k in ('region','bbox','source','start','days')})
            or type(req.get('days')) is not int or not 1 <= req['days'] <= 5):
            raise ValueError('Request identity or scope differs.')
        for i in range(req['days']):
            day = date.fromisoformat(req['start']) + timedelta(days=i)
            if day not in expected or day in covered:
                raise ValueError('Request days overlap or fall outside the month.')
            covered.add(day)
        csv_path, meta_path = root/'requests'/f"{req['id']}.csv", root/'requests'/f"{req['id']}.json"
        if not csv_path.is_file() or not meta_path.is_file():
            return None, 'request-original-or-receipt-missing', len(detections)
        csv_path, meta_path = _inside(root, csv_path), _inside(root, meta_path)
        if csv_path.stat().st_size > acquisition.WINDOW_LIMIT or meta_path.stat().st_size > MAX_PLAN_BYTES:
            raise ValueError('Request evidence exceeds the verifier bound.')
        if not acquisition.receipt_valid(root, req):
            return None, 'request-original-or-receipt-missing', len(detections)
        meta_body = meta_path.read_bytes(); receipt = json.loads(meta_body)
        receipts.append(receipt); versions.update(receipt['versions'])
        all_paths.append((csv_path, receipt['original_sha256']))
        meta_hash = hashlib.sha256(meta_body).hexdigest(); all_paths.append((meta_path, meta_hash))
        with csv_path.open(newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            if writer is None:
                writer = csv.DictWriter(Sink(), fieldnames=reader.fieldnames)
                writer.writeheader()
            elif reader.fieldnames != writer.fieldnames:
                raise ValueError('Request headers differ.')
            w,s,e,n = REGIONS[region]['bbox']
            for row in reader:
                if not (w <= float(row['longitude']) <= e and s <= float(row['latitude']) <= n):
                    continue
                writer.writerow(row)
                normalized = _normalized_row(row, source, '', '')
                if normalized['product_version'] == version:
                    # INSERT OR IGNORE gives the first occurrence of an ID to
                    # its first owner, even when later raw rows differ.
                    identity = normalized['detection_id']
                    if identity not in detections:
                        if len(detections) >= MAX_DETECTIONS:
                            raise ValueError('Detection input exceeds the verifier bound.')
                        if len(detections) >= remaining_role:
                            raise ValueError('Per-role capture detections exceed the verifier memory bound.')
                        if len(detections) >= remaining_total:
                            raise ValueError('Aggregate capture detections exceed the verifier processing bound.')
                        detections[identity] = normalized
    if covered != expected:
        return None, 'incomplete-request-days', len(detections)
    if sorted(versions) != [version]:
        return None, 'empty-unknown-or-mixed-version', len(detections)
    if digest(receipts) != batch['parent_sha256']:
        raise ValueError('Request receipt parent identity differs.')
    merged = root/'months'/f'{region}-{source}-{month}.csv'
    if not merged.is_file():
        return None, 'merged-original-missing', len(detections)
    merged = _inside(root, merged)
    if merged.stat().st_size > MAX_MERGED_BYTES:
        raise ValueError('Merged evidence exceeds the verifier bound.')
    actual_hash = _hash(merged)
    if actual_hash != batch['file_sha256'] or merged_hash.hexdigest() != actual_hash:
        raise ValueError('Merged original differs from reconstructed request bytes.')
    all_paths.append((merged, actual_hash))
    if any(_hash(path) != expected_hash for path, expected_hash in all_paths):
        raise ValueError('Original evidence changed during verification.')
    for path, expected_hash in all_paths:
        _record(fingerprints, path, expected_hash)
    return detections, None, len(detections)



def _verify_role(db, root, plans, inputs, role, cohort, total_detections, fingerprints):
    """Rebuild one role; retained detections and cells die with this frame."""
    state, reasons = 'verified', set()
    verified_batches = {}
    role_detections = 0
    ledger = [r for r in inputs['export_ledger'] if r['source']==cohort['source'] and r['version']==cohort['version']]
    if not ledger:
        state='partial'; reasons.add(f'{role}:no-exact-cohort-ledger')
    ledger_hashes = {r['file_sha256'] for r in ledger}
    for entry in ledger:
        matches = db.execute('''SELECT e.*, b.file_sha256, b.demo FROM source_exports e JOIN batches b ON e.batch_id=b.id
            WHERE e.region_id=? AND e.source_id=? AND e.month=? AND b.file_sha256=?''',
            (inputs['region'], cohort['source'], entry['month'], entry['file_sha256'])).fetchall()
        if len(matches) != 1:
            raise ValueError('Ambiguous or missing imported ledger batch.')
        batch = dict(matches[0])
        if (batch['demo'] or batch['complete_export'] != 1 or batch['coverage_basis'] != 'request-metadata'
            or json.loads(batch['product_versions_json']) != [cohort['version']]
            or tuple(batch[k] for k in ('west','south','east','north')) != REGIONS[inputs['region']]['bbox']
            or batch['request_start'] != entry['start'] or batch['request_end'] != entry['end']):
            raise ValueError('Imported ledger metadata differs.')
        candidates = plans.get((inputs['region'], cohort['source'], entry['month'], batch['request_sha256']), [])
        if not candidates:
            state='partial'; reasons.add(f"{role}:{entry['month']}:plan-unavailable"); continue
        # Identical request lists may appear in several plan files.
        if any(candidate != candidates[0] for candidate in candidates[1:]):
            raise ValueError('Ambiguous request plans.')
        verified, why, processed = _month(root, batch, candidates[0], cohort['version'],
                                remaining_role=MAX_ROLE_DETECTIONS-role_detections,
                                remaining_total=MAX_CAPTURE_DETECTIONS-total_detections,
                                fingerprints=fingerprints)
        total_detections += processed
        if why:
            state='partial'; reasons.add(f"{role}:{entry['month']}:{why}"); continue
        role_detections += len(verified)
        if role_detections > MAX_ROLE_DETECTIONS:
            raise ValueError('Per-role capture detections exceed the verifier memory bound.')
        if total_detections > MAX_CAPTURE_DETECTIONS:
            raise ValueError('Aggregate capture detections exceed the verifier processing bound.')
        verified_batches[batch['batch_id']] = verified
    if any(r['file_sha256'] not in ledger_hashes for r in inputs['observation_files']
           if r['source']==cohort['source'] and r['version']==cohort['version']):
        state='partial'; reasons.add(f'{role}:observation-file-outside-ledger')
    # Every original detection must exist, and its actual first owner
    # must itself be checked before its stored content can be trusted.
    for rows in verified_batches.values():
        for detection_id in rows:
            owner = db.execute('SELECT * FROM observations WHERE detection_id=?', (detection_id,)).fetchone()
            if owner is None:
                raise ValueError('Original detection is absent from the database snapshot.')
            if owner['batch_id'] not in verified_batches:
                state='partial'; reasons.add(f'{role}:first-owner-not-verified')
                continue
            original = verified_batches[owner['batch_id']].get(detection_id)
            if original is None:
                raise ValueError('Detection is absent from its recorded first-owner original.')
            for field in ('detection_id','source_id','platform','sensor','product_version','processing_level','acquisition_utc',
                          'lon','lat','scan_m','track_m','confidence_raw','frp_raw','daynight','thermal_anomaly_flag','grid_x','grid_y','raw_json'):
                if owner[field] != original[field]:
                    raise ValueError('Stored observation differs from its first-owner original: '+field)
    rebuilt = defaultdict(lambda: {'cells':set(), 'platforms':set(), 'files':set()})
    if ledger:
        first = min(r['month'] for r in inputs['export_ledger'])+'-01'
        last = max(r['month'] for r in inputs['export_ledger'])+'-01'
        end = (date.fromisoformat(last).replace(day=28)+timedelta(days=4)).replace(day=1).isoformat()
        w,s,e,n = REGIONS[inputs['region']]['bbox']
        months = {r['month'] for r in inputs['export_ledger']}
        records = db.execute('''SELECT o.*, b.file_sha256 FROM observations o JOIN batches b ON o.batch_id=b.id
            WHERE b.demo=0 AND o.source_id=? AND o.product_version=? AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
            AND o.acquisition_utc>=? AND o.acquisition_utc<?''',
            (cohort['source'],cohort['version'],w,e,s,n,first,end))
        for row in records:
            day = row['acquisition_utc'][:10]
            if day[:7] not in months or not calendar_row_included(row['raw_json']):
                continue
            owned = verified_batches.get(row['batch_id'], {}).get(row['detection_id'])
            if owned is None:
                state='partial'; reasons.add(f'{role}:observation-owner-not-verified'); continue
            for field in ('detection_id','source_id','platform','sensor','product_version','processing_level','acquisition_utc',
                          'lon','lat','scan_m','track_m','confidence_raw','frp_raw','daynight','thermal_anomaly_flag','grid_x','grid_y','raw_json'):
                if row[field] != owned[field]:
                    raise ValueError('Stored observation differs from its first-owner original: '+field)
            group = rebuilt[day]
            group['cells'].add((row['grid_x'],row['grid_y']))
            group['platforms'].add(transfer.platform_name(cohort['source'],row['platform']))
            group['files'].add(row['file_sha256'])
    expected = {r['date']: (set(map(tuple,r['cells'])), set(r['platforms']), set(r['file_sha256s']))
                for r in inputs['daily_cells'] if r['role']==role}
    actual = {day:(value['cells'], value['platforms'], value['files']) for day,value in rebuilt.items()}
    role_totals = {'ledger_months': len(ledger), 'reconstructed_days':len(actual), 'capture_days':len(expected)}
    if not any(reason.startswith(role+':') for reason in reasons) and actual != expected:
        raise ValueError('Original daily cell/platform union differs from captured values.')
    return role_totals, state, reasons, total_detections


def verify_capture(inputs, database, campaign_root, *, fingerprints_out=None):
    """Recount original requests against a single transfer capture.

    Caller supplies the transfer input, a SQLite database and its qualification
    campaign directory. Missing/legacy chains yield partial, and mismatches fail.
    The database is opened read-only in one consistent transaction. No science
    approval, observation-opportunity claim, or historical deployment follows.
    """
    transfer.validate(inputs, False)
    root = Path(campaign_root).resolve(strict=True)
    dbpath = Path(database).resolve(strict=True)
    fingerprints = {}
    plans = _plans(root, fingerprints)
    # A source may have two distinct versions; roles are retained explicitly.
    roles = [('source', inputs['source_cohort']), ('target', inputs['target_cohort'])]
    totals, state, reasons = {}, 'verified', []
    total_detections=0
    with sqlite3.connect(dbpath.as_uri()+'?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        fresh = transfer.capture(db, inputs['region'], inputs['source_cohort'], inputs['target_cohort'])
        for field in ('daily_cells', 'export_ledger', 'observation_files', 'notice_snapshot', 'months'):
            if fresh[field] != inputs[field]:
                raise ValueError('Transfer capture differs from the database snapshot: '+field)
        del fresh
        for role, cohort in roles:
            totals[role], role_state, role_reasons, total_detections = _verify_role(
                db, root, plans, inputs, role, cohort, total_detections, fingerprints)
            reasons.extend(role_reasons)
            if role_state != 'verified':state = 'partial'
        # Month-level checks alone miss changes to an earlier role while a
        # later role is processed. Recheck all read plans, receipts and CSVs.
        # This detects changes retained through this pass; it does not make an
        # uncooperative filesystem immutable after an individual file check.
        for path, expected in fingerprints.items():
            if _inside(root, path) != path or _hash(path) != expected:
                raise ValueError('Original evidence changed before verification completed.')
        if fingerprints_out is not None:
            fingerprints_out.update({str(path.relative_to(root)):expected for path,expected in fingerprints.items()})
        db.rollback()
    result = {'schema':'fireatlas-transfer-provenance-verification-v1', 'input_sha256':inputs['input_sha256'],
              'status':state, 'reasons':sorted(set(reasons)), 'roles':totals,
              'original_sources_reopened':state=='verified', 'scientific_admission':False,
              'historical_deployment_admitted':False,
              'scope':'Recorded request receipts, merged imports, read-only database snapshot and captured daily cell/platform unions; not independent review, proof of provider origin, or observation opportunity.'}
    result['result_sha256'] = digest(result)
    return result
