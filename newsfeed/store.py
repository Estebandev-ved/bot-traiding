"""Publicación de noticias en Firestore.

  news/{id}                  una noticia (título, resumen, fuente, enlace, sentimiento, monedas, ts)
  news_status/current        estado de cada fuente RSS y conteos
  news_status/fng            índice Fear & Greed
  news_status/telegram       estado de Telegram visto desde este bot
  bot_state/news             qué noticias ya se avisaron y qué bots estaban «caídos»
"""
from __future__ import annotations

import json
import os
import time


class FirestoreNews:
    def __init__(self, cred_path: str | None = None, db=None):
        if db is None:
            import firebase_admin
            from firebase_admin import credentials, firestore
            cred_path = cred_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if not cred_path:
                raise RuntimeError("Falta GOOGLE_APPLICATION_CREDENTIALS (ruta al JSON de la cuenta de servicio).")
            if not firebase_admin._apps:
                firebase_admin.initialize_app(credentials.Certificate(cred_path))
            db = firestore.client()
        self.db = db

    def _get(self, col, doc):
        d = self.db.collection(col).document(doc).get()
        return d.to_dict() if d.exists else None

    def load_state(self):
        d = self._get("bot_state", "news")
        return json.loads(d["json"]) if d else None

    def save_state(self, state):
        self.db.collection("bot_state").document("news").set({"json": json.dumps(state), "updated": time.time()})

    def updated(self, col, doc):
        d = self._get(col, doc)
        return d.get("updated") if d else None

    def put_status(self, name, data):
        self.db.collection("news_status").document(name).set({**data, "updated": time.time()})

    def strategy_flags(self, names, defaults=None):
        out, defaults = {}, defaults or {}
        for n in names:
            d = self._get("strategies", n)
            out[n] = bool(d.get("enabled", defaults.get(n, True))) if d else defaults.get(n, True)
        return out

    def publish(self, items, feeds, fng, now):
        col = self.db.collection("news")
        for i in range(0, len(items), 400):
            b = self.db.batch()
            for it in items[i:i + 400]:
                b.set(col.document(it["id"]), it)
            b.commit()
        self.put_status("current", {"feeds": feeds, "count": len(items), "risk_count": sum(1 for x in items if x["risk"]),
                                    "newest": items[0]["ts"] if items else None})
        if fng:
            self.put_status("fng", fng)

    def prune(self, cutoff_ts: int):
        """Borra noticias de más de 7 días para que Firestore no crezca sin límite."""
        col = self.db.collection("news")
        try:
            from google.cloud.firestore_v1.base_query import FieldFilter
            query = col.where(filter=FieldFilter("ts", "<", cutoff_ts))
        except ImportError:                       # librería antigua o entorno de pruebas
            query = col.where("ts", "<", cutoff_ts)
        old = list(query.stream())
        for i in range(0, len(old), 400):
            b = self.db.batch()
            for d in old[i:i + 400]:
                b.delete(d.reference)
            b.commit()
