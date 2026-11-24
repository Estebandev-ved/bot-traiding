"""Textos de las alertas (HTML de Telegram, en español). Todo dato dinámico se escapa con html.escape."""
from __future__ import annotations

import html

NOTIFY_FLAGS = {          # interruptores que se prenden/apagan desde el panel (colección strategies/{id})
    "notify_open": "Avisar al abrir una posición",
    "notify_close": "Avisar al cerrar una operación",
    "notify_daily": "Resumen diario",
    "notify_news": "Noticias de riesgo",
    "notify_alerts": "Alertas del sistema (kill switch, pausa, bot detenido)",
}
DEFAULT_FLAGS = {k: True for k in NOTIFY_FLAGS}
PAPER = "<i>Paper trading: simulación, sin dinero real.</i>"
REASONS = {"SL": "stop loss", "TP": "objetivo", "TIME": "cierre por tiempo", "SL_GAP": "stop (el precio saltó)",
           "stop": "stop", "signal": "señal contraria", "end": "fin"}


def e(x) -> str:
    return html.escape(str(x), quote=False)


def num(x, dec: int = 2) -> str:
    return f"{float(x):,.{dec}f}"


def pct(x) -> str:
    return f"{float(x) * 100:+.2f}%"


def usd(x) -> str:
    x = float(x)
    return f"{'+' if x > 0 else '-' if x < 0 else ''}${abs(x):,.2f}"


# ------------------------------------------------------------------ Breakout 4h
def breakout_open(sym: str, p: dict) -> str:
    return (f"🟢 <b>Breakout 4h · posición abierta</b>\n<b>{e(sym)}</b> a {num(p['entry'], 4)}\n"
            f"Stop {num(p['stop'], 4)} · Objetivo {num(p['target'], 4)}\n"
            f"Tamaño ${num(p['size'])} · Prob. del modelo {float(p['p']) * 100:.0f}%\n{PAPER}")


def breakout_close(t: dict, state: dict) -> str:
    win = float(t["net_ret"]) > 0
    n = len(state.get("closed", []))
    return (f"{'✅' if win else '🔴'} <b>Breakout 4h · {'ganancia' if win else 'pérdida'}</b>\n"
            f"<b>{e(t['symbol'])}</b>: {pct(t['net_ret'])} ({usd(t['pnl'])}) · {e(REASONS.get(t['reason'], t['reason']))}\n"
            f"Equity ${num(state['equity'])} · trades cerrados {n}/100\n{PAPER}")


def breakout_daily(state: dict) -> str:
    cap0, eq = float(state["capital_initial"]), float(state["equity"])
    closed = state.get("closed", [])
    wins = sum(1 for c in closed if float(c["net_ret"]) > 0)
    pos = ", ".join(state.get("positions", {})) or "ninguna"
    wr = f"{wins / len(closed) * 100:.0f}%" if closed else "—"
    why = (state.get("why") or {}).get("text")
    why_line = f"\n💡 <b>Por qué {'está quieto' if not state.get('positions') else 'opera'}:</b> {e(why)}" if why else ""
    a = state.get("activity") or {}
    act_line = (f"\nSeñales vistas {a.get('signals', 0)} · bloqueadas por régimen {a.get('blocked_regime', 0)} · "
                f"descartadas por el modelo {a.get('rejected_model', 0)} · abiertas {a.get('opened', 0)}") if a.get("signals") else \
        ("\nSeñales de ruptura vistas: 0" if why else "")
    return (f"📊 <b>Breakout 4h · resumen diario</b>\nEquity ${num(eq)} ({pct(eq / cap0 - 1)} desde ${num(cap0)})\n"
            f"Trades cerrados {len(closed)}/100 · acierto {wr}\nPosiciones abiertas: {e(pos)}{why_line}{act_line}\n{PAPER}")


# ------------------------------------------------------------------ Richy
def richy_open(symbol: str, op: dict) -> str:
    side = "LONG" if op["side"] > 0 else "SHORT"
    return (f"🟢 <b>Richy · {side} abierta</b>\n<b>{e(symbol)}</b> a {num(op['entry'])} · cantidad {float(op['qty']):.5f}\n"
            f"Stop {num(op['stop'])}\n{PAPER}")


def richy_close(symbol: str, t: dict, equity: float) -> str:
    win = float(t["pnl"]) > 0
    side = "LONG" if t["side"] > 0 else "SHORT"
    return (f"{'✅' if win else '🔴'} <b>Richy · {'ganancia' if win else 'pérdida'}</b>\n"
            f"<b>{e(symbol)}</b> {side}: {usd(t['pnl'])} · {e(REASONS.get(t['reason'], t['reason']))}\n"
            f"Capital simulado ${num(equity)}\n{PAPER}")


def richy_kill(reason: str) -> str:
    return f"🛑 <b>Richy · KILL SWITCH</b>\nEl bot se detuvo: {e(reason)}\nRevisa el panel antes de reactivarlo."


def richy_pause(reasons: list, fng) -> str:
    why = "\n".join(f"• {e(r)}" for r in reasons) or "• señales de riesgo"
    return f"⏸️ <b>Richy · pausa por noticias</b>\n{why}\nFear &amp; Greed: {e(fng if fng is not None else '—')}\nNo abrirá posiciones hasta que pase."


# ------------------------------------------------------------------ noticias y sistema
def news_risk(n: dict) -> str:
    src = f" ({e(n['source'])})" if n.get("source") else ""
    link = f"\n<a href=\"{e(n['link'])}\">Leer</a>" if str(n.get("link", "")).startswith("https://") else ""
    return f"🚨 <b>Noticia de riesgo</b>{src}\n{e(n['title'])}{link}"


def stalled(name: str, hours: float, url: str | None = None) -> str:
    extra = f"\n{e(url)}" if url else ""
    return (f"⚠️ <b>{e(name)} sin actividad</b>\nLleva {hours:.1f} h sin escribir en Firestore (debería hacerlo cada 4 h). "
            f"Revisa GitHub → Actions.{extra}")


def recovered(name: str) -> str:
    return f"✅ <b>{e(name)}</b> volvió a la normalidad."


# ------------------------------------------------------------------ portafolio, deriva y salud de ciclos
def portfolio_halt(reasons: list, index: float) -> str:
    why = "\n".join(f"• {e(r)}" for r in reasons) or "• límite de riesgo combinado"
    return (f"🛡️ <b>Portafolio · entradas nuevas en pausa</b>\n{why}\nÍndice combinado {float(index):.3f} (1.000 = inicio).\n"
            f"Richy y Breakout 4h no abrirán posiciones nuevas; las abiertas siguen con sus stops.")


def portfolio_resume(index: float) -> str:
    return f"✅ <b>Portafolio</b> reanudado: los bots pueden abrir posiciones otra vez (índice {float(index):.3f})."


def portfolio_warn(warnings: list) -> str:
    return "⚠️ <b>Portafolio · aviso</b>\n" + "\n".join(f"• {e(w)}" for w in warnings)


def drift_alert(bot: str, d: dict) -> str:
    why = "\n".join(f"• {e(a)}" for a in d.get("alerts", [])) or "• desviación del backtest"
    return (f"📉 <b>{e(bot)} · deriva frente al backtest</b>\n{why}\nTrades en vivo: {d.get('n', 0)}. "
            f"No es una prueba, pero es la señal de revisar antes de confiar en el bot.\n{PAPER}")


def cycle_lag(label: str, what: str, hours: float) -> str:
    if what == "velas":
        return (f"⏱️ <b>{e(label)} · velas atrasadas</b>\nSu última vela 4h procesada va {hours:.1f} h por detrás. "
                f"Los ciclos escriben pero no avanzan (¿datos pegados?). Revisa GitHub → Actions.")
    return (f"⏱️ <b>{e(label)} · ciclos saltados</b>\nLleva {hours:.1f} h sin escribir (GitHub se saltó ejecuciones). "
            f"Si sigue así revisa GitHub → Actions.")
