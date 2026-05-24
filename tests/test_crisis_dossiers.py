"""
Tests for cbsrm.diagnostics.crisis_dossiers — the deterministic
fixture-backed crisis-window research dossiers.
"""
from __future__ import annotations

import pytest

from cbsrm.diagnostics.crisis_dossiers import (
    CRISIS_DOSSIER_WINDOWS,
    DOSSIER_VERSION,
    FIXTURE_VERSION,
    build_crisis_dossier,
    get_fixture_snapshot,
    list_dossier_windows,
)
from cbsrm.macro.phase_classifier import PHASE_LABELS, RISK_POSTURES


# ─── Constants / registry ──────────────────────────────────────────


def test_supported_windows_exact():
    assert set(CRISIS_DOSSIER_WINDOWS) == {"2008Q4", "2020Q1", "2023Q1"}


def test_list_dossier_windows_returns_sorted_canonical_set():
    assert list_dossier_windows() == ["2008Q4", "2020Q1", "2023Q1"]


# ─── Required output schema ────────────────────────────────────────


REQUIRED_TOP_LEVEL_KEYS = {
    "window_id", "title", "period", "shock_summary",
    "macro_event_scores", "replay_summary", "network_stress_summary",
    "phase_label", "dominant_drivers", "risk_posture",
    "research_notes", "spec",
}


@pytest.mark.parametrize("window_id", ["2008Q4", "2020Q1", "2023Q1"])
def test_dossier_schema_complete(window_id):
    d = build_crisis_dossier(window_id)
    missing = REQUIRED_TOP_LEVEL_KEYS - set(d.keys())
    assert not missing, f"{window_id}: missing keys {missing}"
    assert d["window_id"] == window_id
    assert isinstance(d["title"], str) and d["title"]
    assert set(d["period"].keys()) == {"start", "end"}
    assert isinstance(d["shock_summary"], str) and d["shock_summary"]
    assert isinstance(d["research_notes"], str) and d["research_notes"]
    assert d["phase_label"] in PHASE_LABELS
    assert d["risk_posture"] in RISK_POSTURES


# ─── Phase classifier integration ──────────────────────────────────


def test_2008q4_phase_is_financial_stress():
    d = build_crisis_dossier("2008Q4")
    assert d["phase_label"] == "financial_stress"
    assert d["risk_posture"] == "stress_mitigation"


def test_2020q1_phase_is_financial_stress_via_volatility():
    d = build_crisis_dossier("2020Q1")
    assert d["phase_label"] == "financial_stress"
    # volatility_z must be a dominant driver in this window
    assert "volatility_z" in d["dominant_drivers"]


def test_2023q1_phase_is_NOT_financial_stress():
    """The point of the 2023Q1 window: macro looks benign; stress is hidden
    in the network. Phase classifier should NOT auto-trigger financial_stress.
    """
    d = build_crisis_dossier("2023Q1")
    assert d["phase_label"] != "financial_stress"


def test_dominant_drivers_is_list_of_strings():
    for w in CRISIS_DOSSIER_WINDOWS:
        d = build_crisis_dossier(w)
        assert isinstance(d["dominant_drivers"], list)
        for x in d["dominant_drivers"]:
            assert isinstance(x, str)


# ─── DebtRank / network stress integration ────────────────────────


@pytest.mark.parametrize("window_id", ["2008Q4", "2020Q1", "2023Q1"])
def test_network_stress_summary_shape(window_id):
    d = build_crisis_dossier(window_id)
    nss = d["network_stress_summary"]
    assert set(nss.keys()) == {
        "debt_rank", "iterations", "converged", "n_banks", "seed_node",
    }
    assert isinstance(nss["debt_rank"], float)
    assert 0.0 <= nss["debt_rank"] <= 1.0
    assert isinstance(nss["iterations"], int) and nss["iterations"] >= 1
    assert isinstance(nss["converged"], bool)
    assert isinstance(nss["n_banks"], int) and nss["n_banks"] == 4
    assert isinstance(nss["seed_node"], str) and nss["seed_node"]


def test_2008q4_higher_debt_rank_than_2020q1():
    """Banks were better capitalised post-Dodd-Frank — 2020Q1 fixture must
    produce a lower DebtRank than the 2008Q4 epicentre cascade."""
    a = build_crisis_dossier("2008Q4")["network_stress_summary"]["debt_rank"]
    b = build_crisis_dossier("2020Q1")["network_stress_summary"]["debt_rank"]
    assert a > b


def test_all_windows_debt_rank_strictly_positive():
    for w in CRISIS_DOSSIER_WINDOWS:
        dr = build_crisis_dossier(w)["network_stress_summary"]["debt_rank"]
        assert dr > 0.0


# ─── Macro-event scoring integration ──────────────────────────────


@pytest.mark.parametrize("window_id", ["2008Q4", "2020Q1", "2023Q1"])
def test_macro_event_scores_have_expected_schema(window_id):
    d = build_crisis_dossier(window_id)
    assert len(d["macro_event_scores"]) >= 3   # at least 3 prints per window
    for ev in d["macro_event_scores"]:
        # score_event output minus the "spec" block + release_date echoed in
        for key in ("event", "actual", "consensus", "surprise",
                    "surprise_z", "direction", "severity", "risk_bias",
                    "release_date"):
            assert key in ev, f"{window_id}: macro event missing {key}"


def test_2020q1_nfp_collapse_scored_as_cooler():
    """Mar 2020 NFP -701k vs +10k consensus → cooler_than_expected."""
    d = build_crisis_dossier("2020Q1")
    nfp_releases = [e for e in d["macro_event_scores"] if e["event"] == "NFP"]
    assert nfp_releases, "expected at least one NFP release in 2020Q1"
    assert nfp_releases[0]["direction"] == "cooler_than_expected"


# ─── Replay surface integration ───────────────────────────────────


@pytest.mark.parametrize("window_id", ["2008Q4", "2020Q1", "2023Q1"])
def test_replay_summary_nonempty(window_id):
    d = build_crisis_dossier(window_id)
    rs = d["replay_summary"]
    assert isinstance(rs, list) and len(rs) > 0
    sample = rs[0]
    for key in ("event", "date", "price_series", "pre_return", "post_return",
                "direction", "severity", "risk_bias"):
        assert key in sample, f"{window_id}: replay row missing {key}"


# ─── Spec / version metadata ──────────────────────────────────────


def test_spec_carries_version_metadata():
    d = build_crisis_dossier("2008Q4")
    assert d["spec"]["dossier_version"] == DOSSIER_VERSION
    assert d["spec"]["fixture_version"] == FIXTURE_VERSION
    assert "composition" in d["spec"] and "score_event" in d["spec"]["composition"]
    assert isinstance(d["spec"]["sources"], list) and d["spec"]["sources"]


def test_spec_echoes_caller_config():
    d = build_crisis_dossier("2008Q4", config={"replay_window_days": 5})
    assert d["spec"]["config"] == {"replay_window_days": 5}


# ─── Validation ────────────────────────────────────────────────────


def test_unknown_window_raises():
    with pytest.raises(ValueError, match="unknown crisis window"):
        build_crisis_dossier("1999Q4")


def test_unknown_window_in_snapshot_raises():
    with pytest.raises(ValueError, match="unknown crisis window"):
        get_fixture_snapshot("MADE_UP_WINDOW")


def test_get_fixture_snapshot_returns_copy():
    snap = get_fixture_snapshot("2008Q4")
    snap["phase_features"]["growth_z"] = 999.0
    fresh = get_fixture_snapshot("2008Q4")
    assert fresh["phase_features"]["growth_z"] != 999.0


# ─── Determinism ───────────────────────────────────────────────────


@pytest.mark.parametrize("window_id", ["2008Q4", "2020Q1", "2023Q1"])
def test_dossier_is_deterministic(window_id):
    a = build_crisis_dossier(window_id)
    b = build_crisis_dossier(window_id)
    # Stable surface fields
    for k in ("window_id", "title", "period", "shock_summary",
              "phase_label", "risk_posture", "dominant_drivers"):
        assert a[k] == b[k]
    assert a["network_stress_summary"] == b["network_stress_summary"]
    assert len(a["macro_event_scores"]) == len(b["macro_event_scores"])
    assert len(a["replay_summary"]) == len(b["replay_summary"])


# ─── No external I/O ──────────────────────────────────────────────


def test_module_imports_no_network_or_filesystem_clients():
    """Sanity check: the dossier module composes only the pure v0.8
    surfaces and stdlib + numpy + pandas. No urllib/requests/httpx/socket
    or sqlite3/sqlalchemy clients should be reachable from a fresh import.
    """
    import cbsrm.diagnostics.crisis_dossiers as m
    src = open(m.__file__, encoding="utf-8").read()
    for forbidden in ("urllib", "requests", "httpx", "socket",
                      "sqlite3", "sqlalchemy", "urlopen", "subprocess"):
        assert forbidden not in src, (
            f"crisis_dossiers.py must not reference {forbidden!r}; "
            "the dossier is offline-only by design."
        )


# ─── Fixture-override path ────────────────────────────────────────


def test_fixture_override_path_used_when_supplied():
    """The `fixtures=` override is the test-injection seam; using it must
    bypass the pinned registry."""
    # Use an empty override registry and a name that DOES exist in the
    # pinned set — should still raise because the override registry is
    # what gets looked up.
    with pytest.raises(ValueError, match="unknown crisis window"):
        build_crisis_dossier("2008Q4", fixtures={})


# ─── Phase / posture / driver narrative checks ────────────────────


def test_dossier_research_notes_explains_2023q1_macro_vs_network_split():
    """Operator-facing narrative integrity — the 2023Q1 notes must call
    out the 'macro looks benign, network reveals fragility' framing."""
    notes = build_crisis_dossier("2023Q1")["research_notes"].lower()
    assert "macro" in notes
    assert "network" in notes or "debtrank" in notes or "regional" in notes
