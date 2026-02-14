"""
Sistema de Notificaciones por Telegram para Bot de Trading
Envía alertas en tiempo real de compras/ventas y errores
"""

import os
import asyncio
from typing import Optional, Dict
from datetime import datetime

# Telegram
try:
    from telegram import Bot
    from telegram.error import TelegramError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("[TELEGRAM] Librería no instalada. Ejecuta: pip install python-telegram-bot")


class TelegramNotifier:
    """
    Envía notificaciones a Telegram sobre eventos del bot.
    
    Para configurar:
    1. Habla con @BotFather en Telegram y crea un bot
    2. Obtén el token del bot
    3. Obtén tu chat_id (habla con @userinfobot)
    4. Configura las variables de entorno
    """
    
    def __init__(self, token: str = None, chat_id: str = None):
        """
        Args:
            token: Token del bot de Telegram (de @BotFather)
            chat_id: ID del chat donde enviar mensajes
        """
        self.token = token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.enabled = bool(self.token and self.chat_id and TELEGRAM_AVAILABLE)
        
        if self.enabled:
            self.bot = Bot(token=self.token)
            print("[TELEGRAM] Notificador inicializado correctamente")
        else:
            self.bot = None
            if not TELEGRAM_AVAILABLE:
                print("[TELEGRAM] Librería no disponible")
            elif not self.token:
                print("[TELEGRAM] Token no configurado (TELEGRAM_BOT_TOKEN)")
            elif not self.chat_id:
                print("[TELEGRAM] Chat ID no configurado (TELEGRAM_CHAT_ID)")
    
    def _send_sync(self, message: str) -> bool:
        """Envía mensaje de forma síncrona"""
        if not self.enabled:
            return False
        
        try:
            asyncio.run(self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='HTML'
            ))
            return True
        except Exception as e:
            print(f"[TELEGRAM] Error enviando mensaje: {e}")
            return False
    
    async def _send_async(self, message: str) -> bool:
        """Envía mensaje de forma asíncrona"""
        if not self.enabled:
            return False
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='HTML'
            )
            return True
        except Exception as e:
            print(f"[TELEGRAM] Error enviando mensaje: {e}")
            return False
    
    def send(self, message: str) -> bool:
        """Envía un mensaje de texto"""
        return self._send_sync(message)
    
    def notify_buy(self, symbol: str, quantity: float, price: float, 
                   stop_loss: float, take_profit: float, confidence: float = None):
        """Notifica una compra ejecutada"""
        msg = f"""
🟢 <b>COMPRA EJECUTADA</b>

📈 <b>Par:</b> {symbol}
💰 <b>Cantidad:</b> {quantity:.6f}
💵 <b>Precio:</b> ${price:,.2f}

🛡️ <b>Stop Loss:</b> ${stop_loss:,.2f} ({(1 - stop_loss/price)*100:.1f}%)
🎯 <b>Take Profit:</b> ${take_profit:,.2f} ({(take_profit/price - 1)*100:.1f}%)
"""
        if confidence:
            msg += f"\n🤖 <b>Confianza ML:</b> {confidence:.1%}"
        
        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return self.send(msg)
    
    def notify_sell(self, symbol: str, quantity: float, entry_price: float,
                    exit_price: float, profit: float, reason: str):
        """Notifica una venta ejecutada"""
        profit_pct = (exit_price - entry_price) / entry_price * 100
        emoji = "🟢" if profit > 0 else "🔴"
        
        msg = f"""
{emoji} <b>VENTA EJECUTADA</b>

📈 <b>Par:</b> {symbol}
💰 <b>Cantidad:</b> {quantity:.6f}
💵 <b>Entrada:</b> ${entry_price:,.2f}
💵 <b>Salida:</b> ${exit_price:,.2f}

💰 <b>P&L:</b> ${profit:,.2f} ({profit_pct:+.2f}%)
📊 <b>Razón:</b> {reason}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send(msg)
    
    def notify_trailing_update(self, symbol: str, old_stop: float, new_stop: float,
                                current_price: float, profit_pct: float):
        """Notifica actualización de trailing stop"""
        msg = f"""
📊 <b>TRAILING STOP ACTUALIZADO</b>

📈 <b>Par:</b> {symbol}
💵 <b>Precio actual:</b> ${current_price:,.2f}
🛡️ <b>Stop anterior:</b> ${old_stop:,.2f}
🛡️ <b>Stop nuevo:</b> ${new_stop:,.2f}
📈 <b>Ganancia:</b> {profit_pct:+.2f}%
"""
        return self.send(msg)
    
    def notify_error(self, module: str, error: str, context: str = ""):
        """Notifica un error crítico"""
        msg = f"""
⚠️ <b>ERROR EN BOT</b>

🔧 <b>Módulo:</b> {module}
❌ <b>Error:</b> {error}
"""
        if context:
            msg += f"📝 <b>Contexto:</b> {context}\n"
        
        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return self.send(msg)
    
    def notify_daily_summary(self, metrics: Dict):
        """Envía resumen diario de rendimiento"""
        msg = f"""
📊 <b>RESUMEN DIARIO</b>

📈 <b>Trades hoy:</b> {metrics.get('trades_today', 0)}
💰 <b>P&L hoy:</b> ${metrics.get('pnl_today', 0):,.2f}
✅ <b>Win Rate:</b> {metrics.get('win_rate', 0):.1f}%

💼 <b>Balance:</b> ${metrics.get('balance', 0):,.2f}
📉 <b>Max Drawdown:</b> {metrics.get('max_drawdown', 0):.2f}%
📊 <b>Sharpe Ratio:</b> {metrics.get('sharpe_ratio', 0):.2f}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send(msg)
    
    def notify_signal(self, signal_type: str, symbol: str, confidence: float,
                      trend: str, action_taken: str):
        """Notifica una señal detectada"""
        emoji = "📈" if signal_type == "COMPRA" else "📉" if signal_type == "VENTA" else "⏸️"
        
        msg = f"""
{emoji} <b>SEÑAL DETECTADA</b>

📈 <b>Par:</b> {symbol}
📊 <b>Tipo:</b> {signal_type}
🤖 <b>Confianza:</b> {confidence:.1%}
📈 <b>Tendencia:</b> {trend}
⚡ <b>Acción:</b> {action_taken}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send(msg)
    
    def test_connection(self) -> bool:
        """Envía mensaje de prueba"""
        return self.send("🤖 <b>Bot de Trading conectado</b>\n\nLas notificaciones están funcionando correctamente.")


# Instancia global (singleton)
_notifier: Optional[TelegramNotifier] = None


def get_notifier() -> TelegramNotifier:
    """Obtiene o crea el notificador global"""
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier


# Funciones de conveniencia
def notify_buy(symbol: str, quantity: float, price: float, 
               stop_loss: float, take_profit: float, confidence: float = None):
    """Notifica compra usando el notificador global"""
    return get_notifier().notify_buy(symbol, quantity, price, stop_loss, take_profit, confidence)


def notify_sell(symbol: str, quantity: float, entry_price: float,
                exit_price: float, profit: float, reason: str):
    """Notifica venta usando el notificador global"""
    return get_notifier().notify_sell(symbol, quantity, entry_price, exit_price, profit, reason)


def notify_error(module: str, error: str, context: str = ""):
    """Notifica error usando el notificador global"""
    return get_notifier().notify_error(module, error, context)
