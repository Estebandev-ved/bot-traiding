"""Filtro de noticias y sentimiento. NUNCA abre operaciones: solo PAUSA al bot (lo deja sin posición
y sin entradas nuevas) cuando hay señales de riesgo. Si las fuentes fallan, no pausa (falla abierto)
y lo informa. Fuentes gratuitas: índice Fear & Greed y titulares RSS."""
import json, re, time, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

FEEDS = ["https://www.coindesk.com/arc/outboundfeeds/rss/", "https://cointelegraph.com/rss"]
FNG_URL = "https://api.alternative.me/fng/?limit=1"
RISK = re.compile(r"\b(hack(ed|ers?)?|exploit(ed)?|drain(ed)?|insolven\w*|bankrupt\w*|collaps\w*|halts? withdrawals?|"
                  r"suspends? withdrawals?|crackdown|seiz(ed|ure)|arrest(ed)?|fraud|rug ?pull|de-?peg\w*|delist\w*|"
                  r"ban(s|ned)?|sues?|lawsuit|hackeo|quiebra|prohíbe|estafa)\b", re.I)


def _get(url: str, timeout: float = 8.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "richy-bot"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch_fng(get=_get):
    try:
        return int(json.loads(get(FNG_URL))["data"][0]["value"])
    except Exception:
        return None


def fetch_headlines(get=_get, feeds=FEEDS):
    out, ok = [], 0
    for url in feeds:
        try:
            root = ET.fromstring(get(url)); ok += 1
            for it in root.iter("item"):
                title, pub = (it.findtext("title") or "").strip(), it.findtext("pubDate")
                try:
                    ts = parsedate_to_datetime(pub).astimezone(timezone.utc) if pub else None
                except Exception:
                    ts = None
                if title:
                    out.append((ts, title))
        except Exception:
            continue
    return out, ok


def assess(fng, headlines, now=None, window_h=6.0, min_hits=2, fng_low=10, fng_high=92) -> dict:
    now = now or datetime.now(timezone.utc)
    hits = sorted({t for ts, t in headlines if ts and 0 <= (now - ts).total_seconds() <= window_h * 3600 and RISK.search(t)})
    reasons = []
    if fng is not None and fng <= fng_low:
        reasons.append(f"Miedo extremo (Fear & Greed {fng})")
    if fng is not None and fng >= fng_high:
        reasons.append(f"Euforia extrema (Fear & Greed {fng})")
    if len(hits) >= min_hits:
        reasons.append(f"{len(hits)} titulares de riesgo en {window_h:.0f} h")
    return {"pause": bool(reasons), "reasons": reasons, "fng": fng, "headlines": hits[:5]}


class SentimentFilter:
    def __init__(self, ttl: float = 900.0, get=_get):
        self.ttl, self.get, self._t, self._last = ttl, get, 0.0, None

    def check(self, now_ts: float = None) -> dict:
        now_ts = now_ts if now_ts is not None else time.time()
        if self._last is not None and now_ts - self._t < self.ttl:
            return self._last
        fng = fetch_fng(self.get)
        heads, feeds_ok = fetch_headlines(self.get)
        res = assess(fng, heads, datetime.fromtimestamp(now_ts, timezone.utc))
        res["ok"] = fng is not None or feeds_ok > 0          # False = sin datos: no pausa, pero se avisa
        res["checked"] = now_ts
        self._t, self._last = now_ts, res
        return res
