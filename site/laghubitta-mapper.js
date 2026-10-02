/* CBSRM laghubitta column mapper (plain JavaScript, no dependencies).
 *
 * When an uploaded portfolio export does not use the template header
 * (docs/laghubitta_contract.md section 2), this module suggests which column
 * of the file holds each required field, checks the choice, rewrites the
 * rows into the template layout, and reads and writes the mapping file of
 * docs/laghubitta_contract_v1_1.md section 5. It can also draw the mapping
 * screen.
 *
 * Everything runs locally. This file makes no network calls and loads no
 * external resources. Nothing is uploaded.
 *
 * Needs laghubitta-engine.js (window.LaghubittaEngine, or require() in Node)
 * for COLUMNS and parseCSV. Works in the browser (window.LaghubittaMapper) and
 * in Node (module.exports).
 */
(function (root, factory) {
  "use strict";
  var api = factory(root);
  if (typeof module === "object" && module.exports) { module.exports = api; }
  else { root.LaghubittaMapper = api; }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  var FORMAT = "cbsrm-laghubitta-mapping";
  var VERSION = 1;
  /* Minimum name similarity for a fuzzy match. 0.7 rather than 0.6: at 0.6, columns such as
   * "Savings Balance", "Interest Collected" and "Account Type" were matched to required fields. */
  var THRESHOLD = 0.7;
  var SCORE_EXACT = 1, SCORE_SYNONYM = 0.9, SCORE_FUZZY_MAX = 0.85;

  var E = null;
  function engine() {
    if (E) return E;
    if (root && root.LaghubittaEngine) E = root.LaghubittaEngine;
    else if (typeof require === "function") {
      try { E = require("./laghubitta-engine.js"); } catch (e) { E = null; }
    }
    if (!E) throw new Error("laghubitta-mapper.js needs laghubitta-engine.js to be loaded first.");
    return E;
  }

  /* label: short name used in messages; desc: one plain line shown on screen. */
  var FIELDS = {
    as_of: { label: "month-end date", desc: "month-end date, YYYY-MM-DD" },
    loan_id: { label: "account id", desc: "account or centre account id, the same every month" },
    branch_id: { label: "branch code", desc: "branch code, for example BR001" },
    branch_name: { label: "branch name", desc: "branch name" },
    district: { label: "district name", desc: "district name" },
    province: { label: "province name", desc: "province, one of the 7" },
    product: { label: "loan product", desc: "loan product name" },
    sector: { label: "economic sector", desc: "economic sector or loan purpose" },
    disbursed_npr: { label: "amount disbursed", desc: "principal disbursed to date, NPR" },
    outstanding_npr: { label: "amount outstanding", desc: "principal outstanding, NPR (0 when written off)" },
    days_past_due: { label: "days past due", desc: "days past due, a whole number of 0 or more" },
    restructured: { label: "restructured flag", desc: "restructured or rescheduled, 0 or 1" },
    written_off: { label: "written-off flag", desc: "written off, 0 or 1" },
    writeoff_npr: { label: "amount written off", desc: "amount written off in that month, NPR, else 0" },
    due_npr: { label: "amount due", desc: "amount due in that month, NPR" },
    collected_npr: { label: "amount collected", desc: "amount collected in that month, NPR" }
  };

  /* Other names a CBS or MIS export commonly uses for each field. Compared after norm(). */
  var SYNONYMS = {
    as_of: ["date", "as_of_date", "as_on", "as_on_date", "report_date", "reporting_date", "month_end",
      "month_end_date", "period", "period_end", "report_month"],
    loan_id: ["account_id", "account_no", "account_number", "acc_no", "ac_no", "centre_id", "center_id",
      "centre_account", "center_account", "loan_no", "loan_number", "loan_account"],
    branch_id: ["branch_code", "branch_no", "branch_number", "br_code"],
    branch_name: ["branch", "branch_title"],
    district: ["district_name", "jilla"],
    province: ["state", "pradesh", "province_name"],
    product: ["product_name", "loan_product", "product_type", "loan_type", "scheme"],
    sector: ["purpose", "economic_sector", "loan_purpose", "sector_name"],
    disbursed_npr: ["disbursed", "disbursement", "sanctioned", "loan_amount", "disbursed_amount",
      "disbursement_amount", "sanctioned_amount", "principal_disbursed"],
    outstanding_npr: ["outstanding", "balance", "principal_outstanding", "os_balance",
      "outstanding_balance", "outstanding_amount", "outstanding_principal", "loan_balance",
      "principal_balance"],
    days_past_due: ["dpd", "dpd_days", "overdue_days", "days_overdue", "arrears_days", "days_in_arrears",
      "past_due_days"],
    restructured: ["is_restructured", "rescheduled", "is_rescheduled", "restructured_flag",
      "restructure_flag"],
    written_off: ["is_written_off", "writeoff_flag", "write_off_flag", "written_off_flag", "is_writeoff"],
    writeoff_npr: ["writeoff_amount", "written_off_amount", "amount_written_off", "writeoff_amt"],
    due_npr: ["due", "demand", "installment_due", "instalment_due", "amount_due", "due_amount",
      "demand_amount"],
    collected_npr: ["collected", "collection", "repayment", "paid", "amount_collected",
      "collected_amount", "collection_amount", "repaid", "amount_paid"]
  };

  /* Words that, in a column name, mean the column holds some other kind of value than the numeric
   * field: a date, a count or serial number, interest, penalty or overdue amounts, a code or name.
   * A fuzzy match to a numeric field is not made when the column name has one of these words and
   * the field name or synonym it is compared with does not ("Overdue Amount" is not due_npr,
   * "Interest Outstanding" is not outstanding_npr, "Disbursement Date" is not disbursed_npr).
   * Exact and synonym matches are not affected. */
  var NOT_AMOUNT = ["date", "dt", "by", "no", "number", "count", "days", "since", "interest", "penalty",
    "overdue", "rate", "sheet", "code", "id", "name", "type", "status"];
  var NOT_DAYS = ["date", "dt", "by", "amount", "amt", "npr", "rs", "interest", "penalty", "code", "id",
    "name", "status"];
  var NOT_FLAG = ["date", "dt", "by", "amount", "amt", "npr", "rs", "no", "number", "count", "code", "id",
    "name"];
  var BLOCK = {
    disbursed_npr: NOT_AMOUNT, outstanding_npr: NOT_AMOUNT, writeoff_npr: NOT_AMOUNT, due_npr: NOT_AMOUNT,
    collected_npr: NOT_AMOUNT, days_past_due: NOT_DAYS, restructured: NOT_FLAG, written_off: NOT_FLAG
  };

  function label(f) { return FIELDS[f] ? FIELDS[f].label : f.replace(/_/g, " "); }
  function desc(f) { return FIELDS[f] ? FIELDS[f].desc : f.replace(/_/g, " "); }

  /* ---------------- name similarity ---------------- */
  function norm(s) { return String(s == null ? "" : s).toLowerCase().replace(/[^a-z0-9]+/g, ""); }
  function tokens(s) {
    return String(s == null ? "" : s).replace(/([a-z0-9])([A-Z])/g, "$1 $2").toLowerCase()
      .split(/[^a-z0-9]+/).filter(function (t) { return t !== ""; });
  }
  function bigrams(s) { var out = []; for (var i = 0; i + 1 < s.length; i++) out.push(s.slice(i, i + 2)); return out; }
  /* Dice coefficient on multisets: 2 |A n B| / (|A| + |B|). */
  function dice(a, b) {
    if (!a.length || !b.length) return 0;
    var count = Object.create(null), inter = 0;
    a.forEach(function (x) { count[x] = (count[x] || 0) + 1; });
    b.forEach(function (x) { if (count[x] > 0) { count[x]--; inter++; } });
    return 2 * inter / (a.length + b.length);
  }
  /* Name similarity of file column a to field or synonym b, 0..1: the better of character-bigram
   * Dice and word-token Dice. Token Dice is used only when b has two or more words, so one shared
   * word ("Branch Manager" vs "branch") is not enough. */
  function similarity(a, b) {
    var na = norm(a), nb = norm(b);
    if (!na || !nb) return 0;
    if (na === nb) return 1;
    var tb = tokens(b), best = dice(bigrams(na), bigrams(nb));
    return tb.length > 1 ? Math.max(best, dice(tokens(a), tb)) : best;
  }

  function cleanHeaders(headers) {
    return (headers || []).map(function (h) { return String(h == null ? "" : h).trim(); });
  }

  /* Score of file column h for field f: 1 exact, 0.9 synonym, else the best name similarity to
   * the field or a synonym of 6 or more letters, if at least THRESHOLD, capped at 0.85. Short
   * synonyms ("dpd", "due", "state") count only as exact synonyms. A fuzzy comparison is skipped
   * when h has a BLOCK word for f that the compared name lacks. */
  function scorePair(f, h) {
    var nh = norm(h);
    if (!nh) return 0;
    if (nh === norm(f)) return SCORE_EXACT;
    var syn = SYNONYMS[f] || [], i;
    for (i = 0; i < syn.length; i++) if (norm(syn[i]) === nh) return SCORE_SYNONYM;
    var block = BLOCK[f] || [], th = tokens(h);
    function allowed(target) {
      var tt = tokens(target);
      return !th.some(function (t) { return block.indexOf(t) >= 0 && tt.indexOf(t) < 0; });
    }
    var best = allowed(f) ? similarity(h, f) : 0;
    for (i = 0; i < syn.length; i++) {
      if (norm(syn[i]).length >= 6 && allowed(syn[i])) best = Math.max(best, similarity(h, syn[i]));
    }
    return best >= THRESHOLD ? Math.min(best, SCORE_FUZZY_MAX) : 0;
  }

  /* Greedy assignment by best score; no column is used twice. `taken` holds columns already used. */
  function suggestCore(headers, fields, taken) {
    var hs = cleanHeaders(headers), cand = [], mapping = {}, scores = {}, used = Object.create(null);
    Object.keys(taken || {}).forEach(function (k) { used[k] = 1; });
    fields.forEach(function (f, fi) {
      mapping[f] = null; scores[f] = 0;
      hs.forEach(function (h, hi) {
        if (!h || used[h]) return;
        var s = scorePair(f, h);
        if (s > 0) cand.push({ f: f, h: h, s: s, fi: fi, hi: hi });
      });
    });
    cand.sort(function (a, b) { return (b.s - a.s) || (a.fi - b.fi) || (a.hi - b.hi); });
    cand.forEach(function (c) {
      if (mapping[c.f] !== null || used[c.h]) return;
      mapping[c.f] = c.h; scores[c.f] = c.s; used[c.h] = 1;
    });
    return { mapping: mapping, scores: scores };
  }

  /* suggest(headers) -> {mapping: {field: column or null}, scores: {field: 0..1}} */
  function suggest(headers) { return suggestCore(headers, engine().COLUMNS.slice(), null); }

  /* True when some required field is not a column of the file under its template name. */
  function needsMapping(headers) {
    var hs = cleanHeaders(headers);
    return engine().COLUMNS.some(function (f) { return hs.indexOf(f) < 0; });
  }

  /* ---------------- checking a mapping ---------------- */
  function colValue(v) {
    if (v == null) return null;
    var s = String(v).trim();
    return s === "" ? null : s;
  }
  function listAnd(xs) {
    return xs.length === 2 ? "both " + xs[0] + " and " + xs[1] : xs.slice(0, -1).join(", ") + " and " + xs[xs.length - 1];
  }

  /* validate(mapping, headers) -> list of plain-language problems; [] when the mapping can be applied.
   * Without headers, only missing and repeated choices are checked. */
  function validate(mapping, headers) {
    var cols = engine().COLUMNS, problems = [], users = Object.create(null), order = [];
    var count = null, told = Object.create(null);
    mapping = mapping || {};
    if (headers) {
      count = Object.create(null);
      cleanHeaders(headers).forEach(function (h) { count[h] = (count[h] || 0) + 1; });
    }
    cols.forEach(function (f) {
      var c = colValue(mapping[f]);
      if (c === null) { problems.push("Choose a column for " + f + " (" + label(f) + ")."); return; }
      if (count && !count[c] && !told[c]) { problems.push("Column '" + c + "' is not in this file."); told[c] = 1; }
      else if (count && count[c] > 1 && !told[c]) {
        problems.push("Column '" + c + "' appears " + count[c] + " times in this file, so it is not clear which one to use. Rename the copies in the file.");
        told[c] = 1;
      }
      if (!users[c]) { users[c] = []; order.push(c); }
      users[c].push(f);
    });
    order.forEach(function (c) {
      if (users[c].length > 1) problems.push("Column '" + c + "' is used for " + listAnd(users[c]) + ".");
    });
    return problems;
  }

  /* ---------------- rewriting rows ---------------- */
  function csvCell(v) {
    var s = v == null ? "" : String(v);
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }

  /* Number of physical lines a parsed row spans (line breaks inside quoted values add lines),
   * counted the way LaghubittaEngine.parseCSV counts them. */
  function rowSpan(row) {
    var n = 1;
    (row || []).forEach(function (v) { var m = String(v == null ? "" : v).match(/\r\n|\r|\n/g); if (m) n += m.length; });
    return n;
  }

  /* apply(parsedRows, mapping, lines) -> CSV text with the template header (COLUMNS order).
   * parsedRows is LaghubittaEngine.parseCSV(text).rows, first row the header; lines (optional) is
   * parseCSV(text).lines. Values are copied as they are. Blank lines are added so that every row
   * starts on the same line number as in the source file, so the "Row N" in
   * LaghubittaEngine.validate messages points at the right line of the user's file (with lines
   * given, this also holds when the file has blank lines between rows). A row whose value count
   * differs from the header keeps that difference, so the validator still reports it. Throws when
   * the mapping has problems. */
  function apply(parsedRows, mapping, lines) {
    if (!parsedRows || !parsedRows.length) throw new Error("The file has no rows.");
    var cols = engine().COLUMNS, hs = cleanHeaders(parsedRows[0]);
    var problems = validate(mapping, hs);
    if (problems.length) throw new Error("The column mapping cannot be applied. " + problems.join(" "));
    var idx = cols.map(function (f) { return hs.indexOf(colValue(mapping[f])); });
    var useLines = Array.isArray(lines) && lines.length === parsedRows.length;
    var out = [], at = 1, src = 1;   /* next output line; source line where the next row starts */
    function put(vals, r) {
      var start = useLines && lines[r] > 0 ? lines[r] : src;
      while (at < start) { out.push(""); at++; }
      out.push(vals.map(csvCell).join(","));
      at += rowSpan(vals);
      src = start + rowSpan(parsedRows[r]);
    }
    put(cols, 0);
    for (var r = 1; r < parsedRows.length; r++) {
      var row = parsedRows[r] || [];
      var vals = idx.map(function (i) { return i < row.length ? row[i] : ""; });
      var delta = row.length - hs.length, k;
      if (delta > 0) for (k = 0; k < delta; k++) vals.push("");
      else if (delta < 0) vals.length = Math.max(2, vals.length + delta);
      put(vals, r);
    }
    return out.join("\n") + "\n";
  }

  /* ---------------- mapping file (addendum section 5) ---------------- */
  function toJSON(mapping) {
    var columns = {};
    mapping = mapping || {};
    engine().COLUMNS.forEach(function (f) { columns[f] = colValue(mapping[f]); });
    return JSON.stringify({ format: FORMAT, version: VERSION, columns: columns }, null, 2);
  }

  /* fromJSON(text, headers) -> {mapping, problems}. mapping is null when the file cannot be read
   * as a mapping file at all; otherwise it has every field (null where none is given) and
   * problems lists what still stops it from being applied to a file with these headers. */
  function fromJSON(text, headers) {
    if (typeof text !== "string" || text.trim() === "") {
      return { mapping: null, problems: ["The mapping file is empty."] };
    }
    var obj;
    try { obj = JSON.parse(text.charCodeAt(0) === 0xFEFF ? text.slice(1) : text); }
    catch (e) { return { mapping: null, problems: ["The mapping file is not valid JSON, so it cannot be read."] }; }
    if (!obj || typeof obj !== "object" || Array.isArray(obj) || obj.format !== FORMAT) {
      return { mapping: null, problems: ["This is not a CBSRM laghubitta mapping file. Its \"format\" entry must be \"" + FORMAT + "\"."] };
    }
    if (obj.version !== VERSION) {
      return { mapping: null, problems: [obj.version == null
        ? "The mapping file has no \"version\" entry; this page reads version " + VERSION + "."
        : "This mapping file is version " + JSON.stringify(obj.version) + "; this page reads version " + VERSION + "."] };
    }
    var cols = obj.columns;
    if (!cols || typeof cols !== "object" || Array.isArray(cols)) {
      return { mapping: null, problems: ["The mapping file has no \"columns\" section."] };
    }
    var fields = engine().COLUMNS, mapping = {}, problems = [];
    Object.keys(cols).forEach(function (k) {
      if (fields.indexOf(k) < 0) problems.push("The mapping file lists '" + k + "', which is not a template field. It was ignored.");
    });
    fields.forEach(function (f) {
      var v = Object.prototype.hasOwnProperty.call(cols, f) ? cols[f] : null;
      if (v != null && typeof v !== "string") {
        problems.push("The entry for " + f + " in the mapping file must be a column name in quotes.");
        v = null;
      }
      mapping[f] = colValue(v);
    });
    return { mapping: mapping, problems: problems.concat(validate(mapping, headers)) };
  }

  /* ---------------- mapping screen ---------------- */
  var FALLBACK = {
    bg: "#0A0C10", surface: "#0F141B", "surface-2": "#11161F", border: "#1C2330",
    "border-strong": "#283242", accent: "#3A78C9", text: "#E4E9F2", "text-strong": "#F2F5FA",
    "text-muted": "#8C99AE", "text-dim": "#828FA4", benign: "#4F9E84", watch: "#C9A24B",
    severe: "#C2545A", mono: "ui-monospace,Consolas,Menlo,monospace",
    sans: "ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif"
  };
  var CSS = [
    ".lbm{background:%surface%;border:1px solid %border-strong%;border-radius:8px;padding:18px 20px;",
    "margin:16px 0 0;color:%text%;font-family:%sans%;font-size:14px;line-height:1.5;min-width:0;}",
    ".lbm [hidden]{display:none !important;}",
    ".lbm-overline{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:%text-dim%;margin:0 0 4px;}",
    ".lbm-title{font-size:20px;font-weight:600;color:%text-strong%;margin:0 0 6px;}",
    ".lbm-title:focus{outline:none;}",
    ".lbm-file{font-family:%mono%;font-size:12px;color:%text-muted%;margin:0 0 10px;overflow-wrap:anywhere;}",
    ".lbm-file b{color:%text%;font-weight:600;}",
    ".lbm-intro{margin:0 0 14px;max-width:80ch;color:%text%;}",
    ".lbm-scroll{overflow-x:auto;border:1px solid %border%;border-radius:6px;background:%bg%;}",
    ".lbm-table{border-collapse:collapse;width:100%;}",
    ".lbm-table th,.lbm-table td{padding:7px 10px;border-bottom:1px solid %border%;text-align:left;",
    "vertical-align:middle;white-space:normal;position:static;}",
    ".lbm-table th{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:%text-dim%;",
    "font-weight:400;background:%surface-2%;}",
    ".lbm-table tbody tr:last-child td{border-bottom:0;}",
    ".lbm-table td{font-family:%sans%;font-size:13px;}",
    ".lbm-table td.lbm-c-field{font-family:%mono%;font-size:12.5px;color:%text-strong%;white-space:nowrap;}",
    ".lbm-table td.lbm-c-desc{color:%text-muted%;font-size:12.5px;}",
    ".lbm-sel{background:%surface-2%;color:%text%;border:1px solid %border-strong%;border-radius:5px;",
    "padding:5px 8px;font:12px %mono%;min-width:190px;max-width:100%;}",
    ".lbm-sel:focus-visible{outline:2px solid %accent%;outline-offset:2px;}",
    ".lbm-missing .lbm-sel{border-color:%severe%;}",
    ".lbm-ind{display:inline-block;font:10.5px/1 %mono%;letter-spacing:.06em;text-transform:uppercase;",
    "padding:3px 6px;border-radius:3px;border:1px solid currentColor;white-space:nowrap;}",
    ".lbm-ind-auto{color:%benign%;}.lbm-ind-chosen{color:%accent%;}.lbm-ind-missing{color:%severe%;}",
    ".lbm-sv{display:inline-block;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;",
    "vertical-align:bottom;font-family:%mono%;font-size:12px;color:%text-muted%;}",
    ".lbm-sv.lbm-none{color:%text-dim%;font-style:italic;font-family:%sans%;}",
    ".lbm-unused{font-size:12px;color:%text-dim%;margin:8px 0 0;overflow-wrap:anywhere;}",
    ".lbm-problems,.lbm-msg{margin:14px 0 0;padding:10px 14px;border:1px solid %border-strong%;",
    "border-left:3px solid %watch%;border-radius:6px;background:%surface-2%;font-size:13px;}",
    ".lbm-problems b,.lbm-msg b{color:%watch%;}",
    ".lbm-problems ul,.lbm-msg ul{margin:6px 0 0;padding-left:20px;}",
    ".lbm-problems li,.lbm-msg li{margin:2px 0;overflow-wrap:anywhere;}",
    ".lbm-problems.lbm-ok,.lbm-msg.lbm-ok{border-left-color:%benign%;}",
    ".lbm-problems.lbm-ok b,.lbm-msg.lbm-ok b{color:%benign%;}",
    ".lbm-msg.lbm-err{border-left-color:%severe%;}.lbm-msg.lbm-err b{color:%severe%;}",
    ".lbm-actions{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:16px;}",
    ".lbm-actions .lbm-spacer{flex:1 1 auto;}",
    ".lbm .btn:disabled{opacity:.5;cursor:not-allowed;}",
    ".lbm .btn-primary:disabled:hover{background:%accent%;border-color:%accent%;}",
    ".lbm-note{font-size:12px;color:%text-dim%;margin:10px 0 0;}",
    "@media (max-width:640px){",
    ".lbm{padding:14px 12px;}",
    ".lbm-scroll{overflow-x:visible;border:0;background:transparent;}",
    ".lbm-table thead{display:none;}",
    ".lbm-table,.lbm-table tbody{display:block;}",
    ".lbm-table tr{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 10px;padding:10px 12px;",
    "margin-bottom:8px;border:1px solid %border%;border-radius:6px;background:%bg%;}",
    ".lbm-table td{display:block;padding:0;border:0;min-width:0;}",
    ".lbm-table td.lbm-c-field{grid-column:1;grid-row:1;white-space:normal;overflow-wrap:anywhere;}",
    ".lbm-table td.lbm-c-ind{grid-column:2;grid-row:1;text-align:right;}",
    ".lbm-table td.lbm-c-desc{grid-column:1 / -1;grid-row:2;}",
    ".lbm-table td.lbm-c-sel{grid-column:1 / -1;grid-row:3;}",
    ".lbm-table td.lbm-c-sample{grid-column:1 / -1;grid-row:4;}",
    ".lbm-table td.lbm-c-sample::before{content:\"First value: \";color:%text-dim%;font-size:12px;}",
    ".lbm-sel{width:100%;min-width:0;}",
    ".lbm-sv{max-width:100%;}",
    ".lbm-actions .btn{flex:1 1 auto;}",
    "}"
  ].join("\n").replace(/%([a-z0-9-]+)%/g, function (m, n) { return "var(--" + n + "," + FALLBACK[n] + ")"; });

  function injectStyle(doc) {
    if (doc.getElementById("lbm-style")) return;
    var s = doc.createElement("style");
    s.id = "lbm-style";
    s.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(s);
  }

  /* render(container, opts) draws the mapping screen into container and returns a controller
   * {element, getMapping(), setMapping(mapping), getProblems(), focus(), destroy()}.
   * opts: {fileName, headers, sampleRows (first 3 data rows), mapping (optional initial),
   *        onApply(mapping), onCancel()}. */
  function render(container, opts) {
    if (!container || typeof container.appendChild !== "function") throw new Error("render needs a container element.");
    opts = opts || {};
    var doc = container.ownerDocument || root.document;
    var cols = engine().COLUMNS;
    injectStyle(doc);

    var hs = cleanHeaders(opts.headers), idxOf = Object.create(null), options = [];
    hs.forEach(function (x, i) { if (x !== "" && !(x in idxOf)) { idxOf[x] = i; options.push(x); } });
    var samples = (opts.sampleRows || []).slice(0, 3);
    var state = {}, problems = [], notes = [];

    /* initial choice: a given mapping first, the rest suggested from the remaining columns */
    var taken = Object.create(null), rest = [];
    cols.forEach(function (f) {
      var c = opts.mapping ? colValue(opts.mapping[f]) : null;
      if (c !== null && c in idxOf) { state[f] = { col: c, how: "chosen", score: 0 }; taken[c] = 1; }
      else {
        if (c !== null) notes.push("Column '" + c + "' (for " + f + ") is not in this file.");
        rest.push(f);
      }
    });
    var sg = suggestCore(hs, rest, taken);
    rest.forEach(function (f) {
      state[f] = { col: sg.mapping[f], how: sg.mapping[f] ? "auto" : "chosen", score: sg.scores[f] };
    });

    function h(tag, attrs, kids) {
      var n = doc.createElement(tag);
      Object.keys(attrs || {}).forEach(function (k) {
        var v = attrs[k];
        if (v == null || v === false) return;
        if (k === "text") n.textContent = v;
        else if (k === "className") n.className = v;
        else if (k === "hidden" || k === "disabled") n[k] = true;
        else n.setAttribute(k, v === true ? "" : String(v));
      });
      (kids || []).forEach(function (c) {
        if (c != null) n.appendChild(typeof c === "string" ? doc.createTextNode(c) : c);
      });
      return n;
    }
    function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }

    var nCols = options.length;
    var title = h("h2", { className: "lbm-title", id: "lbm-title", tabindex: "-1", text: "Match your columns" });
    var fileLine = h("p", { className: "lbm-file", id: "lbm-file-name" }, [
      "File: ", h("b", { text: opts.fileName || "your file" }),
      " \u00b7 " + nCols + " column" + (nCols === 1 ? "" : "s") +
      (samples.length ? " \u00b7 values shown are from the first data row" : "")
    ]);
    var intro = h("p", { className: "lbm-intro", id: "lbm-intro",
      text: "This file's columns do not match the template. Match each required field to a column in your file. Nothing leaves this browser." });

    var tbody = h("tbody", { id: "lbm-body" });
    var rowEls = {};
    cols.forEach(function (f) {
      var sel = h("select", { className: "lbm-sel", id: "lbm-sel-" + f, "aria-label": "Column for " + f + " (" + label(f) + ")" },
        [h("option", { value: "", text: "- not mapped -" })].concat(options.map(function (o) {
          return h("option", { value: o, text: o });
        })));
      var ind = h("span", { className: "lbm-ind", id: "lbm-ind-" + f });
      var sv = h("span", { className: "lbm-sv", id: "lbm-sample-" + f });
      var tr = h("tr", { id: "lbm-row-" + f }, [
        h("td", { className: "lbm-c-field" }, [f]),
        h("td", { className: "lbm-c-desc", text: desc(f) }),
        h("td", { className: "lbm-c-sel" }, [sel]),
        h("td", { className: "lbm-c-ind" }, [ind]),
        h("td", { className: "lbm-c-sample" }, [sv])
      ]);
      rowEls[f] = { tr: tr, sel: sel, ind: ind, sv: sv };
      tbody.appendChild(tr);
    });
    var table = h("table", { className: "lbm-table", id: "lbm-table", "aria-label": "Required fields and the column chosen for each" }, [
      h("thead", {}, [h("tr", {}, [
        h("th", { scope: "col", text: "Field" }), h("th", { scope: "col", text: "What it holds" }),
        h("th", { scope: "col", text: "Column in your file" }), h("th", { scope: "col", text: "Match" }),
        h("th", { scope: "col", text: "First value" })
      ])]),
      tbody
    ]);
    var unused = h("p", { className: "lbm-unused", id: "lbm-unused" });
    var probBox = h("div", { className: "lbm-problems", id: "lbm-problems", role: "status", "aria-live": "polite" });
    var msgBox = h("div", { className: "lbm-msg", id: "lbm-msg", hidden: true });
    var btnApply = h("button", { type: "button", className: "btn btn-primary", id: "lbm-apply", text: "Apply mapping" });
    var btnDown = h("button", { type: "button", className: "btn", id: "lbm-download", text: "Download mapping (JSON)" });
    var btnLoad = h("button", { type: "button", className: "btn", id: "lbm-load", text: "Load mapping" });
    var fileIn = h("input", { type: "file", id: "lbm-file", accept: ".json,application/json", hidden: true,
      "aria-label": "Mapping file (JSON)" });
    var btnCancel = h("button", { type: "button", className: "btn", id: "lbm-cancel", text: "Cancel" });
    var el = h("section", { className: "lbm", id: "lbm-root", "aria-labelledby": "lbm-title" }, [
      h("p", { className: "lbm-overline", text: "Column mapping" }), title, fileLine, intro,
      h("div", { className: "lbm-scroll" }, [table]), unused, probBox, msgBox,
      h("div", { className: "lbm-actions" }, [btnApply, btnDown, btnLoad, fileIn, h("span", { className: "lbm-spacer" }), btnCancel]),
      h("p", { className: "lbm-note", text: "The mapping is used only in this browser. Save it with Download mapping and load it next time to skip this step." })
    ]);

    function mapping() {
      var m = {};
      cols.forEach(function (f) { m[f] = state[f].col || null; });
      return m;
    }
    function drawRow(f) {
      var s = state[f], r = rowEls[f], i = s.col ? idxOf[s.col] : -1;
      r.sel.value = s.col || "";
      var kind = !s.col ? "missing" : s.how === "auto" ? "auto" : "chosen";
      r.ind.className = "lbm-ind lbm-ind-" + kind;
      r.ind.textContent = kind === "auto" ? "auto-matched" : kind;
      if (kind === "auto") r.ind.title = "Suggested from the column name (similarity " + s.score.toFixed(2) + ")";
      else r.ind.removeAttribute("title");
      r.tr.className = kind === "missing" ? "lbm-missing" : "";
      var first = i >= 0 && samples.length ? samples[0][i] : null;
      var empty = first == null || String(first).trim() === "";
      r.sv.className = "lbm-sv" + (empty ? " lbm-none" : "");
      r.sv.textContent = !s.col ? "-" : !samples.length ? "no data rows" : empty ? "(empty)" : String(first);
      if (i >= 0 && samples.length) {
        r.sv.title = "First values: " + samples.map(function (row) { return row[i] == null ? "" : row[i]; }).join(" | ");
      } else r.sv.removeAttribute("title");
    }
    function drawProblems() {
      var m = mapping();
      problems = validate(m, hs);
      clear(probBox);
      if (problems.length) {
        probBox.className = "lbm-problems";
        probBox.appendChild(h("b", { text: "Fix " + (problems.length === 1 ? "this" : "these") + " before applying:" }));
        probBox.appendChild(h("ul", { id: "lbm-problem-list" }, problems.map(function (p) { return h("li", { text: p }); })));
      } else {
        probBox.className = "lbm-problems lbm-ok";
        probBox.appendChild(h("b", { text: "Ready." }));
        probBox.appendChild(doc.createTextNode(" All " + cols.length + " fields are matched to different columns."));
      }
      btnApply.disabled = problems.length > 0;
      var usedCols = Object.create(null);
      cols.forEach(function (f) { if (m[f]) usedCols[m[f]] = 1; });
      var left = options.filter(function (o) { return !usedCols[o]; });
      unused.textContent = left.length ? "Columns in your file not used: " + left.join(", ") + "." : "";
      unused.hidden = !left.length;
    }
    function drawAll() { cols.forEach(drawRow); drawProblems(); }
    function showMsg(kind, head, items) {
      clear(msgBox);
      msgBox.className = "lbm-msg" + (kind ? " lbm-" + kind : "");
      msgBox.appendChild(h("b", { text: head }));
      if (items && items.length) msgBox.appendChild(h("ul", {}, items.map(function (p) { return h("li", { text: p }); })));
      msgBox.hidden = false;
    }
    function setMapping(m, how) {
      cols.forEach(function (f) {
        var c = colValue(m && m[f]);
        state[f] = { col: c !== null && c in idxOf ? c : null, how: how || "chosen", score: 0 };
      });
      drawAll();
    }

    tbody.addEventListener("change", function (e) {
      var t = e.target;
      if (!t || !t.id || t.id.indexOf("lbm-sel-") !== 0) return;
      var f = t.id.slice(8);
      if (!state[f]) return;
      state[f] = { col: t.value || null, how: "chosen", score: 0 };
      drawRow(f); drawProblems();
    });
    btnApply.addEventListener("click", function () {
      if (problems.length) return;
      if (typeof opts.onApply === "function") opts.onApply(mapping());
    });
    btnCancel.addEventListener("click", function () {
      if (typeof opts.onCancel === "function") opts.onCancel();
    });
    btnDown.addEventListener("click", function () {
      var blob = new Blob([toJSON(mapping()) + "\n"], { type: "application/json" });
      var url = URL.createObjectURL(blob), a = doc.createElement("a");
      a.href = url; a.download = "laghubitta_mapping.json"; a.hidden = true;
      doc.body.appendChild(a); a.click();
      setTimeout(function () { URL.revokeObjectURL(url); if (a.parentNode) a.parentNode.removeChild(a); }, 0);
    });
    btnLoad.addEventListener("click", function () { fileIn.click(); });
    fileIn.addEventListener("change", function () {
      var file = fileIn.files && fileIn.files[0];
      fileIn.value = "";
      if (!file) return;
      if (file.size > 1000000) { showMsg("err", "This file is too large to be a mapping file.", []); return; }
      var rd = new FileReader();
      rd.onerror = function () { showMsg("err", "The mapping file could not be read by the browser.", []); };
      rd.onload = function () {
        var res = fromJSON(String(rd.result), hs);
        if (!res.mapping) { showMsg("err", "This mapping file could not be used. Nothing was changed.", res.problems); return; }
        setMapping(res.mapping, "chosen");
        var live = Object.create(null);
        problems.forEach(function (p) { live[p] = 1; });
        var extra = res.problems.filter(function (p) { return !live[p]; });
        showMsg(extra.length ? "warn" : "ok", "Loaded mapping from " + file.name + "." +
          (extra.length ? " Some entries could not be used:" : ""), extra);
      };
      rd.readAsText(file);
    });

    clear(container);
    container.appendChild(el);
    drawAll();
    if (notes.length) showMsg("warn", "Some columns in the saved mapping are not in this file:", notes);

    return {
      element: el,
      getMapping: mapping,
      setMapping: function (m) { setMapping(m, "chosen"); },
      getProblems: function () { return problems.slice(); },
      focus: function () { title.focus(); },
      destroy: function () { if (el.parentNode) el.parentNode.removeChild(el); }
    };
  }

  return {
    FORMAT: FORMAT, VERSION: VERSION, THRESHOLD: THRESHOLD, FIELDS: FIELDS, SYNONYMS: SYNONYMS,
    suggest: suggest, needsMapping: needsMapping, validate: validate, apply: apply,
    toJSON: toJSON, fromJSON: fromJSON, render: render,
    similarity: similarity, normalise: norm
  };
});
