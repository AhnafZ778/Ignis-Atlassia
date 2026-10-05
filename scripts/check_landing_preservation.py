"""Capture/check the landing boundary. Only its header is editable."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'docs/implementation/landing-baseline.json'

def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def outside_header(path):
    return re.sub(r'<header\b[^>]*class="topbar[^>]*>.*?</header>', '<!-- protected-header-boundary -->', path.read_text(), count=1, flags=re.S)

def capture():
    assets = set()
    # Existing shared sources loaded by the home page must remain untouched.
    home = ROOT / 'fireatlas/static/index.html'
    for path in (ROOT/'fireatlas/static').rglob('*'):
        if path.is_file() and (path.suffix in {'.webp', '.woff2', '.svg'} or path.parts[-2] in {'fonts','vendor'}):
            assets.add(path)
    for name in re.findall(r'(?:src|href)="/([^"?#]+)', home.read_text()):
        path = ROOT/'fireatlas/static'/name
        if path.is_file() and path.suffix != '.html': assets.add(path)
    for name in ['terrain-earth.html','documented-fires.json','globe.css','landing.css','globe-math.js']:
        assets.add(ROOT/'fireatlas/static'/name)
    for name in ['earth.html','Globe.html']:
        if (ROOT/name).exists(): assets.add(ROOT/name)
    # Include globe textures and local terrain dependencies.
    terrain = (ROOT/'fireatlas/static/terrain-earth.html').read_text()
    for name in re.findall(r'(?:src|href)="(?:/|\./)?([^"?#]+)', terrain):
        path=ROOT/'fireatlas/static'/name
        if path.is_file(): assets.add(path)
    for path in list(assets):
        if path.is_relative_to(ROOT/'fireatlas/static'):
            shipped=ROOT/'site'/path.relative_to(ROOT/'fireatlas/static')
            if shipped.exists(): assets.add(shipped)
    globe=ROOT/'site/data/v2/globe'
    if globe.exists(): assets.update(p for p in globe.rglob('*') if p.is_file())
    result={'schema':'ignis-landing-protection-v1', 'files':{str(p.relative_to(ROOT)):sha(p) for p in sorted(assets)},
            'outside_header':{str(p.relative_to(ROOT)):hashlib.sha256(outside_header(p).encode()).hexdigest()
                              for p in [home,ROOT/'site/index.html'] if p.exists()}}
    BASELINE.write_text(json.dumps(result,indent=2)+'\n')
    print(f'Captured {len(assets)} protected files.')

def check():
    baseline=json.loads(BASELINE.read_text()); failures=[]
    for name,digest in baseline['files'].items():
        path=ROOT/name
        if not path.exists() or sha(path)!=digest: failures.append(name)
    for name,digest in baseline['outside_header'].items():
        if hashlib.sha256(outside_header(ROOT/name).encode()).hexdigest()!=digest: failures.append(name+' outside header')
    if failures: raise SystemExit('Landing protection failed: '+', '.join(failures))
    print(f"Landing preserved: {len(baseline['files'])} asset hashes and both HTML boundaries match.")

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--capture',action='store_true');args=parser.parse_args()
    capture() if args.capture else check()
