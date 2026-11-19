"""Semáforo "¿voy bien?": compara el paper trading contra criterios mínimos y contra comprar y mantener."""
import math

TARGETS = {"days": 28, "trades": 100, "profit_factor": 1.3, "sharpe": 1.0, "max_drawdown": -0.15}


def _num(v, cap=99.0):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return float(max(-cap, min(cap, v))) if isinstance(v, (int, float)) else v


def scorecard(res: dict, closed, start_ts, targets: dict = None) -> dict:
    t = {**TARGETS, **(targets or {})}
    m, eq = res["metrics"], res["equity"]
    days = max(0.0, (closed.index[-1] - start_ts).total_seconds() / 86400)
    px = closed.loc[closed.index >= start_ts, "close"]
    bh = float(px.iloc[-1] / px.iloc[0] - 1) if len(px) > 1 else 0.0
    ret, trades = m["total_return"], m["trades"]
    pf = _num(m["profit_factor"])

    def chk(key, label, value, target, ok, wait, fmt, note=""):
        return {"key": key, "label": label, "value": value, "target": target, "text": fmt,
                "state": "wait" if wait else ("ok" if ok else "bad"), "note": note}

    checks = [
        chk("days", "Tiempo en paper", round(days, 1), t["days"], days >= t["days"], days < t["days"],
            f"{days:.1f} de {t['days']} días", "Menos de 4 semanas no demuestra nada."),
        chk("trades", "Operaciones", trades, t["trades"], trades >= t["trades"], trades < t["trades"],
            f"{trades} de {t['trades']}", "Con pocas operaciones la suerte pesa más que la estrategia."),
        chk("profit_factor", "Profit factor", pf, t["profit_factor"], (pf or 0) >= t["profit_factor"], trades < 30,
            f"{pf:.2f} (meta > {t['profit_factor']})" if pf is not None else "—", "Ganancias entre pérdidas, ya con costos."),
        chk("sharpe", "Sharpe", _num(m["sharpe"]), t["sharpe"], m["sharpe"] >= t["sharpe"], days < 14,
            f"{m['sharpe']:.2f} (meta > {t['sharpe']})", "Ganancia ajustada al riesgo."),
        chk("max_drawdown", "Peor caída", _num(m["max_drawdown"]), t["max_drawdown"], m["max_drawdown"] >= t["max_drawdown"], False,
            f"{m['max_drawdown']:.1%} (límite {t['max_drawdown']:.0%})", "Si esta caída te quitaría el sueño, el bot no es para ti."),
        chk("vs_bh", "Contra comprar y mantener", round(ret - bh, 4), 0.0, ret >= bh, days < 14,
            f"bot {ret:+.1%} · BTC {bh:+.1%}", "Si solo comprar BTC rinde igual o más, el bot no aporta."),
    ]
    enough = days >= t["days"] and trades >= t["trades"]
    bad = [c for c in checks if c["state"] == "bad" and c["key"] not in ("days", "trades")]
    if not enough:
        verdict, state = "Muy pronto para juzgar: sigue en paper hasta completar tiempo y operaciones.", "wait"
    elif bad:
        verdict, state = "No cumple: " + ", ".join(c["label"].lower() for c in bad) + ". No pasar a dinero real.", "bad"
    else:
        verdict, state = "Cumple los criterios mínimos. Aún así, empieza con muy poco capital.", "ok"
    return {"verdict": verdict, "state": state, "checks": checks, "ret": _num(ret), "bh_ret": _num(bh), "days": round(days, 1)}
