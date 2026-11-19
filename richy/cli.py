"""Uso:
  python -m richy.cli backtest   [--csv f.csv] [--strategy trend|meanrev|regime]
  python -m richy.cli walkforward [--csv f.csv]
  python -m richy.cli grid | funding
  python -m richy.cli live --symbol BTC/USDT --exchange binance [--real]   (paper por defecto)
"""
import argparse, json, os, time
import pandas as pd
from . import data
from .backtest import run_backtest, walk_forward, backtest_grid, backtest_funding_arb, CostModel
from .regime import get_regimes
from .risk import RiskConfig, RiskManager
from .strategies import TrendATR, MeanReversion, RegimeSwitched
from .cloud import get_sink


def real_csv(a, funding=False):
    """Solo datos reales: --csv o el archivo que baja `python -m richy.download`. Nunca inventa datos."""
    name = f"datos/{a.symbol.replace('/', '')}_{'funding' if funding else a.timeframe}.csv"
    path = a.csv if (a.csv and not funding) else name
    if not os.path.exists(path):
        raise SystemExit(f"No hay datos reales en {path}.\nBájalos primero:  python -m richy.download --symbol {a.symbol} "
                         f"--timeframe {a.timeframe} --bars 8000{' --funding' if funding else ''}")
    return path


def load(a):
    return pd.read_csv(real_csv(a), index_col=0, parse_dates=True)


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
    p.add_argument("--mirror", default=os.getenv("BINANCE_MIRROR"))
    p.add_argument("--no-news", action="store_true", help="desactiva el filtro de noticias")
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
        f = pd.read_csv(real_csv(a, funding=True), index_col=0, parse_dates=True)["rate"]
        r = backtest_funding_arb(f); show(f"Arbitraje de funding ({len(f)} pagos reales)", r["metrics"])
    else:
        live(a)


def _clean(d):
    """Firestore no acepta fechas de pandas, numpy ni inf/nan: lo deja todo en tipos simples."""
    import math
    if isinstance(d, dict):
        return {k: _clean(v) for k, v in d.items()}
    if isinstance(d, (list, tuple)):
        return [_clean(v) for v in d]
    if hasattr(d, "isoformat"):
        return d.isoformat()
    if isinstance(d, float) and not math.isfinite(d):
        return None
    return d.item() if hasattr(d, "item") else d


def live(a):
    """Paper trading en vivo (sin dinero). Cada ciclo: velas cerradas -> filtro de noticias ->
    simulación -> semáforo -> Firestore. Además simula el arbitraje de funding con datos reales."""
    from .paper import PaperSession
    from .scorecard import scorecard
    from .sentiment import SentimentFilter
    from .funding_paper import FundingPaper
    if a.real:
        raise SystemExit("El modo --real todavía no está habilitado: primero hay que validar la estrategia en paper.")
    sink = get_sink()
    feed = data.make_exchange(a.exchange, mirror=a.mirror)
    tf_s = feed.parse_timeframe(a.timeframe)
    session = PaperSession()
    risk = RiskManager(RiskConfig(), equity=session.state["equity0"])
    news = None if a.no_news else SentimentFilter()
    funding, fx, f_last, f_warned = FundingPaper(), None, 0.0, False
    sent_eq, sent_tr = set(), set()
    print(f"[paper] {a.symbol} {a.timeframe} · capital inicial {session.state['equity0']:,.0f} USDT · "
          f"noticias={'apagado' if news is None else 'activo'} · Ctrl+C para detener")
    while not risk.killed:
        try:
            df = data.fetch_ohlcv_paged(feed, a.symbol, a.timeframe, limit_total=1000)
            risk.api_ok()
        except Exception as e:
            risk.api_error(str(e)); print("[error datos]", str(e)[:120]); time.sleep(10); continue
        closed = df.iloc[:-1]                                      # la última vela sigue abierta: no se usa
        risk.check_data_age(time.time() - closed.index[-1].timestamp() - 2 * tf_s)
        risk.check_price(closed["close"].iloc[-2], closed["close"].iloc[-1])
        if risk.killed:
            break
        flags = sink.strategy_flags(["trend", "meanrev", "funding"])
        sent = news.check() if news else {"pause": False, "reasons": [], "fng": None, "headlines": [], "ok": False}
        res = session.update(closed, build(a, closed, enabled=flags), pause=sent["pause"])
        eq = res["equity"]
        new_pts = [(ts.timestamp(), v) for ts, v in eq.items() if ts.timestamp() not in sent_eq]
        if new_pts:
            sink.equity_batch(new_pts); sent_eq.update(t for t, _ in new_pts)
        for t in res["trades"]:
            key = (t["entry_time"], t["exit_time"])
            if key not in sent_tr:
                sink.trade(t); sent_tr.add(key)
        m, rk, op = res["metrics"], res["risk"], res["open"]
        card = scorecard(res, closed, pd.Timestamp(session.state["start"]))
        sink.status(**_clean(dict(symbol=a.symbol, mode="paper", equity=float(eq.iloc[-1]), total_return=m["total_return"],
                    max_drawdown=m["max_drawdown"], trades=m["trades"], killed=rk["killed"], kill_reason=rk["kill_reason"],
                    halted_today=rk["halted_today"], position=op, scorecard=card, sentiment=sent)))
        if flags.get("funding", True) and time.time() - f_last > 600:        # funding: cada 10 min, sin bloquear el bot
            f_last = time.time()
            try:
                fx = fx or data.make_exchange(a.exchange, futures=True)
                since = int((time.time() - 3 * 86400) * 1000)
                fs = data.fetch_funding_history(fx, a.symbol + ":" + a.symbol.split("/")[1], since_ms=since)
                if len(fs):
                    sink.doc("funding", **_clean({**funding.update(fs), "enabled": True, "error": None}))
                    f_warned = False
            except Exception as e:
                if not f_warned:
                    print("[funding] sin datos (si Binance da 451, usa una VPN o un VPS fuera de tu región):", str(e)[:100]); f_warned = True
                sink.doc("funding", error=str(e)[:160], enabled=True)
        elif not flags.get("funding", True):
            sink.doc("funding", enabled=False)
        print(f"[{closed.index[-1]}] capital={eq.iloc[-1]:,.2f} ret={m['total_return']:+.2%} ops={m['trades']} "
              f"pos={'LONG' if op and op['side']>0 else 'SHORT' if op else '-'} noticias={'PAUSA' if sent['pause'] else 'ok'} kill={rk['killed']}")
        time.sleep(60)
    print("KILL SWITCH:", risk.kill_reason)
    sink.status(killed=True, kill_reason=risk.kill_reason)


if __name__ == "__main__":
    main()
