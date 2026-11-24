"""«Por qué no opera» para Richy (tendencia solo en largo): qué condición le falta ahora mismo."""
from __future__ import annotations

import numpy as np

from . import indicators as ind
from .strategies import TrendATR


def explain(closed, strategy, position=None, paused: bool = False, killed: bool = False, gate_allow: bool = True,
            gate_reason: str = "") -> dict | None:
    if not isinstance(strategy, TrendATR):
        return None
    f, s = ind.ema(closed["close"], strategy.fast), ind.ema(closed["close"], strategy.slow)
    adx = ind.adx(closed)
    ef, es, ax = float(f.iloc[-1]), float(s.iloc[-1]), float(adx.iloc[-1])
    if not all(np.isfinite([ef, es, ax])):
        return None
    up, strong = ef > es, ax > strategy.adx_min
    info = {"ema_fast": ef, "ema_slow": es, "adx": ax, "adx_min": strategy.adx_min, "fast": strategy.fast, "slow": strategy.slow}
    if killed:
        return {**info, "status": "killed", "text": "Detenido por el kill switch de riesgo."}
    if position:
        return {**info, "status": "open", "text": "Hay una posición LONG abierta; se cierra si la tendencia se rompe o salta el stop."}
    if paused:
        return {**info, "status": "paused", "text": "En pausa por noticias de riesgo o por el sentimiento extremo del mercado."}
    if not gate_allow:
        return {**info, "status": "halted", "text": f"Entradas nuevas en pausa por el portafolio: {gate_reason}."}
    if up and strong:
        return {**info, "status": "signal", "text": "Hay señal de compra (tendencia alcista fuerte); entra en la apertura siguiente."}
    why = []
    if not up:
        why.append(f"la EMA{strategy.fast} ({ef:,.0f}) está bajo la EMA{strategy.slow} ({es:,.0f}): tendencia bajista, y Richy solo opera en largo")
    if not strong:
        why.append(f"el ADX es {ax:.0f} (necesita más de {strategy.adx_min:g} para considerar que hay tendencia)")
    return {**info, "status": "no_signal", "text": "Sin entradas: " + "; ".join(why) + "."}
