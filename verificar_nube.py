#!/usr/bin/env python3
"""
¿Están corriendo los bots? Lee Firestore y dice hace cuánto escribió cada uno.

  # PowerShell
  $env:GOOGLE_APPLICATION_CREDENTIALS="secrets\\serviceAccountKey.json"
  python verificar_nube.py

Estados: OK · RETRASADO · DETENIDO · SIN DATOS (nunca escribió).
Los bots deberían escribir cada 4 h (OK <5 h, DETENIDO >9 h); las noticias cada hora (OK <2 h, DETENIDO >4 h).
"""
import os
import sys
import time

# (etiqueta, colección, documento, horas para «OK», horas para «DETENIDO»). Los bots escriben cada 4 h; las noticias, cada hora.
CHECKS = [
    ("Richy · estado (BTC/USDT)", "status", "current", 5, 9),
    ("Richy · funding", "status", "funding", 5, 9),
    ("Breakout 4h · estado", "breakout_status", "current", 5, 9),
    ("Breakout 4h · validación", "breakout_status", "validation", 5, 9),
    ("Noticias · estado", "news_status", "current", 2, 4),
    ("Noticias · Fear & Greed", "news_status", "fng", 2, 4),
]


def verdict(age_h, ok_h=5, bad_h=9):
    if age_h is None:
        return "SIN DATOS"
    return "OK" if age_h < ok_h else "RETRASADO" if age_h < bad_h else "DETENIDO"


def check(db, now=None):
    """Devuelve [(etiqueta, veredicto, edad_en_horas, detalle)]."""
    now = now or time.time()
    rows = []
    for label, col, doc, ok_h, bad_h in CHECKS:
        d = db.collection(col).document(doc).get()
        data = d.to_dict() if d.exists else None
        age = (now - data["updated"]) / 3600 if data and data.get("updated") else None
        extra = ""
        if data and col == "breakout_status" and doc == "current":
            extra = (f"equity ${data.get('equity', 0):.2f} · {data.get('n_closed', 0)} trades cerrados · "
                     f"{data.get('n_open', 0)} abiertas · última vela {str(data.get('last_bar', '—'))[:16]}")
        if data and col == "news_status" and doc == "current":
            feeds = data.get("feeds", {})
            extra = f"{data.get('count', 0)} noticias · fuentes {sum(1 for f in feeds.values() if f.get('ok'))}/{len(feeds)}"
        rows.append((label, verdict(age, ok_h, bad_h), age, extra))
    return rows


def main():
    cred = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred or not os.path.exists(cred):
        sys.exit("Falta GOOGLE_APPLICATION_CREDENTIALS apuntando al JSON de la cuenta de servicio "
                 "(Firebase > Configuración > Cuentas de servicio > Generar clave privada).")
    import firebase_admin
    from firebase_admin import credentials, firestore
    firebase_admin.initialize_app(credentials.Certificate(cred))
    rows = check(firestore.client())
    print(f"{'Fuente':32s} {'Estado':10s} Última escritura")
    for label, v, age, extra in rows:
        when = "nunca" if age is None else (f"hace {age * 60:.0f} min" if age < 1 else f"hace {age:.1f} h")
        print(f"{label:32s} {v:10s} {when}   {extra}")
    if all(v == "SIN DATOS" for _, v, _, _ in rows):
        print("\nNingún bot ha escrito nunca. Probable causa: el workflow no está en la rama main o falta el secreto "
              "FIREBASE_SERVICE_ACCOUNT. Ver GUIA_DE_USO.md, sección 2.")
    elif any(v in ("DETENIDO", "RETRASADO") for _, v, _, _ in rows):
        print("\nAlgún bot no está al día. Revisa GitHub > Actions (¿marca roja o sin ejecuciones?). Ver GUIA_DE_USO.md.")


if __name__ == "__main__":
    main()
