"""
Módulo de Trailing Stop para Bot de Trading
Gestiona stop-loss dinámico que sigue el precio
"""

from binance.client import Client
from typing import Optional, Dict
import time


class TrailingStopManager:
    """
    Gestiona trailing stops para posiciones abiertas.
    El trailing stop sube cuando el precio sube, pero nunca baja.
    """
    
    def __init__(self, client: Client, symbol: str, trailing_pct: float = 0.02, 
                 activation_pct: float = 0.01):
        """
        Args:
            client: Cliente de Binance
            symbol: Par de trading (ej: BTCUSDT)
            trailing_pct: Porcentaje de trailing (0.02 = 2%)
            activation_pct: Porcentaje de ganancia para activar trailing (0.01 = 1%)
        """
        self.client = client
        self.symbol = symbol
        self.trailing_pct = trailing_pct
        self.activation_pct = activation_pct
        
        # Estado de la posición
        self.entry_price: Optional[float] = None
        self.quantity: Optional[float] = None
        self.highest_price: Optional[float] = None
        self.trailing_stop_price: Optional[float] = None
        self.is_active: bool = False
        self.trailing_activated: bool = False
    
    def open_position(self, entry_price: float, quantity: float):
        """Registra una nueva posición abierta"""
        self.entry_price = entry_price
        self.quantity = quantity
        self.highest_price = entry_price
        self.trailing_stop_price = entry_price * (1 - self.trailing_pct)
        self.is_active = True
        self.trailing_activated = False
        print(f"[TRAILING] Posición abierta: {quantity} @ ${entry_price:.2f}")
        print(f"[TRAILING] Stop inicial: ${self.trailing_stop_price:.2f}")
    
    def update(self, current_price: float) -> Dict:
        """
        Actualiza el trailing stop basado en el precio actual.
        
        Returns:
            Dict con 'action' ('HOLD', 'STOP_HIT'), 'stop_price', 'profit_pct'
        """
        if not self.is_active or self.entry_price is None:
            return {'action': 'NO_POSITION', 'stop_price': None, 'profit_pct': 0}
        
        profit_pct = (current_price - self.entry_price) / self.entry_price
        
        # Verificar si el precio tocó el stop
        if current_price <= self.trailing_stop_price:
            print(f"[TRAILING] ¡STOP HIT! Precio: ${current_price:.2f} <= Stop: ${self.trailing_stop_price:.2f}")
            return {
                'action': 'STOP_HIT',
                'stop_price': self.trailing_stop_price,
                'profit_pct': profit_pct,
                'exit_price': current_price
            }
        
        # Activar trailing si el precio subió lo suficiente
        if not self.trailing_activated and profit_pct >= self.activation_pct:
            self.trailing_activated = True
            print(f"[TRAILING] Trailing ACTIVADO con ganancia de {profit_pct*100:.2f}%")
        
        # Actualizar highest price y trailing stop
        if current_price > self.highest_price:
            self.highest_price = current_price
            
            if self.trailing_activated:
                new_stop = current_price * (1 - self.trailing_pct)
                if new_stop > self.trailing_stop_price:
                    old_stop = self.trailing_stop_price
                    self.trailing_stop_price = new_stop
                    print(f"[TRAILING] Stop actualizado: ${old_stop:.2f} -> ${new_stop:.2f}")
        
        return {
            'action': 'HOLD',
            'stop_price': self.trailing_stop_price,
            'profit_pct': profit_pct,
            'highest_price': self.highest_price,
            'trailing_activated': self.trailing_activated
        }
    
    def close_position(self):
        """Cierra la posición y resetea el estado"""
        result = {
            'entry_price': self.entry_price,
            'quantity': self.quantity,
            'highest_price': self.highest_price,
            'final_stop': self.trailing_stop_price
        }
        
        self.entry_price = None
        self.quantity = None
        self.highest_price = None
        self.trailing_stop_price = None
        self.is_active = False
        self.trailing_activated = False
        
        print("[TRAILING] Posición cerrada")
        return result
    
    def execute_market_sell(self) -> Optional[Dict]:
        """Ejecuta venta a mercado cuando se activa el stop"""
        if not self.is_active or self.quantity is None:
            return None
        
        try:
            order = self.client.create_order(
                symbol=self.symbol,
                side=Client.SIDE_SELL,
                type=Client.ORDER_TYPE_MARKET,
                quantity=str(self.quantity)
            )
            print(f"[TRAILING] Orden de venta ejecutada: {order}")
            self.close_position()
            return order
        except Exception as e:
            print(f"[TRAILING] Error ejecutando venta: {e}")
            return None
    
    def get_status(self) -> Dict:
        """Retorna el estado actual del trailing stop"""
        if not self.is_active:
            return {'is_active': False}
        
        return {
            'is_active': True,
            'entry_price': self.entry_price,
            'quantity': self.quantity,
            'highest_price': self.highest_price,
            'current_stop': self.trailing_stop_price,
            'trailing_activated': self.trailing_activated,
            'trailing_pct': self.trailing_pct
        }
