"""
Deriva paper vs backtest: ¿el bot en vivo rinde como prometía el laboratorio, o se está desviando?

Compara los trades en vivo con la línea base (trades fuera de muestra del backtest con la MISMA configuración):
  * rendimiento medio por trade  -> z = (media_vivo - media_base) / (sd_base / √n)
  * tasa de acierto              -> z binomial contra la tasa base
  * caída máxima en vivo         -> contra el peor 5 % de las simulaciones Monte Carlo de la línea base

Con pocos trades no se concluye nada ("wait"). Es una alarma de deriva, no una prueba de edge: para eso están PSR/DSR
en `research/robust.py`. La línea base sale de `python -m research.run_enhancements` (reports/baseline_breakout.json).
"""
from __future__ import annotations

import json
import math
import os

import numpy as np

from research import robust

MIN_TRADES = 20
Z_WARN, Z_BAD = -1.65, -2.33          # ~5 % y ~1 % de cola inferior
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE_PATH = os.path.join(ROOT, "reports", "baseline_breakout.json")


def load_baseline(path: str | None = None) -> dict | None:
    try:
        with open(path or BASELINE_PATH, encoding="utf-8") as f:
            b = json.load(f)
        return b if len(b.get("net_ret", [])) >= 30 and len(b.get("port_ret", [])) >= 30 else None
    except (OSError, ValueError):
        return None


def live_returns(closed: list[dict]) -> tuple[list[float], list[float]]:
    """(retorno neto por trade, retorno sobre el equity por trade) a partir de los trades cerrados del paper trader."""
    net, port = [], []
    for c in closed:
        net.append(float(c["net_ret"]))
        before = float(c["equity_after"]) - float(c["pnl"])
        port.append(float(c["pnl"]) / before if before > 0 else 0.0)
    return net, port


def drift_report(closed: list[dict], baseline: dict | None, min_trades: int = MIN_TRADES) -> dict:
    if not baseline:
        return {"state": "wait", "n": len(closed), "alerts": [], "text": "Sin línea base de backtest para comparar."}
    net, port = live_returns(closed)
    n = len(net)
    if n < min_trades:
        return {"state": "wait", "n": n, "alerts": [],
                "text": f"Aún {n} de {min_trades} trades: muy pronto para comparar con el backtest."}
    b_net = np.asarray(baseline["net_ret"], dtype=float)
    b_mean, b_sd = float(b_net.mean()), float(b_net.std(ddof=1))
    mean = float(np.mean(net))
    z_mean = (mean - b_mean) / (b_sd / math.sqrt(n)) if b_sd > 0 else 0.0
    b_wr = float((b_net > 0).mean())
    wr = float(np.mean(np.asarray(net) > 0))
    z_wr = (wr - b_wr) / math.sqrt(b_wr * (1 - b_wr) / n) if 0 < b_wr < 1 else 0.0
    eq = np.cumprod(1.0 + np.asarray(port))
    live_dd = float((eq / np.maximum.accumulate(np.concatenate([[1.0], eq]))[1:] - 1).min())
    mc = robust.monte_carlo(baseline["port_ret"], horizon=n, n_sims=3000)
    dd95 = mc.get("dd_p95") if mc.get("ok") else None

    alerts = []
    if z_mean <= Z_BAD:
        alerts.append(f"rendimiento por trade {mean:+.2%} vs {b_mean:+.2%} esperado (z={z_mean:.1f}): deriva fuerte")
    elif z_mean <= Z_WARN:
        alerts.append(f"rendimiento por trade {mean:+.2%} vs {b_mean:+.2%} esperado (z={z_mean:.1f}): deriva")
    if z_wr <= Z_BAD:
        alerts.append(f"aciertos {wr:.0%} vs {b_wr:.0%} esperado (z={z_wr:.1f})")
    if dd95 is not None and live_dd < dd95:
        alerts.append(f"caída en vivo {live_dd:.1%} peor que el 95 % de simulaciones ({dd95:.1%})")
    state = "bad" if (z_mean <= Z_BAD or (dd95 is not None and live_dd < dd95)) else ("warn" if alerts else "ok")
    text = ("Rinde como el backtest." if state == "ok" else "Se desvía del backtest: " + "; ".join(alerts))
    return {"state": state, "n": n, "alerts": alerts, "text": text, "mean": mean, "base_mean": b_mean, "z_mean": z_mean,
            "win_rate": wr, "base_win_rate": b_wr, "z_win_rate": z_wr, "live_dd": live_dd, "mc_dd95": dd95}
