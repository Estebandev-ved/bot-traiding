"""
Portafolio con CAPITAL COMPARTIDO (lo que realmente pasa con una cuenta pequeña):
  * máx. K posiciones simultáneas entre todos los activos
  * tamaño = min(riesgo/stop, 1/K) del equity realizado al momento de entrar
  * respeta el mínimo de Binance (min_notional) -> si la posición sería menor, se omite
  * equity mark-to-market por vela para un drawdown honesto
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import Params, compute_metrics


def portfolio_backtest(frames: dict, candidates: pd.DataFrame, p: Params, start: str, end: str | None,
                       initial: float = 1000.0, max_positions: int = 3, min_notional: float = 5.0) -> dict:
    s = pd.Timestamp(start, tz="UTC")
    e = pd.Timestamp(end, tz="UTC") if end else None
    index = None
    for o in frames.values():
        index = o.index if index is None else index.union(o.index)
    index = index[(index >= s) & ((index < e) if e is not None else True)]
    close = pd.DataFrame({k: o["close"] for k, o in frames.items()}).reindex(index).ffill()
    n = len(index)

    cand = candidates.sort_values(["entry_time", "p"], ascending=[True, False])
    cand = cand[(cand["entry_time"] >= index[0]) & (cand["exit_time"] <= index[-1])]
    taken, open_pos = [], []   # open_pos: dicts con entry_pos/exit_pos
    skipped_min = 0
    for t in cand.itertuples(index=False):
        ep, xp = index.get_loc(t.entry_time), index.get_loc(t.exit_time)
        # una posición que sale DENTRO de la vela ep sigue ocupando su cupo al abrir esa vela (no se puede
        # saber de antemano), por eso se conserva mientras exit_pos >= ep
        open_pos = [q for q in open_pos if q["exit_pos"] >= ep]
        if len(open_pos) >= max_positions or any(q["symbol"] == t.symbol for q in open_pos):
            continue
        realized = initial + sum(q["pnl"] for q in taken if q["exit_pos"] < ep)
        f = min(p.risk_per_trade / t.stop_frac, 1.0 / max_positions)
        size = realized * f
        if size < min_notional:
            skipped_min += 1
            continue
        pnl = size * t.net_ret
        q = {"symbol": t.symbol, "entry_pos": ep, "exit_pos": xp, "size": size, "pnl": pnl,
             "net_ret": t.net_ret, "entry_time": t.entry_time, "exit_time": t.exit_time,
             "reason": t.reason, "entry_px": t.entry, "exit_px": t.exit, "port_ret": pnl / realized}
        taken.append(q)
        open_pos.append(q)

    realized_arr, unreal = np.zeros(n), np.zeros(n)
    for q in taken:
        realized_arr[q["exit_pos"]:] += q["pnl"]
        px = close[q["symbol"]].to_numpy()
        entry_fill = q["entry_px"] * (1 + p.fee)
        for j in range(q["entry_pos"], q["exit_pos"]):
            unreal[j] += q["size"] * (px[j] / entry_fill - 1)
    equity = pd.Series(initial + realized_arr + unreal, index=index)
    trades = pd.DataFrame(taken)
    return {"equity": equity, "trades": trades, "skipped_min_notional": skipped_min,
            "metrics": compute_metrics(equity, trades, initial) if len(trades) else {"n_trades": 0}}


def buy_hold_equal(frames: dict, start: str, end: str | None, initial: float = 1000.0) -> pd.Series:
    s = pd.Timestamp(start, tz="UTC")
    e = pd.Timestamp(end, tz="UTC") if end else None
    r = {}
    for k, o in frames.items():
        c = o["close"][(o.index >= s) & ((o.index < e) if e is not None else True)]
        r[k] = c.pct_change().fillna(0)
    return initial * (1 + pd.DataFrame(r).fillna(0).mean(axis=1)).cumprod()
