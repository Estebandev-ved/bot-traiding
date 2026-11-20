"""Pruebas del feed de noticias y del vigilante (sin red: XML de ejemplo y dobles)."""
import json
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, ".")
from newsfeed import fetch
from newsfeed.runner import MemoryStore, run_cycle

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def rfc(dt):
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


def rss(items):
    body = "".join(f"<item><title>{t}</title><link>{l}</link><pubDate>{rfc(d)}</pubDate><description>{desc}</description></item>"
                   for t, l, d, desc in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{body}</channel></rss>'


H = lambda h: NOW - timedelta(hours=h)
EN_FEED = rss([
    ("Bitcoin surges to a new record as ETF inflows jump", "https://ex.com/a", H(1), "<p>BTC rally &amp; more</p>"),
    ("Exchange hacked: $50M drained from hot wallet", "https://ex.com/b", H(2), "Funds drained"),
    ("Ethereum developers schedule upgrade", "https://ex.com/c", H(5), ""),
    ("Old news from last month", "https://ex.com/old", NOW - timedelta(days=30), ""),
    ("Peligroso <script>alert(1)</script>", "javascript:alert(1)", H(1), ""),
])
ATOM_FEED = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Solana cae 8% tras desplome del mercado</title>
<link href="https://es.ex.com/x"/><published>2026-11-20T10:30:00Z</published><summary>Caída fuerte</summary></entry></feed>"""

FEEDS = [{"id": "en", "name": "EN Feed", "lang": "en", "url": "u1"}, {"id": "es", "name": "ES Feed", "lang": "es", "url": "u2"},
         {"id": "bad", "name": "Roto", "lang": "en", "url": "u3"}]


class R:
    def __init__(self, text="", code=200):
        self.text, self.code = text, code

    def raise_for_status(self):
        if self.code != 200:
            raise RuntimeError(f"HTTP {self.code}")


FNG_JSON = {"data": [{"value": "25", "value_classification": "Extreme Fear", "timestamp": "1795000000"},
                     {"value": "30", "value_classification": "Fear", "timestamp": "1794913600"}]}


# ---------------------------------------------------------------- análisis
def test_classify_sentiment_risk_and_coins():
    a = fetch.classify("Bitcoin surges to a new record as ETF inflows jump")
    assert a["sentiment"] == "positive" and a["coins"] == ["BTC"] and not a["risk"]
    b = fetch.classify("Exchange hacked: $50M drained from hot wallet")
    assert b["risk"] and b["sentiment"] == "negative"
    c = fetch.classify("Solana cae 8% tras desplome del mercado")
    assert c["sentiment"] == "negative" and c["coins"] == ["SOL"]
    assert fetch.classify("Ethereum developers schedule upgrade")["coins"] == ["ETH"]
    assert fetch.classify("Reunión de la junta")["sentiment"] == "neutral"


def test_clean_strips_html_and_truncates():
    assert fetch.clean("<p>BTC rally &amp; more</p>") == "BTC rally & more"
    assert len(fetch.clean("palabra " * 200)) <= 222


def test_safe_link_blocks_other_schemes():
    assert fetch.safe_link("https://a.b/c") == "https://a.b/c"
    assert fetch.safe_link("javascript:alert(1)") == "" and fetch.safe_link("data:text/html,x") == ""


# ---------------------------------------------------------------- feeds
def test_parse_rss_and_atom():
    rss_items = fetch.parse_feed(EN_FEED, FEEDS[0], NOW)
    assert len(rss_items) == 5 and rss_items[0]["source"] == "EN Feed" and rss_items[0]["summary"].startswith("BTC rally")
    atom_items = fetch.parse_feed(ATOM_FEED, FEEDS[1], NOW)
    assert atom_items[0]["link"] == "https://es.ex.com/x" and atom_items[0]["lang"] == "es"
    bad = [i for i in rss_items if "Peligroso" in i["title"]][0]
    assert bad["link"] == ""                                                       # enlace peligroso descartado


def test_collect_isolates_failing_feed_and_filters_old():
    items, status = fetch.collect(get_all, feeds=FEEDS, now=NOW)
    assert status["en"]["ok"] and status["es"]["ok"] and not status["bad"]["ok"] and "503" in status["bad"]["error"]
    titles = [i["title"] for i in items]
    assert not any("Old news" in t for t in titles)                                # más de 3 días: fuera
    assert [i["ts"] for i in items] == sorted((i["ts"] for i in items), reverse=True)
    assert len({i["id"] for i in items}) == len(items)


def test_fng_parsing_and_failure():
    f = fetch.fetch_fng(lambda url, **kw: R(json.dumps(FNG_JSON)))
    assert f["value"] == 25 and f["label"] == "Miedo extremo" and f["prev"] == 30 and len(f["history"]) == 2
    assert fetch.fetch_fng(lambda url, **kw: R("", 500)) is None


# ---------------------------------------------------------------- ciclo
class TG:
    def __init__(self, enabled=True):
        self.enabled, self.out, self.last_error, self.last_sent = enabled, [], None, None

    def send(self, text, silent=False):
        self.out.append(text)
        self.last_sent = 1.0
        return True


def get_all(url, **kw):
    """Servidor falso: dos feeds buenos, uno roto (503) y el índice Fear & Greed."""
    if "alternative" in url:
        return R(json.dumps(FNG_JSON))
    return {"u1": R(EN_FEED), "u2": R(ATOM_FEED), "u3": R("", 503)}[url]


@pytest.fixture(autouse=True)
def only_test_feeds(monkeypatch):
    monkeypatch.setattr(fetch, "FEEDS", FEEDS)


def cycle(store, tg, now=NOW):
    return run_cycle(store, tg, get=get_all, now=now)


def test_first_cycle_publishes_but_does_not_alert():
    store, tg = MemoryStore(), TG()
    r = cycle(store, tg)
    assert r["items"] >= 3 and r["risk"] >= 1 and tg.out == [] and store.items
    assert store.status["fng"]["value"] == 25 and store.state["notified"]


def test_risk_news_alerts_once_and_respects_flag():
    store, tg = MemoryStore(), TG()
    cycle(store, tg)                                                              # 1.ª vez: solo marca
    store.state["notified"] = []                                                  # simulo que la noticia de riesgo es nueva
    r = cycle(store, tg)
    assert r["sent"] == 1 and "Noticia de riesgo" in tg.out[0] and "hacked" in tg.out[0]
    assert cycle(store, tg)["sent"] == 0                                          # sin repetir
    store2, tg2 = MemoryStore(flags={"notify_news": False}), TG()
    cycle(store2, tg2); store2.state["notified"] = []
    assert cycle(store2, tg2)["sent"] == 0


def test_watchdog_alerts_when_bot_stalls_and_when_it_recovers():
    now_ts = NOW.timestamp()
    store = MemoryStore(updated={("status", "current"): now_ts - 15 * 3600, ("breakout_status", "current"): now_ts - 3600})
    tg = TG()
    cycle(store, tg)
    assert any("Richy sin actividad" in t for t in tg.out) and not any("Breakout" in t for t in tg.out)
    n = len(tg.out)
    cycle(store, tg)
    assert len(tg.out) == n                                                       # no insiste
    store._updated[("status", "current")] = now_ts - 600                          # vuelve a escribir
    cycle(store, tg)
    assert any("volvió a la normalidad" in t for t in tg.out)


def test_never_written_bot_is_not_reported_as_down():
    store, tg = MemoryStore(), TG()
    cycle(store, tg)
    assert not any("sin actividad" in t for t in tg.out)


def test_all_feeds_failing_keeps_previous_news():
    store, tg = MemoryStore(), TG()
    cycle(store, tg)
    before = dict(store.items)
    r = run_cycle(store, tg, get=lambda url, **kw: R("", 500), now=NOW)
    assert r["feeds_ok"] == 0 and store.items == before


def test_delay_between_6_and_12_hours_does_not_alert():
    """GitHub se salta ejecuciones programadas: un retraso de 8 h es normal y no debe despertarte."""
    now_ts = NOW.timestamp()
    store, tg = MemoryStore(updated={("status", "current"): now_ts - 8 * 3600}), TG()
    cycle(store, tg)
    assert not any("sin actividad" in t for t in tg.out)


def test_only_new_news_are_written_each_cycle():
    store, tg = MemoryStore(), TG()
    cycle(store, tg)
    first = dict(store.items)
    writes = []
    orig = store.publish
    store.publish = lambda items, *a, **k: (writes.append(len(items)), orig(items, *a, **k))[1]
    cycle(store, tg)                                   # mismos titulares: nada nuevo que escribir
    assert writes == [0] and store.items == first
    assert store.status["current"]["count"] == len(first)           # pero los conteos siguen reflejando todo lo vigente
