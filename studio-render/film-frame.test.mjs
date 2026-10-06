import { test } from 'node:test';
import assert from 'node:assert/strict';
import { filmFrame, filmMotion } from './film-frame.mjs';
test('prepared figure fits without covering captions and retains source marks', () => {
  const svg = filmFrame({title:'A <checked> comparison',caption:'Retain the measured unit & UTC date.',visual_svg:'<svg viewBox="0 0 960 540"><text>MODIS / cell-days</text></svg>'},0,4);
  assert.match(svg,/height="676" viewBox="0 0 960 540" preserveAspectRatio="xMidYMid meet"/);
  assert.match(svg,/MODIS \/ cell-days/);
  assert.match(svg,/A &lt;checked&gt; comparison/);
  assert.match(svg,/measured unit &amp; UTC/);
  assert.match(svg,/01 \/ 04/);
});
test('entrances are smooth at adjacent frames and preserve the frozen figure without scale changes', () => {
  const a = filmMotion(.3, 16), b = filmMotion(.3 + 1/30, 16);
  assert.ok(b.opacity > a.opacity && b.opacity - a.opacity < .06);
  assert.ok(b.y < a.y && a.y - b.y < 2);
  assert.deepEqual(filmMotion(4, 16), { opacity: 1, y: 0 });
  assert.ok(filmMotion(15.9, 16).opacity < .4);
});
test('film removes duplicate title and UI badge while preserving units, scope and measured marks', () => {
  const svg = filmFrame({ title: 'Reading the record', caption: 'A dated comparison.', duration_seconds: 16,
    visual_svg: '<svg><text x="32" y="42">Reading the record</text><rect x="650" y="22" width="134" height="24"/><text x="657" y="38">map: UI badge</text><text>175 occupied cells · UTC 2019-09-08</text></svg>' }, 0, 4);
  assert.equal(svg.split('Reading the record').length, 2);
  assert.ok(!svg.includes('UI badge'));
  assert.match(svg, /175 occupied cells · UTC 2019-09-08/);
  assert.ok(!svg.includes('scale('));
});
