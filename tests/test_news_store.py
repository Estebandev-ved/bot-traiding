"""FirestoreNews contra una base de datos simulada en memoria (sin red)."""
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")
from newsfeed.store import FirestoreNews


class Doc:
    def __init__(self, db, col, id): self.db, self.col, self.id = db, col, id
    @property
    def reference(self): return self
    def set(self, data, merge=False):
        json.dumps(data, allow_nan=False)                       # Firestore real: solo tipos serializables
        self.db.data.setdefault(self.col, {})[self.id] = dict(data)
    def delete(self): self.db.data.get(self.col, {}).pop(self.id, None)
    def get(self):
        v = self.db.data.get(self.col, {}).get(self.id)
        return type("S", (), {"exists": v is not None, "to_dict": lambda s: v})()


class Query:
    def __init__(self, db, col, cond): self.db, self.col, self.cond = db, col, cond
    def stream(self): return [Doc(self.db, self.col, i) for i, d in list(self.db.data.get(self.col, {}).items()) if self.cond(d)]


class Col:
    def __init__(self, db, name): self.db, self.name = db, name
    def document(self, i): return Doc(self.db, self.name, str(i))
    def where(self, field, op, value): return Query(self.db, self.name, lambda d: d[field] < value)


class Batch:
    def __init__(self): self.ops = []
    def set(self, doc, data): self.ops.append(lambda: doc.set(data))
    def delete(self, doc): self.ops.append(doc.delete)
    def commit(self): [o() for o in self.ops]


class DB:
    def __init__(self): self.data = {}
    def collection(self, n): return Col(self, n)
    def batch(self): return Batch()


def item(i, ts, risk=False):
    return {"id": f"id{i}", "title": f"t{i}", "summary": "", "source": "S", "source_id": "s", "lang": "en", "link": "https://x",
            "published": "2026-11-20T00:00:00+00:00", "ts": ts, "sentiment": "neutral", "score": 0, "risk": risk, "coins": []}


def test_publish_prune_and_flags():
    db = DB()
    s = FirestoreNews(db=db)
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    t = int(now.timestamp())
    old = item(0, t - 9 * 86400)
    db.collection("news").document("id0").set(old)                          # una noticia de hace 9 días ya guardada
    s.publish([item(1, t - 100, risk=True), item(2, t - 200)], {"a": {"ok": True}}, {"value": 25, "label": "Miedo extremo"}, now)
    s.prune(t - 7 * 86400)
    assert set(db.data["news"]) == {"id1", "id2"}                           # la vieja se borró
    cur = db.data["news_status"]["current"]
    assert cur["count"] == 2 and cur["risk_count"] == 1 and cur["newest"] == t - 100
    assert db.data["news_status"]["fng"]["value"] == 25
    # interruptores del panel
    db.collection("strategies").document("notify_news").set({"enabled": False})
    assert s.strategy_flags(["notify_news", "notify_open"], defaults={"notify_news": True, "notify_open": True}) == {"notify_news": False, "notify_open": True}
    # estado y latido
    s.save_state({"notified": ["a"], "watch": {}})
    assert s.load_state()["notified"] == ["a"]
    s.put_status("telegram", {"enabled": False})
    assert s.updated("news_status", "telegram") is not None and s.updated("news_status", "nada") is None
