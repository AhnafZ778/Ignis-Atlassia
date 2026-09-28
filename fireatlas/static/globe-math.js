/* Matches earth.html's ray/sphere renderer: +Y north, +Z Greenwich, +X east. */
((root) => {
  const vector = (lon, lat) => {
    const a = lon * Math.PI / 180, b = lat * Math.PI / 180;
    return [Math.cos(b) * Math.sin(a), Math.sin(b), Math.cos(b) * Math.cos(a)];
  };
  function project(point, view) {
    if (typeof view.project === "function") return view.project(point);
    const r = view.rotation;
    const x = r[0]*point[0] + r[1]*point[1] + r[2]*point[2];
    const y = r[3]*point[0] + r[4]*point[1] + r[5]*point[2];
    const z = r[6]*point[0] + r[7]*point[1] + r[8]*point[2];
    // Surface normals beyond the perspective horizon are occluded by Earth.
    if (z * view.distance <= 1.001) return null;
    const scale = Math.min(view.width, view.height) / 2;
    return {x:view.width/2 + (2.4*x/(view.distance-z)+view.framing)*scale,
            y:view.height/2 - (2.4*y/(view.distance-z)+view.vertical)*scale};
  }
  const api = {vector, project};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FireGlobeMath = api;
})(globalThis);
