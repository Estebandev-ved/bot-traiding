"""
Gestor de portafolio: junta a Richy (tendencia, BTC) y Breakout 4h (5 pares) bajo UN solo presupuesto de riesgo.

Cada bot sigue decidiendo y dimensionando por su cuenta; el gestor mira el CONJUNTO y puede frenar las entradas
nuevas de AMBOS (nunca cierra posiciones ni toca stops):

  * Índice combinado   Σ peso_i · (equity_i / equity_inicial_i)   (arranca en 1.0)
  * Pérdida diaria     si el índice cae >= max_daily_loss en el día UTC -> sin entradas nuevas hasta mañana.
  * Caída máxima       si cae >= max_drawdown desde su pico -> sin entradas nuevas; se reanuda al recuperar la mitad.
  * Exposición         Σ peso_i · exposición_i (nocional / equity). Solo informa si supera max_exposure.
  * Concentración      exposición combinada por activo (p. ej. BTC en Richy y en Breakout a la vez). Solo avisa,
                       salvo que se active enforce_asset_cap (por defecto NO, para no alterar el historial de cada bot).

La compuerta (`gate`) falla ABIERTA: si falta o está vieja (> GATE_MAX_AGE_H) los bots operan normal. Un fallo de
la vigilancia nunca debe apagar al bot; para eso están el kill switch y las alertas.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

GATE_MAX_AGE_H = 12.0
HISTORY_KEEP = 500


@dataclass
class PortfolioConfig:
    weights: dict = field(default_factory=lambda: {"richy": 0.5, "breakout": 0.5})
    max_daily_loss: float = 0.03
    max_drawdown: float = 0.15
    max_exposure: float = 1.0
    max_asset_exposure: float = 0.60
    enforce_asset_cap: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "PortfolioConfig":
        d = d or {}
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Sleeve:
    """Foto de un bot en un instante. `exposure` = nocional abierto / equity; `assets` = nocional/equity por activo."""
    name: str
    equity: float
    equity0: float
    exposure: float = 0.0
    assets: dict = field(default_factory=dict)
    updated: float | None = None      # epoch del último latido del bot


def new_state() -> dict:
    return {"day": None, "day_start": None, "peak": 1.0, "halt_dd": False, "history": []}


def _weights(cfg: PortfolioConfig, names) -> dict:
    """Pesos normalizados entre los bots presentes."""
    w = {n: max(0.0, float(cfg.weights.get(n, 0.0))) for n in names}
    tot = sum(w.values())
    return {n: (v / tot if tot > 0 else 1.0 / len(w)) for n, v in w.items()} if w else {}


def combined_index(sleeves: list[Sleeve], cfg: PortfolioConfig) -> float:
    w = _weights(cfg, [s.name for s in sleeves])
    return float(sum(w[s.name] * (s.equity / s.equity0 if s.equity0 > 0 else 1.0) for s in sleeves))


def evaluate(sleeves: list[Sleeve], cfg: PortfolioConfig, state: dict, now_ts: float) -> tuple[dict, dict]:
    """Devuelve (decisión, nuevo estado). Pura: no toca red ni disco."""
    st = {**new_state(), **(state or {})}
    st["history"] = list(st.get("history", []))
    if not sleeves:
        return {"allow_new": True, "reasons": [], "blocked_symbols": [], "index": 1.0, "drawdown": 0.0,
                "daily_pnl": 0.0, "exposure": 0.0, "assets": {}, "warnings": ["sin datos de los bots"],
                "weights": {}}, st
    w = _weights(cfg, [s.name for s in sleeves])
    idx = combined_index(sleeves, cfg)
    day = str(np.datetime64(int(now_ts), "s"))[:10]            # día UTC
    if st["day"] != day or not st["day_start"]:
        st["day"], st["day_start"] = day, idx
    st["peak"] = max(float(st["peak"] or 1.0), idx)
    daily = idx / st["day_start"] - 1.0
    dd = idx / st["peak"] - 1.0

    if dd <= -cfg.max_drawdown:
        st["halt_dd"] = True
    elif st["halt_dd"] and dd > -cfg.max_drawdown / 2:         # histéresis: se reanuda al recuperar la mitad
        st["halt_dd"] = False

    reasons, warnings = [], []
    if daily <= -cfg.max_daily_loss:
        reasons.append(f"pérdida diaria combinada {daily:.1%} (límite -{cfg.max_daily_loss:.0%})")
    if st["halt_dd"]:
        reasons.append(f"caída combinada {dd:.1%} desde el pico (límite -{cfg.max_drawdown:.0%})")

    exposure = float(sum(w[s.name] * s.exposure for s in sleeves))
    if exposure >= cfg.max_exposure:
        warnings.append(f"exposición combinada {exposure:.0%} (tope {cfg.max_exposure:.0%})")
    assets: dict = {}
    for s in sleeves:
        for a, v in s.assets.items():
            assets[a] = assets.get(a, 0.0) + w[s.name] * float(v)
    over = sorted(a for a, v in assets.items() if v >= cfg.max_asset_exposure)
    if over:
        warnings.append("concentración alta en " + ", ".join(f"{a} {assets[a]:.0%}" for a in over))
    blocked = over if cfg.enforce_asset_cap else []

    st["history"].append([int(now_ts), round(idx, 6)])
    st["history"] = st["history"][-HISTORY_KEEP:]
    return {"allow_new": not reasons, "reasons": reasons, "blocked_symbols": blocked, "index": idx, "drawdown": dd,
            "daily_pnl": daily, "exposure": exposure, "assets": assets, "warnings": warnings, "weights": w}, st


# ------------------------------------------------------------------ compuerta que leen los bots
def gate_allows(gate: dict | None, now_ts: float, symbol: str | None = None) -> tuple[bool, str]:
    """¿Puede el bot abrir posiciones nuevas? Falla ABIERTO si no hay compuerta o está vieja."""
    if not gate:
        return True, "sin compuerta (opera normal)"
    upd = gate.get("updated")
    if upd is None or (now_ts - float(upd)) / 3600.0 > GATE_MAX_AGE_H:
        return True, "compuerta vieja (opera normal)"
    if symbol and symbol in (gate.get("blocked_symbols") or []):
        return False, f"{symbol}: concentración de portafolio"
    if not gate.get("allow_new", True):
        return False, "; ".join(gate.get("reasons") or ["portafolio en pausa"])
    return True, "ok"


# ------------------------------------------------------------------ análisis de laboratorio
def combine_equity(curves: dict, weights: dict | None = None) -> "np.ndarray":
    """Mezcla curvas de equity (pandas Series con índice de tiempo) con rebalanceo diario a pesos fijos."""
    import pandas as pd
    daily = {k: c.resample("1D").last().dropna().pct_change().fillna(0.0) for k, c in curves.items()}
    df = pd.DataFrame(daily).fillna(0.0)
    w = {k: (weights or {}).get(k, 1.0 / len(df.columns)) for k in df.columns}
    tot = sum(w.values())
    r = sum(df[k] * v / tot for k, v in w.items())
    return (1.0 + r).cumprod()


def inverse_vol_weights(returns: dict, shrink: float = 0.5) -> dict:
    """Pesos ∝ 1/volatilidad, mezclados con partes iguales (shrink=0 -> iguales, 1 -> inverso puro)."""
    vol = {k: float(np.std(np.asarray(v, dtype=float), ddof=1)) for k, v in returns.items() if len(v) > 2}
    vol = {k: v for k, v in vol.items() if v > 0 and math.isfinite(v)}
    if not vol:
        n = len(returns)
        return {k: 1.0 / n for k in returns} if n else {}
    inv = {k: 1.0 / v for k, v in vol.items()}
    tot = sum(inv.values())
    n = len(inv)
    return {k: (1 - shrink) / n + shrink * inv[k] / tot for k in inv}
