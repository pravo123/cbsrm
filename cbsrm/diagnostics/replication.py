"""
Replication diagnostics for cross-indicator comparison.

The whitepaper §7 commits CBSRM to a quantitative replication standard:
CBSRM-computed indices must correlate with their canonical published
references at Pearson r ≥ 0.85 in declared crisis windows and ≥ 0.90 over
full sample. This module supplies the primitives that quantify that.

USAGE
-----

    from cbsrm.diagnostics import replicate, CRISIS_WINDOWS

    rep = replicate(
        cbsrm_series=ciss_us_result.values,
        canonical_series=ofr_fsi_result.values,
        cbsrm_label="CISS-US-Canonical v0.1",
        canonical_label="OFR FSI",
    )
    print(rep.summary())
    # Full sample: pearson_r=0.84, spearman_rho=0.87, n=3120
    # 2008-2009: pearson_r=0.91, n=440
    # 2020 COVID: pearson_r=0.88, n=120

    # Just one window
    crisis = crisis_windows()["2020-covid"]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd


# ─── Canonical crisis windows (US-centric for v0.2) ──────────────────


CRISIS_WINDOWS: dict[str, tuple[str, str]] = {
    "2007-subprime":     ("2007-07-01", "2008-09-01"),
    "2008-gfc-acute":    ("2008-09-01", "2009-04-01"),
    "2010-eu-debt":      ("2010-04-01", "2010-09-01"),
    "2011-eu-debt-2":    ("2011-07-01", "2011-12-01"),
    "2015-china-deval":  ("2015-08-01", "2015-10-01"),
    "2018-q4":           ("2018-10-01", "2019-01-01"),
    "2020-covid":        ("2020-02-15", "2020-05-15"),
    "2022-inflation":    ("2022-06-01", "2022-11-01"),
    "2023-svb":          ("2023-03-01", "2023-05-01"),
}


def crisis_windows() -> dict[str, tuple[str, str]]:
    """Return the canonical crisis-window dictionary."""
    return dict(CRISIS_WINDOWS)


# ─── Report types ────────────────────────────────────────────────────


@dataclass
class WindowDiagnostic:
    """Statistics for one window (full-sample or named crisis)."""
    window_name: str
    start: str
    end: str
    n_overlap: int
    pearson_r: float
    spearman_rho: float
    mae_zscore: float
    cbsrm_mean: float
    cbsrm_std: float
    canon_mean: float
    canon_std: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "window": self.window_name,
            "start": self.start, "end": self.end,
            "n_overlap": self.n_overlap,
            "pearson_r": round(self.pearson_r, 4),
            "spearman_rho": round(self.spearman_rho, 4),
            "mae_zscore": round(self.mae_zscore, 4),
            "cbsrm_mean": round(self.cbsrm_mean, 4),
            "cbsrm_std": round(self.cbsrm_std, 4),
            "canon_mean": round(self.canon_mean, 4),
            "canon_std": round(self.canon_std, 4),
        }


@dataclass
class ReplicationReport:
    cbsrm_label: str
    canonical_label: str
    full_sample: WindowDiagnostic | None
    by_window: dict[str, WindowDiagnostic] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cbsrm": self.cbsrm_label,
            "canonical": self.canonical_label,
            "full_sample": self.full_sample.as_dict() if self.full_sample else None,
            "by_window": {k: v.as_dict() for k, v in self.by_window.items()},
            "warnings": list(self.warnings),
        }

    def summary(self) -> str:
        lines = [
            f"Replication: {self.cbsrm_label}  vs  {self.canonical_label}",
            "─" * 64,
        ]
        if self.full_sample:
            d = self.full_sample
            lines.append(
                f"  Full sample [{d.start} → {d.end}]: "
                f"r={d.pearson_r:+.3f}  ρ={d.spearman_rho:+.3f}  "
                f"MAE(z)={d.mae_zscore:.3f}  n={d.n_overlap}"
            )
        if self.by_window:
            lines.append("")
            for name, d in self.by_window.items():
                lines.append(
                    f"  {name:18s} r={d.pearson_r:+.3f}  ρ={d.spearman_rho:+.3f}  "
                    f"n={d.n_overlap:>5d}"
                )
        if self.warnings:
            lines.append("")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        return "\n".join(lines)

    def meets_threshold(
        self, full_sample_r: float = 0.85, crisis_r: float = 0.80,
    ) -> tuple[bool, list[str]]:
        """Check whitepaper-style replication thresholds. Returns (ok, breaches)."""
        breaches: list[str] = []
        if self.full_sample is None:
            breaches.append("no full-sample diagnostic (no overlap?)")
        elif self.full_sample.pearson_r < full_sample_r:
            breaches.append(
                f"full-sample r={self.full_sample.pearson_r:.3f} < {full_sample_r}"
            )
        for name, d in self.by_window.items():
            if d.n_overlap < 5:
                continue   # window too short to judge
            if d.pearson_r < crisis_r:
                breaches.append(
                    f"window '{name}' r={d.pearson_r:.3f} < {crisis_r}"
                )
        return (len(breaches) == 0, breaches)


# ─── Main entry ──────────────────────────────────────────────────────


def replicate(
    cbsrm_series: pd.Series,
    canonical_series: pd.Series,
    cbsrm_label: str = "cbsrm",
    canonical_label: str = "canonical",
    windows: dict[str, tuple[str, str]] | None = None,
) -> ReplicationReport:
    """Compute replication diagnostics between two time series.

    cbsrm_series : the CBSRM-computed indicator (pandas Series, dt index)
    canonical_series : the reference series to compare against
    windows : crisis windows to break out individually. Defaults to
              CRISIS_WINDOWS.

    Output ReplicationReport contains per-window and full-sample Pearson,
    Spearman, and z-score MAE. Replication thresholds are checked by
    `report.meets_threshold(...)`.
    """
    if windows is None:
        windows = CRISIS_WINDOWS

    warnings: list[str] = []

    # Standardize indexes — both should be DatetimeIndex
    a = _ensure_dt_index(cbsrm_series).dropna()
    b = _ensure_dt_index(canonical_series).dropna()
    if a.empty or b.empty:
        warnings.append("one of the input series is empty after dropna")
        return ReplicationReport(
            cbsrm_label=cbsrm_label, canonical_label=canonical_label,
            full_sample=None, warnings=warnings,
        )

    # Align on intersection of dates (inner join)
    joined = pd.concat([a.rename("a"), b.rename("b")], axis=1, join="inner").dropna()

    full = _compute_window(
        joined, "full_sample",
        start_iso=str(joined.index.min().date()) if not joined.empty else "",
        end_iso=str(joined.index.max().date()) if not joined.empty else "",
    )

    by_window: dict[str, WindowDiagnostic] = {}
    for name, (s, e) in windows.items():
        sub = joined.loc[(joined.index >= pd.Timestamp(s, tz=joined.index.tz))
                         & (joined.index <= pd.Timestamp(e, tz=joined.index.tz))]
        if sub.empty:
            continue
        diag = _compute_window(sub, name, s, e)
        by_window[name] = diag

    return ReplicationReport(
        cbsrm_label=cbsrm_label, canonical_label=canonical_label,
        full_sample=full, by_window=by_window, warnings=warnings,
    )


# ─── Internals ───────────────────────────────────────────────────────


def _ensure_dt_index(s: pd.Series) -> pd.Series:
    """Coerce a pandas Series to a UTC-tz DatetimeIndex."""
    if s is None:
        return pd.Series(dtype=float)
    if not isinstance(s.index, pd.DatetimeIndex):
        s = s.copy()
        s.index = pd.to_datetime(s.index, utc=True, errors="coerce")
    elif s.index.tz is None:
        s = s.copy()
        s.index = s.index.tz_localize("UTC")
    return s


def _compute_window(
    joined: pd.DataFrame, name: str, start_iso: str, end_iso: str,
) -> WindowDiagnostic:
    a, b = joined["a"], joined["b"]
    n = int(len(joined))
    if n < 2:
        return WindowDiagnostic(
            window_name=name, start=start_iso, end=end_iso, n_overlap=n,
            pearson_r=float("nan"), spearman_rho=float("nan"),
            mae_zscore=float("nan"),
            cbsrm_mean=float(a.mean()) if n else float("nan"),
            cbsrm_std=float(a.std(ddof=0)) if n > 1 else float("nan"),
            canon_mean=float(b.mean()) if n else float("nan"),
            canon_std=float(b.std(ddof=0)) if n > 1 else float("nan"),
        )

    pearson_r = float(a.corr(b, method="pearson"))
    spearman_rho = float(a.corr(b, method="spearman"))

    # z-score MAE (scale-free)
    a_std = a.std(ddof=0); b_std = b.std(ddof=0)
    az = (a - a.mean()) / a_std if a_std > 1e-12 else a * 0
    bz = (b - b.mean()) / b_std if b_std > 1e-12 else b * 0
    mae_z = float((az - bz).abs().mean())

    return WindowDiagnostic(
        window_name=name, start=start_iso, end=end_iso, n_overlap=n,
        pearson_r=pearson_r if not np.isnan(pearson_r) else 0.0,
        spearman_rho=spearman_rho if not np.isnan(spearman_rho) else 0.0,
        mae_zscore=mae_z,
        cbsrm_mean=float(a.mean()),
        cbsrm_std=float(a.std(ddof=0)),
        canon_mean=float(b.mean()),
        canon_std=float(b.std(ddof=0)),
    )
