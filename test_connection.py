#!/usr/bin/env python3
"""
Script para probar la conexión con Binance Testnet
"""

from binance.client import Client
from dotenv import load_dotenv
import os

# Cargar variables de entorno
load_dotenv('config.env')

def test_testnet_connection():
    """Prueba la conexión con Binance Testnet"""
    try:
        # Inicializar cliente testnet
        api_key = os.getenv('BINANCE_TESTNET_API_KEY')
        api_secret = os.getenv('BINANCE_TESTNET_API_SECRET')
        
        print(f"API Key: {api_key[:10]}...")
        print(f"API Secret: {api_secret[:10]}...")
        
        client = Client(api_key, api_secret, testnet=True)
        client.API_URL = "https://testnet.binance.vision/api"
        
        print("Cliente testnet inicializado")
        
        # Probar conexión obteniendo información de la cuenta
        account = client.get_account()
        print("Conexion con testnet exitosa")
        
        # Mostrar balances
        print("\nBALANCES EN TESTNET:")
        for balance in account['balances']:
            if float(balance['free']) > 0:
                print(f"  {balance['asset']}: {balance['free']}")
        
        # Probar obtención de datos de mercado
        ticker = client.get_symbol_ticker(symbol="BTCUSDT")
        print(f"\nPrecio BTC/USDT: {ticker['price']} USDT")
        
        return True
        
    except Exception as e:
        print(f"Error de conexion: {e}")
        return False

if __name__ == "__main__":
    print("PROBANDO CONEXION CON BINANCE TESTNET")
    print("="*50)
    
    if test_testnet_connection():
        print("\nConexion exitosa! El bot puede operar en testnet.")
    else:
        print("\nError de conexion. Revisa las API keys.")
