"""
Almacenamiento y publicación del paper trader "Breakout 4h".

FileStore       -> estado en archivos locales (PC). No publica nada.
FirestoreStore  -> estado en Firestore (para GitHub Actions, donde el disco se borra entre corridas) y
                   publicación para el panel de Firebase.

Colecciones (todas con prefijo `breakout_` para NO mezclarse con las de Richy: status, equity, trades):
  bot_state/breakout            estado completo de la sesión (JSON)
  bot_state/breakout_model      modelo ML entrenado (joblib comprimido en base64, ~80 KB)
  breakout_status/current       KPIs, posiciones abiertas, latido (`updated`)
  breakout_status/validation    resultados de la validación (de reports/resultados.json)
  breakout_equity/{t}           curva de equity (una fila por trade cerrado)
  breakout_trades/{id}          trades cerrados
Las reglas de firestore.rules (lectura solo para tu correo, escritura solo con la cuenta de servicio) ya cubren
estas colecciones.
"""
from __future__ import annotations

import base64
import io
import json
import os
import time

import joblib
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_TRADES = 100
PRIMARY = "PRIMARIA  SL2/TP4/H24"


def _iso(x) -> str:
    return pd.Timestamp(x).isoformat()


def _ts(x) -> int:
    return int(pd.Timestamp(x).timestamp())


def validation_payload(path: str | None = None) -> dict | None:
    """Resumen compacto de reports/resultados.json para mostrar en el panel."""
    path = path or os.path.join(ROOT, "reports", "resultados.json")
    try:
        with open(path, encoding="utf-8") as f:
            res = json.load(f)
    except (OSError, ValueError):
        return None

    def seg(v, s):
        m = v.get(s, {}).get("ml", {})
        if not m.get("n_trades"):
            return None
        return {"ret": m["total_return"], "cagr": m.get("cagr"), "dd": m["max_drawdown"], "sharpe": m["sharpe"],
                "n": m["n_trades"], "win": m["win_rate"], "pf": m["profit_factor"], "bh": v[s]["bh_return"]}

    variants = {name: {"design": seg(v, "DISEÑO"), "holdout": seg(v, "HOLDOUT")}
                for name, v in res.get("variants", {}).items()}
    prim = variants.get(PRIMARY, {})
    return {"design": prim.get("design"), "holdout": prim.get("holdout"), "variants": variants,
            "holdout_start": res.get("holdout_start")}


def status_payload(state: dict, bundle: dict | None) -> dict:
    """KPIs del paper trading listos para el panel."""
    closed = pd.DataFrame(state.get("closed", []))
    n = len(closed)
    cap0, eq = float(state["capital_initial"]), float(state["equity"])
    out = {"equity": eq, "capital_initial": cap0, "ret": eq / cap0 - 1, "n_closed": n, "n_open": len(state["positions"]),
           "target_trades": TARGET_TRADES, "last_bar": state.get("last_ts"), "win_rate": None, "profit_factor": None,
           "max_dd": 0.0,
           "positions": [{"symbol": s, "entry": p["entry"], "stop": p["stop"], "target": p["target"], "size": p["size"],
                          "p": p["p"], "since": _iso(p["entry_ts"])} for s, p in state["positions"].items()]}
    if n:
        out["win_rate"] = float((closed["net_ret"] > 0).mean())
        gl = abs(float(closed.loc[closed["pnl"] <= 0, "pnl"].sum()))
        out["profit_factor"] = float(closed.loc[closed["pnl"] > 0, "pnl"].sum() / gl) if gl else None
        out["max_dd"] = float((closed["equity_after"] / closed["equity_after"].cummax() - 1).min())
    eq_safe = eq if eq > 0 else 1.0
    out["exposure"] = float(sum(float(p["size"]) for p in state["positions"].values()) / eq_safe)
    out["assets"] = {s: float(p["size"]) / eq_safe for s, p in state["positions"].items()}
    out["overlays"] = state.get("overlays")
    out["filters"] = state.get("filters")
    out["gate"] = state.get("gate")
    if bundle:
        out["model"] = {"trained_at": bundle.get("trained_at"), "threshold": bundle.get("threshold"),
                        "n_train": bundle.get("n_train")}
    return out


def equity_points(state: dict) -> list[tuple[int, float]]:
    closed = state.get("closed", [])
    start = state.get("started") or (closed[0]["entry_time"] if closed else state.get("last_ts"))
    pts = [(_ts(start), float(state["capital_initial"]))] if start else []
    pts += [(_ts(c["exit_time"]), float(c["equity_after"])) for c in closed]
    return pts


def trade_docs(state: dict) -> list[tuple[str, dict]]:
    out = []
    for c in state.get("closed", []):
        doc = {**c, "entry_time": _iso(c["entry_time"]), "exit_time": _iso(c["exit_time"])}
        out.append((f"{_ts(c['entry_time'])}_{_ts(c['exit_time'])}_{c['symbol']}", doc))
    return out


# ------------------------------------------------------------------ serialización del modelo
def pack_bundle(bundle: dict) -> str:
    buf = io.BytesIO()
    joblib.dump(bundle, buf, compress=3)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def unpack_bundle(b64: str) -> dict:
    return joblib.load(io.BytesIO(base64.b64decode(b64)))


# ------------------------------------------------------------------ stores
class FileStore:
    """Estado y modelo en archivos locales."""
    name = "archivos locales"

    def __init__(self, state_path: str, model_path: str):
        self.state_path, self.model_path = state_path, model_path

    def load_state(self):
        if os.path.exists(self.state_path):
            with open(self.state_path, encoding="utf-8") as f:
                return json.load(f)
        return None

    def save_state(self, state):
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.state_path)

    def load_model(self):
        return joblib.load(self.model_path) if os.path.exists(self.model_path) else None

    def save_model(self, bundle):
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        joblib.dump(bundle, self.model_path)

    def publish(self, state, bundle, full=True):
        pass

    def strategy_flags(self, names, defaults=None):
        return {n: (defaults or {}).get(n, True) for n in names}

    def put_status(self, name, data):
        pass

    def get_gate(self):
        return None            # sin nube no hay gestor de portafolio: el bot opera normal


class FirestoreStore:
    """Estado y modelo en Firestore + publicación para el panel. Requiere GOOGLE_APPLICATION_CREDENTIALS."""
    name = "Firestore"

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
        d = self._get("bot_state", "breakout")
        return json.loads(d["json"]) if d else None

    def save_state(self, state):
        self.db.collection("bot_state").document("breakout").set({"json": json.dumps(state, default=str), "updated": time.time()})

    def load_model(self):
        d = self._get("bot_state", "breakout_model")
        return unpack_bundle(d["b64"]) if d else None

    def save_model(self, bundle):
        self.db.collection("bot_state").document("breakout_model").set({"b64": pack_bundle(bundle), "updated": time.time()})

    def strategy_flags(self, names, defaults=None):
        """Interruptores del panel (strategies/{id}.enabled). Si no existen, vale el valor por defecto."""
        out, defaults = {}, defaults or {}
        for n in names:
            d = self._get("strategies", n)
            out[n] = bool(d.get("enabled", defaults.get(n, True))) if d else defaults.get(n, True)
        return out

    def put_status(self, name, data):
        self.db.collection("breakout_status").document(name).set({**data, "updated": time.time()})

    def get_gate(self):
        """Compuerta del gestor de portafolio (portfolio_status/gate). Si falla la lectura, el bot opera normal."""
        try:
            return self._get("portfolio_status", "gate")
        except Exception as e:
            print(f"[portafolio] no se pudo leer la compuerta ({type(e).__name__}); opero normal")
            return None

    def publish(self, state, bundle, full=True):
        """Siempre escribe el estado y la validación (latido). `full` además reescribe la curva de equity y los trades:
        solo hace falta cuando se cerró un trade o la sesión es nueva."""
        now = time.time()
        self.db.collection("breakout_status").document("current").set({**status_payload(state, bundle), "updated": now})
        val = validation_payload()
        if val:
            self.db.collection("breakout_status").document("validation").set({**val, "updated": now})
        if not full:
            return
        pts = equity_points(state)
        col = self.db.collection("breakout_equity")
        for i in range(0, len(pts), 400):
            b = self.db.batch()
            for t, v in pts[i:i + 400]:
                b.set(col.document(str(t)), {"t": t, "v": v})
            b.commit()
        tcol = self.db.collection("breakout_trades")
        docs = trade_docs(state)
        for i in range(0, len(docs), 400):
            b = self.db.batch()
            for tid, doc in docs[i:i + 400]:
                b.set(tcol.document(tid), doc)
            b.commit()
