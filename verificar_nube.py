#!/usr/bin/env python3
"""
¿Están corriendo los bots? Lee Firestore y dice hace cuánto escribió cada uno.

  # PowerShell
  $env:GOOGLE_APPLICATION_CREDENTIALS="secrets\\serviceAccountKey.json"
  python verificar_nube.py

Estados: OK (<5 h) · RETRASADO (5-9 h) · DETENIDO (>9 h) · SIN DATOS (nunca escribió).
Cada bot debería escribir cada 4 h.
"""
import os
import sys
import time

CHECKS = [
    ("Richy · estado (BTC/USDT)", "status", "current"),
    ("Richy · funding", "status", "funding"),
    ("Breakout 4h · estado", "breakout_status", "current"),
    ("Breakout 4h · validación", "breakout_status", "validation"),
]


def verdict(age_h):
    if age_h is None:
        return "SIN DATOS"
    return "OK" if age_h < 5 else "RETRASADO" if age_h < 9 else "DETENIDO"


def check(db, now=None):
    """Devuelve [(etiqueta, veredicto, edad_en_horas, detalle)]."""
    now = now or time.time()
    rows = []
    for label, col, doc in CHECKS:
        d = db.collection(col).document(doc).get()
        data = d.to_dict() if d.exists else None
        age = (now - data["updated"]) / 3600 if data and data.get("updated") else None
        extra = ""
        if data and col == "breakout_status" and doc == "current":
            extra = (f"equity ${data.get('equity', 0):.2f} · {data.get('n_closed', 0)} trades cerrados · "
                     f"{data.get('n_open', 0)} abiertas · última vela {str(data.get('last_bar', '—'))[:16]}")
        rows.append((label, verdict(age), age, extra))
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
