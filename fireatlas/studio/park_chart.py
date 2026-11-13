"""Create a bounded, source-linked Park case table for an investigation board."""
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path

from .datasets import add
from .errors import StudioError

ROOT=Path(__file__).resolve().parents[2]/'site'/'data'
DAYS=tuple(f'2024-07-{day:02d}' for day in range(25,29))
SOURCES=('MODIS_SP','VIIRS_SNPP_SP','VIIRS_NOAA20_SP','VIIRS_NOAA21_SP')
BBOX=[-122.0,39.5,-121.3,40.5]


def published_timeline(root=ROOT):
    """Return recorded detection counts and separate export states, never imputed gaps."""
    root=Path(root)
    try:
        replay_bytes=(root/'replay/cases/park-2024.json.gz').read_bytes()
        replay=json.loads(gzip.decompress(replay_bytes))
        primary_hash=hashlib.sha256(replay_bytes).hexdigest()
        manifest=json.loads((root/'park-platforms/v1/manifest.json').read_text())
        if manifest.get('schema')!='fireatlas-park-platform-publication-v1' or replay.get('case_id')!='park-2024' or replay['case']['bbox']!=BBOX:
            raise ValueError('wrong case')
        frames={frame['date_utc']:frame for frame in replay['frames']}
        rows=[]
        for day in DAYS:
            filename=day+'.json.gz';blob=(root/'park-platforms/v1'/filename).read_bytes();digest=hashlib.sha256(blob).hexdigest()
            published=manifest['files'][filename]
            if digest!=published['sha256'] or len(blob)!=published['bytes']:raise ValueError('NOAA publication mismatch')
            noaa=json.loads(gzip.decompress(blob))
            if noaa.get('date_utc')!=day or noaa.get('bbox')!=BBOX:raise ValueError('wrong NOAA case')
            values={};states={}
            for source in SOURCES:
                if source in SOURCES[:2]:
                    product=frames[day]['products'][source];state=product['state'];count=product['detections']
                else:
                    product=noaa['sources'][source];state=product['state'];count=len(product['observations'])
                if not isinstance(state,str) or type(count) is not int or count<0:raise ValueError('invalid count')
                states[source]=state
                values[source]=count if state=='complete_export' or count>0 else None
            rows.append({'date':day,'values':values,'states':states,'replay_sha256':primary_hash,'noaa_sha256':digest})
    except (OSError,KeyError,TypeError,ValueError,EOFError,json.JSONDecodeError) as error:
        raise StudioError('The published Park case is unavailable or inconsistent.',code='park-source-unavailable') from error
    return rows


def save_timeline(store,principal,document_id,root=ROOT):
    rows=published_timeline(root)
    buffer=io.StringIO(newline='');writer=csv.writer(buffer,lineterminator='\n')
    writer.writerow(['UTC date',*SOURCES,*(source+' state' for source in SOURCES),'replay source SHA256','NOAA day source SHA256'])
    for row in rows:
        writer.writerow([row['date'],*(row['values'][source] if row['values'][source] is not None else '' for source in SOURCES),
                         *(row['states'][source] for source in SOURCES),row['replay_sha256'],row['noaa_sha256']])
    dataset=add(store,principal,document_id,'Park Fire daily platform observations.csv',buffer.getvalue().encode())
    return {'dataset':dataset,'rows':rows,'unit':'recorded detections','bbox':BBOX,'outage_source':'VIIRS_SNPP_SP'}
