#!/usr/bin/env python3
"""Fingerprint existing data for a submission release; no downloads or database writes."""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from fireatlas.assistant.science import Science
from fireatlas.assistant.store import Store
from fireatlas.assistant.contracts import digest

p=argparse.ArgumentParser();p.add_argument('--db',type=Path,default=Path('data/fireatlas.sqlite3'));a=p.parse_args()
if Path(str(a.db)+'-wal').exists():raise SystemExit('Close the importing service and use a checkpointed database snapshot before fingerprinting. No database was changed.')
before=a.db.stat()
h=hashlib.sha256()
with a.db.open('rb') as f:
 while block:=f.read(8*1024*1024):h.update(block)
with tempfile.TemporaryDirectory() as t:
 s=Science(a.db,Store(Path(t)/'workspace.sqlite3'));release=s.release()
 after=a.db.stat()
 if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise SystemExit('Data changed while fingerprinting. No release was saved.')
 manifest={**release,'id':digest({'basis':release['manifest'],'database_sha256':h.hexdigest()}),'database':a.db.name,'database_sha256':h.hexdigest(),'database_stamp':[after.st_mtime_ns,after.st_size],'source_basis_hash':digest(release['manifest']),'frozen':True,'basis':'SHA-256 of checkpointed source snapshot plus manifests; file changes invalidate this release'}
 target=a.db.parent/'assistant-release.json';target.write_text(json.dumps(manifest,indent=2));print('Saved release fingerprint:',target,'\nRelease:',manifest['id'])
