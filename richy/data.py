"""Datos: ccxt (REST + WebSocket con ccxt.pro), funding, open interest y datos sintéticos."""
import numpy as np
import pandas as pd


def make_exchange(name: str = "binance", futures: bool = False, **opts):
    import ccxt  # opcional
    cfg = {"enableRateLimit": True, **opts}
    if futures:
        cfg["options"] = {"defaultType": "swap", **cfg.get("options", {})}
    return getattr(ccxt, name)(cfg)


def fetch_ohlcv_paged(ex, symbol: str, timeframe: str = "1h", since_ms: int = None, limit_total: int = 5000) -> pd.DataFrame:
    rows, since = [], since_ms
    while len(rows) < limit_total:
        batch = ex.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not batch:
            break
        rows += batch
        since = batch[-1][0] + 1
        if len(batch) < 2:
            break
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.pop("ts"), unit="ms", utc=True)
    return df[~df.index.duplicated()].astype(float)


def fetch_funding_history(ex, symbol: str, since_ms: int = None, limit: int = 1000) -> pd.Series:
    h = ex.fetch_funding_rate_history(symbol, since=since_ms, limit=limit)
    s = pd.Series({pd.to_datetime(x["timestamp"], unit="ms", utc=True): x["fundingRate"] for x in h}, dtype=float)
    return s.sort_index()


def fetch_open_interest_history(ex, symbol: str, timeframe: str = "1h", limit: int = 500) -> pd.Series:
    h = ex.fetch_open_interest_history(symbol, timeframe, limit=limit)
    return pd.Series({pd.to_datetime(x["timestamp"], unit="ms", utc=True): x["openInterestAmount"] for x in h}, dtype=float).sort_index()


async def stream_order_book(exchange_name: str, symbol: str, on_book, depth: int = 20):
    """WebSocket del libro de órdenes con ccxt.pro (mismo código para Binance, Bybit, OKX...)."""
    import ccxt.pro as ccxtpro  # opcional
    ex = getattr(ccxtpro, exchange_name)({"enableRateLimit": True})
    try:
        while True:
            ob = await ex.watch_order_book(symbol, depth)
            await on_book(exchange_name, symbol, ob)
    finally:
        await ex.close()


def synthetic_ohlcv(n: int = 6000, seed: int = 1, start_price: float = 30000.0, freq: str = "1h") -> pd.DataFrame:
    """Mercado sintético con regímenes alternados (tendencia, rango, volatilidad) para pruebas."""
    rng = np.random.default_rng(seed)
    drift = np.zeros(n); vol = np.full(n, 0.004)
    i = 0
    while i < n:
        L = int(rng.integers(150, 500)); kind = rng.choice(["up", "down", "range", "wild"])
        d = {"up": 0.0006, "down": -0.0006, "range": 0.0, "wild": 0.0}[kind]
        drift[i:i + L] = d
        vol[i:i + L] = 0.012 if kind == "wild" else 0.004
        if kind == "range":   # reversión a la media dentro del rango
            drift[i:i + L] = 0.0
        i += L
    r = rng.normal(drift, vol)
    close = start_price * np.exp(np.cumsum(r))
    open_ = np.r_[start_price, close[:-1]]
    spread = np.abs(rng.normal(0, vol)) * close * 0.6
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    idx = pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "volume": rng.lognormal(5, 0.4, n)}, index=idx)


def synthetic_funding(n: int = 1500, seed: int = 2) -> pd.Series:
    rng = np.random.default_rng(seed)
    rate = 0.0001 + np.cumsum(rng.normal(0, 0.00002, n)) * 0.2
    rate = 0.0001 + 0.00008 * np.sin(np.arange(n) / 60) + rng.normal(0, 0.00003, n)
    return pd.Series(rate, index=pd.date_range("2024-01-01", periods=n, freq="8h", tz="UTC"))
