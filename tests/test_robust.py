import numpy as np
import pytest

from research import robust


def _noise(n=200, mu=0.0, sd=0.02, seed=1):
    return np.random.default_rng(seed).normal(mu, sd, n)


def test_psr_is_high_for_clear_edge_and_unclear_for_noise():
    assert robust.psr(_noise(mu=0.01)) > 0.99
    assert 0.05 < robust.psr(_noise(mu=0.0, seed=3)) < 0.95
    assert robust.psr(_noise(mu=-0.01)) < 0.05


def test_psr_needs_enough_samples():
    assert np.isnan(robust.psr([0.01] * 5))
    assert np.isnan(robust.dsr([0.01] * 5, 10))


def test_deflated_sharpe_drops_with_more_trials():
    r = _noise(n=120, mu=0.004, seed=5)
    d1, d50 = robust.dsr(r, 1), robust.dsr(r, 50)
    assert d50 < d1 <= robust.psr(r) + 1e-9
    assert robust.expected_max_sharpe(1, 0.01) == 0.0
    assert robust.expected_max_sharpe(100, 0.01) > robust.expected_max_sharpe(10, 0.01) > 0


def test_monte_carlo_is_reproducible_and_ordered():
    r = _noise(mu=0.003)
    a, b = robust.monte_carlo(r, n_sims=500), robust.monte_carlo(r, n_sims=500)
    assert a == b
    assert a["ret_p5"] <= a["ret_p50"] <= a["ret_p95"]
    assert a["dd_p95"] <= a["dd_p50"] <= 0
    assert 0 <= a["p_loss"] <= 1 and 0 <= a["p_ruin"] <= 1


def test_monte_carlo_all_winners_never_loses_or_draws_down():
    a = robust.monte_carlo([0.01] * 40, n_sims=200)
    assert a["p_loss"] == 0 and a["dd_p95"] == 0.0 and a["ret_p5"] > 0


def test_monte_carlo_horizon_changes_the_spread():
    r = _noise(mu=0.0)
    short, long_ = robust.monte_carlo(r, horizon=20, n_sims=800), robust.monte_carlo(r, horizon=400, n_sims=800)
    assert (long_["ret_p95"] - long_["ret_p5"]) > (short["ret_p95"] - short["ret_p5"])


def test_robustness_short_sample_is_not_judged():
    r = robust.robustness([0.01, -0.01, 0.02])
    assert r["enough"] is False and "10 trades" in robust.verdict(r)


def test_robustness_summary_and_verdict_wording():
    good = robust.robustness(_noise(n=300, mu=0.01), n_trials=3)
    assert good["enough"] and good["psr"] > 0.99 and good["mc"]["ok"]
    assert "sólido" in robust.verdict(good)
    bad = robust.robustness(_noise(n=80, mu=-0.002, seed=9), n_trials=3)
    assert "Sin evidencia" in robust.verdict(bad)


def test_min_track_record_infinite_when_no_edge_and_shrinks_with_edge():
    assert robust.min_track_record(_noise(mu=-0.01)) == float("inf")
    weak, strong = robust.min_track_record(_noise(mu=0.002, seed=2)), robust.min_track_record(_noise(mu=0.01, seed=2))
    assert strong < weak


def test_bootstrap_ci_brackets_the_sample_sharpe():
    r = _noise(mu=0.005)
    lo, hi = robust.bootstrap_sharpe_ci(r)
    assert lo < robust.sharpe(r) < hi
