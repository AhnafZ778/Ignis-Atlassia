"""Allowlisted display actions; never model-authored selectors or JavaScript."""
TARGETS={
 'overview-globe':('overview','earth-frame-host','Existing Earth globe and satellite'),
 'terrain-globe':('terrain','earth','Standalone terrain Earth'),
 'source-catalog':('sources','source-catalog','Imported source catalog'),
 'archive-ledger':('sources','data-references','Source files and reproducibility'),
 'native-files':('sources','native-mask-downloads','Native NASA files'),
 'imports':('sources','import-workflow','Import workflow'),
 'calculation-method':('method','data-flow','Calculation method'),
 'native-review':('review','sample-workspace','Native mask review'),
 'atlas-map':('atlas','atlas-section','Geographic atlas'),
 'raw-calendar':('calendar','calendar-section','Raw observation calendar'),
 'harmonized-calendar':('harmonized','harmonized-calendar','Harmonized calendar'),
 'sensor-overlap':('overlap','overview-result','Sensor overlap results'),
 'candidate-groups':('candidates','candidate-list','Connected detection groups'),
 'coverage-rates':('exposure','coverage-output','Observation coverage denominators'),
 'validation-gates':('validation','validation-gates','Scientific validation gates'),
 'replay-map':('replay','replay-workspace','Historical replay map'),
 'replay-timeline':('timeline','replay-timeline','UTC day replay'),
 'replay-records':('records','source-records','Original observation rows'),
 'assistant-map':('assistant','mission-map-stage','Current observation map'),
 'assistant-records':('assistant','mission-panel-evidence','Exact calculation evidence'),
 'assistant-sources':('assistant','mission-panel-network','Source availability'),
}

VIEW_SETTINGS={
 'assistant':{'source','metric','layer','scope','split','day'},
 'atlas':{'source','layer','day'},'calendar':{'source','layer','day'},'harmonized':{'source','layer','day'},
 'replay':{'source','metric','layer','day','view'},'timeline':{'source','metric','layer','day','view'},'records':{'source','metric','layer','day','view'},
}

VISUAL_KINDS={'replay':'daily','missingness':'availability','research':'overlap','exposure':'overlap',
             'archive_search':'archive','availability':'inventory','persistence':'persistence','compare':'comparison'}

def validate_visualization(evidence,kind):
    """Charts select an existing calculation; the model supplies no chart values."""
    if kind!='workflow' and VISUAL_KINDS.get(evidence['operation'])!=kind:
        raise ValueError('Choose a visualization matching the retrieved calculation, or a workflow diagram.')
    return {'result_id':evidence['id'],'kind':kind}

def validate_options(options):
    value=dict(options or {})
    if set(value)-{'kind','target','place_id','candidate_id','settings'}:raise ValueError('Unsupported display parameters.')
    kind=value.setdefault('kind','navigate')
    if kind not in {'navigate','focus_place','highlight','set_view'}:raise ValueError('Unsupported display action.')
    if (kind=='highlight' or 'target' in value) and value.get('target') not in TARGETS:raise ValueError('Unknown visual target.')
    if kind=='focus_place' and not isinstance(value.get('place_id'),str):raise ValueError('Resolve a place before focusing it.')
    if value.get('candidate_id') is not None and (not isinstance(value['candidate_id'],str) or len(value['candidate_id'])>100):raise ValueError('Invalid candidate identifier.')
    settings=value.get('settings',{})
    allowed={'source':{'joint','MODIS_SP','VIIRS_SNPP_SP'},'metric':{'density','persistence','frp'},'layer':{'none','ndvi','landcover','terrain','burned-area'},'view':{'2d','3d'},'scope':{'daily','history'},'split':{True,False},'day':None}
    if not isinstance(settings,dict) or set(settings)-set(allowed):raise ValueError('Unsupported view setting.')
    for key,val in settings.items():
        if key=='day':
            from datetime import date
            if not isinstance(val,str):raise ValueError('UTC day must be an ISO date string.')
            date.fromisoformat(val)
        elif key=='split':
            if type(val) is not bool:raise ValueError('Comparison state must be a boolean.')
        elif not isinstance(val,str) or val not in allowed[key]:raise ValueError('Unsupported '+key+' setting.')
    return value
