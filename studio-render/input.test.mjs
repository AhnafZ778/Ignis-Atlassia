import test from 'node:test';
import assert from 'node:assert/strict';
import { checkInput } from './input.mjs';
import { cameraMatrix, cameraSvg } from './camera.mjs';
test('camera crops only frozen map geometry and keeps headings and units stationary', () => {
  const visual = { scope: { bbox: [0, 0, 10, 10] }, camera_transition: { from_bbox: [0, 0, 10, 10], to_bbox: [0, 0, 5, 5] } };
  assert.deepEqual(cameraMatrix(visual, 0), [1, 0, 0, 1, 0, 0]);
  assert.deepEqual(cameraMatrix(visual, 1), [2, 0, 0, 2, -90, -435]);
  const svg = '<svg><text>UTC and cell-days</text><g data-map-camera="true" transform="matrix(1 0 0 1 0 0)"><circle/></g><text>Legend</text></svg>';
  assert.equal(cameraSvg(svg, visual, 1), svg.replace('matrix(1 0 0 1 0 0)', 'matrix(2 0 0 2 -90 -435)'));
  assert.equal(cameraSvg(svg, {}, 1), svg);
});
const input = () => ({ resolved: { schema: 'fireatlas-resolved-story-v1', profile: { width: 1920, height: 1080, fps: 30, duration_seconds: 2 }, scenes: [{ chapter_id: 'a', start_seconds: 0, duration_seconds: 2, visual_svg: '<svg xmlns="http://www.w3.org/2000/svg"><text>Frozen result</text></svg>', caption: 'Caption', narration_text: 'Narration' }] }, audio: [] });
test('one frozen scene is accepted without altering its timing or text', () => { const value = input(); assert.equal(checkInput(value), value); });
test('render inputs reject remote resources and executable markup', () => {
  for (const svg of ['<svg><image href="http://localhost/private"/></svg>', '<svg><image href=http://localhost/private /></svg>', '<svg><rect fill="url(http://localhost/private)" /></svg>', '<svg onload="alert(1)"></svg>', '<svg><script>bad()</script></svg>']) { const value = input(); value.resolved.scenes[0].visual_svg = svg; assert.throws(() => checkInput(value), /prepared/); }
});
test('oversized or changed timing and traversal audio are rejected', () => {
  const value = input(); value.resolved.scenes[0].start_seconds = 20; assert.throws(() => checkInput(value), /timing/);
  const bad = input(); bad.audio = [{ chapter_id: 'a', file: '../../secret.mp3' }]; assert.throws(() => checkInput(bad), /narration/);
});

test('prepared camera transitions are bounded numeric scene metadata', () => {
  const valid = input();
  valid.resolved.scenes[0].visual = { camera_transition: { from_bbox: [-1, -1, 1, 1], to_bbox: [-.5, -.5, .5, .5] } };
  assert.doesNotThrow(() => checkInput(valid));
  const invalid = input();
  invalid.resolved.scenes[0].visual = { camera_transition: { from_bbox: ['bad', -1, 1, 1], to_bbox: [-.5, -.5, .5, .5] } };
  assert.throws(() => checkInput(invalid), /camera transition/);
});
