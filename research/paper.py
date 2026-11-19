"""
Motor de PAPER TRADING (sin dinero) para la estrategia validada: ruptura 4h + filtro ML.
Misma lógica que el backtest (entrada al open siguiente, SL/TP por ATR, comisiones, slippage, capital compartido),
pero incremental y con estado persistente, para generar un historial verificable en vivo.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict

import joblib
import numpy as np
import pandas as pd

from .engine import Params
from .features import FEATURE_COLUMNS, build_features, signal_breakout
from .walkforward import _choose_threshold, build_dataset, make_model

SYMS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(ROOT, "models", "breakout_gbm.joblib")
STATE_PATH = os.path.join(ROOT, "paper_state.json")
PRIMARY = Params(sl_atr=2.0, tp_atr=4.0, max_hold=24)
BAR = pd.Timedelta(hours=4)


# ------------------------------------------------------------------ modelo
def train_final(cutoff: str | None = None, path: str = MODEL_PATH, kind: str = "gbm") -> dict:
    """Entrena con todos los trades ya TERMINADOS antes de `cutoff` (por defecto, ahora)."""
    p = PRIMARY
    ds = build_dataset(SYMS, "4h", "breakout", p)
    cut = pd.Timestamp(cutoff, tz="UTC") if cutoff else pd.Timestamp.now(tz="UTC")
    train = ds.trades[ds.trades["exit_time"] < cut]
    th = _choose_threshold(train, kind)
    model = make_model(kind).fit(train[FEATURE_COLUMNS], train["win"])
    bundle = {"model": model, "threshold": th, "params": asdict(p), "features": FEATURE_COLUMNS,
              "trained_at": str(pd.Timestamp.now(tz="UTC")), "cutoff": str(cut), "n_train": int(len(train)),
              "base_win_rate": float(train["win"].mean())}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    joblib.dump(bundle, path)
    return bundle


def load_bundle(path: str = MODEL_PATH) -> dict:
    return joblib.load(path)


# ------------------------------------------------------------------ estado
def new_state(capital: float) -> dict:
    return {"capital_initial": capital, "equity": capital, "positions": {}, "closed": [], "last_ts": None,
            "log": []}


def load_state(path: str = STATE_PATH, capital: float = 25.0) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return new_state(capital)


def save_state(state: dict, path: str = STATE_PATH) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def make_features(raw: dict) -> dict:
    return {s: build_features(df) for s, df in raw.items()}


# ------------------------------------------------------------------ núcleo
def _close_position(state: dict, sym: str, ts, exit_px: float, reason: str, p: Params, bar_idx: int) -> None:
    pos = state["positions"].pop(sym)
    net = (exit_px * (1 - p.slippage) * (1 - p.fee)) / (pos["entry"] * (1 + p.fee)) - 1
    pnl = pos["size"] * net
    state["equity"] += pnl
    state["closed"].append({"symbol": sym, "entry_time": pos["entry_ts"], "exit_time": str(ts),
                            "entry": pos["entry"], "exit": exit_px, "reason": reason, "size": pos["size"],
                            "net_ret": net, "pnl": pnl, "equity_after": state["equity"], "p": pos["p"]})


def advance(state: dict, feats: dict, bundle: dict, last_closed_ts, max_positions: int = 3,
            min_notional: float = 5.0, risk_per_trade: float = 0.02) -> int:
    """Procesa en orden todas las velas cerradas nuevas. Devuelve cuántas velas procesó.
    `feats[sym]` puede incluir UNA vela final aún en formación: solo se usa su `open` para entrar."""
    p = Params(**{k: v for k, v in bundle["params"].items() if k != "extra"})
    p.risk_per_trade = risk_per_trade
    th, model = bundle["threshold"], bundle["model"]
    index = None
    for o in feats.values():
        index = o.index if index is None else index.union(o.index)
    last_closed = pd.Timestamp(last_closed_ts)
    start = pd.Timestamp(state["last_ts"]) if state["last_ts"] else None
    todo = [t for t in index if t <= last_closed and (start is None or t > start)]
    sigs_cache = {s: signal_breakout(o).fillna(False).to_numpy(dtype=bool, copy=True) for s, o in feats.items()}
    done = 0
    for ts in todo:
        # 1) gestionar posiciones abiertas con la vela ts
        for sym in list(state["positions"]):
            o = feats[sym]
            if ts not in o.index:
                continue
            row = o.loc[ts]
            pos = state["positions"][sym]
            if pd.Timestamp(pos["entry_ts"]) > ts:
                continue
            first = pos["bars_done"] == 0
            exited = False
            if (not first) and row["open"] <= pos["stop"]:
                _close_position(state, sym, ts, row["open"], "SL_GAP", p, 0); exited = True
            elif row["low"] <= pos["stop"]:
                _close_position(state, sym, ts, pos["stop"], "SL", p, 0); exited = True
            elif row["high"] >= pos["target"]:
                _close_position(state, sym, ts, pos["target"], "TP", p, 0); exited = True
            else:
                pos["bars_done"] += 1
                if pos["bars_done"] >= p.max_hold:
                    _close_position(state, sym, ts, row["close"], "TIME", p, 0); exited = True
            if exited:
                continue
        # 2) señales al cierre de ts -> entrada al open de la vela siguiente
        cands = []
        for sym, o in feats.items():
            if ts not in o.index or sym in state["positions"]:
                continue
            i = o.index.get_loc(ts)
            if i < 250 or not sigs_cache[sym][i]:
                continue
            x = o.iloc[i][FEATURE_COLUMNS]
            if x.isna().any() or not np.isfinite(o["atr"].iloc[i]) or o["atr"].iloc[i] <= 0:
                continue
            if i + 1 >= len(o):
                return done            # aún no existe la vela siguiente: reintentar en la próxima ejecución
            pr = float(model.predict_proba(pd.DataFrame([x.to_numpy()], columns=FEATURE_COLUMNS))[0, 1])
            if pr >= th:
                cands.append((pr, sym, i))
        for pr, sym, i in sorted(cands, reverse=True):
            if len(state["positions"]) >= max_positions:
                break
            o = feats[sym]
            entry = float(o["open"].iloc[i + 1]) * (1 + p.slippage)
            atr = float(o["atr"].iloc[i])
            stop, target = entry - p.sl_atr * atr, entry + p.tp_atr * atr
            if stop <= 0:
                continue
            f = min(p.risk_per_trade / ((entry - stop) / entry), 1.0 / max_positions)
            size = state["equity"] * f
            if size < min_notional:
                state["log"].append(f"{ts} {sym}: señal omitida, tamaño {size:.2f} < mínimo {min_notional}")
                continue
            state["positions"][sym] = {"entry_ts": str(o.index[i + 1]), "entry": entry, "stop": stop,
                                       "target": target, "size": size, "p": pr, "bars_done": 0}
        state["last_ts"] = str(ts)
        done += 1
    state["log"] = state["log"][-200:]
    return done


def summary(state: dict) -> dict:
    c = pd.DataFrame(state["closed"])
    out = {"capital_inicial": state["capital_initial"], "equity_realizado": round(state["equity"], 4),
           "retorno": state["equity"] / state["capital_initial"] - 1, "abiertas": len(state["positions"]),
           "cerradas": len(c), "ultima_vela": state["last_ts"]}
    if len(c):
        out.update({"win_rate": float((c["net_ret"] > 0).mean()), "avg_trade_net": float(c["net_ret"].mean()),
                    "profit_factor": float(c.loc[c.pnl > 0, "pnl"].sum() / abs(c.loc[c.pnl <= 0, "pnl"].sum()))
                    if (c.pnl <= 0).any() and c.loc[c.pnl <= 0, "pnl"].sum() != 0 else None,
                    "max_dd_realizado": float((c["equity_after"] / c["equity_after"].cummax() - 1).min())})
    return out
