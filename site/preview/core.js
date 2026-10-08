(function (root) {
  'use strict';
  const LEVELS = ['province','district','municipality','branch','centre','portfolio','segment'];
  function validate(data) {
    if (!data || !Array.isArray(data.nodes) || !Array.isArray(data.records)) throw Error('Invalid dataset');
    const nodes = new Map();
    for (const n of data.nodes) {
      if (!n || typeof n.id !== 'string' || !n.id || nodes.has(n.id)) throw Error('Duplicate or missing geography code');
      if (!LEVELS.includes(n.level) || typeof n.label !== 'string') throw Error('Invalid geography level/label');
      nodes.set(n.id, n);
    }
    for (const n of nodes.values()) {
      const i = LEVELS.indexOf(n.level), p = nodes.get(n.parent);
      if (i === 0 ? n.parent != null : !p || p.level !== LEVELS[i-1]) throw Error('Orphan or conflicting parent chain');
    }
    const ids = new Set();
    for (const r of data.records) {
      if (!r || typeof r.id !== 'string' || ids.has(r.id)) throw Error('Duplicate record');
      ids.add(r.id);
      if (!Number.isFinite(r.exposure) || r.exposure < 0 || !Number.isFinite(r.par30Amount) || r.par30Amount < 0 || r.par30Amount > r.exposure) throw Error('Invalid exposure/PAR numerator');
      if (r.score != null && (!Number.isFinite(r.score) || r.score < 0 || r.score > 100)) throw Error('Invalid risk score');
      if (typeof r.currency !== 'string' || !/^[A-Z]{3}$/.test(r.currency) || !/^\d{4}-\d{2}-\d{2}$/.test(r.asOf)) throw Error('Invalid currency/date');
      const date = new Date(r.asOf + 'T00:00:00Z');
      if (!Number.isFinite(+date) || date.toISOString().slice(0,10) !== r.asOf) throw Error('Invalid calendar date');
      const leaf = nodes.get(r.nodeId);
      if (leaf && leaf.level !== 'segment') throw Error('Records must use segment leaves');
      if (leaf && lineage(nodes, leaf.id).find(n => n.level === 'branch').id !== r.branchId) throw Error('Conflicting record branch');
      if (typeof r.branchId !== 'string' || !r.branchId) throw Error('Missing branch code');
    }
    return nodes;
  }
  function lineage(nodes, id) {
    const out = []; let node = nodes.get(id);
    while (node) { out.unshift(node); node = nodes.get(node.parent); }
    return out;
  }
  function band(score) {
    if (score == null) return 'Unknown';
    return score < 25 ? 'Normal' : score < 50 ? 'Watch' : score < 75 ? 'Elevated' : 'Critical';
  }
  // This allow-list is an adapter fixture, NOT server authorization.
  // Production must send already-filtered current-session aggregates.
  function aggregate(data, selected, allowedBranches, asOf) {
    const nodes = validate(data);
    if (!(allowedBranches instanceof Set)) throw Error('Explicit branch scope required');
    if (selected !== null && selected !== 'unmatched' && !nodes.has(selected)) throw Error('Unknown selection');
    const records = data.records.filter(r => allowedBranches.has(r.branchId) && r.asOf === asOf && (
      selected === null || (selected === 'unmatched' ? !nodes.has(r.nodeId) : lineage(nodes,r.nodeId).some(n => n.id === selected))
    ));
    const currencies = new Set(records.map(r => r.currency));
    if (currencies.size > 1) throw Error('Mixed currencies: choose one currency; no conversion performed');
    const exposure = records.reduce((a,r) => a+r.exposure,0);
    const par30Amount = records.reduce((a,r) => a+r.par30Amount,0);
    const scored = records.filter(r => r.score != null);
    const scoredExposure = scored.reduce((a,r) => a+r.exposure,0);
    const score = scoredExposure > 0 ? scored.reduce((a,r) => a+r.score*r.exposure,0)/scoredExposure : null;
    return { exposure, par30Amount, par30: exposure > 0 ? par30Amount/exposure : null,
      score, status: band(score), scoredExposure, coverage: exposure > 0 ? scoredExposure/exposure : null,
      partial: scored.length < records.length, currency: [...currencies][0] || null, asOf,
      count: records.length, unmatched: records.filter(r => !nodes.has(r.nodeId)).length };
  }
  function children(data, selected) {
    const nodes = validate(data);
    if (selected === 'unmatched') return [];
    if (selected !== null && !nodes.has(selected)) throw Error('Unknown selection');
    return [...nodes.values()].filter(n => (n.parent == null ? null : n.parent) === selected);
  }
  function back(data, selected) { return selected === 'unmatched' ? null : (validate(data).get(selected)?.parent || null); }
  function geometry(data, geojson, meta) {
    const nodes = validate(data);
    for (const key of ['source','version','date','license','redistribution','codeSchema','joinCoverage']) {
      if (!meta || typeof meta[key] !== 'string' || !meta[key].trim()) throw Error('Missing geometry provenance: '+key);
    }
    if (meta.crs !== 'EPSG:4326' || geojson?.type !== 'FeatureCollection' || !Array.isArray(geojson.features)) throw Error('Unsupported geometry/CRS');
    const seen = new Set(), shapes = [], unmatched = [];
    for (const f of geojson.features) {
      const code = f?.properties?.code;
      if (typeof code !== 'string' || seen.has(code)) throw Error('Duplicate/missing boundary code');
      seen.add(code);
      const g = f.geometry;
      if (!g || !['Polygon','MultiPolygon'].includes(g.type)) throw Error('Unsupported boundary geometry');
      const polygons = g.type === 'Polygon' ? [g.coordinates] : g.coordinates;
      if (!Array.isArray(polygons) || !polygons.length) throw Error('Empty geometry');
      for (const poly of polygons) {
        if (!Array.isArray(poly) || !poly.length) throw Error('Empty polygon');
        for (const ring of poly) {
          if (!Array.isArray(ring) || ring.length < 4) throw Error('Invalid boundary ring');
          for (const pt of ring) if (!Array.isArray(pt) || pt.length < 2 || !Number.isFinite(pt[0]) || !Number.isFinite(pt[1]) || Math.abs(pt[0])>180 || Math.abs(pt[1])>90) throw Error('Invalid boundary coordinate');
          if (ring[0][0] !== ring.at(-1)[0] || ring[0][1] !== ring.at(-1)[1]) throw Error('Unclosed boundary ring');
        }
      }
      if (!nodes.has(code)) unmatched.push(code); else shapes.push({code, polygons});
    }
    return {shapes, unmatched, provenance: {...meta}, verification:'Supplied metadata only; controller review required'};
  }
  function svgPath(polygons, project) {
    return polygons.map(poly => poly.map(ring => ring.map((pt,i) => { const p = project(pt); return (i?'L':'M')+p[0]+','+p[1]; }).join(' ')+' Z').join(' ')).join(' ');
  }
  const api = {LEVELS, validate, lineage, aggregate, children, back, band, geometry, svgPath};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.CBSRMMap = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
