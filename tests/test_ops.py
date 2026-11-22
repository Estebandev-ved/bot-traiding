import json
import numpy as np
import pandas as pd
import pytest

from ops import drift, health, portfolio as pf, runner
from ops.runner import MemoryOps, run_cycle

DAY = 86400.0
T0 = 1_800_000_000.0 - (1_800_000_000.0 % DAY)         # medianoche UTC


def sl(name, eq, eq0=100.0, expo=0.0, assets=None):
    return pf.Sleeve(name, eq, eq0, expo, assets or {})


# ------------------------------------------------------------------ portafolio
def test_combined_index_weights_and_missing_bot():
    cfg = pf.PortfolioConfig()
    assert pf.combined_index([sl("richy", 110), sl("breakout", 90)], cfg) == pytest.approx(1.0)
    assert pf.combined_index([sl("richy", 120)], cfg) == pytest.approx(1.2)          # un solo bot: pesa 100 %
    d, _ = pf.evaluate([], cfg, None, T0)
    assert d["allow_new"] and "sin datos" in d["warnings"][0]


def test_daily_loss_halts_until_next_day():
    cfg = pf.PortfolioConfig(max_daily_loss=0.03)
    _, st = pf.evaluate([sl("richy", 100), sl("breakout", 100)], cfg, None, T0)
    d, st = pf.evaluate([sl("richy", 94), sl("breakout", 100)], cfg, st, T0 + 3600)      # índice 0.97 -> -3 %
    assert not d["allow_new"] and "diaria" in d["reasons"][0]
    d, st = pf.evaluate([sl("richy", 94), sl("breakout", 100)], cfg, st, T0 + DAY + 60)   # día nuevo, sin pérdida nueva
    assert d["allow_new"]


def test_drawdown_halt_has_hysteresis():
    cfg = pf.PortfolioConfig(max_drawdown=0.15, max_daily_loss=0.9)
    st = None
    for i, v in enumerate([100, 105, 88]):                       # pico 1.05 -> 0.88 = -16 %
        d, st = pf.evaluate([sl("breakout", v)], cfg, st, T0 + i * DAY)
    assert not d["allow_new"] and "caída" in d["reasons"][0]
    d, st = pf.evaluate([sl("breakout", 97)], cfg, st, T0 + 3 * DAY)      # -7.6 %: aún no recupera la mitad
    assert not d["allow_new"]
    d, st = pf.evaluate([sl("breakout", 99)], cfg, st, T0 + 4 * DAY)      # -5.7 %: se reanuda
    assert d["allow_new"]


def test_exposure_and_concentration_only_warn_by_default():
    cfg = pf.PortfolioConfig()
    a, b = sl("richy", 100, expo=1.0, assets={"BTCUSDT": 1.0}), sl("breakout", 100, expo=0.34, assets={"BTCUSDT": 0.34})
    d, _ = pf.evaluate([a, b], cfg, None, T0)
    assert d["allow_new"] and d["assets"]["BTCUSDT"] == pytest.approx(0.67) and d["blocked_symbols"] == []
    assert any("concentración" in w for w in d["warnings"])
    d, _ = pf.evaluate([a, b], pf.PortfolioConfig(enforce_asset_cap=True), None, T0)
    assert d["blocked_symbols"] == ["BTCUSDT"] and d["allow_new"]
    d, _ = pf.evaluate([sl("richy", 100, expo=1.0), sl("breakout", 100, expo=1.0)], cfg, None, T0)
    assert any("exposición" in w for w in d["warnings"])


def test_gate_fails_open_and_blocks_when_fresh():
    now = T0 + 10
    assert pf.gate_allows(None, now)[0]
    assert pf.gate_allows({"allow_new": False, "updated": now - 13 * 3600}, now)[0]          # vieja: opera normal
    assert pf.gate_allows({"allow_new": True, "updated": now - 60}, now)[0]
    ok, why = pf.gate_allows({"allow_new": False, "reasons": ["x"], "updated": now - 60}, now)
    assert not ok and "x" in why
    assert not pf.gate_allows({"allow_new": True, "blocked_symbols": ["BTCUSDT"], "updated": now - 60}, now, "BTCUSDT")[0]
    assert pf.gate_allows({"allow_new": True, "blocked_symbols": ["BTCUSDT"], "updated": now - 60}, now, "ETHUSDT")[0]


def test_inverse_vol_weights_and_combine_equity():
    rng = np.random.default_rng(0)
    r = {"calm": rng.normal(0, 0.005, 200), "wild": rng.normal(0, 0.02, 200)}
    w = pf.inverse_vol_weights(r, shrink=1.0)
    assert w["calm"] > w["wild"] and sum(w.values()) == pytest.approx(1.0)
    assert pf.inverse_vol_weights(r, shrink=0.0) == {"calm": 0.5, "wild": 0.5}
    idx = pd.date_range("2025-01-01", periods=240, freq="1h", tz="UTC")
    a, b = pd.Series(np.linspace(100, 110, 240), idx), pd.Series(np.linspace(100, 90, 240), idx)
    mix = pf.combine_equity({"a": a, "b": b}, {"a": 1, "b": 1})
    assert 0.95 < mix.iloc[-1] < 1.05


# ------------------------------------------------------------------ deriva
def fake_closed(rets, eq0=100.0, size_frac=0.3):
    out, eq = [], eq0
    for r in rets:
        pnl = eq * size_frac * r
        eq += pnl
        out.append({"net_ret": r, "pnl": pnl, "equity_after": eq})
    return out


BASE_RNG = np.random.default_rng(4)
BASE = {"net_ret": list(BASE_RNG.normal(0.012, 0.05, 150)), "port_ret": list(BASE_RNG.normal(0.004, 0.017, 150))}


def test_drift_waits_with_few_trades_or_no_baseline():
    assert drift.drift_report(fake_closed([0.01] * 5), BASE)["state"] == "wait"
    assert drift.drift_report(fake_closed([0.01] * 50), None)["state"] == "wait"


def test_drift_ok_when_live_matches_backtest():
    live = list(np.random.default_rng(8).normal(0.012, 0.05, 60))
    assert drift.drift_report(fake_closed(live), BASE)["state"] == "ok"


def test_drift_flags_a_live_bot_that_loses_what_the_backtest_won():
    live = list(np.random.default_rng(9).normal(-0.02, 0.05, 60))
    d = drift.drift_report(fake_closed(live), BASE)
    assert d["state"] == "bad" and d["z_mean"] < -2.33 and d["alerts"] and d["live_dd"] < 0


def test_load_baseline_validates_file(tmp_path):
    p = tmp_path / "b.json"
    assert drift.load_baseline(str(p)) is None
    p.write_text(json.dumps({"net_ret": [0.1] * 5, "port_ret": [0.1] * 5}))
    assert drift.load_baseline(str(p)) is None                    # muy corta
    p.write_text(json.dumps(BASE))
    assert drift.load_baseline(str(p))["net_ret"]
    p.write_text("no es json")
    assert drift.load_baseline(str(p)) is None


# ------------------------------------------------------------------ salud
def test_bar_lag_hours():
    now = pd.Timestamp("2026-06-01 09:00", tz="UTC").timestamp()      # última vela 4h cerrada: la de las 04:00
    assert health.bar_lag_hours("2026-06-01T04:00:00+00:00", now) == 0
    assert health.bar_lag_hours("2026-06-01T00:00:00+00:00", now) == 4
    assert health.bar_lag_hours("2026-05-31 20:00:00+00:00", now) == 8
    assert health.bar_lag_hours(None, now) is None


def test_health_alerts_once_and_recovers_with_hysteresis():
    now = 1_000_000.0
    snap = lambda h: {"richy": {"updated": now - h * 3600}, "breakout": {"updated": now - 3600, "last_bar": None}}
    ev, st = health.evaluate(snap(7), {}, now)
    assert [e["kind"] for e in ev] == ["down"] and st["richy_heartbeat"]
    ev, st = health.evaluate(snap(8), st, now)
    assert ev == []                                               # no repite
    ev, st = health.evaluate(snap(4), st, now)
    assert ev == []                                               # entre 3 h y 6 h: sigue «mal» sin parpadear
    ev, st = health.evaluate(snap(1), st, now)
    assert [e["kind"] for e in ev] == ["up"] and not st["richy_heartbeat"]


# ------------------------------------------------------------------ ciclo completo
class FakeTG:
    enabled, last_error, last_sent = True, None, None
    def __init__(self): self.sent = []
    def send(self, text, silent=False): self.sent.append(text); return True


def docs(now, richy_eq=10_000.0, bo_eq=25.0, bar="2026-06-01T04:00:00+00:00", upd_age=600):
    return {("status", "current"): {"equity": richy_eq, "equity0": 10_000.0, "exposure": 0.0, "assets": {}, "updated": now - upd_age},
            ("breakout_status", "current"): {"equity": bo_eq, "capital_initial": 25.0, "positions": [], "updated": now - upd_age,
                                              "last_bar": bar}}


NOW = pd.Timestamp("2026-06-01 09:00", tz="UTC").timestamp()


def test_cycle_healthy_publishes_open_gate_and_sends_nothing():
    st, tg = MemoryOps(docs(NOW)), FakeTG()
    r = run_cycle(st, tg, NOW, baseline=BASE)
    assert r["allow_new"] and tg.sent == []
    assert st.written[("portfolio_status", "gate")]["allow_new"] is True
    assert st.written[("portfolio_status", "current")]["index"] == pytest.approx(1.0)


def test_cycle_halts_once_alerts_once_and_resumes():
    st, tg = MemoryOps(docs(NOW, bo_eq=15.0)), FakeTG()                 # Breakout -40 % -> índice 0.8
    r = run_cycle(st, tg, NOW, baseline=BASE)
    assert not r["allow_new"] and len(tg.sent) == 1 and "pausa" in tg.sent[0]
    assert st.written[("portfolio_status", "gate")]["allow_new"] is False
    run_cycle(st, tg, NOW + 3600, baseline=BASE)
    assert len(tg.sent) == 1                                            # no repite
    st.docs = {**st.docs, **docs(NOW + 7200, bo_eq=25.0)}
    r = run_cycle(st, tg, NOW + 7200, baseline=BASE)
    assert r["allow_new"] and len(tg.sent) == 2 and "reanudado" in tg.sent[1]


def test_cycle_observation_mode_never_blocks_nor_announces_a_pause():
    st, tg = MemoryOps(docs(NOW, bo_eq=15.0), flags={"portfolio_enforce": False}), FakeTG()
    r = run_cycle(st, tg, NOW, baseline=BASE)
    assert r["allow_new"] and not any("pausa" in m for m in tg.sent)
    assert st.written[("portfolio_status", "current")]["reasons"]       # el motivo sí queda registrado


def test_cycle_detects_stuck_bars_and_stale_heartbeat():
    st, tg = MemoryOps(docs(NOW, bar="2026-05-31T12:00:00+00:00", upd_age=8 * 3600)), FakeTG()
    r = run_cycle(st, tg, NOW, baseline=BASE)
    assert r["health_events"] == 3 and len(tg.sent) == 3
    assert any("velas atrasadas" in m for m in tg.sent) and any("ciclos saltados" in m for m in tg.sent)


def test_cycle_drift_alert_is_sent_once():
    bad = fake_closed(list(np.random.default_rng(9).normal(-0.02, 0.05, 60)))
    st, tg = MemoryOps(docs(NOW), closed=bad), FakeTG()
    run_cycle(st, tg, NOW, baseline=BASE)
    run_cycle(st, tg, NOW + 3600, baseline=BASE)
    assert sum("deriva" in m for m in tg.sent) == 1


def test_cycle_failed_telegram_is_retried_next_cycle():
    class Down(FakeTG):
        def send(self, text, silent=False): return False
    st = MemoryOps(docs(NOW, bo_eq=15.0))
    run_cycle(st, Down(), NOW, baseline=BASE)
    tg = FakeTG()
    run_cycle(st, tg, NOW + 3600, baseline=BASE)
    assert any("pausa" in m for m in tg.sent)


def test_old_breakout_doc_without_exposure_fields_is_handled():
    d = docs(NOW)
    d[("breakout_status", "current")]["positions"] = [{"symbol": "BTCUSDT", "size": 10.0}]
    r = run_cycle(MemoryOps(d), FakeTG(), NOW, baseline=BASE)
    assert "breakout" in r["sleeves"]
