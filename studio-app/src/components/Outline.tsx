import { useStudio } from '../store';
import { propagateSummary } from '../lib/outline';

/** Linear alternative to the board: the same cards, in order, reachable without a pointer. */
export function Outline() {
  const { doc, selected, select } = useStudio();
  const state = doc!.state;
  const items = state.order.map((id) => state.cards[id]).filter(Boolean);
  if (!items.length) return <div className="panel empty-state"><h2>No cards yet</h2><p>Add a card from the library to start the outline.</p></div>;
  return (
    <ol className="outline" aria-label="Cards in board order">
      {items.map((card, index) => {
        const snapshot = card.snapshot_id ? doc!.snapshots?.[card.snapshot_id] : null;
        const links = propagateSummary(state, card.id);
        return (
          <li key={card.id} aria-current={selected === card.id}>
            <div>
              <strong>{index + 1}. {card.title || 'Untitled'}</strong> <span className="chip off">{card.type.replace('-', ' ')}</span>{' '}
              {snapshot ? <span className="chip ok">frozen · {snapshot.unit}</span> : card.binding ? <span className="chip warn">not frozen</span> : null}
              {links ? <div className="muted">{links}</div> : null}
              {card.text ? <div className="muted">{card.text.slice(0, 140)}{card.text.length > 140 ? '…' : ''}</div> : null}
            </div>
            <button type="button" className="btn small" onClick={() => select(card.id)} aria-label={`Inspect ${card.title || card.type}`}>Inspect</button>
          </li>
        );
      })}
    </ol>
  );
}
