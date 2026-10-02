"""Build the synthetic laghubitta (microfinance) pilot demo data.

Deterministic generator for the illustrative CBSRM pilot prototype. It writes

  site/laghubitta_loans.csv   account-month panel (contract section 2)
  site/laghubitta_demo.json   computed figures (contract section 6)
  site/laghubitta.html        rewrites the inline <script id="demo-data"> block

Each CSV row is a centre-level pooled account (group loans aggregated per
centre) at one month-end. The column is still called `loan_id`, per the
contract schema. Amounts are simulated at single-account ticket sizes and
multiplied by SCALE (100) when written, so a branch carries roughly NPR 10 to
35 crore and the institution about NPR 1,200 crore. Ratios are unaffected.

All data is SYNTHETIC. Institution label: "Sample Laghubitta (synthetic data)".
Thresholds and provisioning rates are illustrative, to be calibrated. No
regulatory or compliance claim is made.

Every figure is computed here directly from the frozen contract
(docs/laghubitta_contract.md). This file deliberately does NOT import
cbsrm.mfi; agreement with the library is proven by
tests/test_laghubitta_parity.py.

Usage:  python tools/build_laghubitta_demo.py
Deps:   stdlib, numpy, pandas.
"""

from __future__ import annotations

import calendar
import hashlib
import io
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20261002
CONTRACT_VERSION = 1
INSTITUTION = "Sample Laghubitta (synthetic data)"
LAST_MONTH_END = (2026, 9)  # latest as_of = 2026-09-30
N_MONTHS = 24
MAX_LOANS = 2000
SCALE = 100  # every NPR amount (CSV money columns, balance sheet) is x100

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
CSV_PATH = SITE / "laghubitta_loans.csv"
JSON_PATH = SITE / "laghubitta_demo.json"
HTML_PATH = SITE / "laghubitta.html"

# ---------------------------------------------------------------- contract
BUCKETS = ["current", "b1_30", "b31_90", "b91_180", "b180p"]
STATES = BUCKETS + ["written_off", "closed"]
METRICS = ["gross_npr", "par30", "par90", "npl_ratio", "restructured_ratio",
           "writeoff_ratio", "collection_efficiency", "n_loans"]
DEFAULT_CONFIG: dict = {
    "npl_dpd_threshold": 90,
    "provision_rates": {"current": 0.01, "b1_30": 0.05, "b31_90": 0.25,
                        "b91_180": 0.50, "b180p": 1.00},   # illustrative
    "alerts": {"par30_level": 0.10, "par30_jump": 0.02,
               "roll_rate": 0.05, "collection_drop": 0.05},
}
CSV_COLUMNS = ["as_of", "loan_id", "branch_id", "branch_name", "district",
               "province", "product", "sector", "disbursed_npr",
               "outstanding_npr", "days_past_due", "restructured",
               "written_off", "writeoff_npr", "due_npr", "collected_npr"]
MONEY_COLS = ["disbursed_npr", "outstanding_npr", "writeoff_npr", "due_npr",
              "collected_npr"]

# ---------------------------------------------------------------- geography
# Real Nepal district names, all 7 provinces. Repeated districts get a 2nd branch.
PROVINCE_DISTRICTS = {
    "Koshi": ["Jhapa", "Jhapa", "Morang", "Morang", "Sunsari", "Sunsari",
              "Ilam", "Dhankuta", "Udayapur", "Khotang"],
    "Madhesh": ["Saptari", "Siraha", "Dhanusha", "Dhanusha", "Mahottari",
                "Sarlahi", "Sarlahi", "Rautahat", "Bara", "Bara", "Parsa"],
    "Bagmati": ["Kathmandu", "Lalitpur", "Bhaktapur", "Chitwan", "Chitwan",
                "Makwanpur", "Kavrepalanchok", "Dhading", "Nuwakot",
                "Sindhupalchok"],
    "Gandaki": ["Kaski", "Kaski", "Tanahun", "Syangja", "Gorkha", "Nawalpur",
                "Baglung"],
    "Lumbini": ["Rupandehi", "Rupandehi", "Kapilvastu", "Dang", "Dang", "Banke",
                "Banke", "Bardiya", "Palpa", "Gulmi"],
    "Karnali": ["Surkhet", "Dailekh", "Jumla", "Salyan", "Kalikot"],
    "Sudurpashchim": ["Kailali", "Kailali", "Kanchanpur", "Doti", "Dadeldhura",
                      "Baitadi", "Achham"],
}
# Branches whose risk ramps up over the last few months (the "story").
# (district, ramp length in months, hazard multiplier at the latest month)
DETERIORATING = {"Siraha": (6, 16.0), "Rautahat": (6, 14.0), "Kapilvastu": (5, 14.0),
                 "Bardiya": (5, 12.0), "Saptari": (4, 12.0)}
AGRI_PROVINCES = ("Madhesh", "Lumbini")

SECTORS = ["Agriculture", "Livestock", "Retail Trade", "Services",
           "Manufacturing and Cottage", "Transport"]
SECTOR_W_AGRI = [0.38, 0.25, 0.14, 0.10, 0.08, 0.05]
SECTOR_W_OTHER = [0.12, 0.08, 0.30, 0.26, 0.14, 0.10]

PRODUCTS = {  # name: (min ticket, max ticket, term months, annual rate); before SCALE
    "Group Loan": (30_000, 150_000, 24, 0.14),
    "Micro Enterprise": (100_000, 500_000, 36, 0.145),
    "Agriculture Seasonal": (50_000, 200_000, 12, 0.13),
    "Livestock": (80_000, 300_000, 24, 0.135),
    "Housing Improvement": (150_000, 700_000, 36, 0.14),
}
PRODUCT_BY_SECTOR = {
    "Agriculture": (["Agriculture Seasonal", "Group Loan", "Housing Improvement"],
                    [0.55, 0.30, 0.15]),
    "Livestock": (["Livestock", "Group Loan", "Housing Improvement"],
                  [0.60, 0.30, 0.10]),
}
PRODUCT_DEFAULT = (["Group Loan", "Micro Enterprise", "Housing Improvement"],
                   [0.42, 0.43, 0.15])

# Seasonal multiplier on the monthly miss hazard, by calendar month. Monsoon
# (Jun to Sep) hurts farm cash flows; post-harvest (Nov, Dec) is strongest.
SEASON = {1: 0.8, 2: 0.8, 3: 0.9, 4: 1.0, 5: 1.1, 6: 1.8, 7: 2.6, 8: 2.4,
          9: 1.6, 10: 1.0, 11: 0.5, 12: 0.5}
FARM_SECTORS = ("Agriculture", "Livestock")

BASE_HAZARD = 0.010
CURE_BY_MISSED = [0.0, 0.50, 0.33, 0.20, 0.12, 0.08, 0.05, 0.03, 0.02]
STAY_PROB = 0.22
WRITE_OFF_AT = 9          # missed installments
PREPAY_PROB = 0.006
INITIAL_LOANS = 1080
NEW_PER_MONTH = 38

# Scenario library (contract 5.1). Parameters are illustrative.
SCENARIOS = [
    {"id": "base", "label": "Base case (no shock)"},
    {"id": "rate_up_200bp", "label": "Funding rates up 200 bp",
     "base_shift": 0.02, "funding_cost_bps": 200},
    {"id": "agri_income_shock", "label": "Farm income shock (crop prices fall)",
     "base_shift": 0.05,
     "sector_mult": {"Agriculture": 4.0, "Livestock": 3.0}},
    {"id": "monsoon_seasonal", "label": "Heavy monsoon season",
     "base_shift": 0.06,
     "sector_mult": {"Agriculture": 2.5, "Livestock": 2.0, "Transport": 1.5},
     "inflow_haircut": 0.10},
    {"id": "regional_disaster", "label": "Flood in Madhesh and Lumbini",
     "base_shift": 0.08,
     "province_mult": {"Madhesh": 4.0, "Lumbini": 3.0},
     "sector_mult": {"Agriculture": 1.5, "Livestock": 1.5},
     "inflow_haircut": 0.20, "outflow_mult": 1.10},
    {"id": "funding_squeeze", "label": "Wholesale funding squeeze",
     "funding_cost_bps": 300, "inflow_haircut": 0.25, "outflow_mult": 1.35},
]


# ---------------------------------------------------------------- helpers
def month_ends(last: tuple[int, int], n: int) -> list[str]:
    y, m = last
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def r2(x: float) -> float:
    return float(round(x, 2))


def build_branches() -> list[dict]:
    rows = []
    seen: dict[str, int] = {}
    i = 0
    for province, districts in PROVINCE_DISTRICTS.items():
        for d in districts:
            i += 1
            seen[d] = seen.get(d, 0) + 1
            rows.append({"branch_id": f"BR{i:03d}",
                         "branch_name": f"{d} {seen[d]}",
                         "district": d, "province": province})
    return rows


# ---------------------------------------------------------------- simulation
def simulate(rng: np.random.Generator) -> pd.DataFrame:
    dates = month_ends(LAST_MONTH_END, N_MONTHS)
    branches = build_branches()
    bw = np.array([1.4 if b["province"] in AGRI_PROVINCES else 1.0 for b in branches])
    bw = bw / bw.sum()

    def stress_mult(branch: dict, t: int) -> tuple[float, float]:
        cfg = DETERIORATING.get(branch["district"])
        if cfg is None or branch["branch_name"].endswith(" 2"):
            return 1.0, 1.0
        length, peak = cfg
        start = N_MONTHS - 1 - length
        if t <= start:
            return 1.0, 1.0
        frac = (t - start) / length
        return 1.0 + (peak - 1.0) * frac, 1.0 - 0.6 * frac

    loans: list[dict] = []

    def new_loan(t: int, seasoned: bool) -> dict:
        b = branches[int(rng.choice(len(branches), p=bw))]
        sw = SECTOR_W_AGRI if b["province"] in AGRI_PROVINCES else SECTOR_W_OTHER
        sector = SECTORS[int(rng.choice(len(SECTORS), p=sw))]
        names, pw = PRODUCT_BY_SECTOR.get(sector, PRODUCT_DEFAULT)
        product = names[int(rng.choice(len(names), p=pw))]
        lo, hi, term, rate = PRODUCTS[product]
        disbursed = float(round(rng.uniform(lo, hi) / 1000.0) * 1000.0)
        age = int(rng.integers(0, int(term * 0.6))) if seasoned else 0
        outstanding = r2(disbursed * (1 - age / term))
        ln = {"loan_id": f"LN{len(loans) + 1:05d}", **b, "product": product,
              "sector": sector, "disbursed": disbursed, "term": term,
              "rate": rate, "inst_p": r2(disbursed / term),
              "out": outstanding, "missed": 0, "arrears": 0.0,
              "arrears_p": 0.0, "restructured": 0, "offset": int(rng.integers(1, 30)),
              # seasoned loans already have a repayment history at the panel start
              "start": -1 if seasoned else t, "done": False}
        if seasoned and rng.random() < 0.04:   # some seasoned arrears at start
            ln["missed"] = int(rng.integers(1, 5))
            ln["arrears_p"] = r2(min(ln["missed"] * ln["inst_p"], outstanding * 0.5))
            ln["arrears"] = r2(ln["arrears_p"] * 1.1)
        return ln

    for _ in range(INITIAL_LOANS):
        loans.append(new_loan(0, seasoned=True))

    rows: list[dict] = []
    for t, as_of in enumerate(dates):
        cal_month = int(as_of[5:7])
        if t > 0:
            for _ in range(NEW_PER_MONTH):
                if len(loans) < MAX_LOANS:
                    loans.append(new_loan(t, seasoned=False))
        for ln in loans:
            if ln["done"]:
                continue
            row = {"as_of": as_of, "loan_id": ln["loan_id"],
                   "branch_id": ln["branch_id"], "branch_name": ln["branch_name"],
                   "district": ln["district"], "province": ln["province"],
                   "product": ln["product"], "sector": ln["sector"],
                   "disbursed_npr": ln["disbursed"]}
            if ln["start"] == t:   # disbursement month: no demand yet
                due = collected = 0.0
            else:
                if rng.random() < PREPAY_PROB and ln["missed"] == 0:
                    ln["done"] = True
                    continue
                h_mult, c_mult = stress_mult(ln, t)
                season = SEASON[cal_month] if ln["sector"] in FARM_SECTORS else \
                    1.0 + (SEASON[cal_month] - 1.0) * 0.4
                interest = r2(ln["out"] * ln["rate"] / 12.0)
                sched_p = min(ln["inst_p"], max(ln["out"] - ln["arrears_p"], 0.0))
                sched = r2(sched_p + interest)
                due = r2(sched + ln["arrears"])
                m = ln["missed"]
                u = rng.random()
                if m == 0:
                    outcome = "miss" if u < BASE_HAZARD * h_mult * season else "pay"
                else:
                    cure = min(0.95, CURE_BY_MISSED[min(m, 8)] * c_mult / season)
                    outcome = ("cure" if u < cure else
                               "pay" if u < cure + STAY_PROB else "miss")
                if (m >= 3 and h_mult > 1.0 and t >= N_MONTHS - 4
                        and rng.random() < 0.12):
                    outcome = "restructure"
                elif m >= 2 and rng.random() < 0.01:
                    outcome = "restructure"
                if outcome == "pay":
                    collected = sched
                    ln["out"] = r2(ln["out"] - sched_p)
                elif outcome == "cure":
                    collected = due
                    ln["out"] = r2(ln["out"] - sched_p - ln["arrears_p"])
                    ln["missed"], ln["arrears"], ln["arrears_p"] = 0, 0.0, 0.0
                elif outcome == "restructure":
                    collected = r2(interest)
                    ln["restructured"] = 1
                    ln["missed"], ln["arrears"], ln["arrears_p"] = 0, 0.0, 0.0
                    ln["inst_p"] = r2(ln["out"] / 18.0)
                else:  # miss
                    collected = r2(sched * rng.uniform(0.2, 0.6))
                    ln["missed"] += 1
                    ln["arrears"] = r2(ln["arrears"] + sched - collected)
                    ln["arrears_p"] = r2(ln["arrears_p"] + sched_p)
                if ln["out"] <= 1.0:
                    ln["done"] = True     # matured: absent from this month on
                    continue
            m = ln["missed"]
            dpd = 0 if m == 0 else 30 * (m - 1) + ln["offset"]
            if m >= WRITE_OFF_AT:
                row.update(outstanding_npr=0.0, days_past_due=dpd,
                           restructured=ln["restructured"], written_off=1,
                           writeoff_npr=ln["out"], due_npr=due,
                           collected_npr=collected)
                ln["done"] = True
            else:
                row.update(outstanding_npr=ln["out"], days_past_due=dpd,
                           restructured=ln["restructured"], written_off=0,
                           writeoff_npr=0.0, due_npr=due, collected_npr=collected)
            rows.append(row)
    assert len(loans) <= MAX_LOANS
    return pd.DataFrame(rows, columns=CSV_COLUMNS)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    out = df.copy()
    for c in MONEY_COLS:
        out[c] = out[c].map(lambda v: f"{v * SCALE:.2f}")
    out.to_csv(buf, index=False, lineterminator="\n")
    return buf.getvalue().encode("utf-8")


def read_loans(path_or_bytes) -> pd.DataFrame:
    src = io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, bytes) else path_or_bytes
    return pd.read_csv(src, dtype={"as_of": str, "loan_id": str, "branch_id": str})


# ---------------------------------------------------------------- metrics (contract 3, 4)
def assign_bucket(dpd: pd.Series) -> pd.Series:
    out = pd.Series("b180p", index=dpd.index, dtype=object)
    out[dpd <= 180] = "b91_180"
    out[dpd <= 90] = "b31_90"
    out[dpd <= 30] = "b1_30"
    out[dpd == 0] = "current"
    return out


def _ratio(num: float, den: float) -> float:
    return float(num) / float(den) if den != 0 else math.nan


# Summation note: contract parity is absolute 1e-9, below one ulp of an NPR sum
# near 1e8. Sums are therefore taken with whole-column pandas reductions over
# zero-masked columns (frame sum, or groupby sum), so any implementation of the
# contract that reduces the same way agrees to the last bit.
_SUMS = ["gross_npr", "par30", "par90", "npl_ratio", "restructured_ratio",
         "writeoff_npr", "due_npr", "collected_npr", "n_loans"]


def _masked(rows: pd.DataFrame, config: dict) -> pd.DataFrame:
    f = rows.copy()
    live = f["written_off"] == 0
    o = f["outstanding_npr"].where(live, 0.0)
    d = f["days_past_due"]
    f["gross_npr"] = o
    f["par30"] = o.where(d > 30, 0.0)
    f["par90"] = o.where(d > 90, 0.0)
    f["npl_ratio"] = o.where(d > config["npl_dpd_threshold"], 0.0)
    f["restructured_ratio"] = o.where(f["restructured"] == 1, 0.0)
    f["n_loans"] = live.astype(int)
    return f


def _finish(t: dict) -> dict:
    gross, w = float(t["gross_npr"]), float(t["writeoff_npr"])
    return {
        "gross_npr": gross,
        "par30": _ratio(t["par30"], gross),
        "par90": _ratio(t["par90"], gross),
        "npl_ratio": _ratio(t["npl_ratio"], gross),
        "restructured_ratio": _ratio(t["restructured_ratio"], gross),
        "writeoff_ratio": _ratio(w, gross + w),
        "collection_efficiency": _ratio(t["collected_npr"], t["due_npr"]),
        "n_loans": int(t["n_loans"]),
    }


def metrics_for(rows: pd.DataFrame, config: dict) -> dict:
    return _finish(_masked(rows, config)[_SUMS].sum().to_dict())


def portfolio_metrics(loans: pd.DataFrame, as_of: str, by=(), config=None) -> list[dict]:
    config = config or DEFAULT_CONFIG
    rows = loans[loans["as_of"] == as_of]
    if not by:
        return [metrics_for(rows, config)]
    g = _masked(rows, config).groupby(list(by), sort=True)[_SUMS].sum()
    out = []
    for key, t in g.iterrows():
        key = key if isinstance(key, tuple) else (key,)
        out.append({**dict(zip(by, key, strict=True)), **_finish(t.to_dict())})
    return out


def bucket_balances(loans: pd.DataFrame, as_of: str, by=()) -> list[dict]:
    rows = loans[(loans["as_of"] == as_of) & (loans["written_off"] == 0)].copy()
    bucket = assign_bucket(rows["days_past_due"])
    for b in BUCKETS:
        rows[b] = rows["outstanding_npr"].where(bucket == b, 0.0)
    if not by:
        return [{b: float(v) for b, v in rows[BUCKETS].sum().items()}]
    g = rows.groupby(list(by), sort=True)[BUCKETS].sum()
    out = []
    for key, t in g.iterrows():
        key = key if isinstance(key, tuple) else (key,)
        out.append({**dict(zip(by, key, strict=True)), **{b: float(t[b]) for b in BUCKETS}})
    return out


def migration_matrix(loans: pd.DataFrame, from_as_of: str, to_as_of: str,
                     weight: str = "outstanding") -> dict:
    a = loans[(loans["as_of"] == from_as_of) & (loans["written_off"] == 0)].copy()
    a["from"] = assign_bucket(a["days_past_due"])
    b = loans[loans["as_of"] == to_as_of].copy()
    b["to"] = assign_bucket(b["days_past_due"])
    b.loc[b["written_off"] == 1, "to"] = "written_off"
    m = a.merge(b[["loan_id", "to"]], on="loan_id", how="left")
    m["to"] = m["to"].fillna("closed")
    m["w"] = m["outstanding_npr"] if weight == "outstanding" else 1.0
    matrix: dict = {}
    for fb in BUCKETS:
        sub = m[m["from"] == fb]
        tot = float(sub["w"].sum())
        matrix[fb] = {s: _ratio(sub.loc[sub["to"] == s, "w"].sum(), tot) for s in STATES}
    return matrix


def roll_rates(matrix: dict) -> dict:
    out = {}
    for i, fb in enumerate(BUCKETS):
        row = matrix[fb]
        worse = ["written_off"] if fb == "b180p" else BUCKETS[i + 1:] + ["written_off"]
        out[fb] = math.nan if any(math.isnan(row[s]) for s in STATES) else \
            float(sum(row[s] for s in worse))
    return out


def _shares(loans: pd.DataFrame, as_of: str, by: str) -> pd.Series:
    live = loans[(loans["as_of"] == as_of) & (loans["written_off"] == 0)]
    g = live.groupby(by)["outstanding_npr"].sum()
    return g / g.sum()


def hhi(loans: pd.DataFrame, as_of: str, by: str) -> float:
    return float((_shares(loans, as_of, by) ** 2).sum())


def top_n_share(loans: pd.DataFrame, as_of: str, by: str, n: int = 5) -> float:
    return float(_shares(loans, as_of, by).sort_values(ascending=False).head(n).sum())


def branch_alerts(loans: pd.DataFrame, as_of: str, prev_as_of: str, config=None) -> list[dict]:
    config = config or DEFAULT_CONFIG
    th = config["alerts"]
    cur = {r["branch_id"]: r for r in portfolio_metrics(loans, as_of, ["branch_id"], config)}
    prv = {r["branch_id"]: r for r in portfolio_metrics(loans, prev_as_of, ["branch_id"], config)}
    out = []
    for bid in sorted(set(cur) | set(prv)):
        c, p = cur.get(bid), prv.get(bid)
        nan = math.nan
        sub = loans[loans["branch_id"] == bid]
        rr = roll_rates(migration_matrix(sub, prev_as_of, as_of))["current"]
        vals = {
            "COLLECTION_DROP": ((p["collection_efficiency"] if p else nan)
                                - (c["collection_efficiency"] if c else nan),
                                th["collection_drop"]),
            "PAR30_JUMP": ((c["par30"] if c else nan) - (p["par30"] if p else nan),
                           th["par30_jump"]),
            "PAR30_LEVEL": (c["par30"] if c else nan, th["par30_level"]),
            "ROLL_RATE": (rr, th["roll_rate"]),
        }
        for rule in sorted(vals):
            v, t = vals[rule]
            if not math.isnan(v) and v >= t:
                out.append({"branch_id": bid, "rule": rule, "value": float(v),
                            "threshold": float(t),
                            "severity": "high" if v >= 2 * t else "medium"})
    return out


def apply_scenario(segments: list[dict], balance_sheet: dict, scenario: dict,
                   config=None) -> dict:
    config = config or DEFAULT_CONFIG
    rates = config["provision_rates"]
    base_shift = scenario.get("base_shift", 0.0)
    smult, pmult = scenario.get("sector_mult", {}), scenario.get("province_mult", {})
    seg = pd.DataFrame(segments)
    s = (base_shift * seg["sector"].map(lambda k: smult.get(k, 1.0))
         * seg["province"].map(lambda k: pmult.get(k, 1.0))).clip(upper=1.0)
    stressed = {"current": seg["current"] * (1 - s),
                "b1_30": seg["b1_30"] * (1 - s) + seg["current"] * s,
                "b31_90": seg["b31_90"] * (1 - s) + seg["b1_30"] * s,
                "b91_180": seg["b91_180"] * (1 - s) + seg["b31_90"] * s,
                "b180p": seg["b180p"] + seg["b91_180"] * s}
    T = {b: float(stressed[b].sum()) for b in BUCKETS}
    U = {b: float(seg[b].sum()) for b in BUCKETS}
    gross = sum(T.values())
    prov = sum(T[b] * rates[b] for b in BUCKETS)
    prov_base = sum(U[b] * rates[b] for b in BUCKETS)
    nii = balance_sheet["borrowings_npr"] * scenario.get("funding_cost_bps", 0) / 10000
    capital = balance_sheet["capital_npr"] - (prov - prov_base) - nii
    return {
        "scenario_id": scenario["id"], "buckets": T, "gross_npr": gross,
        "par30": _ratio(T["b31_90"] + T["b91_180"] + T["b180p"], gross),
        "par90": _ratio(T["b91_180"] + T["b180p"], gross),
        "provisions_npr": prov, "delta_provisions_npr": prov - prov_base,
        "nii_hit_npr": nii, "capital_npr": capital,
        "car": _ratio(capital, balance_sheet["rwa_npr"]),
        "liquidity_gap_90d_npr": (balance_sheet["liquid_assets_npr"]
                                  + balance_sheet["inflows_90d_npr"]
                                  * (1 - scenario.get("inflow_haircut", 0.0))
                                  - balance_sheet["outflows_90d_npr"]
                                  * scenario.get("outflow_mult", 1.0)),
    }


# ---------------------------------------------------------------- audit (contract 5.2)
def canon(x) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"))


def sha(s: str | bytes) -> str:
    return hashlib.sha256(s.encode("utf-8") if isinstance(s, str) else s).hexdigest()


def record(name: str, input_sha256: str, params: dict, output, prev_hash=None) -> dict:
    p, o = sha(canon(params)), sha(canon(output))
    return {"name": name, "input_sha256": input_sha256, "params_sha256": p,
            "output_sha256": o, "prev_hash": prev_hash,
            "hash": sha(canon([prev_hash or "", name, input_sha256, p, o]))}


HASH_SIG_DIGITS = 10


def round_sig(x, digits: int = HASH_SIG_DIGITS):
    """Round every float to `digits` significant digits, recursively.

    Contract-owner ruling R2: outputs are hashed at 10 significant digits so the
    audit chain is stable across summation order and platform; the figures
    stored in the JSON stay unrounded. Ints, bools, strings and None pass through.
    """
    if isinstance(x, bool) or x is None:
        return x
    if isinstance(x, float):
        return float(format(x, f".{digits}g")) if math.isfinite(x) else x
    if isinstance(x, dict):
        return {k: round_sig(v, digits) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [round_sig(v, digits) for v in x]
    return x


def clean(x):
    """NaN -> None recursively (JSON null)."""
    if isinstance(x, float):
        return None if math.isnan(x) else x
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        return clean(float(x))
    return x


# ---------------------------------------------------------------- build
def build(loans: pd.DataFrame, csv_sha: str) -> dict:
    cfg = DEFAULT_CONFIG
    dates = sorted(loans["as_of"].unique().tolist())
    latest, prev = dates[-1], dates[-2]

    institution = [{"as_of": d, **portfolio_metrics(loans, d, (), cfg)[0]} for d in dates]

    binfo = (loans[["branch_id", "branch_name", "district", "province"]]
             .drop_duplicates("branch_id").sort_values("branch_id"))
    per_date = {d: {r["branch_id"]: r for r in portfolio_metrics(loans, d, ["branch_id"], cfg)}
                for d in dates}
    branches = []
    for b in binfo.to_dict("records"):
        series = []
        for d in dates:
            r = per_date[d].get(b["branch_id"])
            if r is None:   # no rows at this date: metrics over an empty set
                r = metrics_for(loans.iloc[0:0], cfg)
            series.append({"as_of": d, **{k: r[k] for k in METRICS}})
        branches.append({**b, "series": series})

    def by_key(col: str) -> list[dict]:
        return [{"key": r[col], **{k: r[k] for k in METRICS}}
                for r in portfolio_metrics(loans, latest, [col], cfg)]

    segments = bucket_balances(loans, latest, ["sector", "province"])
    matrix = migration_matrix(loans, prev, latest)
    migration = {"from_as_of": prev, "to_as_of": latest, "states": STATES,
                 "matrix": matrix, "roll_rates": roll_rates(matrix)}
    concentration = {by: {"hhi": hhi(loans, latest, by),
                          "top5_share": top_n_share(loans, latest, by, 5)}
                     for by in ("district", "sector", "product")}
    alerts = branch_alerts(loans, latest, prev, cfg)

    g = institution[-1]["gross_npr"]
    def sized(k: float) -> float:   # rounded on the unscaled gross, then x SCALE
        return float(round(k * g / SCALE, -3) * SCALE)

    balance_sheet = {
        "capital_npr": sized(0.125),
        "rwa_npr": sized(1.08),
        "liquid_assets_npr": sized(0.11),
        "inflows_90d_npr": sized(0.24),
        "outflows_90d_npr": sized(0.28),
        "borrowings_npr": sized(0.70),
    }
    scen_results = [apply_scenario(segments, balance_sheet, s, cfg) for s in SCENARIOS]

    # audit chain: one record per computed block. Outputs are hashed after
    # rounding to 10 significant digits (ruling R2); params are hashed as is.
    chain: list[dict] = []

    def add(name, params, output):
        chain.append(record(name, csv_sha, clean(params), round_sig(clean(output)),
                            chain[-1]["hash"] if chain else None))

    add("institution", {"config": cfg, "as_of_dates": dates}, institution)
    add("branches", {"config": cfg, "as_of_dates": dates}, branches)
    add("migration", {"from_as_of": prev, "to_as_of": latest, "weight": "outstanding"},
        migration)
    add("concentration", {"as_of": latest, "n": 5}, concentration)
    add("alerts", {"as_of": latest, "prev_as_of": prev, "config": cfg}, alerts)
    for s, res in zip(SCENARIOS, scen_results, strict=True):
        add(f"scenario:{s['id']}",
            {"scenario": s, "balance_sheet": balance_sheet, "config": cfg}, res)

    out = {
        "meta": {"institution": INSTITUTION, "synthetic": True, "seed": SEED,
                 "generated_at": f"{latest}T23:59:59+05:45",
                 "contract_version": CONTRACT_VERSION, "currency": "NPR"},
        "config": cfg,
        "as_of_dates": dates,
        "institution": institution,
        "branches": branches,
        "by_district": by_key("district"),
        "by_product": by_key("product"),
        "by_sector": by_key("sector"),
        "segments": segments,
        "migration": migration,
        "concentration": concentration,
        "alerts": alerts,
        "balance_sheet": balance_sheet,
        "scenarios": SCENARIOS,
        "audit": {"input_sha256": csv_sha, "chain": chain,
                  "head_hash": chain[-1]["hash"]},
    }
    return clean(out)


def write_html_block(json_text: str) -> bool:
    if not HTML_PATH.exists():
        return False
    html = HTML_PATH.read_text(encoding="utf-8")
    pat = re.compile(r"(<!-- DEMO_DATA_START -->).*?(<!-- DEMO_DATA_END -->)", re.S)
    if not pat.search(html):
        return False
    safe = json_text.replace("</", "<\\/")
    block = ('<!-- DEMO_DATA_START -->\n<script id="demo-data" type="application/json">'
             + safe + "</script>\n<!-- DEMO_DATA_END -->")
    HTML_PATH.write_text(pat.sub(lambda _m: block, html), encoding="utf-8")
    return True


def main() -> None:
    rng = np.random.default_rng(SEED)
    raw = simulate(rng)
    csv_bytes = to_csv_bytes(raw)
    CSV_PATH.write_bytes(csv_bytes)
    loans = read_loans(csv_bytes)        # compute from exactly what was written
    data = build(loans, sha(csv_bytes))
    text = json.dumps(data, allow_nan=False, separators=(",", ":"))
    JSON_PATH.write_text(text + "\n", encoding="utf-8")
    patched = write_html_block(text)
    inst = data["institution"][-1]
    print(f"rows={len(loans)} loans={loans['loan_id'].nunique()} "
          f"branches={len(data['branches'])} as_of={data['as_of_dates'][-1]}")
    print(f"gross={inst['gross_npr']:.0f} par30={inst['par30']:.4f} "
          f"par90={inst['par90']:.4f} ce={inst['collection_efficiency']:.4f} "
          f"alerts={len(data['alerts'])} html_patched={patched}")


if __name__ == "__main__":
    main()
