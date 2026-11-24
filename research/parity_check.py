"""
Prueba de paridad laboratorio <-> paper trader (datos reales).   python -m research.parity_check [--desde 2025-06-01]

Mismas señales, mismo "modelo" (una función determinista de las features, para que no haya azar) y mismo filtro de
régimen: `portfolio_backtest` (laboratorio) y `paper.advance` (en vivo) deben abrir y cerrar EXACTAMENTE los mismos trades.
Si difieren, lo que se validó en el laboratorio no es lo que corre en vivo.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict

import numpy as np
import pandas as pd

from . import paper
from .engine import Params
from .features import FEATURE_COLUMNS
from .overlays import Overlays
from .portfolio import portfolio_backtest
from .walkforward import build_dataset

TH = 0.5


def score(ret_6) -> np.ndarray:
    """Probabilidad de mentira pero determinista y distinta por señal (desempata sin depender del orden)."""
    return 1.0 / (1.0 + np.exp(-60.0 * np.asarray(ret_6, dtype=float)))


class Det:
    def predict_proba(self, X):
        p = float(score(X["ret_6"].iloc[0]))
        return np.array([[1 - p, p]])


def compare(since: str, overlays: Overlays, syms=None, verbose=True) -> dict:
    syms = syms or paper.DEFAULT_SYMS
    p = Params(**paper.PRIMARY.__dict__) if hasattr(paper.PRIMARY, "__dict__") else paper.PRIMARY
    ds = build_dataset(syms, "4h", "breakout", p)
    cand = ds.trades.copy()
    cand["p"] = score(cand["ret_6"])
    cand = cand[cand["p"] >= TH]
    lab = portfolio_backtest(ds.frames, cand, p, since, None, 1000.0, max_positions=3, overlays=overlays)
    lab_set = {(t.symbol, str(t.entry_time), str(t.exit_time)) for t in lab["trades"].itertuples()} if len(lab["trades"]) else set()

    start = pd.Timestamp(since, tz="UTC")
    index = None
    for o in ds.frames.values():
        index = o.index if index is None else index.union(o.index)
    last_closed = index[-2]                                   # la última vela queda como "en formación"
    st = paper.new_state(1000.0)
    st["last_ts"] = str(index[index >= start][0] - pd.Timedelta(hours=4))
    bundle = {"params": asdict(p), "threshold": TH, "model": Det()}
    paper.advance(st, ds.frames, bundle, last_closed, max_positions=3, min_notional=5.0, overlays=overlays)
    live_set = {(c["symbol"], str(pd.Timestamp(c["entry_time"])), str(pd.Timestamp(c["exit_time"]))) for c in st["closed"]}
    # el laboratorio solo cuenta trades cerrados dentro de la ventana; las posiciones aún abiertas en vivo no se comparan
    only_lab, only_live = sorted(lab_set - live_set), sorted(live_set - lab_set)
    # tamaños: donde actúan los multiplicadores de volatilidad / correlación
    lab_size = {(t.symbol, str(t.entry_time)): float(t.size) for t in lab["trades"].itertuples()} if len(lab["trades"]) else {}
    live_size = {(c["symbol"], str(pd.Timestamp(c["entry_time"]))): float(c["size"]) for c in st["closed"]}
    common = lab_size.keys() & live_size.keys()
    size_err = max((abs(lab_size[k] / live_size[k] - 1) for k in common if live_size[k] > 0), default=0.0)
    out = {"lab": len(lab_set), "live": len(live_set), "common": len(lab_set & live_set), "only_lab": only_lab,
           "only_live": only_live, "size_err": size_err, "regime_skips_live": st.get("filters", {}).get("regime", 0),
           "regime_skips_lab": lab.get("skipped_regime", 0)}
    if verbose:
        print(f"[{overlays.describe():34}] lab={out['lab']:3d} vivo={out['live']:3d} coinciden={out['common']:3d} "
              f"solo_lab={len(only_lab)} solo_vivo={len(only_live)} error_tamaño={out['size_err']:.2e}")
        for x in only_lab[:5]:
            print("   solo laboratorio:", x)
        for x in only_live[:5]:
            print("   solo en vivo   :", x)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", default="2025-01-01")
    a = ap.parse_args()
    ok = True
    for ov in (Overlays.off(), Overlays(), Overlays(regime="btc_ema200d", vol_scale=True, corr_scale=True)):
        r = compare(a.desde, ov)
        ok &= not r["only_lab"] and not r["only_live"] and r["lab"] > 0 and r["size_err"] < 1e-6
    print("PARIDAD OK" if ok else "PARIDAD ROTA")
    raise SystemExit(0 if ok else 1)
