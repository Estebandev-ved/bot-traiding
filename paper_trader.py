#!/usr/bin/env python3
"""
Paper trader (SIN dinero) de la estrategia validada: ruptura 4h + filtro ML, precios reales de Binance.

  python paper_trader.py train     # entrena el modelo con todo el histórico y lo guarda en models/
  python paper_trader.py run       # procesa velas 4h nuevas (ejecutar cada 4h, minuto 1-5 UTC)
  python paper_trader.py status    # resumen del historial en vivo
  python paper_trader.py reset     # borra el estado (empezar un nuevo historial)

Programar (cron):  2 */4 * * *  cd /ruta/bot-traiding && python3 paper_trader.py run >> paper.log 2>&1
No necesita API keys: solo lee datos públicos de mercado.
"""
import argparse
import json
import os
import sys

import pandas as pd

from research import paper
from research.live import fetch_live_4h


def cmd_train(_):
    b = paper.train_final()
    print(f"Modelo guardado en {paper.MODEL_PATH}\n  umbral={b['threshold']}  n_train={b['n_train']}  "
          f"win_rate_base={b['base_win_rate']:.1%}  entrenado_con_datos_hasta={b['cutoff']}")


def cmd_run(a):
    if not os.path.exists(paper.MODEL_PATH):
        print("No hay modelo; entrenando uno nuevo...")
        paper.train_final()
    bundle = paper.load_bundle()
    state = paper.load_state(capital=a.capital)
    frames, last_closed = fetch_live_4h(paper.SYMS)
    feats = paper.make_features(frames)
    if state["last_ts"] is None:
        state["last_ts"] = str(last_closed - pd.Timedelta(hours=4))   # el historial empieza AHORA
        print(f"Nuevo historial de paper trading con capital {state['capital_initial']} USDT")
    n_open, n_closed = len(state["positions"]), len(state["closed"])
    n = paper.advance(state, feats, bundle, last_closed, max_positions=a.max_positions,
                      min_notional=a.min_notional, risk_per_trade=a.risk)
    paper.save_state(state)
    print(f"[{pd.Timestamp.now(tz='UTC'):%Y-%m-%d %H:%M}Z] velas nuevas: {n} | abiertas {n_open}->{len(state['positions'])}"
          f" | cerradas {n_closed}->{len(state['closed'])} | equity {state['equity']:.4f}")
    for sym, p in state["positions"].items():
        print(f"   ABIERTA {sym}: entrada {p['entry']:.4f} SL {p['stop']:.4f} TP {p['target']:.4f} "
              f"tamaño {p['size']:.2f} USDT (p={p['p']:.2f})")


def cmd_status(_):
    state = paper.load_state()
    print(json.dumps(paper.summary(state), indent=2, ensure_ascii=False, default=str))
    if state["closed"]:
        print(pd.DataFrame(state["closed"]).tail(10)[["symbol", "entry_time", "exit_time", "reason", "net_ret", "pnl"]]
              .to_string(index=False))
    n = len(state["closed"])
    if n < 100:
        print(f"\nOJO: {n} trades cerrados. Con menos de ~100 trades NO se puede distinguir suerte de habilidad.")


def cmd_reset(_):
    if os.path.exists(paper.STATE_PATH):
        os.remove(paper.STATE_PATH)
    print("Estado borrado.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("train").set_defaults(f=cmd_train)
    r = sp.add_parser("run")
    r.add_argument("--capital", type=float, default=25.0, help="capital inicial simulado (USDT)")
    r.add_argument("--max-positions", type=int, default=3)
    r.add_argument("--min-notional", type=float, default=5.0, help="mínimo por orden en Binance (USDT)")
    r.add_argument("--risk", type=float, default=0.02, help="riesgo por trade como fracción del equity")
    r.set_defaults(f=cmd_run)
    sp.add_parser("status").set_defaults(f=cmd_status)
    sp.add_parser("reset").set_defaults(f=cmd_reset)
    args = ap.parse_args()
    args.f(args)
