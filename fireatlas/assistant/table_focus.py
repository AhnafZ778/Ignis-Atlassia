"""Find an explicitly requested date in a retrieved page of source rows."""
from datetime import date
import calendar
import re

_MONTHS={name.lower():i for i in range(1,13) for name in (calendar.month_name[i],calendar.month_abbr[i])}
_MONTH=r'(?:'+ '|'.join(sorted(_MONTHS,key=len,reverse=True)) +r')'


def requested_dates(question):
    dates=set()
    for match in re.finditer(r'\b(\d{4})-(\d{2})-(\d{2})\b',question):
        try:dates.add(date(*map(int,match.groups())).isoformat())
        except ValueError:pass
    for match in re.finditer(r'\b('+_MONTH+r')\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s+(\d{4})\b',question,re.I):
        try:dates.add(date(int(match[3]),_MONTHS[match[1].lower()],int(match[2])).isoformat())
        except ValueError:pass
    return dates


def requested_date(question):
    dates=requested_dates(question)
    return next(iter(dates)) if len(dates)==1 else None


def matching_row(question,rows):
    """Return date and unique matching row; ambiguous or absent rows stay unknown."""
    wanted=requested_date(question)
    if not wanted:
        # Resolve a yearless date only when the returned source rows identify
        # exactly one full ISO date, rather than asking for an obvious year.
        partials={( _MONTHS[m[1].lower()],int(m[2])) for m in re.finditer(r'\b('+_MONTH+r')\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b',question,re.I)}
        if len(partials)==1:
            month,day=next(iter(partials));candidates=set()
            for row in rows:
                for cell in row if isinstance(row,list) else []:
                    if not isinstance(cell,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',cell.strip()):continue
                    try:parsed=date.fromisoformat(cell.strip())
                    except ValueError:continue
                    if (parsed.month,parsed.day)==(month,day):candidates.add(parsed.isoformat())
            if len(candidates)==1:wanted=next(iter(candidates))
    if not wanted:return None,None
    matches=[index for index,row in enumerate(rows) if isinstance(row,list) and any(isinstance(cell,str) and cell.strip()==wanted for cell in row)]
    return wanted,matches[0] if len(matches)==1 else None


def chronological_pattern(groups):
    """Describe successive means only for a complete, strictly dated series."""
    import math
    if not isinstance(groups,list) or len(groups)<2:return None
    points=[]
    for group in groups:
        label=group.get('group');value=group.get('mean')
        if not isinstance(label,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',label) or isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):return None
        try:date.fromisoformat(label)
        except ValueError:return None
        points.append((label,value))
    if any(points[i][0]>=points[i+1][0] for i in range(len(points)-1)):return None
    changes=[points[i+1][1]-points[i][1] for i in range(len(points)-1)]
    return {'successive_direction':['increase' if v>0 else 'decrease' if v<0 else 'unchanged' for v in changes],
            'intervals':[{'from':points[i][0],'to':points[i+1][0],'change':change} for i,change in enumerate(changes)]}


def contradicts_pattern(text,pattern):
    """Detect a bounded set of claims about every consecutive interval."""
    if not pattern:return False
    lower=text.lower()
    extreme=re.search(r'\b(?:steepest|largest|greatest|biggest)\s+(?:decline|decrease|drop|fall)\b[^.!?]*\bafter\s+(?:the\s+)?(first|second|third|fourth|fifth)\b',lower)
    if extreme:
        index=('first','second','third','fourth','fifth').index(extreme[1])
        changes=[item['change'] for item in pattern['intervals']]
        if index>=len(changes) or changes[index]>=0 or changes[index]!=min(changes):return True
    if not re.search(r'\b(steadily|consistently|monotonically|every day|each day)\b',lower):return False
    directions=pattern['successive_direction']
    if re.search(r'\b(declin\w*|decreas\w*|drop\w*|fall\w*|fell)\b',lower):return any(value!='decrease' for value in directions)
    if re.search(r'\b(increas\w*|rise|rises|rising|risen|rose|grow\w*|grew)\b',lower):return any(value!='increase' for value in directions)
    return False


def neighboring_comparisons(payload,question):
    """Compare actual numeric cells with the nearest earlier dated source row.

    This is a display comparison, not a trend model or an inference about fire
    intensity. Dates and original scalar strings remain available for binding.
    """
    from decimal import Decimal,InvalidOperation
    rows=payload.get('rows',[])
    selected_day,index=matching_row(question,rows)
    if index is None:return []
    date_columns=[i for i,value in enumerate(rows[index]) if value.strip()==selected_day]
    if len(date_columns)!=1:return []
    date_column=date_columns[0]
    dated=[]
    for i,row in enumerate(rows):
        try:day=date.fromisoformat(row[date_column].strip())
        except (ValueError,IndexError,TypeError):continue
        if day.isoformat()<selected_day:dated.append((day,i))
    if not dated:return []
    previous_day=max(day for day,_ in dated)
    prior=[i for day,i in dated if day==previous_day]
    if len(prior)!=1:return []
    previous=rows[prior[0]];comparisons=[]
    names={'MODIS_SP':'MODIS','VIIRS_SNPP_SP':'VIIRS S-NPP','VIIRS_NOAA20_SP':'VIIRS NOAA-20','VIIRS_NOAA21_SP':'VIIRS NOAA-21'}
    for column,(before,after) in enumerate(zip(previous,rows[index])):
        if column==date_column:continue
        try:a,b=Decimal(before.strip()),Decimal(after.strip())
        except (InvalidOperation,ValueError,TypeError):continue
        if not a.is_finite() or not b.is_finite():continue
        comparisons.append({'field':names.get(payload['columns'][column],payload['columns'][column]),
            'previous_date':previous_day.isoformat(),'previous_value':before,'selected_date':selected_day,
            'selected_value':after,'direction':'higher' if b>a else 'lower' if b<a else 'unchanged'})
    return comparisons


# Compare explicit scalar transitions only. Dates and unqualified ranges are not
# directional claims, and values from different clauses are not paired.
_NUMBER = r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
_CHANGE = re.compile(
    r'\b(?P<direction>increas\w*|decreas\w*|declin\w*|ris(?:e|es|ing|en)|rose|'
    r'drop\w*|fell|fall\w*|grew|grow\w*)\b[^.;!?]{0,48}?\bfrom\s+'
    r'(?P<before>'+_NUMBER+r')\s*%?\s+to\s+(?P<after>'+_NUMBER+r')(?![\w+-]|[.,]\d)',
    re.I,
)


def contradicts_numeric_change(text):
    """Reject a stated increase or decrease that reverses its own values."""
    from decimal import Decimal
    for match in _CHANGE.finditer(text):
        if re.search(r"(?:\bnot|\bnever|n't)\s+$", text[max(0, match.start()-12):match.start()], re.I):
            continue
        before, after = (Decimal(match[key].replace(',', '')) for key in ('before', 'after'))
        upward = match['direction'].lower().startswith(('increas', 'ris', 'rose', 'grew', 'grow'))
        if (after <= before if upward else after >= before):
            return True
    return False
