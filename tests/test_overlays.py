import numpy as np
import pandas as pd
import pytest

from research import overlays as ov

IDX = pd.date_range("2025-01-01", periods=2400, freq="4h", tz="UTC")     # 400 días


def frame(path):
    c = pd.Series(path, index=IDX)
    return pd.DataFrame({"open": c.shift(1).fillna(c), "high": c * 1.001, "low": c * 0.999, "close": c})


def btc_up_then_crash(crash_at=1800):
    p = 100 * np.exp(np.concatenate([np.linspace(0, 1.0, crash_at), np.linspace(1.0, 0.2, len(IDX) - crash_at)]))
    return frame(p)


def test_vol_mult_only_cuts_never_raises():
    assert ov.vol_mult(0.5) == ov.vol_mult(1.0) == ov.vol_mult(float("nan")) == ov.vol_mult(None) == 1.0
    assert ov.vol_mult(2.0) == pytest.approx(0.5)
    assert ov.vol_mult(1.25) == pytest.approx(0.8)
    assert ov.vol_mult(10.0, floor=0.5) == 0.5


def test_regime_follows_btc_daily_ema200_and_waits_for_history():
    r = ov.regime_series({"BTCUSDT": btc_up_then_crash()}, "btc_ema200d", IDX)
    assert not r.iloc[:6 * 150].any()                 # sin 200 días de historia no se opera
    assert r.iloc[6 * 250]                            # tendencia alcista consolidada
    assert not r.iloc[-1]                             # tras el desplome, fuera


def test_regime_has_no_lookahead():
    """El régimen en una vela no cambia si se recortan los datos futuros."""
    full = btc_up_then_crash()
    cut = 1700
    a = ov.regime_series({"BTCUSDT": full}, "btc_ema200d", IDX)
    b = ov.regime_series({"BTCUSDT": full.iloc[:cut]}, "btc_ema200d", IDX[:cut])
    pd.testing.assert_series_equal(a.iloc[:cut], b, check_names=False)


def test_regime_uses_only_closed_days():
    """Dentro de un día, el valor es el de la jornada ANTERIOR (la de hoy aún no cerró)."""
    r = ov.regime_series({"BTCUSDT": btc_up_then_crash()}, "btc_ema200d", IDX)
    day = r.groupby(r.index.date).nunique()
    assert (day == 1).all()


def test_regime_without_btc_is_permissive_and_flagged():
    assert ov.regime_series({"ETHUSDT": btc_up_then_crash()}, "btc_ema200d", IDX) is None
    assert ov.regime_ok(None, IDX[10]) is True
    ctx = ov.Context(ov.Overlays(), {"ETHUSDT": btc_up_then_crash()})
    assert ctx.missing_regime and ctx.allows(IDX[10])


def test_breadth_regime_and_unknown_mode():
    f = {"A": btc_up_then_crash(), "B": btc_up_then_crash()}
    r = ov.regime_series(f, "breadth", IDX)
    assert r.iloc[6 * 150] and not r.iloc[-1]
    with pytest.raises(ValueError):
        ov.regime_series(f, "magia", IDX)


def test_corr_mult_cuts_for_correlated_open_positions_and_respects_floor():
    rng = np.random.default_rng(0)
    base = rng.normal(0, 0.01, len(IDX))
    mk = lambda r: frame(100 * np.exp(np.cumsum(r)))
    frames = {"A": mk(base), "B": mk(base * 1.1), "C": mk(base * 0.9), "D": mk(rng.normal(0, 0.01, len(IDX)))}
    rets = ov.returns_frame(frames)
    ts = IDX[1000]
    assert ov.corr_mult(rets, ts, "A", []) == 1.0
    assert ov.corr_mult(rets, ts, "A", ["B"]) == pytest.approx(0.75)
    assert ov.corr_mult(rets, ts, "A", ["B", "C"]) == pytest.approx(0.5625)
    assert ov.corr_mult(rets, ts, "A", ["B", "C", "B"], floor=0.6) >= 0.6
    assert ov.corr_mult(rets, ts, "A", ["D"]) == 1.0                 # independiente: sin recorte
    assert ov.corr_mult(rets, IDX[10], "A", ["B"]) == 1.0            # historia insuficiente: sin recorte


def test_default_overlays_only_enable_what_the_lab_supports():
    o = ov.Overlays()
    assert o.regime == "btc_ema200d" and not o.vol_scale and not o.corr_scale and o.active


def test_overlays_roundtrip_off_and_describe():
    o = ov.Overlays()
    assert ov.Overlays.from_dict(o.to_dict()) == o
    assert ov.Overlays.from_dict({"regime": None, "zzz": 1}).regime is None       # claves desconocidas se ignoran
    assert not ov.Overlays.off().active and ov.Overlays.off().describe() == "sin overlays"
    assert "btc_ema200d" in o.describe()


def test_context_combines_vol_and_corr():
    base = np.random.default_rng(1).normal(0, 0.01, len(IDX))
    f = {"BTCUSDT": btc_up_then_crash(), "A": frame(100 * np.exp(np.cumsum(base))), "B": frame(100 * np.exp(np.cumsum(base * 1.2)))}
    ctx = ov.Context(ov.Overlays(vol_scale=True, corr_scale=True), f)
    assert ctx.size_mult(IDX[1500], "A", 1.0, []) == 1.0
    assert ctx.size_mult(IDX[1500], "A", 2.0, []) == pytest.approx(0.5)
    assert ctx.size_mult(IDX[1500], "A", 2.0, ["B"]) == pytest.approx(0.5 * 0.75)
    assert ov.Context(ov.Overlays.off(), f).size_mult(IDX[1500], "A", 3.0, ["B"]) == 1.0
