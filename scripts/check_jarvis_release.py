"""Check source/static asset parity and analytical JavaScript syntax without touching the landing."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    source=ROOT/'fireatlas/static';site=ROOT/'site'
    manifest=json.loads((source/'studio-assets/studio-manifest.json').read_text())
    for name,metadata in manifest['files'].items():
        for base in (source,site):
            path=base/'studio-assets'/name
            if not path.is_file() or path.stat().st_size!=metadata['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=metadata['sha256']:
                raise SystemExit('Asset inventory mismatch: '+str(path.relative_to(ROOT)))
    for name in ('jarvis-orchestration.js','jarvis-orchestration.css'):
        if (source/name).read_bytes()!=(site/name).read_bytes():raise SystemExit('Scoped source/static mismatch: '+name)
    # Supported refresh adds static capability/snapshot metadata to the editor HTML.
    shipped=re.sub(r'<meta name="fireatlas-static-(?:data|snapshot)"[^>]*>\n?','',(site/'studio-excalidraw.html').read_text())
    if shipped!=(source/'studio-excalidraw.html').read_text():raise SystemExit('Unexpected continuation-editor HTML difference.')
    checked=[]
    for path in sorted(source.rglob('*')):
        if path.suffix not in {'.js','.mjs','.cjs'}:continue
        result=subprocess.run(['node','--input-type=module','--check'],input=path.read_bytes(),capture_output=True)
        if result.returncode:raise SystemExit(str(path.relative_to(ROOT))+': '+result.stderr.decode()[:1000])
        checked.append(str(path.relative_to(ROOT)))
    report={'studio_manifest_files':len(manifest['files']),'source_and_static_hashes_match':True,
            'scoped_asset_parity':True,'editor_html_expected_static_metadata_only':True,
            'javascript_syntax_files':len(checked),'checked_javascript':checked}
    (ROOT/'docs/implementation/jarvis-checks/asset-syntax-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='checked_javascript'}))


if __name__=='__main__':main()
