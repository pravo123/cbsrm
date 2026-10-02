/* Headless checks for the laghubitta pages (sample dashboard, app, product page).
 *
 * Usage:  (cd site && python3 -m http.server 8790 &)
 *         node tools/laghubitta_headless_checks.js http://localhost:8790/
 *
 * Needs Playwright with Chromium (require('playwright'), or set PLAYWRIGHT_PATH).
 * Exits non-zero when any check fails. Synthetic data only; nothing is uploaded.
 */
"use strict";
let pw;
try { pw = require("playwright"); } catch (e) { pw = require(process.env.PLAYWRIGHT_PATH || "/opt/node22/lib/node_modules/playwright"); }
const path = require("path"), fs = require("fs"), os = require("os");
const BASE = (process.argv[2] || "http://localhost:8790/").replace(/\/?$/, "/");
const SITE = path.resolve(__dirname, "..", "site");
const VERIFIED = "Verified against the open-source reference library";
const CUSTOM = "Custom parameters. Not compared with the reference.";
const results = [];
function check(name, ok, detail) { results.push({ name, ok: !!ok, detail }); }

/* A copy of the sample with renamed and reordered columns, so the column mapper opens. */
function renamedSample() {
  const lines = fs.readFileSync(path.join(SITE, "laghubitta_loans.csv"), "utf8").trim().split("\n");
  const rename = { as_of: "Report Date", loan_id: "Centre ID", branch_id: "Branch Code", branch_name: "Branch",
    district: "District", province: "Province", product: "Loan Product", sector: "Purpose", disbursed_npr: "Disbursed",
    outstanding_npr: "Outstanding", days_past_due: "DPD", restructured: "Rescheduled", written_off: "Is Written Off",
    writeoff_npr: "Writeoff Amount", due_npr: "Demand", collected_npr: "Collection" };
  const hdr = lines[0].split(","), order = [10, 3, 15, 0, 7, 1, 12, 5, 9, 2, 14, 6, 13, 4, 11, 8];
  const out = lines.map((l, i) => { const c = l.split(","); return order.map(j => i === 0 ? rename[hdr[j]] : c[j]).join(","); });
  const f = path.join(os.tmpdir(), "laghubitta_renamed_reordered.csv");
  fs.writeFileSync(f, out.join("\n") + "\n");
  return f;
}

async function badgeState(p) {
  return p.evaluate(() => {
    const b = document.getElementById("verifiedBadge");
    return { shown: !b.hidden && b.offsetParent !== null, text: document.getElementById("verifiedTxt").textContent,
      label: document.getElementById("dsLabel").textContent, audit: (document.getElementById("auRef") || {}).textContent || "" };
  });
}

async function badgeChecks(browser) {
  const p = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  const errs = []; p.on("console", m => { if (m.type() === "error") errs.push(m.text()); }); p.on("pageerror", e => errs.push(e.message));
  await p.goto(BASE + "laghubitta-app.html"); await p.waitForSelector('html[data-boot="1"]');
  await p.click("#btnSample"); await p.waitForSelector('html[data-ready="1"]');
  let s = await badgeState(p);
  check("badge: sample with defaults shows Verified", s.shown && s.text === VERIFIED, s.text);
  check("badge: audit panel says it matches the reference", /^Matches the reference figures/.test(s.audit), s.audit.slice(0, 60));
  await p.click("#settingsBox summary");
  await p.fill("#cfg-alerts-par30_level", "5"); await p.waitForTimeout(500);
  s = await badgeState(p);
  check("badge: changed threshold shows the custom-parameters notice", s.shown && s.text === CUSTOM, s.text);
  check("badge: audit panel follows the custom rule", s.audit.startsWith(CUSTOM), s.audit.slice(0, 60));
  await p.emulateMedia({ media: "print" });
  const board = await p.innerText("#board");
  check("badge: board summary does not claim a match with custom parameters", board.includes(CUSTOM) && !/engine matches the reference/.test(board), "");
  await p.emulateMedia({ media: "screen" });
  await p.click("#btnReset"); await p.waitForTimeout(400);
  s = await badgeState(p);
  check("badge: Reset restores Verified", s.shown && s.text === VERIFIED, s.text);
  await p.click("#btnAnother"); await p.waitForTimeout(200);
  s = await badgeState(p);
  check("badge: start screen for another file clears badge and sample label", !s.shown && s.label === "no data loaded", s.label);
  await p.click("#btnSample"); await p.waitForSelector('html[data-ready="1"]'); await p.waitForTimeout(200);
  s = await badgeState(p);
  check("badge: reloading the sample shows Verified again", s.shown && s.text === VERIFIED, s.text);
  await p.click("#btnAnother");
  await p.setInputFiles("#fileIn", renamedSample());
  await p.waitForSelector("#mapper:not([hidden]) select", { timeout: 30000 });
  s = await badgeState(p);
  check("badge: column mapper for another file clears badge and sample label", !s.shown && s.label === "no data loaded", s.label);
  await p.click("#mapper .btn-primary, #mapper [id^=lbm-apply]");
  await p.waitForFunction(() => !document.getElementById("dash").hidden && /Your file/.test(document.getElementById("dsInfo").textContent), null, { timeout: 30000 });
  s = await badgeState(p);
  check("badge: a mapped upload never shows a badge", !s.shown, s.text);
  await p.click("#btnAnother");
  await p.setInputFiles("#fileIn", path.join(SITE, "laghubitta_loans.csv"));
  await p.waitForFunction(() => !document.getElementById("dash").hidden && /Your file/.test(document.getElementById("dsInfo").textContent), null, { timeout: 30000 });
  s = await badgeState(p);
  check("badge: an upload byte-identical to the sample never shows a badge", !s.shown, s.text);
  check("badge section: no console errors", errs.length === 0, errs.join(" | "));
  await p.close();
}

const PAGES = ["laghubitta.html", "laghubitta-app.html", "laghubitta-product.html"];

async function connectChecks(browser) {
  for (const page of PAGES) {
    const p = await browser.newPage({ viewport: { width: 1366, height: 900 } });
    await p.goto(BASE + page); await p.waitForTimeout(300);
    if (page === "laghubitta-app.html") { await p.click("#btnSample"); await p.waitForSelector('html[data-ready="1"]'); }
    const t = await p.evaluate(() => document.body.innerText);
    check(`connect: ${page} says "Existing CBS / MIS (CSV export)"`, t.includes("Existing CBS / MIS (CSV export)"), "");
    check(`connect: ${page} says the API connection is not built`, t.includes("Direct API connection is pilot work, not built yet."), "");
    check(`connect: ${page} makes no API or regulator-report claim`, !/export, report or API|regulator-oriented reports/i.test(t), "");
    await p.close();
  }
}

/* A two-month book where everything is written off: every ratio is NaN, gross is 0. */
function allWrittenOff() {
  const hdr = "as_of,loan_id,branch_id,branch_name,district,province,product,sector,disbursed_npr,outstanding_npr,days_past_due,restructured,written_off,writeoff_npr,due_npr,collected_npr";
  const rows = [hdr];
  ["2026-08-31", "2026-09-30"].forEach(d => {
    rows.push(`${d},C1,BR1,Test Branch,Jhapa,Koshi,Group Loan,Agriculture,1000000.00,0.00,400,0,1,0.00,0.00,0.00`);
    rows.push(`${d},C2,BR1,Test Branch,Jhapa,Koshi,Group Loan,Retail Trade,500000.00,0.00,0,0,1,0.00,0.00,0.00`);
  });
  const f = path.join(os.tmpdir(), "laghubitta_all_written_off.csv");
  fs.writeFileSync(f, rows.join("\n") + "\n");
  return f;
}
const BAD_WORDS = /\b(null|undefined|NaN)\b/i;
function badWords(t) { const m = t.match(new RegExp(BAD_WORDS.source, "gi")); return m ? [...new Set(m)].join(",") : ""; }

async function visibleText(p, withBoard) {
  let t = await p.evaluate(() => document.body.innerText);
  if (withBoard) { await p.emulateMedia({ media: "print" }); t += "\n" + await p.innerText("#board"); await p.emulateMedia({ media: "screen" }); }
  return t;
}

async function nullChecks(browser) {
  for (const page of ["laghubitta.html", "laghubitta-product.html"]) {
    const p = await browser.newPage({ viewport: { width: 1366, height: 900 } });
    await p.goto(BASE + page); await p.waitForTimeout(400);
    const t = await visibleText(p, false);
    check(`text: ${page} shows no null/undefined/NaN`, !badWords(t), badWords(t));
    await p.close();
  }
  const p = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  const app = BASE + "laghubitta-app.html";
  async function state(name, withBoard) { const t = await visibleText(p, withBoard); check(`text: app ${name} shows no null/undefined/NaN`, !badWords(t), badWords(t)); }
  await p.goto(app); await p.waitForSelector('html[data-boot="1"]'); await state("start screen", false);
  await p.click("#btnSample"); await p.waitForSelector('html[data-ready="1"]'); await state("sample + board summary", true);
  await p.click("#settingsBox summary");
  for (const [id, v] of [["#cfg-alerts-par30_level", "0"], ["#cfg-provision_rates-b31_90", "0"], ["#cfg-bands-0-max_dpd", "0"], ["#cfg-capital_npr", "0"], ["#cfg-rwa_npr", "0"]]) { await p.fill(id, v); }
  await p.waitForTimeout(600); await state("sample with extreme settings (zero RWA) + board summary", true);
  await p.click("#btnReset"); await p.waitForTimeout(300);
  for (const sc of ["regional_disaster", "funding_squeeze", "custom"]) { await p.click(`#scSeg button[data-id="${sc}"]`); }
  await state("sample after scenarios", false);
  await p.click("#btnAnother");
  await p.setInputFiles("#fileIn", renamedSample()); await p.waitForSelector("#mapper:not([hidden]) select", { timeout: 30000 });
  await state("column mapper", false);
  await p.click("#mapper .btn-primary, #mapper [id^=lbm-apply]");
  await p.waitForFunction(() => !document.getElementById("dash").hidden && /Your file/.test(document.getElementById("dsInfo").textContent), null, { timeout: 30000 });
  await state("mapped upload + board summary", true);
  await p.click("#btnAnother"); await p.setInputFiles("#fileIn", path.join(SITE, "laghubitta_template.csv"));
  await p.waitForFunction(() => /laghubitta_template/.test(document.getElementById("dsInfo").textContent), null, { timeout: 30000 });
  await state("one-month template upload + board summary", true);
  await p.click("#btnAnother"); await p.setInputFiles("#fileIn", allWrittenOff());
  await p.waitForFunction(() => /all_written_off/.test(document.getElementById("dsInfo").textContent), null, { timeout: 30000 });
  await state("all-written-off upload (NaN ratios) + board summary", true);
  const tpl = fs.readFileSync(path.join(SITE, "laghubitta_template.csv"), "utf8").replace(",45,", ",forty-five,");
  await p.click("#btnAnother"); await p.setInputFiles("#fileIn", { name: "bad.csv", mimeType: "text/csv", buffer: Buffer.from(tpl) });
  await p.waitForSelector("#loadMsg:not([hidden])"); await state("malformed upload error", false);
  await p.close();
}

(async () => {
  const browser = await pw.chromium.launch();
  try {
    for (const [name, fn] of [["null scan", nullChecks], ["connect", connectChecks], ["badge", badgeChecks]]) {
      try { await fn(browser); } catch (e) { check(`${name} section ran to completion`, false, String(e.message || e).split("\n")[0]); }
    }
  } finally { await browser.close(); }
  let failed = 0;
  results.forEach(r => { if (!r.ok) failed++; console.log((r.ok ? "PASS " : "FAIL ") + r.name + (r.ok || !r.detail ? "" : "  [" + r.detail + "]")); });
  console.log(`${results.length - failed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
