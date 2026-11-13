"""Descriptive candidates from imported same-sensor record profiles, not fire equivalence."""
from __future__ import annotations
import math
from datetime import date,timedelta
from .regions import REGIONS

def match_imported_profiles(db,cfg,args,cancel=None):
    source=cfg['source']
    if source not in {'MODIS_SP','VIIRS_SNPP_SP'}:
        raise ValueError('Choose one sensor (MODIS or S-NPP) before comparing historical record profiles.')
    first,last=date.fromisoformat(cfg['start']),date.fromisoformat(cfg['end'])
    length=(last-first).days+1
    if not 2<=length<=14:
        raise ValueError('Profile comparison uses an explicit reference interval of two to fourteen UTC days.')
    first_year=args.get('first_year',2006);last_year=args.get('last_year',date.today().year)
    if type(first_year) is not int or type(last_year) is not int or not 2000<=first_year<=last_year<=2100 or last_year-first_year>25:
        raise ValueError('Choose an ordered candidate search range of at most twenty-six years.')
    region_ids=args.get('regions',list(REGIONS))
    if not isinstance(region_ids,list) or not region_ids or len(region_ids)>2 or any(region not in REGIONS for region in region_ids):
        raise ValueError('Choose from the available imported regions: '+', '.join(REGIONS))
    def daily(box,start,end):
        w,s,e,n=box
        return {row['day']:row['records'] for row in db.execute("""
            SELECT substr(o.acquisition_utc,1,10) AS day,COUNT(*) AS records
            FROM observations o JOIN batches b ON b.id=o.batch_id
            WHERE b.demo=0 AND o.processing_level='SP' AND o.source_id=?
              AND o.acquisition_utc>=? AND o.acquisition_utc<?
              AND o.lon>=? AND o.lon<=? AND o.lat>=? AND o.lat<=?
            GROUP BY day ORDER BY day
        """,(source,start,(date.fromisoformat(end)+timedelta(days=1)).isoformat(),w,e,s,n))}
    ref_days=[(first+timedelta(days=i)).isoformat() for i in range(length)]
    records=daily(cfg['bbox'],cfg['start'],cfg['end'])
    if any(day not in records for day in ref_days):
        raise ValueError('The reference has dates without imported records. Their source availability must be checked; they cannot be filled with zero for matching.')
    counts=[records[day] for day in ref_days];total=sum(counts)
    reference_profile=[count/total for count in counts]
    candidates=[];inventories=[];skipped=0
    for region_id in region_ids:
        if cancel and cancel.is_set():raise InterruptedError('Historical comparison stopped.')
        region=REGIONS[region_id];box=list(region['bbox'])
        rows=daily(box,f'{first_year}-01-01',f'{last_year}-12-31')
        inventories.append({'region':region_id,'bbox':box,'dates_with_records':len(rows)})
        w,s,e,n=box;a,b,c,d=cfg['bbox']
        overlaps=not (e<a or c<w or n<b or d<s)
        for start in sorted(rows):
            start_date=date.fromisoformat(start)
            end_date=start_date+timedelta(days=length-1)
            if end_date.year>last_year:continue
            if overlaps and start_date<=last and end_date>=first:continue
            days=[(start_date+timedelta(days=i)).isoformat() for i in range(length)]
            if any(day not in rows for day in days):skipped+=1;continue
            values=[rows[day] for day in days];denominator=sum(values)
            distance=math.sqrt(sum((a-b/denominator)**2 for a,b in zip(reference_profile,values)))
            candidates.append({'region':region_id,'bbox':box,'start':start,'end':end_date.isoformat(),
                'source':source,'counts':values,'imported_records':denominator,'distance':round(distance,9),
                'scope_note':'Fixed regional archive boundary; not a confirmed incident or matched fire extent.'})
    selected=[]
    for candidate in sorted(candidates,key=lambda item:(item['distance'],item['region'],item['start'])):
        if any(previous['region']==candidate['region'] and candidate['start']<=previous['end'] and previous['start']<=candidate['end'] for previous in selected):continue
        selected.append(candidate)
        if len(selected)==3:break
    return {'reference':{'bbox':cfg['bbox'],'start':cfg['start'],'end':cfg['end'],'source':source,'dates':ref_days,'counts':counts,'imported_records':total},
            'candidates':selected,'candidate_count':len(selected),'eligible_windows':len(candidates),
            'first_year':first_year,'last_year':last_year,'coverage':inventories,'skipped_missing_date_windows':skipped,
            'note':('Candidate windows resemble the reference daily record profile in the imported '+', '.join(item['region'] for item in inventories)+' archives. Different boundaries and source coverage can affect counts; shared causes and candidate environmental drivers have not been established.') if selected else 'No complete candidate windows were found in the requested imported archives. Missing records remain unknown.',
            'criterion':'Euclidean distance between daily shares of imported same-sensor records over equal-length windows.',
            'unit':'imported thermal records before alias deduplication',
            'limitations':['Closest available temporal profiles are candidates, not validated event or driver similarity.',
                'Search covers only the listed locally imported regional archives, not an exhaustive worldwide catalog.',
                'Counts can reflect acquisition, processing, repeated imports and different boundary areas; no coverage correction is applied.',
                'A date without records remains unknown and is excluded, never filled with zero.',
                'Weather, human activity and environmental drivers for these candidate windows have not been established.']}
