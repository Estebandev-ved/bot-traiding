"""Backtesting realista: comisiones, deslizamiento, órdenes que no se llenan,
stops intrabarra, límites de riesgo y walk-forward. Sin mirar el futuro:
la señal del cierre de la barra t se ejecuta en la apertura de t+1."""
from dataclasses import dataclass
import itertools
import numpy as np
import pandas as pd
from .risk import RiskManager, RiskConfig

BARS_PER_YEAR = {"1m": 525600, "5m": 105120, "15m": 35040, "1h": 8760, "4h": 2190, "1d": 365}


@dataclass
class CostModel:
    fee: float = 0.0006        # 0.06% por lado (taker aprox.)
    slippage: float = 0.0005   # 0.05% en contra al entrar/salir
    fill_prob: float = 0.9     # prob. de que una orden de entrada se llene (límite)
    seed: int = 7


def metrics(equity: pd.Series, trades: list, bars_per_year: int = 8760) -> dict:
    ret = equity.pct_change().dropna()
    dd = equity / equity.cummax() - 1
    sharpe = float(ret.mean() / ret.std() * np.sqrt(bars_per_year)) if len(ret) > 2 and ret.std() > 0 else 0.0
    pnl = np.array([t["pnl"] for t in trades]) if trades else np.array([])
    wins, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    return {
        "total_return": float(equity.iloc[-1] / equity.iloc[0] - 1),
        "max_drawdown": float(dd.min()),
        "sharpe": sharpe,
        "trades": int(len(pnl)),
        "win_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
        "profit_factor": float(wins / losses) if losses > 0 else (float("inf") if wins > 0 else 0.0),
    }


def run_backtest(df: pd.DataFrame, strategy, equity0: float = 10_000.0, cost: CostModel = None,
                 risk: RiskConfig = None, start: int = 0, interval: str = "1h", close_at_end: bool = True):
    """Opera solo desde la barra `start` (las anteriores sirven de calentamiento).
    close_at_end=False deja abierta la posición final (paper trading en vivo)."""
    cost = cost or CostModel()
    rng = np.random.default_rng(cost.seed)
    rm = RiskManager(risk, equity0)
    g = strategy.generate(df)
    sig, sdist = g["signal"].to_numpy(), g["stop_dist"].to_numpy()
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    idx = df.index

    cash, qty, entry, stop, entry_i, entry_fee = equity0, 0.0, 0.0, 0.0, 0, 0.0
    equity = np.full(len(df), equity0)
    trades = []

    def close_pos(i, price, reason):
        nonlocal cash, qty
        side = np.sign(qty)
        px = price * (1 - side * cost.slippage)
        fee = abs(qty) * px * cost.fee
        pnl = qty * (px - entry) - fee - entry_fee
        cash += qty * (px - entry) - fee
        trades.append({"entry_time": idx[entry_i], "exit_time": idx[i], "side": int(side), "entry": entry,
                       "exit": px, "qty": abs(qty), "pnl": float(pnl), "reason": reason})
        qty = 0.0

    for i in range(max(start, 1), len(df)):
        mark = cash + qty * (c[i - 1] - entry)
        rm.update(idx[i], mark)
        want = int(sig[i - 1]) if rm.can_open() else 0
        if rm.killed:
            want = 0
        if qty != 0 and (want != np.sign(qty)):                       # salida por señal / apagado de riesgo
            close_pos(i, o[i], "kill" if rm.killed else ("daily_limit" if rm.halted_today else "signal"))
        if qty == 0 and want != 0 and rm.can_open():
            sd = sdist[i - 1]
            if sd > 0 and not np.isnan(sd) and rng.random() <= cost.fill_prob:
                px = o[i] * (1 + want * cost.slippage)
                q = rm.position_size(cash, px, sd)
                if q > 0:
                    entry_fee = q * px * cost.fee
                    cash -= entry_fee
                    qty, entry, entry_i = want * q, px, i
                    stop = px - want * sd
        if qty != 0:                                                  # stop intrabarra (con gaps)
            s = np.sign(qty)
            if (s > 0 and l[i] <= stop) or (s < 0 and h[i] >= stop):
                close_pos(i, min(stop, o[i]) if s > 0 else max(stop, o[i]), "stop")
            else:                                                     # trailing por ATR
                trail = c[i] - s * sdist[i] if not np.isnan(sdist[i]) else stop
                stop = max(stop, trail) if s > 0 else min(stop, trail)
        equity[i] = cash + qty * (c[i] - entry)
    open_pos = None
    if qty != 0 and close_at_end:
        close_pos(len(df) - 1, c[-1], "end")
        equity[-1] = cash
    elif qty != 0:
        open_pos = {"side": int(np.sign(qty)), "qty": abs(float(qty)), "entry": float(entry), "stop": float(stop),
                    "since": idx[entry_i]}
    eq = pd.Series(equity, index=idx)[max(start, 1) - 1:]
    return {"equity": eq, "trades": trades, "metrics": metrics(eq, trades, BARS_PER_YEAR.get(interval, 8760)),
            "risk": rm.state(), "open": open_pos}


def walk_forward(df: pd.DataFrame, make_strategy, grid: dict, train_bars: int, test_bars: int,
                 objective: str = "sharpe", warmup: int = 300, **kw):
    """Ajusta parámetros en una ventana (train) y valida en la siguiente (test) que
    el bot nunca vio. Devuelve métricas por ventana y el equity encadenado fuera de muestra."""
    keys, combos = list(grid), list(itertools.product(*grid.values()))
    windows, oos, eq_level = [], [], 1.0
    s = 0
    while s + train_bars + test_bars <= len(df):
        tr_end, te_end = s + train_bars, s + train_bars + test_bars
        best, best_score = None, -np.inf
        for combo in combos:
            p = dict(zip(keys, combo))
            res = run_backtest(df.iloc[s:tr_end], make_strategy(**p), **kw)
            score = res["metrics"][objective]
            if res["metrics"]["trades"] >= 3 and score > best_score:
                best, best_score = p, score
        if best is None:
            best = dict(zip(keys, combos[0]))
        lo = max(0, tr_end - warmup)
        res = run_backtest(df.iloc[lo:te_end], make_strategy(**best), start=tr_end - lo, **kw)
        e = res["equity"]
        seg = e / e.iloc[0] * eq_level
        eq_level = float(seg.iloc[-1])
        oos.append(seg.iloc[1:])
        windows.append({"train": (df.index[s], df.index[tr_end - 1]), "test": (df.index[tr_end], df.index[te_end - 1]),
                        "params": best, "in_sample_" + objective: best_score, "oos": res["metrics"]})
        s += test_bars
    equity = pd.concat(oos) if oos else pd.Series(dtype=float)
    return {"windows": windows, "oos_equity": equity,
            "oos_metrics": metrics(equity, [], BARS_PER_YEAR.get(kw.get("interval", "1h"), 8760)) if len(equity) > 2 else {}}


def backtest_grid(df: pd.DataFrame, lower: float, upper: float, levels: int = 10, equity0: float = 10_000.0,
                  cost: CostModel = None, capital_frac: float = 0.9):
    """Grid en rango: compras escalonadas hacia abajo, ventas un escalón arriba.
    Usa high/low de cada barra; cada ejecución paga comisión y deslizamiento."""
    cost = cost or CostModel()
    grid = np.linspace(lower, upper, levels + 1)
    per_level = equity0 * capital_frac / levels
    c0 = df["close"].iloc[0]
    holding = {}                  # nivel i -> (qty, precio de compra); se vende en grid[i+1]
    cash, pnl_closed, n, eq = equity0, 0.0, 0, []
    for _, r in df.iterrows():
        for i in range(levels):
            if i in holding:      # venta un escalón arriba
                if r["high"] >= grid[i + 1]:
                    q, bpx = holding.pop(i)
                    px = grid[i + 1] * (1 - cost.slippage)
                    cash += q * px * (1 - cost.fee)
                    pnl_closed += q * (px - bpx) - q * (px + bpx) * cost.fee
                    n += 1
            elif grid[i] < c0 and r["low"] <= grid[i]:   # compra límite escalonada bajo el precio inicial
                px = grid[i] * (1 + cost.slippage)
                q = per_level / px
                cash -= q * px * (1 + cost.fee)
                holding[i] = (q, px)
        eq.append(cash + sum(q for q, _ in holding.values()) * r["close"])
    eq = pd.Series(eq, index=df.index)
    return {"equity": eq, "cycles": n, "realized_pnl": pnl_closed,
            "metrics": metrics(eq, [{"pnl": pnl_closed / max(n, 1)}] * n)}


def backtest_funding_arb(funding: pd.Series, equity0: float = 10_000.0, enter_above: float = 0.0001,
                         exit_below: float = 0.0, cost: CostModel = None, leverage_short: float = 1.0):
    """Spot largo + futuro corto del mismo tamaño (delta neutral). Se cobra el funding
    mientras sea positivo; entrar y salir cuesta comisión+slippage en las dos patas."""
    cost = cost or CostModel()
    notional = equity0 / (1 + 1 / leverage_short)   # parte del capital va a spot, parte al margen del corto
    in_pos, equity, trades, curve = False, equity0, 0, []
    for ts, rate in funding.items():
        if in_pos:                           # solo cobra si YA estaba dentro antes de este pago (sin mirar adelante)
            equity += notional * rate        # el que está corto cobra si rate>0 (y paga si <0)
        if not in_pos and rate >= enter_above:      # decide con la tasa ya conocida; cobra desde el siguiente pago
            equity -= 2 * notional * (cost.fee + cost.slippage)
            in_pos, trades = True, trades + 1
        elif in_pos and rate < exit_below:
            equity -= 2 * notional * (cost.fee + cost.slippage)
            in_pos = False
        curve.append(equity)
    eq = pd.Series(curve, index=funding.index)
    if len(eq) > 1:        # punto inicial con el capital sin tocar: así el costo de entrada cuenta en retorno y drawdown
        eq = pd.concat([pd.Series([equity0], index=[eq.index[0] - (eq.index[1] - eq.index[0])]), eq])
    return {"equity": eq, "entries": trades, "metrics": metrics(eq, [], 3 * 365)}
