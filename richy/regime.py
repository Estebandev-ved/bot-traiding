"""Detección de régimen: tendencia / rango / volatilidad alta.

Sin dependencias: reglas sobre ADX y ATR%. Si hay LightGBM instalado, RegimeModel
aprende a *anticipar* el régimen de las próximas barras con features rezagadas.
El modelo solo elige qué estrategia se activa; no decide órdenes."""
import numpy as np
import pandas as pd
from . import indicators as ind

REGIMES = ["trend", "range", "volatile"]


def features(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close"]
    a = ind.atr(df)
    f = pd.DataFrame(index=df.index)
    f["adx"] = ind.adx(df)
    f["atr_pct"] = a / c
    f["atr_rank"] = f["atr_pct"].rolling(200, min_periods=50).rank(pct=True)
    f["ret_5"] = c.pct_change(5)
    f["ret_20"] = c.pct_change(20)
    f["rsi"] = ind.rsi(c)
    f["ema_gap"] = ind.ema(c, 20) / ind.ema(c, 50) - 1
    f["vol_ratio"] = df["volume"] / df["volume"].rolling(50).mean() if "volume" in df else 1.0
    return f


def rule_regime(df: pd.DataFrame, adx_trend: float = 25.0, vol_rank: float = 0.9) -> pd.Series:
    f = features(df)
    r = pd.Series("range", index=df.index)
    r[f["adx"] > adx_trend] = "trend"
    r[f["atr_rank"] > vol_rank] = "volatile"   # la volatilidad extrema manda sobre la tendencia
    return r


class RegimeModel:
    """LightGBM que predice el régimen (por reglas) `horizon` barras adelante."""

    def __init__(self, horizon: int = 12):
        self.horizon, self.model = horizon, None

    def fit(self, df: pd.DataFrame):
        import lightgbm as lgb  # opcional
        X = features(df)
        y = rule_regime(df).shift(-self.horizon)
        m = X.notna().all(axis=1) & y.notna()
        self.model = lgb.LGBMClassifier(n_estimators=150, learning_rate=0.05, num_leaves=15,
                                        min_child_samples=40, verbose=-1)
        self.model.fit(X[m], y[m])
        return self

    def predict(self, df: pd.DataFrame) -> pd.Series:
        X = features(df).ffill().fillna(0)
        return pd.Series(self.model.predict(X), index=df.index)


def get_regimes(df: pd.DataFrame, model: RegimeModel = None) -> pd.Series:
    return model.predict(df) if model is not None and model.model is not None else rule_regime(df)
