"""Arbitraje de funding en paper (spot largo + futuro corto, delta neutral): solo simula el cobro de
funding con datos REALES de Binance y costos de entrada/salida. Sin dinero."""
import json, os
import pandas as pd
from .backtest import backtest_funding_arb, CostModel

PERIODS_PER_YEAR = 3 * 365


class FundingPaper:
    def __init__(self, path="funding_state.json", equity0=10_000.0, enter_above=0.0001, exit_below=0.0):
        self.path, self.enter_above, self.exit_below = path, enter_above, exit_below
        self.state = {"equity0": equity0, "start": None}
        if os.path.exists(path):
            with open(path) as f:
                self.state = json.load(f)

    def update(self, funding: pd.Series, cost: CostModel = None) -> dict:
        """`funding` = historial de tasas ya liquidadas. La sesión usa las tasas desde que arrancó."""
        funding = funding.sort_index()
        if self.state["start"] is None:
            self.state["start"] = funding.index[-1].isoformat()    # arranca con la última liquidación como referencia
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.state, f)
            os.replace(tmp, self.path)
        start = pd.Timestamp(self.state["start"])
        series = funding[funding.index >= start]
        res = backtest_funding_arb(series, self.state["equity0"], self.enter_above, self.exit_below, cost or CostModel())
        eq = res["equity"]
        last = float(funding.iloc[-1])
        in_pos = bool(res["in_position"])
        return {"equity": float(eq.iloc[-1]), "total_return": float(eq.iloc[-1] / self.state["equity0"] - 1), "entries": int(res["entries"]),
                "in_position": bool(in_pos), "last_rate": last, "apr": last * PERIODS_PER_YEAR,
                "periods": int(len(series)), "since": self.state["start"]}


def analyze(funding: pd.Series, cost: CostModel = None) -> dict:
    """Diagnóstico con datos reales: cómo es el funding y qué parámetros lo hacen rentable (o no)."""
    cost = cost or CostModel()
    f = funding.sort_index()
    stats = {"payments": int(len(f)), "mean_apr": float(f.mean() * PERIODS_PER_YEAR), "pct_positive": float((f > 0).mean()),
             "pct_above_1bp": float((f >= 0.0001).mean()), "min": float(f.min()), "max": float(f.max()),
             "first": f.index[0].isoformat(), "last": f.index[-1].isoformat()}
    hold = backtest_funding_arb(f, enter_above=-1, exit_below=-2, cost=cost)          # entra al inicio y nunca sale
    rows = []
    for smooth in (1, 9, 21):                                                          # 8 h, 3 días, 7 días
        for enter in (0.0001, 0.00015):
            for exit_ in (-0.00005, 0.0, 0.00005):
                r = backtest_funding_arb(f, enter_above=enter, exit_below=exit_, cost=cost, smooth=smooth)
                rows.append({"smooth": smooth, "enter": enter, "exit": exit_, "ret": r["metrics"]["total_return"],
                             "entries": r["entries"], "gross": r["gross_funding"], "costs": r["costs"]})
    return {"stats": stats, "hold": {"ret": hold["metrics"]["total_return"], "gross": hold["gross_funding"], "costs": hold["costs"],
            "dd": hold["metrics"]["max_drawdown"]}, "sweep": rows}
