"""Read-only, bounded Park Fire NOAA standard-product observations."""
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

BBOX = (-122.0, 39.5, -121.3, 40.5)
SOURCES = ('VIIRS_NOAA20_SP', 'VIIRS_NOAA21_SP')
DAYS = tuple('2024-07-%02d' % day for day in range(25, 29))
DEFAULT_DB = Path(__file__).resolve().parents[1] / 'data/qualification/campaign/observations.sqlite3'


def read_park_day(day, database=DEFAULT_DB):
    if day not in DAYS:
        raise ValueError('Choose a Park pilot date from July 25–28, 2024.')
    if not Path(database).is_file():
        raise FileNotFoundError('NOAA campaign archive is unavailable.')
    db = sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        records = {}
        for source in SOURCES:
            exports = db.execute('''SELECT e.batch_id,e.parent_sha256,e.request_sha256,b.file_sha256,b.retrieved_utc,e.product_versions_json
                FROM source_exports e JOIN batches b ON b.id=e.batch_id
                WHERE e.source_id=? AND e.complete_export=1 AND b.demo=0
                AND e.request_start<=? AND e.request_end>=?
                AND e.west<=? AND e.south<=? AND e.east>=? AND e.north>=?''',
                (source, day, day, *BBOX)).fetchall()
            def matching_version(r):
                try:
                    versions=json.loads(r['product_versions_json'])
                    return isinstance(versions,list) and '2' in versions
                except (ValueError,TypeError):
                    return False
            exports=[r for r in exports if matching_version(r)]
            if not exports:
                records[source] = {'state':'unavailable', 'observations':[], 'exports':[]}
                continue
            rows = db.execute('''SELECT o.detection_id,o.acquisition_utc,o.source_id,o.platform,o.product_version,
                o.lon,o.lat,o.grid_x,o.grid_y,o.frp_raw,o.confidence_raw,o.daynight,o.scan_m,o.track_m,o.raw_json,
                b.file_sha256,b.retrieved_utc FROM observations o JOIN batches b ON b.id=o.batch_id
                WHERE o.source_id=? AND o.product_version='2' AND o.processing_level='SP' AND b.demo=0
                AND o.acquisition_utc>=? AND o.acquisition_utc<?
                AND o.lon BETWEEN ? AND ? AND o.lat BETWEEN ? AND ?
                ORDER BY o.acquisition_utc,o.detection_id''',
                (source,day,(date.fromisoformat(day)+timedelta(days=1)).isoformat(),BBOX[0],BBOX[2],BBOX[1],BBOX[3])).fetchall()
            observations=[]
            for r in rows:
                try: raw = json.loads(r['raw_json'])
                except (ValueError,TypeError): continue
                if not isinstance(raw,dict) or str(raw.get('type') or '').strip() not in ('','0'): continue
                observations.append({'id':r['detection_id'],'date':day,'acquisition_utc':r['acquisition_utc'],
                    'source_id':source,'platform':r['platform'],'product_version':r['product_version'],
                    'longitude':r['lon'],'latitude':r['lat'],'grid_x':r['grid_x'],'grid_y':r['grid_y'],'frp_mw':r['frp_raw'],
                    'confidence':r['confidence_raw'],'daynight':r['daynight'],'scan_m':r['scan_m'],
                    'track_m':r['track_m'],'source_file_sha256':r['file_sha256'],'retrieved_utc':r['retrieved_utc']})
            records[source]={'state':'complete_export', 'observations':observations,
                'exports':[dict(r) for r in exports]}
        return {'schema':'fireatlas-park-platforms-v1','date_utc':day,'bbox':list(BBOX),
                'sources':records,'outage':{'source':'VIIRS_SNPP_SP','start_utc':'2024-07-24T05:24:00Z',
                'end_utc':'2024-07-29T15:18:00Z','url':'https://landweb.modaps.eosdis.nasa.gov/displayissue?id=716'}}
    finally:
        db.close()
