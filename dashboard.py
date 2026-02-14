"""
Dashboard Web para Bot de Trading
Interfaz Streamlit para monitoreo en tiempo real
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import json
import os
import sys

# Agregar directorio actual al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Importar módulos del bot
try:
    from metrics import PerformanceMetrics
    from logger import TradesHistory
    from position_manager import PositionManager
    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False


# Configuración de página
st.set_page_config(
    page_title="Bot de Trading Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        padding: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .positive {color: #00ff00;}
    .negative {color: #ff4444;}
    .stMetric {
        background-color: #1e1e1e;
        padding: 1rem;
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)


def load_trades_history():
    """Carga historial de trades desde archivo"""
    trades_file = 'logs/trades_history.json'
    if os.path.exists(trades_file):
        with open(trades_file, 'r') as f:
            return json.load(f)
    return []


def load_position_state():
    """Carga estado de posición actual"""
    state_file = 'positions_state.json'
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            return json.load(f)
    return {'position': None, 'pending_orders': []}


def main():
    # Header
    st.markdown('<h1 class="main-header">🤖 Bot de Trading Dashboard</h1>', unsafe_allow_html=True)
    
    # Sidebar
    st.sidebar.title("⚙️ Configuración")
    
    # Estado del bot (simulado)
    bot_status = st.sidebar.selectbox(
        "Estado del Bot",
        ["🟢 ACTIVO", "🟡 PAUSADO", "🔴 DETENIDO"],
        index=0
    )
    
    st.sidebar.markdown("---")
    
    # Cargar datos
    trades = load_trades_history()
    position_state = load_position_state()
    
    # Métricas principales
    st.markdown("### 📊 Métricas en Tiempo Real")
    
    col1, col2, col3, col4 = st.columns(4)
    
    # Calcular métricas
    total_trades = len(trades)
    total_profit = sum(t.get('profit', 0) for t in trades)
    wins = sum(1 for t in trades if t.get('profit', 0) > 0)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    with col1:
        st.metric("Total Trades", total_trades)
    
    with col2:
        st.metric("P&L Total", f"${total_profit:,.2f}", 
                  delta=f"{total_profit:+.2f}" if total_profit != 0 else None)
    
    with col3:
        st.metric("Win Rate", f"{win_rate:.1f}%")
    
    with col4:
        position = position_state.get('position')
        if position:
            st.metric("Posición Activa", f"{position.get('quantity', 0):.4f} BTC",
                     delta=f"@ ${position.get('entry_price', 0):,.2f}")
        else:
            st.metric("Posición Activa", "Sin posición")
    
    st.markdown("---")
    
    # Gráficas
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.markdown("### 📈 Equity Curve")
        
        if trades:
            # Construir equity curve
            initial_balance = 1000
            equity = [initial_balance]
            for trade in trades:
                equity.append(equity[-1] + trade.get('profit', 0))
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                y=equity,
                mode='lines+markers',
                name='Equity',
                line=dict(color='#00ff88', width=2),
                fill='tozeroy',
                fillcolor='rgba(0,255,136,0.1)'
            ))
            fig.update_layout(
                template='plotly_dark',
                height=300,
                margin=dict(l=20, r=20, t=20, b=20),
                showlegend=False,
                yaxis_title='Balance (USDT)'
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay trades para mostrar")
    
    with col_right:
        st.markdown("### 🎯 Distribución de P&L")
        
        if trades:
            profits = [t.get('profit', 0) for t in trades]
            colors = ['#00ff88' if p > 0 else '#ff4444' for p in profits]
            
            fig = go.Figure()
            fig.add_trace(go.Bar(
                y=profits,
                marker_color=colors,
                name='P&L por Trade'
            ))
            fig.update_layout(
                template='plotly_dark',
                height=300,
                margin=dict(l=20, r=20, t=20, b=20),
                showlegend=False,
                yaxis_title='Profit (USDT)'
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay trades para mostrar")
    
    st.markdown("---")
    
    # Tabla de trades recientes
    st.markdown("### 📋 Trades Recientes")
    
    if trades:
        df = pd.DataFrame(trades[-20:])  # Últimos 20 trades
        
        # Formatear columnas
        if 'profit' in df.columns:
            df['profit'] = df['profit'].apply(lambda x: f"${x:,.2f}")
        if 'profit_pct' in df.columns:
            df['profit_pct'] = df['profit_pct'].apply(lambda x: f"{x:+.2f}%")
        if 'entry_price' in df.columns:
            df['entry_price'] = df['entry_price'].apply(lambda x: f"${x:,.2f}")
        if 'exit_price' in df.columns:
            df['exit_price'] = df['exit_price'].apply(lambda x: f"${x:,.2f}")
        
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No hay trades registrados")
    
    st.markdown("---")
    
    # Métricas avanzadas
    st.markdown("### 📉 Métricas Avanzadas")
    
    col1, col2, col3, col4 = st.columns(4)
    
    if trades and MODULES_AVAILABLE:
        metrics = PerformanceMetrics()
        metrics.load_trades(trades)
        all_metrics = metrics.get_all_metrics()
        
        with col1:
            st.metric("Sharpe Ratio", f"{all_metrics.get('sharpe_ratio', 0):.2f}")
        with col2:
            st.metric("Max Drawdown", f"{all_metrics.get('max_drawdown_pct', 0):.2f}%")
        with col3:
            st.metric("Profit Factor", f"{all_metrics.get('profit_factor', 0):.2f}")
        with col4:
            st.metric("Sortino Ratio", f"{all_metrics.get('sortino_ratio', 0):.2f}")
    else:
        with col1:
            st.metric("Sharpe Ratio", "N/A")
        with col2:
            st.metric("Max Drawdown", "N/A")
        with col3:
            st.metric("Profit Factor", "N/A")
        with col4:
            st.metric("Sortino Ratio", "N/A")
    
    # Footer
    st.markdown("---")
    st.markdown(
        f"<p style='text-align: center; color: gray;'>Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>",
        unsafe_allow_html=True
    )
    
    # Auto-refresh
    if st.sidebar.checkbox("🔄 Auto-refresh (30s)", value=False):
        st.rerun()


if __name__ == "__main__":
    main()
