import numpy as np, pandas as pd, pytest
from richy import data, indicators as ind
from richy.risk import RiskManager, RiskConfig
from richy.backtest import run_backtest, walk_forward, backtest_grid, backtest_funding_arb, CostModel
from richy.strategies import TrendATR, MeanReversion, RegimeSwitched
from richy.regime import rule_regime
from richy.execution import Executor, PaperExchange, reconcile, client_order_id


def test_position_size_respects_risk_and_exposure():
    rm = RiskManager(RiskConfig(risk_per_trade=0.01, max_exposure=1.0), 10_000)
    q = rm.position_size(10_000, entry=100, stop_dist=2)       # arriesga 100 USD -> 50 unidades = 5000 nocional
    assert q == pytest.approx(50)
    q2 = rm.position_size(10_000, 100, 0.1)                    # stop muy corto -> topado por exposición
    assert q2 * 100 <= 10_000 + 1e-6
    assert RiskManager(RiskConfig(risk_per_trade=0.5)).position_size(10_000, 100, 2) == pytest.approx(10_000 * 0.02 / 2)


def test_daily_loss_halts_then_resets_next_day():
    rm = RiskManager(RiskConfig(max_daily_loss=0.03), 10_000)
    rm.update(pd.Timestamp("2024-01-01 00:00"), 10_000)
    rm.update(pd.Timestamp("2024-01-01 10:00"), 9_650)
    assert rm.halted_today and not rm.can_open()
    rm.update(pd.Timestamp("2024-01-02 00:00"), 9_650)
    assert rm.can_open()


def test_kill_switch_triggers():
    rm = RiskManager(RiskConfig(max_drawdown_kill=0.2, max_api_errors=3, max_price_jump=0.1), 1000)
    rm.update(pd.Timestamp("2024-01-01"), 1000); rm.update(pd.Timestamp("2024-01-01 01:00"), 790)
    assert rm.killed
    r2 = RiskManager(RiskConfig(max_api_errors=3)); [r2.api_error("x") for _ in range(3)]
    assert r2.killed
    r3 = RiskManager(); assert not r3.check_price(100, 130) and r3.killed
    r4 = RiskManager(); assert not r4.check_data_age(9999) and r4.killed


def test_no_lookahead_in_backtest():
    """Cambiar el futuro no puede cambiar lo que se hizo antes."""
    df = data.synthetic_ohlcv(1500)
    a = run_backtest(df, TrendATR())["equity"]
    df2 = df.copy(); df2.iloc[1200:, :4] *= 1.5
    b = run_backtest(df2, TrendATR())["equity"]
    pd.testing.assert_series_equal(a.iloc[:1190], b.iloc[:1190])


def test_costs_reduce_returns():
    df = data.synthetic_ohlcv(3000)
    free = run_backtest(df, TrendATR(), cost=CostModel(fee=0, slippage=0, fill_prob=1))["metrics"]["total_return"]
    real = run_backtest(df, TrendATR(), cost=CostModel(fee=0.002, slippage=0.002, fill_prob=1))["metrics"]["total_return"]
    assert real < free


def test_risk_per_trade_bounds_losses():
    df = data.synthetic_ohlcv(4000)
    r = run_backtest(df, MeanReversion(), cost=CostModel(fee=0, slippage=0, fill_prob=1), risk=RiskConfig(risk_per_trade=0.01))
    worst = min((t["pnl"] for t in r["trades"]), default=0)
    assert worst > -10_000 * 0.05          # un stop nunca debería costar mucho más del 1% (con gaps, margen)


def test_walk_forward_windows_do_not_overlap():
    df = data.synthetic_ohlcv(3500)
    r = walk_forward(df, lambda **k: TrendATR(**k), {"fast": [10, 20], "slow": [50]}, train_bars=1200, test_bars=600)
    assert len(r["windows"]) >= 3
    for w in r["windows"]:
        assert w["train"][1] < w["test"][0]
    tests = [w["test"] for w in r["windows"]]
    assert all(tests[i][1] < tests[i + 1][0] for i in range(len(tests) - 1))


def test_regime_and_router():
    df = data.synthetic_ohlcv(3000)
    reg = rule_regime(df)
    assert set(reg.unique()) <= {"trend", "range", "volatile"} and reg.nunique() >= 2
    s = RegimeSwitched(regimes=reg, routes={"trend": TrendATR(), "range": MeanReversion()})
    assert run_backtest(df, s)["metrics"]["trades"] > 0
    off = RegimeSwitched(regimes=reg, routes={"trend": TrendATR(), "range": MeanReversion()}, enabled={"trend": False, "meanrev": False})
    assert run_backtest(df, off)["metrics"]["trades"] == 0      # botón del panel apagado


def test_grid_and_funding_run():
    df = data.synthetic_ohlcv(800, seed=3)
    c = df["close"].iloc[0]
    g = backtest_grid(df, c * 0.9, c * 1.1, 10)
    assert g["cycles"] >= 0 and np.isfinite(g["equity"]).all()
    f = backtest_funding_arb(data.synthetic_funding())
    assert f["metrics"]["total_return"] > -0.5
    neg = backtest_funding_arb(pd.Series(-0.001, index=pd.date_range("2024", periods=50, freq="8h")), enter_above=-1, exit_below=-2)
    assert neg["metrics"]["total_return"] < 0               # pagar funding negativo pierde


def test_retry_does_not_duplicate_orders():
    ex = PaperExchange(lose_response=True)                  # la orden llega, la respuesta se pierde
    e = Executor(ex, RiskManager(), sleep=lambda s: None)
    o = e.place_limit("BTC/USDT", "buy", 0.1, 30000, intent="buy-BTC-2024-01-01T00")
    assert len(ex.orders) == 1 and o["clientOrderId"] == client_order_id("buy-BTC-2024-01-01T00")


def test_retry_recovers_from_timeouts_and_kill_blocks_orders():
    ex = PaperExchange(fail_first=2)
    e = Executor(ex, RiskManager(), sleep=lambda s: None)
    e.place_limit("BTC/USDT", "buy", 0.1, 30000, "x"); assert len(ex.orders) == 1
    rm = RiskManager(); rm.kill("test")
    with pytest.raises(RuntimeError):
        Executor(PaperExchange(), rm).place_limit("BTC/USDT", "buy", 1, 1, "y")


def test_reconcile_finds_differences():
    assert reconcile({"BTC": 0.5}, {"BTC": 0.5}) == []
    d = reconcile({"BTC": 0.5}, {"BTC": 0.0, "ETH": 1.0})
    assert {x["symbol"] for x in d} == {"BTC", "ETH"}


# ---------------- paper trading ----------------
from richy.paper import PaperSession
from richy.regime import rule_regime


def _strat(enabled=None, df=None):
    return RegimeSwitched(regimes=rule_regime(df), routes={"trend": TrendATR(), "range": MeanReversion()}, enabled=enabled)


def test_open_position_is_kept_and_not_counted_as_trade():
    df = data.synthetic_ohlcv(1500)
    r = run_backtest(df, TrendATR(), close_at_end=False)
    assert all(t["reason"] != "end" for t in r["trades"])
    r2 = run_backtest(df, TrendATR())
    assert len(r2["trades"]) >= len(r["trades"])


def test_paper_is_deterministic_and_past_is_frozen(tmp_path):
    df = data.synthetic_ohlcv(1600)
    path = str(tmp_path / "paper.json")
    s = PaperSession(path, 10_000)
    s.state["start"] = df.index[900].isoformat()            # arranca a mitad del histórico
    a = s.update(df.iloc[:1200], _strat(None, df.iloc[:1200]))
    # más tarde: llegan 300 velas nuevas y el usuario APAGA todas las estrategias desde el panel
    b = s.update(df.iloc[:1500], _strat({"trend": False, "meanrev": False}, df.iloc[:1500]))
    common = a["equity"].index.intersection(b["equity"].index)
    pd.testing.assert_series_equal(a["equity"].loc[common].iloc[:-3], b["equity"].loc[common].iloc[:-3])   # el pasado no cambia
    done_a = {(t["entry_time"], t["exit_time"]) for t in a["trades"]}
    assert done_a <= {(t["entry_time"], t["exit_time"]) for t in b["trades"]}                              # no desaparecen operaciones
    # con todo apagado, las barras NUEVAS no abren posiciones nuevas
    new_entries = [t for t in b["trades"] if t["entry_time"] > df.index[1200]]   # la barra 1200 ejecuta la señal congelada de la 1199
    assert new_entries == []


def test_paper_state_survives_restart(tmp_path):
    df = data.synthetic_ohlcv(1300)
    path = str(tmp_path / "p.json")
    s1 = PaperSession(path); s1.state["start"] = df.index[800].isoformat()
    r1 = s1.update(df, _strat(None, df))
    r2 = PaperSession(path).update(df, _strat(None, df))      # reinicio: mismo estado, mismo resultado
    pd.testing.assert_series_equal(r1["equity"], r2["equity"])
    assert r1["open"] == r2["open"]


def test_paper_starts_at_initial_capital_and_respects_risk_limits(tmp_path):
    df = data.synthetic_ohlcv(1300)
    s = PaperSession(str(tmp_path / "q.json"), 5_000.0)
    r = s.update(df, _strat(None, df))
    assert r["equity"].iloc[0] == 5_000.0
    assert min(r["equity"]) > 0
