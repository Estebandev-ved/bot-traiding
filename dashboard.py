"""
NEXUS//TRADER — Dashboard futurista para el bot de trading.
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

THEMES = {  # primario, secundario
    'Cyan': ('#00f0ff', '#7a5cff'),
    'Violeta': ('#b46bff', '#ff4fd8'),
    'Verde': ('#00ff9d', '#00b8ff'),
    'Ámbar': ('#ffb300', '#ff5a36'),
}
WIN, LOSS = '#00ff9d', '#ff3d6e'

st.set_page_config(page_title="NEXUS//TRADER", page_icon="⚡", layout="wide",
                   initial_sidebar_state="collapsed")

if 'cfg' not in st.session_state:
    st.session_state.cfg = load_settings()
cfg = st.session_state.cfg
C1, C2 = THEMES.get(cfg['theme'], THEMES['Cyan'])


# ---------------------------------------------------------------- estilos
def inject_css():
    st.markdown(f"""
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Rajdhani:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {{ --c1:{C1}; --c2:{C2}; --win:{WIN}; --loss:{LOSS}; --bg:#05060f; --panel:rgba(14,18,40,.72); }}
html, body, [class*="css"], .stApp {{ font-family:'Rajdhani',sans-serif; color:#dfe8ff; }}
.stApp {{
  background:
    radial-gradient(1200px 600px at 10% -10%, color-mix(in srgb, var(--c2) 22%, transparent), transparent 60%),
    radial-gradient(900px 500px at 100% 0%, color-mix(in srgb, var(--c1) 16%, transparent), transparent 55%),
    linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px) 0 0/44px 44px,
    linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px) 0 0/44px 44px,
    var(--bg);
}}
header[data-testid="stHeader"] {{ background:transparent; }}
.block-container {{ padding-top:1.2rem; max-width:1500px; }}
.brand {{ display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap:wrap;
  padding:.9rem 1.3rem; border:1px solid color-mix(in srgb,var(--c1) 35%,transparent);
  background:var(--panel); backdrop-filter:blur(10px); border-radius:14px;
  box-shadow:0 0 30px color-mix(in srgb,var(--c1) 14%,transparent), inset 0 0 40px rgba(255,255,255,.02); }}
.brand h1 {{ font-family:Orbitron; font-weight:900; letter-spacing:.18em; margin:0; font-size:1.7rem;
  background:linear-gradient(90deg,var(--c1),var(--c2)); -webkit-background-clip:text; color:transparent; }}
.brand small {{ color:#8a97c4; letter-spacing:.25em; font-size:.75rem; text-transform:uppercase; }}
.pill {{ font-family:Orbitron; font-size:.7rem; letter-spacing:.15em; padding:.35rem .8rem; border-radius:99px;
  border:1px solid; display:inline-flex; align-items:center; gap:.5rem; }}
.pill.on {{ color:var(--win); border-color:var(--win); background:rgba(0,255,157,.08); }}
.pill.off {{ color:#ffb300; border-color:#ffb300; background:rgba(255,179,0,.08); }}
.dot {{ width:8px; height:8px; border-radius:50%; background:currentColor; box-shadow:0 0 10px currentColor; animation:pulse 1.4s infinite; }}
@keyframes pulse {{ 50% {{ opacity:.25; transform:scale(.7); }} }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:14px; margin:16px 0; }}
.kpi {{ position:relative; overflow:hidden; padding:16px 18px; border-radius:14px; background:var(--panel);
  border:1px solid rgba(255,255,255,.07); backdrop-filter:blur(8px); }}
.kpi::before {{ content:""; position:absolute; inset:0 0 auto 0; height:2px;
  background:linear-gradient(90deg,transparent,var(--c1),transparent); opacity:.8; }}
.kpi .l {{ font-size:.72rem; letter-spacing:.22em; color:#8a97c4; text-transform:uppercase; }}
.kpi .v {{ font-family:Orbitron; font-size:1.65rem; font-weight:700; margin-top:6px; }}
.kpi .s {{ font-size:.85rem; color:#8a97c4; margin-top:2px; }}
.pos {{ color:var(--win); text-shadow:0 0 14px rgba(0,255,157,.45); }}
.neg {{ color:var(--loss); text-shadow:0 0 14px rgba(255,61,110,.45); }}
.neu {{ color:#fff; }}
.sec {{ font-family:Orbitron; letter-spacing:.2em; font-size:.8rem; color:var(--c1); margin:14px 0 6px;
  display:flex; align-items:center; gap:10px; text-transform:uppercase; }}
.sec::after {{ content:""; flex:1; height:1px; background:linear-gradient(90deg,var(--c1),transparent); opacity:.5; }}
.ticker {{ overflow:hidden; white-space:nowrap; border-radius:10px; border:1px solid rgba(255,255,255,.07);
  background:rgba(0,0,0,.35); padding:6px 0; margin-top:12px; }}
.ticker span {{ display:inline-block; padding-left:100%; animation:slide 40s linear infinite;
  font-family:Orbitron; font-size:.75rem; letter-spacing:.12em; color:#9fb0e6; }}
@keyframes slide {{ to {{ transform:translateX(-100%); }} }}
.poscard {{ padding:16px 20px; border-radius:14px; background:var(--panel); border:1px solid var(--c1);
  box-shadow:0 0 24px color-mix(in srgb,var(--c1) 22%,transparent); }}
.poscard b {{ font-family:Orbitron; color:var(--c1); }}
.stTabs [data-baseweb="tab-list"] {{ gap:6px; border-bottom:1px solid rgba(255,255,255,.08); }}
.stTabs [data-baseweb="tab"] {{ font-family:Orbitron; letter-spacing:.15em; font-size:.78rem; padding:10px 18px;
  background:transparent; border-radius:8px 8px 0 0; color:#b9c6ee; }}
.stTabs [aria-selected="true"] {{ color:var(--c1)!important; background:color-mix(in srgb,var(--c1) 10%,transparent)!important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background:var(--c1)!important; box-shadow:0 0 12px var(--c1); }}
div[data-testid="stForm"] {{ border:1px solid rgba(255,255,255,.08); background:var(--panel); border-radius:14px; }}
.stButton>button, .stFormSubmitButton>button {{ font-family:Orbitron; letter-spacing:.14em; font-size:.75rem;
  border:1px solid var(--c1); color:var(--c1); background:transparent; border-radius:10px; transition:.2s; }}
.stButton>button:hover, .stFormSubmitButton>button:hover {{ background:var(--c1); color:#000; box-shadow:0 0 20px var(--c1); }}
[data-testid="stDataFrame"] {{ border:1px solid rgba(255,255,255,.08); border-radius:12px; overflow:hidden; }}
label, .stMarkdown p {{ font-weight:500; }}
</style>""", unsafe_allow_html=True)


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
                sound = cfg['sound_win']; msgs.append(('🟢', f"GANANCIA +${p:,.2f}"))
            else:
                sound = cfg['sound_loss']; msgs.append(('🔴', f"PÉRDIDA -${abs(p):,.2f}"))
        ss.seen_id = last_id
    if pos_key and pos_key != ss.seen_pos and cfg['sound_on_open']:
        sound = sound or 'Apertura'; msgs.append(('⚡', 'NUEVA POSICIÓN ABIERTA'))
    ss.seen_pos = pos_key
    # límites diarios
    today = [t for t in trades if str(t.get('timestamp', ''))[:10] == datetime.now().strftime('%Y-%m-%d')]
    day = sum(t.get('profit', 0) for t in today)
    if cfg['daily_loss_limit'] > 0 and day <= -cfg['daily_loss_limit'] and not ss.get('warned_loss'):
        ss.warned_loss = True; sound = 'Alerta'; msgs.append(('🛑', f"LÍMITE DE PÉRDIDA DIARIA ({day:,.2f})"))
    if cfg['daily_profit_target'] > 0 and day >= cfg['daily_profit_target'] and not ss.get('warned_win'):
        ss.warned_win = True; sound = cfg['sound_win']; msgs.append(('🎯', f"META DIARIA ALCANZADA (+{day:,.2f})"))
    return sound, msgs


# ---------------------------------------------------------------- componentes
def fmt_money(v, sign=True):
    return f"{'+' if sign and v > 0 else '-' if v < 0 else ''}${abs(v):,.2f}"


def kpi(label, value, sub='', cls='neu'):
    return f'<div class="kpi"><div class="l">{label}</div><div class="v {cls}">{value}</div><div class="s">{sub}</div></div>'


def style_fig(fig, h=320):
    fig.update_layout(template='plotly_dark', height=h, margin=dict(l=10, r=10, t=10, b=10),
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False,
                      font=dict(family='Rajdhani', color='#9fb0e6'), hovermode='x unified')
    fig.update_xaxes(gridcolor='rgba(255,255,255,.05)', zeroline=False)
    fig.update_yaxes(gridcolor='rgba(255,255,255,.05)', zeroline=False)
    return fig


def header(trades_n):
    on = cfg['bot_enabled']
    st.markdown(f"""
<div class="brand"><div><h1>NEXUS//TRADER</h1><small>Quantum Trading Terminal · {cfg['SYMBOL']} · {cfg['INTERVAL']}</small></div>
<div style="display:flex;gap:10px;flex-wrap:wrap">
<span class="pill {'on' if on else 'off'}"><span class="dot"></span>{'BOT ACTIVO' if on else 'BOT EN PAUSA'}</span>
<span class="pill on" style="color:var(--c1);border-color:var(--c1);background:transparent">LIVE · {cfg['refresh_seconds']}s</span>
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
                     f"{chg:+.2f}% 24h" if chg is not None else "sin conexión", cls(chg or 0))
    st.markdown('<div class="kpis">' +
                kpi('Balance', f"${balance:,.2f}", f"inicial ${cfg['initial_balance']:,.0f}") +
                kpi('P&L total', fmt_money(total), f"{total / cfg['initial_balance'] * 100:+.2f}% ROI", cls(total)) +
                kpi('P&L hoy', fmt_money(day), datetime.now().strftime('%d %b %Y'), cls(day)) +
                kpi('Win rate', f"{wr:.1f}%", f"{wins}W / {n - wins}L · {n} trades") +
                kpi('Profit factor', '∞' if pf == float('inf') else f"{pf:.2f}", 'ganancia bruta / pérdida bruta') +
                price_html + '</div>', unsafe_allow_html=True)

    if position:
        ep = position.get('entry_price', 0)
        unreal = ((price - ep) * position.get('quantity', 0)) if price else None
        st.markdown(f"""<div class="poscard">⚡ <b>POSICIÓN ABIERTA</b> &nbsp; {position.get('quantity',0):.6f} {position.get('symbol','')}
 @ ${ep:,.2f} &nbsp;|&nbsp; SL ${position.get('stop_loss',0):,.2f} &nbsp;|&nbsp; TP ${position.get('take_profit',0):,.2f}
 {'&nbsp;|&nbsp; P&L flotante <span class="'+cls(unreal)+'">'+fmt_money(unreal)+'</span>' if unreal is not None else ''}</div>""",
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="poscard" style="border-color:rgba(255,255,255,.1);box-shadow:none">'
                    '◌ Sin posición abierta — escaneando mercado…</div>', unsafe_allow_html=True)

    gl_, gr_ = st.columns([3, 2])
    with gl_:
        st.markdown('<div class="sec">Equity curve</div>', unsafe_allow_html=True)
        if n:
            eq = (df['profit'].cumsum() + cfg['initial_balance']).tolist()
            xs = df['ts'] if df['ts'].notna().all() else list(range(n))
            col = WIN if total >= 0 else LOSS
            fig = go.Figure(go.Scatter(x=xs, y=eq, mode='lines', line=dict(color=col, width=3, shape='spline'),
                                       fill='tozeroy', fillcolor='rgba(0,255,157,.08)' if total >= 0 else 'rgba(255,61,110,.08)'))
            fig.add_hline(y=cfg['initial_balance'], line_dash='dot', line_color='rgba(255,255,255,.3)')
            fig.update_yaxes(range=[min(eq + [cfg['initial_balance']]) * .995, max(eq + [cfg['initial_balance']]) * 1.005])
            st.plotly_chart(style_fig(fig), use_container_width=True, key='eq')
        else:
            st.info("Aún no hay trades. Activa **modo demo** en la pestaña CONFIG para previsualizar.")
    with gr_:
        st.markdown('<div class="sec">P&L por trade</div>', unsafe_allow_html=True)
        if n:
            last = df.tail(30)
            fig = go.Figure(go.Bar(y=last['profit'], marker_color=[WIN if p > 0 else LOSS for p in last['profit']]))
            st.plotly_chart(style_fig(fig), use_container_width=True, key='pnl')

    if n:
        items = '   ◆   '.join(f"#{r.get('id', i)} {'▲' if r['profit'] > 0 else '▼'} {fmt_money(r['profit'])}"
                               for i, r in df.tail(12).iterrows())
        st.markdown(f'<div class="ticker"><span>{items}</span></div>', unsafe_allow_html=True)
    st.caption(f"⟳ actualizado {datetime.now().strftime('%H:%M:%S')}")


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
    st.download_button("⬇ EXPORTAR CSV", df.drop(columns=['ts']).to_csv(index=False), "trades.csv", "text/csv")


# ---------------------------------------------------------------- CONFIG
def _reset_alerts():
    for k in ('seen_id', 'seen_pos'):
        st.session_state.pop(k, None)


def config_tab():
    c = dict(cfg)
    st.markdown('<div class="sec">Centro de control</div>', unsafe_allow_html=True)
    top = st.columns([1, 1, 1, 2])
    with top[0]:
        if st.button("⏸ PAUSAR BOT" if c['bot_enabled'] else "▶ REANUDAR BOT", use_container_width=True):
            cfg['bot_enabled'] = not cfg['bot_enabled']; save_settings(cfg); st.rerun()
    with top[1]:
        st.toggle("Modo demo (datos ficticios)", key='demo', on_change=_reset_alerts)
    with top[2]:
        if st.button("🔊 PROBAR SONIDOS", use_container_width=True):
            st.session_state.test_sound = time.time()
    if 'test_sound' in st.session_state:
        play(cfg['sound_win'], st.session_state.test_sound)

    with st.form("cfg_form"):
        t1, t2, t3, t4 = st.tabs(["⚔ ESTRATEGIA", "🛡 RIESGO", "🔔 ALERTAS & SONIDO", "🎨 INTERFAZ"])
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
            c['theme'] = a.selectbox("Tema neón", themes, index=themes.index(c['theme']) if c['theme'] in themes else 0)
            c['refresh_seconds'] = b.select_slider("Auto-actualización (seg)", [1, 2, 3, 5, 10, 15, 30, 60], int(c['refresh_seconds']) if int(c['refresh_seconds']) in [1, 2, 3, 5, 10, 15, 30, 60] else 5)
            c['max_trades_shown'] = d.number_input("Trades en tabla", 5, 1000, int(c['max_trades_shown']), 5)
        s1, s2 = st.columns([1, 1])
        save = s1.form_submit_button("💾 GUARDAR CONFIGURACIÓN", use_container_width=True)
        reset = s2.form_submit_button("↺ RESTAURAR VALORES POR DEFECTO", use_container_width=True)
    if save:
        cfg.update(c); save_settings(cfg)
        st.success("Configuración guardada. El bot la aplicará en su próximo ciclo.")
        st.rerun()
    if reset:
        cfg.clear(); cfg.update(DEFAULTS); save_settings(cfg); st.rerun()


# ---------------------------------------------------------------- main
inject_css()
header(0)
tab_live, tab_hist, tab_cfg = st.tabs(["◈ PANEL EN VIVO", "▤ OPERACIONES", "⚙ CONFIGURACIÓN"])
with tab_live:
    live_panel()
with tab_hist:
    history_tab()
with tab_cfg:
    config_tab()
