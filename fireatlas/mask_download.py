"""Create an exact frozen NASA download checklist; optionally use Earthdata login.

No credentials are written by this module. Acquisition is a user-run operation.
"""
from __future__ import annotations

import argparse
import csv
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

from .granules import load


def checklist(case_id=None):
    inventory = load()
    result = {}
    for identifier, case in inventory['cases'].items():
        if case_id and case_id != identifier:
            continue
        for product in case['products']:
            for granule in product['granules']:
                url = granule.get('download_url')
                if not url:
                    raise ValueError(f"Missing URL for {granule['producer_id']}")
                filename = Path(urlsplit(url).path).name
                key = (identifier, filename)
                result[key] = {
                    'case_id': identifier, 'product': product['product'],
                    'version': product['version'], 'role': product['role'],
                    'filename': filename, 'start_utc': granule['start_utc'],
                    'end_utc': granule['end_utc'], 'cmr_id': granule['cmr_id'],
                    'download_url': url,
                }
    if not result:
        raise ValueError('Unknown case identifier')
    return list(result.values())


def _candidate_urls(row):
    """Yield the frozen URL and the current LAADS form when applicable.

    A few older checklist rows still point at ``ladsweb.modaps.eosdis.nasa.gov``.
    LAADS has moved those files behind the Earthdata Cloud hostname, so a failed
    legacy URL gets one equivalent, filename-based fallback.  The checklist is
    deliberately left unchanged as the historical source record.
    """
    url = row['download_url']
    yield url
    parsed = urlsplit(url)
    if parsed.netloc == 'ladsweb.modaps.eosdis.nasa.gov':
        yield (
            'https://data.laadsdaac.earthdatacloud.nasa.gov/prod-lads/'
            f"{row['product']}/{row['filename']}"
        )


def _format_bytes(value):
    value = float(value)
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if value < 1024 or unit == 'GiB':
            return f'{value:.1f} {unit}'
        value /= 1024


def _missing_rows(rows, output):
    return [
        row for row in rows
        if not (output / row['filename']).is_file()
        or (output / row['filename']).stat().st_size == 0
    ]


def _clean_partials(output):
    """Remove temporary files left by an interrupted Earthaccess run."""
    candidates = set(output.glob('partial_*'))
    candidates.update(output.glob('.*.partial-*'))
    removed = 0
    for path in candidates:
        if path.is_file():
            path.unlink()
            removed += 1
    return removed


def _download_one(session, row, output, retries, connect_timeout, read_timeout, label):
    """Download one row atomically, isolating retries to this file."""
    target = output / row['filename']
    last_error = 'no URL candidate was attempted'

    for url_index, url in enumerate(_candidate_urls(row)):
        for attempt in range(1, retries + 1):
            temporary = None
            try:
                print(
                    f'[{label}] {row["filename"]}: attempt {attempt}/{retries}',
                    flush=True,
                )
                with tempfile.NamedTemporaryFile(
                    dir=output,
                    prefix=f'.{target.name}.partial-',
                    delete=False,
                ) as stream:
                    temporary = Path(stream.name)

                with session.get(
                    url,
                    stream=True,
                    allow_redirects=True,
                    timeout=(connect_timeout, read_timeout),
                ) as response:
                    response.raise_for_status()
                    content_type = response.headers.get('Content-Type', '').lower()
                    if 'text/html' in content_type:
                        raise RuntimeError(
                            f'HTML response received (status {response.status_code})'
                        )
                    expected_header = response.headers.get('Content-Length')
                    expected = int(expected_header) if expected_header and expected_header.isdigit() else None
                    written = 0
                    with temporary.open('wb') as destination:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                destination.write(chunk)
                                written += len(chunk)

                if written == 0:
                    raise IOError('empty response body')
                if expected is not None and written != expected:
                    raise IOError(f'incomplete body: received {written} of {expected} bytes')
                temporary.replace(target)
                print(f'[{label}] {row["filename"]}: OK ({_format_bytes(written)})', flush=True)
                return True, None
            except Exception as error:  # requests errors vary by transport/backend
                last_error = f'{type(error).__name__}: {error}'
                if temporary is not None and temporary.exists():
                    temporary.unlink()
                if attempt < retries:
                    time.sleep(min(2 ** (attempt - 1), 8))

        if url_index == 0:
            print(
                f'[{label}] {row["filename"]}: trying LAADS Earthdata URL fallback',
                flush=True,
            )

    return False, last_error


def _download_missing(rows, output, retries, connect_timeout, read_timeout):
    """Download only absent files and return rows that still failed."""
    missing = _missing_rows(rows, output)
    if not missing:
        print(f'All {len(rows)} checklist files are already present.')
        return []

    try:
        import earthaccess
    except ImportError:
        raise SystemExit(
            'Run: uv run --with earthaccess==0.19.0 '
            'python -m fireatlas.mask_download --download'
        ) from None

    try:
        auth = earthaccess.login(strategy='interactive', persist=False)
    except Exception as error:  # authentication uses requests and can fail before a response
        detail = str(error)
        if 'NameResolutionError' in detail or 'Temporary failure in name resolution' in detail:
            raise SystemExit(
                'Earthdata Login could not resolve urs.earthdata.nasa.gov. '
                'This is a local DNS/network failure, before NASA received the login. '
                'Restore internet/VPN/proxy DNS, verify with '
                '`getent hosts urs.earthdata.nasa.gov`, then rerun the same command.'
            ) from None
        raise SystemExit(
            f'Earthdata Login failed ({type(error).__name__}). '
            'Check the network and retry; credentials were not stored by this command.'
        ) from None
    if not auth.authenticated:
        raise SystemExit('Earthdata login did not succeed; no coverage state was changed.')

    session = earthaccess.get_requests_https_session()
    failures = []
    print(f'{len(missing)} files remain; existing files will be skipped.', flush=True)
    for index, row in enumerate(missing, start=1):
        success, error = _download_one(
            session,
            row,
            output,
            retries=retries,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            label=f'{index}/{len(missing)}',
        )
        if not success:
            failures.append((row, error))
            print(f'[{index}/{len(missing)}] {row["filename"]}: FAILED — {error}', flush=True)
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=('park-2024', 'grove-2025'))
    parser.add_argument('--output', type=Path, default=Path('NASA_data/fire_masks'))
    parser.add_argument(
        '--download', action='store_true',
        help='Prompt for Earthdata Login and download missing files with per-file timeouts',
    )
    parser.add_argument(
        '--clean-partials', action='store_true',
        help='Remove temporary partial_* files left by an interrupted download first',
    )
    parser.add_argument('--retries', type=int, default=4, help='Retries per URL (default: 4)')
    parser.add_argument('--connect-timeout', type=float, default=20.0, help='Connection timeout in seconds')
    parser.add_argument('--read-timeout', type=float, default=90.0, help='Per-read timeout in seconds')
    args = parser.parse_args()
    if args.retries < 1 or args.connect_timeout <= 0 or args.read_timeout <= 0:
        parser.error('--retries must be >= 1 and timeouts must be positive')
    rows = checklist(args.case)
    args.output.mkdir(parents=True, exist_ok=True)
    if args.clean_partials:
        print(f'Removed {_clean_partials(args.output)} stale partial file(s).')
    ledger = args.output / 'download_checklist.csv'
    with ledger.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f'{len(rows)} frozen files listed in {ledger}')
    if not args.download:
        print('Checklist only. Use --download to log in and retrieve the exact URLs.')
        return
    failures = _download_missing(
        rows,
        args.output,
        retries=args.retries,
        connect_timeout=args.connect_timeout,
        read_timeout=args.read_timeout,
    )
    if failures:
        print(f'Download incomplete: {len(failures)} file(s) still missing.')
        for row, error in failures:
            print(f'  {row["filename"]}: {error}')
        raise SystemExit(2)
    print(f'Download complete: all {len(rows)} checklist files are present.')


if __name__ == '__main__':
    main()
