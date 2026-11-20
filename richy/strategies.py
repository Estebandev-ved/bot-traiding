"""Estrategias. Cada una devuelve, por barra y usando solo datos hasta el cierre,
la posición deseada (-1, 0, 1) y la distancia de stop (en precio, basada en ATR).
El motor la ejecuta en la apertura de la barra siguiente (sin mirar el futuro)."""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from . import indicators as ind


class Strategy:
    name = "base"

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:  # -> columnas: signal, stop_dist
        raise NotImplementedError


@dataclass
class TrendATR(Strategy):
    """Sigue tendencia: cruce de EMAs + ADX; stop que se ajusta con ATR (trailing)."""
    fast: int = 20
    slow: int = 50
    adx_min: float = 20.0
    atr_mult: float = 2.5
    allow_short: bool = True
    name: str = "trend"

    def generate(self, df):
        f, s = ind.ema(df["close"], self.fast), ind.ema(df["close"], self.slow)
        strong = ind.adx(df) > self.adx_min
        sig = np.where(strong & (f > s), 1, np.where(strong & (f < s) & self.allow_short, -1, 0))
        return pd.DataFrame({"signal": sig, "stop_dist": ind.atr(df) * self.atr_mult}, index=df.index)


@dataclass
class MeanReversion(Strategy):
    """Apuesta a que el precio vuelve al promedio tras un movimiento exagerado."""
    window: int = 50
    entry_z: float = 2.0
    exit_z: float = 0.25
    atr_mult: float = 2.0
    allow_short: bool = True
    name: str = "meanrev"

    def generate(self, df):
        z = ind.zscore(df["close"], self.window).to_numpy()
        sig = np.zeros(len(df), dtype=int)
        pos = 0
        for i, v in enumerate(z):
            if np.isnan(v):
                pass
            elif pos == 0:
                pos = 1 if v <= -self.entry_z else (-1 if v >= self.entry_z and self.allow_short else 0)
            elif (pos == 1 and v >= -self.exit_z) or (pos == -1 and v <= self.exit_z):
                pos = 0
            sig[i] = pos
        return pd.DataFrame({"signal": sig, "stop_dist": ind.atr(df) * self.atr_mult}, index=df.index)


class Flat(Strategy):
    name = "flat"

    def generate(self, df):
        return pd.DataFrame({"signal": 0, "stop_dist": ind.atr(df) * 2}, index=df.index)


@dataclass
class RegimeSwitched(Strategy):
    """La IA/regla detecta el régimen y activa una estrategia u otra (nunca decide órdenes)."""
    regimes: pd.Series = None            # 'trend' | 'range' | 'volatile' por barra
    routes: dict = None                  # régimen -> Strategy
    enabled: dict = None                 # nombre -> bool (botones del panel)
    name: str = "regime"

    def generate(self, df):
        out = pd.DataFrame({"signal": 0, "stop_dist": ind.atr(df) * 2}, index=df.index)
        reg = self.regimes.reindex(df.index).ffill()
        for regime, strat in self.routes.items():
            if self.enabled is not None and not self.enabled.get(strat.name, True):
                continue
            g = strat.generate(df)
            m = (reg == regime).to_numpy()
            out.loc[m, "signal"] = g["signal"].to_numpy()[m]
            out.loc[m, "stop_dist"] = g["stop_dist"].to_numpy()[m]
        return out
