// Reuse the user's self-contained earth.html scene without changing its renderer or textures.
// The landing scene fills the hero on desktop and mobile.
document.addEventListener("DOMContentLoaded", () => {
  const host = document.getElementById("earth-frame-host");
  const hero = document.querySelector(".earth-hero");
  const caption = document.getElementById("earth-caption");
  if (!host || !hero) return;

  const frame = document.createElement("iframe");
  frame.src = "/earth.html?embed=landing";
  frame.title = "Interactive 3D Earth model. Drag to rotate; open the full Earth for all controls.";
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

    const started = performance.now();
    const timer = setInterval(() => {
      const loader = documentInFrame.getElementById("loading");
      if (loader && loader.hidden) {
        clearInterval(timer);
        host.classList.add("ready");
        hero.classList.add("model-ready");
        caption.textContent = "DRAG TO ROTATE";
        window.dispatchEvent(new CustomEvent("earth-ready", {detail:{frame}}));
      } else if (performance.now() - started > 20000 || loader?.classList.contains("error")) {
        clearInterval(timer);
        frame.remove();
        caption.textContent = "EARTH PREVIEW · OPEN FULL MODEL ↗";
        window.dispatchEvent(new CustomEvent("earth-unavailable"));
      }
    }, 250);
  });
});
