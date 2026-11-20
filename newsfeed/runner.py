"""Un ciclo del bot de noticias: descarga -> publica -> alertas de riesgo -> vigilante de los otros bots."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

from alerts import messages as am
from . import fetch

WATCH = [("Richy", "status", "current"), ("Breakout 4h", "breakout_status", "current")]
STALE_H, OK_H = 12.0, 6.0       # >12 h sin escribir = alerta; <6 h = recuperado (GitHub retrasa o se salta ejecuciones programadas)
RISK_WINDOW_H, MAX_ALERTS = 3.0, 3


class MemoryStore:
    """Almacén en memoria (pruebas y --dry). Mismo interfaz que FirestoreNews."""
    def __init__(self, updated: dict | None = None, flags: dict | None = None):
        self.state, self.items, self.status, self.pruned = None, {}, {}, 0
        self._updated, self._flags = updated or {}, flags or {}

    def load_state(self): return self.state
    def save_state(self, s): self.state = s
    def publish(self, items, feeds, fng, now, all_items=None):
        self.items.update({i["id"]: i for i in items})
        self.status["current"], self.status["fng"] = {"feeds": feeds, "count": len(all_items if all_items is not None else items)}, fng
    def prune(self, cutoff_ts): self.pruned = cutoff_ts
    def put_status(self, name, data): self.status[name] = data
    def updated(self, col, doc): return self._updated.get((col, doc))
    def strategy_flags(self, names, defaults=None): return {n: self._flags.get(n, (defaults or {}).get(n, True)) for n in names}


def run_cycle(store, tg, get=requests.get, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    items, feeds = fetch.collect(get, now=now)
    fng = fetch.fetch_fng(get)
    flags = store.strategy_flags(list(am.DEFAULT_FLAGS), defaults=am.DEFAULT_FLAGS)
    st = store.load_state()
    first = st is None
    st = st or {"notified": [], "watch": {}}

    # 1) publicar solo si hay algo (si TODAS las fuentes fallan no se borra lo anterior)
    published = set(st.get("published", []))
    if items or any(f["ok"] for f in feeds.values()):
        new = [i for i in items if i["id"] not in published]          # solo se escribe lo nuevo: menos escrituras en Firestore
        store.publish(new, feeds, fng, now, all_items=items)
        store.prune(int(now.timestamp()) - 7 * 86400)
        published.update(i["id"] for i in new)
        st["published"] = sorted(published)[-400:]
    else:
        store.put_status("current", {"feeds": feeds, "count": 0})

    sent = failed = 0

    def deliver(text, wanted):
        nonlocal sent, failed
        if not wanted or not tg.enabled:
            return True
        if tg.send(text):
            sent += 1
            return True
        failed += 1
        return False

    # 2) alertas de noticias de riesgo (nunca más de MAX_ALERTS por ciclo; la primera vez solo se marcan)
    notified = set(st["notified"])
    fresh = [i for i in items if i["risk"] and i["id"] not in notified and now.timestamp() - i["ts"] <= RISK_WINDOW_H * 3600]
    if first:
        notified.update(i["id"] for i in items)
    else:
        for i in fresh[:MAX_ALERTS]:
            if not deliver(am.news_risk(i), flags["notify_news"]):
                break
            notified.add(i["id"])
        notified.update(i["id"] for i in fresh[MAX_ALERTS:])         # el exceso se marca como visto para no acumular
    st["notified"] = sorted(notified)[-400:]

    # 3) vigilante: ¿algún bot dejó de escribir?
    for name, col, doc in WATCH:
        upd = store.updated(col, doc)
        if upd is None:
            continue                                                  # nunca escribió: no es una «caída», es que no se activó
        age = (now.timestamp() - upd) / 3600
        was_down = bool(st["watch"].get(name))
        if age > STALE_H and not was_down:
            if deliver(am.stalled(name, age), flags["notify_alerts"]):
                st["watch"][name] = True
        elif age < OK_H and was_down:
            if deliver(am.recovered(name), flags["notify_alerts"]):
                st["watch"][name] = False

    store.save_state(st)
    store.put_status("telegram", {"enabled": tg.enabled, "last_error": tg.last_error, "last_sent": tg.last_sent})
    return {"items": len(items), "risk": sum(1 for i in items if i["risk"]), "feeds_ok": sum(1 for f in feeds.values() if f["ok"]),
            "feeds": feeds, "fng": fng, "sent": sent, "failed": failed}
