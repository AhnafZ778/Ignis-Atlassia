/** Shared map-only crop for browser and both video adapters. No measurement interpolation. */
export function cameraMatrix(visual, progress = 0) {
  const camera = visual?.camera_transition;
  if (!camera) return [1, 0, 0, 1, 0, 0];
  const [w, s, e, n] = visual.scope.bbox;
  const t = Math.max(0, Math.min(1, progress));
  const [a, b, c, d] = camera.from_bbox.map((first, i) => first + (camera.to_bbox[i] - first) * t);
  const sx = (e - w) / (c - a), sy = (n - s) / (d - b);
  return [sx, 0, 0, sy, 90 * (1 - sx) + 770 * (w - a) / (c - a), 105 * (1 - sy) + 330 * (d - n) / (d - b)];
}
export function cameraSvg(svg, visual, progress = 0) {
  if (!visual?.camera_transition) return svg;
  const matrix = cameraMatrix(visual, progress).join(' ');
  return svg.replace(/data-map-camera="true" transform="[^"]*"/, `data-map-camera="true" transform="matrix(${matrix})"`);
}
