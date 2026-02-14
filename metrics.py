"""
Módulo de Métricas de Rendimiento para Bot de Trading
Calcula Sharpe Ratio, Max Drawdown, Win Rate, Profit Factor
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime


class PerformanceMetrics:
    """
    Calcula métricas de rendimiento del bot de trading.
    """
    
    def __init__(self, initial_balance: float = 1000.0, risk_free_rate: float = 0.02):
        """
        Args:
            initial_balance: Balance inicial en USDT
            risk_free_rate: Tasa libre de riesgo anualizada (default 2%)
        """
        self.initial_balance = initial_balance
        self.risk_free_rate = risk_free_rate
        self.trades: List[Dict] = []
        self.equity_curve: List[float] = [initial_balance]
    
    def add_trade(self, entry_price: float, exit_price: float, quantity: float,
                  exit_reason: str, entry_time: str = None, exit_time: str = None):
        """Agrega un trade completado"""
        profit = (exit_price - entry_price) * quantity
        profit_pct = (exit_price - entry_price) / entry_price * 100
        
        trade = {
            'entry_price': entry_price,
            'exit_price': exit_price,
            'quantity': quantity,
            'profit': profit,
            'profit_pct': profit_pct,
            'exit_reason': exit_reason,
            'entry_time': entry_time or datetime.now().isoformat(),
            'exit_time': exit_time or datetime.now().isoformat()
        }
        
        self.trades.append(trade)
        
        # Actualizar equity curve
        new_equity = self.equity_curve[-1] + profit
        self.equity_curve.append(new_equity)
    
    def load_trades(self, trades: List[Dict]):
        """Carga trades desde una lista existente"""
        self.trades = trades
        
        # Reconstruir equity curve
        self.equity_curve = [self.initial_balance]
        for trade in trades:
            new_equity = self.equity_curve[-1] + trade.get('profit', 0)
            self.equity_curve.append(new_equity)
    
    def get_total_trades(self) -> int:
        """Número total de trades"""
        return len(self.trades)
    
    def get_win_rate(self) -> float:
        """Porcentaje de trades ganadores"""
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.get('profit', 0) > 0)
        return wins / len(self.trades) * 100
    
    def get_profit_factor(self) -> float:
        """
        Profit Factor = Ganancias brutas / Pérdidas brutas
        Un valor > 1 indica sistema rentable
        """
        if not self.trades:
            return 0.0
        
        gross_profit = sum(t['profit'] for t in self.trades if t.get('profit', 0) > 0)
        gross_loss = abs(sum(t['profit'] for t in self.trades if t.get('profit', 0) < 0))
        
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        
        return gross_profit / gross_loss
    
    def get_max_drawdown(self) -> Dict:
        """
        Maximum Drawdown = (Pico - Valle) / Pico
        Mide la mayor caída desde un pico hasta un valle
        """
        if len(self.equity_curve) < 2:
            return {'max_drawdown_pct': 0, 'max_drawdown_value': 0}
        
        equity = np.array(self.equity_curve)
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak * 100
        
        max_dd_idx = np.argmax(drawdown)
        max_dd_pct = drawdown[max_dd_idx]
        max_dd_value = peak[max_dd_idx] - equity[max_dd_idx]
        
        return {
            'max_drawdown_pct': max_dd_pct,
            'max_drawdown_value': max_dd_value,
            'peak_value': peak[max_dd_idx],
            'valley_value': equity[max_dd_idx]
        }
    
    def get_sharpe_ratio(self, periods_per_year: int = 365) -> float:
        """
        Sharpe Ratio = (Retorno promedio - Tasa libre riesgo) / Desviación estándar
        
        Args:
            periods_per_year: Número de periodos de trading por año (365 para diario)
        """
        if len(self.trades) < 2:
            return 0.0
        
        # Calcular retornos
        returns = [t.get('profit_pct', 0) / 100 for t in self.trades]
        
        avg_return = np.mean(returns)
        std_return = np.std(returns)
        
        if std_return == 0:
            return 0.0
        
        # Ajustar tasa libre de riesgo al periodo
        rf_per_period = self.risk_free_rate / periods_per_year
        
        # Sharpe Ratio anualizado
        sharpe = (avg_return - rf_per_period) / std_return * np.sqrt(periods_per_year)
        
        return sharpe
    
    def get_sortino_ratio(self, periods_per_year: int = 365) -> float:
        """
        Sortino Ratio = Similar a Sharpe pero solo considera volatilidad negativa
        """
        if len(self.trades) < 2:
            return 0.0
        
        returns = [t.get('profit_pct', 0) / 100 for t in self.trades]
        negative_returns = [r for r in returns if r < 0]
        
        if not negative_returns:
            return float('inf')
        
        avg_return = np.mean(returns)
        downside_std = np.std(negative_returns)
        
        if downside_std == 0:
            return 0.0
        
        rf_per_period = self.risk_free_rate / periods_per_year
        sortino = (avg_return - rf_per_period) / downside_std * np.sqrt(periods_per_year)
        
        return sortino
    
    def get_avg_trade(self) -> Dict:
        """Estadísticas promedio de trades"""
        if not self.trades:
            return {'avg_profit': 0, 'avg_profit_pct': 0, 'avg_winner': 0, 'avg_loser': 0}
        
        profits = [t.get('profit', 0) for t in self.trades]
        profit_pcts = [t.get('profit_pct', 0) for t in self.trades]
        
        winners = [p for p in profits if p > 0]
        losers = [p for p in profits if p < 0]
        
        return {
            'avg_profit': np.mean(profits),
            'avg_profit_pct': np.mean(profit_pcts),
            'avg_winner': np.mean(winners) if winners else 0,
            'avg_loser': np.mean(losers) if losers else 0,
            'largest_win': max(profits) if profits else 0,
            'largest_loss': min(profits) if profits else 0
        }
    
    def get_all_metrics(self) -> Dict:
        """Retorna todas las métricas calculadas"""
        avg_trade = self.get_avg_trade()
        max_dd = self.get_max_drawdown()
        
        return {
            'total_trades': self.get_total_trades(),
            'win_rate': self.get_win_rate(),
            'profit_factor': self.get_profit_factor(),
            'sharpe_ratio': self.get_sharpe_ratio(),
            'sortino_ratio': self.get_sortino_ratio(),
            'max_drawdown_pct': max_dd['max_drawdown_pct'],
            'max_drawdown_value': max_dd['max_drawdown_value'],
            'total_profit': sum(t.get('profit', 0) for t in self.trades),
            'total_return_pct': (self.equity_curve[-1] - self.initial_balance) / self.initial_balance * 100 if self.equity_curve else 0,
            'final_balance': self.equity_curve[-1] if self.equity_curve else self.initial_balance,
            **avg_trade
        }
    
    def export_to_dataframe(self) -> pd.DataFrame:
        """Exporta trades a DataFrame"""
        return pd.DataFrame(self.trades)
    
    def print_summary(self):
        """Imprime resumen de métricas"""
        metrics = self.get_all_metrics()
        
        print("\n" + "="*60)
        print("📊 MÉTRICAS DE RENDIMIENTO")
        print("="*60)
        print(f"   Total Trades:      {metrics['total_trades']}")
        print(f"   Win Rate:          {metrics['win_rate']:.2f}%")
        print(f"   Profit Factor:     {metrics['profit_factor']:.2f}")
        print(f"   Sharpe Ratio:      {metrics['sharpe_ratio']:.2f}")
        print(f"   Sortino Ratio:     {metrics['sortino_ratio']:.2f}")
        print(f"   Max Drawdown:      {metrics['max_drawdown_pct']:.2f}%")
        print("-"*60)
        print(f"   Total Profit:      ${metrics['total_profit']:.2f}")
        print(f"   Total Return:      {metrics['total_return_pct']:.2f}%")
        print(f"   Final Balance:     ${metrics['final_balance']:.2f}")
        print("-"*60)
        print(f"   Avg Profit/Trade:  ${metrics['avg_profit']:.2f}")
        print(f"   Avg Winner:        ${metrics['avg_winner']:.2f}")
        print(f"   Avg Loser:         ${metrics['avg_loser']:.2f}")
        print(f"   Largest Win:       ${metrics['largest_win']:.2f}")
        print(f"   Largest Loss:      ${metrics['largest_loss']:.2f}")
        print("="*60 + "\n")
