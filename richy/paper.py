"""Paper trading en vivo: simula las decisiones del bot con costos y riesgo reales, sin dinero.

Reproduce el historial desde el inicio de la sesión en cada ciclo (determinista), pero las señales
de barras ya cerradas quedan CONGELADAS en paper_state.json: si luego apagas una estrategia desde el
panel, solo afecta a las barras nuevas y el pasado no se reescribe."""
import json, os
import pandas as pd
from .backtest import run_backtest, CostModel
from .risk import RiskConfig
from .strategies import Strategy


class _Frozen(Strategy):
    name = "frozen"

    def __init__(self, table: pd.DataFrame):
        self.table = table

    def generate(self, df):
        return self.table.reindex(df.index)


class PaperSession:
    def __init__(self, path: str = "paper_state.json", equity0: float = 10_000.0):
        self.path, self.state = path, {"equity0": equity0, "start": None, "signals": {}}
        if os.path.exists(path):
            with open(path) as f:
                self.state = json.load(f)

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f)
        os.replace(tmp, self.path)

    def update(self, closed: pd.DataFrame, strategy: Strategy, cost: CostModel = None, risk: RiskConfig = None,
               pause: bool = False):
        """`closed` = solo velas CERRADAS. Devuelve el resultado del motor con la posición abierta."""
        st = self.state
        if st["start"] is None:
            st["start"] = closed.index[-1].isoformat()
        start_ts = pd.Timestamp(st["start"])
        live = strategy.generate(closed)
        table = live.copy()
        table.loc[table.index < start_ts, "signal"] = 0          # la sesión arranca siempre sin posición
        for ts in closed.index[closed.index >= start_ts]:
            key = ts.isoformat()
            if key not in st["signals"]:                       # barra nueva: se congela con las flags de ahora
                sig0 = 0 if pause else int(live.loc[ts, "signal"])        # pausa por noticias: queda sin posición
                st["signals"][key] = [sig0, float(live.loc[ts, "stop_dist"])]
            sig, sd = st["signals"][key]
            table.loc[ts, ["signal", "stop_dist"]] = [sig, sd]
        self._save()
        start_idx = int(closed.index.searchsorted(start_ts))
        return run_backtest(closed, _Frozen(table), equity0=st["equity0"], cost=cost or CostModel(),
                            risk=risk, start=start_idx, close_at_end=False)
