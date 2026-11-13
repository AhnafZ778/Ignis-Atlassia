"""Evidence-based readiness; software availability is never scientific acceptance."""
from __future__ import annotations
from collections import defaultdict
from .comparability import capture,complete_months
from .qualification import protocol,digest
from .regions import REGIONS

CRITERIA={
'G01':('Common target beyond shared grid','Monthly v2 implemented; new target qualification requires approved evaluation.'),
'G02':('Daily performance admission','Separate daily engine requires protocol approval, three supported holdouts and method review.'),
'G03':('MODIS-zero positive recovery','Authentic hurdle-count zero-recovery and baseline comparisons are available by exact cohort; all daily performance and independent-review gates must pass.'),
'G04':('Continuous historical record','Verified original standard history and backward-transfer report required; no assumed January 2000 start.'),
'G05':('Collection bridge','Exact collections remain separate; no independently approved direct collection bridge.'),
'G06':('Prediction uncertainty','Authentic chronological interval coverage, width and score are reported by exact cohort; numerical screening does not supply independent scientific approval.'),
'G07':('Observation opportunity','Native centroid samples lack qualified pixel footprint and quality geometry; no-pass disabled.'),
'G08':('Validity denominators','True native rematching and directional denominators implemented; independent native review pending.'),
'G09':('Pass inspection','Candidate timeline available; official orbit metadata retained where supplied; complete-pass qualification pending.'),
'G10':('Supported disagreement explanations','Time differences link granules; physical causes remain unresolved without evidence.'),
'G11':('Fixed-scope raw versus adjusted','Existing v1 same-scope retrospective comparison preserved; new v2 release pending scientific gates.'),
'G12':('Separate readiness states','Seven independent readiness states available; none inferred from software completion.'),
'G13':('Supported historical baseline','Only qualified comparable years may extend a baseline; historical transfer pending.'),
'G14':('Declared objective and tradeoffs','Frozen proposal defines target, candidates, partitions, intervals and project gates; human approval pending.'),
'G15':('Whole-period denominators','Strict UTC month eligibility and twelve-month annual calculations implemented and regression checked.'),
'G16':('Long-record generalization','Verified compatible long overlap and separately evaluated regions required.'),
'G17':('Forward-time evidence','Chronological engine isolates training/calibration/test; AI-reviewed exploratory support assessment available; qualified evaluation requires independent approval.'),
'G18':('Platform/day/night/opportunity effects','Platforms remain distinct; native solar/view-angle and raw-flag diagnostics are separate from validated full-cell observation opportunity.'),
'G19':('Modern VIIRS continuity','NOAA-20/21 standard ingestion identities available; direct platform mapping and scientific transfer review absent.'),
'G20':('Regional applicability','Fixed regions and exact cohorts enforced; no arbitrary-area scientific qualification.'),
'G21':('Independent scientific proof','Owner must recruit protocol/conclusion reviewer and independent native processing reviewer.'),
'G22':('Scientist task completion','Blank five-person task-study packet prepared; no participants or observed study results.'),
'G23':('AI disclosure','Repository credit and submission draft available; owner must verify actual external publication and films.'),
'G24':('Studio release integrity','Studio excluded from the core scientific demonstration; additional authoring/export/reader QA required if included.'),
'G25':('FRP meaning','Source-specific sampled MW retained; no daily energy or harmonized FRP claim.'),
'G26':('Export versus usable coverage','Separate export, native sampled state and opportunity contracts; validated opportunity remains unknown.'),
'G27':('Time/grid/confidence robustness','Time/grid/confidence and native solar/view-angle subsets are independently rematched; validated opportunity robustness and scientific review remain open.')}


def inventory(db):
    regions={}
    for region in REGIONS:
        inputs=capture(db,region);rows,excluded=complete_months(inputs)
        cohorts=defaultdict(list)
        for r in rows:cohorts[tuple(r['versions'])].append(r['date'])
        ledger=inputs['source_ledger']
        regions[region]={'name':REGIONS[region]['name'],'input_sha256':digest(inputs),
            'cohorts':[{'versions':list(k),'complete_months':len(v),'first':min(v),'last':max(v),'months':v} for k,v in sorted(cohorts.items())],
            'excluded_months':excluded,'verified_export_records':sum(bool(r['complete_export']) and r['coverage_basis']=='request-metadata' for r in ledger),
            'reconstructed_export_records':sum(r['coverage_basis']=='reconstructed-rows-only' for r in ledger),
            'latest_imported_standard_utc':inputs['latest_standard_utc'],
            'states':{k:{'passed':False,'reason':why} for k,why in {
                'data_complete':'Full compatible overlap campaign not yet qualified.',
                'model_fitted':'No supported v2 fit recorded; AI-reviewed exploratory execution is available separately.',
                'retrospective_performance_qualified':'Scientific qualification requires the selected exact-cohort performance and human reviews; acquired-cohort experiments and old v1 evidence remain separate.',
                'prediction_intervals_evaluated':'The primary recent cohort lacks supported test intervals; acquired exact cohorts report their own evaluated intervals and support.',
                'historical_transfer_qualified':'No reviewed direct collection/platform bridge.',
                'daily_reconstruction_qualified':'Separate daily protocol and method approval plus evidence required.',
                'independently_reviewed':'Signed independent protocol and conclusion reviews absent.'}.items()}}
    return {'schema':'fireatlas-readiness-v2','protocols':{kind:protocol(kind) for kind in ('monthly','daily')},'regions':regions,
        'criteria':[{'criterion_id':key,'title':title,'status':'blocked' if key in {'G02','G03','G04','G05','G06','G07','G13','G16','G17','G19','G21','G22','G23'} else 'partial',
                     'evidence_references':['docs/MENTOR_CRITERIA_STATUS.md','docs/qualification/REVIEWER_PACKET.md'],'reviewer':None,'unresolved_requirements':reason} for key,(title,reason) in CRITERIA.items()],
        'human_dependencies':['Owner recruits and verifies protocol/conclusion reviewer.','Independent native reviewer inspects at least thirty samples per case.','Five qualified task-study participants and owner publication evidence required.'],
        'claims':{'qualified_monthly_release':False,'daily_estimates':False,'historical_continuity':False,'forecasting':False},
        'interpretation':'Engineering tests and visible interfaces never automatically satisfy scientific acceptance. Original v1 results remain retrospective.'}
