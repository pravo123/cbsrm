#!/usr/bin/env python3
"""
build_history_snapshot.py — full historical QUARTERLY systemic-risk series for
the "pick any quarter" explorer at cbsrm.wavervanir.com.

Writes ``site/history.json``: for each lens, a ``quarter -> value`` (and/or
``quarter -> regime state``) map across all available history (floored at
1999Q1), the master quarter axis, the crisis windows as quick-jump presets,
and a content-hash. The frontend (site/explorer.html) lets a user select ANY
quarter and shows that quarter's reading + a per-lens sparkline.

Every value is reproduced from public data (ECB SDMX + FRED), resampled to the
quarter-end observation. Run daily (GitHub Action): a fresh runner has no cache
so it always fetches live; the latest quarter updates, deep history is stable.

Lenses (long-history, single-series): ECB-CISS US/EA/UK · STLFSI4 · recession
probability (yield curve) · 4-state macro regime · Sahm rule · HY credit spread.
(CISS-US needs the 15-input FRED panel incl. SOFR (2018+) → deferred to phase 2.)
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SITE = _REPO / "site"
_CACHE = _REPO / ".cbsrm_cache"
_MIN_QUARTER = "1999Q1"


def _load_env_local() -> None:
    if os.environ.get("FRED_API_KEY"):
        return
    f = _REPO / ".env.local"
    if f.is_file():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _quarterly(series):
    """Daily/weekly/monthly pd.Series -> {'YYYYQn': float} at quarter-end."""
    import pandas as pd

    s = series.dropna()
    if s.empty:
        return {}
    s.index = pd.to_datetime(s.index)
    if s.index.tz is not None:
        s.index = s.index.tz_localize(None)
    try:
        q = s.resample("QE").last().dropna()
    except ValueError:
        q = s.resample("Q").last().dropna()
    return {str(p): round(float(v), 6) for p, v in zip(q.index.to_period("Q"), q.values)}


def _floor(d: dict) -> dict:
    return {q: v for q, v in d.items() if q >= _MIN_QUARTER}


# ─── per-lens series builders (each returns (values|None, states|None)) ──

def _ecb(variant):
    from cbsrm.data import ECBSDMXClient
    from cbsrm.indicators import ECBCISSWrap

    client = ECBSDMXClient()
    fetch = {"US": client.get_ciss_us, "EA": client.get_ciss_euro_area,
             "UK": client.get_ciss_uk}[variant]
    res = ECBCISSWrap(variant=variant).compute(fetch())
    return _floor(_quarterly(res.values)), None


def _stlfsi():
    from cbsrm.data import FREDClient
    from cbsrm.indicators import STLFSIWrap

    df = FREDClient().get_multi(["STLFSI4"])
    res = STLFSIWrap().compute(df)
    return _floor(_quarterly(res.values)), None


def _yield_curve():
    from cbsrm.data import FREDClient
    from cbsrm.macro import YieldCurveIndicator

    df = FREDClient().get_multi(["T10Y3M"], frequency="d")
    res = YieldCurveIndicator().compute(df)
    return _floor(_quarterly(res.values)), None  # values = 12m recession prob


def _macro_regime():
    import pandas as pd
    from cbsrm.data import FREDClient
    from cbsrm.macro import MacroCompositeIndicator

    fred = FREDClient()
    daily = fred.get_multi(["T10Y3M", "DFF", "DTWEXBGS"], frequency="d")
    monthly = fred.get_multi(["PAYEMS"], frequency="m")
    df = daily.copy()
    df["PAYEMS"] = monthly["PAYEMS"].reindex(daily.index, method="ffill")
    df = df.dropna(how="any")
    res = MacroCompositeIndicator().compute(df)
    qscore = _floor(_quarterly(res.values))

    def regime(s):
        if s >= 0.4:
            return "RISK_ON"
        if s > -0.1:
            return "TRANSITION_UP"
        if s > -0.4:
            return "TRANSITION_DOWN"
        return "RISK_OFF"

    states = {q: regime(v) for q, v in qscore.items()}
    return None, states  # state-only lens


def _sahm():
    from cbsrm.data import FREDClient
    from cbsrm.macro import SahmRuleIndicator

    df = FREDClient().get_multi(["UNRATE"], frequency="m")
    res = SahmRuleIndicator().compute(df)
    vals = _floor(_quarterly(res.values))
    states = {q: ("RECESSION_SIGNAL" if v >= 0.5 else "NORMAL") for q, v in vals.items()}
    return vals, states


def _credit_spread():
    from cbsrm.data import FREDClient
    from cbsrm.macro import CreditSpreadRegimeIndicator

    df = FREDClient().get_multi(["BAMLH0A0HYM2"], frequency="d")
    res = CreditSpreadRegimeIndicator().compute(df)
    vals = _floor(_quarterly(res.values))

    def regime(b):
        if b >= 1000:
            return "CREDIT_STRESS"
        if b >= 600:
            return "CREDIT_WIDENING"
        return "CREDIT_BENIGN"

    states = {q: regime(v) for q, v in vals.items()}
    return vals, states


# lens metadata mirrors the current-conditions cards (same fmt/tone contract)
_LENSES = [
    ("ECB-CISS-US", "ECB CISS — United States", "System stress", "ratio", "index 0–1", "ECB SDMX", lambda: _ecb("US")),
    ("ECB-CISS-EA", "ECB CISS — Euro Area", "System stress", "ratio", "index 0–1", "ECB SDMX", lambda: _ecb("EA")),
    ("ECB-CISS-UK", "ECB CISS — United Kingdom", "System stress", "ratio", "index 0–1", "ECB SDMX", lambda: _ecb("UK")),
    ("STLFSI4", "St. Louis Fed Financial Stress", "System stress", "signed", "z · 0 = normal", "FRED", _stlfsi),
    ("YIELD-CURVE", "Recession probability · 12m", "Macro regime", "probability", "Estrella–Mishkin", "FRED", _yield_curve),
    ("MACRO-REGIME", "Macro regime · 4-state", "Macro regime", "state", "composite", "FRED", _macro_regime),
    ("SAHM", "Sahm Rule recession signal", "Macro regime", "pp2", "pp · trigger 0.50", "FRED", _sahm),
    ("CREDIT-SPREAD", "HY credit-spread · OAS", "Tail / credit", "bps", "bps", "FRED", _credit_spread),
]


def build() -> dict:
    from cbsrm.reporting.manifest import sha256_jsonable

    lenses, all_quarters = [], set()
    for lid, label, lens, fmt, unit, source, fn in _LENSES:
        entry = {"id": lid, "label": label, "lens": lens, "fmt": fmt,
                 "unit": unit, "source": source}
        try:
            values, states = fn()
            if values:
                entry["values"] = values
                all_quarters.update(values)
            if states:
                entry["states"] = states
                all_quarters.update(states)
            if not values and not states:
                entry["status"] = "unavailable"
            print(f"  ok   {lid:<14} {len(values or states or {})} quarters", file=sys.stderr)
        except Exception as exc:
            entry["status"] = "unavailable"
            entry["reason"] = f"{type(exc).__name__}: {exc}"
            print(f"  --   {lid:<14} {type(exc).__name__}: {str(exc)[:80]}", file=sys.stderr)
        lenses.append(entry)

    quarters = sorted(q for q in all_quarters if q >= _MIN_QUARTER)
    return {
        "schema": "cbsrm-history/1.0.0",
        "generated_at_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quarters": quarters,
        "presets": [
            {"quarter": "2008Q4", "label": "2008Q4 — Global Financial Crisis"},
            {"quarter": "2020Q1", "label": "2020Q1 — COVID crash"},
            {"quarter": "2023Q1", "label": "2023Q1 — Regional-bank stress"},
        ],
        "lenses": lenses,
        "sources": sorted({l["source"] for l in lenses}),
        "disclaimer": ("Historical quarterly readings reproduced from public data "
                       "(ECB SDMX + FRED), at each provider's quarter-end observation. "
                       "Risk measurement — not investment advice."),
        "output_sha256": sha256_jsonable(lenses),
    }


def main() -> int:
    _load_env_local()
    if "--no-clear" not in sys.argv and _CACHE.exists():
        shutil.rmtree(_CACHE, ignore_errors=True)
        print(f"[history] cleared cache {_CACHE}", file=sys.stderr)
    print(f"[history] FRED_API_KEY present: {bool(os.environ.get('FRED_API_KEY'))}",
          file=sys.stderr)
    snap = build()
    _SITE.mkdir(parents=True, exist_ok=True)
    (_SITE / "history.json").write_text(
        json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    q = snap["quarters"]
    print(f"[history] wrote site/history.json — {len(snap['lenses'])} lenses, "
          f"{len(q)} quarters ({q[0] if q else '-'} .. {q[-1] if q else '-'})",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
