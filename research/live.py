"""Datos en vivo (públicos, sin API key) para el paper trader: caché histórico + velas recientes incl. la actual."""
from __future__ import annotations

import pandas as pd

from .data import COLS, NUM, _get, download_klines, resample_ohlcv


def fetch_live_4h(symbols, now: pd.Timestamp | None = None):
    """Devuelve (frames 4h con la vela en formación al final, timestamp de la última vela 4h CERRADA)."""
    now = now or pd.Timestamp.now(tz="UTC")
    frames = {}
    for s in symbols:
        base = download_klines(s, "1h")                       # actualiza el caché con velas cerradas
        raw = _get("/api/v3/klines", {"symbol": s, "interval": "1h", "limit": 6})
        tail = pd.DataFrame(raw, columns=COLS)
        tail["open_time"] = pd.to_datetime(tail["open_time"], unit="ms", utc=True)
        tail[NUM] = tail[NUM].astype(float)
        tail = tail.set_index("open_time")[NUM]
        full = pd.concat([base, tail[~tail.index.isin(base.index)]]).sort_index()
        frames[s] = resample_ohlcv(full, "4h")
    last_closed = now.floor("4h") - pd.Timedelta(hours=4)
    return frames, last_closed
