"""
Walk-forward con meta-labeling:
  1) Una señal primaria (breakout / ema_cross / pullback) propone entradas.
  2) Cada señal se etiqueta con el resultado NETO real del trade (SL/TP/tiempo, con costos).
  3) Un modelo (entrenado SOLO con trades que ya habían terminado antes del periodo de test) estima la
     probabilidad de que la señal sea ganadora. Solo se opera si p >= umbral (umbral elegido en validación
     interna del tramo de entrenamiento, nunca en test).
  4) Todo se evalúa fuera de muestra, por trimestres sucesivos.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .data import load_symbols
from .engine import Params, compute_metrics, label_signals, run_backtest
from .features import FEATURE_COLUMNS, SIGNALS, build_features

warnings.filterwarnings("ignore")
THRESHOLD_GRID = [0.0, 0.40, 0.45, 0.50, 0.55, 0.60]   # 0.0 => sin filtro ML


def make_model(kind: str = "gbm"):
    if kind == "logit":
        return make_pipeline(StandardScaler(), LogisticRegression(C=0.2, max_iter=500))
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=120,
                                          l2_regularization=2.0, min_samples_leaf=60, random_state=42)


@dataclass
class Dataset:
    frames: dict          # symbol -> DataFrame con features
    trades: pd.DataFrame  # una fila por señal etiquetada, con features y tiempos


def build_dataset(symbols, timeframe: str, signal: str, p: Params, start="2020-01-01") -> Dataset:
    data = load_symbols(symbols, timeframe, start)
    frames, rows = {}, []
    for sym, df in data.items():
        o = build_features(df)
        frames[sym] = o
        sig = SIGNALS[signal](o).fillna(False).to_numpy(dtype=bool, copy=True)
        sig[:250] = False   # warm-up de EMA200
        idx = np.flatnonzero(sig)
        t = label_signals(o, idx, p)
        if t.empty:
            continue
        feats = o.iloc[t["signal_idx"].to_numpy()][FEATURE_COLUMNS].reset_index(drop=True)
        t = pd.concat([t.reset_index(drop=True), feats], axis=1)
        t["symbol"] = sym
        t["sig_time"] = o.index[t["signal_idx"].to_numpy()]
        t["exit_time"] = o.index[t["exit_idx"].to_numpy()]
        t["entry_time"] = o.index[t["entry_idx"].to_numpy()]
        rows.append(t)
    trades = pd.concat(rows, ignore_index=True).dropna(subset=FEATURE_COLUMNS)
    trades["win"] = (trades["net_ret"] > 0).astype(int)
    return Dataset(frames, trades.sort_values("sig_time").reset_index(drop=True))


def _choose_threshold(train: pd.DataFrame, kind: str) -> float:
    """Validación interna: entrena en el 75% más antiguo, elige umbral en el 25% reciente (con purga)."""
    cut = train["sig_time"].quantile(0.75)
    fit = train[train["exit_time"] < cut]
    val = train[train["sig_time"] >= cut]
    if len(fit) < 200 or len(val) < 60 or fit["win"].nunique() < 2:
        return 0.50
    m = make_model(kind).fit(fit[FEATURE_COLUMNS], fit["win"])
    pv = m.predict_proba(val[FEATURE_COLUMNS])[:, 1]
    best, best_score = 0.50, -9
    for th in THRESHOLD_GRID[1:]:
        sel = val[pv >= th]
        if len(sel) < 25:
            continue
        score = sel["net_ret"].mean() - 0.5 * sel["net_ret"].std() / np.sqrt(len(sel))  # penaliza incertidumbre
        if score > best_score:
            best, best_score = th, score
    return best


def walk_forward(ds: Dataset, kind: str, test_start: str, test_end: str | None, step_months: int = 3,
                 min_train: int = 300) -> pd.DataFrame:
    """Devuelve las señales de test con su probabilidad OOS (columna 'p') y el umbral usado ('th')."""
    t = ds.trades
    start = pd.Timestamp(test_start, tz="UTC")
    end = pd.Timestamp(test_end, tz="UTC") if test_end else t["sig_time"].max() + pd.Timedelta(days=1)
    out, cur = [], start
    while cur < end:
        nxt = min(cur + pd.DateOffset(months=step_months), end)
        train = t[t["exit_time"] < cur]
        test = t[(t["sig_time"] >= cur) & (t["sig_time"] < nxt)].copy()
        if len(train) >= min_train and train["win"].nunique() == 2 and len(test):
            th = _choose_threshold(train, kind)
            model = make_model(kind).fit(train[FEATURE_COLUMNS], train["win"])
            test["p"] = model.predict_proba(test[FEATURE_COLUMNS])[:, 1]
            test["th"] = th
            out.append(test)
        cur = nxt
    return pd.concat(out) if out else pd.DataFrame()


def evaluate(ds: Dataset, oos: pd.DataFrame, p: Params, use_ml: bool, start: str, end: str | None,
             initial: float = 1000.0) -> dict:
    """Backtest secuencial por símbolo sobre el periodo OOS y portafolio equiponderado."""
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC") if end else None
    curves, trade_frames = {}, []
    for sym, o in ds.frames.items():
        sl = o[(o.index >= start_ts) & ((o.index < end_ts) if end_ts is not None else True)]
        cand = oos[oos["symbol"] == sym]
        if use_ml:
            cand = cand[cand["p"] >= cand["th"]]
        if cand.empty or sl.empty:
            continue
        offset = o.index.get_loc(sl.index[0])
        cand = cand.copy()
        for col in ("entry_idx", "exit_idx"):
            cand[col] = cand[col] - offset
        cand = cand[(cand["entry_idx"] >= 0) & (cand["exit_idx"] < len(sl))]
        if cand.empty:
            continue
        bt = run_backtest(sl, cand, p, initial)
        curves[sym] = bt["bar_ret"]
        tr = bt["trades"].copy()
        tr["symbol"] = sym
        tr["entry_time"] = sl.index[tr["entry_idx"].to_numpy()]
        trade_frames.append(tr)
    if not curves:
        return {"metrics": {"n_trades": 0}, "equity": None, "trades": pd.DataFrame(), "per_symbol": {}}
    rets = pd.DataFrame(curves).fillna(0.0)
    port_ret = rets.mean(axis=1)                       # equiponderado, rebalanceo por vela
    eq = initial * (1 + port_ret).cumprod()
    trades = pd.concat(trade_frames, ignore_index=True)
    per_symbol = {s: compute_metrics(initial * (1 + rets[s]).cumprod(), trades[trades["symbol"] == s], initial)
                  for s in rets.columns}
    return {"metrics": compute_metrics(eq, trades, initial), "equity": eq, "trades": trades,
            "per_symbol": per_symbol}


def buy_and_hold(frames: dict, start: str, end: str | None, initial: float = 1000.0) -> pd.Series:
    s, e = pd.Timestamp(start, tz="UTC"), (pd.Timestamp(end, tz="UTC") if end else None)
    rets = {}
    for sym, o in frames.items():
        c = o["close"][(o.index >= s) & ((o.index < e) if e is not None else True)]
        rets[sym] = c.pct_change().fillna(0)
    r = pd.DataFrame(rets).fillna(0).mean(axis=1)
    return initial * (1 + r).cumprod()
