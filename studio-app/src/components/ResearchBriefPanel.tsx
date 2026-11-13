import type {PublicResearchSource,ResearchAnswer,PublicReadingReport} from '../types';

export function ResearchBriefPanel({brief,sources,readings}:{brief:ResearchAnswer;sources:PublicResearchSource[];readings?:PublicReadingReport[]}) {
  const citations=sources.filter(source=>source.id && brief.source_ids.includes(source.id) && source.url.startsWith('https://'));
  return <section className="research-brief" aria-label="Public research brief">
    <div className="research-brief-title"><span className="assistant-eyebrow">FROM REFERENCES TO A TEST</span><h3>A question worth investigating.</h3></div>
    <div className="research-brief-step"><span aria-hidden="true">01</span><div><h4>Research context</h4><p>{brief.synthesis}</p></div></div>
    <div className="research-brief-step"><span aria-hidden="true">02</span><div><h4>Working hypothesis</h4><p>{brief.hypothesis}</p></div></div>
    <div className="research-brief-step"><span aria-hidden="true">03</span><div><h4>Proposed test</h4><p>{brief.proposed_test}</p></div></div>
    <p className="research-brief-scope">{readings?.some(report=>report.passages.length) ? 'AI research proposal based on selected original passages. This is not a full-paper review or independent scientific approval.' : 'AI research proposal based on search metadata. Review the original methods before adopting paper findings.'}</p>
    <div className="research-brief-citations" aria-label="References used">{citations.map(source=><a key={source.url} href={source.url} target="_blank" rel="noopener noreferrer">{source.id} · {source.title} ↗</a>)}</div>
  </section>;
}
