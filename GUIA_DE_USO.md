# Guía de uso: Richy + Breakout 4h + panel de Firebase

Todo funciona en **paper trading** (precios reales de Binance, **sin dinero real**). Esta guía explica qué hay,
cómo activarlo, cómo comprobar que corre y cómo leer el panel.

---

## 1. Qué hay en este proyecto

| Pieza | Qué hace | Dónde se ve |
|---|---|---|
| **Richy** (`richy/`) | Bot de tendencia en BTC/USDT 4h con gestión de riesgo, noticias y funding. Capital simulado de 10,000 USDT. | Panel de Firebase → pestañas **Panel** y **Operaciones** |
| **Breakout 4h** (`research/`, `paper_trader.py`) | Bot de ruptura de máximos en 5 pares (BTC, ETH, BNB, SOL, XRP) con filtro de aprendizaje automático. Capital simulado de 25 USDT, como tu cuenta real. | Panel de Firebase → pestaña **Breakout 4h** |
| **Panel de Firebase** (`web/index.html`) | Página privada (login con tu Google) que lee Firestore: `https://bot-richy.firebaseapp.com` | Navegador |
| **Laboratorio de validación** (`research/`) | Descarga datos, simula con comisiones y valida fuera de muestra. Produce `reports/`. | `reports/INFORME_VALIDACION.md` |
| **Dashboard de Streamlit** (`dashboard.py`) | Panel local opcional (NEXUS Terminal) con pestaña Paper Trading. | `python -m streamlit run dashboard.py` |
| `bot-richy.py` (original) | Bot antiguo. **No lo uses con dinero**: su backtest tiene fuga de información y no cuenta comisiones. | — |

**Estado honesto de la estrategia Breakout 4h** (detalle en `reports/INFORME_VALIDACION.md`): ganó +81 % entre 2022 y
nov 2025 fuera de muestra, pero **perdió −9.5 % en el último año**. La rentabilidad sostenida **no está confirmada**.
Por eso solo se usa en simulación hasta reunir ~100 trades en vivo (a ~3–7 trades al mes, de 1 a 2 años).

---

## 2. Verificación de GitHub Actions (lo que encontré)

Revisé tu repositorio el 2026-11-20:

- **GitHub Actions no tiene ningún workflow ni ninguna ejecución.**
- El workflow de Richy (`bot.yml`) estaba solo en la rama `ccr-69142cb1-o754l1` (PR #2, **sin fusionar a `main`**).
- GitHub **solo ejecuta los horarios (`cron`) desde la rama por defecto (`main`)**.

**Conclusión: el bot no ha estado corriendo en GitHub Actions.** Si en el panel ves datos de Richy, vinieron de
otra parte (por ejemplo, de haberlo ejecutado a mano en tu PC).

### Cómo activarlo (una sola vez)

1. **Llevar el código a `main`.** En GitHub: *Pull requests → New pull request* → base `main`, compare
   `claude/epic-feynman-pxcmqd` → *Create pull request* → *Merge*. Esa rama ya incluye todo lo de Richy (PR #2) más
   Breakout 4h; después puedes cerrar el PR #2.
2. **Crear el secreto.** *Settings → Secrets and variables → Actions → New repository secret*:
   nombre `FIREBASE_SERVICE_ACCOUNT`, valor = **todo el contenido** del JSON de la cuenta de servicio
   (Firebase → Configuración del proyecto → Cuentas de servicio → *Generar nueva clave privada*; ábrelo con el Bloc
   de notas y copia todo). **Nunca** subas ese JSON al repositorio.
3. **Habilitar y probar.** Pestaña *Actions* → si pide confirmación, pulsa *"I understand my workflows, go ahead and
   enable them"*. Elige **breakout-bot** → *Run workflow* → rama `main`. Repite con **richy-bot**.
4. **Comprobar.** En 2–4 minutos cada ejecución debe quedar con ✔ verde. Abre la ejecución → *ciclo*: la primera vez
   verás `Almacén: Firestore | modelo re-entrenado`.
5. **Publicar el panel nuevo.** En PowerShell, en la carpeta del proyecto:

```powershell
firebase deploy --only hosting
```

> Usa **`--only hosting`**. No despliegues las reglas desde el repositorio: el archivo del repo trae el correo de
> ejemplo `TU_CORREO@gmail.com` y te dejaría sin acceso. Tu `firestore.rules` local ya tiene tu correo real.

Después, cada 4 horas GitHub corre los dos bots solo. Limitaciones de GitHub Actions: no es 24/7, los horarios pueden
retrasarse unos minutos y GitHub **desactiva los cron tras 60 días sin actividad** en el repositorio (se reactivan en
la pestaña *Actions*).

---

## 3. ¿Está corriendo el bot? (3 comprobaciones)

1. **En el panel** → pestaña **Breakout 4h**: debe verse un punto **verde** «Último ciclo hace X». Rojo = más de 9 h
   sin escribir (debería escribir cada 4 h).
2. **En GitHub** → *Actions*: debe haber ejecuciones de `breakout-bot` y `richy-bot` con ✔ cada 4 h.
   Si Actions está vacío (0 workflows), el workflow aún no está en `main` (paso 1 de la sección 2).
3. **Desde tu PC**, con la clave de servicio:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="secrets\serviceAccountKey.json"
pip install firebase-admin
python verificar_nube.py
```

Imprime, por cada bot, `OK` (menos de 5 h), `RETRASADO` (5–9 h), `DETENIDO` (más de 9 h) o `SIN DATOS`.

---

## 4. Cómo leer el panel

**Pestaña Breakout 4h**

- **Validación**: resultado de la estrategia en el pasado, *fuera de muestra* y con comisiones. «Último año» es el
  tramo que no se usó para diseñarla.
- **Equity simulado**: el capital de práctica (parte de 25 USDT).
- **Progreso a 100 trades**: con menos no se puede distinguir habilidad de suerte.
- **Profit factor**: ganancia bruta ÷ pérdida bruta. Menor que 1 = pierde dinero; sano: por encima de 1.3.
- **Caída máx.**: la peor caída desde un máximo. Pregúntate si la aguantarías con dinero real.
- **Motivo** del trade: `SL` stop loss · `TP` objetivo · `TIME` cierre a las 24 velas de 4 h · `SL_GAP` el precio saltó el stop.
- **Calculadora**: pones tu capital, tu meta diaria y un rendimiento anual supuesto. Con 16.5 % anual (lo mejor que
  midió el periodo de diseño, **no confirmado**) $25 rinden ~$0.01 al día; para $1 al día harían falta ~$2,200.

**Pestañas Panel / Operaciones**: son de Richy (semáforo «¿Voy bien?», noticias, funding, interruptores por
estrategia). **Ajustes**: tema y sonidos (se guardan solo en tu navegador). **Guía**: resumen de esto dentro del panel.

---

## 5. Rutina recomendada

- **Una vez por semana**: abre el panel, comprueba el punto verde y cuántos trades van. No hace falta más.
- **No cambies parámetros a mitad de camino**: el valor del historial es que nadie lo ajustó mirando resultados. El
  modelo se **re-entrena solo cada 7 días** con datos nuevos (es parte del diseño).
- **No pongas dinero real** por una racha corta buena o mala. Decide con 100+ trades y resultado positivo.
- **No corras el mismo bot en dos sitios a la vez.** Si corres `python paper_trader.py run` en tu PC *sin* `--cloud`,
  se crea un historial **local distinto** del de GitHub Actions. Elige uno (recomendado: Actions).
  Con Richy, además, no lo corras en tu PC con la misma base de datos mientras funcione en Actions.

---

## 6. Uso local (opcional, PowerShell)

Carpeta del proyecto. `python`, no `python3`, en Windows.

```powershell
pip install -r requirements-research.txt
python paper_trader.py train        # entrena el modelo (usa el histórico incluido en data_seed/)
python paper_trader.py run          # procesa velas 4h nuevas, historial local (breakout_state.json)
python paper_trader.py status       # resumen del historial local
python -m streamlit run dashboard.py   # dashboard local (pestaña «Paper Trading»)
```

`python paper_trader.py run --cloud` guarda y publica en Firestore (es lo que hace GitHub Actions; necesita
`GOOGLE_APPLICATION_CREDENTIALS`). Reproducir la validación: `python -m research.run_research` y
`python -m research.report`.

---

## 7. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| Actions vacío («0 workflows») | Los workflows no están en `main` | Sección 2, paso 1 |
| Ejecución roja: «Falta el secreto FIREBASE_SERVICE_ACCOUNT» | No creaste el secreto | Sección 2, paso 2 |
| Ejecución roja con `403` / `PermissionDenied` de Firestore | Firestore no está creado o la cuenta de servicio es de otro proyecto | Crea Firestore en la consola y genera la clave desde **ese** proyecto |
| El panel dice «no tiene permiso para ver el panel» | El correo de `firestore.rules` no es el que usaste para entrar | Pon tu correo en `firestore.rules` y despliega las reglas |
| Panel: «El bot aún no ha publicado nada» | Todavía no hubo ninguna ejecución | Lanza *Run workflow* a mano |
| Punto rojo «Último ciclo hace X h» | El bot dejó de correr | Mira *Actions*; si pasaron 60 días sin actividad, reactiva los workflows |
| `streamlit` no se reconoce (Windows) | El Python de la Microsoft Store no pone `Scripts` en el PATH | `python -m streamlit run dashboard.py` |
| La primera descarga de datos se ve «colgada» | Descarga lenta | Ya no ocurre: el histórico viene en `data_seed/`; solo baja lo nuevo |
| Binance responde 451 | Bloqueo por región | Los datos usan `data-api.binance.vision`; no hace falta nada |

---

## 8. Lo que NO pude verificar desde aquí (hazlo tú)

- **Firestore real, el secreto y el sitio publicado**: probé el almacenamiento con una base de datos **simulada en
  memoria** y el panel en **modo demo**. La primera ejecución real en GitHub Actions es la prueba definitiva.
- **Tu sitio `bot-richy.firebaseapp.com`**: mi entorno no puede abrirlo; no sé qué versión del panel está publicada.
  Hasta que ejecutes `firebase deploy --only hosting`, no tendrá las pestañas nuevas.

---

## 9. Seguridad

- API keys de Binance **sin permiso de retiro** y restringidas por IP, el día que uses dinero real.
- La `apiKey` web del panel es pública por diseño; la clave **de servicio** (JSON) **no**: va solo como secreto de
  GitHub o en `secrets/` (ignorado por git).
- Gestionar dinero de terceros puede requerir registro o licencia según tu país: consúltalo con un abogado antes de
  captar fondos. Un backtest no convence a un inversionista; un historial en vivo verificable, sí.
