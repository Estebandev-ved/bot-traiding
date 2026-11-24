"""
Laboratorio de MEJORAS sobre Breakout 4h.   python -m research.run_enhancements

Qué responde: ¿los overlays (filtro de régimen, tamaño por volatilidad / correlación) y más pares mejoran
el resultado FUERA DE MUESTRA, o solo se ven bien por haberlos mirado?

Reglas del experimento (declaradas ANTES de ver resultados):
  * Misma señal, mismos parámetros y mismo walk-forward ML que `run_research` (nada se vuelve a ajustar).
  * Un conjunto cerrado de configuraciones, todas reportadas (no solo la mejor). N de pruebas -> Sharpe deflactado.
  * DISEÑO = 2022-01 .. (hoy-365d). HOLDOUT = últimos 365 días. El holdout YA FUE VISTO en el informe anterior:
    sirve para no engañarnos, no como validación nueva. La única validación limpia es el paper trading hacia adelante.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

from .engine import Params
from .overlays import Overlays
from .portfolio import buy_hold_equal, portfolio_backtest
from .robust import robustness, verdict
from .run_research import OUT, PRIMARY, SYMS as BASE_SYMS, fmt
from .walkforward import build_dataset, walk_forward

EXTRA_SYMS = ["ADAUSDT", "LINKUSDT", "AVAXUSDT", "DOGEUSDT", "LTCUSDT"]
UNIVERSES = {"5 pares": BASE_SYMS, "10 pares": BASE_SYMS + EXTRA_SYMS}
CONFIGS = {
    "base (sin overlays)": Overlays.off(),
    "régimen BTC EMA200d (PRODUCCIÓN)": Overlays(),      # la configuración que corre en vivo (solo régimen)
    "régimen amplitud": Overlays(regime="breadth", vol_scale=False, corr_scale=False),
    "solo tamaño vol": Overlays(regime=None, vol_scale=True, corr_scale=False),
    "solo tamaño corr": Overlays(regime=None, vol_scale=False, corr_scale=True),
    "TODO (régimen BTC + vol + corr)": Overlays(regime="btc_ema200d", vol_scale=True, corr_scale=True),
}


def main(holdout_days: int = 365, kind: str = "gbm") -> dict:
    os.makedirs(OUT, exist_ok=True)
    now = pd.Timestamp.now(tz="UTC").floor("1D")
    hold_start = (now - pd.Timedelta(days=holdout_days)).strftime("%Y-%m-%d")
    design_start = "2022-01-01"
    p = Params(**PRIMARY)
    # Pruebas totales para el Sharpe deflactado: las 12 de esta corrida + 6 de la primera pasada, donde el multiplicador
    # de tamaño se aplicaba ANTES del tope de 1/3 por posición (casi nunca mordía) y se corrigió tras verlo.
    n_trials = len(CONFIGS) * len(UNIVERSES) + 6
    results = {"holdout_start": hold_start, "n_trials": n_trials, "universes": {}}
    baseline = None
    for uname, syms in UNIVERSES.items():
        ds = build_dataset(syms, "4h", "breakout", p)
        oos = walk_forward(ds, kind, design_start, None)
        sel = oos[oos["p"] >= oos["th"]]
        results["universes"][uname] = {}
        print(f"\n######## {uname}: {', '.join(syms)}")
        for cname, ov in CONFIGS.items():
            row = {}
            for seg, (a, b) in {"DISEÑO": (design_start, hold_start), "HOLDOUT": (hold_start, None)}.items():
                r = portfolio_backtest(ds.frames, sel, p, a, b, 1000.0, max_positions=3, overlays=ov)
                m = r["metrics"]
                rb = robustness(r["trades"]["port_ret"].to_numpy(), n_trials=n_trials) if len(r["trades"]) else {}
                if uname == "5 pares" and cname.endswith("(PRODUCCIÓN)") and seg == "DISEÑO" and len(r["trades"]):
                    t = r["trades"]       # línea base para el detector de deriva (ops/drift.py): misma configuración que corre en vivo
                    baseline = {"config": ov.to_dict(), "universe": syms, "period": [design_start, hold_start], "n": int(len(t)),
                                "net_ret": [round(float(x), 6) for x in t["net_ret"]],
                                "port_ret": [round(float(x), 6) for x in t["port_ret"]]}
                row[seg] = {"metrics": m, "skipped_regime": r.get("skipped_regime", 0), "robust": rb,
                            "bh": float(buy_hold_equal(ds.frames, a, b).iloc[-1] / 1000 - 1)}
            results["universes"][uname][cname] = row
            print(f"\n  {cname}   [{ov.describe()}]")
            for seg in row:
                print(f"    [{seg:7}] {fmt(row[seg]['metrics'])}  (régimen bloqueó {row[seg]['skipped_regime']})")
                rb = row[seg]["robust"]
                if rb.get("enough"):
                    print(f"              PSR={rb['psr']:.0%} DSR={rb['dsr']:.0%} MC dd95={rb['mc']['dd_p95']:.1%} "
                          f"P(pérdida)={rb['mc']['p_loss']:.0%} → {verdict(rb)}")
    path = os.path.join(OUT, "mejoras.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, ensure_ascii=False,
                  default=lambda o: None if isinstance(o, float) and np.isnan(o) else float(o) if isinstance(o, (np.floating, np.integer)) else str(o))
    if baseline:
        with open(os.path.join(OUT, "baseline_breakout.json"), "w", encoding="utf-8") as f:
            json.dump(baseline, f)
        print(f"Línea base de deriva: {baseline['n']} trades -> reports/baseline_breakout.json")
    print(f"\nGuardado en {path}")
    return results


if __name__ == "__main__":
    main()
