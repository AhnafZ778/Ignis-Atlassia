"""Bounded, immutable user CSV tables stored separately from NASA observations."""
import csv
import hashlib
import io
import math
import re
import secrets

from .errors import LimitExceeded, NotFound, StudioError
from .store import dumps

MAX_BYTES=5*1024*1024
MAX_ROWS=50000
MAX_COLUMNS=100
MAX_BOARD_BYTES=50*1024*1024
NUMBER=re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?')


def numeric(value):
    value=value.strip()
    if not NUMBER.fullmatch(value):return None
    result=float(value)
    return result if math.isfinite(result) else None


def parse_csv(data,offset=0,limit=10):
    if type(offset) is not int or type(limit) is not int or offset<0 or not 1<=limit<=100:
        raise StudioError('Choose a valid row range of at most 100 rows.',code='invalid-csv')
    if not isinstance(data,bytes) or not data or len(data)>MAX_BYTES:
        raise LimitExceeded('Choose a CSV up to 5 MiB.',code='dataset-limit')
    try:
        text=data.decode('utf-8-sig')
        reader=csv.reader(io.StringIO(text,newline=''),strict=True)
        header=next(reader)
        if not header or len(header)>MAX_COLUMNS or any(not value.strip() or len(value)>200 for value in header) or len(set(header))!=len(header):
            raise StudioError('CSV needs unique, nonempty column names (at most 100 columns).',code='invalid-csv')
        count=0;preview=[]
        for row in reader:
            if len(row)!=len(header):raise StudioError('Every CSV row must have the same number of fields as the header.',code='invalid-csv')
            if any(len(value)>10000 for value in row):raise LimitExceeded('A CSV field exceeds 10,000 characters.',code='dataset-limit')
            if offset<=count<offset+limit:preview.append(row)
            count+=1
            if count>MAX_ROWS:raise LimitExceeded('A CSV may have at most 50,000 rows.',code='dataset-limit')
    except (UnicodeDecodeError,csv.Error,StopIteration):
        raise StudioError('Choose a valid UTF-8 CSV with a header row.',code='invalid-csv') from None
    return {'columns':header,'row_count':count,'preview':preview}


def add(store, principal, document_id, name, data):
    parsed=parse_csv(data)
    if not isinstance(name,str) or not name.strip() or len(name)>200 or any(ord(c)<32 for c in name):
        raise StudioError('Choose a valid dataset name.',code='invalid-csv')
    digest=hashlib.sha256(data).hexdigest()
    with store.connection(write=True) as db:
        store.require(db,principal,document_id,'editor')
        existing=db.execute('SELECT id,name,row_count,columns_json FROM datasets WHERE document_id=? AND sha256=?',(document_id,digest)).fetchone()
        if existing:
            return {'id':existing['id'],'name':existing['name'],'sha256':digest,**parsed,'existing':True}
        total=db.execute('SELECT COALESCE(SUM(length(content)),0) FROM datasets WHERE document_id=?',(document_id,)).fetchone()[0]
        if total+len(data)>MAX_BOARD_BYTES:raise LimitExceeded('This board exceeds its 50 MiB dataset limit.',code='dataset-limit')
        identifier='dataset_'+secrets.token_urlsafe(12)
        db.execute('INSERT INTO datasets VALUES(?,?,?,?,?,?,?,?,?)',(identifier,document_id,principal,name.strip(),digest,data,parsed['row_count'],dumps(parsed['columns']),store.clock()))
    return {'id':identifier,'name':name.strip(),'sha256':digest,**parsed,'existing':False}


def read(store,principal,document_id,identifier,offset=0,limit=10):
    with store.connection() as db:
        store.require(db,principal,document_id)
        row=db.execute('SELECT * FROM datasets WHERE document_id=? AND id=?',(document_id,identifier)).fetchone()
        if not row:raise NotFound('Dataset not found.')
        data=bytes(row['content'])
        if hashlib.sha256(data).hexdigest()!=row['sha256']:raise StudioError('Stored dataset integrity check failed.',code='dataset-corrupt')
        return {'id':row['id'],'name':row['name'],'sha256':row['sha256'],'offset':offset,**parse_csv(data,offset,limit)},data


def list_datasets(store,principal,document_id):
    with store.connection() as db:
        store.require(db,principal,document_id)
        return [dict(row) for row in db.execute('SELECT id,name,sha256,row_count FROM datasets WHERE document_id=? ORDER BY created,id',(document_id,))]


def scatter(store,principal,document_id,identifier,x_column,y_column):
    info,data=read(store,principal,document_id,identifier)
    if x_column not in info['columns'] or y_column not in info['columns'] or x_column==y_column:
        raise StudioError('Choose two different columns from this table.',code='invalid-columns')
    x_index,y_index=info['columns'].index(x_column),info['columns'].index(y_column)
    reader=csv.reader(io.StringIO(data.decode('utf-8-sig'),newline=''),strict=True);next(reader)
    points=[];skipped=0
    for index,row in enumerate(reader, start=2):
        try:
            x,y=numeric(row[x_index]),numeric(row[y_index])
            if x is None or y is None:raise ValueError()
        except ValueError:
            skipped+=1;continue
        points.append({'row':index,'x':x,'y':y})
        if len(points)>5000:raise LimitExceeded('This scatter plot supports at most 5,000 numeric rows; use a smaller table.',code='dataset-limit')
    if not points:raise StudioError('These columns have no rows with two numeric values.',code='invalid-columns')
    return {'dataset_id':identifier,'sha256':info['sha256'],'name':info['name'],'x_column':x_column,'y_column':y_column,
            'points':points,'skipped_rows':skipped,'total_rows':info['row_count']}


def summarize(store,principal,document_id,identifier,columns):
    """Descriptive statistics over all rows; missing and nonnumeric values remain separate."""
    info,data=read(store,principal,document_id,identifier)
    if not isinstance(columns,list) or not 1<=len(columns)<=8 or any(not isinstance(c,str) or c not in info['columns'] for c in columns) or len(set(columns))!=len(columns):
        raise StudioError('Choose up to eight distinct columns from this table.',code='invalid-columns')
    indices=[info['columns'].index(column) for column in columns]
    values=[[] for _ in columns];missing=[0]*len(columns);invalid=[0]*len(columns)
    reader=csv.reader(io.StringIO(data.decode('utf-8-sig'),newline=''),strict=True);next(reader)
    for row in reader:
        for i,index in enumerate(indices):
            cell=row[index].strip()
            if not cell:missing[i]+=1;continue
            number=numeric(cell)
            if number is None:invalid[i]+=1
            else:values[i].append(number)
    summaries=[]
    for i,column in enumerate(columns):
        samples=sorted(values[i]);count=len(samples)
        stats={'column':column,'numeric_count':count,'missing_count':missing[i],'non_numeric_count':invalid[i],
               'minimum':None,'maximum':None,'mean':None,'median':None}
        if count:
            scale=max(abs(samples[0]),abs(samples[-1])) or 1.0
            mean=(math.fsum(v/scale for v in samples)/count)*scale
            mid=count//2
            median=samples[mid] if count%2 else ((samples[mid-1]/scale+samples[mid]/scale)/2)*scale
            stats.update(minimum=samples[0],maximum=samples[-1],mean=mean,median=median)
        summaries.append(stats)
    return {'dataset_id':identifier,'sha256':info['sha256'],'name':info['name'],'total_rows':info['row_count'],
            'columns':summaries,'numeric_format':'binary64','note':'All rows included. Values without a finite numeric format are counted separately; units are not inferred.'}


def group_summary(store,principal,document_id,identifier,group_column,value_column):
    """Compare numeric values by exact category without dropping missing data."""
    info,data=read(store,principal,document_id,identifier)
    if group_column not in info['columns'] or value_column not in info['columns'] or group_column==value_column:
        raise StudioError('Choose two different existing columns.',code='invalid-columns')
    groups={};gi=info['columns'].index(group_column);vi=info['columns'].index(value_column)
    reader=csv.reader(io.StringIO(data.decode('utf-8-sig'),newline=''),strict=True);next(reader)
    for row in reader:
        name=row[gi].strip() or None
        if name is not None and len(name)>200:raise LimitExceeded('Group labels may contain at most 200 characters.',code='group-limit')
        if name not in groups:
            if len(groups)>=30:raise LimitExceeded('Choose a column with at most 30 distinct groups.',code='group-limit')
            groups[name]={'rows':0,'missing':0,'nonnumeric':0,'values':[]}
        group=groups[name];group['rows']+=1;cell=row[vi].strip()
        if not cell:group['missing']+=1
        elif (number:=numeric(cell)) is None:group['nonnumeric']+=1
        else:group['values'].append(number)
    output=[]
    for name,group in sorted(groups.items(),key=lambda item:(item[0] is None,item[0] or '')):
        values=group['values'];scale=max((abs(v) for v in values),default=0) or 1.0
        output.append({'group':name,'rows':group['rows'],'numeric_count':len(values),'missing_count':group['missing'],
                       'non_numeric_count':group['nonnumeric'],'mean':math.fsum(v/scale for v in values)/len(values)*scale if values else None})
    return {'dataset_id':identifier,'sha256':info['sha256'],'name':info['name'],'group_column':group_column,'value_column':value_column,
            'total_rows':info['row_count'],'groups':output,'note':'All rows included. Blank group labels are unknown; units and causes are not inferred.'}
