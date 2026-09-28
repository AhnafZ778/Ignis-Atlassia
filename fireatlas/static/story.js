/* A five-stop, hands-on tour driven by the same controls as normal exploration. */
(() => {
  const $ = id => document.getElementById(id);
  const steps = [
    {topic:"01 / LOCATE",icon:"◎",title:"Start with a place.",
      description:"The outline is your area of interest. Zoom and move the map to explore imported locations, then use its view as an area. This stop uses generated examples.",
      target:"atlas-section",focus:".atlas-panel",apply: async () => {
        await loadCalendar({year:2015,month:6,series:"joint",bbox:"-122,39,-120,41",day:null}); drawAoi(true);
      }},
    {topic:"02 / DISCOVER",icon:"▥",title:"Find the active season.",
      description:"The July column contains four detected cell-days in this sample. Gray months have no complete export; they are unknown rather than zero-burning months.",
      target:"calendar-section",focus:".content-grid",apply: async () => {
        await loadCalendar({year:2015,month:6,series:"joint",day:null});
      }},
    {topic:"03 / COMPARE",icon:"◇",title:"Change the sensor.",
      description:"VIIRS contributes three original pixels on July 1 in this sample. The shared grid still counts one cell-day. Use the MODIS and Joint buttons to compare the source views yourself.",
      target:"calendar-section",focus:".source-compare",apply: async () => {
        await loadCalendar({year:2015,month:6,series:"viirs-snpp",day:"2015-07-01"});
      }},
    {topic:"04 / VERIFY",icon:"⌁",title:"Open the raw evidence.",
      description:"The joint view shows all four original pixels behind July 1. Expand a record to inspect the source fields and acquisition time.",
      target:"evidence-section",focus:".evidence-grid",apply: async () => {
        await loadCalendar({year:2015,month:6,series:"joint",day:"2015-07-01"});
        $("records").querySelector("details")?.setAttribute("open", "");
      }},
    {topic:"05 / EXPLORE",icon:"✦",title:"Take the next step.",
      description:"The Training Lab turns these ideas into a clearly simulated crew exercise. The Research Lab lets you inspect overlap and question the method.",
      target:"open-research-study",focus:".workspace-links",apply: async () => {}},
  ];
  let current = -1, focus = null, opening = null, sequence = 0;
  const motion = () => matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth";
  function close() {
    sequence++; current = -1;
    $("story-dock").hidden = true;
    focus?.classList.remove("tour-focus"); focus = null;
    opening?.focus(); opening = null;
  }
  async function show(index) {
    const workspace = $("study-workspace");
    if (workspace?.tagName === "DETAILS") workspace.open = true;
    const turn = ++sequence, step = steps[index];
    if (!step) return;
    $("story-next").disabled = $("story-back").disabled = true;
    try {
      if (!state.demo || !state.data) await selectDataset(true);
      if (turn !== sequence) return;
      await step.apply();
      if (turn !== sequence) return;
      current = index;
      focus?.classList.remove("tour-focus");
      focus = document.querySelector(step.focus);
      focus?.classList.add("tour-focus");
      $("story-dock").hidden = false;
      $("story-progress").textContent = `${String(index+1).padStart(2,"0")} / 05`;
      $("story-icon").textContent = step.icon;
      $("story-topic").textContent = step.topic;
      $("story-title").textContent = step.title;
      $("story-description").textContent = step.description;
      $("story-progress-fill").style.width = `${(index+1)*20}%`;
      $("story-back").disabled = index === 0;
      $("story-next").disabled = false;
      $("story-next").innerHTML = index === steps.length - 1 ? "Open Training Lab <span aria-hidden='true'>↗</span>" : "Next stop <span aria-hidden='true'>→</span>";
      const anchor = document.getElementById(step.target);
      anchor?.scrollIntoView({behavior:motion(),block:"start"});
      $("story-title").focus({preventScroll:true});
    } catch (error) {
      close(); toast(error.message || "The tour could not load this example.");
    }
  }
  document.addEventListener("DOMContentLoaded", () => {
    for (const id of ["start-tour","hero-start-tour"]) $(id)?.addEventListener("click", event => {
      opening = event.currentTarget; show(0);
    });
    $("story-close").addEventListener("click", close);
    $("story-back").addEventListener("click", () => show(current - 1));
    $("story-next").addEventListener("click", () => {
      if (current === steps.length - 1) location.href = "/training.html";
      else show(current + 1);
    });
    document.addEventListener("keydown", event => { if (event.key === "Escape" && current >= 0) close(); });
  });
})();
