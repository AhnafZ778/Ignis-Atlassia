"""Refresh the published UI while preserving the existing observation snapshot."""

from __future__ import annotations

import argparse
import json
import sys
import re
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.export_static import STATIC, _copy_site_assets, _rebase_local_asset_urls


def refresh(site: Path) -> None:
    from scripts.check_landing_preservation import check, outside_header, sha
    protected_path = ROOT / 'docs/implementation/landing-baseline.json'
    if protected_path.exists():
        check()
    manifest_path = site / "data" / "v2" / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("No observation manifest found. Build the static data export first.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot = manifest.get("snapshot_utc_date")
    if not snapshot:
        raise ValueError("The data manifest has no snapshot date; refusing to relabel its observations.")
    protected=json.loads(protected_path.read_text()) if protected_path.exists() else {'files':{}}
    protected_names={str(Path(name).relative_to('site')) for name in protected['files'] if name.startswith('site/')}
    target_hashes = {name: sha(site/name) for name in protected_names if (site/name).is_file()}
    target_html = outside_header(site/'index.html')
    original_home=(site/'index.html').read_text()
    with tempfile.TemporaryDirectory(prefix='ignis-ui-refresh-') as temporary:
        stage=Path(temporary)
        _copy_site_assets(stage, STATIC, snapshot_date=snapshot)
        _rebase_local_asset_urls(stage)
        for path in stage.rglob('*'):
            if not path.is_file():continue
            name=str(path.relative_to(stage))
            if name in protected_names or name=='index.html':continue
            target=site/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
        # Generated SDK bundles are content-addressed. Remove stale hashed
        # chunks so the published derivative is an exact copy of the current
        # frontend build rather than an accumulation of prior builds.
        for directory in ('studio-assets', 'studio-mcp'):
            staged = stage / directory
            target = site / directory
            if staged.is_dir() and target.is_dir():
                for old in target.rglob('*'):
                    if old.is_file() and not (staged / old.relative_to(target)).is_file():
                        old.unlink()
        header=re.search(r'<header\b[^>]*class="topbar[^>]*>.*?</header>',(stage/'index.html').read_text(),re.S).group()
        (site/'index.html').write_text(re.sub(r'<header\b[^>]*class="topbar[^>]*>.*?</header>',lambda _:header,original_home,count=1,flags=re.S))
    analysis=site/'data/analysis/manifest.json'
    if analysis.exists():
        analytical=json.loads(analysis.read_text())
        for name in ['atlas.html','evidence.html','research.html','investigate.html']:
            page=site/name;text=page.read_text()
            text=re.sub(r'(<meta name="fireatlas-static-data" content=")[^"]+',r'\1./data/analysis/',text)
            text=re.sub(r'(<meta name="fireatlas-static-snapshot" content=")[^"]+',lambda m:m[1]+analytical['snapshot_utc_date'],text)
            text=text.replace('</head>','<meta name="fireatlas-static-evidence" content="./data/v2/">\n</head>',1)
            page.write_text(text)
    if any(sha(site/name) != digest for name, digest in target_hashes.items()):
        raise ValueError('UI refresh changed a protected landing asset in the target site.')
    if outside_header(site/'index.html') != target_html:
        raise ValueError('UI refresh changed target landing HTML outside its header.')
    if protected_path.exists():
        check()
    print(f"Updated website assets in {site}; frozen globe/evidence snapshot remains {snapshot}; analytical manifest retains its own snapshot.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    args = parser.parse_args()
    refresh(args.site.resolve())
