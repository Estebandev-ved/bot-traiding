#!/usr/bin/env python3
"""
Monitor del Bot de Trading con Gráficas en Tiempo Real
"""

import matplotlib.pyplot as plt
import matplotlib.animation as animation
from binance.client import Client
from dotenv import load_dotenv
import pandas as pd
import numpy as np
import os
import time
from datetime import datetime
import talib

# Cargar configuración
load_dotenv('config.env')

class BotMonitor:
    def __init__(self):
        # Configuración
        self.symbol = os.getenv('SYMBOL', 'BTCUSDT')
        self.interval = os.getenv('INTERVAL', '1h')
        
        # Cliente Binance
        api_key = os.getenv('BINANCE_TESTNET_API_KEY')
        api_secret = os.getenv('BINANCE_TESTNET_API_SECRET')
        self.client = Client(api_key, api_secret, testnet=True)
        self.client.API_URL = "https://testnet.binance.vision/api"
        
        # Datos para gráficas
        self.prices = []
        self.ema9_values = []
        self.ema26_values = []
        self.rsi_values = []
        self.timestamps = []
        self.signals = []
        
        # Configurar gráficas
        self.setup_plots()
        
    def setup_plots(self):
        """Configura las gráficas"""
        self.fig, (self.ax1, self.ax2, self.ax3) = plt.subplots(3, 1, figsize=(12, 10))
        self.fig.suptitle(f'Bot de Trading - {self.symbol} - Tiempo Real', fontsize=16)
        
        # Gráfica de precios y EMAs
        self.ax1.set_title('Precio y Medias Móviles')
        self.ax1.set_ylabel('Precio (USDT)')
        self.ax1.grid(True)
        
        # Gráfica de RSI
        self.ax2.set_title('RSI (14)')
        self.ax2.set_ylabel('RSI')
        self.ax2.set_ylim(0, 100)
        self.ax2.axhline(y=70, color='r', linestyle='--', alpha=0.7, label='Sobrecompra')
        self.ax2.axhline(y=30, color='g', linestyle='--', alpha=0.7, label='Sobreventa')
        self.ax2.grid(True)
        self.ax2.legend()
        
        # Gráfica de señales
        self.ax3.set_title('Señales de Trading')
        self.ax3.set_ylabel('Señal')
        self.ax3.set_xlabel('Tiempo')
        self.ax3.set_ylim(-1.5, 1.5)
        self.ax3.grid(True)
        
    def get_latest_data(self):
        """Obtiene los datos más recientes"""
        try:
            # Obtener velas recientes
            klines = self.client.get_klines(
                symbol=self.symbol,
                interval=self.interval,
                limit=100
            )
            
            # Convertir a DataFrame
            df = pd.DataFrame(klines, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base', 'taker_buy_quote', 'ignore'
            ])
            
            # Convertir tipos
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(float)
            df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
            
            # Calcular indicadores
            close_prices = df['close'].values
            df['EMA9'] = talib.EMA(close_prices, timeperiod=9)
            df['EMA26'] = talib.EMA(close_prices, timeperiod=26)
            df['RSI14'] = talib.RSI(close_prices, timeperiod=14)
            
            # Detectar señales
            df['signal'] = 0
            for i in range(1, len(df)):
                if (df.iloc[i-1]['EMA9'] <= df.iloc[i-1]['EMA26'] and 
                    df.iloc[i]['EMA9'] > df.iloc[i]['EMA26']):
                    df.iloc[i, df.columns.get_loc('signal')] = 1  # Señal de compra
                elif (df.iloc[i-1]['EMA9'] >= df.iloc[i-1]['EMA26'] and 
                      df.iloc[i]['EMA9'] < df.iloc[i]['EMA26']):
                    df.iloc[i, df.columns.get_loc('signal')] = -1  # Señal de venta
            
            return df
            
        except Exception as e:
            print(f"Error obteniendo datos: {e}")
            return None
    
    def update_plots(self, frame):
        """Actualiza las gráficas"""
        df = self.get_latest_data()
        if df is None or len(df) < 50:
            return
        
        # Limpiar gráficas
        self.ax1.clear()
        self.ax2.clear()
        self.ax3.clear()
        
        # Configurar gráficas nuevamente
        self.setup_plots()
        
        # Obtener últimos 50 puntos para mejor visualización
        df_plot = df.tail(50).copy()
        
        # Gráfica 1: Precios y EMAs
        self.ax1.plot(df_plot['close_time'], df_plot['close'], label='Precio', linewidth=2)
        self.ax1.plot(df_plot['close_time'], df_plot['EMA9'], label='EMA 9', alpha=0.7)
        self.ax1.plot(df_plot['close_time'], df_plot['EMA26'], label='EMA 26', alpha=0.7)
        self.ax1.legend()
        self.ax1.grid(True)
        
        # Marcar señales de compra/venta
        buy_signals = df_plot[df_plot['signal'] == 1]
        sell_signals = df_plot[df_plot['signal'] == -1]
        
        if not buy_signals.empty:
            self.ax1.scatter(buy_signals['close_time'], buy_signals['close'], 
                           color='green', marker='^', s=100, label='Señal Compra')
        if not sell_signals.empty:
            self.ax1.scatter(sell_signals['close_time'], sell_signals['close'], 
                           color='red', marker='v', s=100, label='Señal Venta')
        
        # Gráfica 2: RSI
        self.ax2.plot(df_plot['close_time'], df_plot['RSI14'], label='RSI 14', color='purple')
        self.ax2.axhline(y=70, color='r', linestyle='--', alpha=0.7)
        self.ax2.axhline(y=30, color='g', linestyle='--', alpha=0.7)
        self.ax2.legend()
        self.ax2.grid(True)
        
        # Gráfica 3: Señales
        colors = ['red' if x == -1 else 'green' if x == 1 else 'gray' for x in df_plot['signal']]
        self.ax3.scatter(df_plot['close_time'], df_plot['signal'], c=colors, s=50)
        self.ax3.set_ylim(-1.5, 1.5)
        self.ax3.grid(True)
        
        # Información adicional
        current_price = df_plot['close'].iloc[-1]
        current_rsi = df_plot['RSI14'].iloc[-1]
        current_signal = df_plot['signal'].iloc[-1]
        
        self.ax1.text(0.02, 0.98, f'Precio: ${current_price:.2f}', 
                     transform=self.ax1.transAxes, verticalalignment='top',
                     bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        self.ax2.text(0.02, 0.98, f'RSI: {current_rsi:.1f}', 
                     transform=self.ax2.transAxes, verticalalignment='top',
                     bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        signal_text = "COMPRA" if current_signal == 1 else "VENTA" if current_signal == -1 else "ESPERAR"
        signal_color = "green" if current_signal == 1 else "red" if current_signal == -1 else "gray"
        
        self.ax3.text(0.02, 0.98, f'Señal: {signal_text}', 
                     transform=self.ax3.transAxes, verticalalignment='top',
                     bbox=dict(boxstyle='round', facecolor=signal_color, alpha=0.8))
        
        plt.tight_layout()
    
    def start_monitoring(self):
        """Inicia el monitoreo en tiempo real"""
        print("Iniciando monitor del bot...")
        print("Presiona Ctrl+C para detener")
        
        # Animación que se actualiza cada 30 segundos
        ani = animation.FuncAnimation(self.fig, self.update_plots, interval=30000, blit=False)
        
        try:
            plt.show()
        except KeyboardInterrupt:
            print("\nMonitor detenido por el usuario")

def main():
    """Función principal"""
    print("="*60)
    print("MONITOR DEL BOT DE TRADING - GRAFICAS EN TIEMPO REAL")
    print("="*60)
    print("Este monitor muestra:")
    print("- Precios y medias móviles")
    print("- RSI en tiempo real")
    print("- Señales de compra/venta")
    print("- Se actualiza cada 30 segundos")
    print("="*60)
    
    try:
        monitor = BotMonitor()
        monitor.start_monitoring()
    except Exception as e:
        print(f"Error iniciando monitor: {e}")

if __name__ == "__main__":
    main()
