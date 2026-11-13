"""Recounted historical readiness; no historical deployment is qualified.

The earlier continuity contract is frozen. This module does not treat an
arbitrary admission flag, a hash-shaped label, or overlap approval as authority
for extrapolation. The historical model and source-era opportunity protocol
have not yet been scientifically qualified: candidate estimates are inspected
but never admitted by this version.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
import copy
import math
import re

from . import transfer, transfer_opportunity
from .qualification import digest

SCHEMA = 'fireatlas-historical-readiness-v3'
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_MONTH = re.compile(r'[0-9]{4}-[0-9]{2}\Z')
MAX_CANDIDATES = 12000


def _month(value):
    if not isinstance(value, str) or not _MONTH.fullmatch(value):
        raise ValueError('A canonical UTC calendar month is required.')
    first = date.fromisoformat(value + '-01')
    if first.isoformat()[:7] != value:
        raise ValueError('A canonical UTC calendar month is required.')
    return first


def _observations(inputs):
    """Derive individual-cohort complete-month counts from recounted cells.

    The transfer input asserts request-backed exports and source fingerprints.
    This recount does not reopen original CSVs or verify their provenance.
    An asserted complete zero is not an observation opportunity or no fire.
    """
    transfer.validate(inputs, inputs.get('synthetic') is True)
    cohorts = [transfer.cohort(inputs['source_cohort']), transfer.cohort(inputs['target_cohort'])]
    supported = transfer.ledger_months(inputs['export_ledger'], cohorts)
    notices = transfer.frozen_notices(inputs['notice_snapshot'])
    counts = {}
    for row in inputs['daily_cells']:
        # The frozen transfer validator accepts both compact and dashed ISO
        # dates. Group their canonical date, not their original spelling.
        key = (row['role'], date.fromisoformat(row['date']).isoformat()[:7])
        counts[key] = counts.get(key, 0) + len(row['cells'])
    result = []
    for role, cohort in zip(('source', 'target'), cohorts):
        for month in sorted(supported[cohort]):
            first = _month(month)
            last = first + timedelta(days=monthrange(first.year, first.month)[1])
            start = datetime.fromisoformat(first.isoformat() + 'T00:00:00+00:00')
            end = datetime.fromisoformat(last.isoformat() + 'T00:00:00+00:00')
            if any(source == cohort[0] and lo < end and hi >= start for source, lo, hi in notices):
                continue
            result.append({'kind': 'observation', 'month': month,
                'region': inputs['region'], 'cohort': {'source': cohort[0], 'version': cohort[1]},
                'count': counts.get((role, month), 0), 'units': transfer.UNITS,
                'grid': transfer.GRID, 'input_sha256': inputs['input_sha256'],
                'original_source_files_verified': False})
    return result


def _validate_candidates(candidates, observations, evidence):
    if not isinstance(candidates, list) or len(candidates) > MAX_CANDIDATES:
        raise ValueError('Bounded explicit candidate list required.')
    source = {(r['month'], digest(r['cohort'])): r for r in observations}
    seen = set()
    for row in candidates:
        if not isinstance(row, dict) or row.get('kind') != 'counterfactual-estimate':
            raise ValueError('Explicit counterfactual estimate candidate required.')
        _month(row.get('month'))
        if row['month'] in seen:
            raise ValueError('Duplicate estimate month.')
        seen.add(row['month'])
        if row.get('region') != evidence['region'] or row.get('source_cohort') != evidence['source_cohort'] or row.get('target_cohort') != evidence['target_cohort']:
            raise ValueError('Candidate region and ordered cohorts must match the recounted bridge.')
        if (row['month'], digest(row['target_cohort'])) in source:
            raise ValueError('An estimate cannot overwrite an observation.')
        original = source.get((row['month'], digest(row['source_cohort'])))
        if original is None:
            raise ValueError('A complete original source month is required.')
        model = row.get('model')
        identity = row.get('model_sha256')
        if (not isinstance(model, dict) or not isinstance(identity, str) or not _HASH.fullmatch(identity)
                or identity != digest(model) or model.get('transfer_evidence_sha256') != evidence['result_sha256']
                or model.get('region') != row['region'] or model.get('source_cohort') != row['source_cohort']
                or model.get('target_cohort') != row['target_cohort']):
            raise ValueError('A content-bound model with exact evidence and scope is required.')
        if row.get('input_sha256') != digest(original):
            raise ValueError('Candidate input must bind the recounted source observation.')
        interval = row.get('interval')
        value = row.get('value')
        if (not isinstance(interval, list) or len(interval) != 2
                or any(type(n) not in (float, int) or not math.isfinite(n) or n < 0 for n in [value, *interval])
                or not interval[0] <= value <= interval[1]):
            raise ValueError('Finite nonnegative ordered interval containing the estimate required.')


def build(evidence, packets=(), *, conclusions=None, candidates=None, original_directory=None):
    """Recount supplied overlap and source capture without admitting deployment.

    Even a passing independently reviewed overlap does not approve historical
    deployment. Input candidates are validated as untrusted proposals; they are
    never returned as admitted estimates or used to overwrite observations.
    """
    if not isinstance(evidence, dict) or evidence.get('schema') != 'fireatlas-direct-transfer-opportunity-v2':
        raise ValueError('Full recounted transfer-opportunity evidence required.')
    admission = transfer_opportunity.admission(evidence, conclusions, packets, original_directory=original_directory)
    observations = _observations(evidence['count_evidence']['inputs'])
    proposed = [] if candidates is None else candidates
    _validate_candidates(proposed, observations, evidence)
    result = {'schema': SCHEMA, 'region': evidence['region'],
        'source_cohort': copy.deepcopy(evidence['source_cohort']),
        'target_cohort': copy.deepcopy(evidence['target_cohort']),
        'synthetic': evidence['synthetic'], 'original_source_files_verified': False,
        'source_provenance_status': 'asserted-fingerprints-not-reopened', 'transfer_evidence_sha256': evidence['result_sha256'],
        'overlap_admission': admission, 'observations': observations, 'estimates': [],
        'candidate_count': len(proposed), 'candidate_sha256': digest(proposed),
        'historical_deployment_admitted': False, 'continuous_claim': False,
        'unresolved': ['separately-frozen-historical-deployment-protocol',
            'source-era-observation-opportunity-and-applicability-evidence',
            'source-bound-historical-model-and-uncertainty-recount',
            'independent-historical-protocol-and-conclusion-review'],
        'interpretation': 'Monthly values are recounted from the supplied transfer capture; original source CSVs were not reopened. Candidate estimates are withheld pending independent historical qualification; asserted export completeness does not establish fire absence or full observation opportunity.'}
    result['result_sha256'] = digest(result)
    return result


def verify(result, evidence, packets=(), *, conclusions=None, candidates=None, original_directory=None):
    rebuilt = build(evidence, packets, conclusions=conclusions, candidates=candidates, original_directory=original_directory)
    if digest(rebuilt) != digest(result):
        raise ValueError('Historical readiness recount differs.')
    return {'verified': True, 'result_sha256': result['result_sha256'], 'historical_deployment_admitted': False}
