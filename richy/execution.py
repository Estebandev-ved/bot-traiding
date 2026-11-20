"""Ejecución: órdenes límite, reintentos sin duplicar y conciliación con el exchange."""
import hashlib
import time
from .risk import RiskManager


def client_order_id(intent: str) -> str:
    """ID determinista por intención: el mismo intento siempre da el mismo ID,
    así un reintento nunca crea una segunda orden."""
    return "rch" + hashlib.sha1(intent.encode()).hexdigest()[:24]


class Executor:
    def __init__(self, exchange, risk: RiskManager, retries: int = 3, backoff: float = 0.5, sleep=time.sleep):
        self.ex, self.risk, self.retries, self.backoff, self.sleep = exchange, risk, retries, backoff, sleep

    def _find_existing(self, symbol: str, cid: str):
        try:
            for o in self.ex.fetch_open_orders(symbol):
                if o.get("clientOrderId") == cid:
                    return o
            for o in self.ex.fetch_closed_orders(symbol, limit=50):
                if o.get("clientOrderId") == cid:
                    return o
        except Exception:
            pass
        return None

    def place_limit(self, symbol: str, side: str, qty: float, price: float, intent: str):
        if self.risk.killed:
            raise RuntimeError(f"kill switch activo: {self.risk.kill_reason}")
        cid = client_order_id(intent)
        last = None
        for attempt in range(self.retries + 1):
            existing = self._find_existing(symbol, cid) if attempt else None
            if existing:                       # el intento anterior sí llegó: no duplicar
                self.risk.api_ok()
                return existing
            try:
                order = self.ex.create_order(symbol, "limit", side, qty, price, {"clientOrderId": cid})
                self.risk.api_ok()
                return order
            except Exception as e:             # red caída, timeout, etc.
                last = e
                self.risk.api_error(str(e))
                if self.risk.killed:
                    break
                self.sleep(self.backoff * 2 ** attempt)
        raise RuntimeError(f"orden no colocada tras reintentos: {last}")

    def cancel_all(self, symbol: str):
        for o in self.ex.fetch_open_orders(symbol):
            self.ex.cancel_order(o["id"], symbol)


def reconcile(bot_positions: dict, exchange_positions: dict, tol: float = 1e-6) -> list:
    """Compara lo que el bot cree tener con lo que hay de verdad. Devuelve discrepancias."""
    diffs = []
    for sym in sorted(set(bot_positions) | set(exchange_positions)):
        a, b = bot_positions.get(sym, 0.0), exchange_positions.get(sym, 0.0)
        if abs(a - b) > tol * max(1.0, abs(b)):
            diffs.append({"symbol": sym, "bot": a, "exchange": b, "diff": a - b})
    return diffs


class PaperExchange:
    """Exchange simulado con la interfaz mínima de ccxt, para paper trading y tests."""
    def __init__(self, fail_first: int = 0, lose_response: bool = False):
        self.orders, self.fail_first, self.lose_response, self.calls = [], fail_first, lose_response, 0

    def create_order(self, symbol, type_, side, amount, price=None, params=None):
        self.calls += 1
        cid = (params or {}).get("clientOrderId")
        if any(o["clientOrderId"] == cid for o in self.orders):
            raise RuntimeError("duplicate clientOrderId")
        if self.calls <= self.fail_first:
            raise ConnectionError("timeout")
        o = {"id": str(len(self.orders) + 1), "clientOrderId": cid, "symbol": symbol, "side": side,
             "amount": amount, "price": price, "status": "open"}
        self.orders.append(o)
        if self.lose_response and self.calls == 1:   # la orden llegó pero la respuesta se perdió
            raise ConnectionError("response lost")
        return o

    def fetch_open_orders(self, symbol=None):
        return [o for o in self.orders if o["status"] == "open"]

    def fetch_closed_orders(self, symbol=None, limit=50):
        return [o for o in self.orders if o["status"] != "open"]

    def cancel_order(self, oid, symbol=None):
        for o in self.orders:
            if o["id"] == oid:
                o["status"] = "canceled"
