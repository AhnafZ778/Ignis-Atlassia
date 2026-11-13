"""Compare a refit to frozen daily research without changing release gates.

The byte-bound original is checked separately from these exploratory numerical
comparisons. Matching numbers do not constitute independent scientific review.
"""
from __future__ import annotations

import math
import platform
import sys
from importlib import metadata
from .qualification import digest

ABSOLUTE_TOLERANCE = 1e-8
RELATIVE_TOLERANCE = 1e-6
MAX_DIFFERENCE_EXAMPLES = 20


def runtime_fingerprint():
    versions = {}
    for name in ('statsmodels', 'numpy', 'scipy', 'pandas', 'threadpoolctl'):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    try:
        from threadpoolctl import threadpool_info
        pools = [{key: item.get(key) for key in
                  ('user_api', 'internal_api', 'num_threads', 'prefix', 'version', 'architecture')}
                 for item in threadpool_info()]
    except ImportError:
        pools = None
    return {'python': sys.version.split()[0], 'platform': platform.platform(),
            'libraries': versions, 'threadpools': pools}


def compare(original, rebuilt):
    """Compare all fields except the derived result hash and fold environment.

    Strings, keys, list order, integer counts and booleans are exact. Floating
    point values use fixed exploratory tolerances; nonfinite values fail. Fold
    environment metadata is reported separately, not considered a fit result.
    A changed gate boolean, partition or input must fail even if floats agree.
    """
    report = {'exact_mismatches': 0, 'numeric_mismatches': 0,
              'numeric_values': 0, 'max_absolute_difference': 0.0,
              'max_relative_difference': 0.0, 'absolute_difference_overflow': False, 'examples': []}

    def issue(path, reason, numeric=False):
        report['numeric_mismatches' if numeric else 'exact_mismatches'] += 1
        if len(report['examples']) < MAX_DIFFERENCE_EXAMPLES:
            report['examples'].append({'path': path, 'reason': reason})

    def walk(a, b, path):
        if isinstance(a, dict) and isinstance(b, dict):
            if set(a) != set(b):
                issue(path, 'object keys differ')
            for key in sorted(set(a) & set(b)):
                if path == '$' and key == 'result_sha256':
                    continue
                if path == '$' and key in ('inputs', 'platform_counts', 'protocol', 'review', 'experimental_review'):
                    try:
                        if digest(a[key]) != digest(b[key]):
                            issue(path + '.' + key, 'input identity differs')
                    except (ValueError, TypeError):
                        issue(path + '.' + key, 'invalid input values')
                    continue
                if key == 'environment' and path.startswith('$.folds['):
                    continue
                walk(a[key], b[key], path + '.' + key)
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                issue(path, 'list length differs')
            for i, (left, right) in enumerate(zip(a, b)):
                walk(left, right, f'{path}[{i}]')
        elif isinstance(a, bool) or isinstance(b, bool):
            if type(a) is not type(b) or a != b:
                issue(path, 'boolean differs')
        elif type(a) is int and type(b) is int:
            if a != b:
                issue(path, 'integer differs')
        elif type(a) is float and type(b) is float:
            left, right = float(a), float(b)
            report['numeric_values'] += 1
            if not math.isfinite(left) or not math.isfinite(right):
                issue(path, 'nonfinite value', numeric=True)
                return
            absolute = abs(left - right)
            magnitude = max(abs(left), abs(right))
            relative = abs(left / magnitude - right / magnitude) if magnitude else 0.0
            if math.isfinite(absolute) and not report['absolute_difference_overflow']:
                report['max_absolute_difference'] = max(report['max_absolute_difference'], absolute)
            elif not math.isfinite(absolute):
                report['absolute_difference_overflow'] = True
                report['max_absolute_difference'] = None
            report['max_relative_difference'] = max(report['max_relative_difference'], relative)
            if not math.isclose(left, right, rel_tol=RELATIVE_TOLERANCE, abs_tol=ABSOLUTE_TOLERANCE):
                issue(path, 'outside fixed tolerances', numeric=True)
        elif type(a) is not type(b) or a != b:
            issue(path, 'value or type differs')

    walk(original, rebuilt, '$')
    report['numerically_consistent'] = (report['exact_mismatches'] == 0 and report['numeric_mismatches'] == 0)
    report['tolerances'] = {'absolute': ABSOLUTE_TOLERANCE, 'relative': RELATIVE_TOLERANCE,
                            'rule': 'maximum of absolute and relative * maximum magnitude'}
    return report
