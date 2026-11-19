"""
NEXUS Terminal — Dashboard para el bot de trading.
Ejecutar:  streamlit run dashboard.py
Características: auto-actualización en vivo, alertas sonoras (ganancia / pérdida /
posición abierta), módulo de configuración que el bot relee en cada ciclo.
"""
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from settings_store import DEFAULTS, load_settings, save_settings  # noqa: E402

try:
    from metrics import PerformanceMetrics
    MODULES_AVAILABLE = True
except Exception:
    MODULES_AVAILABLE = False

BASE = os.path.dirname(os.path.abspath(__file__))
TRADES_FILES = [os.path.join(BASE, 'logs', 'trades_history.json'),
                os.path.join(BASE, 'trades_history.json')]
STATE_FILE = os.path.join(BASE, 'positions_state.json')

THEMES = {  # acento, acento suave
    'Azul': ('#4c8dff', '#2a4a8a'),
    'Teal': ('#2bb5a0', '#1b6b5f'),
    'Ámbar': ('#e0a030', '#7a5a1c'),
    'Grafito': ('#9aa7b8', '#4a5463'),
}
WIN, LOSS = '#26a69a', '#ef5350'   # verde/rojo de velas, sobrios

st.set_page_config(page_title="NEXUS Terminal", page_icon=":material/candlestick_chart:", layout="wide",
                   initial_sidebar_state="collapsed")

if 'cfg' not in st.session_state:
    st.session_state.cfg = load_settings()
cfg = st.session_state.cfg
C1, C2 = THEMES.get(cfg['theme'], THEMES['Azul'])


# ---------------------------------------------------------------- estilos
def inject_css():
    st.markdown(f"""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {{ --ac:{C1}; --ac2:{C2}; --win:{WIN}; --loss:{LOSS}; --bg:#0b0e13; --panel:#11151c; --line:#1f2733; --mut:#7d8a9c; --txt:#d5dbe5; }}
html, body, [class*="css"], .stApp {{ font-family:'Inter',sans-serif; color:var(--txt); }}
.stApp {{ background:var(--bg); }}
header[data-testid="stHeader"] {{ background:transparent; }}
.block-container {{ padding-top:1rem; max-width:1500px; }}
svg.i {{ width:15px; height:15px; stroke:currentColor; fill:none; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; vertical-align:-3px; }}
.brand {{ display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap:wrap;
  padding:12px 18px; background:var(--panel); border:1px solid var(--line); border-radius:6px; border-left:3px solid var(--ac); }}
.brand .logo {{ display:flex; align-items:center; gap:12px; }}
.brand .logo svg {{ width:26px; height:26px; color:var(--ac); }}
.brand h1 {{ margin:0; padding:0; font-size:1.05rem; font-weight:600; letter-spacing:.04em; color:#fff; }}
.brand small {{ color:var(--mut); font-size:.74rem; letter-spacing:.06em; }}
.chips {{ display:flex; gap:8px; flex-wrap:wrap; }}
.chip {{ font-size:.72rem; font-weight:500; padding:5px 10px; border:1px solid var(--line); border-radius:4px; color:var(--mut); display:inline-flex; gap:7px; align-items:center; background:#0d1117; }}
.chip .d {{ width:7px; height:7px; border-radius:50%; background:currentColor; }}
.chip.on {{ color:var(--win); }} .chip.off {{ color:#e0a030; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:10px; margin:14px 0; }}
.kpi {{ padding:13px 15px; background:var(--panel); border:1px solid var(--line); border-radius:6px; }}
.kpi .l {{ font-size:.68rem; letter-spacing:.09em; color:var(--mut); text-transform:uppercase; font-weight:500; display:flex; gap:6px; align-items:center; }}
.kpi .v {{ font-family:'JetBrains Mono',monospace; font-size:1.45rem; font-weight:500; margin-top:7px; color:#fff; }}
.kpi .s {{ font-size:.76rem; color:var(--mut); margin-top:3px; }}
.pos {{ color:var(--win)!important; }} .neg {{ color:var(--loss)!important; }} .neu {{ color:#fff; }}
.sec {{ font-size:.72rem; font-weight:600; letter-spacing:.1em; color:var(--mut); margin:18px 0 8px; text-transform:uppercase; display:flex; align-items:center; gap:8px; }}
.sec::after {{ content:""; flex:1; height:1px; background:var(--line); }}
.poscard {{ padding:12px 16px; background:var(--panel); border:1px solid var(--line); border-radius:6px; font-size:.88rem; display:flex; gap:18px; flex-wrap:wrap; align-items:center; }}
.poscard.open {{ border-left:3px solid var(--ac); }}
.poscard b {{ color:#fff; font-weight:600; }}
.poscard .f {{ color:var(--mut); }} .poscard .f span {{ color:var(--txt); font-family:'JetBrains Mono',monospace; }}
table.tl {{ width:100%; border-collapse:collapse; font-size:.82rem; background:var(--panel); border:1px solid var(--line); }}
table.tl th {{ text-align:left; color:var(--mut); font-weight:500; font-size:.68rem; letter-spacing:.08em; text-transform:uppercase; padding:8px 12px; border-bottom:1px solid var(--line); }}
table.tl td {{ padding:7px 12px; border-bottom:1px solid #161c26; font-family:'JetBrains Mono',monospace; }}
.stTabs [data-baseweb="tab-list"] {{ gap:2px; border-bottom:1px solid var(--line); }}
.stTabs [data-baseweb="tab"] {{ font-size:.82rem; font-weight:500; padding:9px 16px; background:transparent; color:var(--mut); }}
.stTabs [aria-selected="true"] {{ color:#fff!important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background:var(--ac)!important; height:2px; }}
div[data-testid="stForm"] {{ border:1px solid var(--line); background:var(--panel); border-radius:6px; }}
.stButton>button, .stFormSubmitButton>button {{ font-size:.8rem; font-weight:500; border:1px solid var(--line); color:var(--txt);
  background:#151b25; border-radius:4px; transition:border-color .15s, background .15s; }}
.stButton>button:hover, .stFormSubmitButton>button:hover {{ border-color:var(--ac); color:#fff; background:#1a2230; }}
[data-testid="stDataFrame"] {{ border:1px solid var(--line); border-radius:6px; overflow:hidden; }}
</style>""", unsafe_allow_html=True)


ICONS = {
    'logo': '<path d="M6 3v3M6 15v4M12 2v4M12 16v5M18 5v3M18 16v3"/><rect x="4" y="6" width="4" height="9" rx=".5"/><rect x="10" y="6" width="4" height="10" rx=".5"/><rect x="16" y="8" width="4" height="8" rx=".5"/>',
    'wallet': '<path d="M3 7h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7zM3 7l12-3v3M16 14h2"/>',
    'trend': '<path d="M3 17l6-6 4 4 8-8M15 7h6v6"/>',
    'calendar': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    'target': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/>',
    'scale': '<path d="M12 3v18M5 7h14M5 7l-3 8a3 3 0 0 0 6 0L5 7zM19 7l-3 8a3 3 0 0 0 6 0l-3-8z"/>',
    'pulse': '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    'open': '<path d="M5 12h14M13 6l6 6-6 6"/>',
    'idle': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    'refresh': '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>',
}


def ico(name, cls='i', size=None):
    return f'<svg class="{cls}" viewBox="0 0 24 24">{ICONS[name]}</svg>'


# ---------------------------------------------------------------- datos
def read_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, ValueError, OSError):
        return default


def load_trades():
    for p in TRADES_FILES:
        data = read_json(p, None)
        if data is not None:
            return data
    return []


def demo_trades(n=40):
    rnd = random.Random(7)
    out, t = [], datetime.now() - timedelta(hours=n * 3)
    price = 62000
    for i in range(n):
        entry = price * (1 + rnd.uniform(-.02, .02))
        pct = rnd.gauss(0.6, 2.2)
        exit_ = entry * (1 + pct / 100)
        qty = 0.01
        out.append({'id': i + 1, 'timestamp': (t + timedelta(hours=i * 3)).isoformat(),
                    'entry_price': entry, 'exit_price': exit_, 'quantity': qty,
                    'profit': (exit_ - entry) * qty * 10, 'profit_pct': pct,
                    'exit_reason': rnd.choice(['TAKE_PROFIT', 'STOP_LOSS', 'TRAILING_STOP'])})
        price = exit_
    return out


@st.cache_data(ttl=4, show_spinner=False)
def live_price(symbol):
    try:
        import requests
        r = requests.get('https://api.binance.com/api/v3/ticker/24hr',
                         params={'symbol': symbol}, timeout=3).json()
        return float(r['lastPrice']), float(r['priceChangePercent'])
    except Exception:
        return None, None


def trades_df(trades):
    df = pd.DataFrame(trades)
    if df.empty:
        return df
    for col in ('profit', 'profit_pct', 'entry_price', 'exit_price'):
        if col not in df:
            df[col] = 0.0
    df['ts'] = pd.to_datetime(df.get('timestamp'), errors='coerce')
    return df


# ---------------------------------------------------------------- sonido
SOUND_JS = """
<script>
const ctx = new (window.AudioContext || window.webkitAudioContext)();
const vol = %(vol)s;
function tone(f, t0, d, type='sine', g=1){
  const o=ctx.createOscillator(), a=ctx.createGain();
  o.type=type; o.frequency.value=f; o.connect(a); a.connect(ctx.destination);
  const t=ctx.currentTime+t0;
  a.gain.setValueAtTime(0,t); a.gain.linearRampToValueAtTime(vol*g*.4,t+.02);
  a.gain.exponentialRampToValueAtTime(.0001,t+d); o.start(t); o.stop(t+d+.05);
}
const S = {
  'Campana': ()=>{tone(988,0,.9);tone(1319,.12,1.1);tone(1760,.26,1.3,'sine',.8)},
  'Moneda':  ()=>{tone(1318,0,.12,'square',.5);tone(1760,.1,.5,'square',.5)},
  'Arpegio': ()=>{[523,659,784,1047,1319].forEach((f,i)=>tone(f,i*.09,.5,'triangle'))},
  'Grave':   ()=>{tone(196,0,.5,'sawtooth',.7);tone(147,.25,.8,'sawtooth',.7)},
  'Alerta':  ()=>{for(let i=0;i<3;i++){tone(880,i*.22,.15,'square',.6)}},
  'Apertura':()=>{tone(660,0,.15,'triangle');tone(880,.12,.3,'triangle')},
  'Silencio':()=>{}
};
ctx.resume().finally(()=>{(S['%(name)s']||S['Campana'])();});
</script>"""


def play(name, key):
    """Renderiza un iframe que reproduce el sonido (key distinta = reproduce de nuevo)."""
    components.html(f"<!-- {key} -->" + SOUND_JS % {'vol': cfg['sound_volume'], 'name': name}, height=0)


def check_alerts(trades, position):
    """Detecta trades nuevos / posición nueva y devuelve (sonido, mensajes)."""
    ss = st.session_state
    sound, msgs = None, []
    ids = [t.get('id', i) for i, t in enumerate(trades)]
    last_id = ids[-1] if ids else 0
    pos_key = (position or {}).get('entry_time')
    if 'seen_id' not in ss:               # primera carga: no suena
        ss.seen_id, ss.seen_pos = last_id, pos_key
        return None, msgs
    if last_id != ss.seen_id and trades:
        new = [t for t in trades if t.get('id', 0) > ss.seen_id] or [trades[-1]]
        for t in new:
            p = t.get('profit', 0)
            if abs(p) < cfg['notify_min_profit']:
                continue
            if p >= 0:
                sound = cfg['sound_win']; msgs.append((':material/trending_up:', f"Ganancia +${p:,.2f}"))
            else:
                sound = cfg['sound_loss']; msgs.append((':material/trending_down:', f"Pérdida -${abs(p):,.2f}"))
        ss.seen_id = last_id
    if pos_key and pos_key != ss.seen_pos and cfg['sound_on_open']:
        sound = sound or 'Apertura'; msgs.append((':material/bolt:', 'Nueva posición abierta'))
    ss.seen_pos = pos_key
    # límites diarios
    today = [t for t in trades if str(t.get('timestamp', ''))[:10] == datetime.now().strftime('%Y-%m-%d')]
    day = sum(t.get('profit', 0) for t in today)
    if cfg['daily_loss_limit'] > 0 and day <= -cfg['daily_loss_limit'] and not ss.get('warned_loss'):
        ss.warned_loss = True; sound = 'Alerta'; msgs.append((':material/block:', f"Límite de pérdida diaria ({day:,.2f})"))
    if cfg['daily_profit_target'] > 0 and day >= cfg['daily_profit_target'] and not ss.get('warned_win'):
        ss.warned_win = True; sound = cfg['sound_win']; msgs.append((':material/flag:', f"Meta diaria alcanzada (+{day:,.2f})"))
    return sound, msgs


# ---------------------------------------------------------------- componentes
def fmt_money(v, sign=True):
    return f"{'+' if sign and v > 0 else '-' if v < 0 else ''}${abs(v):,.2f}"


def kpi(label, value, sub='', cls='neu', icon=None):
    return f'<div class="kpi"><div class="l">{ico(icon) if icon else ""}{label}</div><div class="v {cls}">{value}</div><div class="s">{sub}</div></div>'


def style_fig(fig, h=320):
    fig.update_layout(template='plotly_dark', height=h, margin=dict(l=10, r=10, t=10, b=10),
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False,
                      font=dict(family='Inter', color='#9fb0e6'), hovermode='x unified')
    fig.update_xaxes(gridcolor='rgba(255,255,255,.05)', zeroline=False)
    fig.update_yaxes(gridcolor='rgba(255,255,255,.05)', zeroline=False)
    return fig


def header(trades_n):
    on = cfg['bot_enabled']
    st.markdown(f"""
<div class="brand"><div class="logo"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">{ICONS['logo']}</svg><div><h1>NEXUS Terminal</h1><small>{cfg['SYMBOL']} &nbsp;·&nbsp; {cfg['INTERVAL']} &nbsp;·&nbsp; Motor algorítmico</small></div></div>
<div class="chips">
<span class="chip {'on' if on else 'off'}"><span class="d"></span>{'Bot activo' if on else 'Bot en pausa'}</span>
<span class="chip">{ico('refresh')}Actualiza cada {cfg['refresh_seconds']} s</span>
</div></div>""", unsafe_allow_html=True)


# ---------------------------------------------------------------- PANEL (se auto-actualiza)
@st.fragment(run_every=cfg['refresh_seconds'])
def live_panel():
    demo = st.session_state.get('demo', False)
    trades = demo_trades() if demo else load_trades()
    state = read_json(STATE_FILE, {'position': None})
    position = state.get('position')
    df = trades_df(trades)

    sound, msgs = check_alerts(trades, position)
    for icon, m in msgs[-3:]:
        st.toast(m, icon=icon)
    if sound and cfg['sound_enabled'] and sound != 'Silencio':
        play(sound, time.time())

    total = float(df['profit'].sum()) if not df.empty else 0.0
    n = len(df)
    wins = int((df['profit'] > 0).sum()) if n else 0
    wr = wins / n * 100 if n else 0
    gp = float(df.loc[df['profit'] > 0, 'profit'].sum()) if n else 0
    gl = abs(float(df.loc[df['profit'] < 0, 'profit'].sum())) if n else 0
    pf = gp / gl if gl else (float('inf') if gp else 0)
    balance = cfg['initial_balance'] + total
    today_str = datetime.now().strftime('%Y-%m-%d')
    day = float(df.loc[df['ts'].dt.strftime('%Y-%m-%d') == today_str, 'profit'].sum()) if n else 0.0
    price, chg = live_price(cfg['SYMBOL'])

    cls = lambda v: 'pos' if v > 0 else 'neg' if v < 0 else 'neu'
    price_html = kpi(f"{cfg['SYMBOL']} EN VIVO", f"${price:,.2f}" if price else "—",
                     f"{chg:+.2f}% 24h" if chg is not None else "sin conexión", cls(chg or 0), 'pulse')
    st.markdown('<div class="kpis">' +
                kpi('Balance', f"${balance:,.2f}", f"inicial ${cfg['initial_balance']:,.0f}", icon='wallet') +
                kpi('P&L total', fmt_money(total), f"{total / cfg['initial_balance'] * 100:+.2f}% ROI", cls(total), 'trend') +
                kpi('P&L hoy', fmt_money(day), datetime.now().strftime('%d/%m/%Y'), cls(day), 'calendar') +
                kpi('Win rate', f"{wr:.1f}%", f"{wins}G / {n - wins}P · {n} operaciones", icon='target') +
                kpi('Profit factor', '∞' if pf == float('inf') else f"{pf:.2f}", 'ganancia bruta / pérdida bruta', icon='scale') +
                price_html + '</div>', unsafe_allow_html=True)

    if position:
        ep = position.get('entry_price', 0)
        unreal = ((price - ep) * position.get('quantity', 0)) if price else None
        fl = (f'<div class="f">P&L flotante <span class="{cls(unreal)}">{fmt_money(unreal)}</span></div>' if unreal is not None else '')
        st.markdown(f"""<div class="poscard open">{ico('open')}<b>Posición abierta</b>
<div class="f">Cantidad <span>{position.get('quantity',0):.6f} {position.get('symbol','')}</span></div>
<div class="f">Entrada <span>${ep:,.2f}</span></div>
<div class="f">Stop loss <span>${position.get('stop_loss',0):,.2f}</span></div>
<div class="f">Take profit <span>${position.get('take_profit',0):,.2f}</span></div>{fl}</div>""", unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="poscard">{ico("idle")}<span style="color:var(--mut)">Sin posición abierta. Analizando el mercado.</span></div>', unsafe_allow_html=True)

    gl_, gr_ = st.columns([3, 2])
    with gl_:
        st.markdown('<div class="sec">Equity curve</div>', unsafe_allow_html=True)
        if n:
            eq = (df['profit'].cumsum() + cfg['initial_balance']).tolist()
            xs = df['ts'] if df['ts'].notna().all() else list(range(n))
            col = WIN if total >= 0 else LOSS
            fig = go.Figure(go.Scatter(x=xs, y=eq, mode='lines', line=dict(color=col, width=1.8),
                                       fill='tozeroy', fillcolor='rgba(0,255,157,.08)' if total >= 0 else 'rgba(255,61,110,.08)'))
            fig.add_hline(y=cfg['initial_balance'], line_dash='dot', line_color='rgba(255,255,255,.3)')
            fig.update_yaxes(range=[min(eq + [cfg['initial_balance']]) * .995, max(eq + [cfg['initial_balance']]) * 1.005])
            st.plotly_chart(style_fig(fig), use_container_width=True, key='eq')
        else:
            st.info("Aún no hay operaciones. Activa el modo demo en Configuración para previsualizar.")
    with gr_:
        st.markdown('<div class="sec">P&L por operación</div>', unsafe_allow_html=True)
        if n:
            last = df.tail(30)
            fig = go.Figure(go.Bar(y=last['profit'], marker_color=[WIN if p > 0 else LOSS for p in last['profit']]))
            st.plotly_chart(style_fig(fig), use_container_width=True, key='pnl')

    if n:
        st.markdown('<div class="sec">Últimas operaciones</div>', unsafe_allow_html=True)
        rows = ''.join(
            f"<tr><td>#{r.get('id', i)}</td><td>{str(r.get('timestamp', ''))[:16].replace('T', ' ')}</td>"
            f"<td>${r['entry_price']:,.2f}</td><td>${r['exit_price']:,.2f}</td>"
            f"<td class='{cls(r['profit'])}'>{r['profit_pct']:+.2f}%</td><td class='{cls(r['profit'])}'>{fmt_money(r['profit'])}</td></tr>"
            for i, r in df.tail(6).iloc[::-1].iterrows())
        st.markdown('<table class="tl"><tr><th>ID</th><th>Fecha</th><th>Entrada</th><th>Salida</th><th>Var.</th><th>P&L</th></tr>' + rows + '</table>', unsafe_allow_html=True)
    st.caption(f"Actualizado {datetime.now().strftime('%H:%M:%S')}")


@st.fragment(run_every=max(cfg['refresh_seconds'] * 3, 10))
def history_tab():
    demo = st.session_state.get('demo', False)
    trades = demo_trades() if demo else load_trades()
    df = trades_df(trades)
    if df.empty:
        st.info("Sin operaciones registradas.")
        return
    st.markdown('<div class="sec">Métricas avanzadas</div>', unsafe_allow_html=True)
    m = {}
    if MODULES_AVAILABLE:
        try:
            pm = PerformanceMetrics(); pm.load_trades(trades); m = pm.get_all_metrics()
        except Exception:
            m = {}
    # drawdown local como respaldo
    eq = df['profit'].cumsum() + cfg['initial_balance']
    dd = float(((eq - eq.cummax()) / eq.cummax()).min() * 100)
    st.markdown('<div class="kpis">' +
                kpi('Sharpe', f"{m.get('sharpe_ratio', 0):.2f}" if m else 'N/A') +
                kpi('Sortino', f"{m.get('sortino_ratio', 0):.2f}" if m else 'N/A') +
                kpi('Max drawdown', f"{m.get('max_drawdown_pct', dd):.2f}%", cls='neg') +
                kpi('Mejor trade', fmt_money(df['profit'].max()), cls='pos') +
                kpi('Peor trade', fmt_money(df['profit'].min()), cls='neg') + '</div>', unsafe_allow_html=True)
    st.markdown('<div class="sec">Historial de operaciones</div>', unsafe_allow_html=True)
    view = df.drop(columns=['ts']).tail(int(cfg['max_trades_shown'])).iloc[::-1]
    st.dataframe(view, use_container_width=True, hide_index=True,
                 column_config={'profit': st.column_config.NumberColumn('P&L', format="$%.2f"),
                                'profit_pct': st.column_config.NumberColumn('P&L %', format="%.2f%%"),
                                'entry_price': st.column_config.NumberColumn('Entrada', format="$%.2f"),
                                'exit_price': st.column_config.NumberColumn('Salida', format="$%.2f")})
    st.download_button("Exportar CSV", df.drop(columns=['ts']).to_csv(index=False), "trades.csv", "text/csv", icon=":material/download:")


# ---------------------------------------------------------------- CONFIG
def _reset_alerts():
    for k in ('seen_id', 'seen_pos'):
        st.session_state.pop(k, None)


def config_tab():
    c = dict(cfg)
    st.markdown('<div class="sec">Panel de control</div>', unsafe_allow_html=True)
    top = st.columns([1, 1, 1, 2])
    with top[0]:
        if st.button("Pausar bot" if c['bot_enabled'] else "Reanudar bot", icon=":material/pause_circle:" if c['bot_enabled'] else ":material/play_circle:", use_container_width=True):
            cfg['bot_enabled'] = not cfg['bot_enabled']; save_settings(cfg); st.rerun()
    with top[1]:
        st.toggle("Modo demo (datos ficticios)", key='demo', on_change=_reset_alerts)
    with top[2]:
        if st.button("Probar sonidos", icon=":material/volume_up:", use_container_width=True):
            st.session_state.test_sound = time.time()
    if 'test_sound' in st.session_state:
        play(cfg['sound_win'], st.session_state.test_sound)

    with st.form("cfg_form"):
        t1, t2, t3, t4 = st.tabs([":material/psychology: Estrategia", ":material/shield: Riesgo", ":material/notifications_active: Alertas y sonido", ":material/palette: Interfaz"])
        with t1:
            a, b, d = st.columns(3)
            c['SYMBOL'] = a.text_input("Par", c['SYMBOL']).upper()
            c['INTERVAL'] = b.selectbox("Intervalo de vela", ['1m', '5m', '15m', '30m', '1h', '4h', '1d'],
                                        index=['1m', '5m', '15m', '30m', '1h', '4h', '1d'].index(c['INTERVAL']) if c['INTERVAL'] in ['1m', '5m', '15m', '30m', '1h', '4h', '1d'] else 4)
            c['SLEEP_SECONDS'] = d.number_input("Ciclo del bot (seg)", 10, 86400, int(c['SLEEP_SECONDS']), 10)
            c['MIN_CONFIDENCE'] = a.slider("Confianza mínima ML", 0.50, 0.95, float(c['MIN_CONFIDENCE']), 0.01)
            c['MIN_VOLUME_RATIO'] = b.slider("Volumen mínimo vs promedio", 0.1, 3.0, float(c['MIN_VOLUME_RATIO']), 0.05)
            c['MAX_ATR_PCT'] = d.slider("Volatilidad máx (ATR %)", 0.5, 15.0, float(c['MAX_ATR_PCT']), 0.1)
        with t2:
            a, b, d = st.columns(3)
            c['RISK_PER_TRADE'] = a.slider("Riesgo por trade", 0.005, 0.10, float(c['RISK_PER_TRADE']), 0.005, format="%.3f")
            c['STOP_LOSS_PCT'] = b.slider("Stop Loss", 0.005, 0.15, float(c['STOP_LOSS_PCT']), 0.005, format="%.3f")
            c['TAKE_PROFIT_PCT'] = d.slider("Take Profit", 0.005, 0.30, float(c['TAKE_PROFIT_PCT']), 0.005, format="%.3f")
            c['TRAILING_STOP_ENABLED'] = a.toggle("Trailing stop", bool(c['TRAILING_STOP_ENABLED']))
            c['TRAILING_STOP_PCT'] = b.slider("Distancia trailing", 0.005, 0.10, float(c['TRAILING_STOP_PCT']), 0.005, format="%.3f")
            c['TRAILING_STOP_ACTIVATION'] = d.slider("Activar trailing tras", 0.0, 0.10, float(c['TRAILING_STOP_ACTIVATION']), 0.005, format="%.3f")
            c['initial_balance'] = a.number_input("Balance inicial (USDT)", 1.0, 1e9, float(c['initial_balance']), 100.0)
            c['daily_loss_limit'] = b.number_input("Límite pérdida diaria (USDT, 0=off)", 0.0, 1e9, float(c['daily_loss_limit']), 10.0)
            c['daily_profit_target'] = d.number_input("Meta ganancia diaria (USDT, 0=off)", 0.0, 1e9, float(c['daily_profit_target']), 10.0)
            st.caption("Ratio riesgo/beneficio: **1 : %.1f**" % (c['TAKE_PROFIT_PCT'] / c['STOP_LOSS_PCT']))
        with t3:
            a, b, d = st.columns(3)
            c['sound_enabled'] = a.toggle("Sonidos activados", bool(c['sound_enabled']))
            c['sound_on_open'] = b.toggle("Sonar al abrir posición", bool(c['sound_on_open']))
            c['sound_volume'] = d.slider("Volumen", 0.0, 1.0, float(c['sound_volume']), 0.05)
            wins_ = ['Campana', 'Moneda', 'Arpegio']; loss_ = ['Grave', 'Alerta', 'Silencio']
            c['sound_win'] = a.selectbox("Sonido de ganancia", wins_, index=wins_.index(c['sound_win']) if c['sound_win'] in wins_ else 0)
            c['sound_loss'] = b.selectbox("Sonido de pérdida", loss_, index=loss_.index(c['sound_loss']) if c['sound_loss'] in loss_ else 0)
            c['notify_min_profit'] = d.number_input("Solo sonar si |P&L| ≥ (USDT)", 0.0, 1e6, float(c['notify_min_profit']), 0.5)
            st.caption("Los navegadores exigen un clic en la página antes de permitir audio: pulsa «Probar sonidos» una vez.")
        with t4:
            a, b, d = st.columns(3)
            themes = list(THEMES)
            c['theme'] = a.selectbox("Color de acento", themes, index=themes.index(c['theme']) if c['theme'] in themes else 0)
            c['refresh_seconds'] = b.select_slider("Auto-actualización (seg)", [1, 2, 3, 5, 10, 15, 30, 60], int(c['refresh_seconds']) if int(c['refresh_seconds']) in [1, 2, 3, 5, 10, 15, 30, 60] else 5)
            c['max_trades_shown'] = d.number_input("Trades en tabla", 5, 1000, int(c['max_trades_shown']), 5)
        s1, s2 = st.columns([1, 1])
        save = s1.form_submit_button("Guardar configuración", icon=":material/save:", use_container_width=True)
        reset = s2.form_submit_button("Restaurar valores por defecto", icon=":material/restart_alt:", use_container_width=True)
    if save:
        cfg.update(c); save_settings(cfg)
        st.success("Configuración guardada. El bot la aplicará en su próximo ciclo.")
        st.rerun()
    if reset:
        cfg.clear(); cfg.update(DEFAULTS); save_settings(cfg); st.rerun()


# ---------------------------------------------------------------- main
inject_css()
header(0)
tab_live, tab_hist, tab_cfg = st.tabs([":material/monitoring: Panel", ":material/receipt_long: Operaciones", ":material/tune: Configuración"])
with tab_live:
    live_panel()
with tab_hist:
    history_tab()
with tab_cfg:
    config_tab()
