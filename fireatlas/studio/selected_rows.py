"""Bind explicit map selections to frozen replay rows and portable CSV."""
import csv
import io
from ..assistant.annotations import validate_geometry
from ..assistant.geometry import contains
from .errors import StudioError

FIELDS=('id','acquisition_utc','source_id','platform','product_version','latitude','longitude','frp_mw','confidence','daynight','source_file_sha256','retrieved_utc')

def selection_rows(selection, receipt, day, source):
    if receipt.get('operation')!='replay' or not isinstance(selection,dict):
        raise StudioError('Map selections require a frozen replay.')
    if selection.get('target') not in ('observation-record','observation-cell','query-boundary'):
        raise StudioError('Select an observation, cell, or area to include its records.')
    geometry=validate_geometry(selection.get('geometry'))
    rows=receipt['payload'].get('observations',[])
    date=selection.get('date') or day
    if not isinstance(date,str) or date not in {f['date_utc'] for f in receipt['payload'].get('frames',[])}:
        raise StudioError('The selection date is outside the frozen replay.')
    if source not in ('joint','MODIS_SP','VIIRS_SNPP_SP'):
        raise StudioError('Choose an available source.')
    eligible=[r for r in rows if r.get('date')==date and (source=='joint' or r.get('source_id')==source)]
    target=selection['target']
    if target=='observation-record':
        eligible=[r for r in eligible if r.get('id')==selection.get('record_id') and geometry['type']=='Point' and [r.get('longitude'),r.get('latitude')]==geometry['coordinates']]
        if len(eligible)!=1: raise StudioError('The selected observation is not in the frozen source.')
    elif target=='observation-cell':
        cell=selection.get('cell_id','')
        frame=next(f for f in receipt['payload']['frames'] if f['date_utc']==date)
        matches=[c for c in frame.get('cells',[]) if str(c['grid_x'])+','+str(c['grid_y'])==cell and geometry=={'type':'Polygon','coordinates':[c['ring']]}]
        if len(matches)!=1: raise StudioError('The selected cell is not in the frozen source.')
        eligible=[r for r in eligible if str(r.get('grid_x'))+','+str(r.get('grid_y'))==cell]
    else:
        if geometry['type']!='Polygon':raise StudioError('Select a polygon for area records.')
        eligible=[r for r in eligible if contains(geometry['coordinates'][0],r['longitude'],r['latitude'])]
    return {'target':target,'date':date,'source':source,'geometry':geometry,'record_id':selection.get('record_id'),'cell_id':selection.get('cell_id')},eligible

def csv_bytes(rows):
    out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=FIELDS,extrasaction='ignore',lineterminator='\r\n');writer.writeheader();writer.writerows(rows);return out.getvalue().encode('utf-8')
