"""
Pestaña "Paper Trading" del dashboard NEXUS.
Muestra: (1) historial en vivo sin dinero, (2) resultados de la validación fuera de muestra,
(3) calculadora de capital necesario para una meta diaria.
Se importa desde dashboard.py; los helpers de estilo se pasan como argumentos para no duplicar código.
"""
import json
import os
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, "paper_state.json")
REPORTS = os.path.join(BASE, "reports")
PRIMARY = "PRIMARIA  SL2/TP4/H24"
TARGET_TRADES = 100   # trades mínimos para distinguir habilidad de suerte


def _read(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError, OSError):
        return default


def _cls(v):
    return "pos" if v > 0 else "neg" if v < 0 else "neu"


# ---------------------------------------------------------------- resumen de validación
def _validation_banner(res, k):
    if not res:
        st.info("Aún no hay resultados de validación. Ejecuta `python -m research.run_research`.")
        return
    v = res["variants"].get(PRIMARY, {})
    d, h = v.get("DISEÑO", {}).get("ml", {}), v.get("HOLDOUT", {}).get("ml", {})
    if not d or not h:
        return
    st.markdown(
        f'<div class="poscard" style="border-left:3px solid #e0a030;display:block">'
        f'<b>Estado de la validación: NO confirmada.</b><br>'
        f'<span class="f">Diseño (2022 → nov 2025, fuera de muestra): '
        f'<span class="{_cls(d["total_return"])}">{d["total_return"]:+.1%}</span> · '
        f'Sharpe {d["sharpe"]:.2f} · drawdown {d["max_drawdown"]:.1%} · {d["n_trades"]} trades</span><br>'
        f'<span class="f">Último año (tramo final sin tocar): '
        f'<span class="{_cls(h["total_return"])}">{h["total_return"]:+.1%}</span> · '
        f'drawdown {h["max_drawdown"]:.1%} · {h["n_trades"]} trades '
        f'(comprar y mantener: {v["HOLDOUT"]["bh_return"]:+.1%})</span><br>'
        f'<span class="f">Todavía no hay evidencia de rentabilidad sostenida. Usa solo paper trading (sin dinero) '
        f'hasta reunir ~{TARGET_TRADES} trades en vivo.</span></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- paper trading en vivo (auto-actualiza)
@st.fragment(run_every=30)
def _live(kpi, fmt_money, style_fig, win, loss):
    state = _read(STATE_FILE, None)
    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("Procesar velas nuevas ahora", icon=":material/sync:", use_container_width=True):
            try:
                from research import paper
                with st.spinner("Descargando datos y procesando velas de 4h..."):
                    r = paper.run_once()
                st.toast(f"Velas nuevas: {r['velas']} · cerradas: {r['cerradas'][1]}", icon="✅")
                state = r["state"]
            except Exception as e:  # red, modelo ausente, etc.
                st.error(f"No se pudo actualizar: {e}")
    with c2:
        st.caption("Se actualiza solo cada 30 s leyendo `paper_state.json`. Las velas nuevas se procesan al ejecutar "
                   "`python paper_trader.py run` (o programándolo) o con el botón.")

    if not state:
        st.info("Aún no hay historial de paper trading. En la terminal ejecuta: "
                "`python paper_trader.py train` y luego `python paper_trader.py run`.")
        return

    closed = pd.DataFrame(state.get("closed", []))
    n = len(closed)
    cap0, eq = float(state["capital_initial"]), float(state["equity"])
    ret = eq / cap0 - 1
    wr = float((closed["net_ret"] > 0).mean()) if n else 0.0
    gp = float(closed.loc[closed["pnl"] > 0, "pnl"].sum()) if n else 0.0
    gl = abs(float(closed.loc[closed["pnl"] <= 0, "pnl"].sum())) if n else 0.0
    pf = (gp / gl) if gl else None
    dd = float((closed["equity_after"] / closed["equity_after"].cummax() - 1).min()) if n else 0.0
    st.markdown('<div class="kpis">' +
                kpi("Equity simulado", f"${eq:,.2f}", f"inicial ${cap0:,.2f}", icon="wallet") +
                kpi("Retorno", f"{ret:+.2%}", fmt_money(eq - cap0), _cls(ret), "trend") +
                kpi("Trades cerrados", f"{n}", f"meta de validación: {TARGET_TRADES}", icon="target") +
                kpi("Win rate", f"{wr:.0%}" if n else "—", "sobre trades cerrados", icon="pulse") +
                kpi("Profit factor", f"{pf:.2f}" if pf else "—", "ganancia bruta / pérdida bruta", icon="scale") +
                kpi("Max DD realizado", f"{dd:.1%}" if n else "—", "sobre trades cerrados", "neg" if dd < 0 else "neu") +
                "</div>", unsafe_allow_html=True)
    st.progress(min(n / TARGET_TRADES, 1.0), text=f"Progreso hacia {TARGET_TRADES} trades en vivo: {n}/{TARGET_TRADES}"
                + ("  ·  con menos trades no se distingue suerte de habilidad" if n < TARGET_TRADES else ""))
    st.caption(f"Última vela de 4h procesada: {str(state.get('last_ts', '—'))[:16]} UTC")

    st.markdown('<div class="sec">Posiciones abiertas (simuladas)</div>', unsafe_allow_html=True)
    pos = state.get("positions", {})
    if pos:
        for sym, p in pos.items():
            st.markdown(
                f'<div class="poscard open"><b>{sym}</b>'
                f'<div class="f">Entrada <span>${p["entry"]:,.4f}</span></div>'
                f'<div class="f">Stop <span>${p["stop"]:,.4f}</span></div>'
                f'<div class="f">Objetivo <span>${p["target"]:,.4f}</span></div>'
                f'<div class="f">Tamaño <span>${p["size"]:,.2f}</span></div>'
                f'<div class="f">Prob. ML <span>{p["p"]:.0%}</span></div>'
                f'<div class="f">Desde <span>{str(p["entry_ts"])[:16]}</span></div></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="poscard"><span style="color:var(--mut)">Sin posiciones abiertas. '
                    'Espera una ruptura de máximos confirmada por el modelo.</span></div>', unsafe_allow_html=True)

    if n:
        g1, g2 = st.columns([3, 2])
        with g1:
            st.markdown('<div class="sec">Equity simulado</div>', unsafe_allow_html=True)
            xs = [pd.to_datetime(closed["entry_time"].iloc[0])] + list(pd.to_datetime(closed["exit_time"]))
            ys = [cap0] + closed["equity_after"].tolist()
            col = win if eq >= cap0 else loss
            fig = go.Figure(go.Scatter(x=xs, y=ys, mode="lines+markers", line=dict(color=col, width=1.8, shape="hv"),
                                       marker=dict(size=5)))
            fig.add_hline(y=cap0, line_dash="dot", line_color="rgba(255,255,255,.3)")
            st.plotly_chart(style_fig(fig), use_container_width=True, key="paper_eq")
        with g2:
            st.markdown('<div class="sec">Resultado por trade</div>', unsafe_allow_html=True)
            fig = go.Figure(go.Bar(y=closed["net_ret"] * 100, marker_color=[win if x > 0 else loss for x in closed["net_ret"]]))
            fig.update_yaxes(ticksuffix="%")
            st.plotly_chart(style_fig(fig), use_container_width=True, key="paper_pnl")
        st.markdown('<div class="sec">Trades cerrados</div>', unsafe_allow_html=True)
        view = closed[["symbol", "entry_time", "exit_time", "reason", "entry", "exit", "size", "net_ret", "pnl"]].iloc[::-1]
        st.dataframe(view, use_container_width=True, hide_index=True, column_config={
            "symbol": "Par", "entry_time": "Entrada", "exit_time": "Salida", "reason": "Motivo",
            "entry": st.column_config.NumberColumn("Precio ent.", format="%.4f"),
            "exit": st.column_config.NumberColumn("Precio sal.", format="%.4f"),
            "size": st.column_config.NumberColumn("Tamaño $", format="$%.2f"),
            "net_ret": st.column_config.NumberColumn("Var. neta", format="percent"),
            "pnl": st.column_config.NumberColumn("P&L $", format="$%.3f")})
    log = state.get("log", [])
    if log:
        with st.expander(f"Avisos ({len(log)})"):
            st.text("\n".join(log[-20:]))


# ---------------------------------------------------------------- validación
def _validation(res, style_fig):
    st.markdown('<div class="sec">Resultados de la validación (fuera de muestra, con comisiones)</div>', unsafe_allow_html=True)
    if not res:
        st.info("Sin resultados. Ejecuta `python -m research.run_research` y `python -m research.report`.")
        return
    rows = []
    for name, v in res["variants"].items():
        for seg in ("DISEÑO", "HOLDOUT"):
            m = v.get(seg, {}).get("ml", {})
            if m.get("n_trades"):
                rows.append({"Variante": name.replace("PRIMARIA  ", "★ "), "Segmento": "Diseño 2022–nov 2025" if seg == "DISEÑO" else "Último año (sin tocar)",
                             "Trades": m["n_trades"], "Retorno": m["total_return"], "Max DD": m["max_drawdown"],
                             "Sharpe": m["sharpe"], "Win rate": m["win_rate"], "Prof. factor": m["profit_factor"],
                             "Comprar y mantener": v[seg]["bh_return"]})
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, column_config={
        "Retorno": st.column_config.NumberColumn(format="percent"), "Max DD": st.column_config.NumberColumn(format="percent"),
        "Win rate": st.column_config.NumberColumn(format="percent"), "Comprar y mantener": st.column_config.NumberColumn(format="percent"),
        "Sharpe": st.column_config.NumberColumn(format="%.2f"), "Prof. factor": st.column_config.NumberColumn(format="%.2f")})
    st.caption("★ = estrategia candidata declarada antes de mirar el último año. Las 3 variantes ganan en el diseño y pierden en el último año.")
    img = os.path.join(REPORTS, "equity_primaria.png")
    if os.path.exists(img):
        st.image(img, use_container_width=True)
    rep = os.path.join(REPORTS, "INFORME_VALIDACION.md")
    if os.path.exists(rep):
        with st.expander("Informe completo de validación"):
            st.markdown(open(rep, encoding="utf-8").read())


# ---------------------------------------------------------------- calculadora
def _calculator():
    st.markdown('<div class="sec">Calculadora: ¿cuánto capital necesito para mi meta diaria?</div>', unsafe_allow_html=True)
    a, b, c = st.columns(3)
    capital = a.number_input("Capital actual (USDT)", 1.0, 1e9, 25.0, 5.0, key="calc_cap")
    goal = b.number_input("Meta diaria (USDT)", 0.1, 1e6, 1.0, 0.5, key="calc_goal")
    ann = c.slider("Rendimiento anual supuesto", 0.01, 0.50, 0.165, 0.005, format="%.3f", key="calc_ann")
    per_day = capital * ann / 365
    needed = goal * 365 / ann
    k1, k2, k3 = st.columns(3)
    k1.metric("Ganancia diaria con tu capital", f"${per_day:,.3f}")
    k2.metric(f"Capital para ganar ${goal:,.2f}/día", f"${needed:,.0f}")
    k3.metric("Días para ganar $1 con tu capital", f"{(1 / per_day):,.0f}" if per_day > 0 else "—")
    st.caption("16.5 % anual fue el resultado del periodo de diseño (2022–nov 2025). El último año dio −9.5 %, "
               "así que el rendimiento real futuro es incierto y podría ser menor o negativo. Es un supuesto, no una promesa.")


def render(kpi, fmt_money, style_fig, win, loss):
    res = _read(os.path.join(REPORTS, "resultados.json"), None)
    _validation_banner(res, kpi)
    st.markdown('<div class="sec">Paper trading en vivo (sin dinero, precios reales de Binance)</div>', unsafe_allow_html=True)
    _live(kpi, fmt_money, style_fig, win, loss)
    _validation(res, style_fig)
    _calculator()
