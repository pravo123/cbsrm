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

(async () => {
  const browser = await pw.chromium.launch();
  try {
    await badgeChecks(browser);
  } finally { await browser.close(); }
  let failed = 0;
  results.forEach(r => { if (!r.ok) failed++; console.log((r.ok ? "PASS " : "FAIL ") + r.name + (r.ok || !r.detail ? "" : "  [" + r.detail + "]")); });
  console.log(`${results.length - failed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
