"""Read-only exact-byte access to immutable qualification publications."""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from .qualification import digest

NAMES=re.compile(r'(?:(?:readiness|availability|campaign|first-inspection|collection-pilot)\.json|(?:monthly|monthly-inputs|monthly-cohorts|daily|daily-cohorts|transfer-summary|transfer-cohorts|transfer-opportunity-summary)/(?:norcal|punjab-haryana)\.json|transfer/(?:norcal|punjab-haryana)\.json\.gz|(?:cohort-(?:monthly|daily|transfer)|transfer-opportunity|daily-hybrid|daily-neighbors)/[0-9a-f]{16}\.json\.gz|(?:(?:transfer|monthly)-provenance|daily-diagnostics)/[0-9a-f]{16}\.json|(?:acquisition|opportunity|native-summary|native-context-summary|coverage-summary|disagreement-summary|footprint-summary)/(?:park-2024|grove-2025)\.json|(?:native|native-inputs|native-context|coverage|disagreement|footprint-campaign)/(?:park-2024|grove-2025)\.json\.gz|(?:opportunity-packet|footprint-part)/[0-9a-f]{64}\.json\.gz)\Z')


def read(root,name,release=None):
    root=Path(root)
    pointer=json.loads((root/'current.json').read_text())
    if not re.fullmatch('[0-9a-f]{64}',pointer.get('release_id','')):raise ValueError('Invalid publication pointer.')
    if name=='current.json':return (root/'current.json').read_bytes()
    selected=release or pointer['release_id']
    if not re.fullmatch('[0-9a-f]{64}',selected):raise ValueError('Invalid release ID.')
    directory=root/'releases'/selected;body=(directory/'manifest.json').read_bytes();manifest=json.loads(body);material=dict(manifest);material.pop('release_id',None)
    if digest(material)!=selected or manifest.get('release_id')!=selected:raise ValueError('Manifest identity differs.')
    if selected==pointer['release_id'] and hashlib.sha256(body).hexdigest()!=pointer.get('manifest_sha256'):raise ValueError('Pointer manifest hash differs.')
    if name=='manifest.json':return body
    if not NAMES.fullmatch(name) or name not in manifest['files']:raise ValueError('Unsupported publication artifact.')
    file=directory/name;meta=manifest['files'][name]
    if file.stat().st_size>512_000_000:raise ValueError('Publication artifact exceeds size limit.')
    content=file.read_bytes()
    if len(content)!=meta['bytes'] or hashlib.sha256(content).hexdigest()!=meta['sha256']:raise ValueError('Frozen artifact hash differs.')
    return content
