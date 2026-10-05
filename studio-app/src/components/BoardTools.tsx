import { useState } from 'react';
import { useStudio } from '../store';

/** Domain groups are independent of the active canvas SDK and never change evidence. */
export function BoardTools() {
  const { doc, transact, canEdit, select, canvasCards } = useStudio();
  const [checked, setChecked] = useState<string[]>([]);
  const [title, setTitle] = useState('Evidence group');
  const [query, setQuery] = useState('');
  if (!doc) return null;
  const cards = checked.map((id) => canvasCards[id]).filter(Boolean);
  const free = cards.every((card) => !Object.values(doc.state.groups || {}).some((g) => g.card_ids.includes(card.id)));
  const edit = async (ops: Record<string, unknown>[]) => { const result = await transact(ops); if (result) setChecked([]); };
  return <details className="panel board-tools"><summary>Arrange, group and find cards</summary>
    <label className="field">Find cards<input type="search" value={query} onChange={(e) => setQuery(e.target.value)} /></label>
    <div className="group-card-list" aria-label="Cards to arrange">{doc.state.order.map((id) => canvasCards[id]).filter((c) => c.title.toLowerCase().includes(query.toLowerCase())).map((card) => <label key={card.id}>
      <input type="checkbox" disabled={!canEdit || card.locked} checked={checked.includes(card.id)} onChange={(e) => setChecked((ids) => e.target.checked ? [...ids, card.id] : ids.filter((id) => id !== card.id))} />
      <button className="link-button" type="button" onClick={() => select(card.id)}>{card.title || card.type}</button>
    </label>)}</div>
    <div className="row"><label className="field">Group title<input value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} /></label>
      <button className="btn" disabled={!canEdit || cards.length < 2 || !free || !title.trim()} onClick={() => void edit([{ op: 'set_group', group: { id: `g_${crypto.randomUUID().replaceAll('-', '')}`, title: title.trim(), card_ids: cards.map((c) => c.id) } }])}>Group checked cards</button>
      <button className="btn" disabled={!canEdit || cards.length < 2 || cards.length > 50} onClick={() => { const left = Math.min(...cards.map((c) => c.transform.x)); void edit(cards.map((card) => ({ op: 'move_card', id: card.id, layout_origin: card.transform, transform: { ...card.transform, x: left } }))); }}>Align left</button>
      <button className="btn" disabled={!canEdit || cards.length < 2 || cards.length > 50} onClick={() => { const top = Math.min(...cards.map((c) => c.transform.y)); let x = Math.min(...cards.map((c) => c.transform.x)); void edit(cards.map((card) => { const transform = { ...card.transform, x, y: top }; x += card.transform.w + 24; return { op: 'move_card', id: card.id, transform, layout_origin: card.transform }; })); }}>Arrange in a row</button>
    </div>
    {Object.values(doc.state.groups || {}).map((group) => <div className="row group-controls" key={group.id}><strong>{group.title}</strong><span>{group.card_ids.length} cards</span>
      <button className="btn small" disabled={!canEdit} onClick={() => void transact([{ op: 'move_group', id: group.id, dx: 32, dy: 0 }])}>Move group right</button>
      <button className="btn small" disabled={!canEdit} onClick={() => void transact([{ op: 'move_group', id: group.id, dx: 0, dy: 32 }])}>Move group down</button>
      <button className="btn small" disabled={!canEdit} onClick={() => void transact([{ op: 'remove_group', id: group.id }])}>Ungroup</button>
    </div>)}
    <p className="muted">Groups organize presentation. They do not imply a scientific relationship. Locked cards cannot move.</p>
  </details>;
}
