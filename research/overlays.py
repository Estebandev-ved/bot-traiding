"""
Overlays de riesgo para Breakout 4h. UNA sola implementación que usan tanto el laboratorio (portfolio_backtest)
como el paper trader en vivo (paper.advance), para que lo probado sea exactamente lo que corre.

  1) Filtro de régimen  -> no abrir posiciones nuevas en mercado bajista.
        "btc_ema200d": BTC con el cierre diario por encima de su EMA200 diaria (la última jornada CERRADA).
        "breadth":     al menos la mitad de los pares con cierre diario sobre su EMA50 diaria.
  2) Tamaño por volatilidad -> el tamaño solo se REDUCE (nunca se aumenta) cuando la volatilidad actual supera su
     promedio: mult = clip(1 / atr_ratio, floor, 1). OPCIONAL, apagado por defecto.
  3) Tamaño por correlación -> cada posición abierta muy correlacionada con el activo nuevo recorta el tamaño
     (los cripto se mueven casi juntos: 3 posiciones correlacionadas son en la práctica 1 grande). OPCIONAL, apagado.
  Los multiplicadores se aplican DESPUÉS del tope de 1/K por posición: antes casi nunca mordían, porque ese tope manda.

Todo usa solo información disponible al cierre de la vela de la señal (sin mirar al futuro).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

REGIMES = (None, "btc_ema200d", "breadth")


@dataclass
class Overlays:
    # Por defecto SOLO el filtro de régimen: es lo único que el laboratorio respalda (reports/INFORME_MEJORAS.md).
    # Los tamaños por volatilidad y correlación están implementados y probados, pero costaron retorno sin mejorar el holdout.
    regime: str | None = "btc_ema200d"
    vol_scale: bool = False
    vol_floor: float = 0.5        # el riesgo nunca baja de la mitad
    corr_scale: bool = False
    corr_window: int = 120        # velas 4h (~20 días) para medir la correlación
    corr_thr: float = 0.80        # por encima de esto se considera "el mismo trade"
    corr_per: float = 0.75        # recorte por cada posición abierta correlacionada
    corr_floor: float = 0.50

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "Overlays":
        d = d or {}
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def off(cls) -> "Overlays":
        return cls(regime=None, vol_scale=False, corr_scale=False)

    @property
    def active(self) -> bool:
        return bool(self.regime or self.vol_scale or self.corr_scale)

    def describe(self) -> str:
        parts = []
        if self.regime:
            parts.append(f"régimen={self.regime}")
        if self.vol_scale:
            parts.append(f"vol(≥{self.vol_floor:g}x)")
        if self.corr_scale:
            parts.append(f"corr(>{self.corr_thr:g})")
        return ", ".join(parts) or "sin overlays"


# ------------------------------------------------------------------ 1) régimen
def regime_series(frames: dict, mode: str | None, index: pd.DatetimeIndex | None = None) -> pd.Series | None:
    """Serie booleana por vela 4h: ¿se permite abrir? Usa la última jornada diaria ya CERRADA.
    Si falta BTC (modo btc_ema200d) devuelve None y el filtro queda desactivado (se avisa al llamar)."""
    if not mode:
        return None
    if index is None:
        index = None
        for o in frames.values():
            index = o.index if index is None else index.union(o.index)
    if mode == "btc_ema200d":
        btc = frames.get("BTCUSDT")
        if btc is None:
            return None
        d = btc["close"].resample("1D").last().dropna()
        ok = (d > d.ewm(span=200, adjust=False, min_periods=200).mean())
        valid = d.ewm(span=200, adjust=False, min_periods=200).mean().notna()
        flag = ok.where(valid)                      # NaN mientras no hay 200 días de historia
    elif mode == "breadth":
        votes = []
        for o in frames.values():
            d = o["close"].resample("1D").last().dropna()
            m = d.ewm(span=50, adjust=False, min_periods=50).mean()
            votes.append((d > m).where(m.notna()).astype(float))
        if not votes:
            return None
        flag = (pd.concat(votes, axis=1).mean(axis=1) >= 0.5).where(pd.concat(votes, axis=1).notna().any(axis=1))
    else:
        raise ValueError(f"régimen desconocido: {mode}")
    flag = flag.shift(1)                             # la jornada D solo se conoce al cierre de D -> se usa desde D+1
    out = flag.reindex(index.union(flag.index)).ffill().reindex(index)
    return out.fillna(False).astype(bool)


def regime_ok(series: pd.Series | None, ts) -> bool:
    if series is None:
        return True
    ts = pd.Timestamp(ts)
    if ts in series.index:
        return bool(series.loc[ts])
    pos = series.index.searchsorted(ts, side="right") - 1
    return bool(series.iloc[pos]) if pos >= 0 else False


# ------------------------------------------------------------------ 2) volatilidad
def vol_mult(atr_ratio: float, floor: float = 0.5) -> float:
    """1.0 con volatilidad normal o baja; baja hasta `floor` cuando el ATR es >= 1/floor veces su promedio."""
    if atr_ratio is None or not np.isfinite(atr_ratio) or atr_ratio <= 1.0:
        return 1.0
    return float(min(1.0, max(floor, 1.0 / atr_ratio)))


# ------------------------------------------------------------------ 3) correlación
def returns_frame(frames: dict) -> pd.DataFrame:
    return pd.DataFrame({k: o["close"].pct_change() for k, o in frames.items()})


def corr_mult(rets: pd.DataFrame, ts, sym: str, open_syms, window: int = 120, thr: float = 0.80,
              per: float = 0.75, floor: float = 0.50) -> float:
    """Recorta el tamaño por cada posición abierta cuya correlación (últimas `window` velas hasta `ts`) supera `thr`."""
    others = [s for s in open_syms if s != sym and s in rets.columns]
    if not others or sym not in rets.columns:
        return 1.0
    ts = pd.Timestamp(ts)
    end = rets.index.searchsorted(ts, side="right")
    win = rets.iloc[max(0, end - window):end]
    if len(win) < window // 2:
        return 1.0
    n_high = 0
    for s in others:
        c = win[sym].corr(win[s])
        if c == c and c >= thr:
            n_high += 1
    return float(max(floor, per ** n_high)) if n_high else 1.0


# ------------------------------------------------------------------ combinación
class Context:
    """Precalcula lo que dependen de los datos (régimen y retornos) y expone un único `size_mult`."""

    def __init__(self, overlays: Overlays | None, frames: dict):
        self.cfg = overlays or Overlays.off()
        self.regime = regime_series(frames, self.cfg.regime) if self.cfg.regime else None
        self.missing_regime = bool(self.cfg.regime) and self.regime is None
        self.rets = returns_frame(frames) if self.cfg.corr_scale else None

    def allows(self, ts) -> bool:
        return regime_ok(self.regime, ts)

    def size_mult(self, ts, sym: str, atr_ratio: float, open_syms=()) -> float:
        m = 1.0
        if self.cfg.vol_scale:
            m *= vol_mult(atr_ratio, self.cfg.vol_floor)
        if self.cfg.corr_scale and self.rets is not None:
            m *= corr_mult(self.rets, ts, sym, list(open_syms), self.cfg.corr_window, self.cfg.corr_thr,
                           self.cfg.corr_per, self.cfg.corr_floor)
        return m
