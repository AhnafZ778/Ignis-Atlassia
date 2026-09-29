// Shared navigation behavior; data tools retain their own state and controls.
document.addEventListener("DOMContentLoaded", () => {
  if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/app-sw.js", {scope:"/",updateViaCache:"none"}).catch(() => {});
  }
  const toggle = document.querySelector(".nav-toggle");
  const navigation = document.querySelector("#site-navigation");
  if (toggle && navigation) {
    const close = () => { toggle.setAttribute("aria-expanded", "false"); navigation.classList.remove("is-open"); };
    toggle.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open)); navigation.classList.toggle("is-open", open);
    });
    navigation.addEventListener("click", event => { if (event.target.closest("a")) close(); });
    document.addEventListener("keydown", event => { if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") { close(); toggle.focus(); } });
    document.addEventListener("click", event => { if (!event.target.closest(".topbar")) close(); });
    matchMedia("(min-width: 761px)").addEventListener("change", close);
  }
  const links = [...document.querySelectorAll('.workspace-nav a[href^="#"]')];
  if (links.length && "IntersectionObserver" in window) {
    const visible = new Set();
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) { if (entry.isIntersecting) visible.add(entry.target.id); else visible.delete(entry.target.id); }
      const active = links.find(link => visible.has(link.hash.slice(1)));
      if (active) for (const link of links) {
        link.classList.toggle("current", link === active);
        if (link === active) link.setAttribute("aria-current", "location"); else link.removeAttribute("aria-current");
      }
    }, {rootMargin: "-110px 0px -45% 0px", threshold: 0});
    for (const link of links) { const section = document.querySelector(link.hash); if (section) observer.observe(section); }
  }
});
