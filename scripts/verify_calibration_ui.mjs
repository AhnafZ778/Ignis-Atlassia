#!/usr/bin/env node

// Verify the static Method page with the installed Chrome and Node runtime.
// No browser automation package or network install is needed.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {spawn} from "node:child_process";

const args = process.argv.slice(2);
function option(name, fallback) {
  const index = args.indexOf(name);
  return index < 0 ? fallback : args[index + 1];
}
const base = option("--base", "http://127.0.0.1:8000").replace(/\/$/, "");
const chromePath = option("--chrome", "/usr/bin/google-chrome");
const evidenceDir = path.resolve(option("--evidence", "docs/winning-plan/evidence"));
const regions = ["norcal", "punjab-haryana"];
const labels = {
  monthly_ratio: "Month-specific ratio",
  annual_ratio: "One annual ratio",
  no_harmonization: "No scaling · factor 1",
};
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const format = (value, digits = 3) => value === null || value === undefined
  ? "—" : Number(value).toLocaleString("en-US", {minimumFractionDigits: digits, maximumFractionDigits: digits});
const percent = (value) => value === null || value === undefined ? "—" : format(value * 100, 1) + "%";

async function main() {
  if (!fs.existsSync(chromePath)) throw new Error("Chrome not found: " + chromePath);
  fs.mkdirSync(evidenceDir, {recursive: true});
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "fireatlas-calibration-chrome-"));
  const chrome = spawn(chromePath, [
    "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
    "--disable-dev-shm-usage", "--remote-debugging-port=0", "--user-data-dir=" + profile,
    "--window-size=1440,1500", "about:blank",
  ], {stdio: "ignore"});
  let socket;
  let targetId;
  const exceptions = [];
  try {
    const portFile = path.join(profile, "DevToolsActivePort");
    const deadline = Date.now() + 20000;
    while (!fs.existsSync(portFile)) {
      if (chrome.exitCode !== null) throw new Error("Chrome exited before starting DevTools.");
      if (Date.now() > deadline) throw new Error("Timed out waiting for Chrome DevTools.");
      await sleep(100);
    }
    const port = fs.readFileSync(portFile, "utf8").split(/\r?\n/)[0];
    const endpoint = "http://127.0.0.1:" + port;
    const created = await fetch(endpoint + "/json/new?about:blank", {method: "PUT"});
    if (!created.ok) throw new Error("Could not create Chrome tab: HTTP " + created.status);
    const target = await created.json();
    targetId = target.id;
    socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      socket.addEventListener("open", resolve, {once: true});
      socket.addEventListener("error", reject, {once: true});
    });

    let nextId = 0;
    const pending = new Map();
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.method === "Runtime.exceptionThrown") {
        exceptions.push(message.params.exceptionDetails.text || "Browser exception");
      }
      if (!message.id) return;
      const entry = pending.get(message.id);
      if (!entry) return;
      pending.delete(message.id);
      if (message.error) entry.reject(new Error(message.error.message));
      else entry.resolve(message.result || {});
    });
    const send = (method, params = {}) => new Promise((resolve, reject) => {
      const id = ++nextId;
      pending.set(id, {resolve, reject});
      socket.send(JSON.stringify({id, method, params}));
    });
    const evaluate = async (expression) => {
      const result = await send("Runtime.evaluate", {
        expression, awaitPromise: true, returnByValue: true, userGesture: true,
      });
      if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
      return result.result?.value;
    };

    await send("Page.enable");
    await send("Runtime.enable");
    await send("Page.navigate", {url: base + "/method.html"});
    await waitFor(evaluate, "document.querySelector('#calibration-status')?.textContent.includes('matched complete months')");

    for (const region of regions) {
      await evaluate("(() => { const s=document.querySelector('#calibration-region'); s.value=" + JSON.stringify(region) + "; s.dispatchEvent(new Event('change')); })()");
      await waitFor(evaluate, "document.querySelector('#calibration-context')?.textContent.includes(" + JSON.stringify(region === "norcal" ? "Northern California" : "Punjab") + ") && document.querySelectorAll('#calibration-models .calibration-model').length === 4 && document.querySelectorAll('#calibration-gap-table tbody tr').length === 16");

      const report = await evaluate("(async () => { const region=" + JSON.stringify(region) + "; const url=new URL('samples/calibration/'+region+'.json',document.baseURI); const response=await fetch(url); if(!response.ok) throw new Error('Artifact HTTP '+response.status); return {artifact:await response.json(), href:document.querySelector('#calibration-download').href, status:document.querySelector('#calibration-status').textContent, provenance:document.querySelector('#calibration-provenance').textContent, context:document.querySelector('#calibration-context').textContent, models:[...document.querySelectorAll('#calibration-models .calibration-model')].map(row=>({name:row.querySelector('.calibration-model-name strong').textContent,badge:row.querySelector('.calibration-model-name span').textContent,stats:[...row.querySelectorAll('.calibration-model-stat strong')].map(node=>node.textContent)})),dailyValue:document.querySelector('#calibration-daily-value').textContent,dailyNote:document.querySelector('#calibration-daily-note').textContent,gapRows:[...document.querySelectorAll('#calibration-gap-table tbody tr')].map(row=>[...row.cells].map(cell=>cell.textContent.trim())),coverage:document.querySelector('#calibration-coverage-value').textContent,coverageNote:document.querySelector('#calibration-coverage-note').textContent,stepValue:document.querySelector('#calibration-step-value').textContent,stepNote:document.querySelector('#calibration-step-note').textContent,stepResult:document.querySelector('#calibration-step-value').getAttribute('data-result'),tableHeaders:[...document.querySelectorAll('#calibration-gap-table thead th')].map(node=>node.textContent.trim())}; })()");
      const artifact = report.artifact;
      const calibration = artifact.calibration;
      const validation = calibration.validation;
      if (artifact.schema !== "fireatlas-calibration-artifact-v1" || artifact.region.id !== region) throw new Error(region + ": artifact identity mismatch");
      if (report.models.length !== 4) throw new Error(region + ": expected one nested estimate and three fixed references");
      const nested = validation.nested_selected_pipeline;
      const expectedModels = [
        ["Nested selected pipeline", "NESTED HELD-OUT ESTIMATE", nested],
        ...Object.keys(labels).map((name) => [labels[name], "FIXED CANDIDATE REFERENCE", validation.models[name]]),
      ];
      for (let index = 0; index < expectedModels.length; index += 1) {
        const [name, badge, model] = expectedModels[index];
        const actual = report.models[index];
        if (!model || actual.name !== name || actual.badge !== badge
            || actual.stats[0] !== format(model.median_absolute_log_error)
            || actual.stats[1] !== percent(model.median_annual_absolute_percent_error)) {
          throw new Error(region + ": model result differs from artifact at row " + index);
        }
      }
      if (!report.provenance.includes("41 eligible for this calibration")) throw new Error(region + ": source-bundle and eligible calibration month counts are unclear");
      const daily = validation.daily_gap_benchmark.daily_metrics;
      const expectedDaily = format(daily.selected_pipeline.median_absolute_log_error) + " median log error · "
        + percent(daily.selected_pipeline.median_absolute_percent_error_nonzero) + " median nonzero-day absolute percentage error";
      if (report.dailyValue !== expectedDaily) throw new Error(region + ": daily metric differs from artifact");
      if (!report.dailyNote.includes("Fixed-reference median log errors")) throw new Error(region + ": daily fixed-reference scores are missing");

      const groups = new Map();
      for (const item of validation.daily_gap_benchmark.contiguous_gap_contribution_metrics) {
        const key = item.gap_duration_days + ":" + item.season;
        if (!groups.has(key)) groups.set(key, {gap_duration_days: item.gap_duration_days, season: item.season});
        groups.get(key)[item.model] = item;
      }
      const gapGroups = [...groups.values()].sort((a,b) => a.gap_duration_days-b.gap_duration_days || a.season.localeCompare(b.season));
      if (report.tableHeaders.length !== 6 || report.gapRows.length !== 16 || gapGroups.length !== 16) throw new Error(region + ": gap table shape differs from artifacts");
      for (let index = 0; index < gapGroups.length; index += 1) {
        const group = gapGroups[index];
        const countSource = group.selected_pipeline || group.monthly_ratio || group.annual_ratio || group.no_harmonization;
        const expected = [
          group.gap_duration_days + " day" + (group.gap_duration_days === 1 ? "" : "s") + " · " + group.season,
          Number(countSource.window_count || 0).toLocaleString("en-US"),
          format(group.selected_pipeline?.median_absolute_log_error),
          format(group.monthly_ratio?.median_absolute_log_error),
          format(group.annual_ratio?.median_absolute_log_error),
          format(group.no_harmonization?.median_absolute_log_error),
        ];
        if (JSON.stringify(report.gapRows[index]) !== JSON.stringify(expected)) throw new Error(region + ": gap metric differs from artifact at row " + index);
      }
      if (validation.prediction_interval.status !== "withheld-not-independently-calibrated"
          || report.coverage !== "Withheld" || validation.prediction_interval.held_out_coverage !== null
          || validation.prediction_interval.median_width !== null) throw new Error(region + ": prediction interval status is overstated");
      if (!report.coverageNote.includes("No coverage or interval width is claimed.")) throw new Error(region + ": withheld interval explanation is incomplete");
      const step = calibration.step_2012 || {};
      if (step.status !== "evaluated") {
        if (report.stepValue !== "Not tested" || report.stepResult !== null || step.ratio !== null || step.within_interval !== null) throw new Error(region + ": pending 2012 test exposes a result");
        if (!report.stepNote.includes("saved request metadata do not establish complete source exports")) throw new Error(region + ": pending 2012 limitation is not shown");
      }
      await evaluate("window.scrollTo(0,0)");
      const rect = await evaluate("(() => { const r=document.querySelector('#calibration-validation').getBoundingClientRect(); return {x:r.left,y:r.top+window.scrollY,width:r.width,height:r.height}; })()");
      const shot = await send("Page.captureScreenshot", {
        format: "png", captureBeyondViewport: true,
        clip: {x: rect.x, y: rect.y, width: rect.width, height: rect.height, scale: 1},
      });
      const screenshot = path.join(evidenceDir, "C10-T1-calibration-" + region + ".png");
      fs.writeFileSync(screenshot, Buffer.from(shot.data, "base64"));
      console.log(region + ": nested and fixed baselines, daily and seasonal gap metrics, withheld interval and 2012 status match source JSON; saved " + screenshot);
    }
    if (exceptions.length) throw new Error("Browser exceptions: " + exceptions.join("; "));
    console.log("Static Method page verified at " + base + " with no browser exceptions.");
  } finally {
    try { socket?.close(); } catch {}
    if (targetId) await fetch("http://127.0.0.1:" + fs.readFileSync(path.join(profile, "DevToolsActivePort"), "utf8").split(/\r?\n/)[0] + "/json/close/" + targetId).catch(() => {});
    chrome.kill("SIGTERM");
    await sleep(200);
    fs.rmSync(profile, {recursive: true, force: true});
  }
}

async function waitFor(evaluate, expression) {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    try {
      if (await evaluate("Boolean(" + expression + ")")) return;
    } catch {}
    await sleep(100);
  }
  throw new Error("Timed out waiting for browser condition: " + expression);
}

main().catch((error) => {
  console.error(error.stack || String(error));
  process.exitCode = 1;
});
