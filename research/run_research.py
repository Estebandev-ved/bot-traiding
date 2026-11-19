"""
Experimento oficial y reproducible.   python -m research.run_research

Protocolo (fijado ANTES de mirar el tramo final):
  - Estrategia candidata declarada: ruptura Donchian-48 + filtro EMA200 en 4h, SL 2 ATR / TP 4 ATR / max 24 velas,
    con filtro ML (GBM) walk-forward. Es el centro de la meseta de parámetros del periodo de diseño, no el máximo.
  - DISEÑO: 2022-01-01 .. (hoy-365d). HOLDOUT (no usado para decidir nada): últimos 365 días.
  - Variantes de sensibilidad se reportan TODAS (no solo la mejor).
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

from .engine import Params
from .portfolio import buy_hold_equal, portfolio_backtest
from .walkforward import build_dataset, walk_forward

SYMS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
PRIMARY = dict(sl_atr=2.0, tp_atr=4.0, max_hold=24)
VARIANTS = {
    "PRIMARIA  SL2/TP4/H24": PRIMARY,
    "SL1.5/TP3/H24": dict(sl_atr=1.5, tp_atr=3.0, max_hold=24),
    "SL2/TP6/H48": dict(sl_atr=2.0, tp_atr=6.0, max_hold=48),
}


def fmt(m: dict) -> str:
    if not m or m.get("n_trades", 0) == 0:
        return "sin trades"
    return (f"n={m['n_trades']:3d} ret={m['total_return']:+7.1%} cagr={m['cagr']:+6.1%} dd={m['max_drawdown']:6.1%} "
            f"sharpe={m['sharpe']:5.2f} win={m['win_rate']:.0%} PF={m['profit_factor']:.2f} "
            f"avg/trade={m['avg_trade_net']:+.2%} p(avg<=0)={m['p_mean_le_0']:.2f}")


def main(holdout_days: int = 365, kind: str = "gbm", timeframe: str = "4h") -> dict:
    os.makedirs(OUT, exist_ok=True)
    now = pd.Timestamp.now(tz="UTC").floor("1D")
    hold_start = (now - pd.Timedelta(days=holdout_days)).strftime("%Y-%m-%d")
    design_start = "2022-01-01"
    results = {"holdout_start": hold_start, "kind": kind, "timeframe": timeframe, "variants": {}}
    store = {}
    for name, kw in VARIANTS.items():
        p = Params(**kw)
        ds = build_dataset(SYMS, timeframe, "breakout", p)
        oos = walk_forward(ds, kind, design_start, None)           # un único walk-forward continuo
        sel = oos[oos["p"] >= oos["th"]]
        raw = oos.assign(th=0.0)
        res = {}
        for seg, (a, b) in {"DISEÑO": (design_start, hold_start), "HOLDOUT": (hold_start, None)}.items():
            ml = portfolio_backtest(ds.frames, sel, p, a, b, 1000.0, max_positions=3)
            rw = portfolio_backtest(ds.frames, raw, p, a, b, 1000.0, max_positions=3)
            bh = buy_hold_equal(ds.frames, a, b)
            res[seg] = {"ml": ml["metrics"], "raw": rw["metrics"], "bh_return": float(bh.iloc[-1] / 1000 - 1)}
            store[(name, seg)] = (ml, rw, bh)
        results["variants"][name] = res
        print(f"\n### {name}")
        for seg in res:
            print(f"  [{seg}] B&H eq-weight: {res[seg]['bh_return']:+.1%}")
            print(f"     ML  : {fmt(res[seg]['ml'])}")
            print(f"     RAW : {fmt(res[seg]['raw'])}")
    # guardar trades/equity de la variante primaria
    for seg in ("DISEÑO", "HOLDOUT"):
        ml, rw, bh = store[("PRIMARIA  SL2/TP4/H24", seg)]
        ml["trades"].to_csv(os.path.join(OUT, f"trades_primaria_{seg}.csv"), index=False)
        ml["equity"].to_csv(os.path.join(OUT, f"equity_primaria_{seg}.csv"))
    with open(os.path.join(OUT, "resultados.json"), "w") as f:
        json.dump(results, f, indent=2, default=lambda o: None if isinstance(o, float) and np.isnan(o) else float(o) if isinstance(o, (np.floating, np.integer)) else str(o))
    return results


if __name__ == "__main__":
    main()
