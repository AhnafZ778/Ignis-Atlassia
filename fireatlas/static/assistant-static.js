/* Read-only static capability adapter. No owner sessions or provider probes. */
(() => {
  "use strict";
  const reason = "Local assistant service required. Frozen maps, comparisons and downloads remain available; private analysis and authoring require the Python service.";
  const unavailable = async () => { throw Error(reason); };
  function notice(message = reason) {
    for (const id of ["assistant-service-note", "assistant-turn-status", "assistant-ai-state"]) {
      const node = document.getElementById(id);
      if (node) { node.hidden = false; node.textContent = message; }
    }
  }
  window.FireAtlasAssistant = {
    isReady: () => false, isBusy: () => false, stop: async () => {},
    context: () => window.FireAtlasContext?.toAssistantContext() || {},
    request: unavailable, showEvidence: unavailable, navigate: unavailable,
    investigate: async () => notice(), refreshNotebook: unavailable, notify: notice
  };
  document.addEventListener("DOMContentLoaded", async () => {
    if (window.FireAtlasStudyReady) await window.FireAtlasStudyReady;
    notice();
    for (const id of ["assistant-question-form", "assistant-note-form"]) {
      const form = document.getElementById(id);
      if (form) {
        form.addEventListener("submit", e => { e.preventDefault(); notice(); });
        form.querySelectorAll("button,input,textarea,select").forEach(el => { el.disabled = true; });
      }
    }
    document.querySelectorAll("[data-investigation],#workspace-open-jarvis,#assistant-capture,#assistant-mic,#assistant-pin,#assistant-control,#assistant-clear,#assistant-mask,#mission-search-archive,#mission-refine").forEach(el => {
      el.disabled = true; el.title = reason;
    });
    document.querySelectorAll(".assistant-export a").forEach(a => { a.removeAttribute("href"); a.setAttribute("aria-disabled", "true"); a.title = reason; });
    window.dispatchEvent(new CustomEvent("fireatlas:assistant-unavailable", {detail: {message: reason, static: true}}));
  });
})();
