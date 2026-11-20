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


# ---------------- semáforo, noticias, funding ----------------
from datetime import datetime, timezone, timedelta
from richy.scorecard import scorecard
from richy import sentiment as snt
from richy.funding_paper import FundingPaper


def test_scorecard_waits_when_too_early_and_never_says_ready_with_losses(tmp_path):
    df = data.synthetic_ohlcv(1300)
    s = PaperSession(str(tmp_path / "p.json")); s.state["start"] = df.index[1100].isoformat()
    res = s.update(df, _strat(None, df))
    sc = scorecard(res, df, pd.Timestamp(s.state["start"]))
    assert sc["state"] == "wait" and "Muy pronto" in sc["verdict"]
    assert {c["key"] for c in sc["checks"]} >= {"days", "trades", "profit_factor", "sharpe", "max_drawdown", "vs_bh"}
    import json; json.dumps(sc)                                   # serializable para Firestore (sin inf/nan)


def test_scorecard_rejects_a_losing_bot_with_enough_sample():
    idx = pd.date_range("2024-01-01", periods=2000, freq="1h", tz="UTC")
    closed = pd.DataFrame({"close": 100.0}, index=idx)
    eq = pd.Series(10_000 * (1 - 0.0001 * np.arange(2000)), index=idx)
    res = {"equity": eq, "metrics": {"total_return": -0.2, "max_drawdown": -0.2, "sharpe": -2.0, "trades": 150, "profit_factor": 0.7, "win_rate": .3}}
    sc = scorecard(res, closed, idx[0])
    assert sc["state"] == "bad" and "No pasar a dinero real" in sc["verdict"]


def test_news_filter_pauses_on_extremes_and_clusters_of_risk_headlines():
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    h = lambda t, m: (now - timedelta(minutes=m), t)
    calm = snt.assess(50, [h("Bitcoin ETF inflows rise", 30)], now)
    assert not calm["pause"]
    assert snt.assess(6, [], now)["pause"] and snt.assess(95, [], now)["pause"]            # miedo / euforia extremos
    risky = snt.assess(50, [h("Exchange hacked, millions drained", 20), h("Regulator sues major crypto firm", 60)], now)
    assert risky["pause"] and "titulares de riesgo" in risky["reasons"][0]
    old = snt.assess(50, [h("Exchange hacked", 600), h("Firm sues rival", 700)], now)       # titulares viejos no cuentan
    assert not old["pause"]


def test_news_filter_fails_open_and_reports_it():
    def boom(url, timeout=8): raise OSError("sin red")
    r = snt.SentimentFilter(get=boom).check(1000.0)
    assert r["pause"] is False and r["ok"] is False


def test_news_filter_parses_rss_and_caches():
    rss = "<rss><channel><item><title>Exchange hack drains funds</title><pubDate>Thu, 01 Jan 2026 11:30:00 +0000</pubDate></item>" \
          "<item><title>Protocol exploit discovered</title><pubDate>Thu, 01 Jan 2026 11:40:00 +0000</pubDate></item></channel></rss>"
    calls = []
    def get(url, timeout=8):
        calls.append(url); return '{"data":[{"value":"40"}]}' if "alternative" in url else rss
    f = snt.SentimentFilter(ttl=900, get=get)
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc).timestamp()
    r = f.check(now); n = len(calls); f.check(now + 60)
    assert r["pause"] and r["fng"] == 40 and len(calls) == n          # segunda llamada usa la caché


def test_pause_freezes_flat_signals_for_new_bars_only(tmp_path):
    df = data.synthetic_ohlcv(1500)
    s = PaperSession(str(tmp_path / "p.json")); s.state["start"] = df.index[900].isoformat()
    a = s.update(df.iloc[:1200], _strat(None, df.iloc[:1200]))
    b = s.update(df, _strat(None, df), pause=True)                      # llega una noticia peligrosa
    assert all(t["entry_time"] <= df.index[1200] for t in b["trades"] if t["entry_time"] > df.index[1199])
    assert b["open"] is None or b["open"]["since"] <= df.index[1200]    # sin posiciones nuevas durante la pausa


def test_funding_backtest_has_no_lookahead_and_costs_matter():
    idx = pd.date_range("2024-01-01", periods=10, freq="8h", tz="UTC")
    f = pd.Series([0.0, 0.0, 0.001, 0.0, 0.0, 0, 0, 0, 0, 0], index=idx)       # un único pago alto en el paso 2
    r = backtest_funding_arb(f, 10_000, enter_above=0.0001, exit_below=0.0, cost=CostModel(fee=0, slippage=0))
    assert r["equity"].iloc[-1] == 10_000                                       # no puede cobrar el pago que lo hizo entrar
    steady = pd.Series(0.0003, index=pd.date_range("2024-01-01", periods=300, freq="8h", tz="UTC"))
    free = backtest_funding_arb(steady, 10_000, cost=CostModel(fee=0, slippage=0))["metrics"]["total_return"]
    paid = backtest_funding_arb(steady, 10_000, cost=CostModel(fee=0.001, slippage=0.001))["metrics"]["total_return"]
    assert free > paid > 0


def test_funding_paper_persists_and_reports(tmp_path):
    idx = pd.date_range("2024-01-01", periods=40, freq="8h", tz="UTC")
    f = pd.Series(0.0002, index=idx)
    fp = FundingPaper(str(tmp_path / "f.json")); a = fp.update(f.iloc[:20])
    b = FundingPaper(str(tmp_path / "f.json")).update(f)                       # reinicio: misma fecha de arranque
    assert a["since"] == b["since"] and b["periods"] > a["periods"]
    assert b["last_rate"] == 0.0002 and abs(b["apr"] - 0.0002 * 1095) < 1e-9


def test_csv_with_mixed_millisecond_timestamps_loads_as_datetimes(tmp_path):
    p = tmp_path / "f.csv"
    p.write_text("ts,rate\n2026-01-01 00:00:00+00:00,0.0001\n2026-01-01 08:00:00.005000+00:00,0.00012\n"
                 "2026-01-01 16:00:00+00:00,0.0001\n2026-01-02 00:00:00.003000+00:00,0.00009\n")
    f = data.read_csv_ts(str(p))["rate"]
    assert isinstance(f.index, pd.DatetimeIndex) and f.index.is_monotonic_increasing
    r = backtest_funding_arb(f)                       # el caso real que fallaba con 'str' - 'str'
    assert len(r["equity"]) == len(f) + 1


def test_scorecard_judges_defensive_strategy_by_return_per_risk():
    idx = pd.date_range("2024-01-01", periods=2000, freq="4h", tz="UTC")
    close = pd.Series(np.r_[np.linspace(100, 140, 1000), np.linspace(140, 91, 1000)], index=idx)       # mercado +/-: sube y se desploma
    closed = pd.DataFrame({"close": close})
    res = {"equity": pd.Series(10_000.0, index=idx), "metrics": {"total_return": -0.0, "max_drawdown": -0.02, "sharpe": 0.9,
           "trades": 40, "profit_factor": 1.4, "win_rate": .4}}
    sc = scorecard(res, closed, idx[0])
    vs = next(c for c in sc["checks"] if c["key"] == "vs_bh")
    assert vs["state"] == "ok"                      # rinde -0% con caída del 2% frente a un mercado que cayó mucho más


def test_funding_smoothing_cuts_churn_and_reports_costs():
    rng = np.random.default_rng(3)
    idx = pd.date_range("2024-01-01", periods=600, freq="8h", tz="UTC")
    noisy = pd.Series(0.0001 + rng.normal(0, 0.00012, 600), index=idx)                  # promedio positivo pero ruidoso
    raw = backtest_funding_arb(noisy, exit_below=0.0)
    smooth = backtest_funding_arb(noisy, exit_below=0.0, smooth=21)
    assert smooth["entries"] < raw["entries"]
    assert raw["costs"] > 0 and abs(raw["metrics"]["total_return"] - (raw["gross_funding"] - raw["costs"]) / 10_000) < 1e-9


def test_funding_analyze_runs_on_a_series():
    from richy.funding_paper import analyze
    idx = pd.date_range("2024-01-01", periods=400, freq="8h", tz="UTC")
    d = analyze(pd.Series(0.00012, index=idx))
    assert len(d["sweep"]) == 18 and d["stats"]["pct_positive"] == 1.0 and d["hold"]["ret"] > 0


def test_funding_monitor_flags_low_yield_and_strategy_flags_default_off():
    from richy.funding_paper import monitor
    from richy.cloud import NullSink
    idx = pd.date_range("2024-01-01", periods=120, freq="8h", tz="UTC")
    low = monitor(pd.Series(0.00003, index=idx)); high = monitor(pd.Series(0.0003, index=idx))
    assert not low["worth_it"] and high["worth_it"] and abs(low["apr_30d"] - 0.00003 * 1095) < 1e-9
    assert NullSink().strategy_flags(["trend", "funding"], defaults={"funding": False}) == {"trend": True, "funding": False}


# ---------------- modo --once (GitHub Actions): el estado vive en la nube ----------------
import json, time, types


class FakeCloud:
    """Firestore simulado: guarda estado, capital, operaciones y documentos de estado."""
    def __init__(self):
        self.store, self.eq, self.tr, self.docs, self.writes = {}, {}, {}, {}, 0

    def status(self, **kw): self.docs["current"] = kw
    def doc(self, name, **kw): self.docs[name] = kw
    def load_state(self, name): return json.loads(json.dumps(self.store[name])) if name in self.store else None
    def save_state(self, name, data): self.store[name] = json.loads(json.dumps(data))
    def equity_batch(self, pts):
        for ts, v in pts: self.eq[ts] = v; self.writes += 1
    def trade(self, t): self.tr[(t["entry_time"], t["exit_time"])] = t
    def strategy_flags(self, names, defaults=None): return {n: (defaults or {}).get(n, True) for n in names}


def _run_once(monkeypatch, tmp_path, cloud, df):
    from richy import cli
    class Feed:
        def parse_timeframe(self, tf): return 4 * 3600
    monkeypatch.chdir(tmp_path)                                   # sin disco compartido entre corridas
    monkeypatch.setattr(cli, "get_sink", lambda: cloud)
    monkeypatch.setattr(cli.data, "make_exchange", lambda *a, **k: Feed())
    monkeypatch.setattr(cli.data, "fetch_ohlcv_paged", lambda *a, **k: df)
    monkeypatch.setattr(cli.data, "fetch_funding_history", lambda *a, **k: (_ for _ in ()).throw(OSError("451")))
    args = types.SimpleNamespace(symbol="BTC/USDT", exchange="binance", timeframe="4h", real=False, mirror=None,
                                 no_news=True, strategy="trend", once=True, csv=None)
    cli.live(args)


def test_once_mode_continues_the_session_from_cloud_state_without_duplicating(monkeypatch, tmp_path):
    end = pd.Timestamp("2026-06-01 08:00", tz="UTC")              # vela de 4 h en curso en la primera corrida
    full = data.synthetic_ohlcv(1101, freq="4h").set_axis(pd.date_range(end=end + pd.Timedelta(hours=4), periods=1101, freq="4h"))
    from richy import cli
    now1 = end.timestamp() + 7 * 60                               # Actions corre 7 min después del cierre
    cloud = FakeCloud()
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    monkeypatch.setattr(cli.time, "time", lambda: now1)
    _run_once(monkeypatch, tmp_path / "a", cloud, full.iloc[:-1])
    start1 = cloud.store["paper"]["start"]; n1 = len(cloud.eq)
    assert cloud.docs["current"]["mode"] == "paper" and "scorecard" in cloud.docs["current"]
    monkeypatch.setattr(cli.time, "time", lambda: now1 + 4 * 3600)
    _run_once(monkeypatch, tmp_path / "b", cloud, full)           # 4 h después, "otra máquina": solo el estado en la nube
    assert cloud.store["paper"]["start"] == start1               # misma sesión, no empieza de cero
    assert len(cloud.eq) > n1 and cloud.writes == len(cloud.eq)   # llegó la vela nueva y ningún punto se reenvió
    assert cloud.docs["funding"]["error"]                        # funding bloqueado (451) no tumba el ciclo


def test_once_mode_refuses_a_session_with_another_timeframe(monkeypatch, tmp_path):
    end = pd.Timestamp("2026-06-01 08:00", tz="UTC")
    df = data.synthetic_ohlcv(1100, freq="4h").set_axis(pd.date_range(end=end, periods=1100, freq="4h"))
    cloud = FakeCloud(); cloud.store["paper"] = {"equity0": 10_000.0, "start": df.index[-50].isoformat(), "signals": {}, "tf": "1h"}
    from richy import cli
    monkeypatch.setattr(cli.time, "time", lambda: end.timestamp() + 420)
    with pytest.raises(SystemExit):
        _run_once(monkeypatch, tmp_path, cloud, df)
