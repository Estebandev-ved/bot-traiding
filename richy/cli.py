"""Uso:
  python -m richy.cli backtest   [--csv f.csv] [--strategy trend|meanrev|regime]
  python -m richy.cli walkforward [--csv f.csv]
  python -m richy.cli grid | funding
  python -m richy.cli live --symbol BTC/USDT --exchange binance [--real]   (paper por defecto)
"""
import argparse, json, time
import pandas as pd
from . import data
from .backtest import run_backtest, walk_forward, backtest_grid, backtest_funding_arb, CostModel
from .regime import get_regimes
from .risk import RiskConfig, RiskManager
from .strategies import TrendATR, MeanReversion, RegimeSwitched
from .cloud import get_sink


def load(a):
    if a.csv:
        df = pd.read_csv(a.csv, index_col=0, parse_dates=True)
        return df
    return data.synthetic_ohlcv()


def build(a, df, enabled=None):
    if a.strategy == "trend":
        return TrendATR()
    if a.strategy == "meanrev":
        return MeanReversion()
    return RegimeSwitched(regimes=get_regimes(df), routes={"trend": TrendATR(), "range": MeanReversion()}, enabled=enabled)


def show(title, m):
    print(f"\n== {title} ==")
    print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()}, indent=2))


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["backtest", "walkforward", "grid", "funding", "live"])
    p.add_argument("--csv"); p.add_argument("--strategy", default="regime", choices=["trend", "meanrev", "regime"])
    p.add_argument("--symbol", default="BTC/USDT"); p.add_argument("--exchange", default="binance")
    p.add_argument("--timeframe", default="1h"); p.add_argument("--real", action="store_true")
    a = p.parse_args(argv)

    if a.cmd == "backtest":
        df = load(a); r = run_backtest(df, build(a, df), cost=CostModel())
        show(f"Backtest {a.strategy}", r["metrics"])
    elif a.cmd == "walkforward":
        df = load(a)
        r = walk_forward(df, lambda **k: TrendATR(**k), {"fast": [10, 20], "slow": [50, 100], "atr_mult": [2.0, 3.0]},
                         train_bars=1500, test_bars=500)
        for w in r["windows"]:
            print(w["test"][0].date(), w["params"], f"IS sharpe={w['in_sample_sharpe']:.2f}", f"OOS sharpe={w['oos']['sharpe']:.2f}", f"OOS ret={w['oos']['total_return']:.1%}")
        show("Walk-forward fuera de muestra", r["oos_metrics"])
    elif a.cmd == "grid":
        df = load(a); c = df["close"].iloc[0]
        r = backtest_grid(df.iloc[:800], c * 0.9, c * 1.1, 12)
        show("Grid", {**r["metrics"], "ciclos": r["cycles"]})
    elif a.cmd == "funding":
        r = backtest_funding_arb(data.synthetic_funding()); show("Arbitraje de funding", r["metrics"])
    else:
        live(a)


def live(a):
    """Bucle en vivo. Paper por defecto: solo con --real y claves coloca órdenes reales."""
    from .execution import Executor, PaperExchange, reconcile
    sink = get_sink()
    ex = data.make_exchange(a.exchange) if a.real else PaperExchange()
    feed = data.make_exchange(a.exchange)
    risk = RiskManager(RiskConfig(), equity=10_000.0)
    exe = Executor(ex, risk)
    pos = {}
    while not risk.killed:
        try:
            df = data.fetch_ohlcv_paged(feed, a.symbol, a.timeframe, limit_total=600)
            risk.api_ok()
        except Exception as e:
            risk.api_error(str(e)); time.sleep(10); continue
        age = time.time() - df.index[-1].timestamp()
        risk.check_data_age(age + 0 if a.timeframe == "1m" else max(0, age - 3600))
        risk.check_price(df["close"].iloc[-2], df["close"].iloc[-1])
        flags = sink.strategy_flags(["trend", "meanrev"])
        sig = build(a, df, enabled=flags).generate(df).iloc[-2]
        risk.update(df.index[-1], 10_000.0)
        sink.status(symbol=a.symbol, signal=int(sig["signal"]), killed=risk.killed, kill_reason=risk.kill_reason,
                    halted_today=risk.halted_today, mode="real" if a.real else "paper")
        print(f"[{df.index[-1]}] señal={int(sig['signal'])} kill={risk.killed}")
        time.sleep(60)
    print("KILL SWITCH:", risk.kill_reason)


if __name__ == "__main__":
    main()
