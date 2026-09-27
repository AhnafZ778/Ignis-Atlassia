(() => {
  "use strict";
  const status = () => document.getElementById("offline-pack-status");
  async function prepare() {
    if (!("serviceWorker" in navigator) || !window.isSecureContext) {
      status().textContent = "Offline reload needs a supported browser on localhost or HTTPS.";
      return;
    }
    try {
      const registration = await navigator.serviceWorker.register("/training-sw.js", {scope:"/training.html", updateViaCache:"none"});
      const ready = await Promise.race([navigator.serviceWorker.ready,
        new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), 15000))]);
      if (!ready.active) throw new Error("not active");
      status().textContent = "Offline page ready · this tab can reload without a connection.";
      status().dataset.ready = "true";
      if (registration.waiting) status().textContent += " An update will apply after all Training Lab tabs close.";
    } catch {
      // An already-installed pack remains useful when checking for an update fails offline.
      const registration = await navigator.serviceWorker.getRegistration("/training.html").catch(() => null);
      if (registration?.active && navigator.serviceWorker.controller) {
        status().textContent = "Using the installed offline page. Reconnect to check for updates.";
        status().dataset.ready = "true";
      } else status().textContent = "Offline page unavailable. Keep this tab open and reconnect to prepare it.";
    }
  }
  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("prepare-offline").addEventListener("click", prepare);
    prepare();
  });
})();
