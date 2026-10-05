import type { Scene } from '../types';

/** Read the already-resolved display values; never estimate pixels or recalculate counts. */
export function FrozenHeatTable({ views }: { views: Scene['visible_card_views'] }) {
  const heat = (views || []).filter((view) => view.visual?.kind === 'heat');
  if (!heat.length) return null;
  return <div className="card-table-scroll" data-heat-table role="region" aria-label="Frozen heat-image values" tabIndex={0}><table className="facts">
    <caption>Frozen heat-image values · recorded common cells, with collected-export state shown separately</caption>
    <thead><tr><th scope="col">Sensor</th><th scope="col">UTC date</th><th scope="col">Recorded common cells</th><th scope="col">Collected-export state</th><th scope="col">Concentration scale</th></tr></thead>
    <tbody>{heat.map((view) => {
      const image = view.visual!, source = String(image.source), products = image.products as Record<string, { state: string }>;
      const states = source === 'joint' ? Object.values(products || {}).map((p) => p.state).join(' / ') : products?.[source]?.state;
      const domain = image.domain as number[];
      return <tr key={view.id}><th scope="row">{source === 'MODIS_SP' ? '● MODIS' : source === 'VIIRS_SNPP_SP' ? '◆ S-NPP VIIRS' : '■ Combined detections'}</th><td>{String(image.day)}</td><td>{image.count == null ? 'unknown' : String(image.count)}</td><td>{states?.replaceAll('_', ' ') || 'unknown'}</td><td title={domain?.join('–')}>{domain ? `${domain[0]}–${domain[1].toFixed(2)}` : 'unknown'} · study-fixed</td></tr>;
    })}</tbody>
  </table><p className="muted">Heat shows smoothed recorded common-cell centers. Incomplete exports do not establish an observed zero or fire-free area.</p></div>;
}
