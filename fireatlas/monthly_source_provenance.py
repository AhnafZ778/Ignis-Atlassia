"""Verify monthly model cell-day inputs against original acquisition evidence.

This is a separate read-only evidence check, not a change to the frozen monthly
model or an assertion of scientific approval, provider identity or coverage.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

from . import comparability, comparability_v2, transfer, transfer_provenance
from .qualification import digest


def capture_for_bundle(bundle, database):
    """Capture the exact regional source pair in a read-only transaction."""
    inputs=bundle['inputs'];versions=inputs['versions']
    with closing(sqlite3.connect(Path(database).resolve(strict=True).as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        return transfer.capture(db,inputs['region'],{'source':'MODIS_SP','version':versions[0]},
                                {'source':'VIIRS_SNPP_SP','version':versions[1]})


def _verify_while_locked(bundle, capture, database, campaign_root, *, fingerprints_out=None):
    """Recount eligible monthly model counts against exact-cohort source files.

    The caller must hold the shared or exclusive campaign acquisition lock.
    ``capture`` must be a MODIS-to-S-NPP direct source capture from the same
    region and versions. The original-file verifier reopens and checks its
    underlying request receipts, merged files and first-owner observations.
    Only eligible monthly model cell-day counts are covered here: excluded
    periods, raw row totals and other diagnostics are not certified.
    """
    check = comparability_v2.verify(bundle)
    result = bundle['result']; inputs = bundle['inputs']
    if check['synthetic'] is not False or result.get('synthetic') is not False:
        raise ValueError('Authentic monthly evidence is required; synthetic results remain separate.')
    versions = inputs.get('versions')
    if (not isinstance(versions, list) or len(versions) != 2
            or capture.get('region') != inputs.get('region')
            or capture.get('source_cohort') != {'source':'MODIS_SP','version':versions[0]}
            or capture.get('target_cohort') != {'source':'VIIRS_SNPP_SP','version':versions[1]}):
        raise ValueError('Monthly and source capture region or exact cohort differs.')
    transfer_rows = transfer.validate(capture, False)
    eligible, _ = comparability.complete_months(inputs)
    eligible = [row for row in eligible if row['versions'] == versions]
    if len(eligible) != result['eligible_months']:
        raise ValueError('Monthly eligible support differs from the recounted experiment.')
    transfer_by_month = {row['date']: row for row in transfer_rows}
    cells = {(row['role'], row['date']): len(row['cells']) for row in capture['daily_cells']}
    month_days = {row['date']: row for row in inputs['days']}
    checked_days = 0
    for month in eligible:
        peer = transfer_by_month.get(month['date'])
        if peer is None or peer['modis'] != month['modis'] or peer['viirs'] != month['viirs']:
            raise ValueError('Eligible month lacks matching exact-cohort source counts.')
        # Strict monthly eligibility has already verified all expected UTC days.
        for stamp, day in month_days.items():
            if stamp[:7] != month['date']:
                continue
            for role, source in (('source','MODIS_SP'),('target','VIIRS_SNPP_SP')):
                if day['sources'][source]['cells'] != cells.get((role,stamp), 0):
                    raise ValueError('Eligible daily cell count differs from source capture.')
            checked_days += 1
    if fingerprints_out is None:
        source = transfer_provenance.verify_capture(capture, database, campaign_root)
    else:
        source = transfer_provenance.verify_capture(capture, database, campaign_root, fingerprints_out=fingerprints_out)
    state = 'verified' if eligible and source['status'] == 'verified' else 'partial'
    value = {'schema':'fireatlas-monthly-source-provenance-v1',
             'status':state, 'region':inputs['region'], 'versions':versions,
             'monthly_input_sha256':result['input_sha256'], 'monthly_result_sha256':result['result_sha256'],
             'source_capture_sha256':capture['input_sha256'], 'eligible_months':len(eligible),
             'eligible_utc_days_checked':checked_days, 'source_verification':source,
             'original_sources_reopened':state=='verified', 'scientific_admission':False,
             'scope':'Eligible monthly MODIS and S-NPP centroid-cell-day counts and their retained original request chain. Raw detection totals, excluded months, provider signatures, usable coverage, scientific review and future applicability are not verified.'}
    value['result_sha256'] = digest(value)
    return value


def verify(bundle, capture, database, campaign_root):
    """Recount under the shared campaign lock used by cooperating writers."""
    with transfer_provenance.campaign_read_lock(campaign_root):
        return _verify_while_locked(bundle, capture, database, campaign_root)


def verify_bundle(bundle, database, campaign_root):
    """Capture and recount one consistent source snapshot under the same lock."""
    with transfer_provenance.campaign_read_lock(campaign_root):
        capture = capture_for_bundle(bundle, database)
        return _verify_while_locked(bundle, capture, database, campaign_root)
