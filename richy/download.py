"""Baja velas (y funding) públicos de Binance y los guarda en CSV. No necesita API keys.
  python -m richy.download --symbol BTC/USDT --timeframe 1h --bars 8000
"""
import argparse, os, time
from . import data

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="BTC/USDT"); p.add_argument("--timeframe", default="1h")
    p.add_argument("--bars", type=int, default=8000); p.add_argument("--exchange", default="binance")
    p.add_argument("--mirror", default=os.getenv("BINANCE_MIRROR"), help="host espejo de datos, p. ej. data-api.binance.vision")
    p.add_argument("--funding", action="store_true", help="también funding del perpetuo")
    a = p.parse_args()
    ex = data.make_exchange(a.exchange, mirror=a.mirror)
    ms = ex.parse_timeframe(a.timeframe) * 1000
    since = int(time.time() * 1000) - a.bars * ms
    df = data.fetch_ohlcv_paged(ex, a.symbol, a.timeframe, since_ms=since, limit_total=a.bars)
    os.makedirs("datos", exist_ok=True)
    name = f"datos/{a.symbol.replace('/', '')}_{a.timeframe}.csv"
    df.to_csv(name)
    print(f"{len(df)} velas  {df.index[0]} -> {df.index[-1]}  guardado en {name}")
    if a.funding:
        fx = data.make_exchange(a.exchange, futures=True)
        sym = a.symbol + ":" + a.symbol.split("/")[1]
        f = data.fetch_funding_history(fx, sym, since_ms=since)
        fname = f"datos/{a.symbol.replace('/', '')}_funding.csv"
        f.to_csv(fname, header=["rate"]); print(f"{len(f)} funding  guardado en {fname}")

if __name__ == "__main__":
    main()
