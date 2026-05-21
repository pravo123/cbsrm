"""
CBSRM — Live Financial-Stability Dashboard
==========================================

Single-page Streamlit demo of the CBSRM v0.5 public API.

Renders, top-to-bottom:
  1. Macro composite regime (4-state badge + composite score + sub-score bars)
  2. Stress indicators (ECB CISS EA/US/UK + FRED STLFSI4)
  3. Macro indicators (yield-curve recession probit, USD/JPY z, DXY z, FFR change)
  4. SRISK panel for three illustrative US G-SIBs (JPM / BAC / C)
  5. ΔCoVaR + MES on a synthetic paired-return illustration

All numbers compute live from the installed cbsrm package. Set
``FRED_API_KEY`` (or place it in ``../.env`` two levels up) before running.

Run:
    streamlit run dashboard/streamlit_app.py

Apache-2.0. Methodology citations in the footer. NOT investment advice.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st


# ─── Environment + .env loading ────────────────────────────────────────


def _load_env_from_dotfiles() -> None:
    """Best-effort load of FRED_API_KEY from local .env files."""
    if os.environ.get("FRED_API_KEY"):
        return
    here = Path(__file__).resolve()
    candidates = [
        here.parent / ".env",
        here.parent.parent / ".env",
        here.parent.parent.parent / ".env",
        Path("C:/Users/Prabhawa Koirala/.openclaw/workspace/.env"),
    ]
    for p in candidates:
        try:
            if not p.is_file():
                continue
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k == "FRED_API_KEY" and v and "FRED_API_KEY" not in os.environ:
                    os.environ["FRED_API_KEY"] = v
                    return
        except Exception:
            continue


_load_env_from_dotfiles()


# ─── Page config ────────────────────────────────────────────────────────


st.set_page_config(
    page_title="CBSRM — Live Financial-Stability Dashboard",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)


REGIME_COLORS = {
    "RISK_ON":          ("#1b7f3a", "#d3f0dc"),
    "TRANSITION_UP":    ("#3a8f5a", "#e6f5ea"),
    "TRANSITION_DOWN":  ("#b9670c", "#fbe7cf"),
    "RISK_OFF":         ("#b3261e", "#fadcd9"),
    "INSUFFICIENT_HISTORY": ("#555", "#eee"),
}


# ─── Cached compute helpers ─────────────────────────────────────────────


@st.cache_resource(show_spinner=False)
def _fred_client():
    from cbsrm.data import FREDClient
    return FREDClient()


@st.cache_resource(show_spinner=False)
def _ecb_client():
    from cbsrm.data import ECBSDMXClient
    return ECBSDMXClient()


@st.cache_data(ttl=3600, show_spinner=False)
def compute_macro_composite() -> dict:
    from cbsrm.macro import MacroCompositeIndicator
    fred = _fred_client()
    daily = fred.get_multi(
        ["T10Y3M", "DFF", "DTWEXBGS"],
        observation_start="2020-01-01", frequency="d",
    )
    monthly = fred.get_multi(
        ["PAYEMS"], observation_start="2010-01-01", frequency="m",
    )
    if daily.empty or monthly.empty:
        return {"error": "no_data"}
    aligned = monthly["PAYEMS"].reindex(daily.index, method="ffill")
    daily["PAYEMS"] = aligned
    df = daily.dropna(how="any")
    if df.empty:
        return {"error": "no_aligned_data"}
    res = MacroCompositeIndicator().compute(df)
    return {
        "regime": res.metadata["latest_regime"],
        "composite_score": res.metadata["latest_composite_score"],
        "sub_scores": res.metadata["latest_sub_scores"],
        "overrides": res.metadata["latest_override_triggers"],
        "last_date": res.metadata["last_date"],
        "sub_meta": res.metadata["sub_indicators"],
    }


@st.cache_data(ttl=3600, show_spinner=False)
def compute_stlfsi() -> dict:
    from cbsrm.indicators import STLFSIWrap
    df = _fred_client().get_multi(["STLFSI4"])
    if df.empty:
        return {"error": "no_data"}
    res = STLFSIWrap().compute(df)
    if res.latest is None:
        return {"error": "no_latest"}
    ts, val = res.latest
    return {"value": float(val), "as_of": ts.date().isoformat()}


@st.cache_data(ttl=3600, show_spinner=False)
def compute_ecb_ciss(variant: str) -> dict:
    from cbsrm.indicators import ECBCISSWrap
    ecb = _ecb_client()
    if variant == "EA":
        s = ecb.get_ciss_euro_area(start_period="2024-01-01")
    elif variant == "US":
        s = ecb.get_ciss_us(start_period="2024-01-01")
    elif variant == "UK":
        s = ecb.get_ciss_uk(start_period="2024-01-01")
    else:
        return {"error": f"unknown variant {variant}"}
    s = s.dropna()
    if s.empty:
        return {"error": "no_data"}
    res = ECBCISSWrap(variant=variant).compute(s)
    if res.latest is None:
        return {"error": "no_latest"}
    ts, val = res.latest
    return {"value": float(val), "as_of": ts.date().isoformat()}


@st.cache_data(ttl=3600, show_spinner=False)
def compute_jpy_regime() -> dict:
    from cbsrm.macro import JPYRegimeIndicator
    df = _fred_client().get_multi(
        ["DEXJPUS"], observation_start="2020-01-01", frequency="d",
    )
    if df.empty:
        return {"error": "no_data"}
    res = JPYRegimeIndicator().compute(df)
    return {
        "z": res.metadata.get("latest_z_score"),
        "regime": res.metadata.get("regime"),
        "level": res.metadata.get("latest_usd_jpy"),
        "as_of": res.metadata.get("last_date"),
    }


@st.cache_data(ttl=3600, show_spinner=False)
def compute_srisk_panel() -> pd.DataFrame:
    """Compute SRISK for three illustrative G-SIBs.

    Market cap / book debt figures are *approximate 2026 ballpark* — clearly
    labeled as illustrative in the UI. Goal is methodology demo, not live
    bank-balance-sheet monitoring.
    """
    from cbsrm.risk import LRMESMonteCarlo, SRISKCalculator
    firms = [
        {"firm": "JPM", "W_bn": 580.0,  "D_bn": 3400.0, "rho": 0.78, "sigma_firm": 0.020},
        {"firm": "BAC", "W_bn": 305.0,  "D_bn": 2700.0, "rho": 0.82, "sigma_firm": 0.022},
        {"firm": "C",   "W_bn": 135.0,  "D_bn": 2300.0, "rho": 0.80, "sigma_firm": 0.024},
    ]
    calc = SRISKCalculator(k=0.08)
    rows = []
    for f in firms:
        # Per-firm GARCH-DCC params — use defaults but tweak rho to differentiate.
        from cbsrm.risk import GARCHDCCParams
        params = GARCHDCCParams(rho_bar=f["rho"])
        lrmes_out = LRMESMonteCarlo(
            params=params, n_paths=2000, seed=42,
        ).compute()
        lrmes = float(lrmes_out["lrmes"])
        srisk = calc.compute(
            firm=f["firm"],
            market_cap_W=f["W_bn"] * 1e9,
            book_debt_D=f["D_bn"] * 1e9,
            lrmes=lrmes,
        )
        rows.append({
            "Firm": f["firm"],
            "Market cap ($B)": f["W_bn"],
            "Book debt ($B)": f["D_bn"],
            "LRMES": round(lrmes, 4),
            "SRISK ($B)": round(srisk.srisk / 1e9, 2),
            "Status": "SHORTFALL" if srisk.is_shortfall else "surplus",
        })
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600, show_spinner=False)
def compute_synthetic_covar_mes() -> dict:
    from cbsrm.risk import DeltaCoVaREstimator, empirical_mes
    rng = np.random.RandomState(42)
    n = 2000
    rho = 0.75
    u = rng.normal(0, 0.01, (n, 2))
    L = np.array([[1.0, 0.0], [rho, np.sqrt(1.0 - rho ** 2)]])
    z = u @ L.T
    firm_ret, sys_ret = z[:, 0], z[:, 1]
    covar = DeltaCoVaREstimator(q=0.05).estimate(
        firm="synthetic_bank",
        firm_returns=firm_ret, system_returns=sys_ret,
    )
    mes = empirical_mes(firm_returns=firm_ret, market_returns=sys_ret, q=0.05)
    return {
        "delta_covar": float(covar.delta_covar),
        "beta_q": float(covar.beta_q),
        "mes": float(mes.mes),
        "var_q_market": float(mes.var_q_market),
        "n_tail_obs": int(mes.n_tail_obs),
        "n_total_obs": int(mes.n_total_obs),
        "rho": rho,
    }


# ─── UI helpers ─────────────────────────────────────────────────────────


def regime_badge(regime: str) -> str:
    fg, bg = REGIME_COLORS.get(regime, REGIME_COLORS["INSUFFICIENT_HISTORY"])
    return (
        f"<span style='background:{bg};color:{fg};padding:6px 14px;"
        f"border-radius:6px;font-weight:700;font-size:1.4em;letter-spacing:1px;"
        f"border:1px solid {fg}'>{regime}</span>"
    )


def render_no_key_banner() -> None:
    st.warning(
        "**FRED_API_KEY not set.** This dashboard needs a free FRED key to "
        "render live macro + stress numbers. Get one at "
        "https://fred.stlouisfed.org/docs/api/api_key.html and either export "
        "it as `FRED_API_KEY` or place it in a local `.env` file at the "
        "repo root, then refresh."
    )


# ─── Render ─────────────────────────────────────────────────────────────


def main() -> None:
    st.title("CBSRM — Live Financial-Stability Dashboard")
    st.markdown(
        "_Reproducible. Audit-traceable. Open-source (Apache 2.0)._  "
        "&nbsp;&nbsp;[github.com/pravo123/cbsrm](https://github.com/pravo123/cbsrm)"
    )
    st.caption(f"Rendered {datetime.utcnow().isoformat(timespec='seconds')}Z")

    has_key = bool(os.environ.get("FRED_API_KEY"))
    if not has_key:
        render_no_key_banner()

    st.divider()

    # ── Panel 1 — Macro composite ─────────────────────────────────────
    st.subheader("1. Macro regime composite — 4-state")
    if has_key:
        with st.spinner("Fetching FRED series + computing 4-state regime…"):
            try:
                comp = compute_macro_composite()
            except Exception as e:
                comp = {"error": f"{type(e).__name__}: {e}"}
        if "error" in comp:
            st.error(f"Macro composite unavailable: {comp['error']}")
        else:
            col_a, col_b = st.columns([1, 2])
            with col_a:
                st.markdown(regime_badge(comp["regime"]), unsafe_allow_html=True)
                score = comp.get("composite_score")
                if score is not None and not (isinstance(score, float) and np.isnan(score)):
                    st.metric("Composite score", f"{score:+.3f}", help="Range [-1, +1]; >=+0.4 = RISK_ON, <=-0.4 = RISK_OFF.")
                st.caption(f"As of {comp.get('last_date', 'n/a')}")
                ov = comp.get("overrides") or []
                if ov:
                    st.warning("Override triggers: " + ", ".join(ov))
                else:
                    st.caption("No hard-override triggers active.")
            with col_b:
                subs = comp.get("sub_scores") or {}
                if subs:
                    sub_df = pd.DataFrame({
                        "score": list(subs.values()),
                    }, index=list(subs.keys()))
                    st.bar_chart(sub_df, height=240)
    else:
        st.info("Macro composite skipped (no FRED key).")

    st.divider()

    # ── Panel 2 — Stress indicators ───────────────────────────────────
    st.subheader("2. Composite stress indicators")
    c1, c2, c3, c4 = st.columns(4)
    if has_key:
        with st.spinner("Fetching ECB CISS (EA / US / UK) + FRED STLFSI4…"):
            stress = {}
            for k, fn_args in [
                ("ECB CISS — EA", ("EA",)),
                ("ECB CISS — US", ("US",)),
                ("ECB CISS — UK", ("UK",)),
            ]:
                try:
                    stress[k] = compute_ecb_ciss(*fn_args)
                except Exception as e:
                    stress[k] = {"error": f"{type(e).__name__}: {e}"}
            try:
                stress["STLFSI4"] = compute_stlfsi()
            except Exception as e:
                stress["STLFSI4"] = {"error": f"{type(e).__name__}: {e}"}

        for col, label in zip(
            [c1, c2, c3, c4],
            ["ECB CISS — EA", "ECB CISS — US", "ECB CISS — UK", "STLFSI4"],
        ):
            r = stress.get(label, {})
            with col:
                if "error" in r:
                    st.metric(label, "—", help=r["error"])
                else:
                    st.metric(label, f"{r['value']:.4f}", help=f"as of {r['as_of']}")
    else:
        for col, label in zip([c1, c2, c3, c4], ["ECB CISS — EA", "ECB CISS — US", "ECB CISS — UK", "STLFSI4"]):
            with col:
                st.metric(label, "—", help="Set FRED_API_KEY to enable.")

    st.divider()

    # ── Panel 3 — Macro indicators ────────────────────────────────────
    st.subheader("3. Macro sub-indicators")
    m1, m2, m3, m4 = st.columns(4)
    if has_key:
        with st.spinner("Computing macro sub-indicators…"):
            try:
                comp_data = compute_macro_composite()
            except Exception as e:
                comp_data = {"error": str(e)}
            try:
                jpy = compute_jpy_regime()
            except Exception as e:
                jpy = {"error": str(e)}

        if "error" not in comp_data:
            sub = comp_data.get("sub_meta") or {}
            yc = sub.get("yield_curve", {})
            dxy = sub.get("dxy_regime", {})
            ffr = sub.get("ffr_change", {})

            p = yc.get("latest_recession_prob_12mo")
            with m1:
                if p is not None and not (isinstance(p, float) and np.isnan(p)):
                    st.metric("Yield-curve recession prob (12mo)", f"{p:.1%}",
                              help="NY-Fed Estrella-Mishkin probit from T10Y3M.")
                else:
                    st.metric("Yield-curve recession prob (12mo)", "—")

            with m2:
                if "error" not in jpy and jpy.get("z") is not None:
                    st.metric("USD/JPY z-score (252d)", f"{jpy['z']:+.2f}",
                              help=f"Regime: {jpy.get('regime', '—')} | level {jpy.get('level', float('nan')):.2f}")
                else:
                    st.metric("USD/JPY z-score (252d)", "—")

            with m3:
                z_dxy = dxy.get("latest_z_score")
                if z_dxy is not None and not (isinstance(z_dxy, float) and np.isnan(z_dxy)):
                    st.metric("DXY z-score (252d)", f"{z_dxy:+.2f}",
                              help=f"Regime: {dxy.get('regime', '—')}")
                else:
                    st.metric("DXY z-score (252d)", "—")

            with m4:
                bp = ffr.get("latest_composite_change_bp")
                if bp is not None and not (isinstance(bp, float) and np.isnan(bp)):
                    st.metric("FFR composite change (bp)", f"{bp:+.0f}",
                              help=f"Regime: {ffr.get('regime', '—')}")
                else:
                    st.metric("FFR composite change (bp)", "—")
        else:
            st.error(f"Macro sub-indicators unavailable: {comp_data['error']}")
    else:
        for col, label in zip(
            [m1, m2, m3, m4],
            ["Yield-curve recession prob (12mo)", "USD/JPY z-score (252d)", "DXY z-score (252d)", "FFR composite change (bp)"],
        ):
            with col:
                st.metric(label, "—", help="Set FRED_API_KEY to enable.")

    st.divider()

    # ── Panel 4 — SRISK panel ─────────────────────────────────────────
    st.subheader("4. SRISK panel — illustrative G-SIBs")
    st.caption(
        "**Illustrative only.** Market cap + book debt below are *approximate* "
        "ballpark figures. For live regulator-grade numbers, NYU Stern V-Lab "
        "publishes the canonical SRISK series."
    )
    with st.spinner("Running GJR-GARCH-DCC Monte Carlo (2000 paths × 3 firms, seed=42)…"):
        try:
            srisk_df = compute_srisk_panel()
            st.dataframe(srisk_df, use_container_width=True, hide_index=True)
            total = float(srisk_df["SRISK ($B)"].clip(lower=0.0).sum())
            st.caption(
                f"Σ positive SRISK = **${total:.2f}B**. SRISK > 0 means the firm "
                f"would need that much equity injection to remain solvent in the "
                f"simulated crisis (Brownlees-Engle 2017, k = 8%, horizon = 126 trading days, "
                f"market crisis threshold = -40%)."
            )
        except Exception as e:
            st.error(f"SRISK panel failed: {type(e).__name__}: {e}")

    st.divider()

    # ── Panel 5 — ΔCoVaR + MES synthetic ─────────────────────────────
    st.subheader("5. ΔCoVaR + MES — synthetic paired-return illustration")
    st.caption(
        "Methodology demo on a synthetic Gaussian pair "
        "(rho = 0.75, n = 2000, seed = 42). Replace with real firm + market "
        "returns to get publishable numbers."
    )
    with st.spinner("Estimating ΔCoVaR and MES…"):
        try:
            cm = compute_synthetic_covar_mes()
            a, b, c = st.columns(3)
            with a:
                st.metric("ΔCoVaR (q=0.05)", f"{cm['delta_covar']:+.4f}",
                          help="Adrian-Brunnermeier 2016. More negative = "
                               "larger systemic contribution.")
            with b:
                st.metric("MES (q=0.05)", f"{cm['mes']:+.4f}",
                          help="Empirical expected firm return on market-tail days.")
            with c:
                st.metric("Market VaR_q", f"{cm['var_q_market']:+.4f}",
                          help=f"Tail obs: {cm['n_tail_obs']} / {cm['n_total_obs']}")
        except Exception as e:
            st.error(f"ΔCoVaR / MES failed: {type(e).__name__}: {e}")

    st.divider()

    # ── Footer ─────────────────────────────────────────────────────────
    st.markdown(
        """
        #### Citations
        - Brownlees, C. & Engle, R.F. (2017). *SRISK: A Conditional Capital
          Shortfall Measure of Systemic Risk.* Rev. Financial Studies 30(1).
        - Adrian, T. & Brunnermeier, M.K. (2016). *CoVaR.* AER 106(7).
        - Acharya, V.V., Pedersen, L.H., Philippon, T., Richardson, M. (2017).
          *Measuring Systemic Risk.* Rev. Financial Studies 30(1).
        - Hollo, D., Kremer, M., Lo Duca, M. (2012). *CISS — A Composite
          Indicator of Systemic Stress in the Financial System.* ECB WP 1426.
        - Estrella, A. & Mishkin, F.S. (1996). *The Yield Curve as a Predictor
          of US Recessions.* NY Fed Current Issues 2(7).

        **Reproduce:**
        ```bash
        git clone https://github.com/pravo123/cbsrm
        cd cbsrm
        pip install -e ".[all]" streamlit
        export FRED_API_KEY=your_key
        streamlit run dashboard/streamlit_app.py
        ```

        _Not investment advice. Educational use. Indicators are reproductions
        of published methodology. ECB CISS data &copy; European Central Bank;
        FRED data &copy; Federal Reserve Bank of St. Louis. Bank financial
        figures shown are approximate illustrations, not live filings._
        """
    )


if __name__ == "__main__":
    main()
