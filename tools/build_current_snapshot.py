#!/usr/bin/env python3
"""
build_current_snapshot.py — generate the site's "Current Conditions" snapshot
from LIVE data, for cbsrm.wavervanir.com.

Writes ``site/current.json``: the latest available reading of each public
systemic-stress lens CBSRM reproduces, every value carrying its OWN true
``as_of`` date and source. Designed to run on a daily schedule (e.g. a GitHub
Action) so the terminal always shows current readings.

Honesty contract (this ships on a sold site):
* Each reading shows the REAL date the data provider last published — never
  today's date faked. Stress indices publish with a lag; that is expected and
  shown plainly.
* A source that cannot be fetched (no key, network, provider error) is recorded
  with ``status: "unavailable"`` and a reason — never silently dropped or made up.
* The snapshot carries an ``output_sha256`` (same hashing the audit chain uses),
  so a Current Conditions reading is content-addressed like everything else.

Freshness: the run clears ``.cbsrm_cache`` first so cached responses never mask
new data. A CI runner has no cache, so it always fetches live regardless.

Data sources:
* ECB-CISS (US / EA / UK) — ECB SDMX, **no key required**.
* STLFSI4, yield-curve recession probability, 4-state macro regime, Sahm rule,
  HY credit-spread regime — FRED, **needs ``FRED_API_KEY``** (free key, read
  from the environment or a local gitignored ``.env.local``).
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import io
import json
import os
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SITE = _REPO / "site"
_CACHE = _REPO / ".cbsrm_cache"


def _load_env_local() -> None:
    """Load ``FRED_API_KEY`` from a gitignored ``.env.local`` if present and not
    already in the environment. Keeps the key out of chat and out of git."""
    if os.environ.get("FRED_API_KEY"):
        return
    env_file = _REPO / ".env.local"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _run_json(args: list[str]) -> dict | None:
    """Invoke the cbsrm CLI in-process and parse its JSON stdout, or None."""
    from cbsrm.cli import main

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            main(args)
    except SystemExit:
        pass
    except Exception:
        return None
    out = buf.getvalue().strip()
    if not out.startswith("{"):
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def _start(years: int) -> str:
    """A start date ``years`` back, for indicators that take a window."""
    today = _dt.date.today()
    return today.replace(year=today.year - years).isoformat()


def _as_date(iso: str | None) -> str | None:
    """Normalise an ISO timestamp to a plain ``YYYY-MM-DD`` date string."""
    if not iso or not isinstance(iso, str):
        return None
    return iso[:10]


# Each lens, with the EXACT field names each command returns (verified against
# live output). Tuple: key, label, lens, cli args, value_field, state_field,
# fmt, unit, source.  value_field=None → a state-only card.
_LENSES = [
    ("ECB-CISS-US", "ECB CISS — United States", "System stress",
     ["ecb-ciss", "--variant", "US"], "value", None, "ratio", "index 0–1", "ECB SDMX"),
    ("ECB-CISS-EA", "ECB CISS — Euro Area", "System stress",
     ["ecb-ciss", "--variant", "EA"], "value", None, "ratio", "index 0–1", "ECB SDMX"),
    ("ECB-CISS-UK", "ECB CISS — United Kingdom", "System stress",
     ["ecb-ciss", "--variant", "UK"], "value", None, "ratio", "index 0–1", "ECB SDMX"),
    ("STLFSI4", "St. Louis Fed Financial Stress", "System stress",
     ["latest", "STLFSI4"], "value", None, "signed", "z · 0 = normal", "FRED"),
    ("YIELD-CURVE", "Recession probability · 12m", "Macro regime",
     ["yield-curve", "--start", _start(3)], "latest_recession_prob_12mo", None,
     "probability", "Estrella–Mishkin", "FRED"),
    ("MACRO-REGIME", "Macro regime · 4-state", "Macro regime",
     ["macro-regime", "--start", _start(3)], None, "latest_regime",
     "state", "composite", "FRED"),
    ("SAHM", "Sahm Rule recession signal", "Macro regime",
     ["sahm-rule", "--start", _start(3)], "value", "classification",
     "pp2", "pp · trigger 0.50", "FRED"),
    ("CREDIT-SPREAD", "HY credit-spread · OAS", "Tail / credit",
     ["credit-spread", "--start", _start(3)], "value", "regime",
     "bps", "bps", "FRED"),
]


def _reading(spec) -> dict:
    key, label, lens, args, vfield, sfield, fmt, unit, source = spec
    base = {"id": key, "label": label, "lens": lens, "unit": unit, "source": source}
    data = _run_json(args)
    if data is None:
        return {**base, "status": "unavailable",
                "reason": "no data (missing key, provider error, or non-JSON output)"}

    as_of = _as_date(data.get("as_of") or data.get("date") or data.get("observation_date"))
    value = data.get(vfield) if vfield else None
    state = data.get(sfield) if sfield else None

    out = {**base, "status": "ok", "as_of": as_of, "fmt": fmt}
    if isinstance(value, (int, float)):
        out["value"] = round(float(value), 6)
    if isinstance(state, str):
        out["state"] = state
    if isinstance(data.get("interpretation"), str):
        out["interpretation"] = data["interpretation"]
    if out.get("value") is None and out.get("state") is None:
        out["status"] = "unavailable"
        out["reason"] = "fetched but no recognised value/state field"
        out["raw_keys"] = sorted(data.keys())
    return out


def build_snapshot(*, generated_at_utc: str | None = None) -> dict:
    from cbsrm.reporting.manifest import sha256_jsonable

    readings = [_reading(s) for s in _LENSES]
    ok = [r for r in readings if r.get("status") == "ok"]
    # Content address over the readings only (not the wall-clock stamp), so the
    # hash changes iff the data changes.
    output_sha256 = sha256_jsonable(readings)
    return {
        "schema": "cbsrm-current-conditions/1.0.0",
        "generated_at_utc": generated_at_utc,
        "readings": readings,
        "summary": {"total": len(readings), "live": len(ok),
                    "unavailable": len(readings) - len(ok)},
        "sources": sorted({r["source"] for r in readings}),
        "disclaimer": ("Latest available public readings, each dated to its "
                       "provider's last publication. Risk measurement — not "
                       "investment advice."),
        "output_sha256": output_sha256,
    }


def main() -> int:
    _load_env_local()
    fresh = "--no-clear" not in sys.argv
    if fresh and _CACHE.exists():
        shutil.rmtree(_CACHE, ignore_errors=True)
        print(f"[snapshot] cleared cache {_CACHE}", file=sys.stderr)
    has_fred = bool(os.environ.get("FRED_API_KEY"))
    print(f"[snapshot] FRED_API_KEY present: {has_fred}", file=sys.stderr)

    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    snap = build_snapshot(generated_at_utc=stamp)

    _SITE.mkdir(parents=True, exist_ok=True)
    out_path = _SITE / "current.json"
    out_path.write_text(
        json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    s = snap["summary"]
    print(f"[snapshot] wrote {out_path} — {s['live']}/{s['total']} live, "
          f"{s['unavailable']} unavailable", file=sys.stderr)
    for r in snap["readings"]:
        if r["status"] == "ok":
            print(f"  ok   {r['id']:<14} {r.get('value', r.get('state'))}  "
                  f"@ {r.get('as_of')}", file=sys.stderr)
        else:
            print(f"  --   {r['id']:<14} {r.get('reason')}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
