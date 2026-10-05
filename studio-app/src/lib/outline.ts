import type { DocState } from '../types';

/** Short text describing a card's links, for the linear outline. */
export function propagateSummary(state: DocState, id: string): string {
  const parts: string[] = [];
  for (const link of Object.values(state.connections)) {
    if (link.source === id) parts.push(`${link.kind} → ${state.cards[link.target]?.title || link.target}`);
    else if (link.target === id) parts.push(`${link.kind} ← ${state.cards[link.source]?.title || link.source}`);
  }
  return parts.join(' · ');
}
