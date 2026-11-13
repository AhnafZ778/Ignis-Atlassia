/** Keep actual units visible; avoid repeating the generic CSV placeholder. */
export function formatClaim(claim:{label:string;value:unknown;unit?:string}):string {
  const unit=claim.unit && claim.unit !== 'reported value' ? ` ${claim.unit}` : '';
  return `${claim.label}: ${String(claim.value)}${unit}`;
}
