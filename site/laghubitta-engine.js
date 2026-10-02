/* CBSRM laghubitta risk engine (plain JavaScript, no dependencies).
 *
 * Implements docs/laghubitta_contract.md sections 3, 4, 5 and 5.1: bucket
 * assignment, portfolio metrics by any grouping, bucket balances, migration
 * matrix and roll rates, HHI and top-N share, branch early-warning alerts and
 * the stress engine, with the contract's DEFAULT_CONFIG. Also a CSV parser and
 * a schema validator for contract section 2 that reports problems in plain
 * language.
 *
 * Everything runs locally. This file makes no network calls.
 * Defaults are illustrative, to be calibrated. No compliance claim is made.
 *
 * Works in the browser (window.LaghubittaEngine) and in Node (module.exports).
 */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module === "object" && module.exports) { module.exports = api; }
  else { root.LaghubittaEngine = api; }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var BUCKETS = ["current", "b1_30", "b31_90", "b91_180", "b180p"];
  var STATES = BUCKETS.concat(["written_off", "closed"]);
  var DEFAULT_CONFIG = {
    npl_dpd_threshold: 90,
    provision_rates: { current: 0.01, b1_30: 0.05, b31_90: 0.25, b91_180: 0.50, b180p: 1.00 },
    alerts: { par30_level: 0.10, par30_jump: 0.02, roll_rate: 0.05, collection_drop: 0.05 }
  };
  var COLUMNS = ["as_of", "loan_id", "branch_id", "branch_name", "district", "province",
    "product", "sector", "disbursed_npr", "outstanding_npr", "days_past_due", "restructured",
    "written_off", "writeoff_npr", "due_npr", "collected_npr"];
  var MONEY = ["disbursed_npr", "outstanding_npr", "writeoff_npr", "due_npr", "collected_npr"];
  var TEXT = ["loan_id", "branch_id", "branch_name", "district", "province", "product", "sector"];
  var METRICS = ["gross_npr", "par30", "par90", "npl_ratio", "restructured_ratio",
    "writeoff_ratio", "collection_efficiency", "n_loans"];
  var PROVINCES = ["Koshi", "Madhesh", "Bagmati", "Gandaki", "Lumbini", "Karnali", "Sudurpashchim"];

  function clone(x) { return JSON.parse(JSON.stringify(x)); }
  function ratio(n, d) { return d !== 0 ? n / d : NaN; }

  /* ---------------- section 3: buckets ---------------- */
  function assignBucket(dpd) {
    if (dpd <= 0) return "current";
    if (dpd <= 30) return "b1_30";
    if (dpd <= 90) return "b31_90";
    if (dpd <= 180) return "b91_180";
    return "b180p";
  }

  /* ---------------- CSV parsing (RFC 4180 style) ---------------- */
  function parseCSV(text) {
    if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);
    var rows = [], row = [], field = "", i = 0, q = false, n = text.length, c;
    while (i < n) {
      c = text[i];
      if (q) {
        if (c === '"') { if (text[i + 1] === '"') { field += '"'; i += 2; continue; } q = false; i++; continue; }
        field += c; i++; continue;
      }
      if (c === '"' && field === "") { q = true; i++; continue; }
      if (c === ",") { row.push(field); field = ""; i++; continue; }
      if (c === "\r") { i++; continue; }
      if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; i++; continue; }
      field += c; i++;
    }
    if (field !== "" || row.length) { row.push(field); rows.push(row); }
    return { unterminatedQuote: q, rows: rows.filter(function (r) { return !(r.length === 1 && r[0].trim() === ""); }) };
  }

  /* ---------------- section 2: schema validation ---------------- */
  var DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
  function isMonthEnd(s) {
    if (!DATE_RE.test(s)) return false;
    var y = +s.slice(0, 4), m = +s.slice(5, 7), d = +s.slice(8, 10);
    if (m < 1 || m > 12) return false;
    return d === new Date(Date.UTC(y, m, 0)).getUTCDate();
  }
  function num(s) { var t = String(s).trim(); if (t === "") return NaN; var v = Number(t); return isFinite(v) ? v : NaN; }

  /* Returns {ok, rows, errors, warnings, summary}. Error strings are plain language. */
  function validate(text, opts) {
    opts = opts || {};
    var maxErrors = opts.maxErrors || 25;
    var errors = [], warnings = [], badRows = 0, out = [];
    if (typeof text !== "string" || text.trim() === "") {
      return { ok: false, rows: [], errors: ["The file is empty."], warnings: [], summary: null };
    }
    var parsed = parseCSV(text);
    if (parsed.unterminatedQuote) errors.push("The file has an opening quote (\") that is never closed, so it cannot be read as CSV.");
    if (!parsed.rows.length) return { ok: false, rows: [], errors: ["The file has no rows."], warnings: [], summary: null };
    var header = parsed.rows[0].map(function (h) { return h.trim(); });
    var idx = {};
    header.forEach(function (h, i) { idx[h] = i; });
    var missing = COLUMNS.filter(function (c) { return !(c in idx); });
    if (missing.length) {
      errors.push("Missing column" + (missing.length > 1 ? "s" : "") + ": " + missing.join(", ") +
        ". The first row must be the header from the template (laghubitta_template.csv).");
      return { ok: false, rows: [], errors: errors, warnings: warnings, summary: null };
    }
    var extra = header.filter(function (h) { return COLUMNS.indexOf(h) < 0; });
    if (extra.length) warnings.push("Ignored extra column" + (extra.length > 1 ? "s" : "") + ": " + extra.join(", ") + ".");
    if (parsed.rows.length < 2) {
      errors.push("The file has a header but no data rows.");
      return { ok: false, rows: [], errors: errors, warnings: warnings, summary: null };
    }
    var seen = {};
    function bad(lineNo, msg) {
      if (errors.length < maxErrors) errors.push("Row " + lineNo + ": " + msg);
    }
    for (var r = 1; r < parsed.rows.length; r++) {
      var raw = parsed.rows[r], line = r + 1, okRow = true;
      if (raw.length !== header.length) {
        bad(line, "expected " + header.length + " values but found " + raw.length + ". Check for a missing or extra comma.");
        badRows++; continue;
      }
      var rec = {};
      var asOf = raw[idx.as_of].trim();
      if (!isMonthEnd(asOf)) { bad(line, "as_of must be a month-end date written YYYY-MM-DD (found \"" + asOf + "\")."); okRow = false; }
      rec.as_of = asOf;
      TEXT.forEach(function (c) {
        var v = raw[idx[c]].trim();
        if (v === "") { bad(line, c + " is empty."); okRow = false; }
        rec[c] = v;
      });
      MONEY.forEach(function (c) {
        var v = num(raw[idx[c]]);
        if (isNaN(v)) { bad(line, c + " must be a number in NPR (found \"" + raw[idx[c]] + "\")."); okRow = false; }
        else if (v < 0) { bad(line, c + " cannot be negative (found " + v + ")."); okRow = false; }
        rec[c] = v;
      });
      var dpd = num(raw[idx.days_past_due]);
      if (isNaN(dpd) || dpd < 0 || Math.floor(dpd) !== dpd) {
        bad(line, "days_past_due must be a whole number of 0 or more (found \"" + raw[idx.days_past_due] + "\")."); okRow = false;
      }
      rec.days_past_due = dpd;
      ["restructured", "written_off"].forEach(function (c) {
        var v = raw[idx[c]].trim();
        if (v !== "0" && v !== "1") { bad(line, c + " must be 0 or 1 (found \"" + v + "\")."); okRow = false; }
        rec[c] = v === "1" ? 1 : 0;
      });
      if (okRow && rec.written_off === 1 && rec.outstanding_npr !== 0) {
        bad(line, "outstanding_npr must be 0 when written_off is 1 (found " + rec.outstanding_npr + ")."); okRow = false;
      }
      if (okRow && rec.written_off === 0 && rec.writeoff_npr !== 0) {
        warnings.length < 10 && warnings.push("Row " + line + ": writeoff_npr is " + rec.writeoff_npr + " on a loan that is not written off; it still counts in the write-off ratio.");
      }
      if (okRow) {
        var key = rec.as_of + "|" + rec.loan_id;
        if (seen[key]) { bad(line, "loan_id " + rec.loan_id + " appears twice for " + rec.as_of + " (first on row " + seen[key] + ")."); okRow = false; }
        else seen[key] = line;
      }
      if (okRow) out.push(rec); else badRows++;
    }
    if (badRows > 0 && errors.length >= maxErrors) {
      errors.push("Stopped listing after " + maxErrors + " problems; " + badRows + " rows in total have problems.");
    }
    var ok = errors.length === 0 && out.length > 0;
    var dates = {};
    out.forEach(function (x) { dates[x.as_of] = 1; });
    var nDates = Object.keys(dates).length;
    if (ok && nDates < 2) warnings.push("Only one month-end found. Migration, roll rates and alerts need at least two consecutive month-ends.");
    if (ok) {
      var unknownProv = {};
      out.forEach(function (x) { if (PROVINCES.indexOf(x.province) < 0) unknownProv[x.province] = 1; });
      var up = Object.keys(unknownProv);
      if (up.length) warnings.push("Province name" + (up.length > 1 ? "s" : "") + " not in the list of 7 provinces: " + up.slice(0, 5).join(", ") + ". They are kept as written.");
    }
    return { ok: ok, rows: ok ? out : [], errors: errors, warnings: warnings,
      summary: { data_rows: parsed.rows.length - 1, valid_rows: out.length, bad_rows: badRows, month_ends: nDates } };
  }

  /* ---------------- dataset ---------------- */
  function Dataset(rows) {
    var byDate = {}, branchInfo = {};
    rows.forEach(function (x) {
      (byDate[x.as_of] = byDate[x.as_of] || []).push(x);
      if (!branchInfo[x.branch_id]) branchInfo[x.branch_id] = { branch_id: x.branch_id, branch_name: x.branch_name, district: x.district, province: x.province };
    });
    this.rows = rows;
    this.byDate = byDate;
    this.dates = Object.keys(byDate).sort();
    this.branchInfo = branchInfo;
  }

  /* ---------------- section 4: portfolio metrics ---------------- */
  function emptySums() { return { gross: 0, p30: 0, p90: 0, npl: 0, restr: 0, w: 0, due: 0, coll: 0, n: 0 }; }
  function addRow(s, x, nplT) {
    if (x.written_off === 0) {
      var o = x.outstanding_npr, d = x.days_past_due;
      s.gross += o; s.n += 1;
      if (d > 30) s.p30 += o;
      if (d > 90) s.p90 += o;
      if (d > nplT) s.npl += o;
      if (x.restructured === 1) s.restr += o;
    }
    s.w += x.writeoff_npr; s.due += x.due_npr; s.coll += x.collected_npr;
  }
  function finish(s) {
    return { gross_npr: s.gross, par30: ratio(s.p30, s.gross), par90: ratio(s.p90, s.gross),
      npl_ratio: ratio(s.npl, s.gross), restructured_ratio: ratio(s.restr, s.gross),
      writeoff_ratio: ratio(s.w, s.gross + s.w), collection_efficiency: ratio(s.coll, s.due), n_loans: s.n };
  }
  function cmpKeys(a, b) { return a < b ? -1 : a > b ? 1 : 0; }

  /* by: array of column names. Returns rows [{...by, ...metrics}] sorted ascending by the by columns. */
  function portfolioMetrics(ds, asOf, by, config) {
    by = by || []; config = config || DEFAULT_CONFIG;
    var rows = ds.byDate[asOf] || [], nplT = config.npl_dpd_threshold;
    if (!by.length) { var s = emptySums(); rows.forEach(function (x) { addRow(s, x, nplT); }); return [finish(s)]; }
    var groups = {}, keys = {};
    rows.forEach(function (x) {
      var kv = by.map(function (c) { return x[c]; }), k = kv.join("\u0001");
      if (!groups[k]) { groups[k] = emptySums(); keys[k] = kv; }
      addRow(groups[k], x, nplT);
    });
    return Object.keys(groups).sort(function (a, b) {
      for (var i = 0; i < by.length; i++) { var c = cmpKeys(keys[a][i], keys[b][i]); if (c) return c; }
      return 0;
    }).map(function (k) {
      var rec = {}; by.forEach(function (c, i) { rec[c] = keys[k][i]; });
      var m = finish(groups[k]); METRICS.forEach(function (mk) { rec[mk] = m[mk]; });
      return rec;
    });
  }

  function bucketBalances(ds, asOf, by) {
    by = by || [];
    var rows = ds.byDate[asOf] || [], groups = {}, keys = {};
    rows.forEach(function (x) {
      if (x.written_off !== 0) return;
      var kv = by.map(function (c) { return x[c]; }), k = kv.join("\u0001");
      if (!groups[k]) { groups[k] = { current: 0, b1_30: 0, b31_90: 0, b91_180: 0, b180p: 0 }; keys[k] = kv; }
      groups[k][assignBucket(x.days_past_due)] += x.outstanding_npr;
    });
    if (!by.length && !groups[""]) groups[""] = { current: 0, b1_30: 0, b31_90: 0, b91_180: 0, b180p: 0 }, keys[""] = [];
    return Object.keys(groups).sort(function (a, b) {
      for (var i = 0; i < by.length; i++) { var c = cmpKeys(keys[a][i], keys[b][i]); if (c) return c; }
      return 0;
    }).map(function (k) {
      var rec = {}; by.forEach(function (c, i) { rec[c] = keys[k][i]; });
      BUCKETS.forEach(function (b) { rec[b] = groups[k][b]; });
      return rec;
    });
  }

  /* ---------------- section 5: migration, concentration, alerts ---------------- */
  function migrationMatrix(ds, fromAsOf, toAsOf, weight, filter) {
    weight = weight || "outstanding";
    var to = {};
    (ds.byDate[toAsOf] || []).forEach(function (x) {
      if (filter && !filter(x)) return;
      to[x.loan_id] = x.written_off === 1 ? "written_off" : assignBucket(x.days_past_due);
    });
    var acc = {};
    BUCKETS.forEach(function (b) { acc[b] = {}; STATES.forEach(function (s) { acc[b][s] = 0; }); });
    (ds.byDate[fromAsOf] || []).forEach(function (x) {
      if (x.written_off !== 0 || (filter && !filter(x))) return;
      var w = weight === "count" ? 1 : x.outstanding_npr;
      acc[assignBucket(x.days_past_due)][to[x.loan_id] || "closed"] += w;
    });
    var m = {};
    BUCKETS.forEach(function (b) {
      var tot = 0; STATES.forEach(function (s) { tot += acc[b][s]; });
      m[b] = {}; STATES.forEach(function (s) { m[b][s] = ratio(acc[b][s], tot); });
    });
    return m;
  }

  function rollRates(m) {
    var out = {};
    BUCKETS.forEach(function (b, i) {
      var worse = b === "b180p" ? ["written_off"] : BUCKETS.slice(i + 1).concat(["written_off"]);
      var v = 0, any = false;
      worse.forEach(function (s) { if (!isNaN(m[b][s])) { v += m[b][s]; any = true; } });
      out[b] = any ? v : NaN;
    });
    return out;
  }

  function shares(ds, asOf, by) {
    var g = {}, tot = 0;
    (ds.byDate[asOf] || []).forEach(function (x) {
      if (x.written_off !== 0) return;
      g[x[by]] = (g[x[by]] || 0) + x.outstanding_npr; tot += x.outstanding_npr;
    });
    return Object.keys(g).map(function (k) { return { key: k, share: ratio(g[k], tot) }; });
  }
  function hhi(ds, asOf, by) {
    var s = shares(ds, asOf, by); if (!s.length || isNaN(s[0].share)) return NaN;
    return s.reduce(function (a, r) { return a + r.share * r.share; }, 0);
  }
  function topNShare(ds, asOf, by, n) {
    n = n == null ? 5 : n;
    var s = shares(ds, asOf, by); if (!s.length || isNaN(s[0].share)) return NaN;
    return s.sort(function (a, b) { return b.share - a.share; }).slice(0, n).reduce(function (a, r) { return a + r.share; }, 0);
  }

  function branchAlerts(ds, asOf, prevAsOf, config) {
    config = config || DEFAULT_CONFIG;
    var th = config.alerts, cur = {}, prv = {};
    portfolioMetrics(ds, asOf, ["branch_id"], config).forEach(function (r) { cur[r.branch_id] = r; });
    portfolioMetrics(ds, prevAsOf, ["branch_id"], config).forEach(function (r) { prv[r.branch_id] = r; });
    var ids = Object.keys(cur).concat(Object.keys(prv).filter(function (k) { return !(k in cur); })).sort();
    var out = [];
    ids.forEach(function (bid) {
      var c = cur[bid], p = prv[bid];
      var rr = rollRates(migrationMatrix(ds, prevAsOf, asOf, "outstanding", function (x) { return x.branch_id === bid; })).current;
      var vals = {
        COLLECTION_DROP: [(p ? p.collection_efficiency : NaN) - (c ? c.collection_efficiency : NaN), th.collection_drop],
        PAR30_JUMP: [(c ? c.par30 : NaN) - (p ? p.par30 : NaN), th.par30_jump],
        PAR30_LEVEL: [c ? c.par30 : NaN, th.par30_level],
        ROLL_RATE: [rr, th.roll_rate]
      };
      Object.keys(vals).sort().forEach(function (rule) {
        var v = vals[rule][0], t = vals[rule][1];
        if (!isNaN(v) && v >= t) out.push({ branch_id: bid, rule: rule, value: v, threshold: t, severity: v >= 2 * t ? "high" : "medium" });
      });
    });
    return out;
  }

  /* ---------------- section 5.1: stress engine ---------------- */
  function applyScenario(segments, bs, sc, config) {
    config = config || DEFAULT_CONFIG;
    var rates = config.provision_rates, shift = sc.base_shift || 0, sm = sc.sector_mult || {}, pm = sc.province_mult || {};
    var T = {}, U = {};
    BUCKETS.forEach(function (b) { T[b] = 0; U[b] = 0; });
    segments.forEach(function (g) {
      var s = Math.min(1, shift * (sm[g.sector] != null ? sm[g.sector] : 1) * (pm[g.province] != null ? pm[g.province] : 1));
      var st = { current: (1 - s) * g.current, b1_30: (1 - s) * g.b1_30 + s * g.current,
        b31_90: (1 - s) * g.b31_90 + s * g.b1_30, b91_180: (1 - s) * g.b91_180 + s * g.b31_90,
        b180p: g.b180p + s * g.b91_180 };
      BUCKETS.forEach(function (b) { T[b] += st[b]; U[b] += g[b]; });
    });
    var gross = 0, prov = 0, provB = 0;
    BUCKETS.forEach(function (b) { gross += T[b]; prov += T[b] * rates[b]; provB += U[b] * rates[b]; });
    var nii = bs.borrowings_npr * (sc.funding_cost_bps || 0) / 10000;
    var cap = bs.capital_npr - (prov - provB) - nii;
    return { scenario_id: sc.id, buckets: T, gross_npr: gross,
      par30: ratio(T.b31_90 + T.b91_180 + T.b180p, gross), par90: ratio(T.b91_180 + T.b180p, gross),
      provisions_npr: prov, delta_provisions_npr: prov - provB, nii_hit_npr: nii, capital_npr: cap,
      car: ratio(cap, bs.rwa_npr),
      liquidity_gap_90d_npr: bs.liquid_assets_npr + bs.inflows_90d_npr * (1 - (sc.inflow_haircut || 0)) -
        bs.outflows_90d_npr * (sc.outflow_mult != null ? sc.outflow_mult : 1) };
  }

  var DEFAULT_SCENARIOS = [
    { id: "base", label: "Base case (no shock)" },
    { id: "rate_up_200bp", label: "Funding rates up 200 bp", base_shift: 0.02, funding_cost_bps: 200 },
    { id: "agri_income_shock", label: "Farm income shock (crop prices fall)", base_shift: 0.05,
      sector_mult: { Agriculture: 4.0, Livestock: 3.0 } },
    { id: "monsoon_seasonal", label: "Heavy monsoon season", base_shift: 0.06,
      sector_mult: { Agriculture: 2.5, Livestock: 2.0, Transport: 1.5 }, inflow_haircut: 0.10 },
    { id: "regional_disaster", label: "Flood in Madhesh and Lumbini", base_shift: 0.08,
      province_mult: { Madhesh: 4.0, Lumbini: 3.0 }, sector_mult: { Agriculture: 1.5, Livestock: 1.5 },
      inflow_haircut: 0.20, outflow_mult: 1.10 },
    { id: "funding_squeeze", label: "Wholesale funding squeeze", funding_cost_bps: 300,
      inflow_haircut: 0.25, outflow_mult: 1.35 }
  ];

  /* Illustrative balance sheet sized from gross when the export carries none. */
  function defaultBalanceSheet(gross) {
    function r(k) { return Math.round(k * gross / 1000) * 1000; }
    return { capital_npr: r(0.125), rwa_npr: r(1.08), liquid_assets_npr: r(0.11),
      inflows_90d_npr: r(0.24), outflows_90d_npr: r(0.28), borrowings_npr: r(0.70) };
  }

  /* ---------------- whole dashboard in the demo JSON shape (contract section 6) ---------------- */
  function computeAll(ds, config, balanceSheet, scenarios) {
    config = config || DEFAULT_CONFIG;
    var dates = ds.dates, latest = dates[dates.length - 1], prev = dates.length > 1 ? dates[dates.length - 2] : null;
    var institution = dates.map(function (d) { var m = portfolioMetrics(ds, d, [], config)[0]; m.as_of = d; return m; });
    var perDate = {};
    dates.forEach(function (d) {
      perDate[d] = {};
      portfolioMetrics(ds, d, ["branch_id"], config).forEach(function (r) { perDate[d][r.branch_id] = r; });
    });
    var empty = finish(emptySums());
    var branches = Object.keys(ds.branchInfo).sort().map(function (bid) {
      var b = clone(ds.branchInfo[bid]);
      b.series = dates.map(function (d) {
        var r = perDate[d][bid] || empty, s = { as_of: d };
        METRICS.forEach(function (k) { s[k] = r[k]; });
        return s;
      });
      return b;
    });
    function byKey(col) {
      return portfolioMetrics(ds, latest, [col], config).map(function (r) {
        var o = { key: r[col] }; METRICS.forEach(function (k) { o[k] = r[k]; }); return o;
      });
    }
    var segments = bucketBalances(ds, latest, ["sector", "province"]);
    var bs = balanceSheet || defaultBalanceSheet(institution[institution.length - 1].gross_npr);
    var migration = null, alerts = [];
    if (prev) {
      var mm = migrationMatrix(ds, prev, latest, "outstanding");
      migration = { from_as_of: prev, to_as_of: latest, states: STATES.slice(), matrix: mm, roll_rates: rollRates(mm) };
      alerts = branchAlerts(ds, latest, prev, config);
    }
    var concentration = {};
    ["district", "sector", "product"].forEach(function (by) {
      concentration[by] = { hhi: hhi(ds, latest, by), top5_share: topNShare(ds, latest, by, 5) };
    });
    return { config: clone(config), as_of_dates: dates.slice(), institution: institution, branches: branches,
      by_district: byKey("district"), by_product: byKey("product"), by_sector: byKey("sector"),
      segments: segments, migration: migration, concentration: concentration, alerts: alerts,
      balance_sheet: bs, scenarios: scenarios || clone(DEFAULT_SCENARIOS) };
  }

  /* ---------------- verification against a reference (ruling R1) ---------------- */
  var AMOUNT_KEYS = { gross_npr: 1, current: 1, b1_30: 1, b31_90: 1, b91_180: 1, b180p: 1 };
  function closeR1(exp, act, amount) {
    var en = exp == null || (typeof exp === "number" && isNaN(exp));
    var an = act == null || (typeof act === "number" && isNaN(act));
    if (en || an) return en && an;
    if (amount) { var m = Math.max(Math.abs(exp), Math.abs(act)); return Math.abs(exp - act) <= 1e-9 * m; }
    return Math.abs(exp - act) <= 1e-9;
  }
  /* Compares computed vs reference JSON. Ratios: absolute 1e-9. NPR amounts: relative 1e-9. */
  function verify(comp, ref) {
    var checked = 0, mism = [];
    function cmp(where, e, a, amount) { checked++; if (!closeR1(e, a, amount) && mism.length < 20) mism.push(where + ": reference " + e + ", engine " + a); }
    function metrics(where, e, a) { METRICS.forEach(function (k) { cmp(where + "." + k, e[k], a[k], k in AMOUNT_KEYS); }); }
    if (JSON.stringify(ref.as_of_dates) !== JSON.stringify(comp.as_of_dates)) mism.push("as_of_dates differ");
    ref.institution.forEach(function (r, i) { metrics("institution[" + r.as_of + "]", r, comp.institution[i] || {}); });
    var cb = {}; comp.branches.forEach(function (b) { cb[b.branch_id] = b; });
    ref.branches.forEach(function (b) {
      var c = cb[b.branch_id]; if (!c) { mism.push("branch " + b.branch_id + " missing"); return; }
      b.series.forEach(function (s, i) { metrics(b.branch_id + "[" + s.as_of + "]", s, c.series[i] || {}); });
    });
    ["by_district", "by_product", "by_sector"].forEach(function (k) {
      var cm = {}; comp[k].forEach(function (r) { cm[r.key] = r; });
      ref[k].forEach(function (r) { metrics(k + "[" + r.key + "]", r, cm[r.key] || {}); });
    });
    var cs = {}; comp.segments.forEach(function (s) { cs[s.sector + "|" + s.province] = s; });
    ref.segments.forEach(function (s) { var c = cs[s.sector + "|" + s.province] || {}; BUCKETS.forEach(function (b) { cmp("segment " + s.sector + "/" + s.province + "." + b, s[b], c[b], true); }); });
    if (ref.migration && comp.migration) {
      BUCKETS.forEach(function (b) {
        STATES.forEach(function (s) { cmp("migration " + b + "->" + s, ref.migration.matrix[b][s], comp.migration.matrix[b][s], false); });
        cmp("roll_rate " + b, ref.migration.roll_rates[b], comp.migration.roll_rates[b], false);
      });
    }
    Object.keys(ref.concentration).forEach(function (k) {
      cmp("hhi " + k, ref.concentration[k].hhi, comp.concentration[k].hhi, false);
      cmp("top5 " + k, ref.concentration[k].top5_share, comp.concentration[k].top5_share, false);
    });
    if (ref.alerts.length !== comp.alerts.length) mism.push("alert count: reference " + ref.alerts.length + ", engine " + comp.alerts.length);
    else ref.alerts.forEach(function (a, i) {
      var c = comp.alerts[i];
      if (a.branch_id !== c.branch_id || a.rule !== c.rule || a.severity !== c.severity) mism.push("alert " + i + " differs");
      cmp("alert " + i + " value", a.value, c.value, false);
    });
    return { ok: mism.length === 0, checked: checked, mismatches: mism };
  }

  /* ---------------- file hashing (no network) ---------------- */
  function sha256Hex(buffer) {
    try {
      var subtle = (typeof crypto !== "undefined" && crypto.subtle) ? crypto.subtle : null;
      if (!subtle) return Promise.resolve(null);
      return subtle.digest("SHA-256", buffer).then(function (h) {
        return Array.prototype.map.call(new Uint8Array(h), function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
      }, function () { return null; });
    } catch (e) { return Promise.resolve(null); }
  }

  return {
    BUCKETS: BUCKETS, STATES: STATES, COLUMNS: COLUMNS, METRICS: METRICS, PROVINCES: PROVINCES,
    DEFAULT_CONFIG: DEFAULT_CONFIG, DEFAULT_SCENARIOS: DEFAULT_SCENARIOS,
    defaultConfig: function () { return clone(DEFAULT_CONFIG); },
    assignBucket: assignBucket, parseCSV: parseCSV, validate: validate, Dataset: Dataset,
    portfolioMetrics: portfolioMetrics, bucketBalances: bucketBalances,
    migrationMatrix: migrationMatrix, rollRates: rollRates, hhi: hhi, topNShare: topNShare,
    branchAlerts: branchAlerts, applyScenario: applyScenario, defaultBalanceSheet: defaultBalanceSheet,
    computeAll: computeAll, verify: verify, sha256Hex: sha256Hex
  };
});
