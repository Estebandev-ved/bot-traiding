"""Genera el gráfico y tablas de apoyo a partir de reports/*.csv (salida de run_research)."""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from .data import load_symbols
from .portfolio import buy_hold_equal
from .run_research import OUT, SYMS


def main():
    d = pd.read_csv(os.path.join(OUT, "equity_primaria_DISEÑO.csv"), index_col=0, parse_dates=True).iloc[:, 0]
    h = pd.read_csv(os.path.join(OUT, "equity_primaria_HOLDOUT.csv"), index_col=0, parse_dates=True).iloc[:, 0]
    frames = {k: v for k, v in load_symbols(SYMS, "4h").items()}
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6), gridspec_kw={"width_ratios": [3, 1.4]})
    for a, eq, title in ((ax[0], d, "DISEÑO (walk-forward fuera de muestra)"), (ax[1], h, "HOLDOUT: últimos 12 meses")):
        bh = buy_hold_equal(frames, str(eq.index[0].date()), str((eq.index[-1] + pd.Timedelta(hours=4)).date()))
        a.plot(eq.index, eq / eq.iloc[0] * 100, label="Estrategia (ruptura 4h + ML)", lw=1.6, color="#1565c0")
        a.plot(bh.index, bh / bh.iloc[0] * 100, label="Comprar y mantener (5 cripto)", lw=1.1, color="#9e9e9e")
        a.axhline(100, color="k", lw=.5, ls=":")
        a.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=5)); a.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
        a.set_title(title, fontsize=10); a.grid(alpha=.25); a.set_ylabel("Capital (inicio = 100)")
    ax[0].legend(fontsize=8)
    fig.suptitle("Resultado FUERA DE MUESTRA con comisiones 0.075% y slippage 0.02% por lado", fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "equity_primaria.png"), dpi=130)

    t = pd.concat([pd.read_csv(os.path.join(OUT, f"trades_primaria_{s}.csv"), parse_dates=["entry_time"])
                   for s in ("DISEÑO", "HOLDOUT")])
    t["year"] = t["entry_time"].dt.year
    print("\nPor año:\n", t.groupby("year").agg(trades=("pnl", "size"), win=("net_ret", lambda x: (x > 0).mean()),
                                              avg_net=("net_ret", "mean"), pnl_pct=("port_ret", "sum")).round(4))
    pa = t.groupby("symbol")["pnl"].sum(); print("\nPnL por activo (USDT sobre 1000):\n", pa.round(1))
    for seg in ("DISEÑO", "HOLDOUT"):
        s = pd.read_csv(os.path.join(OUT, f"trades_primaria_{seg}.csv"))
        top = s.sort_values("pnl", ascending=False).head(5)["pnl"].sum()
        print(f"{seg}: PnL total {s.pnl.sum():.1f}; 5 mejores trades suman {top:.1f}; trades/mes ≈ {len(s)/ ((pd.to_datetime(s.exit_time).max()-pd.to_datetime(s.entry_time).min()).days/30.4):.1f}")


if __name__ == "__main__":
    main()
