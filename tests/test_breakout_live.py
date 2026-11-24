from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("sklearn")
from research import cloud, overlays as ov, paper
from research.engine import Params
from research.features import build_features

N = 2400
IDX = pd.date_range("2025-01-01", periods=N, freq="4h", tz="UTC")


def frame(log_path):
    c = pd.Series(100 * np.exp(log_path), index=IDX)
    rng = np.random.default_rng(len(log_path) + int(log_path[-1] * 1000) % 97)
    o = c.shift(1).fillna(c)
    hi = np.maximum(o, c) * (1 + rng.uniform(0.0005, 0.004, N))
    lo = np.minimum(o, c) * (1 - rng.uniform(0.0005, 0.004, N))
    vol = rng.uniform(100, 200, N)
    return pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c, "volume": vol, "quote_volume": vol * c,
                         "trades": 1000.0, "taker_buy_base": vol * 0.5})


def uptrend(seed, drift=0.0009):
    return np.cumsum(np.random.default_rng(seed).normal(drift, 0.012, N))


def btc_crash(seed=99, crash_at=1500):
    r = np.random.default_rng(seed)
    step = np.concatenate([r.normal(0.0012, 0.01, crash_at), r.normal(-0.004, 0.01, N - crash_at)])
    return np.cumsum(step)


class Yes:                                   # modelo de mentira: acepta toda señal
    def predict_proba(self, X):
        return np.array([[0.0, 1.0]])


def bundle():
    return {"params": asdict(Params(sl_atr=2.0, tp_atr=4.0, max_hold=24)), "threshold": 0.5, "model": Yes()}


def run(feats, overlays=None, allow_new=True, start=300):
    st = paper.new_state(1000.0)
    st["last_ts"] = str(IDX[start])
    paper.advance(st, feats, bundle(), IDX[-2], max_positions=3, min_notional=5.0, overlays=overlays, allow_new=allow_new)
    return st


def entries(st):
    return sorted([pd.Timestamp(c["entry_time"]) for c in st["closed"]] +
                  [pd.Timestamp(p["entry_ts"]) for p in st["positions"].values()])


def feats_with(btc_path):
    f = {"BTCUSDT": frame(btc_path)}
    for i, s in enumerate(["ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]):
        f[s] = frame(uptrend(10 + i))
    return {k: build_features(v) for k, v in f.items()}


@pytest.fixture(scope="module")
def feats():
    return feats_with(btc_crash())


def test_baseline_trades_and_off_overlays_change_nothing(feats):
    a, b = run(feats, overlays=None), run(feats, overlays=ov.Overlays.off())
    assert len(a["closed"]) > 5
    assert a["closed"] == b["closed"] and a["equity"] == b["equity"]          # overlays apagados == comportamiento anterior
    assert not a.get("filters")


def test_portfolio_gate_blocks_new_entries_but_counts_them(feats):
    st = run(feats, allow_new=False)
    assert st["closed"] == [] and st["positions"] == {} and st["filters"]["halted"] > 0
    assert st["equity"] == 1000.0


def test_gate_does_not_touch_positions_already_open(feats):
    full = run(feats)
    first_entry = entries(full)[0]
    st = paper.new_state(1000.0)
    st["last_ts"] = str(IDX[300])
    cut = IDX.get_loc(first_entry) + 1
    paper.advance(st, feats, bundle(), IDX[cut], overlays=None, allow_new=True)
    assert st["positions"] or st["closed"]
    n_before = len(entries(st))
    paper.advance(st, feats, bundle(), IDX[-2], overlays=None, allow_new=False)          # ahora el portafolio frena
    assert len(entries(st)) == n_before                                                    # nada nuevo...
    assert st["last_ts"] == str(IDX[-2])                                                    # avanzó todas las velas
    assert not st["positions"] or all(p["bars_done"] < 24 for p in st["positions"].values())   # nada se queda colgado
    assert any(c["entry_time"] == str(first_entry) for c in st["closed"])                  # la posición ya abierta SÍ se cerró


def test_regime_filter_blocks_entries_after_btc_loses_its_200d_average(feats):
    reg = ov.regime_series(feats, "btc_ema200d")
    after = reg.iloc[1300:]
    blocked_from = after[~after].index[0]
    off = run(feats, overlays=ov.Overlays.off())
    on = run(feats, overlays=ov.Overlays())
    assert any(e >= blocked_from for e in entries(off))                 # sin filtro se sigue comprando altcoins en caída de BTC
    assert not any(e > blocked_from for e in entries(on))      # la señal de la vela bloqueada ya no entra
    assert on["filters"]["regime"] > 0
    assert len(entries(on)) < len(entries(off))


def test_missing_btc_disables_regime_filter_with_a_warning():
    f = {k: v for k, v in feats_with(btc_crash()).items() if k != "BTCUSDT"}
    st = run(f, overlays=ov.Overlays())
    assert any("sin BTCUSDT" in x for x in st["log"]) and len(entries(st)) > 0


def test_correlated_positions_get_smaller_and_the_multiplier_is_audited():
    base = uptrend(5)
    twin = {s: build_features(frame(base * k)) for s, k in
            zip(["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"], [1.0, 1.0, 1.0, 1.0, 1.0])}
    on = run(twin, overlays=ov.Overlays(regime=None, vol_scale=False, corr_scale=True))
    off = run(twin, overlays=ov.Overlays.off())
    mults = {c["risk_mult"] for c in on["closed"]}
    assert 0.75 in mults and 0.5625 in mults                          # 2ª y 3ª posición correlacionadas
    assert {c["risk_mult"] for c in off["closed"]} == {1.0}
    first = max(on["closed"], key=lambda c: c["risk_mult"])
    assert first["risk_mult"] == 1.0 and max(c["size"] for c in on["closed"]) <= max(c["size"] for c in off["closed"]) + 1e-9


def test_overlay_config_changes_are_recorded():
    st = paper.new_state(25.0)
    now = pd.Timestamp("2026-06-01", tz="UTC")
    paper._record_config(st, ov.Overlays(), now)
    paper._record_config(st, ov.Overlays(), now + pd.Timedelta(hours=1))
    assert len(st["overlay_history"]) == 1
    paper._record_config(st, ov.Overlays.off(), now + pd.Timedelta(hours=2))
    assert len(st["overlay_history"]) == 2 and not st["overlays"]["active"]


def test_env_and_flag_switch_overlays_off(monkeypatch):
    monkeypatch.delenv("BREAKOUT_OVERLAYS", raising=False)
    assert paper.overlays_from_env(True).active
    assert not paper.overlays_from_env(False).active                       # interruptor del panel
    monkeypatch.setenv("BREAKOUT_OVERLAYS", "off")
    assert not paper.overlays_from_env(True).active


def test_symbols_default_and_env_override(monkeypatch):
    monkeypatch.delenv("BREAKOUT_SYMS", raising=False)
    assert paper.symbols() == paper.DEFAULT_SYMS and len(paper.DEFAULT_SYMS) == 5
    monkeypatch.setenv("BREAKOUT_SYMS", "btcusdt, ethusdt ,")
    assert paper.symbols() == ["BTCUSDT", "ETHUSDT"]


# ------------------------------------------------------------------ estado publicado y compuerta en Firestore
def test_status_payload_exposes_exposure_overlays_and_gate():
    st = paper.new_state(100.0)
    st["positions"] = {"BTCUSDT": {"entry": 1, "stop": 0.9, "target": 1.2, "size": 20.0, "p": 0.6, "entry_ts": "2026-06-01"}}
    st["overlays"], st["gate"], st["filters"] = {"text": "x"}, {"allow": False}, {"regime": 3}
    out = cloud.status_payload(st, None)
    assert out["exposure"] == pytest.approx(0.2) and out["assets"] == {"BTCUSDT": 0.2}
    assert out["gate"] == {"allow": False} and out["filters"] == {"regime": 3}


class _Doc:
    def __init__(self, data): self.exists, self._d = data is not None, data
    def to_dict(self): return self._d


class _Col:
    def __init__(self, db, name): self.db, self.name = db, name
    def document(self, doc): return _Ref(self.db, self.name, doc)


class _Ref:
    def __init__(self, db, col, doc): self.db, self.k = db, (col, doc)
    def get(self):
        if self.db.fail:
            raise RuntimeError("sin red")
        return _Doc(self.db.docs.get(self.k))
    def set(self, d): self.db.docs[self.k] = d


class _DB:
    def __init__(self, docs=None, fail=False): self.docs, self.fail = docs or {}, fail
    def collection(self, name): return _Col(self, name)


def test_firestore_store_reads_gate_and_fails_open():
    gate = {"allow_new": False, "updated": 1.0}
    assert cloud.FirestoreStore(db=_DB({("portfolio_status", "gate"): gate})).get_gate() == gate
    assert cloud.FirestoreStore(db=_DB()).get_gate() is None
    assert cloud.FirestoreStore(db=_DB(fail=True)).get_gate() is None             # error de red: el bot opera normal
    assert cloud.FileStore("a", "b").get_gate() is None
