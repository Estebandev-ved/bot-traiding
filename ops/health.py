"""
Salud de los ciclos. GitHub Actions retrasa o se salta ejecuciones programadas; esto lo detecta antes que el
vigilante genérico de noticias (12 h) y distingue DOS fallos distintos:

  * latido atrasado    el bot no escribió en N horas (cron saltado o workflow roto).
  * velas atrasadas    el bot escribe, pero su última vela 4h procesada va por detrás (datos pegados o ciclos que no avanzan).
"""
from __future__ import annotations

HEARTBEAT_WARN_H = 6.0      # richy/breakout deberían escribir cada hora; 6 h = al menos 4-5 ejecuciones perdidas
HEARTBEAT_OK_H = 3.0
BAR_LAG_WARN_H = 8.0        # 2 velas de 4 h sin procesar
BAR_LAG_OK_H = 4.5


def bar_lag_hours(last_bar_iso: str | None, now_ts: float) -> float | None:
    """Horas entre la última vela 4h CERRADA que debería estar procesada y la que realmente se procesó."""
    if not last_bar_iso:
        return None
    import pandas as pd
    last = pd.Timestamp(last_bar_iso)
    if last.tzinfo is None:
        last = last.tz_localize("UTC")
    expected = pd.Timestamp(now_ts, unit="s", tz="UTC").floor("4h") - pd.Timedelta(hours=4)
    return max(0.0, (expected - last).total_seconds() / 3600.0)


def evaluate(snap: dict, was_bad: dict, now_ts: float) -> tuple[list[dict], dict]:
    """snap: {"richy": {"updated": ts}, "breakout": {"updated": ts, "last_bar": iso}}.
    Devuelve (eventos [{kind: 'down'|'up', key, text, hours}], nuevo estado {key: bool}).
    Histéresis: se alerta al cruzar WARN y se avisa la recuperación al bajar de OK (sin parpadeos)."""
    events, new = [], dict(was_bad or {})

    def check(key: str, label: str, hours: float | None, warn: float, ok: float, what: str):
        if hours is None:
            return
        bad = bool(new.get(key))
        if hours >= warn and not bad:
            events.append({"kind": "down", "key": key, "label": label, "hours": hours, "what": what})
            new[key] = True
        elif hours < ok and bad:
            events.append({"kind": "up", "key": key, "label": label, "hours": hours, "what": what})
            new[key] = False

    for name, label in (("richy", "Richy"), ("breakout", "Breakout 4h")):
        s = snap.get(name) or {}
        if s.get("updated") is not None:
            check(f"{name}_heartbeat", label, (now_ts - float(s["updated"])) / 3600.0,
                  HEARTBEAT_WARN_H, HEARTBEAT_OK_H, "latido")
    b = snap.get("breakout") or {}
    check("breakout_bars", "Breakout 4h", bar_lag_hours(b.get("last_bar"), now_ts), BAR_LAG_WARN_H, BAR_LAG_OK_H, "velas")
    return events, new
