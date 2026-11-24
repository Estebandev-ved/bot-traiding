from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("sklearn")
from alerts import messages as am
from research import paper, why
from research.engine import Params
from research.features import build_features
from richy import data, why as rwhy
from richy.strategies import TrendATR

N = 2400
IDX = pd.date_range("2025-01-01", periods=N, freq="4h", tz="UTC")


def frame(log_path):
    c = pd.Series(100 * np.exp(log_path), index=IDX)
    rng = np.random.default_rng(7)
    o = c.shift(1).fillna(c)
    hi = np.maximum(o, c) * (1 + rng.uniform(0.0005, 0.004, N))
    lo = np.minimum(o, c) * (1 - rng.uniform(0.0005, 0.004, N))
    vol = rng.uniform(100, 200, N)
    return pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c, "volume": vol, "quote_volume": vol * c,
                         "trades": 1000.0, "taker_buy_base": vol * 0.5})


def path(seed, up=0.0009, down_from=None):
    r = np.random.default_rng(seed)
    step = r.normal(up, 0.012, N)
    if down_from:
        step[down_from:] = r.normal(-0.004, 0.01, N - down_from)
    return np.cumsum(step)


def feats(btc_down_from=1500, alts_down=False):
    f = {"BTCUSDT": build_features(frame(path(99, 0.0012, btc_down_from)))}
    for i, s in enumerate(["ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]):
        f[s] = build_features(frame(path(10 + i, down_from=btc_down_from if alts_down else None)))
    return f


LAST = IDX[-2]


def test_bear_market_is_explained_as_regime_with_numbers():
    r = why.explain(feats(alts_down=True), LAST, {"positions": {}}, overlays_on=True)
    assert r["status"] == "regime" and "bajo su media de 200 días" in r["text"]
    assert r["regime"]["ready"] and not r["regime"]["on"] and r["regime"]["gap"] < 0
    assert len(r["pairs"]) == 5 and all(not p["above_ema200"] for p in r["pairs"])
    assert "Aun sin el filtro" in r["text"] and "no hay ruptura posible" in r["text"]


def test_without_the_filter_the_same_market_is_just_no_signal():
    r = why.explain(feats(alts_down=True), LAST, {"positions": {}}, overlays_on=False)
    assert r["status"] == "no_signal" and "ningún par está rompiendo" in r["text"]


def test_open_positions_and_portfolio_pause_take_priority():
    st = {"positions": {"BTCUSDT": {}, "SOLUSDT": {}}}
    r = why.explain(feats(), LAST, st, True)
    assert r["status"] == "open" and "2 posiciones abiertas" in r["text"] and "BTC, SOL" in r["text"]
    r = why.explain(feats(), LAST, {"positions": {}}, True, gate_allow=False, gate_reason="caída combinada -16%")
    assert r["status"] == "halted" and "caída combinada" in r["text"]


def test_pair_rows_are_consistent_with_the_breakout_rule():
    f = feats(btc_down_from=2300)
    for p in why.pair_rows(f, LAST):
        o = f[p["symbol"]].loc[LAST]
        assert p["signal"] == bool(o["close"] > o["donch_hi"] and o["close"] > o["ema200"])
        assert p["gap_breakout"] == pytest.approx(o["close"] / o["donch_hi"] - 1)


def test_missing_btc_or_short_history_does_not_crash():
    f = feats()
    f.pop("BTCUSDT")
    r = why.explain(f, LAST, {"positions": {}}, True)
    assert r["regime"] is None and r["status"] in ("no_signal", "signal")
    short = {k: v.iloc[:700] for k, v in feats().items()}
    r = why.explain(short, short["BTCUSDT"].index[-2], {"positions": {}}, True)
    assert r["regime"]["ready"] is False and r["status"] != "regime"


def test_text_never_uses_the_regime_wording_when_btc_is_healthy():
    r = why.explain(feats(btc_down_from=N - 1), LAST, {"positions": {}}, True)
    assert r["regime"]["on"] and r["status"] != "regime"


# ------------------------------------------------------------------ contadores de actividad
class Yes:
    def predict_proba(self, X): return np.array([[0.0, 1.0]])


class No:
    def predict_proba(self, X): return np.array([[1.0, 0.0]])


def run(model, overlays=None, allow_new=True):
    f = feats()
    b = {"params": asdict(Params(sl_atr=2.0, tp_atr=4.0, max_hold=24)), "threshold": 0.5, "model": model}
    st = paper.new_state(1000.0)
    st["last_ts"] = str(IDX[300])
    paper.advance(st, f, b, IDX[-2], overlays=overlays, allow_new=allow_new)
    return st


def test_activity_counts_each_fate_of_a_signal():
    from research.overlays import Overlays
    st = run(Yes(), Overlays.off())
    a = st["activity"]
    assert a["signals"] > 0 and a["opened"] == len(st["closed"]) + len(st["positions"]) and a["last_signal"]
    assert a["signals"] >= a["opened"] + a.get("skipped_slots", 0)
    assert run(No(), Overlays.off())["activity"]["rejected_model"] > 0
    g = run(Yes(), Overlays.off(), allow_new=False)["activity"]
    assert g["blocked_gate"] == g["signals"] and "opened" not in g
    r = run(Yes(), Overlays())["activity"]
    assert r["blocked_regime"] > 0 and r["opened"] > 0


def test_status_payload_exposes_why_and_activity():
    from research import cloud
    st = paper.new_state(25.0)
    st["why"], st["activity"] = {"text": "x", "status": "regime"}, {"signals": 3}
    out = cloud.status_payload(st, None)
    assert out["why"]["status"] == "regime" and out["activity"] == {"signals": 3}


# ------------------------------------------------------------------ mensaje diario
def state(**kw):
    return {"capital_initial": 25.0, "equity": 25.0, "closed": [], "positions": {}, **kw}


def test_daily_message_explains_why_it_is_idle():
    msg = am.breakout_daily(state(why={"text": "Sin entradas: BTC está -18,3% bajo su media de 200 días."},
                                  activity={"signals": 8, "blocked_regime": 5, "rejected_model": 2, "opened": 1}))
    assert "Por qué está quieto" in msg and "-18,3% bajo su media" in msg
    assert "Señales vistas 8" in msg and "bloqueadas por régimen 5" in msg and "descartadas por el modelo 2" in msg
    quiet = am.breakout_daily(state(why={"text": "Sin entradas."}))
    assert "Señales de ruptura vistas: 0" in quiet


def test_daily_message_is_unchanged_without_why_and_escapes_html():
    old = am.breakout_daily(state())
    assert "Por qué" not in old and "resumen diario" in old
    msg = am.breakout_daily(state(why={"text": "<script>x</script>"}))
    assert "<script>" not in msg and "&lt;script&gt;" in msg
    open_ = am.breakout_daily(state(positions={"BTCUSDT": {}}, why={"text": "Hay una posición abierta."}))
    assert "Por qué opera" in open_


# ------------------------------------------------------------------ Richy
def test_richy_explains_a_bear_trend():
    df = data.synthetic_ohlcv(1500, freq="4h", seed=3)
    df = df.iloc[: int(np.argmax(df["close"].to_numpy()[300:]) + 300)]            # corta en un máximo...
    down = df.copy()
    down["close"] = down["close"].iloc[::-1].to_numpy()                          # ...y lo invierte: tendencia bajista pura
    down["open"], down["high"], down["low"] = down["close"], down["close"] * 1.002, down["close"] * 0.998
    r = rwhy.explain(down, TrendATR(allow_short=False))
    assert r["status"] == "no_signal" and "tendencia bajista" in r["text"] and "solo opera en largo" in r["text"]


def test_richy_priorities_and_unsupported_strategies():
    df = data.synthetic_ohlcv(1200, freq="4h")
    s = TrendATR(allow_short=False)
    assert rwhy.explain(df, s, position={"side": 1})["status"] == "open"
    assert rwhy.explain(df, s, paused=True)["status"] == "paused"
    assert rwhy.explain(df, s, killed=True)["status"] == "killed"
    assert rwhy.explain(df, s, gate_allow=False, gate_reason="x")["status"] in ("halted",)
    assert rwhy.explain(df, object()) is None
