"""Recount and bind the optional MODIS collection pilot for immutable release."""
from pathlib import Path
import json
from .modis_collection_pilot import compare
from scripts.acquire_modis_collection_overlap import FILES, verify_existing


def _inputs(work):
    work=Path(work).resolve(strict=True)
    directory=work/'modis-collection-pilot-v1'
    if directory.is_symlink():raise ValueError('Collection pilot directory cannot be a symbolic link.')
    if not directory.exists():return None
    if directory.resolve(strict=True).parent != work:
        raise ValueError('Collection pilot directory escapes the campaign.')
    files=sorted(directory.glob('comparison-*.json'))
    if not files:return None
    if len(files)!=1 or files[0].is_symlink() or files[0].stat().st_size>1_000_000:
        raise ValueError('Invalid collection pilot result inventory.')
    paths={k:directory/name for k,name in FILES.items()}
    receipts={}
    for k,name in FILES.items():
        receipt=directory/(name+'.receipt.json')
        if paths[k].is_symlink() or receipt.is_symlink():raise ValueError('Collection source cannot be a symbolic link.')
        receipts[k]=verify_existing(paths[k],receipt,k,name)
    return files[0],paths,receipts


def preflight(work):
    checked=_inputs(work)
    if checked is None:return None
    file,paths,receipts=checked
    result=json.loads(file.read_text())
    provenance={k:{field:r[field] for field in ('collection','filename','month','bytes','sha256','retrieved_utc')} for k,r in receipts.items()}
    if result != compare(paths,provenance) or file.name != 'comparison-'+result['result_sha256']+'.json':
        raise ValueError('Collection pilot does not match original-file recount.')
    if _inputs(work)!=(file,paths,receipts):raise ValueError('Collection inputs changed during recount.')
    return result


def verify_sources(work, result):
    checked=_inputs(work)
    if result is None:
        if checked is not None:raise ValueError('Collection result appeared during publication.')
        return
    if checked is None:raise ValueError('Collection inputs disappeared during publication.')
    file,_,receipts=checked
    provenance={k:{field:r[field] for field in ('collection','filename','month','bytes','sha256','retrieved_utc')} for k,r in receipts.items()}
    if json.loads(file.read_text())!=result or provenance!=result['source_files']:
        raise ValueError('Collection inputs changed during publication.')
