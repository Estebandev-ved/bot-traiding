"""Sincronización con Firebase (Firestore). Si no hay credenciales usa NullSink.

Colecciones:
  status/current       estado del bot, equity, drawdown, kill switch
  equity/{ts}          puntos de la curva de capital
  trades/{id}          operaciones cerradas
  strategies/{name}    {enabled: bool}  <- el panel prende/apaga cada estrategia
"""
import os
import time


class NullSink:
    def status(self, **kw): pass
    def equity_point(self, ts, value): pass
    def trade(self, t: dict): pass
    def strategy_flags(self, names): return {n: True for n in names}


class FirebaseSink:
    def __init__(self, cred_path: str = None):
        import firebase_admin
        from firebase_admin import credentials, firestore
        cred_path = cred_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(cred_path))
        self.db = firestore.client()

    def status(self, **kw):
        self.db.collection("status").document("current").set({**kw, "updated": time.time()}, merge=True)

    def equity_point(self, ts, value):
        self.db.collection("equity").document(str(int(ts))).set({"t": int(ts), "v": float(value)})

    def trade(self, t: dict):
        clean = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in t.items()}
        self.db.collection("trades").add(clean)

    def strategy_flags(self, names):
        out = {}
        for n in names:
            doc = self.db.collection("strategies").document(n).get()
            out[n] = bool(doc.to_dict().get("enabled", True)) if doc.exists else True
        return out


def get_sink():
    """FirebaseSink si hay credenciales y la librería; si no, NullSink (el bot sigue)."""
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            return FirebaseSink()
        except Exception as e:
            print(f"[cloud] Firebase no disponible ({e}); sigo sin nube")
    return NullSink()
