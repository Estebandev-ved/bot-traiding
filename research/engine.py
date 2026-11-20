"""
Motor de simulación realista (solo LONG, spot, 1 posición por activo).

Reglas anti-sesgo:
  * La señal se evalúa al CIERRE de la vela i; la entrada es en el OPEN de la vela i+1 (+ slippage).
  * SL/TP basados en ATR de la vela i. Si SL y TP caen en la misma vela se asume que se tocó el SL primero.
  * Si el precio abre más allá del SL (gap) se sale al open, no al precio del SL.
  * Comisiones en ambas patas + slippage en ambas patas.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Params:
    sl_atr: float = 1.5          # stop = entrada - sl_atr * ATR
    tp_atr: float = 3.0          # take profit = entrada + tp_atr * ATR
    max_hold: int = 48           # velas máximas en posición
    fee: float = 0.00075         # 0.075% por lado (taker con BNB). Sin BNB: 0.001
    slippage: float = 0.0002     # 0.02% por lado
    risk_per_trade: float = 0.02 # fracción de equity arriesgada hasta el stop
    max_leverage: float = 1.0    # spot => 1.0 (no se invierte más que el equity)
    extra: dict = field(default_factory=dict)


def simulate_trade(o_: np.ndarray, h_: np.ndarray, l_: np.ndarray, c_: np.ndarray, atr_: np.ndarray,
                   i: int, p: Params):
    """Simula un trade con señal en la vela i. Devuelve dict o None si no hay datos suficientes."""
    n = len(c_)
    if i + 1 >= n or not np.isfinite(atr_[i]) or atr_[i] <= 0:
        return None
    entry = o_[i + 1] * (1 + p.slippage)
    stop = entry - p.sl_atr * atr_[i]
    target = entry + p.tp_atr * atr_[i]
    if stop <= 0:
        return None
    exit_idx, exit_px, reason = None, None, None
    last = min(i + p.max_hold, n - 1)
    for j in range(i + 1, last + 1):
        if j > i + 1 and o_[j] <= stop:       # gap por debajo del stop
            exit_idx, exit_px, reason = j, o_[j], "SL_GAP"
            break
        if l_[j] <= stop:
            exit_idx, exit_px, reason = j, stop, "SL"
            break
        if h_[j] >= target:
            exit_idx, exit_px, reason = j, target, "TP"
            break
    if exit_idx is None:
        exit_idx, exit_px, reason = last, c_[last], "TIME"
    exit_net = exit_px * (1 - p.slippage)
    gross = exit_px / entry - 1
    net = (exit_net * (1 - p.fee)) / (entry * (1 + p.fee)) - 1
    risk_frac = (entry - stop) / entry
    return {"signal_idx": i, "entry_idx": i + 1, "exit_idx": exit_idx, "entry": entry, "exit": exit_px,
            "reason": reason, "gross_ret": gross, "net_ret": net, "stop_frac": risk_frac}


def label_signals(o: pd.DataFrame, signal_idx: np.ndarray, p: Params) -> pd.DataFrame:
    """Simula cada señal por separado (sin importar si había otra posición): sirve para etiquetar ML."""
    a = {k: o[k].to_numpy(float) for k in ("open", "high", "low", "close", "atr")}
    out = []
    for i in signal_idx:
        t = simulate_trade(a["open"], a["high"], a["low"], a["close"], a["atr"], int(i), p)
        if t:
            out.append(t)
    return pd.DataFrame(out)


def run_backtest(o: pd.DataFrame, trades: pd.DataFrame, p: Params, initial: float = 1000.0) -> dict:
    """Ejecuta SECUENCIALMENTE una lista de trades candidatos (omite los que solapan con una posición
    abierta) y devuelve curva de equity por vela (mark-to-market) + trades ejecutados."""
    closes = o["close"].to_numpy(float)
    n = len(o)
    bar_ret = np.zeros(n)
    taken, busy_until = [], -1
    for t in trades.sort_values("entry_idx").itertuples(index=False):
        if t.entry_idx <= busy_until:
            continue
        f = min(p.max_leverage, p.risk_per_trade / t.stop_frac)   # fracción del equity invertida
        e, x = int(t.entry_idx), int(t.exit_idx)
        entry_fill = t.entry * (1 + p.fee)                        # costo de entrada incluido
        for j in range(e, x + 1):
            prev = entry_fill if j == e else closes[j - 1]
            cur = (t.exit * (1 - p.slippage) * (1 - p.fee)) if j == x else closes[j]
            bar_ret[j] = f * (cur / prev - 1)
        busy_until = x
        d = t._asdict()
        d["size_frac"] = f
        d["port_ret"] = f * t.net_ret
        taken.append(d)
    eq = initial * np.cumprod(1 + bar_ret)
    return {"equity": pd.Series(eq, index=o.index), "bar_ret": pd.Series(bar_ret, index=o.index),
            "trades": pd.DataFrame(taken)}


# ------------------------------------------------------------------ métricas
def _bootstrap_ci(x: np.ndarray, n: int = 4000, seed: int = 7):
    if len(x) < 5:
        return (np.nan, np.nan, np.nan)
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(n, len(x)), replace=True).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)), float((means <= 0).mean())


def compute_metrics(equity: pd.Series, trades: pd.DataFrame, initial: float = 1000.0) -> dict:
    eq = equity.copy()
    years = max((eq.index[-1] - eq.index[0]).total_seconds() / (365.25 * 86400), 1e-9)
    daily = eq.resample("1D").last().dropna()
    dr = daily.pct_change().dropna()
    peak = eq.cummax()
    mdd = float((eq / peak - 1).min())
    total = float(eq.iloc[-1] / initial - 1)
    cagr = float((eq.iloc[-1] / initial) ** (1 / years) - 1) if eq.iloc[-1] > 0 else -1.0
    sharpe = float(dr.mean() / dr.std() * np.sqrt(365)) if dr.std() > 0 else 0.0
    dn = dr[dr < 0]
    sortino = float(dr.mean() / dn.std() * np.sqrt(365)) if len(dn) > 1 and dn.std() > 0 else 0.0
    m = {"years": round(years, 2), "total_return": total, "cagr": cagr, "max_drawdown": mdd,
         "sharpe": sharpe, "sortino": sortino, "calmar": (cagr / abs(mdd)) if mdd < 0 else np.nan,
         "n_trades": 0}
    if trades is not None and len(trades):
        r = trades["port_ret"].to_numpy()
        w, l = r[r > 0], r[r <= 0]
        lo, hi, p0 = _bootstrap_ci(trades["net_ret"].to_numpy())
        m.update({"n_trades": int(len(r)), "win_rate": float((r > 0).mean()),
                  "profit_factor": float(w.sum() / abs(l.sum())) if l.sum() < 0 else np.inf,
                  "avg_trade_net": float(trades["net_ret"].mean()),
                  "avg_trade_ci95": (lo, hi), "p_mean_le_0": p0,
                  "exposure": float((eq.index.to_series().map(lambda _: 0)).mean()) if False else float((equity.diff().fillna(0) != 0).mean()),
                  "trades_per_month": float(len(r) / (years * 12))})
    return m
