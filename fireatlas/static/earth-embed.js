// Embed the FireAtlas satellite and elevation scene with its native projection bridge.
// The landing scene fills the hero on desktop and mobile.
document.addEventListener("DOMContentLoaded", () => {
  const host = document.getElementById("earth-frame-host");
  const hero = document.querySelector(".earth-hero");
  const caption = document.getElementById("earth-caption");
  if (!host || !hero) return;

  const frame = document.createElement("iframe");
  frame.src = "/terrain-earth.html?embed=landing";
  frame.title = "FireAtlas Terrain Earth with satellite imagery and World Elevation. Drag to rotate; use the globe controls to explore.";
  frame.loading = "eager";
  frame.allowFullscreen = true;
  host.append(frame);

  frame.addEventListener("load", () => {
    let documentInFrame;
    try { documentInFrame = frame.contentDocument; } catch { return; }
    if (!documentInFrame) return;

    // The full-page version retains its controls, credits, and loading interface.
    // The compact homepage version shows just the same WebGL model.
    const style = documentInFrame.createElement("style");
    style.textContent = ".topbar,.layers,.mode-label,.dock-wrap,.footer,.cinema-return,.toast,dialog{display:none!important}#earth{touch-action:pan-y}";
    documentInFrame.head.append(style);

    const unavailable = () => {
      host.classList.remove("ready");
      frame.remove();
      caption.textContent = "TERRAIN PREVIEW UNAVAILABLE · OPEN FULL EARTH ↗";
      window.dispatchEvent(new CustomEvent("earth-unavailable"));
    };
    frame.contentWindow.addEventListener("terrain-unavailable", unavailable, {once: true});
    const started = performance.now();
    const timer = setInterval(() => {
      const loader = documentInFrame.getElementById("loading");
      if (loader && loader.hidden) {
        clearInterval(timer);
        host.classList.add("ready");
        hero.classList.add("model-ready");
        caption.textContent = "DRAG TO ROTATE";
        window.dispatchEvent(new CustomEvent("earth-ready", {detail:{frame}}));
      } else if (performance.now() - started > 90000 || loader?.classList.contains("error")) {
        clearInterval(timer);
        unavailable();
      }
    }, 250);
  });
});
