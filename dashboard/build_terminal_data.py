"""
build_terminal_data.py — deterministic data bundle for the CBSRM Risk Terminal
==============================================================================

Generates ``cbsrm_terminal_data.json`` — the single, fully-offline, audit-grade
data payload that the self-contained ``cbsrm_terminal.html`` dashboard embeds.

Every number is computed from the canonical ``cbsrm`` public classes (the same
ones the CLI and FastAPI use), so the dashboard is reproducible bit-for-bit:

    python dashboard/build_terminal_data.py

Surfaces captured (all deterministic / seeded — no FRED key, no network):

  * Crisis-window dossiers      2008Q4 / 2020Q1 / 2023Q1
      - macro phase z-scores, phase classification, dominant drivers
      - DebtRank network-contagion summary
      - macro-event surprise scores + replay returns
  * SRISK panel (Brownlees-Engle) for three illustrative G-SIBs, k=8%,
    horizon=126d, crisis threshold=-40%, GJR-GARCH-DCC LRMES Monte Carlo
    (n_paths=2000, seed=42)
  * ΔCoVaR (Adrian-Brunnermeier) + MES (Acharya et al.) on a seeded
    synthetic paired-return illustration (rho=0.75, n=2000, seed=42)
  * A real SHA-256 audit hash-chain over the three crisis-dossier exports
    (cbsrm.audit.AuditChain), with chain-integrity verification

NOT investment advice. Governance / financial-stability measurement only.
Apache-2.0 — see ../LICENSE.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

import cbsrm
from cbsrm.audit.chain import AuditChain
from cbsrm.diagnostics import build_crisis_dossier, list_dossier_windows
from cbsrm.reporting import (
    build_macro_composite_report,
    build_report_manifest,
    build_report_payload,
    stamp_manifest_to_chain,
)
from cbsrm.risk import (
    DeltaCoVaREstimator,
    GARCHDCCParams,
    LRMESMonteCarlo,
    SRISKCalculator,
    empirical_mes,
)

# Illustrative G-SIB balance sheets (approximate 2026 ballpark, $B). These are
# clearly-labelled illustrations in the UI, not live filings — identical to the
# figures used in dashboard/streamlit_app.py so all front-ends agree.
GSIBS = [
    {"firm": "JPM", "name": "JPMorgan Chase", "W_bn": 580.0, "D_bn": 3400.0, "rho": 0.78},
    {"firm": "BAC", "name": "Bank of America", "W_bn": 305.0, "D_bn": 2700.0, "rho": 0.82},
    {"firm": "C", "name": "Citigroup", "W_bn": 135.0, "D_bn": 2300.0, "rho": 0.80},
]

SRISK_K = 0.08
SRISK_HORIZON_DAYS = 126
SRISK_CRISIS_THRESHOLD = -0.40
MC_PATHS = 2000
MC_SEED = 42
COVAR_RHO = 0.75
COVAR_N = 2000
COVAR_SEED = 42
COVAR_Q = 0.05


def _srisk_panel() -> dict[str, Any]:
    """SRISK for the illustrative G-SIBs (deterministic, seeded MC)."""
    calc = SRISKCalculator(k=SRISK_K)
    rows = []
    for f in GSIBS:
        params = GARCHDCCParams(rho_bar=f["rho"])
        lr = LRMESMonteCarlo(params=params, n_paths=MC_PATHS, seed=MC_SEED).compute()
        lrmes = float(lr["lrmes"])
        s = calc.compute(
            firm=f["firm"],
            market_cap_W=f["W_bn"] * 1e9,
            book_debt_D=f["D_bn"] * 1e9,
            lrmes=lrmes,
        )
        rows.append(
            {
                "firm": f["firm"],
                "name": f["name"],
                "market_cap_bn": f["W_bn"],
                "book_debt_bn": f["D_bn"],
                "rho_bar": f["rho"],
                "lrmes": round(lrmes, 4),
                "srisk_bn": round(s.srisk / 1e9, 2),
                "is_shortfall": bool(s.is_shortfall),
                "crisis_frequency": round(float(lr["crisis_frequency"]), 4),
            }
        )
    total_positive = round(sum(max(0.0, r["srisk_bn"]) for r in rows), 2)
    return {
        "params": {
            "k": SRISK_K,
            "horizon_days": SRISK_HORIZON_DAYS,
            "crisis_threshold": SRISK_CRISIS_THRESHOLD,
            "n_paths": MC_PATHS,
            "seed": MC_SEED,
        },
        "firms": rows,
        "total_positive_srisk_bn": total_positive,
    }


def _covar_mes() -> dict[str, Any]:
    """ΔCoVaR + MES on a seeded synthetic Gaussian pair (deterministic)."""
    rng = np.random.RandomState(COVAR_SEED)
    u = rng.normal(0, 0.01, (COVAR_N, 2))
    L = np.array([[1.0, 0.0], [COVAR_RHO, np.sqrt(1.0 - COVAR_RHO**2)]])
    z = u @ L.T
    firm_ret, sys_ret = z[:, 0], z[:, 1]
    covar = DeltaCoVaREstimator(q=COVAR_Q).estimate(
        firm="synthetic_bank", firm_returns=firm_ret, system_returns=sys_ret
    )
    mes = empirical_mes(firm_returns=firm_ret, market_returns=sys_ret, q=COVAR_Q)
    return {
        "params": {"rho": COVAR_RHO, "n": COVAR_N, "seed": COVAR_SEED, "q": COVAR_Q},
        "delta_covar": round(float(covar.delta_covar), 5),
        "beta_q": round(float(covar.beta_q), 5),
        "mes": round(float(mes.mes), 5),
        "var_q_market": round(float(mes.var_q_market), 5),
        "n_tail_obs": int(mes.n_tail_obs),
        "n_total_obs": int(mes.n_total_obs),
    }


def _windows_and_audit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Per-window dossier + macro-composite data, plus a real audit hash-chain."""
    conn = sqlite3.connect(":memory:")
    chain = AuditChain(conn)
    windows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []

    for wid in list_dossier_windows():
        dossier_env = build_crisis_dossier(wid)
        dossier = dossier_env["dossier"] if "dossier" in dossier_env else dossier_env
        payload = build_report_payload(dossier_env)
        macro = build_macro_composite_report(wid)

        canonical = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        manifest = build_report_manifest(
            report_id="crisis-dossier",
            output_text=canonical,
            output_format="json",
            window_id=wid,
            source="python",
            dossier=dossier_env,
            payload=payload,
        )
        row = stamp_manifest_to_chain(chain, manifest)
        audit_rows.append(
            {
                "window_id": wid,
                "row_id": row["row_id"],
                "subject": row["subject"],
                "kind": row["kind"],
                "hash": row["hash"],
                "prev_hash": row["prev_hash"],
                "ts": row["ts"],
            }
        )

        windows.append(
            {
                "window_id": wid,
                "title": dossier["title"],
                "period": dossier["period"],
                "shock_summary": dossier["shock_summary"],
                "phase_label": dossier["phase_label"],
                "risk_posture": dossier["risk_posture"],
                "dominant_drivers": dossier["dominant_drivers"],
                "research_notes": dossier.get("research_notes"),
                "network_stress": dossier["network_stress_summary"],
                "macro_event_scores": dossier["macro_event_scores"],
                "replay_summary": dossier["replay_summary"],
                "phase_features": macro["phase_features"],
                "phase_classification": {
                    "phase": macro["phase_classification"]["phase"],
                    "score": macro["phase_classification"]["score"],
                    "risk_posture": macro["phase_classification"]["risk_posture"],
                    "dominant_drivers": macro["phase_classification"]["dominant_drivers"],
                    "rules_fired": macro["phase_classification"]["spec"]["rules_fired"],
                },
            }
        )

    ok, broken = chain.verify()
    audit = {
        "chain_ok": bool(ok),
        "broken_row_ids": list(broken),
        "algorithm": "SHA-256",
        "n_rows": len(audit_rows),
        "rows": audit_rows,
    }
    return windows, audit


def build_bundle() -> dict[str, Any]:
    windows, audit = _windows_and_audit()
    return {
        "schema_version": "1.0.0",
        "cbsrm_version": cbsrm.__version__,
        "license": "Apache-2.0",
        "disclaimer": (
            "Research / financial-stability measurement output from the CBSRM "
            "open-source library. NOT investment advice, NOT a recommendation "
            "to buy or sell any security, and NOT a regulated investment "
            "communication. All figures are illustrative and computed from "
            "public methodology; validate against live data before any use."
        ),
        "windows": windows,
        "srisk": _srisk_panel(),
        "covar_mes": _covar_mes(),
        "audit": audit,
    }


def main() -> None:
    bundle = build_bundle()

    # Determinism self-check: the *measurement content* must be byte-identical
    # run-to-run. The audit chain's row hash/prev_hash/ts are wall-clock-stamped
    # by AuditChain.append (each export is a distinct, live event) — so we strip
    # those from the comparison while keeping them in the emitted snapshot.
    def _content(b: dict[str, Any]) -> str:
        c = json.loads(json.dumps(b))
        for r in c["audit"]["rows"]:
            r["ts"] = r["hash"] = r["prev_hash"] = "<live>"
        return json.dumps(c, sort_keys=True)

    assert _content(bundle) == _content(build_bundle()), "non-deterministic content!"
    assert bundle["audit"]["chain_ok"], "audit chain failed to verify"

    out = Path(__file__).resolve().parent / "cbsrm_terminal_data.json"
    out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}  ({out.stat().st_size:,} bytes)")
    print(f"  cbsrm v{bundle['cbsrm_version']} | windows={len(bundle['windows'])} "
          f"| srisk firms={len(bundle['srisk']['firms'])} "
          f"| audit chain_ok={bundle['audit']['chain_ok']}")


if __name__ == "__main__":
    main()
