"""
Gestor de Posiciones para Bot de Trading
Rastrea posiciones abiertas y órdenes pendientes
"""

import json
import os
from typing import Optional, Dict, List
from datetime import datetime
from binance.client import Client


POSITIONS_FILE = 'positions_state.json'


class PositionManager:
    """
    Gestiona el estado de posiciones abiertas y órdenes pendientes.
    Persiste el estado en archivo JSON para recuperación ante reinicios.
    """
    
    def __init__(self, client: Client, symbol: str, state_file: str = POSITIONS_FILE):
        self.client = client
        self.symbol = symbol
        self.state_file = state_file
        
        # Estado de posición
        self.position: Optional[Dict] = None
        self.pending_orders: List[Dict] = []
        
        # Cargar estado previo si existe
        self._load_state()
    
    def _load_state(self):
        """Carga el estado desde archivo JSON"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.position = state.get('position')
                    self.pending_orders = state.get('pending_orders', [])
                    print(f"[POSITION] Estado cargado: {self.position}")
            except Exception as e:
                print(f"[POSITION] Error cargando estado: {e}")
    
    def _save_state(self):
        """Guarda el estado en archivo JSON"""
        try:
            state = {
                'position': self.position,
                'pending_orders': self.pending_orders,
                'last_update': datetime.now().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"[POSITION] Error guardando estado: {e}")
    
    def has_open_position(self) -> bool:
        """Verifica si hay una posición abierta"""
        return self.position is not None
    
    def open_position(self, entry_price: float, quantity: float, 
                      stop_loss: float, take_profit: float,
                      order_id: Optional[str] = None):
        """Registra una nueva posición abierta"""
        self.position = {
            'entry_price': entry_price,
            'quantity': quantity,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'entry_time': datetime.now().isoformat(),
            'order_id': order_id,
            'symbol': self.symbol
        }
        self._save_state()
        print(f"[POSITION] Nueva posición: {quantity} {self.symbol} @ ${entry_price:.2f}")
        print(f"[POSITION] SL: ${stop_loss:.2f} | TP: ${take_profit:.2f}")
    
    def close_position(self, exit_price: float, exit_reason: str) -> Dict:
        """Cierra la posición actual y retorna resumen"""
        if not self.position:
            return {}
        
        profit = (exit_price - self.position['entry_price']) * self.position['quantity']
        profit_pct = (exit_price - self.position['entry_price']) / self.position['entry_price'] * 100
        
        result = {
            'entry_price': self.position['entry_price'],
            'exit_price': exit_price,
            'quantity': self.position['quantity'],
            'profit': profit,
            'profit_pct': profit_pct,
            'exit_reason': exit_reason,
            'entry_time': self.position['entry_time'],
            'exit_time': datetime.now().isoformat()
        }
        
        print(f"[POSITION] Posición cerrada: {exit_reason}")
        print(f"[POSITION] P&L: ${profit:.2f} ({profit_pct:+.2f}%)")
        
        self.position = None
        self._save_state()
        
        return result
    
    def update_stop_loss(self, new_stop: float):
        """Actualiza el stop loss de la posición"""
        if self.position:
            old_stop = self.position['stop_loss']
            self.position['stop_loss'] = new_stop
            self._save_state()
            print(f"[POSITION] SL actualizado: ${old_stop:.2f} -> ${new_stop:.2f}")
    
    def add_pending_order(self, order_id: str, order_type: str, price: float):
        """Registra una orden pendiente"""
        self.pending_orders.append({
            'order_id': order_id,
            'order_type': order_type,
            'price': price,
            'created_at': datetime.now().isoformat()
        })
        self._save_state()
    
    def remove_pending_order(self, order_id: str):
        """Elimina una orden pendiente"""
        self.pending_orders = [o for o in self.pending_orders if o['order_id'] != order_id]
        self._save_state()
    
    def sync_with_exchange(self) -> bool:
        """
        Sincroniza el estado local con el exchange.
        Verifica si las órdenes OCO siguen activas.
        """
        try:
            # Obtener órdenes abiertas
            open_orders = self.client.get_open_orders(symbol=self.symbol)
            open_order_ids = {str(o['orderId']) for o in open_orders}
            
            # Actualizar órdenes pendientes
            for pending in self.pending_orders[:]:
                if pending['order_id'] not in open_order_ids:
                    print(f"[POSITION] Orden {pending['order_id']} ya no está activa")
                    self.remove_pending_order(pending['order_id'])
            
            # Verificar balance del activo
            account = self.client.get_account()
            base_asset = self.symbol.replace('USDT', '')
            
            for balance in account.get('balances', []):
                if balance['asset'] == base_asset:
                    free_qty = float(balance['free'])
                    if self.position and free_qty < self.position['quantity'] * 0.9:
                        print(f"[POSITION] Parece que la posición fue cerrada externamente")
                        self.position = None
                        self._save_state()
                    break
            
            return True
            
        except Exception as e:
            print(f"[POSITION] Error sincronizando: {e}")
            return False
    
    def get_position_info(self) -> Optional[Dict]:
        """Retorna información de la posición actual"""
        return self.position
    
    def get_status(self) -> Dict:
        """Retorna estado completo del gestor"""
        return {
            'has_position': self.has_open_position(),
            'position': self.position,
            'pending_orders_count': len(self.pending_orders),
            'pending_orders': self.pending_orders
        }
