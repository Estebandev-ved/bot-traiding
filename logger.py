"""
Sistema de Logging Persistente para Bot de Trading
Incluye rotación de archivos y historial de trades
"""

import logging
from logging.handlers import RotatingFileHandler
import json
import os
from datetime import datetime
from typing import Dict, List, Optional


# Configuración de directorios
LOGS_DIR = 'logs'
TRADES_FILE = 'trades_history.json'


def setup_logging(log_level: str = 'INFO') -> logging.Logger:
    """
    Configura el sistema de logging con rotación de archivos.
    
    Args:
        log_level: Nivel de logging ('DEBUG', 'INFO', 'WARNING', 'ERROR')
    
    Returns:
        Logger configurado
    """
    # Crear directorio de logs si no existe
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR)
    
    # Logger principal
    logger = logging.getLogger('TradingBot')
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Evitar duplicados
    if logger.handlers:
        return logger
    
    # Formato de log
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler para archivo general (rotación 10MB, mantener 5)
    file_handler = RotatingFileHandler(
        os.path.join(LOGS_DIR, 'bot.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # Handler para errores (archivo separado)
    error_handler = RotatingFileHandler(
        os.path.join(LOGS_DIR, 'errors.log'),
        maxBytes=5*1024*1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    
    # Handler para consola
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Agregar handlers
    logger.addHandler(file_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)
    
    logger.info("Sistema de logging inicializado")
    return logger


class TradesHistory:
    """
    Gestiona el historial de trades en archivo JSON.
    """
    
    def __init__(self, filename: str = TRADES_FILE):
        self.filename = os.path.join(LOGS_DIR, filename)
        self.trades: List[Dict] = []
        self._load()
    
    def _load(self):
        """Carga historial desde archivo"""
        if not os.path.exists(LOGS_DIR):
            os.makedirs(LOGS_DIR)
            
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    self.trades = json.load(f)
            except Exception as e:
                print(f"Error cargando historial: {e}")
                self.trades = []
    
    def _save(self):
        """Guarda historial en archivo"""
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(self.trades, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando historial: {e}")
    
    def add_trade(self, trade: Dict):
        """Agrega un trade al historial"""
        trade['timestamp'] = datetime.now().isoformat()
        trade['id'] = len(self.trades) + 1
        self.trades.append(trade)
        self._save()
    
    def get_recent_trades(self, count: int = 10) -> List[Dict]:
        """Retorna los últimos N trades"""
        return self.trades[-count:]
    
    def get_all_trades(self) -> List[Dict]:
        """Retorna todos los trades"""
        return self.trades
    
    def get_trades_by_date(self, start_date: str, end_date: Optional[str] = None) -> List[Dict]:
        """Filtra trades por fecha"""
        result = []
        for trade in self.trades:
            trade_date = trade.get('timestamp', '')[:10]
            if trade_date >= start_date:
                if end_date is None or trade_date <= end_date:
                    result.append(trade)
        return result
    
    def get_summary(self) -> Dict:
        """Retorna resumen del historial"""
        if not self.trades:
            return {'total_trades': 0, 'total_profit': 0}
        
        total_profit = sum(t.get('profit', 0) for t in self.trades)
        wins = sum(1 for t in self.trades if t.get('profit', 0) > 0)
        losses = sum(1 for t in self.trades if t.get('profit', 0) < 0)
        
        return {
            'total_trades': len(self.trades),
            'wins': wins,
            'losses': losses,
            'win_rate': wins / len(self.trades) * 100 if self.trades else 0,
            'total_profit': total_profit,
            'avg_profit': total_profit / len(self.trades) if self.trades else 0
        }


# Instancia global del logger
def get_logger() -> logging.Logger:
    """Obtiene o crea el logger global"""
    return setup_logging()


# Funciones de conveniencia
def log_trade(action: str, symbol: str, quantity: float, price: float, **kwargs):
    """Log de operación de trading"""
    logger = get_logger()
    msg = f"TRADE | {action} | {symbol} | Qty: {quantity} | Price: ${price:.2f}"
    if kwargs:
        extras = " | ".join(f"{k}: {v}" for k, v in kwargs.items())
        msg += f" | {extras}"
    logger.info(msg)


def log_signal(signal_type: str, confidence: float, details: Dict):
    """Log de señal detectada"""
    logger = get_logger()
    logger.info(f"SIGNAL | {signal_type} | Confidence: {confidence:.2%} | {details}")


def log_error(module: str, error: Exception, context: str = ""):
    """Log de error"""
    logger = get_logger()
    logger.error(f"ERROR | {module} | {error} | Context: {context}")
