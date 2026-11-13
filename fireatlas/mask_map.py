"""Read bounded, geolocated native mask samples for the map."""
from __future__ import annotations
from collections import Counter
from datetime import date
from pathlib import Path
import sqlite3

STORE = Path(__file__).resolve().parent.parent / 'data' / 'validity_masks.sqlite3'
NAMES = {3: 'non-fire water', 4: 'cloud', 5: 'non-fire land', 7: 'fire low', 8: 'fire nominal', 9: 'fire high'}

def samples(day, bbox, path=STORE, limit=1800):
    date.fromisoformat(day)
    path = Path(path)
    if not path.is_file():
        return {'date': day, 'available': False, 'samples': [], 'counts': {}, 'reason': 'Native mask archive is not available.'}
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute('''SELECT p.lat,p.lon,p.mask_class,g.source_id,g.platform,g.start_utc,p.producer_id
            FROM granules g JOIN pixels p ON p.case_id=g.case_id AND p.producer_id=g.producer_id
            WHERE g.start_utc>=? AND g.start_utc<? AND p.lon>=? AND p.lon<=? AND p.lat>=? AND p.lat<=?
              AND g.source_id IN ('MODIS_SP','VIIRS_SNPP_SP') AND p.mask_class IN (3,4,5,7,8,9)
            ORDER BY g.source_id,p.mask_class,g.start_utc,p.producer_id,p.line,p.sample''',
            (day+'T00:00:00',day+'T24:00:00',bbox[0],bbox[2],bbox[1],bbox[3]))
        buckets = {}; counts = Counter()
        # Keep a bounded deterministic uniform sample for each sensor and class.
        for row in rows:
            key=(row['source_id'],row['mask_class']); counts[key]+=1
            bucket=buckets.setdefault(key,[])
            value={'lat':row['lat'],'lon':row['lon'],'class':row['mask_class'],'label':NAMES[row['mask_class']],
                   'source':row['source_id'],'platform':row['platform'],'acquired':row['start_utc'],'granule':row['producer_id']}
            per_bucket=max(1,limit//12)
            if len(bucket)<per_bucket: bucket.append(value)
            else:
                # Deterministic reservoir sampling preserves the full acquisition interval.
                import hashlib
                pick=int.from_bytes(hashlib.blake2b((row['producer_id']+str(counts[key])).encode(),digest_size=8).digest(),'big') % counts[key]
                if pick<per_bucket: bucket[pick]=value
    return {'date':day,'available':bool(counts),'samples':[v for b in buckets.values() for v in b],
            'counts':{f'{s}:{c}':n for (s,c),n in counts.items()},
            'reason':None if counts else 'No stored mask samples for this area and date.'}
