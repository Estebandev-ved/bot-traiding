import json

import numpy as np
import pandas as pd
import pytest

from richy import data
from richy.paper import PaperSession
from richy.scorecard import scorecard
from richy.strategies import TrendATR


def session(tmp_path, df, start=300, name="s"):
    s = PaperSession(str(tmp_path / f"{name}.json"), 10_000.0)
    s.state["start"] = df.index[start].isoformat()
    return s


def signals(s):
    return {k: v[0] for k, v in s.state["signals"].items()}


def test_block_new_prevents_entries_on_a_fresh_session(tmp_path):
    df = data.synthetic_ohlcv(1500, freq="4h")
    strat = TrendATR(allow_short=False)
    free = session(tmp_path, df, name="free").update(df, strat)
    s = session(tmp_path, df, name="blocked")
    blocked = s.update(df, strat, block_new=True)
    assert free["metrics"]["trades"] + (1 if free["open"] else 0) > 0
    assert blocked["metrics"]["trades"] == 0 and blocked["open"] is None
    assert set(signals(s).values()) == {0}


def test_block_new_keeps_a_running_position_but_suppresses_new_entries(tmp_path):
    df = data.synthetic_ohlcv(1500, freq="4h")
    strat = TrendATR(allow_short=False)
    live = strat.generate(df)["signal"]
    # primer tramo libre: termina con una posición abierta (señal 1 en la última vela)
    k = next(i for i in range(600, 1400) if live.iloc[i] == 1 and live.iloc[i - 1] == 1)
    s = session(tmp_path, df, start=300)
    s.update(df.iloc[:k + 1], strat)
    held_before = signals(s)[df.index[k].isoformat()]
    assert held_before == 1
    s.update(df, strat, block_new=True)                                   # ahora el portafolio frena
    sig = signals(s)
    prev = held_before
    for ts in df.index[k + 1:]:
        want = int(live.loc[ts])
        got = sig[ts.isoformat()]
        if want == 1 and prev == 1:
            assert got == 1                                               # la posición abierta se mantiene
        elif want == 1 and prev == 0:
            assert got == 0                                               # entrada nueva: frenada
        else:
            assert got == want
        prev = got


def test_frozen_signals_are_not_rewritten_when_the_block_is_lifted(tmp_path):
    df = data.synthetic_ohlcv(1500, freq="4h")
    strat = TrendATR(allow_short=False)
    s = session(tmp_path, df)
    s.update(df.iloc[:1000], strat, block_new=True)
    frozen = dict(s.state["signals"])
    s.update(df, strat)
    assert all(s.state["signals"][k] == v for k, v in frozen.items())


# ------------------------------------------------------------------ semáforo con PSR
def _res(rets, pnl_scale=100.0):
    trades = [{"pnl": r * pnl_scale, "qty": 1.0, "entry": pnl_scale, "side": 1} for r in rets]
    idx = pd.date_range("2024-01-01", periods=3000, freq="1h", tz="UTC")
    eq = pd.Series(10_000 * np.cumprod(1 + np.full(3000, 0.00002)), index=idx)
    m = {"total_return": 0.06, "max_drawdown": -0.02, "sharpe": 1.5, "trades": len(rets), "profit_factor": 2.0, "win_rate": 0.6}
    return {"equity": eq, "metrics": m, "trades": trades}, pd.DataFrame({"close": 100.0}, index=idx), idx[0]


def test_scorecard_psr_check_waits_then_passes_with_a_real_edge():
    res, closed, start = _res(list(np.random.default_rng(0).normal(0.01, 0.02, 12)))
    sc = scorecard(res, closed, start)
    assert next(c for c in sc["checks"] if c["key"] == "psr")["state"] == "wait"          # < 30 trades: no se juzga
    res, closed, start = _res(list(np.random.default_rng(0).normal(0.01, 0.02, 200)))
    sc = scorecard(res, closed, start)
    chk = next(c for c in sc["checks"] if c["key"] == "psr")
    assert chk["state"] == "ok" and sc["robust"]["psr"] > 0.95 and "verdict" in sc["robust"]
    json.dumps(sc)                                                                          # serializable para Firestore


def test_scorecard_psr_check_flags_a_losing_sample():
    res, closed, start = _res(list(np.random.default_rng(1).normal(-0.004, 0.02, 120)))
    sc = scorecard(res, closed, start)
    assert next(c for c in sc["checks"] if c["key"] == "psr")["state"] == "bad"
    assert sc["state"] == "bad" and "Sin evidencia" in sc["robust"]["verdict"]


def test_scorecard_without_trade_list_still_works():
    res, closed, start = _res([])
    res.pop("trades")
    sc = scorecard(res, closed, start)
    assert sc["robust"] is None and next(c for c in sc["checks"] if c["key"] == "psr")["state"] == "wait"
