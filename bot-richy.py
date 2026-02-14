"""
BOT DE TRADING ALGORÍTMICO CON CAPA DE IA (COMPLETO, MODULAR)
Activo: BTC/USDT (Binance)
Temporalidad: 1H
Lenguaje: Python 3.x

REQUISITOS (instalar antes):
pip install python-binance pandas numpy pandas_ta scikit-learn openpyxl

USO:
 - Rellena BINANCE_API_KEY y BINANCE_API_SECRET.
 - Ejecuta en entorno seguro. Para pruebas usa Binance Testnet.
 - Este archivo combina: conectividad, cálculo de indicadores, ML (LogisticRegression),
   reglas potenciada (EMA crossover + predicción ML), gestión de riesgo, ejecución,
   backtesting simple y exportación a Excel.

ADVERTENCIAS:
 - Código educativo/demostrativo. Revisa lot sizes, precisiones y comisiones antes de operar.
 - Prueba en testnet y con backtest EXTENSIVO antes de usar con dinero real.
"""

import time
import math
import os
from datetime import datetime
from typing import Tuple, Dict, Any

import pandas as pd
import numpy as np

# Binance client
from binance.client import Client

# Indicadores
import talib

# ML
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
import joblib  # NUEVO: Para guardar y cargar el modelo
MODEL_FILENAME = 'modelo_ia.pkl'

def save_model(model, filename=MODEL_FILENAME):
    """Guarda el modelo entrenado en un archivo."""
    joblib.dump(model, filename)
    print(f"[ML] Modelo guardado en {filename}")

def load_model(filename=MODEL_FILENAME):
    """Carga el modelo desde un archivo si existe."""
    import os
    if os.path.exists(filename):
        print(f"[ML] Cargando modelo desde {filename}...")
        return joblib.load(filename)
    else:
        print(f"[ML] No se encontró modelo guardado. Se entrenará uno nuevo.")
        return None

# Cargar variables de entorno
from dotenv import load_dotenv
load_dotenv('config.env')

# === MÓDULOS PERSONALIZADOS ===
try:
    from logger import get_logger, log_trade, log_signal, log_error, TradesHistory
    from trailing_stop import TrailingStopManager
    from position_manager import PositionManager
    from telegram_notifier import notify_buy, notify_sell, notify_error, get_notifier
    from metrics import PerformanceMetrics
    CUSTOM_MODULES_AVAILABLE = True
    print("[INIT] Módulos personalizados cargados correctamente")
except ImportError as e:
    CUSTOM_MODULES_AVAILABLE = False
    print(f"[INIT] Algunos módulos no están disponibles: {e}")

# -----------------------------
# CONFIGURACIÓN GLOBAL (DESDE .ENV)
# -----------------------------
# Cargar configuración desde variables de entorno
TRADING_MODE = os.getenv('TRADING_MODE', 'testnet').lower()

# API Keys según el modo de operación
if TRADING_MODE == 'testnet':
    BINANCE_API_KEY = os.getenv('BINANCE_TESTNET_API_KEY', 'TU_API_KEY_AQUI')
    BINANCE_API_SECRET = os.getenv('BINANCE_TESTNET_API_SECRET', 'TU_API_SECRET_AQUI')
    print("[CONFIG] Modo TESTNET activado - Usando claves de prueba")
else:
    BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', 'TU_API_KEY_AQUI')
    BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', 'TU_API_SECRET_AQUI')
    print("[CONFIG] Modo LIVE activado - Usando claves reales")

# Configuración de trading desde .env
SYMBOL = os.getenv('SYMBOL', 'BTCUSDT')
INTERVAL = os.getenv('INTERVAL', '1h')  # Usar string directamente
LOOKBACK_BARS = int(os.getenv('LOOKBACK_BARS', '1200'))
RISK_PER_TRADE = float(os.getenv('RISK_PER_TRADE', '0.02'))
STOP_LOSS_PCT = float(os.getenv('STOP_LOSS_PCT', '0.03'))
TAKE_PROFIT_PCT = float(os.getenv('TAKE_PROFIT_PCT', '0.06'))
MIN_USDT_TRADE = float(os.getenv('MIN_USDT_TRADE', '10.0'))
MODEL_RANDOM_STATE = int(os.getenv('MODEL_RANDOM_STATE', '42'))
SLEEP_SECONDS = int(os.getenv('SLEEP_SECONDS', '1800'))  # 30 minutos por defecto
DECIMALS_QTY = int(os.getenv('DECIMALS_QTY', '6'))

# Configuración de Trailing Stop
TRAILING_STOP_ENABLED = os.getenv('TRAILING_STOP_ENABLED', 'true').lower() == 'true'
TRAILING_STOP_PCT = float(os.getenv('TRAILING_STOP_PCT', '0.02'))  # 2% trailing
TRAILING_STOP_ACTIVATION = float(os.getenv('TRAILING_STOP_ACTIVATION', '0.01'))  # Activar después de 1% de ganancia

# Filtros adicionales de entrada
MIN_VOLUME_RATIO = float(os.getenv('MIN_VOLUME_RATIO', '0.8'))  # Volumen mínimo vs promedio
MAX_ATR_PCT = float(os.getenv('MAX_ATR_PCT', '5.0'))  # Volatilidad máxima permitida
MIN_CONFIDENCE = float(os.getenv('MIN_CONFIDENCE', '0.6'))  # Confianza mínima del modelo

# -----------------------------
# MÓDULO: Conexión con Binance
# -----------------------------
def init_binance_client(api_key: str, api_secret: str) -> Client:
    """
    Inicializa y retorna el cliente de Binance (REST).
    Configura automáticamente testnet si está en modo testnet.
    """
    if TRADING_MODE == 'testnet':
        client = Client(api_key, api_secret, testnet=True)
        client.API_URL = "https://testnet.binance.vision/api"  # Testnet URL
        print("[CLIENT] Cliente Binance TESTNET inicializado")
    else:
        client = Client(api_key, api_secret)
        print("[CLIENT] Cliente Binance LIVE inicializado")
    return client

# -----------------------------
# MÓDULO: Obtención y preparación de datos
# -----------------------------
def fetch_klines_to_df(client: Client, symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
    """
    Descarga velas (klines) desde Binance y retorna DataFrame con tipos correctos.
    Index: close_time (fecha/hora cierre vela).
    """
    raw = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    cols = [
        "open_time","open","high","low","close","volume",
        "close_time","quote_asset_volume","number_of_trades",
        "taker_buy_base","taker_buy_quote","ignore"
    ]
    df = pd.DataFrame(raw, columns=cols)
    # Conversiones
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
    numeric_cols = ['open','high','low','close','volume','quote_asset_volume','taker_buy_base','taker_buy_quote']
    df[numeric_cols] = df[numeric_cols].astype(float)
    df = df.set_index('close_time')
    # Mantener solo columnas útiles
    df = df[['open','high','low','close','volume','number_of_trades']]
    return df

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula y agrega indicadores AVANZADOS para mejor predicción:
      - EMAs múltiples (9, 21, 50, 200)
      - RSI (14, 21)
      - MACD
      - Bollinger Bands
      - Stochastic
      - ATR (volatilidad)
      - Volume indicators
      - Price patterns
    """
    df = df.copy()
    # Convertir a numpy arrays para talib
    close_prices = df['close'].values.astype(float)
    high_prices = df['high'].values.astype(float)
    low_prices = df['low'].values.astype(float)
    volume_values = df['volume'].values.astype(float)
    
    # === MEDIAS MÓVILES MÚLTIPLES ===
    df['EMA9'] = talib.EMA(close_prices, timeperiod=9)
    df['EMA21'] = talib.EMA(close_prices, timeperiod=21)
    df['EMA50'] = talib.EMA(close_prices, timeperiod=50)
    df['EMA200'] = talib.EMA(close_prices, timeperiod=200)
    df['SMA20'] = talib.SMA(close_prices, timeperiod=20)
    
    # === RSI MÚLTIPLES ===
    df['RSI14'] = talib.RSI(close_prices, timeperiod=14)
    df['RSI21'] = talib.RSI(close_prices, timeperiod=21)
    
    # === MACD ===
    macd, macd_signal, macd_hist = talib.MACD(close_prices, fastperiod=12, slowperiod=26, signalperiod=9)
    df['MACD'] = macd
    df['MACD_signal'] = macd_signal
    df['MACD_hist'] = macd_hist
    
    # === BOLLINGER BANDS ===
    bb_upper, bb_middle, bb_lower = talib.BBANDS(close_prices, timeperiod=20, nbdevup=2, nbdevdn=2)
    df['BB_upper'] = bb_upper
    df['BB_middle'] = bb_middle
    df['BB_lower'] = bb_lower
    df['BB_width'] = (bb_upper - bb_lower) / bb_middle * 100
    df['BB_position'] = (close_prices - bb_lower) / (bb_upper - bb_lower) * 100
    
    # === STOCHASTIC ===
    stoch_k, stoch_d = talib.STOCH(high_prices, low_prices, close_prices, fastk_period=14, slowk_period=3, slowd_period=3)
    df['STOCH_K'] = stoch_k
    df['STOCH_D'] = stoch_d
    
    # === ATR (VOLATILIDAD) ===
    df['ATR'] = talib.ATR(high_prices, low_prices, close_prices, timeperiod=14)
    df['ATR_pct'] = df['ATR'] / close_prices * 100
    
    # === VOLUME INDICATORS ===
    df['OBV'] = talib.OBV(close_prices, volume_values)
    df['AD'] = talib.AD(high_prices, low_prices, close_prices, volume_values)
    df['volume_sma'] = talib.SMA(volume_values, timeperiod=20)
    df['volume_ratio'] = volume_values / df['volume_sma']
    
    # === PRICE PATTERNS ===
    df['price_change'] = df['close'].pct_change() * 100
    df['price_change_2'] = df['close'].pct_change(2) * 100
    df['price_change_5'] = df['close'].pct_change(5) * 100
    
    # === FEATURES AVANZADAS ===
    df['EMA_diff_pct'] = (df['EMA9'] - df['EMA21']) / df['EMA21'] * 100
    df['EMA_trend'] = (df['EMA9'] - df['EMA50']) / df['EMA50'] * 100
    df['EMA_long_trend'] = (df['EMA21'] - df['EMA200']) / df['EMA200'] * 100
    
    # === MOMENTUM INDICATORS ===
    df['MOM'] = talib.MOM(close_prices, timeperiod=10)
    df['ROC'] = talib.ROC(close_prices, timeperiod=10)
    
    # === VOLATILITY ===
    df['NATR'] = talib.NATR(high_prices, low_prices, close_prices, timeperiod=14)
    
    # === SEÑALES SIMPLES ===
    df['EMA_cross'] = (df['EMA9'] > df['EMA21']).astype(int)
    df['MACD_cross'] = (df['MACD'] > df['MACD_signal']).astype(int)
    df['RSI_oversold'] = (df['RSI14'] < 30).astype(int)
    df['RSI_overbought'] = (df['RSI14'] > 70).astype(int)
    
    # === NORMALIZACIÓN ===
    df['vol_log'] = np.log1p(volume_values)
    df['price_log'] = np.log(close_prices)
    
    # Eliminar filas con NaNs (solo las columnas esenciales)
    required_cols = ['EMA9', 'EMA21', 'RSI14']
    df = df.dropna(subset=required_cols)
    
    # Rellenar NaN con valores por defecto para columnas opcionales
    optional_cols = ['MACD', 'MACD_signal', 'BB_position', 'ATR_pct', 'MOM', 'volume_ratio']
    for col in optional_cols:
        if col in df.columns:
            df[col] = df[col].fillna(df[col].median())
    
    return df

# -----------------------------
# MÓDULO: Preparación de features y labels para ML
# -----------------------------
def prepare_features_labels(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Prepara features AVANZADAS y labels para predicción mejorada:
      - Features: 25+ indicadores técnicos
      - Label: 1 si la próxima vela (t+1) cierra más alto que la actual, else 0
      - Predicción de magnitud del movimiento
    """
    df = df.copy()
    df = df.sort_index()
    
    # === LABELS PRINCIPALES ===
    df['close_next'] = df['close'].shift(-1)
    df = df.dropna(subset=['close_next'])
    
    # Label binario: ¿próxima vela alcista?
    df['target'] = (df['close_next'] > df['close']).astype(int)
    
    # Label de magnitud: ¿qué tan grande será el movimiento?
    df['price_change_next'] = (df['close_next'] - df['close']) / df['close'] * 100
    df['target_magnitude'] = df['price_change_next'].apply(lambda x: 
        2 if x > 1.0 else 1 if x > 0.5 else 0 if x > -0.5 else -1 if x > -1.0 else -2)
    
    # === FEATURES SIMPLIFICADAS (para evitar NaN) ===
    feature_columns = [
        # EMAs básicas
        'EMA_diff_pct', 'EMA_trend',
        # RSI
        'RSI14',
        # MACD básico
        'MACD', 'MACD_signal',
        # Bollinger Bands básico
        'BB_position',
        # Volatilidad básica
        'ATR_pct',
        # Volume básico
        'vol_log', 'volume_ratio',
        # Momentum básico
        'MOM',
        # Price patterns básicos
        'price_change',
        # Señales básicas
        'EMA_cross', 'MACD_cross', 'RSI_oversold', 'RSI_overbought'
    ]
    
    # Filtrar columnas que existen
    available_features = [col for col in feature_columns if col in df.columns]
    X = df[available_features].copy()
    y = df['target'].copy()
    
    # Limpiar datos: eliminar filas con NaN
    mask = ~(X.isna().any(axis=1) | y.isna())
    X = X[mask]
    y = y[mask]
    
    print(f"[ML] Datos limpios: {len(X)} filas, {len(X.columns)} features")
    
    return X, y

# -----------------------------
# MÓDULO: Entrenamiento / Modelo ML
# -----------------------------
def train_ml_model(df: pd.DataFrame, random_state: int = MODEL_RANDOM_STATE) -> Pipeline:
    """
    Entrena un pipeline AVANZADO con múltiples modelos para mejor predicción.
    Usa RandomForest + LogisticRegression para predicciones más inteligentes.
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.ensemble import VotingClassifier
    
    X, y = prepare_features_labels(df)
    print(f"[ML] Entrenando con {len(X.columns)} features: {list(X.columns)}")
    
    # Split temporal
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=random_state, shuffle=False)
    
    # === MODELO AVANZADO SIMPLIFICADO ===
    # Usar solo RandomForest (más robusto con NaN)
    rf_model = RandomForestClassifier(
        n_estimators=50,
        max_depth=8,
        min_samples_split=10,
        min_samples_leaf=5,
        random_state=random_state,
        n_jobs=1  # Evitar problemas de paralelización
    )
    
    # Pipeline completo
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('classifier', rf_model)
    ])
    
    # Entrenar
    pipeline.fit(X_train, y_train)
    
    # Evaluar
    train_score = pipeline.score(X_train, y_train)
    test_score = pipeline.score(X_test, y_test)
    
    print(f"[ML] Entrenado modelo AVANZADO:")
    print(f"[ML] - Features utilizadas: {len(X.columns)}")
    print(f"[ML] - Accuracy (train): {train_score:.4f}")
    print(f"[ML] - Accuracy (test): {test_score:.4f}")
    
    # Mostrar importancia de features
    if hasattr(pipeline.named_steps['classifier'], 'feature_importances_'):
        rf_importance = pipeline.named_steps['classifier'].feature_importances_
        feature_importance = list(zip(X.columns, rf_importance))
        feature_importance.sort(key=lambda x: x[1], reverse=True)
        print(f"[ML] - Top 5 features más importantes:")
        for i, (feature, importance) in enumerate(feature_importance[:5]):
            print(f"[ML]   {i+1}. {feature}: {importance:.4f}")
    
    return pipeline

def predict_ml(model: Pipeline, row: pd.Series) -> dict:
    """
    Predicción AVANZADA que retorna múltiples insights:
    - Predicción binaria (1/0)
    - Probabilidad de acierto
    - Confianza de la predicción
    - Análisis de tendencia
    """
    # Usar EXACTAMENTE las mismas features que se usaron para entrenar
    feature_columns = [
        'EMA_diff_pct', 'EMA_trend', 'RSI14', 'MACD', 'MACD_signal',
        'BB_position', 'ATR_pct', 'vol_log', 'volume_ratio', 'MOM',
        'price_change', 'EMA_cross', 'MACD_cross', 'RSI_oversold', 'RSI_overbought'
    ]
    
    # Filtrar features que existen en la fila
    available_features = [col for col in feature_columns if col in row.index]
    # Pasar como DataFrame para evitar warning de sklearn
    X = pd.DataFrame([row[available_features].values], columns=available_features)
    
    # Predicción binaria
    pred = model.predict(X)[0]
    
    # Probabilidades (si el modelo las soporta)
    try:
        probabilities = model.predict_proba(X)[0]
        confidence = max(probabilities)
    except:
        confidence = 0.5
    
    # Análisis de tendencia
    trend_analysis = analyze_trend(row)
    
    return {
        'prediction': int(pred),
        'confidence': confidence,
        'probability_up': probabilities[1] if 'probabilities' in locals() else 0.5,
        'trend_analysis': trend_analysis,
        'features_used': len(available_features)
    }

def analyze_trend(row: pd.Series) -> dict:
    """
    Analiza la tendencia actual basada en múltiples indicadores
    """
    # Usar valores por defecto si las columnas no existen
    ema_cross = row.get('EMA_cross', 0)
    macd_cross = row.get('MACD_cross', 0)
    rsi14 = row.get('RSI14', 50)
    bb_position = row.get('BB_position', 50)
    atr_pct = row.get('ATR_pct', 0)
    volume_ratio = row.get('volume_ratio', 1)
    
    analysis = {
        'ema_trend': 'ALCISTA' if ema_cross == 1 else 'BAJISTA',
        'macd_trend': 'ALCISTA' if macd_cross == 1 else 'BAJISTA',
        'rsi_status': 'SOBRECOMPRA' if rsi14 > 70 else 'SOBREVENTA' if rsi14 < 30 else 'NEUTRO',
        'bb_position': 'ARRIBA' if bb_position > 80 else 'ABAJO' if bb_position < 20 else 'CENTRO',
        'volatility': 'ALTA' if atr_pct > 2 else 'BAJA',
        'volume': 'ALTO' if volume_ratio > 1.5 else 'NORMAL'
    }
    
    # Score de tendencia general
    score = 0
    if analysis['ema_trend'] == 'ALCISTA': score += 1
    if analysis['macd_trend'] == 'ALCISTA': score += 1
    if analysis['rsi_status'] == 'SOBREVENTA': score += 1
    if analysis['bb_position'] == 'ABAJO': score += 1
    if analysis['volume'] == 'ALTO': score += 1
    
    analysis['trend_score'] = score
    analysis['overall_trend'] = 'MUY_ALCISTA' if score >= 4 else 'ALCISTA' if score >= 3 else 'NEUTRO' if score >= 2 else 'BAJISTA'
    
    return analysis

# -----------------------------
# MÓDULO: Gestión de Riesgos
# -----------------------------
def get_lot_size_filters(client: Client, symbol: str):
    """
    Obtiene los filtros de LOT_SIZE y stepSize para el símbolo dado.
    Retorna: min_qty, max_qty, step_size (todos float)
    """
    info = client.get_symbol_info(symbol)
    for f in info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            min_qty = float(f['minQty'])
            max_qty = float(f['maxQty'])
            step_size = float(f['stepSize'])
            return min_qty, max_qty, step_size
    # Valores por defecto si no se encuentra
    return 0.00001, 1000, 0.00001

def calculate_position_size(account_balance_usdt: float, entry_price: float, stop_loss_pct: float, risk_per_trade: float, min_qty: float, max_qty: float, step_size: float) -> float:
    """
    Calcula la cantidad (qty) del activo a comprar basada en riesgo fijo por operación y respeta LOT_SIZE/stepSize.
    """
    riesgo_monetario = account_balance_usdt * risk_per_trade
    perdida_unidad = entry_price * stop_loss_pct
    if perdida_unidad <= 0:
        return 0.0
    qty = riesgo_monetario / perdida_unidad
    # Ajustar a step_size
    precision = int(round(-math.log10(step_size)))
    qty = math.floor(qty / step_size) * step_size
    qty = round(qty, precision)
    # Respetar min/max
    if qty < min_qty or qty > max_qty or qty * entry_price < MIN_USDT_TRADE or qty <= 0:
        return 0.0
    return qty

# -----------------------------
# MÓDULO: Ejecución de órdenes (Binance)
# -----------------------------
def execute_buy_market(client: Client, symbol: str, quantity: float, min_qty: float, max_qty: float, step_size: float) -> Dict[str, Any]:
    """
    Ejecuta orden market BUY ajustando la cantidad a los filtros de Binance.
    """
    if quantity <= 0:
        raise ValueError("Quantity must be > 0")
    # Ajustar cantidad a step_size
    precision = int(round(-math.log10(step_size)))
    quantity = math.floor(quantity / step_size) * step_size
    quantity = round(quantity, precision)
    if quantity < min_qty or quantity > max_qty:
        raise ValueError(f"Quantity {quantity} fuera de los límites permitidos por Binance.")
    print(f"[EXEC] Ejecutando MARKET BUY {quantity} de {symbol}")
    order = client.create_order(
        symbol=symbol,
        side=Client.SIDE_BUY,
        type=Client.ORDER_TYPE_MARKET,
        quantity=str(quantity)
    )
    return order

def place_oco_tp_sl(client: Client, symbol: str, quantity: float, entry_price: float, stop_loss_pct: float, take_profit_pct: float) -> Dict[str, Any]:
    """
    Coloca OCO (Take Profit + Stop Loss).
    Nota: los parámetros concretos pueden variar según versiones de API; revisar documentación.
    En caso de error retorna {}.
    """
    price_tp = entry_price * (1 + take_profit_pct)
    stop_price = entry_price * (1 - stop_loss_pct)
    stop_limit_price = stop_price * 0.999  # pequeño margen
    try:
        oco = client.create_oco_order(
            symbol=symbol,
            side=Client.SIDE_SELL,
            price=f"{price_tp:.2f}",
            quantity=f"{quantity:.6f}",
            stopPrice=f"{stop_price:.2f}",
            stopLimitPrice=f"{stop_limit_price:.2f}",
            stopLimitTimeInForce='GTC'
        )
        return oco
    except Exception as e:
        print(f"[EXEC] Error creando OCO: {e}")
        return {}

def get_balance_usdt(client: Client) -> float:
    """
    Retorna balance libre de USDT en la cuenta. Si no lo encuentra retorna 0.
    """
    try:
        account = client.get_account()
        for asset in account.get('balances', []):
            if asset.get('asset') == 'USDT':
                return float(asset.get('free', 0.0))
    except Exception as e:
        print(f"[EXEC] Error obteniendo balance: {e}")
    return 0.0

# -----------------------------
# MÓDULO: Señal tradicional (EMA crossover)
# -----------------------------
def ema_crossover_signal(df: pd.DataFrame) -> int:
    """
    Detecta cruce entre EMA9 y EMA21 en las dos últimas velas:
      - retorna 1 si hay cruce alcista (EMA9 cruza por encima EMA21)
      - retorna -1 si hay cruce bajista
      - 0 si no hay cruce
    """
    if len(df) < 2:
        return 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    # Cruce alcista
    if (prev['EMA9'] <= prev['EMA21']) and (last['EMA9'] > last['EMA21']):
        return 1
    # Cruce bajista
    if (prev['EMA9'] >= prev['EMA21']) and (last['EMA9'] < last['EMA21']):
        return -1
    return 0

# -----------------------------
# MÓDULO: Backtest simple integrado con IA
# -----------------------------
def simple_backtest_with_ml(df: pd.DataFrame, model: Pipeline, client: Client, initial_balance: float = 1000.0) -> pd.DataFrame:
    """
    Backtest simplificado:
      - Entrada: cruce alcista EMA (en close de vela i) AND modelo predice próxima vela alcista (sobre la fila i)
      - Salida: TP o SL o cierre por timeout (ej. después de N velas)
      - Calcula P&L por operación y actualiza balance
    Retorna DataFrame con trades realizados.
    """
    df = df.copy().sort_index()
    X, _ = prepare_features_labels(df)
    # Predecir para todas las filas (predice próxima vela)
    preds = model.predict(X)
    # Alinear preds con df (eliminar la última fila ya que no tiene target)
    df = df.iloc[:len(preds)].copy()
    df['ml_pred'] = preds
    trades = []
    balance = initial_balance
    position = None  # None o dict con entry, qty, entry_index, stop_price, tp_price
    max_lookahead = 48  # cuántas velas mirar para TP/SL
    for i in range(1, len(df)-1):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        # Detectar cruce alcista en i (usando prev y curr)
        cross = 0
        if (prev['EMA9'] <= prev['EMA21']) and (row['EMA9'] > row['EMA21']):
            cross = 1
        # Si no hay posición, evaluar entrada
        if position is None and cross == 1 and row['ml_pred'] == 1:
            entry_price = row['close']
            min_qty, max_qty, step_size = get_lot_size_filters(client, SYMBOL)
            qty = calculate_position_size(balance, entry_price, STOP_LOSS_PCT, RISK_PER_TRADE, min_qty, max_qty, step_size)
            if qty <= 0:
                continue
            stop_price = entry_price * (1 - STOP_LOSS_PCT)
            tp_price = entry_price * (1 + TAKE_PROFIT_PCT)
            # Simular el seguimiento para ver si se alcanza TP o SL
            exit_price = None
            exit_reason = None
            for j in range(i+1, min(i+1+max_lookahead, len(df))):
                low_j = df.iloc[j]['low']
                high_j = df.iloc[j]['high']
                if low_j <= stop_price:
                    exit_price = stop_price
                    exit_reason = 'SL'
                    break
                if high_j >= tp_price:
                    exit_price = tp_price
                    exit_reason = 'TP'
                    break
            if exit_price is None:
                # cerrar en la última observación del window
                exit_price = df.iloc[min(i+max_lookahead, len(df)-1)]['close']
                exit_reason = 'TIMEOUT_CLOSE'
            profit = (exit_price - entry_price) * qty
            balance += profit
            trades.append({
                'entry_index': i,
                'entry_time': row.name,
                'entry_price': entry_price,
                'qty': qty,
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'profit': profit,
                'balance_after': balance
            })
            # No mantenemos posición entre iteraciones (simulación instantánea)
    trades_df = pd.DataFrame(trades)
    print(f"[BACKTEST] Operaciones: {len(trades_df)}  Balance final: {balance:.2f}")
    return trades_df

# -----------------------------
# MÓDULO: Loop Principal (Realtime/demo)
# -----------------------------
def main_loop():
    """
    Bucle principal real-time (ejecuta iterativamente):
      - descarga datos
      - calcula indicadores
      - detecta señales EMA crossover
      - predice con ML
      - solo ejecuta BUY si (EMA_cross bullish) AND (ML predicts bullish)
      - calcula tamaño según gestión de riesgo y coloca orden market + OCO TP/SL
    IMPORTANTE: En producción inclúir robustez (logs, retries, rate-limit handling, testnet).
    """
    client = init_binance_client(BINANCE_API_KEY, BINANCE_API_SECRET)
    print("[MAIN] Cliente Binance inicializado.")
    # Datos iniciales + entrenamiento
    df = fetch_klines_to_df(client, SYMBOL, INTERVAL, LOOKBACK_BARS)
    df = compute_indicators(df)
    model = load_model()
    if model is None:
        model = train_ml_model(df)
        save_model(model)
    print("[MAIN] Modelo ML listo. Iniciando loop.")
    
    # Contador para re-entrenamiento
    iteration_count = 0
    retrain_interval = 10  # Re-entrenar cada 10 iteraciones (5 horas)
    
    try:
        while True:
            iteration_count += 1
            # 1) actualizar datos
            df = fetch_klines_to_df(client, SYMBOL, INTERVAL, LOOKBACK_BARS)
            df = compute_indicators(df)
            # 2) señal EMA
            signal = ema_crossover_signal(df)
            print(f"[MAIN] {datetime.utcnow().isoformat()} - Señal EMA: {signal}")
            # 3) features última fila y predicción AVANZADA
            last = df.iloc[-1]
            try:
                ml_result = predict_ml(model, last)
                ml_pred = ml_result['prediction']
                confidence = ml_result['confidence']
                trend_analysis = ml_result['trend_analysis']
                
                print(f"[MAIN] Predicción ML próxima vela: {ml_pred}")
                print(f"[MAIN] Confianza: {confidence:.2%}")
                print(f"[MAIN] Tendencia general: {trend_analysis['overall_trend']}")
                print(f"[MAIN] Score tendencia: {trend_analysis['trend_score']}/5")
                print(f"[MAIN] RSI: {trend_analysis['rsi_status']}, Volatilidad: {trend_analysis['volatility']}")
            except Exception as e:
                print(f"[MAIN] Error en predicción ML: {e}")
                ml_pred = 0
                confidence = 0.5
                trend_analysis = {'overall_trend': 'ERROR', 'trend_score': 0, 'rsi_status': 'ERROR', 'volatility': 'ERROR'}
            
            # 4) Verificar filtros adicionales
            volume_ok = last.get('volume_ratio', 1) >= MIN_VOLUME_RATIO if 'volume_ratio' in last.index else True
            volatility_ok = last.get('ATR_pct', 0) <= MAX_ATR_PCT if 'ATR_pct' in last.index else True
            
            # 5) Regla potenciada MEJORADA: ejecutar solo si señal alcista y ML confirma con alta confianza
            if signal == 1 and ml_pred == 1 and confidence > MIN_CONFIDENCE and volume_ok and volatility_ok:
                print("[MAIN] Condición cumplida: EMA bullish y ML confirma alcista -> evaluando ejecución")
                
                # Verificar si ya hay posición abierta
                if CUSTOM_MODULES_AVAILABLE:
                    position_mgr = PositionManager(client, SYMBOL)
                    if position_mgr.has_open_position():
                        print("[MAIN] Ya hay una posición abierta. Saltando...")
                        continue
                
                balance_usdt = get_balance_usdt(client)
                print(f"[MAIN] Balance USDT disponible: {balance_usdt:.2f}")
                entry_price = last['close']  # aproximación
                # Obtener filtros de lot size
                min_qty, max_qty, step_size = get_lot_size_filters(client, SYMBOL)
                qty = calculate_position_size(balance_usdt, entry_price, STOP_LOSS_PCT, RISK_PER_TRADE, min_qty, max_qty, step_size)
                if qty <= 0:
                    print("[MAIN] Tamaño calculado insuficiente o menor al mínimo. No se ejecutará orden.")
                else:
                    # Calcular precios de SL y TP
                    stop_loss_price = entry_price * (1 - STOP_LOSS_PCT)
                    take_profit_price = entry_price * (1 + TAKE_PROFIT_PCT)
                    
                    # Ejecutar market buy
                    order = execute_buy_market(client, SYMBOL, qty, min_qty, max_qty, step_size)
                    print(f"[MAIN] Orden BUY ejecutada: {order}")
                    
                    # Registrar posición y notificar
                    if CUSTOM_MODULES_AVAILABLE:
                        position_mgr.open_position(entry_price, qty, stop_loss_price, take_profit_price)
                        notify_buy(SYMBOL, qty, entry_price, stop_loss_price, take_profit_price, confidence)
                        log_trade("BUY", SYMBOL, qty, entry_price, confidence=f"{confidence:.2%}")
                    
                    # Colocar OCO TP/SL
                    oco = place_oco_tp_sl(client, SYMBOL, qty, entry_price, STOP_LOSS_PCT, TAKE_PROFIT_PCT)
                    print(f"[MAIN] OCO colocada: {oco}")
                    
                    # Iniciar trailing stop si está habilitado
                    if CUSTOM_MODULES_AVAILABLE and TRAILING_STOP_ENABLED:
                        trailing_mgr = TrailingStopManager(client, SYMBOL, TRAILING_STOP_PCT, TRAILING_STOP_ACTIVATION)
                        trailing_mgr.open_position(entry_price, qty)
            elif not volume_ok:
                print(f"[MAIN] Volumen insuficiente (ratio: {last.get('volume_ratio', 'N/A')})")
            elif not volatility_ok:
                print(f"[MAIN] Volatilidad muy alta (ATR%: {last.get('ATR_pct', 'N/A')})")
            else:
                print("[MAIN] No se cumplen condiciones (o señal bajista).")
            
            # RE-ENTRENAMIENTO AUTOMÁTICO
            if iteration_count % retrain_interval == 0:
                print(f"[MAIN] Re-entrenando modelo (iteración {iteration_count})...")
                try:
                    model = train_ml_model(df)
                    save_model(model)
                    print("[MAIN] Modelo re-entrenado y guardado con datos actualizados.")
                except Exception as e:
                    print(f"[MAIN] Error re-entrenando modelo: {e}")
            
            # Esperar antes de la próxima iteración
            print(f"[MAIN] Durmiendo {SLEEP_SECONDS} segundos...")
            time.sleep(SLEEP_SECONDS)
    except KeyboardInterrupt:
        print("[MAIN] Interrumpido por usuario. Saliendo.")
    except Exception as e:
        print(f"[MAIN] Error en loop principal: {e}")

# -----------------------------
# MÓDULO: Exportación a Excel
# -----------------------------
def export_to_excel(df: pd.DataFrame, filename: str = "export.xlsx"):
    """
    Exporta DataFrame a Excel para análisis.
    """
    df.to_excel(filename, index=False)
    print(f"[EXPORT] Exportado: {filename}")

# -----------------------------
# EJECUTABLE / DEMO
# -----------------------------
if __name__ == "__main__":
    """
    Ejecución demo:
      1) Inicializa cliente
      2) Descarga datos y calcula indicadores
      3) Entrena el modelo ML
      4) Ejecuta backtest simple con IA
      5) Exporta resultados
      6) (Opcional) main_loop() - descomenta para correr en tiempo real (advertencia: real trading)
    """
    # INICIALIZAR CLIENTE (usa testnet si estás probando con dinero ficticio)
    client = init_binance_client(BINANCE_API_KEY, BINANCE_API_SECRET)
    print("[DEMO] Cliente Binance inicializado (demo).")

    # DESCARGAR DATOS HISTÓRICOS
    df_hist = fetch_klines_to_df(client, SYMBOL, INTERVAL, LOOKBACK_BARS)
    df_hist = compute_indicators(df_hist)
    print("[DEMO] Indicadores calculados sobre histórico.")

    # CARGAR O ENTRENAR MODELO ML
    model_pipeline = load_model()
    if model_pipeline is None:
        model_pipeline = train_ml_model(df_hist)
        save_model(model_pipeline)
    else:
        print("[DEMO] Modelo ML cargado correctamente.")

    # BACKTEST SIMPLE INTEGRADO CON IA
    trades_df = simple_backtest_with_ml(df_hist, model_pipeline, client, initial_balance=1000.0)
    if not trades_df.empty:
        print("[DEMO] Primeras operaciones del backtest:")
        print(trades_df.head())

    # EXPORTAR RESULTADOS A EXCEL
    export_to_excel(trades_df, filename="backtest_trades_with_ml.xlsx")

    # PARA EJECUTAR EN TIEMPO REAL: descomenta la siguiente línea (advertencia: real trading)
    print("\n" + "="*60)
    print("INICIANDO MODO TRADING EN VIVO (TESTNET)")
    print("="*60)
    print("El bot ahora operara en tiempo real en Binance Testnet")
    print(f"Monitoreando senales cada {SLEEP_SECONDS} segundos...")
    print("Presiona Ctrl+C para detener el bot")
    print("="*60 + "\n")
    
    main_loop()

"""
EXPLICACIÓN RÁPIDA DE LA POTENCIACIÓN CON IA (resumida):
 - El modelo (LogisticRegression) aprende a predecir si la "próxima" vela será alcista (1) o bajista (0)
   usando features sencillas: diferencia porcentual entre EMAs, volumen logarítmico y RSI(14).
 - La regla de ejecución potenciada requiere que:
     * Haya un cruce alcista EMA (9 sobre 26) y
     * El modelo ML prediga clase 1 (alcista)
   Solo cuando ambas condiciones se cumplen se evalúa el tamaño y se ejecuta la orden.
 - La gestión de riesgos calcula la cantidad en base a 2% del balance como riesgo máximo y un SL del 3%.
 - El backtest simula entradas y revisa si en las velas siguientes se alcanza TP (6%) o SL (3%) para medir P&L.

SUGERENCIAS DE MEJORA (futuro):
 - Usar modelos más complejos (RandomForest/XGBoost/Redes) y validación temporal (time-series CV).
 - Incluir features adicionales (ordenes del libro, volatilidad, medias múltiples, derivados de volumen).
 - Implementar reentrenamiento periódico (online learning) y monitor de drift.
 - Manejar lot-size según reglas del exchange (LOT_SIZE, stepSize) y fees/slippage.
 - Añadir logs persistentes, alertas y backtests más exhaustivos (simular comisiones, slippage, spreads).

LECTURA/PRUEBAS:
 - Probar en Binance Testnet antes de operar en real.
 - Ajustar LOOKBACK_BARS, SLEEP_SECONDS y parámetros de gestión de riesgo según tu perfil.
"""
