"""Arbitraje de funding en paper (spot largo + futuro corto, delta neutral): solo simula el cobro de
funding con datos REALES de Binance y costos de entrada/salida. Sin dinero."""
import json, os
import pandas as pd
from .backtest import backtest_funding_arb, CostModel

PERIODS_PER_YEAR = 3 * 365


class FundingPaper:
    def __init__(self, path="funding_state.json", equity0=10_000.0, enter_above=0.0001, exit_below=-0.00005, smooth=9, sink=None):
        # decide con el promedio de 3 días y sale solo si es claramente negativo: evita el churn que se come el funding
        self.path, self.enter_above, self.exit_below, self.smooth = path, enter_above, exit_below, smooth
        self.sink, self.state = sink, {"equity0": equity0, "start": None}
        remote = sink.load_state("funding") if sink is not None else None
        if remote is not None:
            self.state = remote
        elif os.path.exists(path):
            with open(path) as f:
                self.state = json.load(f)

    def update(self, funding: pd.Series, cost: CostModel = None) -> dict:
        """`funding` = historial de tasas ya liquidadas. La sesión usa las tasas desde que arrancó."""
        funding = funding.sort_index()
        if self.state["start"] is None:
            self.state["start"] = funding.index[-1].isoformat()    # arranca con la última liquidación como referencia
            if self.sink is not None:
                self.sink.save_state("funding", self.state)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.state, f)
            os.replace(tmp, self.path)
        start = pd.Timestamp(self.state["start"])
        series = funding[funding.index >= start]
        res = backtest_funding_arb(series, self.state["equity0"], self.enter_above, self.exit_below, cost or CostModel(), smooth=self.smooth)
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


WORTH_IT_APR_ON_CAPITAL = 0.05     # umbral orientativo: por debajo, otras alternativas simples rinden igual o más


def monitor(funding: pd.Series) -> dict:
    """Lectura del funding real, sin simular nada: cuánto rendiría hoy el arbitraje sobre TODO el capital
    (la mitad del capital es margen del corto, por eso el factor 0.5)."""
    f = funding.sort_index()
    apr30 = float(f.iloc[-90:].mean() * PERIODS_PER_YEAR)
    return {"last_rate": float(f.iloc[-1]), "apr_7d": float(f.iloc[-21:].mean() * PERIODS_PER_YEAR), "apr_30d": apr30,
            "expected_on_capital": apr30 * 0.5, "worth_it": bool(apr30 * 0.5 >= WORTH_IT_APR_ON_CAPITAL), "payments": int(len(f))}
