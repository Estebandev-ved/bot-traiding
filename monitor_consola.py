#!/usr/bin/env python3
"""
Monitor del Bot desde Consola - Sin Gráficas
"""

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

def get_market_data():
    """Obtiene datos del mercado"""
    try:
        # Cliente Binance
        api_key = os.getenv('BINANCE_TESTNET_API_KEY')
        api_secret = os.getenv('BINANCE_TESTNET_API_SECRET')
        client = Client(api_key, api_secret, testnet=True)
        client.API_URL = "https://testnet.binance.vision/api"
        
        # Obtener datos
        symbol = os.getenv('SYMBOL', 'BTCUSDT')
        klines = client.get_klines(symbol=symbol, interval='1h', limit=100)
        
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
        
        return df, client
        
    except Exception as e:
        print(f"Error obteniendo datos: {e}")
        return None, None

def detect_signal(df):
    """Detecta señales de trading"""
    if len(df) < 2:
        return 0, "Sin datos suficientes"
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Señal EMA crossover
    if (prev['EMA9'] <= prev['EMA26']) and (last['EMA9'] > last['EMA26']):
        return 1, "SEÑAL DE COMPRA - EMA9 cruza por encima EMA26"
    elif (prev['EMA9'] >= prev['EMA26']) and (last['EMA9'] < last['EMA26']):
        return -1, "SEÑAL DE VENTA - EMA9 cruza por debajo EMA26"
    else:
        return 0, "Sin señal - Esperando cruce"

def get_balance_info(client):
    """Obtiene información del balance"""
    try:
        account = client.get_account()
        usdt_balance = 0
        btc_balance = 0
        
        for balance in account['balances']:
            if balance['asset'] == 'USDT':
                usdt_balance = float(balance['free'])
            elif balance['asset'] == 'BTC':
                btc_balance = float(balance['free'])
        
        return usdt_balance, btc_balance
    except:
        return 0, 0

def print_status(df, signal, signal_text, usdt_balance, btc_balance):
    """Imprime el estado actual"""
    # Limpiar pantalla (funciona en Windows)
    os.system('cls' if os.name == 'nt' else 'clear')
    
    last = df.iloc[-1]
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    print("="*80)
    print(f"BOT DE TRADING - MONITOR EN TIEMPO REAL")
    print(f"Ultima actualizacion: {current_time}")
    print("="*80)
    
    # Información del mercado
    print(f"PAR: {os.getenv('SYMBOL', 'BTCUSDT')}")
    print(f"Precio actual: ${last['close']:.2f} USDT")
    print(f"EMA 9: ${last['EMA9']:.2f}")
    print(f"EMA 26: ${last['EMA26']:.2f}")
    print(f"RSI (14): {last['RSI14']:.1f}")
    
    # Estado de las medias
    if last['EMA9'] > last['EMA26']:
        ema_status = "ALCISTA (EMA9 > EMA26)"
    else:
        ema_status = "BAJISTA (EMA9 < EMA26)"
    print(f"Estado EMAs: {ema_status}")
    
    # Señal actual
    if signal == 1:
        signal_display = "COMPRA"
    elif signal == -1:
        signal_display = "VENTA"
    else:
        signal_display = "ESPERAR"
    
    print(f"Senal actual: {signal_display}")
    print(f"Detalle: {signal_text}")
    
    # Balance
    print(f"Balance USDT: {usdt_balance:.2f}")
    print(f"Balance BTC: {btc_balance:.8f}")
    
    # Historial de precios (últimos 5)
    print("\nULTIMOS 5 PRECIOS:")
    for i in range(-5, 0):
        row = df.iloc[i]
        time_str = row['close_time'].strftime("%H:%M")
        print(f"   {time_str}: ${row['close']:.2f} (RSI: {row['RSI14']:.1f})")
    
    print("\n" + "="*80)
    print("Actualizando cada 30 segundos... (Ctrl+C para salir)")
    print("="*80)

def main():
    """Función principal"""
    print("Iniciando monitor del bot desde consola...")
    print("Presiona Ctrl+C para detener")
    
    try:
        while True:
            # Obtener datos
            df, client = get_market_data()
            
            if df is not None and client is not None:
                # Detectar señal
                signal, signal_text = detect_signal(df)
                
                # Obtener balance
                usdt_balance, btc_balance = get_balance_info(client)
                
                # Mostrar estado
                print_status(df, signal, signal_text, usdt_balance, btc_balance)
            
            # Esperar 30 segundos
            time.sleep(30)
            
    except KeyboardInterrupt:
        print("\n\nMonitor detenido por el usuario")
    except Exception as e:
        print(f"\nError en el monitor: {e}")

if __name__ == "__main__":
    main()
