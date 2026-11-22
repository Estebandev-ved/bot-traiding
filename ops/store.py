"""Almacén de Firestore para el ciclo de operación (lee el estado de los bots; escribe portfolio_status/*)."""
from __future__ import annotations

import json
import os
import time


class FirestoreOps:
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

    def get(self, col, doc):
        try:
            d = self.db.collection(col).document(doc).get()
            return d.to_dict() if d.exists else None
        except Exception as e:
            print(f"[ops] no se pudo leer {col}/{doc}: {type(e).__name__}")
            return None

    def put(self, col, doc, data):
        self.db.collection(col).document(doc).set({**data, "updated": data.get("updated", time.time())})

    def load_state(self):
        d = self.get("bot_state", "ops")
        return json.loads(d["json"]) if d else None

    def save_state(self, s):
        self.db.collection("bot_state").document("ops").set({"json": json.dumps(s, default=str), "updated": time.time()})

    def flags(self, names, defaults=None):
        out, defaults = {}, defaults or {}
        for n in names:
            d = self.get("strategies", n)
            out[n] = bool(d.get("enabled", defaults.get(n, True))) if d else defaults.get(n, True)
        return out

    def breakout_closed(self):
        d = self.get("bot_state", "breakout")
        try:
            return json.loads(d["json"]).get("closed", []) if d else []
        except (ValueError, KeyError):
            return []
