from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_LIMIT, TIME_IN_FORCE_GTC
from binance.client import Client
import numpy as np
import talib
import time
import logging

# ===============
# Configuración de logs
# ======================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ======================
# Configuración API Testnet
# ======================
API_KEY = "KNxLm7U9BSCcCLtkW436TMLvi0Mko8PLNDtfiTXjPeEp6XWbBbx6b2COEEJEjIKx"
API_SECRET = "Iju5h8l5Es0LNmvJoGErwuZR7a5XZaMvFsaPIzqBcNL8DtDxrNU7vnfEQ3wFoQdR"

client = Client(API_KEY, API_SECRET, testnet=True)
client.API_URL = "https://testnet.binancefuture.com/fapi"

# ======================
# Funciones de datos reales
# ======================
def get_balance(asset):
    balances = client.futures_account_balance()
    for b in balances:
        if b['asset'] == asset:
            return float(b['balance'])
    return 0.0

def get_last_price(symbol="BNBUSDT"):
    ticker = client.futures_symbol_ticker(symbol=symbol)
    return float(ticker['price'])

def calculate_rsi(symbol="BNBUSDT", interval="1m", period=14):
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=100)
    closes = np.array([float(k[4]) for k in klines], dtype=float)
    rsi = talib.RSI(closes, timeperiod=period)[-1]
    return rsi, closes[-1]

# ======================
# Órdenes escalonadas reales en testnet
# ======================
def place_sell_orders(symbol, quantity, base_price):
    for i in range(3):
        sell_price = round(base_price * (1 + 0.02 * i), 2)
        try:
            order = client.futures_create_order(
                symbol=symbol,
                side=SIDE_SELL,
                type=ORDER_TYPE_LIMIT,
                timeInForce=TIME_IN_FORCE_GTC,
                quantity=quantity,
                price=sell_price
            )
            logging.info(f"📤 Venta {i+1}: {quantity:.6f} {symbol} a {sell_price} USDT | Orden ID: {order['orderId']}")
        except Exception as e:
            logging.warning(f"⚠️ Error al colocar venta {i+1}: {e}")
            break

def place_buy_orders(symbol, quantity, base_price):
    for i in range(3):
        buy_price = round(base_price * (1 - 0.03 * i), 2)
        try:
            order = client.futures_create_order(
                symbol=symbol,
                side=SIDE_BUY,
                type=ORDER_TYPE_LIMIT,
                timeInForce=TIME_IN_FORCE_GTC,
                quantity=quantity,
                price=buy_price
            )
            logging.info(f"📥 Compra {i+1}: {quantity:.6f} {symbol} a {buy_price} USDT | Orden ID: {order['orderId']}")
        except Exception as e:
            logging.warning(f"⚠️ Error al colocar compra {i+1}: {e}")
            break

# ======================
# Estrategia principal
# ======================
def trade(symbol="BNBUSDT"):
    bnb_balance = get_balance("BNB")
    usdt_balance = get_balance("USDT")

    logging.info(f"🔍 Saldo actual: BNB={bnb_balance:.6f}, USDT={usdt_balance:.2f}")

    rsi, last_price = calculate_rsi(symbol)
    logging.info(f"📊 RSI={rsi:.2f} | Último precio={last_price:.2f}")

    if bnb_balance > 0.001:
        sell_quantity = round(bnb_balance / 2, 3)
        place_sell_orders(symbol, sell_quantity, last_price)

    if usdt_balance > 5 and rsi < 30:
        buy_quantity = round((usdt_balance / last_price) / 2, 3)
        place_buy_orders(symbol, buy_quantity, last_price)

# ======================
# Loop principal
# ======================
if __name__ == "__main__":
    while True:
        try:
            trade()
        except Exception as e:
            logging.error(f"⚠️ Error: {e}")
        time.sleep(5)