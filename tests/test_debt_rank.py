"""
Tests for cbsrm.networks.debt_rank.

Validates the Battiston et al. (2012) DebtRank engine:
state-machine cascade, leverage normalization, invariants, error paths.
"""
from __future__ import annotations

import numpy as np
import pytest

from cbsrm.networks import debt_rank


# ─── Topology fixtures ──────────────────────────────────────────────


def _chain_2node():
    """Bank 1 lends 50 to bank 0; bank 1 has equity 100.

    Shocking bank 0 transmits distress upward to bank 1 via the L[1, 0]
    exposure.
    """
    L = np.array(
        [
            [0.0, 0.0],   # bank 0 has no exposures TO anyone
            [50.0, 0.0],  # bank 1 has 50 exposure TO bank 0
        ]
    )
    E = np.array([100.0, 100.0])
    return L, E


def _chain_3node():
    """0 ← 1 ← 2. Shocking 0 should propagate to 1 then to 2."""
    L = np.array(
        [
            [0.0, 0.0, 0.0],
            [50.0, 0.0, 0.0],  # 1's exposure TO 0
            [0.0, 50.0, 0.0],  # 2's exposure TO 1
        ]
    )
    E = np.array([100.0, 100.0, 100.0])
    return L, E


# ─── Cascade behaviour ──────────────────────────────────────────────


def test_two_node_chain_propagates_distress():
    L, E = _chain_2node()
    h0 = np.array([1.0, 0.0])
    out = debt_rank(L, E, h0)
    assert out["distress_final"][0] == pytest.approx(1.0)
    # bank 1 should receive 50/100 = 0.5 distress from bank 0
    assert out["distress_final"][1] == pytest.approx(0.5)
    assert out["debt_rank"] > 0.0
    assert out["converged"] is True


def test_three_node_chain_full_cascade():
    L, E = _chain_3node()
    h0 = np.array([1.0, 0.0, 0.0])
    out = debt_rank(L, E, h0)
    # 0 stays at 1; 1 receives 50/100=0.5 from 0; 2 then receives 50/100*0.5
    # = 0.25 from 1 in the next propagation step.
    h_final = out["distress_final"]
    assert h_final[0] == pytest.approx(1.0)
    assert h_final[1] == pytest.approx(0.5)
    assert h_final[2] == pytest.approx(0.25)
    assert out["debt_rank"] > 0.0
    assert out["iterations"] >= 2
    assert out["converged"] is True


def test_disconnected_graph_no_cascade():
    N = 4
    L = np.zeros((N, N))
    E = np.array([100.0, 100.0, 100.0, 100.0])
    h0 = np.array([0.3, 0.0, 0.0, 0.0])
    out = debt_rank(L, E, h0)
    # No edges → nobody else gets distressed, only the seeded node.
    np.testing.assert_allclose(out["distress_final"], h0)
    # DR = sum_i v_i * (h_final - h_init) = 0 since h_final == h_init.
    assert out["debt_rank"] == pytest.approx(0.0)


def test_zero_exposures_no_propagation():
    # Equity defined, but L still zero → identical to disconnected.
    N = 3
    L = np.zeros((N, N))
    E = np.array([50.0, 80.0, 60.0])
    h0 = np.array([0.5, 0.5, 0.0])
    out = debt_rank(L, E, h0)
    np.testing.assert_allclose(out["distress_final"], h0)
    assert out["debt_rank"] == pytest.approx(0.0)


# ─── Algebraic invariants ───────────────────────────────────────────


def test_scaling_invariance():
    """Scaling L and E by the same factor leaves W (and DR) unchanged."""
    L, E = _chain_3node()
    h0 = np.array([1.0, 0.0, 0.0])
    base = debt_rank(L, E, h0)
    scaled = debt_rank(L * 7.3, E * 7.3, h0)
    assert scaled["debt_rank"] == pytest.approx(base["debt_rank"])
    np.testing.assert_allclose(scaled["distress_final"], base["distress_final"])
    np.testing.assert_allclose(scaled["leverage_matrix"], base["leverage_matrix"])


def test_self_loop_ignored():
    """Setting L[i, i] = anything must not change the cascade."""
    L, E = _chain_3node()
    L_with_self = L.copy()
    L_with_self[0, 0] = 999.0
    L_with_self[1, 1] = 999.0
    h0 = np.array([1.0, 0.0, 0.0])
    base = debt_rank(L, E, h0)
    looped = debt_rank(L_with_self, E, h0)
    np.testing.assert_allclose(
        looped["distress_final"], base["distress_final"]
    )
    assert looped["debt_rank"] == pytest.approx(base["debt_rank"])


def test_custom_weights_emphasis_on_distressed_downstream():
    """Putting more economic weight on the downstream contagion path
    yields a larger DR than weighting upstream peers, holding the shock
    fixed.

    DebtRank only counts the *change* in distress, so the seed node
    contributes 0. The 3-node chain ``0 ← 1 ← 2`` with a shock on bank 0
    leaves bank 1 at distress 0.5 and bank 2 at 0.25. Weighting those
    two downstream nodes more heavily must give a strictly larger DR
    than concentrating weight on the (unchanged) seed.
    """
    L, E = _chain_3node()
    h0 = np.array([1.0, 0.0, 0.0])
    v_seed_heavy = np.array([0.9, 0.05, 0.05])  # weight on the seed (Δh=0)
    v_downstream = np.array([0.05, 0.475, 0.475])  # weight on Δh>0 nodes
    dr_seed = debt_rank(L, E, h0, v=v_seed_heavy)["debt_rank"]
    dr_down = debt_rank(L, E, h0, v=v_downstream)["debt_rank"]
    assert dr_down > dr_seed


def test_max_iter_reached_pathological_cascade():
    """A very long but very slow cascade must hit max_iter, converged=False."""
    # Construct a 30-node chain with tiny per-step impact and high tol
    # so propagation never quite stops within max_iter=2.
    N = 30
    L = np.zeros((N, N))
    for i in range(1, N):
        # bank i has a small exposure to bank i-1
        L[i, i - 1] = 5.0
    E = np.full(N, 100.0)
    h0 = np.zeros(N)
    h0[0] = 1.0
    out = debt_rank(L, E, h0, max_iter=2, tol=1e-15)
    assert out["iterations"] == 2
    assert out["converged"] is False


def test_converges_with_enough_iterations():
    """Same chain with plenty of iterations terminates cleanly."""
    N = 6
    L = np.zeros((N, N))
    for i in range(1, N):
        L[i, i - 1] = 30.0
    E = np.full(N, 100.0)
    h0 = np.zeros(N)
    h0[0] = 1.0
    out = debt_rank(L, E, h0, max_iter=100, tol=1e-12)
    assert out["converged"] is True
    # Each link multiplies distress by 0.3; after 5 hops, ≈ 0.3**5 = 0.00243
    assert out["distress_final"][-1] == pytest.approx(0.3 ** 5, rel=1e-6)


# ─── Validation / error paths ───────────────────────────────────────


def test_invalid_shape_nonsquare_L_raises():
    L = np.zeros((3, 4))
    E = np.array([1.0, 1.0, 1.0])
    h0 = np.array([0.0, 0.0, 0.0])
    with pytest.raises(ValueError, match="square"):
        debt_rank(L, E, h0)


def test_invalid_shape_E_length_mismatch_raises():
    L = np.zeros((3, 3))
    E = np.array([1.0, 1.0])
    h0 = np.array([0.0, 0.0, 0.0])
    with pytest.raises(ValueError, match="E must be shape"):
        debt_rank(L, E, h0)


def test_invalid_shape_h0_length_mismatch_raises():
    L = np.zeros((3, 3))
    E = np.array([1.0, 1.0, 1.0])
    h0 = np.array([0.0, 0.0])
    with pytest.raises(ValueError, match="h0 must be shape"):
        debt_rank(L, E, h0)


def test_negative_L_raises():
    L = np.array([[0.0, -1.0], [0.0, 0.0]])
    E = np.array([1.0, 1.0])
    h0 = np.array([0.0, 0.0])
    with pytest.raises(ValueError, match="non-negative"):
        debt_rank(L, E, h0)


def test_h0_out_of_bounds_raises():
    L = np.zeros((2, 2))
    E = np.array([1.0, 1.0])
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        debt_rank(L, E, np.array([1.5, 0.0]))
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        debt_rank(L, E, np.array([-0.1, 0.0]))


def test_negative_equity_clipped_with_warning():
    L = np.array([[0.0, 0.0], [10.0, 0.0]])
    E = np.array([100.0, -5.0])
    h0 = np.array([1.0, 0.0])
    with pytest.warns(RuntimeWarning, match="clipped"):
        out = debt_rank(L, E, h0)
    # bank 1 had its equity clipped to 0 ⇒ leverage row is zero ⇒ no impact.
    assert out["distress_final"][1] == pytest.approx(0.0)


def test_v_renormalized_with_warning():
    L = np.zeros((3, 3))
    E = np.array([1.0, 1.0, 1.0])
    h0 = np.array([0.0, 0.0, 0.0])
    v_bad = np.array([2.0, 2.0, 2.0])
    with pytest.warns(RuntimeWarning, match="renormalizing"):
        out = debt_rank(L, E, h0, v=v_bad)
    np.testing.assert_allclose(
        out["economic_weights"], np.array([1 / 3, 1 / 3, 1 / 3])
    )


def test_v_negative_raises():
    L = np.zeros((2, 2))
    E = np.array([1.0, 1.0])
    h0 = np.array([0.0, 0.0])
    with pytest.raises(ValueError, match="non-negative"):
        debt_rank(L, E, h0, v=np.array([-0.5, 1.5]))


def test_output_keys_present():
    L, E = _chain_2node()
    out = debt_rank(L, E, np.array([1.0, 0.0]))
    required = {
        "distress_final",
        "distress_initial",
        "debt_rank",
        "node_contributions",
        "iterations",
        "converged",
        "leverage_matrix",
        "economic_weights",
    }
    assert required.issubset(out.keys())
    assert out["leverage_matrix"].shape == (2, 2)
    assert out["economic_weights"].shape == (2,)


def test_leverage_matrix_diagonal_zero():
    L, E = _chain_3node()
    # Inject self-loop; verify W diagonal is still zero.
    L_loop = L.copy()
    np.fill_diagonal(L_loop, 500.0)
    out = debt_rank(L_loop, E, np.array([0.5, 0.0, 0.0]))
    W = out["leverage_matrix"]
    np.testing.assert_allclose(np.diag(W), np.zeros(3))


def test_debt_rank_sign_when_no_shock_is_zero():
    L, E = _chain_3node()
    h0 = np.zeros(3)
    out = debt_rank(L, E, h0)
    assert out["debt_rank"] == pytest.approx(0.0)
    np.testing.assert_allclose(out["distress_final"], h0)
