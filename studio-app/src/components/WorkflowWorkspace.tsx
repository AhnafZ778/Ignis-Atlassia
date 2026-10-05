import { lazy, Suspense, useMemo, useState, type ComponentType } from 'react';
import { useStudio } from '../store';
import { WorkflowBoundary } from './WorkflowBoundary';

const loadWorkflow = () => import('./WorkflowPanel').then((module) => ({ default: module.WorkflowPanel }));
type WorkflowLoader = () => Promise<{ default: ComponentType }>;

export function workflowRefreshURL(href: string, boardId: string): string {
  const url = new URL(href);
  url.searchParams.set('board', boardId);
  url.searchParams.set('tab', 'workflow');
  return url.href;
}

export function WorkflowWorkspace({ onReturnToBoard, load = loadWorkflow }: {
  onReturnToBoard: () => void;
  load?: WorkflowLoader;
}) {
  const { doc } = useStudio();
  const [attempt, setAttempt] = useState(0);
  // React.lazy remembers a rejected promise. Retrying needs a fresh loader,
  // rather than remounting the same permanently rejected lazy component.
  const Panel = useMemo(() => lazy(load), [load, attempt]);
  return <WorkflowBoundary key={attempt} fallback={() => <section className="panel" aria-label="Workflow recovery">
    <h2>Workflow could not open</h2>
    <p role="alert">The workflow editor could not load or initialize. Your saved board and workflow have not been changed.</p>
    <p>A connection interruption or an updated Studio build can prevent this editor from loading. Retry, or refresh Studio to load the current version. Saved drafts are retained in this browser.</p>
    <div className="row">
      <button className="btn primary" onClick={() => setAttempt((value) => value + 1)}>Retry Workflow</button>
      <a className="btn" href={doc ? workflowRefreshURL(location.href, doc.id) : location.href}>Refresh Studio and open Workflow</a>
      <button className="btn" onClick={onReturnToBoard}>Return to Board</button>
    </div>
  </section>}>
    <Suspense fallback={<p role="status">Opening Workflow Composer…</p>}><Panel key={doc?.id} /></Suspense>
  </WorkflowBoundary>;
}
