"""
¿Combinar Richy (tendencia BTC) y Breakout 4h ayuda?   python -m research.run_portfolio_mix

Mide, fuera de muestra y con costos: correlación diaria entre ambos, y retorno / caída / Sharpe de 100 % Richy,
100 % Breakout, 50/50 y pesos por inverso de volatilidad. Si no se complementan, el gestor de portafolio solo es un
límite de riesgo común y no una fuente de retorno: mejor saberlo.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from ops.portfolio import combine_equity, inverse_vol_weights
from richy.backtest import run_backtest as richy_backtest
from richy.strategies import TrendATR

from .data import load_symbols
from .engine import Params
from .overlays import Overlays
from .portfolio import portfolio_backtest
from .run_research import OUT, PRIMARY, SYMS
from .walkforward import build_dataset, walk_forward


def stats(eq: pd.Series) -> dict:
    d = eq.resample("1D").last().dropna()
    r = d.pct_change().dropna()
    dd = float((d / d.cummax() - 1).min())
    sh = float(r.mean() / r.std() * np.sqrt(365)) if r.std() > 0 else 0.0
    return {"ret": float(d.iloc[-1] / d.iloc[0] - 1), "dd": dd, "sharpe": sh}


def main(holdout_days: int = 365) -> dict:
    now = pd.Timestamp.now(tz="UTC").floor("1D")
    hold = now - pd.Timedelta(days=holdout_days)
    design = pd.Timestamp("2022-01-01", tz="UTC")
    p = Params(**PRIMARY)
    ds = build_dataset(SYMS, "4h", "breakout", p)
    oos = walk_forward(ds, "gbm", "2022-01-01", None)
    sel = oos[oos["p"] >= oos["th"]]
    btc = load_symbols(["BTCUSDT"], "4h")["BTCUSDT"]
    out = {}
    for seg, (a, b) in {"DISEÑO": (design, hold), "HOLDOUT": (hold, None)}.items():
        bo = portfolio_backtest(ds.frames, sel, p, a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d") if b is not None else None,
                                1000.0, max_positions=3, overlays=Overlays())["equity"]
        end = b if b is not None else btc.index[-1] + pd.Timedelta(hours=4)
        sub = btc[(btc.index < end)]
        start_i = int(sub.index.searchsorted(a))
        rr = richy_backtest(sub, TrendATR(allow_short=False), interval="4h", start=start_i)
        ri = rr["equity"]
        ri = ri[ri.index >= a]
        curves = {"richy": ri / ri.iloc[0], "breakout": bo / bo.iloc[0]}
        daily = pd.DataFrame({k: c.resample("1D").last().dropna().pct_change() for k, c in curves.items()}).dropna()
        corr = float(daily["richy"].corr(daily["breakout"]))
        w_iv = inverse_vol_weights({k: daily[k].to_numpy() for k in daily}, shrink=0.5)
        mixes = {"100% Richy": {"richy": 1, "breakout": 0}, "100% Breakout": {"richy": 0, "breakout": 1},
                 "50/50": {"richy": .5, "breakout": .5}, f"inv-vol {w_iv['richy']:.0%}/{w_iv['breakout']:.0%}": w_iv}
        out[seg] = {"corr_diaria": corr, "mezclas": {}}
        print(f"\n[{seg}] correlación diaria Richy-Breakout: {corr:+.2f}")
        for name, w in mixes.items():
            sub_c = {k: c for k, c in curves.items() if w[k] > 0}
            eq = combine_equity(sub_c, {k: w[k] for k in sub_c})
            eq.index = pd.DatetimeIndex(eq.index)
            s = stats(eq)
            out[seg]["mezclas"][name] = s
            print(f"   {name:22} ret={s['ret']:+7.1%}  caída={s['dd']:7.1%}  Sharpe={s['sharpe']:5.2f}")
    with open(os.path.join(OUT, "mezcla_portafolio.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    return out


if __name__ == "__main__":
    main()
