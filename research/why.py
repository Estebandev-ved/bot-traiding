"""
«Por qué no opera»: explica, con datos de la última vela cerrada, qué le falta a Breakout 4h para entrar
(y qué hizo con las señales que sí vio). Sirve para el panel y para el resumen diario de Telegram.

Una entrada necesita TODO esto a la vez: ruptura del máximo de 48 velas + precio sobre la EMA200 (4h) + modelo de
aprendizaje con probabilidad suficiente + régimen de BTC favorable + la compuerta del portafolio abierta + cupo libre.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import signal_breakout


def regime_info(feats: dict, last_closed) -> dict | None:
    """BTC contra su EMA200 DIARIA usando solo jornadas ya cerradas (igual que el filtro de régimen)."""
    btc = feats.get("BTCUSDT")
    if btc is None:
        return None
    day0 = pd.Timestamp(last_closed).normalize()
    d = btc["close"].resample("1D").last().dropna()
    d = d[d.index < day0]
    ema = d.ewm(span=200, adjust=False, min_periods=200).mean()
    if len(d) < 200 or not np.isfinite(ema.iloc[-1]):
        return {"ready": False, "days": int(len(d))}
    close, e = float(d.iloc[-1]), float(ema.iloc[-1])
    return {"ready": True, "btc": close, "ema200d": e, "gap": close / e - 1.0, "on": close > e}


def pair_rows(feats: dict, last_closed) -> list[dict]:
    """Por par: precio, máximo de 48 velas, distancia a la ruptura y posición frente a la EMA200 (4h)."""
    ts = pd.Timestamp(last_closed)
    rows = []
    for sym, o in feats.items():
        if ts not in o.index:
            continue
        r = o.loc[ts]
        c, hi, e2 = float(r["close"]), float(r["donch_hi"]), float(r["ema200"])
        if not (np.isfinite(c) and np.isfinite(hi) and np.isfinite(e2) and hi > 0 and e2 > 0):
            continue
        sig = bool(signal_breakout(o.loc[:ts].tail(2)).iloc[-1])
        rows.append({"symbol": sym, "price": c, "breakout_level": hi, "gap_breakout": c / hi - 1.0,
                     "ema200": e2, "gap_ema200": c / e2 - 1.0, "above_ema200": c > e2, "signal": sig})
    return rows


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%".replace(".", ",")


def explain(feats: dict, last_closed, state: dict, overlays_on: bool, gate_allow: bool = True,
            gate_reason: str = "") -> dict:
    """Devuelve {text, status, regime, pairs, activity}. `status`: open | halted | regime | no_signal | signal."""
    reg = regime_info(feats, last_closed)
    pairs = pair_rows(feats, last_closed)
    open_syms = list(state.get("positions", {}))
    act = dict(state.get("activity") or {})
    below = [p for p in pairs if not p["above_ema200"]]
    near = min(pairs, key=lambda p: abs(p["gap_breakout"])) if pairs else None

    # detalle independiente del filtro de régimen: ¿qué pasaría sin él?
    if pairs and len(below) == len(pairs):
        lo, hi = min(p["gap_breakout"] for p in pairs), max(p["gap_breakout"] for p in pairs)
        detail = (f"Aun sin el filtro, los {len(pairs)} pares están bajo su EMA200 de 4 h y a "
                  f"{abs(hi) * 100:.0f}–{abs(lo) * 100:.0f}% de su máximo de 48 velas: no hay ruptura posible.")
    elif near is not None:
        detail = (f"El par más cercano a una ruptura es {near['symbol'].replace('USDT', '')} "
                  f"({_pct(near['gap_breakout'])} de su máximo de 48 velas); "
                  f"{len(pairs) - len(below)} de {len(pairs)} están sobre su EMA200.")
    else:
        detail = "Sin datos de precio suficientes."

    if open_syms:
        status, head = "open", "Hay " + ("una posición abierta" if len(open_syms) == 1 else f"{len(open_syms)} posiciones abiertas") \
            + ": " + ", ".join(s.replace("USDT", "") for s in open_syms) + "."
    elif not gate_allow:
        status, head = "halted", f"Las entradas nuevas están en pausa por el portafolio: {gate_reason}."
    elif overlays_on and reg and reg.get("ready") and not reg["on"]:
        status = "regime"
        head = (f"Sin entradas: BTC está {_pct(reg['gap'])} bajo su media de 200 días (${reg['btc']:,.0f} frente a "
                f"${reg['ema200d']:,.0f}); el filtro de régimen no deja comprar en mercado bajista.")
    elif any(p["signal"] for p in pairs):
        status, head = "signal", "Hay señal de ruptura en la última vela; entra en la apertura siguiente si el modelo la aprueba."
    else:
        status, head = "no_signal", "Sin entradas: ningún par está rompiendo su máximo de 48 velas."
    text = head if status in ("open", "halted", "signal") else f"{head} {detail}"
    return {"status": status, "text": text, "detail": detail, "regime": reg, "pairs": pairs,
            "overlays_on": bool(overlays_on), "activity": act, "last_bar": str(pd.Timestamp(last_closed))}
