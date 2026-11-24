# Guía de uso: Richy + Breakout 4h + Noticias + Telegram + panel de Firebase

Todo funciona en **paper trading** (precios reales de Binance, **sin dinero real**). Esta guía explica qué hay,
cómo activarlo, cómo comprobar que corre, cómo recibir avisos por Telegram y cómo leer el panel.

---

## 1. Qué hay en este proyecto

| Pieza | Qué hace | Dónde se ve |
|---|---|---|
| **Richy** (`richy/`) | Bot de tendencia en BTC/USDT 4h con gestión de riesgo, filtro de noticias y funding. Capital simulado de 10,000 USDT. | Panel → **Richy** |
| **Breakout 4h** (`research/`, `paper_trader.py`) | Bot de ruptura de máximos en 5 pares (BTC, ETH, BNB, SOL, XRP) con filtro de aprendizaje automático. Capital simulado de 25 USDT, como tu cuenta real. | Panel → **Breakout 4h** |
| **Portafolio y vigilancia** (`ops/`, `ops_bot.py`) | Cada hora junta a Richy y Breakout bajo un límite de riesgo común (pérdida diaria −3 %, caída −15 %), compara el paper con el backtest (deriva) y avisa si los ciclos se saltan. | Panel → **Resumen** (tarjetas Portafolio y Deriva) |
| **Noticias** (`newsfeed/`, `news_bot.py`) | Cada hora descarga titulares en español e inglés, el índice Fear & Greed, avisa de noticias de riesgo y vigila que los otros bots sigan escribiendo. | Panel → **Noticias** |
| **Telegram** (`alerts/`) | Mensajes a tu móvil: posiciones abiertas, cierres, resumen diario, noticias de riesgo y alertas del sistema. | Tu Telegram; se configura en Panel → **Ajustes** |
| **Panel de Firebase** (`web/index.html`) | Página privada (login con tu Google): `https://bot-richy.firebaseapp.com` | Navegador |
| **Laboratorio de validación** (`research/`) | Descarga datos, simula con comisiones y valida fuera de muestra. Produce `reports/`. | `reports/INFORME_VALIDACION.md` |
| **Dashboard de Streamlit** (`dashboard.py`) | Panel local opcional (NEXUS Terminal). Ya no hace falta si usas el panel de Firebase. | `python -m streamlit run dashboard.py` |
| `bot-richy.py` (original) | Bot antiguo. **No lo uses con dinero**: su backtest tiene fuga de información y no cuenta comisiones. | — |

**Estado honesto de la estrategia Breakout 4h** (detalle en `reports/INFORME_VALIDACION.md`): ganó +81 % entre 2022 y
nov 2025 fuera de muestra, pero **perdió −9.5 % en el último año**. La rentabilidad sostenida **no está confirmada**.
Por eso solo se usa en simulación hasta reunir ~100 trades en vivo (a ~3–7 trades al mes, de 1 a 2 años).

---

## 2. Puesta en marcha en GitHub Actions

Los bots corren solos en GitHub (sin tu PC) con estos workflows, que **solo se ejecutan si están en la rama `main`**:

| Workflow | Frecuencia | Qué hace |
|---|---|---|
| `richy-bot` | cada hora (:41) | Un ciclo de Richy |
| `breakout-bot` | cada hora (:23) | Un ciclo de Breakout 4h (solo procesa las velas de 4h nuevas) |
| `news-bot` | cada 20 min (:11, :31, :51) | Noticias, Fear & Greed, alertas de riesgo y vigilante |
| `ops-bot` | cada hora (:47) | Portafolio (compuerta de riesgo común), deriva paper vs backtest y salud de los ciclos |

**¿Por qué tan seguido si las velas son de 4 h?** Porque GitHub **no garantiza** los horarios de las tareas programadas: bajo
carga retrasa o se salta muchas ejecuciones (en las primeras 15 h de este proyecto corrió una sola vez cada bot en vez de
cada 4 h o cada hora). Cada ciclo es **idempotente** (solo procesa lo nuevo y siempre actualiza el «latido»), así que
intentarlo con más frecuencia solo mejora la probabilidad de que corra a tiempo. Nunca se pierde una vela: si un ciclo se
salta, el siguiente procesa todo lo pendiente. Los minutos de Actions son ilimitados porque el repositorio es público.

### Secretos (Settings → Secrets and variables → Actions → New repository secret)

| Nombre | Obligatorio | Contenido |
|---|---|---|
| `FIREBASE_SERVICE_ACCOUNT` | **Sí** | Todo el texto del JSON de la cuenta de servicio de Firebase |
| `TELEGRAM_BOT_TOKEN` | Para Telegram | Token que te da @BotFather |
| `TELEGRAM_CHAT_ID` | Para Telegram | Tu chat_id (ver sección 3) |

Para copiar el JSON sin abrirlo (PowerShell) y vaciar el portapapeles después:

```powershell
Get-Content C:\Users\Lenovo\Documents\bot-traiding\secrets\serviceAccountKey.json -Raw | Set-Clipboard
```

```powershell
Set-Clipboard -Value " "
```

Nunca subas ese JSON ni el token al repositorio (`secrets/` está ignorado por git).

### Probar cada workflow
Pestaña *Actions* → elige el workflow → *Run workflow* → rama `main`. En 2–4 minutos debe quedar con ✔ verde.
Limitaciones de GitHub: no es 24/7, los horarios pueden retrasarse unos minutos y **desactiva los cron tras 60 días sin
actividad** en el repositorio (se reactivan en la pestaña *Actions*). Si algún día haces el repositorio privado,
ten en cuenta el límite de minutos gratuitos (2,000/mes) y baja la frecuencia de los `cron`.

### Publicar el panel
Desde la carpeta que tenga la última versión del repo (PowerShell). Usa **`--only hosting`**: no despliegues las reglas
desde el repo, traen el correo de ejemplo `TU_CORREO@gmail.com` y te dejarían sin acceso.

```powershell
git pull
```

```powershell
npx -y firebase-tools@latest deploy --only hosting --project bot-richy
```

Las reglas actuales de Firestore ya cubren las colecciones nuevas (`news`, `news_status`, `breakout_*`) para lectura, y
los interruptores del panel se guardan en `strategies/` (donde ya tienes permiso de escritura).

---

## 3. Telegram paso a paso

1. **Crea el bot.** En Telegram busca `@BotFather` → `/newbot` → ponle nombre y usuario → copia el **token**
   (parece `123456789:AA...`). No lo compartas.
2. **Inicia el bot.** Abre tu bot nuevo, pulsa **Iniciar** y escríbele «hola».
3. **Obtén tu chat_id.** En PowerShell, en la carpeta del proyecto (te pedirá el token sin mostrarlo):

```powershell
pip install requests
```

```powershell
python telegram_probar.py --chat-id
```

   Imprime algo como `TELEGRAM_CHAT_ID = 123456789`.
4. **Prueba el envío:**

```powershell
python telegram_probar.py
```

   Debe llegarte «✅ Prueba de Telegram». Si no, el script dice el motivo (token mal copiado, no pulsaste Iniciar…).
5. **Guarda los secretos** `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` en GitHub (sección 2).
6. **Elige qué avisos quieres** en el panel → **Ajustes → Telegram** (interruptores). Se guardan en Firestore y los bots
   los leen en su siguiente ciclo.

### Qué mensajes recibirás
| Mensaje | Cuándo |
|---|---|
| 🟢 Posición abierta (Breakout 4h / Richy) | Al abrir una posición simulada |
| ✅ / 🔴 Ganancia / pérdida | Al cerrar una operación |
| 📊 Resumen diario (Breakout 4h) | Una vez al día, en el primer ciclo desde las 12:00 UTC |
| 🚨 Noticia de riesgo | Hackeos, quiebras, prohibiciones… (máx. 3 por hora) |
| ⏸️ Richy en pausa por noticias / 🛑 Kill switch | Cuando cambia el estado de riesgo de Richy |
| ⚠️ Bot sin actividad / ✅ volvió a la normalidad | Si Richy o Breakout llevan >12 h sin escribir |
| ⚠️ *workflow* falló | Si un workflow termina en rojo |

Diseño para no molestarte: **sin duplicados** (cada evento se avisa una vez), **sin aluvión** al activarlo (el historial
anterior no se envía) y **con reintento** (si Telegram falla, se vuelve a intentar en el siguiente ciclo).
El token nunca aparece en logs ni en errores.

---

## 4. Noticias

- **Fuentes** (RSS públicos): CoinDesk, Cointelegraph, Decrypt (inglés); CriptoNoticias, BeInCrypto ES y DiarioBitcoin
  (español); índice Fear & Greed de alternative.me. Cada fuente falla por separado y el panel muestra cuál no responde.
  (Cointelegraph ES se quitó: su RSS devuelve HTTP 410, retirado. BeInCrypto ES y DiarioBitcoin son candidatas aún sin
  confirmar en producción; si alguna aparece «no responde», no afecta al resto.)
- **Sentimiento** (▲ positiva / ▼ negativa / ● neutral / ⚠ riesgo): heurística por palabras clave en el titular. Es una guía
  para ordenar y filtrar; **no es análisis financiero ni una recomendación**. También detecta las monedas mencionadas.
- Se conservan 7 días de noticias; las más viejas se borran solas.
- **Probar tu red** sin tocar Firestore ni Telegram: `python news_bot.py run --dry` imprime qué fuentes responden.
- Richy usa su propio filtro de riesgo (`richy/sentiment.py`) para **pausar** operaciones; el feed del panel es aparte y no
  abre ni cierra operaciones.

---

## 5. Cómo leer el panel

Arriba, las **píldoras de estado** (Richy, Breakout 4h, Noticias, Telegram): verde = escribió hace poco; ámbar = retraso;
rojo = detenido; gris = nunca ha escrito. Pulsa una para ir a su sección. Umbrales: bots 6 h (ámbar) / 12 h (rojo); noticias 2 h / 6 h.
Un ámbar ocasional es normal (ver sección 2: GitHub se salta ejecuciones).

- **Resumen**: ambos bots, mercado (Fear & Greed), últimas noticias, actividad reciente y estado del sistema.
- **Richy / Breakout 4h**: el detalle de cada bot. En los gráficos pasa el cursor (o el dedo) para ver fecha y valor y
  usa 24h / 7d / 30d / Todo para cambiar el rango.
- **Operaciones**: historial de ambos bots. Pulsa un encabezado para ordenar; filtra por par o resultado; **Exportar CSV**.
- **Noticias**: filtra por riesgo, sentimiento, moneda o idioma, o busca una palabra.
- **Ajustes**: color, modo claro/oscuro/automático, sonidos, interruptores de Telegram y estado de los datos.
- Los avisos emergentes y sonidos saltan cuando entra una operación nueva, se abre una posición o llega una noticia de riesgo.

Cifras: **Profit factor** = ganancia bruta ÷ pérdida bruta (menor que 1 pierde; sano > 1.3). **Caída máx.** = peor caída
desde un máximo. **Sharpe** = ganancia ajustada por riesgo (> 1 es buena). **Motivo**: `SL` stop · `TP` objetivo ·
`TIME` cierre por tiempo · `SL_GAP` el precio saltó el stop. **Fear & Greed**: 0 = miedo extremo, 100 = codicia extrema.

---

## 6. ¿Está corriendo el bot? (3 comprobaciones)

1. **En el panel**: las píldoras de arriba en verde y sin banners rojos.
2. **En GitHub** → *Actions*: ejecuciones recientes con ✔. Si está vacío (0 workflows), los workflows no están en `main`.
3. **Desde tu PC**, con la clave de servicio:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\Users\Lenovo\Documents\bot-traiding\secrets\serviceAccountKey.json"
```

```powershell
pip install firebase-admin
```

```powershell
python verificar_nube.py
```

Imprime, por fuente, `OK`, `RETRASADO`, `DETENIDO` o `SIN DATOS`. Además, el bot de noticias te avisa por Telegram si
Richy o Breakout dejan de escribir (solo mientras `news-bot` siga corriendo).

---

## 7. Rutina recomendada

- **Una vez por semana**: abre el Resumen y comprueba que todo esté verde.
- **No cambies parámetros a mitad de camino**: el valor del historial es que nadie lo ajustó mirando resultados. El
  modelo de Breakout 4h se **re-entrena solo cada 7 días** con datos nuevos (es parte del diseño).
- **No pongas dinero real** por una racha corta buena o mala. Decide con 100+ trades y resultado positivo.
- **No corras el mismo bot en dos sitios a la vez.** Si ejecutas `python paper_trader.py run` en tu PC *sin* `--cloud`, se
  crea un historial **local distinto** del de GitHub Actions. Con Richy, no lo corras en tu PC con la misma base de datos
  mientras funcione en Actions.

---

## 8. Uso local (opcional, PowerShell)

```powershell
pip install -r requirements-research.txt
python paper_trader.py train        # entrena el modelo (usa el histórico incluido en data_seed/)
python paper_trader.py run          # historial local (breakout_state.json)
python paper_trader.py status
python -m pytest tests -q           # pruebas automáticas (pip install pytest ccxt)
```

`python paper_trader.py run --cloud` guarda y publica en Firestore (es lo que hace GitHub Actions). Reproducir la
validación: `python -m research.run_research` y `python -m research.report`.

---

## 9. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| Actions vacío («0 workflows») | Los workflows no están en `main` | Fusiona el PR a `main` |
| Ejecución roja: «Falta el secreto FIREBASE_SERVICE_ACCOUNT» | No creaste el secreto | Sección 2 |
| Ejecución roja con `403` / `PermissionDenied` de Firestore | Clave de otro proyecto o Firestore sin crear | Genera la clave desde el proyecto `bot-richy` |
| No llegan mensajes de Telegram | Faltan los secretos, no pulsaste *Iniciar*, o el interruptor está apagado | `python telegram_probar.py`; revisa Ajustes → Telegram |
| Ajustes → Telegram dice «No configurado» | Los bots aún no vieron `TELEGRAM_BOT_TOKEN`/`CHAT_ID` | Crea los secretos y espera al próximo ciclo (o lanza el workflow a mano) |
| Telegram «Error: …401…» | Token incorrecto | Copia el token de @BotFather otra vez |
| Noticias vacías | `news-bot` aún no corrió, o todas las fuentes fallan | Lanza `news-bot` a mano; mira «Fuentes» en la pestaña Noticias |
| Una fuente sale «no responde» | Ese sitio cambió su RSS o bloquea el acceso | Las demás siguen funcionando; no afecta a los bots |
| El panel dice «no tiene permiso» | El correo de `firestore.rules` no es el que usaste | Pon tu correo en `firestore.rules` y despliega las reglas |
| Aviso ámbar «lleva X h sin actualizar» | GitHub se saltó ejecuciones | Normal; se corrige solo en el siguiente ciclo |
| Píldora roja «hace X h» (más de 12 h) | El bot dejó de correr | Mira *Actions*; reactiva los workflows si pasaron 60 días |
| «Richy en pausa por noticias» | Su filtro vio ≥2 titulares con palabras de riesgo (hackeo, demanda, prohibición…) en 6 h, o Fear & Greed ≤10 / ≥92 | No es un error: no abre posiciones nuevas y se reevalúa en cada ciclo. Pulsa **Ver** para leer los titulares. El aviso muestra de cuándo es el último ciclo |
| `streamlit`/`firebase` no se reconoce (Windows) | Falta el PATH | `python -m streamlit …` / `npx -y firebase-tools@latest …` |
| No ves las pestañas nuevas | Caché del navegador o no desplegaste | `Ctrl+F5` o ventana de incógnito; repite el deploy |

---

## 10. Lo que NO pude verificar desde aquí (hazlo tú)

Probé todo con **simulaciones** (más de 110 pruebas automáticas, una base de datos simulada y un navegador real con Firebase
simulado), pero mi entorno no puede alcanzar estos servicios:

- **Telegram real**: el envío se probó con un doble de prueba. La primera prueba real es `python telegram_probar.py`.
- **Las fuentes RSS reales**: probé el análisis con XML de ejemplo. La prueba real es `python news_bot.py run --dry` o la
  primera ejecución de `news-bot`. Si alguna fuente cambió su dirección, el panel mostrará «no responde».
- **Firestore real y tu sitio publicado**: la primera ejecución de cada workflow y el `deploy` son la prueba definitiva.
- **El ciclo `ops-bot` y la compuerta contra tu Firestore real**: se probaron con una base simulada y con el ciclo real de Breakout
  en archivos locales. La primera ejecución de `ops-bot` (Actions → *Run workflow*) debe crear `portfolio_status/{current,gate,drift,health}`;
  compruébalo en el panel (tarjetas «Portafolio» y «Deriva») o en Firestore. Hasta que exista la compuerta, los bots operan normal.

---

## 11. Novedades: portafolio, deriva, robustez y filtro de régimen

Detalle y números en `reports/INFORME_MEJORAS.md`. Lo importante:

**Qué cambió en lo que ya corría**
- **Breakout 4h ahora no abre posiciones si BTC está bajo su media de 200 días** (filtro de régimen). En el laboratorio redujo la
  caída del último año de −20.5 % a −8.8 %, a cambio de ~14 puntos de retorno en el periodo de diseño. Es un reductor de riesgo,
  **no crea ganancia**: sigue sin haber evidencia estadística de edge.
- **Tamaño por volatilidad y por correlación**: implementados y probados, pero **apagados** (empeoraron el último año).
- **Más pares**: se probó con 10 y empeoró mucho, así que el universo sigue siendo de 5 (`BREAKOUT_SYMS` lo cambia a propósito).
- **Richy**: el semáforo suma el check «¿Es habilidad o suerte? (PSR)» y un resumen de robustez (Sharpe deflactado, Monte Carlo).

**Workflow nuevo: `ops-bot`** (cada hora, mismo secreto `FIREBASE_SERVICE_ACCOUNT`, no necesita secretos nuevos)
1. *Portafolio*: calcula un índice combinado 50/50 de Richy y Breakout. Si pierde ≥ 3 % en el día o cae ≥ 15 % desde su pico,
   escribe una **compuerta** en Firestore (`portfolio_status/gate`) y ambos bots **dejan de abrir posiciones nuevas** (las abiertas
   siguen con sus stops; no se cierra nada). Se reanuda al día siguiente (pérdida diaria) o al recuperar la mitad de la caída.
   **Falla abierta**: si el workflow se cae o la compuerta tiene más de 12 h, los bots operan normal.
2. *Deriva*: con ≥ 20 trades en vivo compara el rendimiento por trade, los aciertos y la caída contra el backtest con la misma
   configuración (`reports/baseline_breakout.json`) y te avisa por Telegram si se desvía.
3. *Salud*: avisa si un bot lleva > 6 h sin escribir (cron saltado) o si Breakout lleva > 8 h de retraso en velas (datos pegados).

**Interruptores en el panel** (pestaña Richy → Estrategias; se guardan en Firestore y los bots los leen en su siguiente ciclo)
- *Breakout 4h: filtro de régimen* — apágalo y vuelve al comportamiento anterior.
- *Portafolio: frenar entradas* — apágalo y el gestor solo observa y avisa, sin frenar a los bots.
- También: `BREAKOUT_OVERLAYS=off` (variable de entorno) apaga el filtro sin tocar el panel.

**Ojo con el historial en vivo**: cada cambio de configuración queda en `state["overlay_history"]` con su fecha. No mezcles
estadísticas de tramos con configuraciones distintas. Si ya tenías una sesión de Breakout en curso, sus trades anteriores
fueron **sin** filtro; los nuevos, **con** filtro.

**Reproducir los análisis**
```bash
python -m research.run_enhancements     # overlays y universo de pares, con PSR/DSR y Monte Carlo (regenera la línea base de deriva)
python -m research.run_portfolio_mix    # ¿combinar Richy y Breakout ayuda?
python -m research.parity_check         # laboratorio y paper trader deben abrir/cerrar los mismos trades
python ops_bot.py run --dry             # prueba local del ciclo de operación, sin nube ni Telegram
```
Si regeneras la línea base (`reports/baseline_breakout.json`), súbela al repositorio: la deriva se compara contra ella.

---

## 12. Seguridad

- API keys de Binance **sin permiso de retiro** y restringidas por IP, el día que uses dinero real.
- La `apiKey` web del panel es pública por diseño; la clave **de servicio** (JSON) y el **token de Telegram** no: solo como
  secretos de GitHub o en `secrets/` (ignorado por git). Si alguno se filtra, revócalo (Firebase / @BotFather → `/revoke`).
- Los enlaces de las noticias solo se abren si empiezan por `http(s)://`, y todo texto externo se escapa antes de mostrarse.
- Gestionar dinero de terceros puede requerir registro o licencia según tu país: consúltalo con un abogado antes de
  captar fondos. Un backtest no convence a un inversionista; un historial en vivo verificable, sí.
