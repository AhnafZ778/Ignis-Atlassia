"""Prepare a public, conversation-free starter from an inspected native export.

This is deliberately explicit: it does not publish a user's current board store.
Scientific result bytes and drawing objects are preserved. Run from the repo root.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def prepare(source, target):
    from fireatlas.studio.portability import read_archive
    from fireatlas.studio.store import dumps, sha256_text
    read_archive(source)  # refuse malformed input before transformation
    with zipfile.ZipFile(source) as archive:
        files={name:archive.read(name) for name in archive.namelist() if name!='manifest.json'}
    # Private discussion is not needed to reproduce the three-year comparison.
    files['conversation.json']=dumps([]).encode()
    files['comments.json']=dumps([]).encode()
    doc=json.loads(files['source_document.json'])
    doc['conversation_sha256']=sha256_text(dumps([]))
    files['source_document.json']=dumps(doc).encode()
    files['README.txt']=(
        'Public submission starter: Rajshahi peak UTC days, 2023–2025. '
        'Restore using Investigation > More > Restore investigation. '
        'AI conversation and board discussion were removed for public distribution. '
        'Frozen scientific receipts and drawing objects retain their original bytes. '
        'Thermal observations are not unique fires, burned area or human activity. '
        'A restored package is user-supplied evidence; hashes establish integrity.\n'
    ).encode()
    inventory={name:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in files.items()}
    manifest={'schema':'fireatlas-board-v1','files':inventory,'expanded_bytes':sum(len(data) for data in files.values())}
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,11,13,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,data)
        archive.writestr('manifest.json',dumps(manifest))
    read_archive(target)
    return {'schema':'fireatlas-public-starter-v1','source_package_sha256':hashlib.sha256(Path(source).read_bytes()).hexdigest(),
            'public_package_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'removed':['AI conversation','board discussion'],
            'preserved_result_sha256':{name:meta['sha256'] for name,meta in inventory.items() if name.startswith('results/')}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source');parser.add_argument('target')
    args=parser.parse_args()
    provenance=prepare(args.source,args.target)
    Path(args.target).with_suffix('.provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print('Prepared and integrity-checked public starter; private discussion removed.')
