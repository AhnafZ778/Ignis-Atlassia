import { test } from 'node:test';
import assert from 'node:assert/strict';
import { filmFrame } from './film-frame.mjs';
test('prepared figure fits without covering captions and retains source marks', () => {
  const svg = filmFrame({title:'A <checked> comparison',caption:'Retain the measured unit & UTC date.',visual_svg:'<svg viewBox="0 0 960 540"><text>MODIS / cell-days</text></svg>'},0,4);
  assert.match(svg,/height="712" viewBox="0 0 960 540" preserveAspectRatio="xMidYMid meet"/);
  assert.match(svg,/MODIS \/ cell-days/);
  assert.match(svg,/A &lt;checked&gt; comparison/);
  assert.match(svg,/measured unit &amp; UTC date/);
  assert.match(svg,/1 \/ 4/);
});
