"""
Crisis-replay analyzer — turn an indicator + a crisis window into a quantitative report.
=========================================================================================

For each canonical crisis episode (2008 GFC, 2020 COVID, 2023 SVB, etc.),
this module computes the salient statistics that the whitepaper §7
references:

  • baseline_pre        — mean of indicator in the 60-day window before the event
  • peak_value          — max indicator value within the crisis window
  • peak_date           — when the peak occurred
  • days_to_peak        — business-days from window start to peak
  • z_peak              — peak expressed as z-score against the pre-crisis distribution
  • recovery_value      — mean of indicator in the 60-day window after the event
  • drawdown_pct        — (peak − baseline) / baseline × 100
  • amplification       — peak / baseline (how many times baseline was the stress)
  • attribution         — per-subindex contribution to the peak (if subindex_values given)

Outputs render to markdown (for direct SSRN/working-paper inclusion) or
plain text (for terminal display). JSON-serializable.

USAGE
-----

    from cbsrm.diagnostics import CrisisReplay
    from cbsrm.diagnostics.crisis_replay import replay_all_windows

    rp = CrisisReplay(values=ofr_fsi_result.values,
                       subindex_values=ofr_fsi_result.subindex_values,
                       indicator_id="OFR-FSI")
    report = rp.replay("2020-covid")
    print(report.to_markdown())
    print(report.to_text())

    # Run all windows that fall inside the indicator's date range
    all_reports = replay_all_windows(rp)
    for name, r in all_reports.items():
        print(f"{name}: peak={r.peak_value:.3f} on {r.peak_date.date()} "
              f"(z={r.z_peak:+.1f}, amp={r.amplification:.1f}x)")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from cbsrm.diagnostics.replication import CRISIS_WINDOWS


# ─── Configuration ────────────────────────────────────────────────────


DEFAULT_PRE_WINDOW_DAYS = 60     # how many days before the window-start to average for baseline
DEFAULT_POST_WINDOW_DAYS = 60    # how many days after window-end to average for recovery


# ─── Report types ─────────────────────────────────────────────────────


@dataclass
class CrisisReplayReport:
    """One indicator × one crisis window."""
    indicator_id: str
    window_name: str
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    n_obs: int
    baseline_pre: float | None
    peak_value: float | None
    peak_date: pd.Timestamp | None
    days_to_peak: int | None
    z_peak: float | None
    recovery_value: float | None
    drawdown_pct: float | None
    amplification: float | None
    attribution: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "indicator_id": self.indicator_id,
            "window_name": self.window_name,
            "window_start": self.window_start.isoformat() if self.window_start is not None else None,
            "window_end": self.window_end.isoformat() if self.window_end is not None else None,
            "n_obs": self.n_obs,
            "baseline_pre": _round(self.baseline_pre),
            "peak_value": _round(self.peak_value),
            "peak_date": self.peak_date.isoformat() if self.peak_date is not None else None,
            "days_to_peak": self.days_to_peak,
            "z_peak": _round(self.z_peak),
            "recovery_value": _round(self.recovery_value),
            "drawdown_pct": _round(self.drawdown_pct, 1),
            "amplification": _round(self.amplification, 2),
            "attribution": {k: _round(v) for k, v in self.attribution.items()},
            "warnings": list(self.warnings),
        }

    def to_text(self) -> str:
        if self.peak_value is None:
            return (f"[{self.indicator_id}] {self.window_name}: insufficient data "
                    f"({self.n_obs} obs)")
        z_str = f"z={self.z_peak:+.2f}" if self.z_peak is not None else "z=n/a"
        amp_str = (f"{self.amplification:.2f}× baseline"
                   if self.amplification is not None else "amp=n/a")
        rec_str = (f"recovery={self.recovery_value:.3f}"
                   if self.recovery_value is not None else "recovery=n/a")
        return (
            f"[{self.indicator_id}] {self.window_name}: "
            f"peak={self.peak_value:.3f} on {self.peak_date.date()} "
            f"({self.days_to_peak} days in), {z_str}, {amp_str}, {rec_str}"
        )

    def to_markdown(self) -> str:
        """Render a markdown section for direct paper inclusion."""
        if self.peak_value is None:
            return (f"## {self.window_name} — {self.indicator_id}\n\n"
                    f"_Insufficient data ({self.n_obs} observations in window)._\n")
        lines = [
            f"## {self.window_name} — {self.indicator_id}",
            "",
            f"**Window:** {self.window_start.date()} → {self.window_end.date()}  ",
            f"**Observations:** {self.n_obs}",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Pre-crisis baseline (mean) | {self.baseline_pre:.4f}" if self.baseline_pre is not None else "| Pre-crisis baseline | _insufficient pre-window data_",
            f"| Peak value | **{self.peak_value:.4f}** |",
            f"| Peak date | {self.peak_date.date()} |",
            f"| Days from window start to peak | {self.days_to_peak} |",
            (f"| Peak z-score (vs. pre-crisis) | **{self.z_peak:+.2f}** |"
             if self.z_peak is not None else "| Peak z-score | _insufficient pre-window data_ |"),
            (f"| Amplification (peak / baseline) | **{self.amplification:.2f}×** |"
             if self.amplification is not None else "| Amplification | _insufficient pre-window data_ |"),
            (f"| Post-crisis recovery (mean) | {self.recovery_value:.4f} |"
             if self.recovery_value is not None else "| Post-crisis recovery | _insufficient post-window data_ |"),
        ]
        # Fix incomplete table row (the 'baseline' line above)
        lines = [line + " |" if line.endswith("baseline (mean) | " + f"{self.baseline_pre:.4f}")
                  and not line.endswith("|") else line
                  for line in lines]
        if self.attribution:
            lines.append("")
            lines.append("### Subindex contribution at peak")
            lines.append("")
            lines.append("| Subindex | Value at peak |")
            lines.append("|---|---|")
            for k, v in sorted(self.attribution.items(), key=lambda kv: -kv[1]):
                lines.append(f"| {k} | {v:.4f} |")
        if self.warnings:
            lines.append("")
            lines.append("**Notes:**")
            for w in self.warnings:
                lines.append(f"- {w}")
        return "\n".join(lines) + "\n"


# ─── Replay engine ───────────────────────────────────────────────────


class CrisisReplay:
    """Replay one indicator against any crisis window."""

    def __init__(
        self,
        values: pd.Series,
        subindex_values: pd.DataFrame | None = None,
        indicator_id: str = "indicator",
        pre_window_days: int = DEFAULT_PRE_WINDOW_DAYS,
        post_window_days: int = DEFAULT_POST_WINDOW_DAYS,
    ) -> None:
        if values is None or values.empty:
            raise ValueError("values must be a non-empty pandas Series")
        self.values = self._ensure_dt_index(values).sort_index()
        self.subindex_values = (
            self._ensure_dt_index(subindex_values).sort_index()
            if subindex_values is not None and not subindex_values.empty
            else None
        )
        self.indicator_id = indicator_id
        self.pre_window_days = pre_window_days
        self.post_window_days = post_window_days

    @staticmethod
    def _ensure_dt_index(obj):
        if not isinstance(obj.index, pd.DatetimeIndex):
            obj = obj.copy()
            obj.index = pd.to_datetime(obj.index, utc=True, errors="coerce")
        elif obj.index.tz is None:
            obj = obj.copy()
            obj.index = obj.index.tz_localize("UTC")
        return obj

    # ─── Public API ───────────────────────────────────────────────────

    def replay(self, window_name: str) -> CrisisReplayReport:
        """Replay one named window from CRISIS_WINDOWS."""
        if window_name not in CRISIS_WINDOWS:
            raise KeyError(
                f"unknown window {window_name!r}. "
                f"Available: {sorted(CRISIS_WINDOWS.keys())}"
            )
        start_iso, end_iso = CRISIS_WINDOWS[window_name]
        return self.replay_window(window_name, start_iso, end_iso)

    def replay_window(
        self, window_name: str, start_iso: str, end_iso: str,
    ) -> CrisisReplayReport:
        """Replay an arbitrary window (start_iso, end_iso)."""
        tz = self.values.index.tz
        win_start = pd.Timestamp(start_iso, tz=tz)
        win_end = pd.Timestamp(end_iso, tz=tz)

        warnings: list[str] = []

        # In-window observations
        in_win = self.values.loc[(self.values.index >= win_start) &
                                  (self.values.index <= win_end)]
        n_obs = int(len(in_win))

        if n_obs == 0:
            return CrisisReplayReport(
                indicator_id=self.indicator_id, window_name=window_name,
                window_start=win_start, window_end=win_end, n_obs=0,
                baseline_pre=None, peak_value=None, peak_date=None,
                days_to_peak=None, z_peak=None, recovery_value=None,
                drawdown_pct=None, amplification=None,
                warnings=["no observations inside window"],
            )

        peak_value = float(in_win.max())
        peak_date = in_win.idxmax()
        days_to_peak = int((peak_date - win_start).days)

        # Pre-crisis baseline
        pre_start = win_start - pd.Timedelta(days=self.pre_window_days)
        pre = self.values.loc[(self.values.index >= pre_start)
                               & (self.values.index < win_start)]
        if pre.size >= 2:
            baseline_pre = float(pre.mean())
            pre_std = float(pre.std(ddof=0))
            z_peak = ((peak_value - baseline_pre) / pre_std) if pre_std > 1e-12 else None
        elif pre.size == 1:
            baseline_pre = float(pre.iloc[0])
            z_peak = None
            warnings.append("only one pre-window observation; z-score unavailable")
        else:
            baseline_pre = None
            z_peak = None
            warnings.append(
                f"no pre-window observations (window start {win_start.date()} "
                f"is before earliest data {self.values.index.min().date()})"
            )

        # Post-crisis recovery
        post_end = win_end + pd.Timedelta(days=self.post_window_days)
        post = self.values.loc[(self.values.index > win_end)
                                & (self.values.index <= post_end)]
        if post.size >= 1:
            recovery_value = float(post.mean())
        else:
            recovery_value = None
            warnings.append("no post-window observations for recovery estimate")

        # Amplification + drawdown_pct
        amplification: float | None = None
        drawdown_pct: float | None = None
        if baseline_pre is not None and abs(baseline_pre) > 1e-9:
            amplification = peak_value / baseline_pre
            drawdown_pct = (peak_value - baseline_pre) / abs(baseline_pre) * 100.0
        elif baseline_pre is not None:
            # baseline ~ 0 — amplification undefined, drawdown_pct expressed differently
            warnings.append("baseline ~ 0; amplification not computed")

        # Subindex attribution at peak
        attribution: dict[str, float] = {}
        if self.subindex_values is not None:
            try:
                row = self.subindex_values.loc[peak_date]
                attribution = {str(k): float(v) for k, v in row.items()
                               if pd.notna(v)}
            except KeyError:
                # Peak date may not be in subindex frame (different cadence) — try asof
                try:
                    row = self.subindex_values.iloc[
                        self.subindex_values.index.get_indexer(
                            [peak_date], method="nearest"
                        )[0]
                    ]
                    attribution = {str(k): float(v) for k, v in row.items()
                                   if pd.notna(v)}
                    warnings.append(
                        "subindex attribution taken from nearest available date "
                        "(peak date not in subindex frame)"
                    )
                except Exception:
                    pass

        return CrisisReplayReport(
            indicator_id=self.indicator_id, window_name=window_name,
            window_start=win_start, window_end=win_end, n_obs=n_obs,
            baseline_pre=baseline_pre, peak_value=peak_value,
            peak_date=peak_date, days_to_peak=days_to_peak,
            z_peak=z_peak, recovery_value=recovery_value,
            drawdown_pct=drawdown_pct, amplification=amplification,
            attribution=attribution, warnings=warnings,
        )


# ─── Convenience entry ───────────────────────────────────────────────


def replay_all_windows(rp: CrisisReplay) -> dict[str, CrisisReplayReport]:
    """Run rp.replay() for every CRISIS_WINDOW that overlaps the indicator's range.

    Returns a dict {window_name: CrisisReplayReport}, ordered by window_start.
    """
    out: dict[str, CrisisReplayReport] = {}
    for name in CRISIS_WINDOWS:
        report = rp.replay(name)
        if report.n_obs > 0:
            out[name] = report
    return out


def replay_to_markdown_dossier(rp: CrisisReplay) -> str:
    """Run every replay and concatenate into a single markdown dossier."""
    reports = replay_all_windows(rp)
    sections = [
        f"# Crisis-replay dossier — {rp.indicator_id}",
        "",
        f"_Indicator date range: {rp.values.index.min().date()} → "
        f"{rp.values.index.max().date()}_  ",
        f"_Crisis windows scanned: {len(CRISIS_WINDOWS)}; "
        f"with overlap: {len(reports)}_",
        "",
        "## Summary",
        "",
        "| Episode | Peak | Date | z | Amp |",
        "|---|---|---|---|---|",
    ]
    for name, r in reports.items():
        if r.peak_value is None:
            continue
        z = f"{r.z_peak:+.2f}" if r.z_peak is not None else "n/a"
        amp = f"{r.amplification:.2f}×" if r.amplification is not None else "n/a"
        sections.append(
            f"| {name} | {r.peak_value:.3f} | {r.peak_date.date()} | {z} | {amp} |"
        )
    sections.append("")
    for r in reports.values():
        sections.append(r.to_markdown())
        sections.append("")
    return "\n".join(sections)


# ─── Helpers ──────────────────────────────────────────────────────────


def _round(v, n: int = 4):
    if v is None:
        return None
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return v
