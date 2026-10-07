"""Check the assembled static publication before uploading it to GitHub Pages."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

# Use the conservative decimal interpretation of GitHub Pages' 1 GB limit.
MAX_BYTES = 1_000_000_000


def check(site: Path) -> dict:
    site = site.resolve()
    for name in ('index.html', '.nojekyll', 'atlas.html', 'investigate.html',
                 'research.html', 'evidence.html', 'studio.html'):
        if not (site / name).is_file():
            raise ValueError(f'Missing publication entry: {name}')
    files = []
    for path in site.rglob('*'):
        if path.is_symlink():
            raise ValueError(f'Publication contains a symbolic link: {path.relative_to(site)}')
        if path.is_file():
            if path.name == '.env' or path.name.startswith('.env.') or path.suffix.lower() in {
                '.key', '.pem', '.p12', '.pfx', '.sqlite', '.sqlite3',
            }:
                raise ValueError(f'Private file in publication: {path.relative_to(site)}')
            files.append(path)
    total = sum(path.stat().st_size for path in files)
    if total > MAX_BYTES:
        raise ValueError(f'Publication is {total:,} bytes; GitHub Pages limit is {MAX_BYTES:,}.')
    verified = 0
    for manifest, base in ((site / 'data/v2/manifest.json', site),
                           (site / 'data/analysis/manifest.json', site / 'data/analysis')):
        for entry in json.loads(manifest.read_text(encoding='utf-8'))['files']:
            path = (base / entry['path']).resolve()
            if not path.is_relative_to(base.resolve()) or not path.is_file():
                raise ValueError(f'Missing or invalid evidence path: {entry["path"]}')
            if path.stat().st_size != entry['bytes']:
                raise ValueError(f'Evidence size mismatch: {entry["path"]}')
            with path.open('rb') as source:
                digest = hashlib.sha256()
                while block := source.read(1024 * 1024):
                    digest.update(block)
            if digest.hexdigest() != entry['sha256']:
                raise ValueError(f'Evidence checksum mismatch: {entry["path"]}')
            verified += 1
    return {'files': len(files), 'bytes': total, 'remaining_bytes': MAX_BYTES - total,
            'verified_evidence_files': verified}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=Path('site'))
    args = parser.parse_args()
    try:
        result = check(args.site)
    except (ValueError, KeyError, OSError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
