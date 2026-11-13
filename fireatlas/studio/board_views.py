"""Render frozen scientific receipts as portable board figures; no model-authored values."""
from __future__ import annotations
import html
import math
from collections import Counter, defaultdict
from calendar import monthrange
from datetime import date
from .errors import StudioError

SENSORS=(('MODIS_SP','MODIS','#b46b18'),('VIIRS_SNPP_SP','S-NPP','#14829b'))

def month_calendar(title, days, unit, *, secondary=None, source='NASA FIRMS'):
    """Portable capture of the site's Monday-first observation calendar."""
    from .heat import STOPS
    first=date.fromisoformat(days[0]['date']).replace(day=1)
    last=date.fromisoformat(days[-1]['date'])
    if first.month!=last.month or first.year!=last.year:
        return None
    values={item['date']:item for item in days}
    peak=max((item['value'] or 0 for item in days),default=0)
    out=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" role="img" data-board-figure="v1">',
         '<rect width="960" height="540" fill="#f7faf7"/>']
    def text(x,y,value,size,color='#183832',weight=500):
        family='Space Grotesk' if size>=24 else 'DM Sans'
        out.append(f'<text x="{x}" y="{y}" font-family="{family}, Arial, sans-serif" font-size="{size}" font-weight="{weight}" fill="{color}">{html.escape(str(value))}</text>')
    text(32,45,title,34,weight=700)
    text(32,76,f'{first:%B %Y} UTC · {source}',15,'#526a64',600)
    out.append('<path d="M32 89H928" stroke="#d7e5dd"/>')
    for column,label in enumerate(('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')):
        text(45+128*column,115,label,13,'#526a64',700)
    for number in range(1,monthrange(first.year,first.month)[1]+1):
        key=first.replace(day=number).isoformat()
        row,column=divmod(first.weekday()+number-1,7)
        x,y=32+128*column,128+60*row
        item=values.get(key)
        count=item['value'] if item else None
        color,ink='#f4f7f5','#56726a'
        if item:
            color='#e3e6e4' if count is None else '#edf4ee'
            if count:
                scale=4*math.log1p(count)/math.log1p(peak)
                index=min(3,math.floor(scale))
                rgb=[math.floor(left+(right-left)*(scale-index)+.5) for left,right in zip(STOPS[index],STOPS[index+1])]
                color=f'rgb({rgb[0]},{rgb[1]},{rgb[2]})'
                ink='#fff' if sum(c*w for c,w in zip(rgb,(.2126,.7152,.0722)))<125 else '#24190e'
        out.append(f'<rect x="{x}" y="{y}" width="121" height="54" rx="5" fill="{color}" stroke="#d4e3da"/>')
        text(x+10,y+19,number,13,ink,700)
        text(x+10,y+43,'—' if item is None else '?' if count is None else f'{count:,}',22,ink,700)
        if secondary is not None and key in secondary and secondary[key] is not None:
            text(x+58,y+42,f'{secondary[key]:,} det.',12,ink)
    text(32,510,unit+' per UTC day'+(' · det. = returned FIRMS detections' if secondary is not None else ''),13,weight=700)
    text(32,529,'? unavailable · — outside requested dates · observation coverage unverified',12,'#526a64')
    out.append('</svg>')
    return ''.join(out)


def render(snapshot, receipt, kind):
    from ..assistant.board_views import FIRMS_VIEWS, VIEW_OPERATIONS, _SUMMARY_OPERATIONS, firms_days
    if VIEW_OPERATIONS.get(kind)!=receipt.get('operation'):
        raise StudioError('This visualization does not match its saved scientific source.',code='invalid-preview')
    if kind == 'regional-comparison':
        from .heat import prepare_comparison
        return {'snapshot_sha256': snapshot['snapshot_sha256'], 'visual': prepare_comparison(snapshot, receipt),
                'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540"><title>Source-linked regional comparison</title></svg>'}
    payload,scope=receipt['payload'],snapshot['scope']
    esc=lambda value:html.escape(str(value))
    out=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" role="img" data-board-figure="v1">',
         '<rect width="960" height="540" fill="#f7faf7"/>']
    def text(x,y,value,size=14,color='#264541',weight=500,anchor='start'):
        family='Space Grotesk' if size>=24 else 'DM Sans'
        out.append(f'<text x="{x}" y="{y}" font-family="{family}, Arial, sans-serif" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{color}">{esc(value)}</text>')
    def rect(x,y,w,h,color):
        out.append(f'<rect x="{x}" y="{y}" width="{max(0,w):.3f}" height="{h}" rx="3" fill="{color}"/>')
    operation=receipt['operation']
    projection=next((name for name,value in FIRMS_VIEWS.get(operation,{}).items() if value==kind),None)
    place=payload.get('country') or payload.get('title') or 'FIRMS area'
    names={'calendar':'Reading calendar','readings':'Reading table','satellites':'Satellite comparison','coordinates':'Coordinate readings'}
    title={'inventory-summary':'Archive source inventory','overlap-summary':'Sensor overlap','coverage-summary':'Observation coverage','validation-summary':'Validation checks','archived-readings':'Archived reading table','export-status':'Archive export status','persistence-summary':'Observation persistence','monthly-comparability-summary':'Evaluated monthly comparability','harmonized-summary':'Evaluated monthly harmonization','firms-region-heatmap':payload.get('title','Regional FIRMS heatmap'),'firms-country-heatmap':payload.get('country','Country')+' · NASA FIRMS heatmap','firms-country':payload.get('country','Country')+' · NASA FIRMS thermal detections','coordinates':'Original thermal detection coordinates','satellites':'Daily satellite detections','park-satellites':'Park Fire · four-platform detections','similar':'Candidate historical thermal profiles','archive':'Historical observation windows','factors':'Measured environmental context','analogues':'Measured environmental analogues'}.get(kind) or f'{place} · {names.get(projection,"Observations")}'
    text(32,46,title,34,'#102d2b',700)
    query_scope={**scope,'start':str(payload['first_year'])+'-01-01','end':str(payload['last_year'])+'-12-31','bbox':payload.get('bbox',scope['bbox'])} if kind=='archive' else scope
    dates=query_scope['start'] if query_scope['start']==query_scope['end'] else f"{query_scope['start']} – {query_scope['end']}"
    subtitle='Fixed-region archive · monthly overlap evaluation' if kind in ('monthly-comparability-summary','harmonized-summary') else f'{dates} UTC'
    text(32,73,subtitle,14,'#526a64',600)
    out.append('<path d="M32 86H928" stroke="#d7e5dd"/>')
    if projection=='calendar':
        days=firms_days(payload,scope)
        sensor=payload.get('sensor') or 'No product selected'
        total=sum(item['returned'] or 0 for item in days)
        visual={'kind':kind,'title':title,'scope':scope,'days':days,'total':total,'product':payload.get('product')}
        if days[0]['date'][:7]==days[-1]['date'][:7]:
            from .heat import cell_index
            cells=defaultdict(set)
            for row in payload['records']:
                cells[row['acquisition_utc'][:10]].add(cell_index(row))
            cell_days=[{'date':day['date'],'value':None if day['returned'] is None else len(cells[day['date']])} for day in days]
            visual['cell_days']=cell_days
            svg=month_calendar(title,cell_days,'Occupied 1 km cells',secondary={day['date']:day['returned'] for day in days},source=sensor)
            return {'svg':svg,'visual':visual,'snapshot_sha256':snapshot['snapshot_sha256']}
        rect(32,104,896,83,'#143532')
        text(54,140,sensor,23,'#f6fff9',700)
        text(54,165,'Daily returned detections · UTC',14,'#d1e7dd')
        text(902,150,f'{total:,} returned',28,'#f9fffc',700,'end')
        if len(days)<=5:
            slot=896/len(days)
            for index,item in enumerate(days):
                x=32+index*slot
                day=date.fromisoformat(item['date'])
                rect(x,214,slot-10,204,'#eaf3ed')
                text(x+16,248,day.strftime('%A'),15,'#526a64',600)
                text(x+16,284,day.strftime('%b')+' '+str(day.day),26,'#102d2b',700)
                count=item['returned']
                text(x+16,354,f'{count:,}' if count is not None else '—',45,'#143532',700)
                text(x+16,385,'returned' if count is not None else 'unavailable',14,'#526a64')
        else:
            first=date.fromisoformat(days[0]['date'])
            stride=min(16,840/((first.weekday()+len(days)+6)//7))
            peak=max((item['returned'] or 0 for item in days),default=0)
            colors=('#d4e7dc','#9dcabc','#63a991','#308167','#155645')
            for index,item in enumerate(days):
                day=date.fromisoformat(item['date'])
                week,weekday=divmod(index+first.weekday(),7)
                x,y=78+week*stride,233+weekday*25
                count=item['returned']
                color='#e4e4e4' if count is None else colors[math.ceil(4*math.sqrt(count/peak))] if count else colors[0]
                out.append(f'<rect x="{x:.2f}" y="{y}" width="{stride-2:.2f}" height="19" rx="3" fill="{color}"><title>{item["date"]} UTC · {count if count is not None else "unavailable"}</title></rect>')
                if index==0 or (day.day==1 and week>=3):
                    text(x,218,day.strftime('%b'),12,'#526a64',600)
            for day,label in ((0,'Mon'),(2,'Wed'),(4,'Fri'),(6,'Sun')):
                text(32,247+day*25,label,12,'#526a64',600)
            text(78,438,'Detections per UTC day',13,'#264541',700)
            text(258,438,'0',12)
            for index,color in enumerate(colors):
                rect(273+index*19,427,15,13,color)
            text(371,438,f'{peak:,}',12)
            if any(item['returned'] is None for item in days):
                rect(443,427,15,13,'#e4e4e4')
                text(466,438,'Unavailable in archive',12)
        text(32,503,'NASA FIRMS',13,'#234f43',700)
        text(142,503,'A zero is an empty returned day. Observation coverage is unverified.',13,'#526a64')
        visual={'kind':kind,'title':title,'scope':scope,'days':days,'total':total,'product':payload.get('product')}
    elif projection=='readings':
        rows=sorted(payload['records'],key=lambda row:row['acquisition_utc'])
        text(32,123,f"{payload.get('sensor') or 'NASA FIRMS'} · {len(rows):,} returned records",17,'#234f43',700)
        rect(32,145,896,36,'#143532')
        columns=[(48,'Acquired UTC'),(307,'Latitude'),(464,'Longitude'),(623,'Brightness (K)'),(796,'FRP (MW)')]
        for x,label in columns:text(x,168,label,13,'#f6fff9',700)
        for index,row in enumerate(rows[:8]):
            y=187+index*35
            rect(32,y,896,32,'#eaf3ed' if index%2==0 else '#f0f6f1')
            values=(row['acquisition_utc'].replace('T',' ')[:16], f"{row['latitude']:.5f}",f"{row['longitude']:.5f}",
                    f"{row['brightness_k']:g}",f"{row['frp_mw']:g}" if row['frp_mw'] is not None else '—')
            for (x,_),value in zip(columns,values):text(x,y+21,value,14)
        if not rows:
            rect(32,191,896,72,'#eaf3ed')
            text(48,232,'No readings were returned in this search window.',17,'#526a64',600)
        text(32,503,'NASA FIRMS',13,'#234f43',700)
        text(142,503,f'{min(8,len(rows)):,} shown · full readings remain in the saved source',13,'#526a64')
        visual={'kind':kind,'title':title,'scope':scope,'rows':rows[:8],'total':len(rows),'product':payload.get('product')}
    elif projection=='satellites':
        checks=payload.get('checks') or []
        peak=max([1]+[item['detections'] for item in checks])
        rect(32,106,896,364,'#eaf3ed')
        text(52,141,'Returned detections by product',18,'#234f43',700)
        palette=('#b46b18','#14829b','#7456a3','#318157')
        for index,item in enumerate(checks):
            y=174+index*64
            text(52,y+22,item['sensor'],16,'#264541',600)
            rect(289,y,510,29,'#d9e8df')
            if item['detections']:
                rect(289,y,510*item['detections']/peak,29,palette[index%len(palette)])
            text(896,y+22,f"{item['detections']:,}",20,'#102d2b',700,'end')
        text(32,503,'NASA FIRMS',13,'#234f43',700)
        text(142,503,'Each product is shown separately in its original detection units.',13,'#526a64')
        visual={'kind':kind,'title':title,'scope':scope,'products':[{key:item[key] for key in ('product','sensor','detections')} for item in checks]}
    elif kind in ('firms-country-heatmap','firms-region-heatmap'):
        regional=kind=='firms-region-heatmap'
        rows=payload['records']
        west,south,east,north=scope['bbox']
        ratio=(east-west)*math.cos(math.radians((south+north)/2))/(north-south)
        width,height=min(560,350*ratio),min(350,560/ratio)
        cols,lines=max(1,round(width/14)),max(1,round(height/14))
        width,height=width*.86,height*.86
        left,top=56+(548-width)/2,114+(322-height)/2
        dx,dy=width/cols,height/lines
        counts=Counter(
            (min(cols-1,int((row['longitude']-west)/(east-west)*cols)),
             min(lines-1,int((north-row['latitude'])/(north-south)*lines)))
            for row in rows
        )
        peak=max(counts.values(),default=0)
        rect(32,102,604,365,'#eaf3ed')
        if regional:
            for i in range(5):
                fraction=i/4
                x,y=left+width*fraction,top+height*fraction
                out.append(f'<path d="M{x:.2f} {top:.2f}v{height:.2f} M{left:.2f} {y:.2f}h{width:.2f}" stroke="#c9ded5"/>')
                text(x-17,top+height+20,f'{west+(east-west)*fraction:.2f}°E',11)
                text(left-47,y+4,f'{north-(north-south)*fraction:.2f}°N',11)
            ref=payload['reference']
            x=left+(ref['longitude']-west)/(east-west)*width
            y=top+(north-ref['latitude'])/(north-south)*height
            out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="#285b54"/>')
            text(x+9,y-9,ref['name'],13,'#214a43',700)
        for ring in payload.get('country_outline',[]):
            points=' '.join(f'{left+(lon-west)/(east-west)*width:.2f},{top+(north-lat)/(north-south)*height:.2f}' for lon,lat in ring)
            out.append(f'<polygon points="{points}" fill="#d6e9df" stroke="#6a9483" stroke-width="1"/>')
        palette=('#f5c75b','#efa046','#e57339','#ce493b','#98273c')
        for (column,line),count in sorted(counts.items()):
            color=palette[round(4*(count-1)/(peak-1)) if peak>1 else 0]
            rect(left+column*dx,top+line*dy,max(1,dx-1),max(1,dy-1),color)
        rect(654,102,274,365,'#143532')
        text(676,136,'FIRMS ARCHIVE' if payload.get('incident') or payload.get('archive') else 'SATELLITE RECORDS',13,'#a8d2c4',700)
        text(676,205,f'{len(rows):,}',63,'#f9fffc',700)
        text(677,231,'returned detections',15,'#d1e7dd',600)
        out.append('<path d="M676 252H906" stroke="#45635a"/>')
        checks=payload.get('checks',[])
        if regional and len(checks)>1:
            for index,check in enumerate(checks):
                y=285+index*34
                text(677,y,check['sensor'],15,'#eff9f4',600)
                text(903,y,f"{check['detections']:,}",15,'#eff9f4',700,'end')
        else:
            sensor=payload['sensor'] or 'NASA FIRMS'
            product=payload.get('product') or ''
            mode='Near real time' if product.endswith('_NRT') else 'Standard processing'
            text(677,284,sensor,17,'#f6fff9',700)
            text(677,308,mode,13,'#aed0c2')
            if rows:
                colors=palette if peak>1 else palette[:1]
                for index,color in enumerate(colors):
                    rect(677+index*36,344,31,9,color)
                text(677,377,f'1–{peak} detections per cell' if peak>1 else '1 detection per cell',13,'#e3f1e9',600)
            else:
                text(677,355,'No heat cells in this window',13,'#e3f1e9',600)
        out.append('<path d="M32 483H928" stroke="#d7e5dd"/>')
        text(32,513,'NASA FIRMS',13,'#234f43',700)
        if regional:
            attribution=payload['reference'].get('source','GeoNames')
            text(142,513,f'{attribution} · Pin marks the reference locality',13,'#526a64')
        else:
            text(142,513,'Color shows the returned detections per display cell.',13,'#526a64')
        visual={'kind':kind,'cells':[{'column':col,'row':row,'count':count} for (col,row),count in sorted(counts.items())],
                'grid':{'columns':cols,'rows':lines},'total':len(rows),'scope':scope,'product':payload['product'],'title':title}
    elif projection=='coordinates':
        rows=payload['records']
        west,south,east,north=scope['bbox']
        left,top,width,height=80,116,530,303
        low=min((row['brightness_k'] for row in rows),default=None)
        high=max((row['brightness_k'] for row in rows),default=None)
        rect(32,102,604,365,'#eaf3ed')
        for i in range(5):
            fraction=i/4
            x,y=left+width*fraction,top+height*fraction
            out.append(f'<path d="M{x} {top}v{height} M{left} {y}h{width}" stroke="#cddfd7"/>')
            text(x-17,446,f'{west+(east-west)*fraction:.1f}°',12)
            text(16,y+4,f'{north-(north-south)*fraction:.1f}°',12)
        palette=('#288997','#438f75','#c79943','#d17d40','#c35244')
        stride=max(1,math.ceil(len(rows)/1600))
        points=[]
        for row in rows[::stride]:
            lon,lat=row['longitude'],row['latitude']
            if not west<=lon<=east or not south<=lat<=north:continue
            x=left+(lon-west)/(east-west)*width
            y=top+(north-lat)/(north-south)*height
            band=min(4,int(5*(row['brightness_k']-low)/(high-low))) if high>low else 2
            out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.3" fill="{palette[band]}" fill-opacity=".77"/>')
            points.append(row)
        rect(654,102,274,365,'#143532')
        text(676,136,'SATELLITE RECORDS',13,'#a8d2c4',700)
        text(676,205,f'{len(rows):,}',63,'#f9fffc',700)
        text(677,231,'returned detections',15,'#d1e7dd',600)
        out.append('<path d="M676 252H906" stroke="#45635a"/>')
        text(677,284,payload.get('sensor') or 'NASA FIRMS',17,'#f6fff9',700)
        mode='Near real time' if (payload.get('product') or '').endswith('_NRT') else 'Standard processing'
        text(677,308,mode,13,'#aed0c2')
        if rows:
            for i,color in enumerate(palette):
                rect(677+i*36,344,31,9,color)
            text(677,377,f'Channel brightness · {low:g}–{high:g} K',13,'#e3f1e9',600)
        else:
            text(677,354,'No coordinates returned',13,'#e3f1e9',600)
        out.append('<path d="M32 483H928" stroke="#d7e5dd"/>')
        text(32,513,'NASA FIRMS',13,'#234f43',700)
        text(142,513,f'{len(points):,} of {len(rows):,} returned detections plotted.',13,'#526a64')
        visual={'kind':kind,'points':points,'total':len(rows),'scope':scope,'product':payload['product'],'title':title}
    elif kind=='archived-readings':
        rows=payload['records']
        total=payload['total']
        text(32,123,f'{total:,} matching original archive records',17,'#234f43',700)
        rect(32,145,896,36,'#143532')
        columns=[(48,'Acquired UTC'),(285,'Source'),(475,'Latitude'),(620,'Longitude'),(778,'FRP (MW)')]
        for x,label in columns:text(x,168,label,13,'#f6fff9',700)
        for index,row in enumerate(rows[:8]):
            y=187+index*35
            rect(32,y,896,32,'#eaf3ed' if index%2==0 else '#f0f6f1')
            values=(row['acquisition_utc'].replace('T',' ')[:16],row['source_id'],
                    f"{row['lat']:.5f}",f"{row['lon']:.5f}",row['frp_raw'] if row['frp_raw'] is not None else '—')
            for (x,_),value in zip(columns,values):text(x,y+21,value,14)
        if not rows:text(48,227,'No original records match this archive window.',16,'#526a64',600)
        text(32,503,'NASA FIRMS archive',13,'#234f43',700)
        text(182,503,f'{min(8,len(rows)):,} shown · {len(rows):,} frozen in the source page',13,'#526a64')
        visual={'kind':kind,'title':title,'scope':scope,'rows':rows[:8],'total':total}
    elif kind in _SUMMARY_OPERATIONS:
        facts=snapshot.get('facts',[])
        for index,fact in enumerate(facts[:7]):
            y=108+index*53
            rect(32,y,896,47,'#eaf3ed' if index%2==0 else '#f0f6f1')
            label=str(fact.get('label','Value'))
            value=fact.get('value')
            display='Unavailable' if value is None else str(value)
            units=str(fact.get('unit',''))
            text(49,y+28,label[:60],15,'#264541',600)
            text(904,y+28,(display+' '+units if isinstance(value,(int,float)) else display)[:52],15,'#102d2b',700,'end')
        if not facts:text(48,149,'No display values are available for this scope.',16,'#526a64',600)
        text(32,503,'Saved source',13,'#234f43',700)
        if kind in ('monthly-comparability-summary','harmonized-summary'):
            text(145,503,'Evaluated monthly overlap · original and adjusted series are distinct',13,'#526a64')
        else:
            text(145,503,'Open source for the full verified calculation and scope.',13,'#526a64')
        visual={'kind':kind,'title':title,'scope':scope,'facts':facts}
    elif kind=='coordinates':
        rows=payload.get('records',[])
        if not isinstance(rows,list):raise StudioError('The coordinate source is unavailable.')
        w,s,e,n=scope['bbox']
        rect(75,105,820,325,'#e7f0eb')
        for i in range(5):
            x=75+820*i/4;y=105+325*i/4
            text(x-20,454,f'{w+(e-w)*i/4:.3f}°',12)
            text(8,y+4,f'{n-(n-s)*i/4:.3f}°',11)
        points=[]
        for row in rows:
            lon,lat=row.get('lon'),row.get('lat')
            if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (lon,lat)) or not w<=lon<=e or not s<=lat<=n:continue
            x=75+820*(lon-w)/(e-w);y=105+325*(n-lat)/(n-s)
            color=next((c for source,_,c in SENSORS if source==row.get('source_id')),'#7456a3')
            out.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="3.5" fill="{color}" fill-opacity=".75"/>')
            points.append({'longitude':lon,'latitude':lat,'source':row.get('source_id'),'acquisition_utc':row.get('acquisition_utc')})
        shown_sensors=[item for item in SENSORS if scope.get('source','joint') in ('joint',item[0])]
        for index,(_,label,color) in enumerate(shown_sensors):
            rect(75+index*115,467,10,10,color);text(91+index*115,478,label,13)
        text(75+len(shown_sensors)*115,478,'Original coordinates; overlapping marks remain separate',12)
        text(32,504,f"Showing {len(points)} returned records of {payload.get('total','unknown')} matching rows; bounded page, not a perimeter.",13)
        visual={'kind':kind,'points':points,'total':payload.get('total'),'truncated':payload.get('truncated',False),'scope':scope}
    elif kind in ('satellites','park-satellites'):
        sensors=SENSORS+(('VIIRS_NOAA20_SP','NOAA-20','#7456a3'),('VIIRS_NOAA21_SP','NOAA-21','#318157')) if kind=='park-satellites' else tuple(item for item in SENSORS if scope.get('source','joint') in ('joint',item[0]))
        values=[]
        if kind=='park-satellites':
            values=[{'date':row['date'],'sources':{source:{'value':row['values'][source],'state':row['states'][source]} for source,_,_ in sensors}} for row in payload.get('rows',[])]
        else:
            for frame in payload.get('frames',[]):
                row={'date':frame['date_utc'],'sources':{}}
                for source,_,_ in sensors:
                    product=frame['products'][source];count=product['detections']
                    row['sources'][source]={'value':count if count>0 or product['state']=='complete_export' else None,'state':product['state']}
                values.append(row)
        if not values:raise StudioError('No frozen satellite rows are available.')
        maximum=max([1]+[item['value'] for row in values for item in row['sources'].values() if item['value'] is not None])
        left,top,width,height=75,128,820,265
        for i in range(5):
            y=top+height-i*height/4
            out.append(f'<path d="M{left} {y}h{width}" stroke="#d9e5df"/>')
            text(18,y+4,str(round(maximum*i/4)),11)
        slot=width/len(values);bar=min(28,slot/(len(sensors)+1))
        for i,row in enumerate(values):
            for j,(source,_,color) in enumerate(sensors):
                value=row['sources'][source]['value'];x=left+i*slot+slot/2+(j-len(sensors)/2)*bar
                if value is None:text(x,top+height-5,'?',11,'#64746b')
                else:rect(x,top+height-value/maximum*height,bar-2,value/maximum*height,color)
            if len(values)<=12 or i%max(1,math.ceil(len(values)/10))==0:text(left+i*slot+slot/2-19,420,row['date'][5:],11)
        for i,(_,label,color) in enumerate(sensors):rect(45+i*225,446,12,12,color);text(65+i*225,457,label+' · detections',12)
        text(32,490,'? = unavailable export. Positive partial records are shown; empty unknown dates are not zero.',12)
        text(32,515,'Source-specific detections · not a unique-fire count, burned area or harmonized total.',12)
        visual={'kind':kind,'values':values,'domain':[0,maximum],'unit':'detection records','scope':scope}
    elif kind=='similar':
        reference=payload['reference'];candidates=payload.get('candidates',[])
        panels=[{'label':'Reference · '+reference['source'],**reference},*[{'label':'Candidate · '+row['region'],**row} for row in candidates[:3]]]
        for index,panel in enumerate(panels):
            x=35+(index%2)*465;y=105+(index//2)*175
            rect(x,y,435,158,'#edf5ef' if index==0 else '#eef1f8')
            text(x+12,y+23,panel['label'],14)
            text(x+12,y+43,panel['start']+' – '+panel['end'],11)
            counts=panel['counts'];maximum=max([1]+counts)
            points=' '.join(f'{x+25+i*385/max(1,len(counts)-1):.2f},{y+127-value/maximum*65:.2f}' for i,value in enumerate(counts))
            out.append(f'<polyline points="{points}" fill="none" stroke="#287665" stroke-width="3"/>')
            text(x+12,y+147,'0–'+str(maximum)+' records/day'+(' · profile distance '+str(panel['distance']) if 'distance' in panel else ''),11)
        text(32,480,'Imported records before alias deduplication · may differ from replay detection counts.',12)
        text(32,501,'Imported archive regions: '+', '.join(item['region'] for item in payload.get('coverage',[]))+' · worldwide completeness unknown.',12)
        text(32,522,'Descriptive candidates, not validated fire or causal analogues; candidate drivers are unmeasured.',12)
        visual={'kind':kind,'reference':reference,'candidates':candidates[:3],'coverage':payload.get('coverage',[]),'criterion':payload['criterion'],'scope':scope}
    elif kind=='archive':
        windows=payload.get('windows',[])
        shown=windows[:8];maximum=max([1]+[row['imported_records'] for row in shown])
        for i,row in enumerate(shown):
            y=117+i*41;text(35,y+17,row['month'],15);rect(140,y,530*row['imported_records']/maximum,24,'#2e8870')
            text(690,y+17,str(row['imported_records'])+' records · '+str(row['detected_days'])+' dates',13)
        if not shown:text(35,145,'No matching imported windows in this requested archive scope.',17)
        text(32,475,f"Top {len(shown)} of {payload.get('total_windows',len(windows))} monthly windows in boundary {scope['bbox']}",12)
        text(32,501,'Candidate observation windows, not confirmed incidents or validated similar causes.',13)
        visual={'kind':kind,'windows':shown,'total_windows':payload.get('total_windows'),'scope':query_scope,'reference_scope':scope}
    elif kind=='factors':
        cells=payload.get('cells') or []
        if not cells:raise StudioError('The measured environmental grid is unavailable.')
        west,south,east,north=payload['bbox']
        for panel,(field,label) in enumerate((('ndvi_median','NDVI median'),('elevation_median_m','Elevation median (m)'))):
            left=45+panel*465;top=135;width=400;height=285
            numbers=[cell[field] for cell in cells]
            low,high=min(numbers),max(numbers)
            text(left,110,label,18)
            for cell in cells:
                w,s,e,n=cell['bbox']
                x=left+(w-west)/(east-west)*width;y=top+(north-n)/(north-south)*height
                t=(cell[field]-low)/(high-low) if high>low else .5
                color=f'rgb({int(230-190*t)},{int(244-110*t)},{int(226-130*t)})' if panel==0 else f'rgb({int(235-115*t)},{int(234-165*t)},{int(249-85*t)})'
                rect(x,y,(e-w)/(east-west)*width,(n-s)/(north-south)*height,color)
                text(x+4,y+16,cell['id'],9,'#203d34')
            text(left,447,f'Range: {low} – {high}',13)
        text(32,477,'Environmental window: '+str(payload.get('feature_window','unavailable')),12)
        text(32,499,'Separate recorded MODIS outcome: '+str(payload.get('outcome_window','unavailable')),12)
        text(32,521,'Context does not establish impact. Weather, human activity and other unmeasured drivers remain unknown.',12)
        visual={'kind':kind,'cells':cells,'source_sha256':payload.get('source_sha256'),'feature_window':payload.get('feature_window'),'outcome_window':payload.get('outcome_window'),'scope':scope}
    else:
        target=payload.get('target') or {};matches=payload.get('matches') or []
        rows=[target,*matches[:5]]
        if not target:raise StudioError('The environmental target is unavailable.')
        text(32,105,'Pilot cells · pre-window NDVI and elevation · observed outcomes remain separate',14)
        text(32,140,'Cell',14);text(230,140,'NDVI median',14);text(500,140,'Elevation median (m)',14)
        for i,row in enumerate(rows):
            y=178+i*43
            text(32,y,str(row.get('id',row.get('cell_id','unknown')))+(' · target' if i==0 else ''),14)
            text(230,y,str(row.get('ndvi_median','unavailable')),14)
            text(500,y,str(row.get('elevation_median_m','unavailable')),14)
        text(32,476,'Existing same-date Park spatial pilot; measured similarity is not causal impact.',13)
        text(32,503,'Weather, human activity and other unmeasured drivers remain untested.',13)
        visual={'kind':kind,'target':target,'matches':matches[:5],'scope':scope}
    out.append('</svg>')
    return {'svg':''.join(out),'visual':visual,'snapshot_sha256':snapshot['snapshot_sha256']}
