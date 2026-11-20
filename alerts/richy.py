"""Eventos de Telegram para Richy. El estado `tg` vive dentro de session.state (Firestore bot_state/paper):
  closed: claves de operaciones ya avisadas · open: clave de la posición abierta ya avisada
  pause / kill: último estado conocido (se avisa solo al cambiar)
Richy reproduce todo el historial en cada ciclo, así que la primera vez se marca lo existente sin avisar."""
from __future__ import annotations

from . import messages as m

KEEP = 500


def _tkey(t: dict) -> str:
    return f"{t['entry_time'].isoformat()}|{t['exit_time'].isoformat()}"


def process(tgs: dict, symbol: str, res: dict, sent: dict, risk: dict, flags: dict, tg) -> dict:
    out = {"sent": 0, "failed": 0}

    def deliver(text: str, wanted: bool) -> bool:
        if not wanted or not tg.enabled:
            return True
        if tg.send(text):
            out["sent"] += 1
            return True
        out["failed"] += 1
        return False

    trades, op = res["trades"], res["open"]
    if not tgs.get("init"):
        tgs.update({"init": True, "closed": [_tkey(t) for t in trades], "open": op["since"].isoformat() if op else None,
                    "pause": bool(sent.get("pause")), "kill": bool(risk.get("killed"))})
        return out
    done = set(tgs["closed"])
    for t in trades:
        k = _tkey(t)
        if k in done:
            continue
        if not deliver(m.richy_close(symbol, t, res["equity"].iloc[-1]), flags.get("notify_close", True)):
            return out
        tgs["closed"].append(k)
    tgs["closed"] = tgs["closed"][-KEEP:]
    cur = op["since"].isoformat() if op else None
    if cur and cur != tgs.get("open"):
        if not deliver(m.richy_open(symbol, op), flags.get("notify_open", True)):
            return out
    tgs["open"] = cur
    paused = bool(sent.get("pause"))
    if paused != tgs.get("pause"):
        text = m.richy_pause(sent.get("reasons", []), sent.get("fng")) if paused else m.recovered("Richy (noticias)")
        if not deliver(text, flags.get("notify_alerts", True)):
            return out
        tgs["pause"] = paused
    killed = bool(risk.get("killed"))
    if killed and not tgs.get("kill"):
        if not deliver(m.richy_kill(risk.get("kill_reason", "")), flags.get("notify_alerts", True)):
            return out
    tgs["kill"] = killed
    return out
