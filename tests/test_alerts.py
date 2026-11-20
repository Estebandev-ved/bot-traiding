"""Pruebas de las alertas de Telegram (sin red: todo con dobles de prueba)."""
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, ".")
from alerts import Telegram, messages as m
from alerts import breakout as ab, richy as ar

TOKEN = "123456:SECRET-TOKEN-ABC"


class Resp:
    def __init__(self, status=200, body=None, text=""):
        self.status_code, self._b, self.text, self.content = status, body if body is not None else {"ok": True}, text, b"x"

    def json(self):
        return self._b


class FakeTG:
    """Doble de Telegram: guarda lo enviado; `fail` fuerza fallos."""
    def __init__(self, enabled=True, fail=False):
        self.enabled, self.fail, self.out, self.last_sent, self.last_error = enabled, fail, [], None, None

    def send(self, text, silent=False):
        if self.fail:
            self.last_error = "boom"
            return False
        self.out.append(text)
        self.last_sent = 1.0
        return True


def state(closed=0, positions=None):
    cl = [{"symbol": "SOLUSDT", "entry_time": f"2026-01-0{i+1}T00:00:00+00:00", "exit_time": f"2026-01-0{i+1}T08:00:00+00:00",
           "entry": 100.0, "exit": 104.0, "reason": "TP", "size": 8.0, "net_ret": 0.039, "pnl": 0.31, "equity_after": 25.3 + i, "p": .6}
          for i in range(closed)]
    return {"capital_initial": 25.0, "equity": 25.3, "positions": positions or {}, "closed": cl, "last_ts": "x", "notif": None}


POS = {"BTCUSDT": {"entry_ts": "2026-01-05T00:00:00+00:00", "entry": 90000.5, "stop": 88000.0, "target": 94000.0, "size": 8.3, "p": 0.62, "bars_done": 0}}
ALL_ON = dict(m.DEFAULT_FLAGS)
NOON = datetime(2026, 1, 6, 13, 0, tzinfo=timezone.utc)
MORNING = datetime(2026, 1, 6, 8, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------- Telegram.send
def test_send_ok_and_payload():
    calls = []
    tg = Telegram(TOKEN, "42", post=lambda url, **kw: (calls.append((url, kw)), Resp())[1])
    assert tg.send("hola <b>x</b>") is True and tg.sent == 1 and tg.last_error is None
    url, kw = calls[0]
    assert url.endswith("/sendMessage") and kw["json"]["chat_id"] == "42" and kw["json"]["parse_mode"] == "HTML"


def test_send_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    tg = Telegram(post=lambda *a, **k: pytest.fail("no debe llamar a la red"))
    assert not tg.enabled and tg.send("x") is False and "no configurado" in tg.last_error


def test_http_error_is_reported_without_token():
    tg = Telegram(TOKEN, "42", post=lambda *a, **k: Resp(401, {"ok": False, "description": f"Unauthorized {TOKEN}"}))
    assert tg.send("x") is False
    assert "401" in tg.last_error and TOKEN not in tg.last_error


def test_network_exception_never_leaks_token_or_raises():
    def boom(url, **kw):
        raise RuntimeError(f"fallo conectando a {url}")
    tg = Telegram(TOKEN, "42", post=boom)
    assert tg.send("x") is False and TOKEN not in tg.last_error and "***" in tg.last_error
    assert TOKEN not in str(tg.status())


def test_long_messages_are_truncated():
    seen = {}
    tg = Telegram(TOKEN, "42", post=lambda u, **kw: (seen.update(kw["json"]), Resp())[1])
    tg.send("a" * 10000)
    assert len(seen["text"]) <= 4000


# ---------------------------------------------------------------- mensajes
def test_messages_escape_html():
    txt = m.news_risk({"title": "<script>alert(1)</script> & co", "source": "X<y", "link": "https://a.b/?q=1&z=2"})
    assert "<script>" not in txt and "&lt;script&gt;" in txt
    assert "javascript:" not in m.news_risk({"title": "t", "link": "javascript:alert(1)"})


# ---------------------------------------------------------------- Breakout
def test_new_state_notifies_open_close_and_not_twice():
    st = state(closed=2, positions=POS)
    st["notif"] = ab.new_notif(st, fresh=True)
    tg = FakeTG()
    r = ab.process(st, tg, ALL_ON, MORNING)
    assert r["sent"] == 3 and len(tg.out) == 3          # 1 apertura + 2 cierres
    assert "posición abierta" in tg.out[0] and "ganancia" in tg.out[1]
    assert ab.process(st, tg, ALL_ON, MORNING)["sent"] == 0   # idempotente: no repite


def test_old_state_without_notif_does_not_flood_history():
    st = state(closed=5, positions=POS)
    tg = FakeTG()
    assert ab.process(st, tg, ALL_ON, MORNING)["sent"] == 0 and tg.out == []
    st["closed"].append({**st["closed"][0], "symbol": "XRPUSDT"})          # un trade nuevo después
    assert ab.process(st, tg, ALL_ON, MORNING)["sent"] == 1


def test_failure_is_retried_next_cycle_in_order():
    st = state(closed=2)
    st["notif"] = ab.new_notif(st, fresh=True)
    bad = FakeTG(fail=True)
    assert ab.process(st, bad, ALL_ON, MORNING) == {"sent": 0, "failed": 1}
    assert st["notif"]["closed"] == 0                                   # no avanzó
    good = FakeTG()
    assert ab.process(st, good, ALL_ON, MORNING)["sent"] == 2 and st["notif"]["closed"] == 2


def test_disabled_telegram_or_flag_marks_seen_without_sending():
    st = state(closed=1, positions=POS)
    st["notif"] = ab.new_notif(st, fresh=True)
    off = FakeTG(enabled=False)
    ab.process(st, off, ALL_ON, MORNING)
    assert off.out == [] and st["notif"]["closed"] == 1                 # al activarlo luego no hay aluvión
    st2 = state(closed=1)
    st2["notif"] = ab.new_notif(st2, fresh=True)
    tg = FakeTG()
    ab.process(st2, tg, {**ALL_ON, "notify_close": False}, MORNING)
    assert tg.out == [] and st2["notif"]["closed"] == 1


def test_daily_summary_once_per_day_after_noon():
    st = state(closed=1)
    st["notif"] = ab.new_notif(st, fresh=False)
    tg = FakeTG()
    assert ab.process(st, tg, ALL_ON, MORNING)["sent"] == 0             # antes de las 12 UTC
    assert ab.process(st, tg, ALL_ON, NOON)["sent"] == 1 and "resumen diario" in tg.out[0]
    assert ab.process(st, tg, ALL_ON, NOON)["sent"] == 0                # ya enviado hoy
    nxt = datetime(2026, 1, 7, 12, 30, tzinfo=timezone.utc)
    assert ab.process(st, tg, ALL_ON, nxt)["sent"] == 1                 # al día siguiente, otra vez


def test_closed_position_keys_are_pruned():
    st = state(positions=POS)
    st["notif"] = ab.new_notif(st, fresh=True)
    ab.process(st, FakeTG(), ALL_ON, MORNING)
    assert len(st["notif"]["open"]) == 1
    st["positions"] = {}
    ab.process(st, FakeTG(), ALL_ON, MORNING)
    assert st["notif"]["open"] == []


# ---------------------------------------------------------------- Richy
def res(trades, op, eq=10100.0):
    return {"trades": trades, "open": op, "equity": pd.Series([eq])}


T0 = pd.Timestamp("2026-01-01T00:00:00+00:00")
TR = {"entry_time": T0, "exit_time": T0 + pd.Timedelta(hours=8), "side": 1, "entry": 90000.0, "exit": 91000.0, "qty": .01, "pnl": 10.0, "reason": "signal"}
OP = {"side": 1, "qty": 0.01, "entry": 90000.0, "stop": 88000.0, "since": T0 + pd.Timedelta(hours=12)}
CALM = {"pause": False, "reasons": [], "fng": 50}


def test_richy_first_cycle_marks_history_without_notifying():
    tgs, tg = {}, FakeTG()
    r = ar.process(tgs, "BTC/USDT", res([TR], OP), CALM, {"killed": False}, ALL_ON, tg)
    assert r["sent"] == 0 and tg.out == [] and tgs["init"] is True


def test_richy_notifies_new_trade_open_pause_and_kill_once():
    tgs, tg = {}, FakeTG()
    ar.process(tgs, "BTC/USDT", res([], None), CALM, {"killed": False}, ALL_ON, tg)          # init
    ar.process(tgs, "BTC/USDT", res([TR], OP), CALM, {"killed": False}, ALL_ON, tg)
    kinds = " | ".join(tg.out)
    assert "ganancia" in kinds and "LONG abierta" in kinds
    n = len(tg.out)
    ar.process(tgs, "BTC/USDT", res([TR], OP), CALM, {"killed": False}, ALL_ON, tg)
    assert len(tg.out) == n                                              # sin duplicados
    ar.process(tgs, "BTC/USDT", res([TR], OP), {"pause": True, "reasons": ["Miedo extremo"], "fng": 8}, {"killed": False}, ALL_ON, tg)
    assert "pausa por noticias" in tg.out[-1]
    ar.process(tgs, "BTC/USDT", res([TR], OP), {"pause": True, "reasons": ["x"], "fng": 8}, {"killed": False}, ALL_ON, tg)
    assert sum("pausa por noticias" in t for t in tg.out) == 1           # solo al cambiar
    ar.process(tgs, "BTC/USDT", res([TR], OP), CALM, {"killed": True, "kill_reason": "API caída"}, ALL_ON, tg)
    assert any("KILL SWITCH" in t for t in tg.out)


def test_richy_failure_does_not_lose_the_event():
    tgs = {}
    ar.process(tgs, "BTC/USDT", res([], None), CALM, {"killed": False}, ALL_ON, FakeTG())
    bad = FakeTG(fail=True)
    ar.process(tgs, "BTC/USDT", res([TR], None), CALM, {"killed": False}, ALL_ON, bad)
    good = FakeTG()
    ar.process(tgs, "BTC/USDT", res([TR], None), CALM, {"killed": False}, ALL_ON, good)
    assert len(good.out) == 1
