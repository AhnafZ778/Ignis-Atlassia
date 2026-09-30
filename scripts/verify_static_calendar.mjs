#!/usr/bin/env node

// Browser-check the bundled calendar using only Node and the installed Chrome.
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
const site = path.resolve(option("--site", "site"));
const chromePath = option("--chrome", "/usr/bin/google-chrome");
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const fail = (message) => { throw new Error(message); };
const readCalendar = (region, year) => JSON.parse(
  fs.readFileSync(path.join(site, "data/v2/calendar", region, year + ".json"), "utf8"));

function matchedMonthExpectations(calendar, monthKey) {
  const availability = new Map(calendar.availability
    .filter((item) => item.date.startsWith(monthKey))
    .map((item) => [item.date, item.sources || {}]));
  const days = calendar.days.filter((item) => item.date.startsWith(monthKey));
  const paired = [];
  for (const day of days) {
    const sources = availability.get(day.date) || {};
    if (day.sensor_bridge?.status !== "complete"
        || day.viirs_status === "documented_processing_gap") continue;
    if (!["MODIS_SP", "VIIRS_SNPP_SP"].every((source) =>
      sources[source]?.export_complete
      && sources[source]?.availability?.status !== "documented_processing_gap")) continue;
    paired.push(day.date);
  }
  const totals = {};
  for (const source of ["MODIS_SP", "VIIRS_SNPP_SP"]) {
    const records = paired.map((date) => availability.get(date)[source]);
    totals[source] = {
      rows: records.reduce((sum, item) => sum + Number(item.raw_pixel_count || 0), 0),
      cells: records.reduce((sum, item) => sum + Number(item.detected_cell_days || 0), 0),
    };
  }
  const frpPairs = paired.map((date) => {
    const sources = availability.get(date);
    return [sources.MODIS_SP.frp_sum_mw, sources.VIIRS_SNPP_SP.frp_sum_mw];
  }).filter((pair) => pair.every((value) => value !== null && value !== undefined
    && Number.isFinite(Number(value))));
  return {
    pairedDays: paired.length,
    dayCount: days.length,
    totals,
    frpDays: frpPairs.length,
    frpMeans: frpPairs.length ? [0, 1].map((index) =>
      frpPairs.reduce((sum, pair) => sum + Number(pair[index]), 0) / frpPairs.length)
      : [null, null],
  };
}

async function main() {
  if (!fs.existsSync(chromePath)) fail("Chrome not found: " + chromePath);
  const norcal2024 = readCalendar("norcal", "2024");
  const punjab2024 = readCalendar("punjab-haryana", "2024");
  const norcal2006 = readCalendar("norcal", "2006");
  const july = norcal2024.months.find((item) => item.month === "2024-07");
  const august = norcal2024.months.find((item) => item.month === "2024-08");
  const julyVerdict = {
    norcal: july.verdict,
    punjab: punjab2024.months.find((item) => item.month === "2024-07").verdict,
  };
  const paired = matchedMonthExpectations(norcal2024, "2024-07");
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "fireatlas-calendar-chrome-"));
  const chrome = spawn(chromePath, [
    "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
    "--disable-dev-shm-usage", "--remote-debugging-port=0",
    "--user-data-dir=" + profile, "--window-size=1440,1200", "about:blank",
  ], {stdio: "ignore"});
  let socket;
  let targetId;
  const exceptions = [];
  const apiRequests = [];
  try {
    const portFile = path.join(profile, "DevToolsActivePort");
    const deadline = Date.now() + 20000;
    while (!fs.existsSync(portFile)) {
      if (chrome.exitCode !== null) fail("Chrome exited before starting DevTools.");
      if (Date.now() > deadline) fail("Timed out waiting for Chrome DevTools.");
      await sleep(100);
    }
    const port = fs.readFileSync(portFile, "utf8").split(/\r?\n/)[0];
    const endpoint = "http://127.0.0.1:" + port;
    const created = await fetch(endpoint + "/json/new?about:blank", {method: "PUT"});
    if (!created.ok) fail("Could not create Chrome tab: HTTP " + created.status);
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
      if (message.method === "Network.requestWillBeSent"
          && message.params.request.url.includes("/api/")) {
        apiRequests.push(message.params.request.url);
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
      if (result.exceptionDetails) fail(result.exceptionDetails.text);
      return result.result?.value;
    };
    const waitFor = async (expression, timeout = 20000) => {
      const end = Date.now() + timeout;
      while (Date.now() < end) {
        try {
          if (await evaluate("Boolean(" + expression + ")")) return;
        } catch {}
        await sleep(100);
      }
      const diagnostic = await evaluate("JSON.stringify({status:document.querySelector('#harm-status')?.textContent,ready:document.readyState})");
      fail("Timed out waiting for browser state: " + expression + " · page " + diagnostic
        + " · exceptions " + exceptions.join("; "));
    };
    const select = (selector, value) => evaluate("(() => { const node=document.querySelector("
      + JSON.stringify(selector) + "); node.value=" + JSON.stringify(String(value))
      + "; node.dispatchEvent(new Event('change',{bubbles:true})); })()");

    await send("Page.enable");
    await send("Runtime.enable");
    await send("Network.enable");
    await send("Page.navigate", {url: base + "/__calendar_fixture__"});
    await waitFor("document.querySelector('#harm-status')?.textContent.includes('static snapshot')");
    await waitFor("document.querySelectorAll('#harm-day-grid [data-date]').length === 31");
    await waitFor("document.querySelector('#harm-bridge-days').textContent.includes('days')");

    const current = await evaluate([
      "(() => {",
      "const get = selector => document.querySelector(selector).textContent;",
      "return {",
      "verdict:get('#harm-verdict'), valueNote:get('#harm-value-note'),",
      "years:get('#harm-years'), percentile:get('#harm-percentile'),",
      "bridge:get('#harm-bridge-state'), modis:get('#harm-bridge-modis'),",
      "modisNote:get('#harm-bridge-modis-note'), viirs:get('#harm-bridge-viirs'),",
      "viirsNote:get('#harm-bridge-viirs-note'), resultNote:get('#harm-bridge-result-note'),",
      "frp:get('#harm-frp-value'), frpUnit:get('#harm-frp-unit'),",
      "frpNote:get('#harm-frp-note')",
      "}; })()",
    ].join("\n"));
    if (current.verdict !== julyVerdict.norcal) fail("Northern California verdict differs from its static calendar JSON.");
    const composition = july.observed_days + " VIIRS-observed days · "
      + july.estimated_days + " MODIS-estimated days · " + july.unknown_days + " unknown UTC dates";
    if (!current.valueNote.includes(composition)
        || !current.valueNote.toLowerCase().includes("prediction intervals")
        || current.years !== String(july.n_years)
        || current.percentile !== "Percentile withheld"
        || !current.resultNote.includes("Observed + estimated days")) {
      fail("Mixed-month composition, uncertainty, or insufficient-history state is wrong: "
        + JSON.stringify(current));
    }
    if (paired.pairedDays <= 0
        || !current.modisNote.includes(paired.pairedDays + " matched UTC dates")
        || !current.viirsNote.includes(paired.pairedDays + " matched UTC dates")
        || !current.bridge.startsWith(paired.pairedDays + "/" + paired.dayCount + " paired UTC dates")) {
      fail("Sensor summaries do not expose the same matched-date set: "
        + JSON.stringify({current, paired}));
    }
    const displayedCells = await evaluate(
      '(() => ["#harm-bridge-modis", "#harm-bridge-viirs"].map(selector => '
      + 'Number(document.querySelector(selector).textContent.replace(/[^\\d.-]/g, ""))))()');
    const expectedCells = ["MODIS_SP", "VIIRS_SNPP_SP"].map((source) => paired.totals[source].cells);
    if (JSON.stringify(displayedCells) !== JSON.stringify(expectedCells)) {
      fail("Sensor cell totals include unmatched dates or differ from the bundle: "
        + JSON.stringify({displayedCells, expectedCells}));
    }
    for (const [note, source] of [[current.modisNote, "MODIS_SP"], [current.viirsNote, "VIIRS_SNPP_SP"]]) {
      if (!note.includes(paired.totals[source].rows.toLocaleString("en-US") + " eligible rows")) {
        fail("Matched-date row count is wrong for " + source + ": " + note);
      }
    }
    if (!current.frpUnit.includes("mean MW")
        || !current.frpNote.includes(paired.frpDays + " matched dates")) {
      fail("FRP aggregate or units are unclear: " + current.frpUnit + "; " + current.frpNote);
    }
    const displayedFrp = current.frp.split(" / ").map((value) =>
      Number(value.replace(/[^\d.-]/g, "")));
    if (displayedFrp.some((actual, index) => Math.abs(actual - paired.frpMeans[index]) > 0.051)) {
      fail("FRP values differ from mean daily source sums on matched dates: "
        + JSON.stringify({displayedFrp, expected: paired.frpMeans}));
    }

    const gapLabel = await evaluate("document.querySelector('#harm-day-grid [data-date=\"2024-07-25\"]').getAttribute('aria-label')");
    if (!gapLabel.toLowerCase().includes("gap") || !gapLabel.toLowerCase().includes("scaled")) {
      fail("Documented gap date is not visibly labelled: " + gapLabel);
    }
    await evaluate("document.querySelector('#harm-day-grid [data-date=\"2024-07-25\"]').click()");
    await waitFor("document.querySelector('#harm-records details') !== null");
    const drawer = await evaluate("document.querySelector('#harm-day-summary').textContent.toLowerCase()");
    if (!drawer.includes("prediction interval is withheld")
        || !drawer.includes("not prediction uncertainty")) {
      fail("Documented-gap drawer is missing the estimate uncertainty limit: " + drawer);
    }
    const sourceRows = await evaluate("document.querySelectorAll('#harm-records details').length");
    if (sourceRows < 1) fail("Static gap-date source drilldown returned no records.");
    await evaluate("document.querySelector('#harm-share').click()");
    await waitFor("!document.querySelector('#harm-share-card').hidden");
    const share = await evaluate([
      "(() => ({",
      "title:document.querySelector('#harm-share-card-title').textContent,",
      "inputs:document.querySelector('#harm-share-card-inputs').textContent,",
      "limit:document.querySelector('#harm-share-card-limit').textContent,",
      "quality:document.querySelector('#harm-share-card-quality').textContent,",
      "url:document.querySelector('#harm-share-card-url').href,",
      "method:document.querySelector('#harm-bridge-method').textContent",
      "}))()",
    ].join("\n"));
    if (!share.title.includes("2024") || !share.inputs.includes("SHA-256")
        || !share.quality || !share.limit.includes("MCD64A1 lagged context")
        || !share.url.includes("harm_region=norcal") || !share.url.includes("harm_month=7")
        || !share.method.includes("EASE-Grid")) {
      fail("Static evidence share card lost its trace fields: " + JSON.stringify(share));
    }

    await select("#harm-month", "8");
    await waitFor("document.querySelector('#harm-bridge-result-note').textContent.includes('Observed VIIRS')");
    const augustNote = await evaluate("document.querySelector('#harm-value-note').textContent");
    const expectedAugust = august.observed_days + " VIIRS-observed days · "
      + august.estimated_days + " MODIS-estimated days · " + august.unknown_days + " unknown UTC dates";
    if (august.estimate_type !== "observed" || augustNote !== expectedAugust
        || (await evaluate("document.querySelector('#harm-years').textContent")) !== String(august.n_years)
        || (await evaluate("document.querySelector('#harm-percentile').textContent")) !== "Percentile withheld") {
      fail("Fully observed month or insufficient-history display is wrong: "
        + JSON.stringify({augustNote, august}));
    }
    await waitFor("document.querySelector('#harm-corroboration-note').textContent.includes('906')");
    if (await evaluate("document.querySelector('#harm-corroboration-state').textContent") !== "MCD64A1 LAGGED") {
      fail("August 2024 MCD64A1 context did not render.");
    }
    await select("#harm-month", "9");
    await waitFor("document.querySelector('#harm-corroboration-state').textContent === 'ACTIVE FIRE ONLY'");
    await select("#harm-month", "7");
    await select("#harm-year", "2006");
    await waitFor("document.querySelector('#harm-value').textContent === 'Unknown'");
    const oldJuly = norcal2006.months.find((item) => item.month === "2006-07");
    const oldNote = await evaluate("document.querySelector('#harm-value-note').textContent");
    if (oldJuly.value !== null || !oldNote.includes(oldJuly.unknown_days + " unknown UTC dates")
        || !oldNote.includes("not included in the month total")
        || !oldNote.includes("total unknown, not zero")) {
      fail("Partial historical detections were mixed into the unknown month total: "
        + JSON.stringify({oldNote, oldJuly}));
    }

    await select("#harm-region", "punjab-haryana");
    await waitFor("document.querySelector('#harm-verdict').textContent.includes('Punjab')");
    const punjabVerdict = await evaluate("document.querySelector('#harm-verdict').textContent");
    if (punjabVerdict !== julyVerdict.punjab) fail("Punjab–Haryana verdict differs from the static calendar JSON.");
    const punjab = await evaluate([
      "(() => ({",
      "urls:[...document.querySelectorAll('#harm-official-links a')].map(node => node.href),",
      "text:document.querySelector('#harm-official-links').textContent",
      "}))()",
    ].join("\n"));
    if (JSON.stringify(punjab.urls) !== JSON.stringify(["https://firms.modaps.eosdis.nasa.gov/"])
        || !punjab.text.includes("No verified official local source listed.")
        || !punjab.text.includes("do not identify crop-burning cause")) {
      fail("Punjab–Haryana source or cause limitation is incorrect: " + JSON.stringify(punjab));
    }
    if (apiRequests.length) fail("Static calendar made API requests: " + apiRequests.join(", "));
    if (exceptions.length) fail("Browser exceptions: " + exceptions.join("; "));
    console.log("Static calendar browser verified: mixed July with paired-date sensor and FRP sums, "
      + "observed August, one-year percentile withholding, July 25 documented gap, partial 2006 history, "
      + "share card, both regions, and no API calls. July gap date opened "
      + sourceRows + " bundled source records.");
  } finally {
    try { socket?.close(); } catch {}
    if (targetId && fs.existsSync(path.join(profile, "DevToolsActivePort"))) {
      const debugPort = fs.readFileSync(path.join(profile, "DevToolsActivePort"), "utf8").split(/\r?\n/)[0];
      await fetch("http://127.0.0.1:" + debugPort + "/json/close/" + targetId).catch(() => {});
    }
    chrome.kill("SIGTERM");
    await sleep(200);
    fs.rmSync(profile, {recursive: true, force: true});
  }
}

main().catch((error) => {
  console.error(error.stack || String(error));
  process.exitCode = 1;
});
