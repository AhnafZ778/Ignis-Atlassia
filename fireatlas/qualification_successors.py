"""Authoritative public summaries for frozen opportunity/transfer successors.

No human review is generated. Missing source campaigns remain explicitly absent.
Raw native sample states and validated opportunity are separate contracts.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from contextlib import closing
from datetime import date,timedelta
from dataclasses import dataclass
import gzip,hashlib,io,json,sqlite3
from pathlib import Path
from .qualification import digest
from . import opportunity_frames as frames,opportunity_review,transfer_opportunity
from .validity import CASES

MAX_EXPANDED=512_000_000
MAX_COMPRESSED=128_000_000

@dataclass(frozen=True)
class FrozenFile:
    path: Path
    bytes: int
    sha256: str


def frozen_file(path):
    path=Path(path)
    with path.open('rb') as stream:
        hasher=hashlib.sha256()
        for block in iter(lambda:stream.read(1024*1024),b''):hasher.update(block)
        sha=hasher.hexdigest()
    return FrozenFile(path,path.stat().st_size,sha)


def load_with_reference(path,expected_sha256=None):
    path=Path(path)
    with path.open('rb') as source:compressed=source.read(MAX_COMPRESSED+1)
    if len(compressed)>MAX_COMPRESSED:raise ValueError('Successor artifact compressed size exceeds bound.')
    reference=FrozenFile(path,len(compressed),hashlib.sha256(compressed).hexdigest())
    if expected_sha256 is not None and reference.sha256!=expected_sha256:raise ValueError('Successor source bytes differ from their registered hash.')
    with gzip.GzipFile(fileobj=io.BytesIO(compressed),mode='rb') as stream:body=stream.read(MAX_EXPANDED+1)
    if len(body)>MAX_EXPANDED:raise ValueError('Successor artifact expanded size exceeds bound.')
    return json.loads(body),reference


def load(path):
    return load_with_reference(path)[0]


def indexed_path(work,name,*,prefix):
    if not isinstance(name,str) or Path(name).is_absolute():raise ValueError('Relative successor evidence path required.')
    root=Path(work).resolve();path=(root/name).resolve();allowed=(root/prefix).resolve()
    if not allowed.is_relative_to(root) or not path.is_relative_to(allowed):raise ValueError('Successor evidence escapes its counted namespace.')
    return path


def _entry(work,entry,prefix):
    path=indexed_path(work,entry['artifact'],prefix=prefix)
    if not isinstance(entry.get('sha256'),str):raise ValueError('Registered source hash required.')
    value,reference=load_with_reference(path,entry['sha256'])
    if value.get('result_sha256')!=entry.get('result_sha256'):raise ValueError('Successor source result identity differs.')
    return value,reference


def footprint_summary(campaigns,case):
    if case not in CASES:raise ValueError('Fixed native pilot required.')
    first,last=CASES[case]['start'],CASES[case]['end'];scope=frames.domain(case)
    x0,y0,x1,y1=scope['grid_bounds'];expected=(x1-x0)*(y1-y0)
    days=[(date.fromisoformat(first)+timedelta(days=i)).isoformat() for i in range((date.fromisoformat(last)-date.fromisoformat(first)).days+1)]
    cohorts={};cells=defaultdict(dict);groups=defaultdict(set);native_ids=defaultdict(set);boundary_pixels=defaultdict(set)
    campaign_hashes=[];reviewed_flags=[];no_pass_flags=[];review_flags=[];protocols=set()
    for campaign in campaigns:
      if campaign['synthetic'] is not False:raise ValueError('Publication refuses synthetic opportunity campaigns.')
      campaign_hashes.append(campaign['result_sha256']);reviewed_flags.append(campaign['validated_observation_opportunity'])
      no_pass_flags.append(campaign['no_pass_enabled']);review_flags.append(campaign['review_state']['approved']);protocols.add(campaign['protocol']['id'])
      for frame,classified in zip(campaign['frames'],campaign['classified_frames']):
        if frame['scope']['id']!=case or frame['start']<first or frame['end']>last:
            raise ValueError('Opportunity publication scope differs from its native pilot/window.')
        key=digest(frame['cohort']);cohorts[key]=frame['cohort']
        for row in classified['daily_cells']:
            identity=(row['grid_x'],row['grid_y']);bucket=cells[(key,row['date'])]
            if identity in bucket:raise ValueError('Overlapping pilot frame/date cells cannot be pooled.')
            bucket[identity]=row['validated_opportunity']
        native=frames.inventory(frame['inputs'])
        for g in native.values():
            for day in days:
                if g['start_utc'][:10]<=day<=g['end_utc'][:10]:
                    groups[(key,day)].add(g['acquisition_group_id']);native_ids[(key,day)].add(g['producer_id'])
        for pixel in frame['inputs']['pixels']:
            g=native[pixel['producer_id']]
            for day in days:
                if g['start_utc'][:10]<=day<=g['end_utc'][:10]:boundary_pixels[(key,day)].add((pixel['producer_id'],pixel['line'],pixel['sample']))
    entries=[]
    for key,cohort in sorted(cohorts.items(),key=lambda item:(item[1]['source'],item[1]['version'])):
        rows=[]
        for day in days:
            bucket=cells[(key,day)];states=Counter(bucket.values());missing=expected-len(bucket)
            states['unknown']+=missing
            rows.append({'date':day,'expected_cells':expected,'represented_cells':len(bucket),'missing_cells':missing,
                'validated_state_counts':dict(states),'usable_cells':states['detected']+states['observed-without-detection'],
                'unknown_cells':states['unknown'],'acquisition_groups':len(groups[(key,day)]),'candidate_granules':len(native_ids[(key,day)]),
                'boundary_pixels':len(boundary_pixels[(key,day)])})
        entries.append({'cohort':cohort,'days':rows})
    complete={e['cohort']['source'] for e in entries}=={'MODIS_SP','VIIRS_SNPP_SP'} and all(day['represented_cells']==expected for entry in entries for day in entry['days'])
    reviewed=bool(reviewed_flags) and all(reviewed_flags)
    return {'schema':'fireatlas-footprint-support-summary-v2','case_id':case,'start':first,'end':last,
        'state':('reviewed-opportunity' if complete else 'reviewed-partial-evidence') if reviewed else 'pending-evidence',
        'campaign_sha256s':campaign_hashes,'protocol_ids':sorted(protocols),'cohorts':entries,
        'scope_complete':complete,'reviewed_frames':reviewed,
        'validated_observation_opportunity':reviewed and complete,'no_pass_enabled':bool(no_pass_flags) and all(no_pass_flags) and complete,
        'review_approved':bool(review_flags) and all(review_flags),'units':'clipped common-grid cells per UTC date; acquisition groups are not verified complete passes',
        'full_evidence':f'footprint-campaign/{case}.json.gz',
        'interpretation':'Unknown cells include missing tiles, native boundaries, quality or independent review. Zero usable cells with unknown support does not mean no fire or no observation.'}


def _packets(work,name,*,with_reference=False):
    if name is None:return
    path=indexed_path(work,name,prefix='transfer-opportunity-v2')
    if path.stat().st_size>4_000_000:raise ValueError('Opportunity packet index exceeds bound.')
    index=json.loads(path.read_text())
    if index.get('schema')!='fireatlas-transfer-opportunity-packet-index-v1' or not isinstance(index.get('files'),list) or len(index['files'])>transfer_opportunity.MAX_PACKETS:
        raise ValueError('Versioned bounded opportunity packet index required.')
    seen=set()
    for name in index['files']:
        file=indexed_path(work,name,prefix='opportunity-v2')
        if file in seen:raise ValueError('Duplicate source opportunity packet.')
        seen.add(file);value,reference=load_with_reference(file)
        yield (value,reference) if with_reference else value


def current_transfer_capture(work,count):
    """Read the exact cohort identity while the publisher holds its lock."""
    from . import transfer
    database=Path(work)/'campaign/observations.sqlite3'
    with closing(sqlite3.connect(database.resolve(strict=True).as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        return transfer.capture(db,count['region'],count['source_cohort'],count['target_cohort'])


def provenance_asset(work, entry, count):
    """Recheck an exact registered receipt, retaining stale inputs as pending."""
    if entry is None:return None
    if not isinstance(entry,dict) or set(entry)!={'artifact','sha256','input_sha256'}:
        raise ValueError('A bound provenance registration is required.')
    path=indexed_path(work,entry['artifact'],prefix='provenance-v1')
    with path.open('rb') as stream:body=stream.read(1_000_001)
    if len(body)>1_000_000 or hashlib.sha256(body).hexdigest()!=entry['sha256']:
        raise ValueError('Registered provenance receipt bytes differ.')
    saved=json.loads(body)
    if (saved.get('schema')!='fireatlas-transfer-provenance-verification-v1'
            or saved.get('input_sha256')!=entry['input_sha256']
            or digest({k:v for k,v in saved.items() if k!='result_sha256'})!=saved.get('result_sha256')):
        raise ValueError('Registered provenance receipt identity differs.')
    if saved['input_sha256']!=count['input_sha256']:
        return None  # A prior receipt cannot authenticate a changed capture.
    # New archive months can change the current capture while the registered
    # historical count and receipt still agree with one another. Only this
    # precise identity change is pending; corrupt files and failed recounts
    # must still stop publication. The publisher holds the campaign lock.
    fresh=current_transfer_capture(work,count)
    if fresh['input_sha256']!=count['input_sha256']:
        return None
    del fresh  # The verifier independently captures again; avoid retaining both.
    from .transfer_provenance import verify_capture
    database=Path(work)/'campaign/observations.sqlite3'
    current=verify_capture(count['inputs'],database,Path(work)/'campaign')
    if current!=saved:
        raise ValueError('Registered provenance receipt no longer reproduces its source chain.')
    return saved


def daily_hybrid_asset(work, entry, original, publication_root):
    """Recount an exact daily successor without inheriting an older cohort's evidence."""
    if entry is None:return None
    if not isinstance(entry,dict) or not isinstance(entry.get('sha256'),str):
        raise ValueError('A hash-bound daily hybrid registration is required.')
    path=indexed_path(work,entry['artifact'],prefix='daily-hybrid-v1')
    bundle,reference=load_with_reference(path,entry['sha256'])
    experiment=bundle.get('experiment',{})
    if (bundle.get('schema')!='fireatlas-daily-hybrid-bundle-v1'
            or experiment.get('schema')!='fireatlas-daily-hybrid-experiment-v1'
            or experiment.get('result_sha256')!=entry.get('result_sha256')
            or digest({k:v for k,v in experiment.items() if k!='result_sha256'})!=experiment.get('result_sha256')
            or path.name!=digest(bundle)+'.json.gz'):
        raise ValueError('Registered daily hybrid identity differs.')
    # Changed source cohorts never inherit a previous experiment.
    if bundle.get('original_result_sha256')!=original.get('result_sha256'):
        return None
    if publication_root is None:raise ValueError('Original frozen publication is required for daily hybrid evidence.')
    from . import daily_hybrid_experiment as hybrid,qualification_publication
    source=qualification_publication.read(publication_root,bundle['original_artifact'],bundle['original_release_id'])
    if hashlib.sha256(source).hexdigest()!=bundle.get('original_artifact_sha256'):
        raise ValueError('Daily hybrid source publication bytes differ.')
    with gzip.GzipFile(fileobj=io.BytesIO(source),mode='rb') as stream:body=stream.read(MAX_EXPANDED+1)
    if len(body)>MAX_EXPANDED:raise ValueError('Daily source expanded size exceeds bound.')
    previous=json.loads(body)
    if (digest(previous)!=digest(original) or experiment.get('inputs')!=previous.get('inputs')
            or experiment.get('platform_counts')!=previous.get('platform_counts')
            or experiment.get('region')!=previous.get('region') or experiment.get('versions')!=previous.get('versions')
            or experiment.get('synthetic') is not False or experiment.get('scientific_admission') is not False
            or experiment.get('estimates_admitted') is not False):
        raise ValueError('Daily hybrid inputs, scope or admission differ from source evidence.')
    hybrid.verify(experiment)
    return bundle,reference


def daily_neighbors_asset(work, entry, original, publication_root):
    """Recount an exact daily successor without inheriting an older cohort's evidence."""
    if entry is None:return None
    if not isinstance(entry,dict) or not isinstance(entry.get('sha256'),str):
        raise ValueError('A hash-bound similar-day registration is required.')
    path=indexed_path(work,entry['artifact'],prefix='daily-neighbors-v1')
    bundle,reference=load_with_reference(path,entry['sha256'])
    experiment=bundle.get('experiment',{})
    if (bundle.get('schema')!='fireatlas-daily-neighbors-bundle-v1'
            or experiment.get('schema')!='fireatlas-daily-neighbors-experiment-v1'
            or experiment.get('result_sha256')!=entry.get('result_sha256')
            or digest({k:v for k,v in experiment.items() if k!='result_sha256'})!=experiment.get('result_sha256')
            or path.name!=digest(bundle)+'.json.gz'):
        raise ValueError('Registered similar-day identity differs.')
    # Changed source cohorts never inherit a previous experiment.
    if bundle.get('original_result_sha256')!=original.get('result_sha256'):
        return None
    if publication_root is None:raise ValueError('Original frozen publication is required for similar-day evidence.')
    from . import daily_neighbors_experiment as neighbors,qualification_publication
    source=qualification_publication.read(publication_root,bundle['original_artifact'],bundle['original_release_id'])
    if hashlib.sha256(source).hexdigest()!=bundle.get('original_artifact_sha256'):
        raise ValueError('Similar-day source publication bytes differ.')
    with gzip.GzipFile(fileobj=io.BytesIO(source),mode='rb') as stream:body=stream.read(MAX_EXPANDED+1)
    if len(body)>MAX_EXPANDED:raise ValueError('Daily source expanded size exceeds bound.')
    previous=json.loads(body)
    if (digest(previous)!=digest(original) or experiment.get('inputs')!=previous.get('inputs')
            or experiment.get('platform_counts')!=previous.get('platform_counts')
            or experiment.get('region')!=previous.get('region') or experiment.get('versions')!=previous.get('versions')
            or experiment.get('synthetic') is not False or experiment.get('scientific_admission') is not False
            or experiment.get('estimates_admitted') is not False):
        raise ValueError('Similar-day inputs, scope or admission differ from source evidence.')
    neighbors.verify(experiment)
    return bundle,reference


def daily_diagnostics_asset(work,entry,original,publication_root):
    """Bind descriptive diagnostics to the same recounted frozen daily result."""
    if entry is None:return None
    if not isinstance(entry,dict) or set(entry)!={'artifact','sha256','source_release_id','result_sha256'}:
        raise ValueError('A hash-bound daily diagnostic registration is required.')
    path=indexed_path(work,entry['artifact'],prefix='daily-diagnostics-v1')
    with path.open('rb') as stream:body=stream.read(1_000_001)
    if len(body)>1_000_000 or hashlib.sha256(body).hexdigest()!=entry['sha256']:
        raise ValueError('Registered daily diagnostic bytes differ.')
    report=json.loads(body)
    if (report.get('schema')!='fireatlas-daily-heldout-diagnostic-report-v1'
            or report.get('release_id')!=entry['source_release_id']
            or report.get('result_sha256')!=entry['result_sha256']
            or report.get('scientific_admission') is not False
            or report.get('daily_estimates_admitted') is not False):
        raise ValueError('Registered daily diagnostic identity or admission differs.')
    if original.get('result_sha256')!=entry['result_sha256']:
        return None
    if publication_root is None:raise ValueError('Frozen daily source publication is required.')
    from . import daily_diagnostics,qualification_publication
    from scripts.diagnose_daily_holdouts import source_hashes
    if report.get('method_source_sha256')!=source_hashes():return None
    source=qualification_publication.read(publication_root,report['artifact'],report['release_id'])
    if hashlib.sha256(source).hexdigest()!=report.get('artifact_sha256'):
        raise ValueError('Daily diagnostic source publication bytes differ.')
    with gzip.GzipFile(fileobj=io.BytesIO(source),mode='rb') as stream:raw=stream.read(MAX_EXPANDED+1)
    if len(raw)>MAX_EXPANDED:raise ValueError('Daily diagnostic source exceeds expanded size bound.')
    previous=json.loads(raw)
    if (digest(previous)!=digest(original) or report.get('input_sha256')!=original.get('input_sha256')
            or report.get('region')!=original.get('region') or report.get('versions')!=original.get('versions')
            or report.get('original_checks')!=original.get('checks')
            or report.get('diagnostics')!=daily_diagnostics.analyze(original)):
        raise ValueError('Daily diagnostic scope or recount differs.')
    return report,FrozenFile(path,len(body),hashlib.sha256(body).hexdigest())


def monthly_provenance_asset(work, entry, bundle, *, preflight=None, fingerprints_out=None):
    """Recount a registered receipt while the publisher holds its campaign lock."""
    if entry is None:return None
    if not isinstance(entry,dict) or set(entry)!={'artifact','sha256','monthly_input_sha256','monthly_result_sha256'}:
        raise ValueError('A bound monthly provenance registration is required.')
    path=indexed_path(work,entry['artifact'],prefix='monthly-provenance-v1')
    with path.open('rb') as stream:body=stream.read(1_000_001)
    if len(body)>1_000_000 or hashlib.sha256(body).hexdigest()!=entry['sha256']:
        raise ValueError('Registered monthly provenance receipt bytes differ.')
    saved=json.loads(body)
    if (saved.get('schema')!='fireatlas-monthly-source-provenance-v1'
            or saved.get('monthly_input_sha256')!=entry['monthly_input_sha256']
            or saved.get('monthly_result_sha256')!=entry['monthly_result_sha256']
            or digest({k:v for k,v in saved.items() if k!='result_sha256'})!=saved.get('result_sha256')):
        raise ValueError('Registered monthly provenance receipt identity differs.')
    if (saved['monthly_input_sha256']!=bundle['result']['input_sha256']
            or saved['monthly_result_sha256']!=bundle['result']['result_sha256']):
        return None
    if preflight is not None:
        if (not isinstance(preflight,dict) or set(preflight)!={'entry_sha256','bundle_sha256','status','source_files','database_files','plan_files'}
                or preflight['entry_sha256']!=digest(entry) or preflight['bundle_sha256']!=digest(bundle)
                or preflight['status'] not in ('verified-recount','pending')):
            raise ValueError('Monthly source preflight no longer matches exact publication inputs.')
        if preflight['status']=='pending':return None
        return saved,FrozenFile(path,len(body),hashlib.sha256(body).hexdigest())
    from . import monthly_source_provenance as monthly_source
    database=Path(work)/'campaign/observations.sqlite3';root=Path(work)/'campaign'
    capture=monthly_source.capture_for_bundle(bundle,database)
    if capture['input_sha256']!=saved.get('source_capture_sha256'):
        return None  # A changed source capture cannot inherit a prior receipt.
    if fingerprints_out is None:
        current=monthly_source._verify_while_locked(bundle,capture,database,root)
    else:
        current=monthly_source._verify_while_locked(bundle,capture,database,root,fingerprints_out=fingerprints_out)
    if current!=saved:
        raise ValueError('Registered monthly provenance receipt no longer reproduces its source chain.')
    return saved,FrozenFile(path,len(body),hashlib.sha256(body).hexdigest())


def assets(work,values,*,original_directory=None,publication_root=None,campaign_locked=False,monthly_preflight=None):
    """Recount all source dependencies before adding public bytes.

    Qualified native campaigns need a runtime with GDAL/research dependencies.
    Missing dependencies/originals fail publication; they never downgrade a review.
    """
    work=Path(work);result={};index_path=work/'successor-evidence.json'
    if index_path.exists() and index_path.stat().st_size>1_000_000:raise ValueError('Successor publication index exceeds bound.')
    index=json.loads(index_path.read_text()) if index_path.exists() else {'schema':'fireatlas-successor-evidence-index-v1','footprints':{},'transfers':{}}
    if index.get('schema')!='fireatlas-successor-evidence-index-v1' or set(index.get('footprints',{}))-set(CASES):raise ValueError('Invalid fixed-case successor publication index.')
    monthly_provenance=index.get('monthly_provenance',{})
    if not isinstance(monthly_provenance,dict):raise ValueError('Monthly provenance registrations must be keyed by cohort.')
    known_monthly={name.rsplit('/',1)[1].removesuffix('.json') for name in values if name.startswith('cohort-monthly/')}
    if set(monthly_provenance)-known_monthly:raise ValueError('Registered monthly provenance has no matching published cohort.')
    if monthly_provenance and not campaign_locked:raise ValueError('Monthly source recount requires the publisher campaign lock.')
    if monthly_preflight is not None and (not campaign_locked or set(monthly_preflight)!=set(monthly_provenance)):
        raise ValueError('Complete monthly preflight requires the publisher campaign lock.')
    for region in ('norcal','punjab-haryana'):
        name=f'monthly-cohorts/{region}.json'
        if name not in values:continue
        summary=values[name]
        for item in summary['entries']:
            key=item['id'];bundle=values['cohort-monthly/'+key+'.json']
            checked=monthly_provenance_asset(work,monthly_provenance.get(key),bundle,
                preflight=monthly_preflight.get(key) if monthly_preflight is not None else None)
            if checked is None:
                item['source_provenance']={'status':'pending','full_evidence':None}
            else:
                proof,reference=checked
                result[f'monthly-provenance/{key}.json']=reference
                item['source_provenance']={'status':proof['status'],'eligible_months':proof['eligible_months'],
                    'eligible_utc_days_checked':proof['eligible_utc_days_checked'],
                    'monthly_input_sha256':proof['monthly_input_sha256'],'full_evidence':f'monthly-provenance/{key}.json'}
        result[name]=summary
    for case in CASES:
        entry=index.get('footprints',{}).get(case)
        if entry is None:
            result[f'footprint-summary/{case}.json']={'schema':'fireatlas-footprint-support-summary-v2','case_id':case,
                'state':'not-acquired','cohorts':[],'validated_observation_opportunity':False,'no_pass_enabled':False,
                'full_evidence':None,'reason':'No recounted footprint campaign registered for this pilot. Existing native sampled-state evidence remains separate.'}
            continue
        if not isinstance(entry,list) or not 1<=len(entry)<=256:raise ValueError('Bounded list of disjoint footprint campaign parts required.')
        parts=[]
        def checked_campaigns():
            seen=set()
            for item in entry:
                campaign,reference=_entry(work,item,'opportunity-v2')
                identity=campaign['result_sha256']
                if identity in seen:raise ValueError('Duplicate footprint campaign part.')
                seen.add(identity)
                opportunity_review.verify_campaign(campaign,original_directory=original_directory if campaign.get('original_file_bindings') else None)
                # Original samples must reproduce even before independent approval.
                if not campaign.get('original_file_bindings'):
                    for frame in campaign['frames']:
                        if frame['inputs']['pixels']:
                            if original_directory is None:raise ValueError('Original directory required for authentic boundary publication.')
                            frames.bind_original_files(frame,original_directory)
                name=f'footprint-part/{identity}.json.gz'
                result[name]=reference
                parts.append({'artifact':name,'result_sha256':identity,'cohorts':sorted({json.dumps(f['cohort'],sort_keys=True) for f in campaign['frames']}),
                              'start':min(f['start'] for f in campaign['frames']),'end':max(f['end'] for f in campaign['frames'])})
                parts[-1]['cohorts']=[json.loads(c) for c in parts[-1]['cohorts']]
                yield campaign
        summary=footprint_summary(checked_campaigns(),case);summary['parts']=parts
        result[f'footprint-summary/{case}.json']=summary
        result[f'footprint-campaign/{case}.json']={'schema':'fireatlas-footprint-campaign-index-v2','case_id':case,'parts':parts,
            'interpretation':'Disjoint source campaigns. Each part retains its original gzip bytes, method, inputs and review state.'}
    transfers=index.get('transfers',{});provenance=index.get('provenance',{});consumed=set();entries=defaultdict(list)
    for name,count in list(values.items()):
        if not name.startswith('cohort-transfer/'):continue
        key=name.rsplit('/',1)[1].removesuffix('.json');entry=transfers.get(key);evaluation=None;rebased=False
        if entry:
            evaluation,_reference=_entry(work,entry,'transfer-opportunity-v2');consumed.add(key)
            if evaluation['count_evidence_sha256']!=count['result_sha256']:
                if evaluation.get('protocol_review') or evaluation['opportunity_support']['dependencies']:
                    raise ValueError('Reviewed transfer dependencies differ from current count evidence; retain prior release.')
                evaluation=None;rebased=True  # Retain old private capture and its forms.
        if evaluation is None:evaluation=transfer_opportunity.build(count)
        else:transfer_opportunity.verify(evaluation,_packets(work,entry.get('packet_index')),original_directory=original_directory)
        if evaluation['region']!=count['region'] or evaluation['source_cohort']!=count['source_cohort'] or evaluation['target_cohort']!=count['target_cohort']:
            raise ValueError('Transfer successor scope differs from published count evidence.')
        conclusion=None
        if entry and entry.get('conclusions'):
            conclusion=load(indexed_path(work,entry['conclusions'],prefix='transfer-opportunity-v2'))
            if rebased:
                if conclusion.get('decision') not in (None,'pending') or conclusion.get('human_authored'):
                    raise ValueError('Stale transfer conclusion must be renewed for new count evidence.')
                conclusion=None
        gate=transfer_opportunity.admission(evaluation,conclusion,_packets(work,entry.get('packet_index')) if entry and evaluation['opportunity_support']['dependencies'] else (),original_directory=original_directory)
        proof=provenance_asset(work,provenance.get(key),count)
        if proof is not None:result[f'transfer-provenance/{key}.json']=proof
        packets=[]
        if evaluation['opportunity_support']['dependencies']:
            expected={d['packet_sha256'] for d in evaluation['opportunity_support']['dependencies']};copied=set()
            for packet,reference in _packets(work,entry.get('packet_index'),with_reference=True):
                identity=digest(packet)
                if identity not in expected or identity in copied:raise ValueError('Frozen transfer packet identity differs.')
                copied.add(identity);name=f'opportunity-packet/{identity}.json.gz'
                result[name]=reference;packets.append(name)
            if copied!=expected:raise ValueError('Frozen transfer opportunity packets incomplete.')
        full=f'transfer-opportunity/{key}.json'
        result[full]={'schema':'fireatlas-direct-transfer-opportunity-publication-v2','evaluation':evaluation,'conclusions':conclusion,'admission':gate,'packet_artifacts':packets}
        entries[count['region']].append({'id':key,'source_cohort':evaluation['source_cohort'],'target_cohort':evaluation['target_cohort'],
            'eligible_months':count['eligible_months'],'checks':gate['checks'],'admitted':gate['admitted'],
            'opportunity_required_dates':evaluation['opportunity_support']['required_dates_per_cohort'],
            'opportunity_represented_pairs':evaluation['opportunity_support']['represented_date_cohort_pairs'],
            'platform_acquisition_support':evaluation['opportunity_support']['platform_acquisition_support'],
            'result_sha256':evaluation['result_sha256'],'count_evidence_sha256':count['result_sha256'],
            'source_provenance':({'status':proof['status'],'input_sha256':proof['input_sha256'],'full_evidence':f'transfer-provenance/{key}.json'} if proof else {'status':'pending','input_sha256':count['input_sha256'],'full_evidence':None,'reason':'No matching receipt for the current source capture.'}),
            'full_evidence':full+'.gz','historical_extrapolation_admitted':False,'forecasting_admitted':False})
    if (set(transfers)|set(provenance))-{name.rsplit('/',1)[1].removesuffix('.json') for name in values if name.startswith('cohort-transfer/')}:
        raise ValueError('Registered successor has no matching published count experiment.')
    registrations=index.get('daily_hybrid',{});diagnostic_registrations=index.get('daily_diagnostics',{});neighbor_registrations=index.get('daily_neighbors',{})
    if not isinstance(registrations,dict):raise ValueError('Daily hybrid registrations must be keyed by cohort.')
    if not isinstance(diagnostic_registrations,dict):raise ValueError('Daily diagnostic registrations must be keyed by cohort.')
    if not isinstance(neighbor_registrations,dict):raise ValueError('Daily similar-day registrations must be keyed by cohort.')
    known={name.rsplit('/',1)[1].removesuffix('.json') for name in values if name.startswith('cohort-daily/')}
    if (set(registrations)|set(diagnostic_registrations)|set(neighbor_registrations))-known:raise ValueError('Registered daily evidence has no matching published cohort.')
    for region in ('norcal','punjab-haryana'):
        key=f'daily-cohorts/{region}.json'
        if key not in values:continue
        summary=values[key]
        for item in summary['entries']:
            cohort_id=item['id'];original=values['cohort-daily/'+cohort_id+'.json']
            diagnostic=daily_diagnostics_asset(work,diagnostic_registrations.get(cohort_id),original,publication_root)
            if diagnostic is None:
                item['diagnostics']={'state':'pending'}
            else:
                report,reference=diagnostic;d=report['diagnostics'];name=f'daily-diagnostics/{cohort_id}.json'
                result[name]=reference
                item['diagnostics']={'state':'experimental','overall':d['overall'],'by_test_year':d['by_test_year'],
                    'by_season':d['by_season'],'by_modis_state':d['by_modis_state'],
                    'reproduction_artifact':name,'scientific_admission':False}
            neighbor=daily_neighbors_asset(work,neighbor_registrations.get(cohort_id),original,publication_root)
            if neighbor is None:
                item['neighbors']={'state':'pending'}
            else:
                bundle,reference=neighbor;e=bundle['experiment'];name=f'daily-neighbors/{cohort_id}.json.gz'
                result[name]=reference
                item['neighbors']={'state':'experimental','test_years':[f['test_year'] for f in e['folds']],
                    'test_dates':len(e['rows']),'metrics':e['metrics'],'zero_modis_positive_viirs':e['zero_modis_positive_viirs'],
                    'seasonal':e['seasonal'],'checks':e['checks'],'occurrence_calibration':e['occurrence_calibration'],
                    'occurrence_brier':e['occurrence_brier'],'source_release_id':bundle['original_release_id'],
                    'result_sha256':e['result_sha256'],'reproduction_artifact':name,'estimates_admitted':False}
            checked=daily_hybrid_asset(work,registrations.get(cohort_id),original,publication_root)
            if checked is None:
                item['hybrid']={'state':'pending','reason':'No exact-input hybrid experiment is available for this cohort.'}
                continue
            bundle,reference=checked;e=bundle['experiment'];name=f'daily-hybrid/{cohort_id}.json.gz'
            result[name]=reference
            item['hybrid']={'state':'experimental','test_years':[f['test_year'] for f in e['folds']],
                'test_dates':len(e['rows']),'metrics':e['metrics'],'zero_modis_positive_viirs':e['zero_modis_positive_viirs'],
                'seasonal':e['seasonal'],'checks':e['checks'],'source_release_id':bundle['original_release_id'],
                'result_sha256':e['result_sha256'],'reproduction_artifact':name,'estimates_admitted':False}
        result[key]=summary
    for region in ('norcal','punjab-haryana'):
        result[f'transfer-opportunity-summary/{region}.json']={'schema':'fireatlas-transfer-opportunity-index-v2','region':region,
            'entries':entries[region],'historical_extrapolation_admitted':False,
            'interpretation':'Exact count, regional opportunity and independent review gates. Admitted overlap does not qualify historical deployment or forecasting.'}
    return result
