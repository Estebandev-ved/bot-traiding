"""
Descarga y análisis de noticias. Sin dependencias raras: `requests` + xml.etree.

El «sentimiento» es una heurística de palabras clave (no es IA ni una recomendación de inversión): sirve para
ordenar y filtrar titulares. Cada fuente falla por separado y se informa su estado, para saber cuál no responde.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

FEEDS = [
    {"id": "coindesk", "name": "CoinDesk", "lang": "en", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
    {"id": "cointelegraph", "name": "Cointelegraph", "lang": "en", "url": "https://cointelegraph.com/rss"},
    {"id": "decrypt", "name": "Decrypt", "lang": "en", "url": "https://decrypt.co/feed"},
    {"id": "criptonoticias", "name": "CriptoNoticias", "lang": "es", "url": "https://www.criptonoticias.com/feed/"},
    # Cointelegraph ES se retiró (HTTP 410). Estas dos son candidatas: si alguna falla, el panel muestra «no responde».
    {"id": "beincrypto_es", "name": "BeInCrypto ES", "lang": "es", "url": "https://es.beincrypto.com/feed/"},
    {"id": "diariobitcoin", "name": "DiarioBitcoin", "lang": "es", "url": "https://www.diariobitcoin.com/index.php/feed/"},
]
FNG_URL = "https://api.alternative.me/fng/?limit=8"
UA = {"User-Agent": "Mozilla/5.0 (compatible; richy-news/1.0)"}
ATOM = "{http://www.w3.org/2005/Atom}"

# palabras que indican RIESGO (hackeos, quiebras, prohibiciones...). Mismo criterio que richy/sentiment.py.
RISK = re.compile(r"\b(hack(ed|ers?)?|exploit(ed)?|drain(ed)?|insolven\w*|bankrupt\w*|collaps\w*|halts? withdrawals?|"
                  r"suspends? withdrawals?|crackdown|seiz(ed|ure)|arrest(ed)?|fraud|rug ?pull|de-?peg\w*|delist\w*|"
                  r"ban(s|ned)?|sues?|lawsuit|hackeo|hackeado|quiebra|prohíbe|prohibe|estafa|robo|colapso)\b", re.I)
POS = re.compile(r"\b(surge[sd]?|soar(s|ed)?|rall(y|ies|ied)|record|all-time high|ath|approv(al|ed|es)|adopt(ion|s|ed)|"
                 r"inflows?|bullish|gains?|jump(s|ed)?|rebound(s|ed)?|breakout|upgrade[sd]?|partnership|milestone|recover(s|y|ed)?|"
                 r"sube[n]?|récord|aprobaci[oó]n|aprueba|adopci[oó]n|alcista|ganancias?|rebote|despega|dispara|recupera)\b", re.I)
NEG = re.compile(r"\b(crash(es|ed)?|plunge[sd]?|tumble[sd]?|slump(s|ed)?|sell-?off|drops?|dropped|falls?|fell|bearish|outflows?|"
                 r"liquidat\w*|losses|loss|fear|warns?|decline[sd]?|dump(s|ed)?|"
                 r"cae[n]?|desplome|ca[ií]da|bajista|p[eé]rdidas?|liquidaciones|miedo|advierte|hunde|desploma)\b", re.I)
COINS = {"BTC": r"\b(bitcoin|btc)\b", "ETH": r"\b(ethereum|ether|eth)\b", "SOL": r"\b(solana|sol)\b",
         "XRP": r"\b(xrp|ripple)\b", "BNB": r"\b(bnb|binance coin|bnb chain)\b"}
COIN_RE = {k: re.compile(v, re.I) for k, v in COINS.items()}
FNG_ES = {"Extreme Fear": "Miedo extremo", "Fear": "Miedo", "Neutral": "Neutral", "Greed": "Codicia",
          "Extreme Greed": "Codicia extrema"}


def clean(text: str | None, limit: int = 220) -> str:
    t = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    t = re.sub(r"\s+", " ", html.unescape(t)).strip()
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + "…"


def _text(el) -> str | None:
    """Todo el texto de un elemento, incluso si el feed metió HTML sin escapar dentro de <description>."""
    return "".join(el.itertext()) if el is not None else None


def item_id(link: str, title: str) -> str:
    return hashlib.sha1((link or title).encode("utf-8")).hexdigest()[:16]


def safe_link(link: str | None) -> str:
    """Solo enlaces https/http; cualquier otro esquema (javascript:, data:...) se descarta."""
    link = (link or "").strip()
    return link if re.match(r"^https?://", link, re.I) else ""


def classify(title: str, summary: str = "") -> dict:
    text = f"{title} {summary}"
    risk = bool(RISK.search(title))
    score = len(POS.findall(text)) - len(NEG.findall(text)) - (2 if risk else 0)
    return {"sentiment": "positive" if score >= 1 else "negative" if score <= -1 else "neutral",
            "score": score, "risk": risk, "coins": [c for c, rx in COIN_RE.items() if rx.search(text)]}


def _when(raw: str | None, now: datetime) -> datetime:
    """Acepta fechas RSS (RFC 822) y Atom (ISO 8601). Si no se entiende, usa `now`."""
    for parse in (parsedate_to_datetime, lambda r: datetime.fromisoformat(r.replace("Z", "+00:00"))):
        try:
            dt = parse((raw or "").strip())
            return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
        except Exception:
            continue
    return now


def parse_feed(xml_text: str, feed: dict, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    root = ET.fromstring(xml_text.strip())
    out = []
    for it in list(root.iter("item")) + list(root.iter(ATOM + "entry")):
        if it.tag == ATOM + "entry":
            title = _text(it.find(ATOM + "title"))
            desc = _text(it.find(ATOM + "summary")) or _text(it.find(ATOM + "content"))
            ln = it.find(ATOM + "link")
            link, pub = (ln.get("href") if ln is not None else ""), it.findtext(ATOM + "published") or it.findtext(ATOM + "updated")
        else:
            title, desc = _text(it.find("title")), _text(it.find("description"))
            link, pub = it.findtext("link"), it.findtext("pubDate")
        title = clean(title, 300)
        if not title:
            continue
        summary, dt = clean(desc), _when(pub, now)
        out.append({"id": item_id(link or "", title), "title": title, "summary": summary, "source": feed["name"],
                    "source_id": feed["id"], "lang": feed["lang"], "link": safe_link(link),
                    "published": dt.isoformat(), "ts": int(dt.timestamp()), **classify(title, summary)})
    return out


def fetch_text(url: str, get=requests.get, timeout: float = 12.0) -> str:
    r = get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r.text


def collect(get=requests.get, feeds=None, now: datetime | None = None, max_age_days: int = 3, per_feed: int = 25):
    """Devuelve (noticias ordenadas de nuevas a viejas sin duplicados, estado por fuente)."""
    now = now or datetime.now(timezone.utc)
    feeds = FEEDS if feeds is None else feeds           # se lee al ejecutar (así se puede sustituir en pruebas)
    cutoff = int((now - timedelta(days=max_age_days)).timestamp())
    seen, items, status = set(), [], {}
    for f in feeds:
        try:
            got = parse_feed(fetch_text(f["url"], get), f, now)
            got = sorted([g for g in got if g["ts"] >= cutoff], key=lambda g: -g["ts"])[:per_feed]
            status[f["id"]] = {"name": f["name"], "lang": f["lang"], "ok": True, "count": len(got), "error": None}
            for g in got:
                if g["id"] not in seen:
                    seen.add(g["id"])
                    items.append(g)
        except Exception as e:
            status[f["id"]] = {"name": f["name"], "lang": f["lang"], "ok": False, "count": 0,
                               "error": f"{type(e).__name__}: {str(e)[:100]}"}
    items.sort(key=lambda g: -g["ts"])
    return items, status


def fetch_fng(get=requests.get) -> dict | None:
    """Índice Fear & Greed: valor actual, etiqueta en español, cambio vs ayer e historial de 7 días."""
    try:
        data = json.loads(fetch_text(FNG_URL, get))["data"]
        cur = data[0]
        label = cur.get("value_classification", "")
        return {"value": int(cur["value"]), "label": FNG_ES.get(label, label), "label_en": label,
                "prev": int(data[1]["value"]) if len(data) > 1 else None,
                "history": [{"t": int(d["timestamp"]), "v": int(d["value"])} for d in reversed(data)]}
    except Exception:
        return None
