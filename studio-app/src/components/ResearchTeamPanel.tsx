import type {ResearchTeamReport} from '../types';
export type {ResearchTeamReport} from '../types';

export function ResearchTeamPanel({report}:{report:ResearchTeamReport}) {
  return <section className="research-team-report" aria-label="Research team review">
    <div className="research-team-title"><div><span className="assistant-eyebrow">THREE PERSPECTIVES / ONE INVESTIGATION</span><h3>Put the idea to the test.</h3></div><span className="research-state">{report.status==='completed'?'Review ready':report.status==='partial'?'Partial review':'Unavailable'}</span></div>
    <div className="research-specialists">{report.specialists.map((specialist,index)=><article key={specialist.role} className="research-specialist">
      <div className="research-specialist-heading"><span aria-hidden="true">0{index+1}</span><strong>{specialist.label}</strong><small>{specialist.status==='completed'?'Ready':specialist.status==='cancelled'?'Stopped':'Withheld'}</small></div>
      {specialist.status==='completed'?<><p>{specialist.insight}</p><p className="research-next-test"><b>Next test</b>{specialist.next_test}</p>{specialist.sources?.filter(source=>source.url.startsWith('https://')).map(source=><a key={source.id} href={source.url} target="_blank" rel="noopener noreferrer">{source.id} · {source.title} ↗</a>)}</>:<p>{specialist.reason || 'This specialist did not finish.'}</p>}
    </article>)}</div>
    {report.note && <p className="research-team-note">{report.note}</p>}
    {report.ceiling_usd!==undefined && <p className="research-cost">Team allowance ${report.ceiling_usd.toFixed(2)} · {typeof report.estimated_cost_usd==='number'?`reported usage estimate $${report.estimated_cost_usd.toFixed(4)}`:'usage uncertain; reserved allowance retained'}</p>}
  </section>;
}
