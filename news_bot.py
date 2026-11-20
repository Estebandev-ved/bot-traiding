#!/usr/bin/env python3
"""
Bot de noticias: descarga titulares cripto (ES/EN) + Fear & Greed, los publica en Firestore para el panel,
avisa por Telegram de noticias de riesgo y vigila que Richy y Breakout 4h sigan escribiendo.

  python news_bot.py run --cloud     # publica en Firestore (GitHub Actions, cada hora)
  python news_bot.py run --dry       # solo descarga y muestra (sin Firestore ni Telegram); para probar tu red
"""
import argparse
import json
import sys

from alerts import Telegram
from newsfeed.runner import MemoryStore, run_cycle


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run"])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--cloud", action="store_true", help="publicar en Firestore (necesita GOOGLE_APPLICATION_CREDENTIALS)")
    g.add_argument("--dry", action="store_true", help="solo descargar y mostrar")
    a = ap.parse_args()
    if a.cloud:
        from newsfeed.store import FirestoreNews
        store, tg = FirestoreNews(), Telegram()
    else:
        store, tg = MemoryStore(), Telegram(token="", chat_id="")        # dry: nunca envía
    r = run_cycle(store, tg)
    for fid, f in r["feeds"].items():
        print(f"  {'✔' if f['ok'] else '✘'} {f['name']:18s} {f['count']:3d} noticias" + (f"   {f['error']}" if f["error"] else ""))
    print(f"noticias: {r['items']} · de riesgo: {r['risk']} · fuentes ok: {r['feeds_ok']}/{len(r['feeds'])} · "
          f"Fear&Greed: {r['fng']['value'] if r['fng'] else 'sin datos'} · Telegram enviados: {r['sent']} (fallos {r['failed']})")
    if a.dry:
        for it in list(store.items.values())[:8]:
            print(f"   [{it['sentiment'][:3]}{' RIESGO' if it['risk'] else ''}] {it['source']}: {it['title'][:90]}")
    if r["feeds_ok"] == 0:
        sys.exit("Ninguna fuente respondió (¿sin internet o bloqueo?).")


if __name__ == "__main__":
    main()
