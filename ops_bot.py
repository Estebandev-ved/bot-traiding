#!/usr/bin/env python3
"""
Ciclo de operación: gestor de portafolio + deriva paper-vs-backtest + salud de los ciclos.

  python ops_bot.py run --cloud     # Firestore + Telegram (GitHub Actions, cada hora)
  python ops_bot.py run --dry       # sin nube ni Telegram: solo comprueba que todo importa y corre
"""
import argparse
import json

from alerts import Telegram
from ops.runner import MemoryOps, run_cycle


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run"])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--cloud", action="store_true")
    g.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    if a.cloud:
        from ops.store import FirestoreOps
        store, tg = FirestoreOps(), Telegram()
    else:
        store, tg = MemoryOps(), Telegram(token="", chat_id="")
    r = run_cycle(store, tg)
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
