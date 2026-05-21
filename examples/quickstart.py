"""
CBSRM quick-start walkthrough.

Demonstrates the full public surface of CBSRM v0.5 end-to-end:

1. Fetch a stress baseline from FRED (STLFSI4)
2. Run the macro composite for the four canonical US sub-indicators
3. Compute ΔCoVaR from synthetic paired returns
4. Compute MES (empirical) on the same synthetic pair
5. Compute SRISK for a hand-supplied two-firm panel
6. Persist the full lineage to the audit chain

Requires:
    pip install -e ".[all]"
    export FRED_API_KEY=your_free_fred_key

Run:
    python examples/quickstart.py

Output: human-readable summary to stdout + a SQLite audit file at
``./.cbsrm_quickstart_audit.db`` for inspection via ``cbsrm verify-audit``.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np


def banner(title: str) -> None:
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def step_1_stress_baseline() -> None:
    banner("Step 1 — STLFSI4 stress baseline (FRED)")
    from cbsrm.data import FREDClient
    from cbsrm.indicators import STLFSIWrap

    client = FREDClient()       # reads FRED_API_KEY from env
    df = client.get_multi(["STLFSI4"])
    if df.empty:
        print("  No data returned. Did you export FRED_API_KEY?")
        return
    result = STLFSIWrap().compute(df)
    if result.latest is None:
        print("  No latest value.")
        return
    ts, value = result.latest
    print(f"  As of {ts.date()}: STLFSI4 = {value:.4f}")
    print(f"  ({result.metadata['interpretation']})")


def step_2_macro_composite() -> None:
    banner("Step 2 — Four-state macro regime composite")
    from cbsrm.data import FREDClient
    from cbsrm.macro import MacroCompositeIndicator

    fred = FREDClient()
    daily = fred.get_multi(["T10Y3M", "DFF", "DTWEXBGS"],
                           observation_start="2020-01-01", frequency="d")
    monthly = fred.get_multi(["PAYEMS"],
                             observation_start="2010-01-01", frequency="m")
    if daily.empty or monthly.empty:
        print("  No data — set FRED_API_KEY.")
        return
    aligned = monthly["PAYEMS"].reindex(daily.index, method="ffill")
    daily["PAYEMS"] = aligned
    df = daily.dropna(how="any")
    result = MacroCompositeIndicator().compute(df)
    m = result.metadata
    print(f"  Latest regime:           {m['latest_regime']}")
    print(f"  Composite score:         {m['latest_composite_score']:+.3f}")
    print(f"  Sub-scores:              {m['latest_sub_scores']}")
    print(f"  Override triggers:       {m['latest_override_triggers'] or 'none'}")


def step_3_delta_covar() -> None:
    banner("Step 3 — ΔCoVaR on synthetic paired returns (rho = 0.75)")
    from cbsrm.risk import DeltaCoVaREstimator

    rng = np.random.RandomState(42)
    n = 2000
    u = rng.normal(0, 0.01, (n, 2))
    rho = 0.75
    L = np.array([[1.0, 0.0],
                  [rho, np.sqrt(1.0 - rho ** 2)]])
    z = u @ L.T
    firm_returns, system_returns = z[:, 0], z[:, 1]
    res = DeltaCoVaREstimator(q=0.05).estimate(
        firm="synthetic_bank",
        firm_returns=firm_returns,
        system_returns=system_returns,
    )
    print(f"  β_q (q=0.05):            {res.beta_q:+.3f}")
    print(f"  VaR_q(firm):             {res.var_q_firm:+.4f}")
    print(f"  Median(firm):            {res.median_firm:+.4f}")
    print(f"  ΔCoVaR:                  {res.delta_covar:+.4f}")
    print(f"  (More negative = larger systemic contribution from firm.)")


def step_4_mes() -> None:
    banner("Step 4 — Empirical MES on the same synthetic pair")
    from cbsrm.risk import empirical_mes

    rng = np.random.RandomState(42)
    n = 2000
    u = rng.normal(0, 0.01, (n, 2))
    rho = 0.75
    L = np.array([[1.0, 0.0],
                  [rho, np.sqrt(1.0 - rho ** 2)]])
    z = u @ L.T
    res = empirical_mes(
        firm_returns=z[:, 0],
        market_returns=z[:, 1],
        q=0.05,
        firm="synthetic_bank",
    )
    print(f"  Market VaR_q (q=0.05):   {res.var_q_market:+.4f}")
    print(f"  MES (firm | market q-tail): {res.mes:+.4f}")
    print(f"  Tail-day count:          {res.n_tail_obs}/{res.n_total_obs}")


def step_5_srisk() -> None:
    banner("Step 5 — SRISK on a two-firm panel")
    from cbsrm.risk import srisk_panel

    inputs = [
        {"firm": "BigBank",  "market_cap_W": 250_000_000_000,
         "book_debt_D": 2_000_000_000_000, "lrmes": 0.42,
         "metadata": {"sector": "G-SIB"}},
        {"firm": "SmallBank", "market_cap_W": 5_000_000_000,
         "book_debt_D": 30_000_000_000, "lrmes": 0.30,
         "metadata": {"sector": "regional"}},
    ]
    out = srisk_panel(inputs, k=0.08)
    print(f"  Total positive SRISK:    ${out['total_srisk']/1e9:.2f}B")
    print(f"  Net SRISK:               ${out['total_srisk_net']/1e9:.2f}B")
    print(f"  Firms in shortfall:      {out['n_shortfall']} / {out['n_firms']}")
    for r in out["per_firm"]:
        sign = "SHORTFALL" if r["is_shortfall"] else "surplus"
        print(f"    {r['firm']:>10s}: ${r['srisk']/1e9:+.2f}B  ({sign})")


def step_6_audit_chain() -> None:
    banner("Step 6 — Persist a computation to the audit chain")
    from cbsrm.audit import AuditChain, AuditedIndicator
    from cbsrm.indicators import STLFSIWrap
    from cbsrm.data import FREDClient

    db_path = Path("./.cbsrm_quickstart_audit.db")
    conn = sqlite3.connect(str(db_path))
    audit = AuditChain(conn)
    wrapped = AuditedIndicator(
        STLFSIWrap(), audit, consumer="examples/quickstart.py",
    )
    df = FREDClient().get_multi(["STLFSI4"])
    if df.empty:
        print("  No data — set FRED_API_KEY.")
        return
    result = wrapped.compute(df)
    if result.latest is None:
        print("  No latest value.")
        return
    print(f"  Computed STLFSI4 = {result.latest[1]:.4f}")
    print(f"  Audit row id:    {result.audit_row_id}")
    ok, broken = audit.verify()
    print(f"  Chain integrity: {'OK' if ok else 'BROKEN'} ({len(broken)} broken rows)")
    print(f"  Audit DB:        {db_path.resolve()}")
    print(f"  Verify externally: cbsrm verify-audit --db {db_path}")


def main() -> int:
    print()
    print("CBSRM Quick-Start v0.5.0")
    print(f"  Executed {datetime.utcnow().isoformat()}Z")
    print()
    try:
        step_1_stress_baseline()
        step_2_macro_composite()
        step_3_delta_covar()
        step_4_mes()
        step_5_srisk()
        step_6_audit_chain()
    except KeyboardInterrupt:
        print("\n(interrupted)")
        return 130
    except Exception as e:
        print(f"\n[error] {type(e).__name__}: {e}")
        return 1
    banner("Done")
    print("  All six steps completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
