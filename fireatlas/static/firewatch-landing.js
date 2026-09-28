/* Decorative FireWatch motion. Observations remain driven by the existing APIs. */
document.addEventListener("DOMContentLoaded", () => {
  const canvas = document.getElementById("hero-embers");
  const hero = document.querySelector(".globe-hero");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  if (canvas && hero && !reduced.matches) {
    const ctx = canvas.getContext("2d");
    const particles = Array.from({length: 34}, (_, index) => ({
      x: Math.random(), y: .68 + Math.random() * .34, size: 1 + Math.random() * 2.8,
      speed: .00018 + Math.random() * .00042, drift: (Math.random() - .5) * .00016,
      phase: index * .73, alpha: .25 + Math.random() * .55
    }));
    let frame;
    const draw = time => {
      const rect = hero.getBoundingClientRect();
      const dpr = Math.min(devicePixelRatio || 1, 2);
      const width = Math.max(1, rect.width), height = Math.max(1, rect.height);
      if (canvas.width !== width * dpr || canvas.height !== height * dpr) { canvas.width = width * dpr; canvas.height = height * dpr; }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, width, height);
      // A restrained ember ribbon anchors the scene without becoming a fire perimeter.
      const ribbon = ctx.createLinearGradient(0, height * .9, 0, height);
      ribbon.addColorStop(0, "rgba(255,100,26,0)"); ribbon.addColorStop(.7, "rgba(255,100,26,.12)"); ribbon.addColorStop(1, "rgba(255,100,26,.02)");
      ctx.beginPath(); ctx.moveTo(0, height); ctx.lineTo(0, height * .94);
      for (let x = 0; x <= width; x += width / 8) ctx.quadraticCurveTo(x + width / 16, height * (.89 + Math.sin(time * .001 + x) * .015), x + width / 8, height * .94);
      ctx.lineTo(width, height); ctx.closePath(); ctx.fillStyle = ribbon; ctx.fill();
      for (const particle of particles) {
        particle.y -= particle.speed * 16; particle.x += particle.drift * 16;
        if (particle.y < .1) { particle.y = 1.03; particle.x = Math.random(); }
        const flicker = .7 + Math.sin(time * .004 + particle.phase) * .3;
        ctx.beginPath(); ctx.fillStyle = `rgba(255,${88 + Math.round(particle.size * 26)},${24 + Math.round(particle.size * 18)},${particle.alpha * flicker})`;
        ctx.shadowBlur = 12; ctx.shadowColor = "#ff641a"; ctx.arc(particle.x * width, particle.y * height, particle.size, 0, Math.PI * 2); ctx.fill();
      }
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    reduced.addEventListener?.("change", () => { if (reduced.matches) cancelAnimationFrame(frame); });
  }
  document.querySelectorAll(".hero-hotspot").forEach(button => button.addEventListener("click", () => {
    const toggle = document.getElementById("globe-markers");
    if (toggle && !toggle.checked) toggle.click();
    document.querySelector(".globe-console")?.scrollIntoView({behavior: "smooth", block: "center"});
    const status = document.getElementById("globe-status");
    if (status) status.textContent = `Observation group ${button.dataset.hotspot} selected · inspect the source snapshot below.`;
  }));
  const replay = document.getElementById("fusion-replay");
  replay?.addEventListener("click", () => {
    const stage = replay.closest(".fusion-step"); stage?.classList.remove("is-replaying"); void stage?.offsetWidth; stage?.classList.add("is-replaying");
    replay.blur();
  });
});
