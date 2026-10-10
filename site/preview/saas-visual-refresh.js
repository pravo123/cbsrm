(function () {
  "use strict";
  // Read the theme before the render-blocking stylesheet; store preference only.
  var THEME_KEY = "cbsrm.preview.theme", theme = "dark";
  try {
    var saved = window.localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") theme = saved;
  } catch (_) { /* Storage can be disabled; the controls still work. */ }
  function applyTheme(choice, persist) {
    theme = choice === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", theme);
    document.querySelectorAll("[data-theme-choice]").forEach(function (button) { button.setAttribute("aria-pressed", String(button.dataset.themeChoice === theme)); });
    if (persist) {
      try { window.localStorage.setItem(THEME_KEY, theme); } catch (_) { /* No financial/session data stored. */ }
    }
  }
  applyTheme(theme, false);
  function mount() {
  // UI illustration only. These figures are synthetic, not institution data.
  var branches = [
    { id: "west", label: "West", exposure: 60, overdue: 3, x: 127, y: 114, color: "#e3b75e", series: [6.3, 6.0, 5.8, 5.4, 5.2, 5.0] },
    { id: "central", label: "Central", exposure: 40, overdue: 1.2, x: 279, y: 168, color: "#4bc18c", series: [4.2, 4.0, 3.7, 3.3, 3.1, 3.0] },
    { id: "east", label: "East", exposure: 20, overdue: 1.8, x: 423, y: 213, color: "#cf7887", series: [10.4, 10.2, 9.8, 9.5, 9.3, 9.0] }
  ];
  var positions = { A: [145, 120], B: [411, 84], C: [424, 269], D: [153, 276] };
  var edges = [{ from: "A", to: "B", value: 40 }, { from: "B", to: "C", value: 18 }, { from: "C", to: "A", value: 20 }, { from: "A", to: "D", value: 12 }, { from: "D", to: "C", value: 9 }];
  var months = ["Mar", "Apr", "May", "Jun", "Jul", "Aug"];
  var NS = "http://www.w3.org/2000/svg";
  function svg(tag, attributes, text) {
    var node = document.createElementNS(NS, tag);
    Object.keys(attributes || {}).forEach(function (key) { node.setAttribute(key, String(attributes[key])); });
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function set(id, text) { document.getElementById(id).textContent = text; }
  function amount(id, value) {
    var target = document.getElementById(id), unit = document.createElement("small");
    unit.textContent = "demo units";
    target.replaceChildren(document.createTextNode(value.toFixed(1) + " "), unit);
  }
  function total(rows, field) { return rows.reduce(function (sum, row) { return sum + row[field]; }, 0); }
  function portfolio(id) {
    var rows = id === "all" ? branches : branches.filter(function (row) { return row.id === id; });
    var exposure = total(rows, "exposure"), overdue = total(rows, "overdue");
    var par = 100 * overdue / exposure;
    amount("exposure-value", exposure);
    set("par-value", par.toFixed(2) + "%");
    amount("overdue-value", overdue);
    set("scope-value", id === "all" ? "3 demo branches" : rows[0].label + " · demo branch");
    set("figure-explanation", overdue.toFixed(1) + " overdue units divided by " + exposure.toFixed(1) + " outstanding units gives " + par.toFixed(2) + "%. Branch percentages are weighted by exposure, not averaged.");
    var highest = rows.reduce(function (a, b) { return a.overdue / a.exposure > b.overdue / b.exposure ? a : b; });
    set("review-text", highest.label + " has PAR30 of " + (100 * highest.overdue / highest.exposure).toFixed(2) + "% in this selected sample. Inspect underlying records before proposing an action; this is not a credit decision.");
    document.querySelectorAll("[data-branch]").forEach(function (button) { button.setAttribute("aria-pressed", String(button.dataset.branch === id)); });
    var group = document.getElementById("map-markers");
    group.replaceChildren();
    branches.forEach(function (branch) {
      var selected = id === "all" || id === branch.id;
      var marker = svg("g", { opacity: selected ? 1 : .3 });
      marker.appendChild(svg("circle", { cx: branch.x, cy: branch.y, r: 24, stroke: branch.color, "class": "map-ring" }));
      marker.appendChild(svg("circle", { cx: branch.x, cy: branch.y, r: 11, fill: branch.color, "class": "map-point" }));
      marker.appendChild(svg("text", { x: branch.x, y: branch.y - 33, "text-anchor": "middle", "class": "map-label" }, branch.label + " · demo"));
      group.appendChild(marker);
    });
    var chart = document.getElementById("trend-chart");
    chart.querySelectorAll("g").forEach(function (node) { node.remove(); });
    var layer = svg("g");
    [0, 3, 6, 9, 12].forEach(function (value) {
      var y = 240 - value * 16;
      layer.appendChild(svg("line", { x1: 45, x2: 490, y1: y, y2: y, stroke: "#d8dfe3", "stroke-dasharray": value === 0 ? "0" : "3 4" }));
      layer.appendChild(svg("text", { x: 31, y: y + 4, "text-anchor": "end", "class": "chart-label" }, value + "%"));
    });
    var values = months.map(function (_, index) { return rows.reduce(function (sum, branch) { return sum + branch.series[index] * branch.exposure; }, 0) / exposure; });
    var points = values.map(function (value, index) { return [50 + index * 86, 240 - value * 16]; });
    layer.appendChild(svg("polygon", { points: [[50, 240]].concat(points, [[480, 240]]).map(function (point) { return point.join(","); }).join(" "), fill: "#dbece5", opacity: .7 }));
    layer.appendChild(svg("polyline", { points: points.map(function (point) { return point.join(","); }).join(" "), stroke: "#14658e", "stroke-width": 3, fill: "none", "stroke-linejoin": "round" }));
    points.forEach(function (point, index) {
      var dot = svg("circle", { cx: point[0], cy: point[1], r: 4, fill: "#14658e", stroke: "white", "stroke-width": 2 });
      dot.appendChild(svg("title", {}, months[index] + " 2026 · synthetic PAR30 " + values[index].toFixed(2) + "%"));
      layer.appendChild(dot);
      layer.appendChild(svg("text", { x: point[0], y: 263, "text-anchor": "middle", "class": "chart-label" }, months[index]));
    });
    layer.appendChild(svg("text", { x: 475, y: points[5][1] - 14, "text-anchor": "end", fill: "#14658e", "font-size": 15, "font-weight": 650 }, par.toFixed(2) + "%"));
    chart.appendChild(layer);
  }
  function network(id) {
    var chart = document.getElementById("exposure-network");
    chart.querySelectorAll("g,defs").forEach(function (node) { node.remove(); });
    var defs = svg("defs"), marker = svg("marker", { id: "edge-arrow", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" });
    marker.appendChild(svg("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#a4bec9" }));
    defs.appendChild(marker); chart.appendChild(defs);
    var layer = svg("g");
    edges.forEach(function (edge) {
      var from = positions[edge.from], to = positions[edge.to];
      var dx = to[0] - from[0], dy = to[1] - from[1], length = Math.sqrt(dx * dx + dy * dy);
      var active = edge.from === id || edge.to === id;
      layer.appendChild(svg("line", { x1: from[0] + dx / length * 29, y1: from[1] + dy / length * 29, x2: to[0] - dx / length * 34, y2: to[1] - dy / length * 34, "stroke-width": 1 + edge.value / 13, "marker-end": "url(#edge-arrow)", "class": "network-edge " + (active ? "active" : "dim") }));
      layer.appendChild(svg("text", { x: (from[0] + to[0]) / 2 + 9, y: (from[1] + to[1]) / 2 - 9, "class": "network-weight", opacity: active ? 1 : .45 }, edge.value + " units"));
    });
    Object.keys(positions).forEach(function (key) {
      var point = positions[key];
      layer.appendChild(svg("circle", { cx: point[0], cy: point[1], r: 27, "class": "network-node" + (key === id ? " selected" : "") }));
      layer.appendChild(svg("text", { x: point[0], y: point[1] + 5, "text-anchor": "middle", fill: key === id ? "#e3b75e" : "#cae6ef", "font-size": 16, "font-weight": 600 }, key));
      layer.appendChild(svg("text", { x: point[0], y: point[1] + 48, "text-anchor": "middle", "class": "network-label" }, "Demo " + key));
    });
    chart.appendChild(layer);
    document.querySelectorAll("[data-node]").forEach(function (button) { button.setAttribute("aria-pressed", String(button.dataset.node === id)); });
    set("network-selection", "Demo " + id);
    set("network-out", edges.filter(function (edge) { return edge.from === id; }).reduce(function (sum, edge) { return sum + edge.value; }, 0) + " units");
    set("network-in", edges.filter(function (edge) { return edge.to === id; }).reduce(function (sum, edge) { return sum + edge.value; }, 0) + " units");
  }
  document.querySelectorAll("[data-branch]").forEach(function (button) { button.addEventListener("click", function () { portfolio(button.dataset.branch); }); });
  document.querySelectorAll("[data-node]").forEach(function (button) { button.addEventListener("click", function () { network(button.dataset.node); }); });
  portfolio("all");
  network("A");
  document.querySelectorAll("[data-theme-choice]").forEach(function (button) { button.addEventListener("click", function () { applyTheme(button.dataset.themeChoice, true); }); });
  applyTheme(theme, false);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount, { once: true });
  else mount();
})();
