"""Eventos de Telegram del paper trader Breakout 4h, sin duplicados.

`state["notif"]` guarda qué ya se avisó: nº de trades cerrados, posiciones abiertas y el día del resumen.
  * Solo avanza cuando Telegram aceptó el mensaje, así que un fallo se reintenta en el siguiente ciclo.
  * Si Telegram no está configurado, o el interruptor del evento está apagado, el evento se da por visto:
    activarlo más tarde no dispara un aluvión con el historial.
  * Un estado antiguo (sin `notif`) se inicializa con lo que ya existe, sin avisar de nada.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import messages as m

DAILY_HOUR_UTC = 12   # el resumen diario sale en el primer ciclo a partir de las 12:00 UTC


def _key(sym: str, p: dict) -> str:
    return f"{sym}|{p['entry_ts']}"


def new_notif(state: dict, fresh: bool) -> dict:
    """fresh=True: sesión nueva, todo lo que ocurra se avisa. fresh=False: se asume lo existente como ya avisado."""
    return {"closed": 0 if fresh else len(state.get("closed", [])),
            "open": [] if fresh else [_key(s, p) for s, p in state.get("positions", {}).items()],
            "daily": None, "sent_total": 0, "last_sent": None}


def process(state: dict, tg, flags: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    n = state.get("notif")
    if n is None:
        n = state["notif"] = new_notif(state, fresh=False)
    sent = failed = 0

    def deliver(text: str, wanted: bool) -> bool:
        nonlocal sent, failed
        if not wanted or not tg.enabled:
            return True                      # se da por visto sin enviar
        if tg.send(text):
            sent += 1
            n["sent_total"], n["last_sent"] = n.get("sent_total", 0) + 1, tg.last_sent
            return True
        failed += 1
        return False

    ok = True
    for sym, p in state.get("positions", {}).items():
        k = _key(sym, p)
        if k not in n["open"]:
            if not deliver(m.breakout_open(sym, p), flags.get("notify_open", True)):
                ok = False
                break
            n["open"].append(k)
    if ok:
        for i in range(n["closed"], len(state.get("closed", []))):
            if not deliver(m.breakout_close(state["closed"][i], state), flags.get("notify_close", True)):
                ok = False
                break
            n["closed"] = i + 1
    n["open"] = [k for k in n["open"] if k in {_key(s, p) for s, p in state.get("positions", {}).items()}]
    today = now.date().isoformat()
    if ok and now.hour >= DAILY_HOUR_UTC and n.get("daily") != today:
        if deliver(m.breakout_daily(state), flags.get("notify_daily", True)):
            n["daily"] = today
    return {"sent": sent, "failed": failed}
