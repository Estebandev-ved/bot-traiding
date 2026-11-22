"""
Un ciclo de operación (cada hora en GitHub Actions):
  1) gestor de portafolio  -> índice combinado, límites y compuerta que leen Richy y Breakout.
  2) deriva paper vs backtest del Breakout.
  3) salud de los ciclos (latidos y velas atrasadas).
Todo falla "abierto": ningún error de aquí apaga a los bots. Las alertas de Telegram no se repiten (histéresis).
"""
from __future__ import annotations

import json
import time

from alerts import messages as am

from . import drift as dr
from . import health as hl
from .portfolio import PortfolioConfig, Sleeve, evaluate, new_state

RICHY_EQUITY0 = 10_000.0          # capital inicial del paper de Richy (PaperSession) si el documento aún no lo trae
FLAG_ENFORCE = "portfolio_enforce"


class MemoryOps:
    """Almacén en memoria (pruebas / --dry). Mismo interfaz que FirestoreOps."""
    def __init__(self, docs: dict | None = None, flags: dict | None = None, closed: list | None = None):
        self.docs, self._flags, self._closed, self.state = dict(docs or {}), flags or {}, closed or [], None
        self.written: dict = {}

    def get(self, col, doc): return self.docs.get((col, doc))
    def put(self, col, doc, data):
        self.written[(col, doc)] = data
        self.docs[(col, doc)] = data
    def load_state(self): return self.state
    def save_state(self, s): self.state = s
    def flags(self, names, defaults=None): return {n: self._flags.get(n, (defaults or {}).get(n, True)) for n in names}
    def breakout_closed(self): return self._closed


def _sleeve_richy(d: dict | None) -> Sleeve | None:
    if not d or d.get("equity") is None:
        return None
    return Sleeve("richy", float(d["equity"]), float(d.get("equity0") or RICHY_EQUITY0), float(d.get("exposure") or 0.0),
                  {k: float(v) for k, v in (d.get("assets") or {}).items()}, d.get("updated"))


def _sleeve_breakout(d: dict | None) -> Sleeve | None:
    if not d or d.get("equity") is None:
        return None
    eq = float(d["equity"])
    expo = d.get("exposure")
    assets = d.get("assets")
    if expo is None:                                           # documento anterior a esta versión: se deduce de las posiciones
        pos = d.get("positions") or []
        assets = {p["symbol"]: float(p["size"]) / eq for p in pos} if eq > 0 else {}
        expo = sum(assets.values())
    return Sleeve("breakout", eq, float(d.get("capital_initial") or eq), float(expo),
                  {k: float(v) for k, v in (assets or {}).items()}, d.get("updated"))


def run_cycle(store, tg, now_ts: float | None = None, baseline: dict | None = None) -> dict:
    now_ts = now_ts if now_ts is not None else time.time()
    st = store.load_state() or {}
    st.setdefault("portfolio", new_state())
    st.setdefault("alerts", {"halt": False})
    st.setdefault("health", {})
    st.setdefault("drift_state", "wait")
    st.setdefault("warned", {})
    flags = store.flags(list(am.DEFAULT_FLAGS) + [FLAG_ENFORCE], defaults={**am.DEFAULT_FLAGS, FLAG_ENFORCE: True})
    sent = failed = 0

    def deliver(text: str, wanted: bool = True) -> bool:
        nonlocal sent, failed
        if not wanted or not tg.enabled:
            return True
        if tg.send(text):
            sent += 1
            return True
        failed += 1
        return False

    # 1) portafolio ------------------------------------------------------------------------------------------
    richy_doc, bo_doc = store.get("status", "current"), store.get("breakout_status", "current")
    sleeves = [s for s in (_sleeve_richy(richy_doc), _sleeve_breakout(bo_doc)) if s]
    cfg = PortfolioConfig.from_dict(store.get("portfolio_status", "config"))
    decision, st["portfolio"] = evaluate(sleeves, cfg, st["portfolio"], now_ts)
    enforce = bool(flags.get(FLAG_ENFORCE, True))
    gate = {"allow_new": decision["allow_new"] or not enforce, "reasons": decision["reasons"] if enforce else [],
            "blocked_symbols": decision["blocked_symbols"] if enforce else [], "enforce": enforce, "updated": now_ts}
    store.put("portfolio_status", "gate", gate)
    store.put("portfolio_status", "current", {**decision, "config": cfg.to_dict(), "enforce": enforce,
                                              "history": st["portfolio"]["history"][-200:], "updated": now_ts,
                                              "sleeves": {s.name: {"equity": s.equity, "equity0": s.equity0,
                                                                   "exposure": s.exposure} for s in sleeves}})
    halted = not gate["allow_new"]                      # en modo observación nada se frena, así que no se avisa de pausa
    if halted and not st["alerts"]["halt"]:
        if deliver(am.portfolio_halt(decision["reasons"], decision["index"]), flags["notify_alerts"]):
            st["alerts"]["halt"] = True
    elif not halted and st["alerts"]["halt"]:
        if deliver(am.portfolio_resume(decision["index"]), flags["notify_alerts"]):
            st["alerts"]["halt"] = False
    today = time.strftime("%Y-%m-%d", time.gmtime(now_ts))
    for w in decision["warnings"]:
        if w != "sin datos de los bots" and st["warned"].get(w) != today:
            if deliver(am.portfolio_warn([w]), flags["notify_alerts"]):
                st["warned"][w] = today
    st["warned"] = {k: v for k, v in st["warned"].items() if v == today}

    # 2) deriva ------------------------------------------------------------------------------------------------
    report = dr.drift_report(store.breakout_closed(), baseline if baseline is not None else dr.load_baseline())
    store.put("portfolio_status", "drift", {**report, "updated": now_ts})
    if report["state"] in ("warn", "bad") and st["drift_state"] not in ("warn", "bad"):
        if deliver(am.drift_alert("Breakout 4h", report), flags["notify_alerts"]):
            st["drift_state"] = report["state"]
    elif report["state"] in ("ok", "wait"):
        st["drift_state"] = report["state"]
    elif report["state"] == "bad" and st["drift_state"] == "warn":
        if deliver(am.drift_alert("Breakout 4h", report), flags["notify_alerts"]):    # escaló de aviso a grave
            st["drift_state"] = "bad"

    # 3) salud de los ciclos ------------------------------------------------------------------------------------
    snap = {"richy": {"updated": (richy_doc or {}).get("updated")},
            "breakout": {"updated": (bo_doc or {}).get("updated"), "last_bar": (bo_doc or {}).get("last_bar")}}
    events, new_health = hl.evaluate(snap, st["health"], now_ts)
    for ev in events:
        text = (am.cycle_lag(ev["label"], ev["what"], ev["hours"]) if ev["kind"] == "down"
                else am.recovered(f"{ev['label']} ({ev['what']})"))
        if not deliver(text, flags["notify_alerts"]):
            new_health[ev["key"]] = not new_health[ev["key"]]          # no se pudo avisar: se reintenta en el próximo ciclo
    st["health"] = new_health
    store.put("portfolio_status", "health", {"flags": new_health, "updated": now_ts,
                                             "bar_lag_h": hl.bar_lag_hours(snap["breakout"]["last_bar"], now_ts)})
    store.save_state(st)
    return {"index": decision["index"], "allow_new": gate["allow_new"], "reasons": decision["reasons"],
            "warnings": decision["warnings"], "drift": report["state"], "health_events": len(events),
            "sent": sent, "failed": failed, "sleeves": [s.name for s in sleeves]}
