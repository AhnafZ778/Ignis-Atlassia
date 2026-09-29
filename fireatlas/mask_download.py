"""Create an exact frozen NASA download checklist; optionally use Earthdata login.

No credentials are written by this module. Acquisition is a user-run operation.
"""
from __future__ import annotations

import argparse
import csv
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=('park-2024', 'grove-2025'))
    parser.add_argument('--output', type=Path, default=Path('NASA_data/fire_masks'))
    parser.add_argument('--download', action='store_true', help='Prompt for Earthdata Login using earthaccess')
    args = parser.parse_args()
    rows = checklist(args.case)
    args.output.mkdir(parents=True, exist_ok=True)
    ledger = args.output / 'download_checklist.csv'
    with ledger.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f'{len(rows)} frozen files listed in {ledger}')
    if not args.download:
        print('Checklist only. Use --download to log in and retrieve the exact URLs.')
        return
    try:
        import earthaccess
    except ImportError:
        raise SystemExit('Run: uv run --with earthaccess==0.19.0 python -m fireatlas.mask_download --download') from None
    auth = earthaccess.login(strategy='interactive', persist=False)
    if not auth.authenticated:
        raise SystemExit('Earthdata login did not succeed; no coverage state was changed.')
    urls = list(dict.fromkeys(row['download_url'] for row in rows))
    earthaccess.download(urls, local_path=str(args.output))
    found = {path.name for path in args.output.rglob('*') if path.is_file()}
    missing = sorted({row['filename'] for row in rows} - found)
    print(f'Expected files absent after download: {len(missing)}. Processor verifies native content separately.')
    for filename in missing:
        print(filename)


if __name__ == '__main__':
    main()
