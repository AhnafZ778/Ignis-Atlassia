import type {PublicReadingReport} from '../types';
export function PublicReadingPanel({reports}:{reports:PublicReadingReport[]}) {
 return <section className="research-brief" aria-label="Original source reading">
  <span className="assistant-eyebrow">INSIDE THE SOURCE</span><h3>Read what the paper says.</h3>
  {reports.map((report,index)=><details key={`${report.source_id}-${index}`}>
   <summary>{report.source_id} · {report.status==='article_passages'?'Article passages':report.status==='abstract'?'Abstract only':'Text unavailable'} · {report.title}</summary>
   <p className="research-brief-scope">{report.reason} {report.license ? `Reported license: ${report.license}.` : ''}</p>
   {report.passages.map(passage=><div className="research-source-passage" key={passage.id}><h4>{passage.section}</h4><blockquote>{passage.text}</blockquote><small>{passage.location}{passage.truncated?' · excerpt shortened':''}</small></div>)}
   <p className="research-brief-scope">{report.scope}</p>
   {report.url.startsWith('https://') && <a href={report.url} target="_blank" rel="noopener noreferrer">Open original publication ↗</a>}
  </details>)}
 </section>;
}
