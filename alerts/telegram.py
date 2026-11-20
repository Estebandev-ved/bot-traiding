"""
Envío de mensajes a Telegram con `requests` (sin librerías extra; funciona en GitHub Actions).

Variables de entorno (las mismas que usa telegram_notifier.py):
  TELEGRAM_BOT_TOKEN   token que te da @BotFather
  TELEGRAM_CHAT_ID     tu chat (ver telegram_probar.py --chat-id)

Reglas de seguridad:
  * El token va en la URL de la API, así que NUNCA se incluye en errores ni en logs: se reemplaza por ***.
  * `send` no lanza excepciones: devuelve True/False y deja el motivo en `last_error`.
"""
from __future__ import annotations

import os
import time

import requests

API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000   # Telegram admite 4096 caracteres por mensaje


class Telegram:
    def __init__(self, token: str | None = None, chat_id: str | None = None, post=None, get=None, timeout: float = 15.0):
        self.token = (token or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        self.chat_id = str(chat_id or os.getenv("TELEGRAM_CHAT_ID") or "").strip()
        self._post = post or requests.post
        self._get = get or requests.get
        self.timeout = timeout
        self.last_error: str | None = None
        self.last_sent: float | None = None
        self.sent = 0

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def _clean(self, text: object) -> str:
        s = str(text)
        return s.replace(self.token, "***") if self.token else s

    def send(self, text: str, silent: bool = False) -> bool:
        """Envía `text` (HTML permitido: <b>, <i>, <a>, <code>). Devuelve True si Telegram lo aceptó."""
        if not self.enabled:
            self.last_error = "Telegram no configurado (faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)"
            return False
        try:
            r = self._post(API.format(token=self.token, method="sendMessage"), timeout=self.timeout, json={
                "chat_id": self.chat_id, "text": text[:MAX_LEN], "parse_mode": "HTML",
                "disable_web_page_preview": True, "disable_notification": bool(silent)})
            body = r.json() if r.content else {}
            if r.status_code == 200 and body.get("ok"):
                self.last_error, self.last_sent, self.sent = None, time.time(), self.sent + 1
                return True
            self.last_error = self._clean(f"Telegram respondió {r.status_code}: {body.get('description', r.text[:120])}")
        except Exception as e:   # red, DNS, timeout...
            self.last_error = self._clean(f"{type(e).__name__}: {e}")[:200]
        return False

    def updates(self) -> list[dict]:
        """Mensajes recientes que recibió el bot (sirve para descubrir tu chat_id)."""
        r = self._get(API.format(token=self.token, method="getUpdates"), timeout=self.timeout)
        r.raise_for_status()
        return r.json().get("result", [])

    def status(self) -> dict:
        """Estado resumido para publicar en el panel (sin secretos)."""
        return {"enabled": self.enabled, "last_sent": self.last_sent, "last_error": self.last_error, "sent": self.sent}
