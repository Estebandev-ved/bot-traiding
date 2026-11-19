"""
Descarga y cache de velas públicas de Binance (no requiere API key).
Usa data-api.binance.vision (solo datos de mercado, disponible aun donde api.binance.com está bloqueado).
"""
from __future__ import annotations

import os
import time
from typing import Iterable

import pandas as pd
import requests

BASE_URLS = ["https://data-api.binance.vision", "https://api.binance.com"]
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]
NUM = ["open", "high", "low", "close", "volume", "quote_volume", "trades", "taker_buy_base"]
DEFAULT_START = "2020-01-01"


def _get(path: str, params: dict, retries: int = 5):
    last = None
    for attempt in range(retries):
        for base in BASE_URLS:
            try:
                r = requests.get(base + path, params=params, timeout=20)
                if r.status_code == 200:
                    return r.json()
                last = f"{base} -> HTTP {r.status_code}"
            except requests.RequestException as e:  # red / proxy
                last = f"{base} -> {e}"
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"No se pudo descargar {path} {params}: {last}")


def _cache_path(symbol: str, interval: str) -> str:
    return os.path.join(DATA_DIR, f"{symbol}_{interval}.csv")


def download_klines(symbol: str, interval: str = "1h", start: str = DEFAULT_START,
                    use_cache: bool = True) -> pd.DataFrame:
    """Devuelve DataFrame indexado por open_time (UTC) con velas CERRADAS, actualizando el cache."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = _cache_path(symbol, interval)
    cached = None
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    if use_cache and os.path.exists(path):
        cached = pd.read_csv(path, index_col=0, parse_dates=True)
        if len(cached):
            start_ms = int(cached.index[-1].timestamp() * 1000) + 1

    rows, cursor = [], start_ms
    now_ms = int(time.time() * 1000)
    while cursor < now_ms:
        batch = _get("/api/v3/klines", {"symbol": symbol, "interval": interval,
                                        "startTime": cursor, "limit": 1000})
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1][0] + 1
        if len(batch) < 1000:
            break

    if rows:
        df = pd.DataFrame(rows, columns=COLS)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df[NUM] = df[NUM].astype(float)
        df["close_time_ms"] = df["close_time"]
        df = df.set_index("open_time")[NUM + ["close_time_ms"]]
        # descartar la vela en formación
        df = df[df["close_time_ms"] < now_ms].drop(columns="close_time_ms")
        out = pd.concat([cached, df]) if cached is not None else df
    else:
        out = cached if cached is not None else pd.DataFrame(columns=NUM)

    out = out[~out.index.duplicated(keep="last")].sort_index()
    out.to_csv(path)
    return out


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Agrega velas 1h a otra temporalidad (p.ej. '4h') sin mirar al futuro."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last",
           "volume": "sum", "quote_volume": "sum", "trades": "sum", "taker_buy_base": "sum"}
    out = df.resample(rule, label="left", closed="left").agg(agg)
    return out.dropna(subset=["close"])


def load_symbols(symbols: Iterable[str], timeframe: str = "1h", start: str = DEFAULT_START) -> dict:
    data = {}
    for s in symbols:
        df = download_klines(s, "1h", start)
        data[s] = df if timeframe == "1h" else resample_ohlcv(df, timeframe)
    return data


if __name__ == "__main__":
    import sys
    for sym in (sys.argv[1:] or ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]):
        d = download_klines(sym)
        print(f"{sym}: {len(d)} velas  {d.index[0]} -> {d.index[-1]}")
