"""Indicadores y features en pandas/numpy puro (sin TA-Lib). Todo usa SOLO información hasta la vela i."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


FEATURE_COLUMNS = [
    "ret_1", "ret_6", "ret_24", "ret_72",
    "dist_ema20", "dist_ema50", "dist_ema200", "ema20_50", "ema200_slope",
    "rsi14", "atr_pct", "atr_ratio", "vol_24", "vol_ratio", "taker_ratio",
    "donch_pos", "bb_z", "range_pos_24",
]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve df original + indicadores. Features escalados (sin precios absolutos) para poder
    entrenar un modelo conjunto sobre varios activos."""
    o = df.copy()
    c = o["close"]
    o["ema9"], o["ema20"], o["ema21"] = ema(c, 9), ema(c, 20), ema(c, 21)
    o["ema50"], o["ema200"] = ema(c, 50), ema(c, 200)
    o["atr"] = atr(o, 14)
    lr = np.log(c).diff()
    o["ret_1"] = lr
    o["ret_6"] = np.log(c).diff(6)
    o["ret_24"] = np.log(c).diff(24)
    o["ret_72"] = np.log(c).diff(72)
    o["dist_ema20"] = c / o["ema20"] - 1
    o["dist_ema50"] = c / o["ema50"] - 1
    o["dist_ema200"] = c / o["ema200"] - 1
    o["ema20_50"] = o["ema20"] / o["ema50"] - 1
    o["ema200_slope"] = o["ema200"].pct_change(24)
    o["rsi14"] = rsi(c, 14)
    o["atr_pct"] = o["atr"] / c
    o["atr_ratio"] = o["atr"] / o["atr"].rolling(100).mean()
    o["vol_24"] = lr.rolling(24).std()
    o["vol_ratio"] = o["volume"] / o["volume"].rolling(20).mean()
    o["taker_ratio"] = o["taker_buy_base"] / o["volume"].replace(0, np.nan)
    hi, lo = o["high"].rolling(48).max().shift(1), o["low"].rolling(48).min().shift(1)
    o["donch_hi"] = hi
    o["donch_pos"] = (c - lo) / (hi - lo).replace(0, np.nan)
    sma20, sd20 = c.rolling(20).mean(), c.rolling(20).std()
    o["bb_z"] = (c - sma20) / sd20.replace(0, np.nan)
    h24, l24 = o["high"].rolling(24).max(), o["low"].rolling(24).min()
    o["range_pos_24"] = (c - l24) / (h24 - l24).replace(0, np.nan)
    return o


# ------------------------------------------------------------------ señales primarias (solo LONG, spot)
def signal_breakout(o: pd.DataFrame, n: int = 48) -> pd.Series:
    """Ruptura del máximo de n velas previas, a favor de la tendencia mayor (close > EMA200)."""
    return (o["close"] > o["donch_hi"]) & (o["close"] > o["ema200"])


def signal_ema_cross(o: pd.DataFrame) -> pd.Series:
    """Cruce alcista EMA9/EMA21 (la regla que usa hoy bot-richy.py), con filtro de tendencia mayor."""
    up = (o["ema9"] > o["ema21"]) & (o["ema9"].shift(1) <= o["ema21"].shift(1))
    return up & (o["close"] > o["ema200"])


def signal_pullback(o: pd.DataFrame) -> pd.Series:
    """Retroceso dentro de tendencia alcista: close>EMA200, EMA50>EMA200 y RSI14 bajo, girando al alza."""
    trend = (o["close"] > o["ema200"]) & (o["ema50"] > o["ema200"])
    dip = (o["rsi14"].shift(1) < 38) & (o["rsi14"] > o["rsi14"].shift(1))
    return trend & dip


SIGNALS = {"breakout": signal_breakout, "ema_cross": signal_ema_cross, "pullback": signal_pullback}
