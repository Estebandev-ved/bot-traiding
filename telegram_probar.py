#!/usr/bin/env python3
"""
Probar Telegram desde tu PC (PowerShell) y descubrir tu chat_id.

  1) Crea el bot: en Telegram habla con @BotFather -> /newbot -> copia el token.
  2) Escríbele UN mensaje cualquiera a tu bot nuevo (por ejemplo «hola») desde tu cuenta.
  3) python telegram_probar.py --chat-id     -> imprime tu chat_id
  4) python telegram_probar.py               -> envía un mensaje de prueba

El token se pide por teclado si no está en la variable TELEGRAM_BOT_TOKEN (no se muestra ni queda en el historial).
Después guarda ambos como secretos de GitHub: TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID (ver GUIA_DE_USO.md).
"""
import getpass
import os
import sys

from alerts import Telegram, messages as m


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN") or getpass.getpass("Pega el token del bot (no se mostrará): ").strip()
    tg = Telegram(token, os.getenv("TELEGRAM_CHAT_ID") or "0")
    if "--chat-id" in sys.argv:
        try:
            ups = tg.updates()
        except Exception as e:
            sys.exit(f"No se pudo consultar Telegram: {tg._clean(e)}")
        chats = {}
        for u in ups:
            msg = u.get("message") or u.get("channel_post") or u.get("my_chat_member") or {}
            c = msg.get("chat") or {}
            if c.get("id") is not None:
                chats[c["id"]] = c.get("first_name") or c.get("title") or c.get("username") or "?"
        if not chats:
            sys.exit("El bot no ha recibido mensajes. Ábrelo en Telegram, pulsa «Iniciar» y escríbele «hola»; luego repite.")
        print("Chats que le han escrito a tu bot:")
        for cid, name in chats.items():
            print(f"  TELEGRAM_CHAT_ID = {cid}   ({name})")
        return
    chat = os.getenv("TELEGRAM_CHAT_ID") or input("Tu chat_id (de --chat-id): ").strip()
    tg = Telegram(token, chat)
    ok = tg.send("✅ <b>Prueba de Telegram</b>\nSi lees esto, las alertas de tus bots funcionan.\n" + m.PAPER)
    print("Enviado ✔ Revisa tu Telegram." if ok else f"No se pudo enviar: {tg.last_error}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
