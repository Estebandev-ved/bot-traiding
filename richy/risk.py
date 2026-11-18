"""Gestión de riesgo. Es la pieza que decide si el bot puede operar, no la IA.

Reglas:
  * Riesgo por operación acotado (1-2% del capital).
  * Pérdida diaria máxima -> el bot se apaga solo hasta el día siguiente.
  * Tope de exposición total (nocional / capital).
  * Kill switch permanente: drawdown máximo, errores de API seguidos,
    datos viejos o precios que saltan de forma absurda.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class RiskConfig:
    risk_per_trade: float = 0.01      # fracción del capital arriesgada por operación
    max_risk_per_trade: float = 0.02  # techo duro aunque se configure más
    max_daily_loss: float = 0.03      # pérdida diaria que apaga el bot por hoy
    max_exposure: float = 1.0         # nocional total / capital (1.0 = sin apalancamiento)
    max_drawdown_kill: float = 0.20   # drawdown desde el pico que lo apaga del todo
    max_price_jump: float = 0.15      # salto entre precios consecutivos considerado "raro"
    max_api_errors: int = 5           # errores de API seguidos antes del kill switch
    max_data_age_s: float = 300.0     # antigüedad máxima aceptada del último dato


class RiskManager:
    def __init__(self, cfg: Optional[RiskConfig] = None, equity: float = 0.0):
        self.cfg = cfg or RiskConfig()
        self.peak = equity
        self.day = None
        self.day_start_equity = equity
        self.halted_today = False
        self.killed = False
        self.kill_reason = ""
        self.api_errors = 0

    # ---- estado ----
    def can_open(self) -> bool:
        return not (self.killed or self.halted_today)

    def state(self) -> dict:
        return {"killed": self.killed, "kill_reason": self.kill_reason,
                "halted_today": self.halted_today, "peak": self.peak,
                "api_errors": self.api_errors, "config": asdict(self.cfg)}

    def kill(self, reason: str) -> None:
        if not self.killed:
            self.killed, self.kill_reason = True, reason

    # ---- actualización por barra / ciclo ----
    def update(self, ts, equity: float) -> None:
        """Llamar en cada barra con la fecha y el equity marcado a mercado."""
        day = ts.date() if hasattr(ts, "date") else ts
        if day != self.day:
            self.day, self.day_start_equity, self.halted_today = day, equity, False
        self.peak = max(self.peak, equity)
        if self.day_start_equity > 0 and equity / self.day_start_equity - 1 <= -self.cfg.max_daily_loss:
            self.halted_today = True
        if self.peak > 0 and equity / self.peak - 1 <= -self.cfg.max_drawdown_kill:
            self.kill(f"drawdown {equity / self.peak - 1:.1%} supera el límite")

    # ---- tamaño de posición ----
    def position_size(self, equity: float, entry: float, stop_dist: float, open_notional: float = 0.0) -> float:
        """Unidades a comprar para que, si salta el stop, se pierda <= risk_per_trade."""
        if not self.can_open() or stop_dist <= 0 or entry <= 0 or equity <= 0:
            return 0.0
        risk = min(self.cfg.risk_per_trade, self.cfg.max_risk_per_trade)
        qty = equity * risk / stop_dist
        room = max(0.0, equity * self.cfg.max_exposure - open_notional)
        return max(0.0, min(qty, room / entry))

    # ---- sanidad de datos / API ----
    def check_price(self, prev: float, new: float) -> bool:
        if prev and prev > 0 and abs(new / prev - 1) > self.cfg.max_price_jump:
            self.kill(f"precio raro: {prev} -> {new}")
            return False
        return True

    def check_data_age(self, age_s: float) -> bool:
        if age_s > self.cfg.max_data_age_s:
            self.kill(f"datos viejos ({age_s:.0f}s)")
            return False
        return True

    def api_ok(self) -> None:
        self.api_errors = 0

    def api_error(self, msg: str = "") -> None:
        self.api_errors += 1
        if self.api_errors >= self.cfg.max_api_errors:
            self.kill(f"{self.api_errors} errores de API seguidos: {msg}")
