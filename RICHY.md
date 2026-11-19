# Richy v2: riesgo primero

Paquete `richy/` (el bot anterior `bot-richy.py` sigue intacto).

| Pieza | Archivo | Estado |
|---|---|---|
| Riesgo (1-2%/op, pérdida diaria, exposición, kill switch) | `richy/risk.py` | Probado |
| Backtest con comisiones, slippage, órdenes sin llenar, stops intrabarra | `richy/backtest.py` | Probado |
| Walk-forward (ajusta en train, valida en test no visto) | `richy/backtest.py` | Probado |
| Tendencia+ATR, reversión a la media, grid, arbitraje de funding | `strategies.py`, `backtest.py` | Probado en datos sintéticos |
| Régimen (reglas; LightGBM opcional) que activa una estrategia u otra | `richy/regime.py` | Reglas probadas; LightGBM sin probar aquí |
| Órdenes límite, reintentos sin duplicar, conciliación | `richy/execution.py` | Probado con exchange simulado |
| Datos ccxt: velas reales de Binance a CSV (`python -m richy.download`) | `richy/data.py`, `richy/download.py` | Velas probadas con datos reales. WebSocket, funding y open interest sin probar |
| Firestore + panel con interruptores por estrategia | `richy/cloud.py`, `web/` | Panel probado en modo demo; Firebase real sin probar |
| TimescaleDB, Grafana, Docker | `infra/`, `docker-compose.yml` | Sin probar |

## Resultados con datos reales (Binance, 2023-03 → 2026-11, costos 0.06% + 0.05% por lado)
| Estrategia | BTC 4h | ETH 4h | Veredicto |
|---|---|---|---|
| Tendencia ATR solo largos | +27.4%, caída -11.7%, Sharpe 0.80 | +0.4%, caída -15.6%, Sharpe 0.05 | Defensiva; borde modesto solo en BTC |
| Tendencia largo+corto | +29.2%, Sharpe 0.65 | +10.9%, Sharpe 0.31 | Similar |
| Reversión a la media | -49.9% | -43.4% | **Descartada** |
| Comprar y mantener | +127.4% | +2.0% | |
Walk-forward 4h solo largos: BTC +16.5% fuera de muestra (7 de 13 ventanas positivas), ETH +6.7% (6 de 13).
En 1h la tendencia pierde por costos (-25.6% sin kill switch): por eso el bot usa **4h** por defecto.
Cautelas: elegí 4h y solo largos después de ver que 1h fallaba, así que parte del resultado está sesgado a favor;
son 3.6 años (un ciclo alcista y uno bajista) y los costos asumidos pueden ser pesimistas u optimistas según tu cuenta.

## Datos reales, siempre
El bot en vivo y los comandos `backtest`, `walkforward`, `grid` y `funding` usan **solo datos reales** (velas y funding
de Binance, noticias RSS y el índice Fear & Greed). Si no hay datos, se detienen y te dicen cómo bajarlos; nunca inventan.
Los datos sintéticos existen únicamente dentro de `tests/` para pruebas automáticas.

## Paper trading en vivo (sin dinero)
```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="secrets\serviceAccountKey.json"
python -m richy.cli live --symbol BTC/USDT            # 4h + tendencia solo largos por defecto; si Binance da 451: añade --mirror data-api.binance.vision
```
Cada vela cerrada simula las decisiones del bot con comisiones, slippage y límites de riesgo, y sube a Firestore el
capital, las operaciones y el estado. La sesión arranca con 10,000 USDT simulados y sin posición, y se guarda en
`paper_state.json` (bórralo para empezar de cero). Las señales ya tomadas quedan congeladas: apagar una estrategia
desde el panel solo afecta a las velas nuevas.
Cada ciclo calcula además el **semáforo "¿voy bien?"** (tiempo, operaciones, profit factor, Sharpe, caída máxima y
comparación con comprar y mantener), aplica el **filtro de noticias** (solo pausa al bot; `--no-news` lo apaga) y simula
el **arbitraje de funding** con tasas reales. Binance bloquea futuros en algunas regiones (451): en ese caso el panel lo dice.
`--real` está bloqueado a propósito hasta validar la estrategia.

## Bajar velas reales
```bash
python -m richy.download --symbol BTC/USDT --timeframe 1h --bars 8000
# Si api.binance.com responde 451 (bloqueo por región, p. ej. servidores en EE. UU.):
python -m richy.download --mirror data-api.binance.vision
python -m richy.cli walkforward --csv datos/BTCUSDT_1h.csv
```
Funding (`--funding`) usa `fapi.binance.com`, que Binance también bloquea por región; ejecútalo desde tu PC o un VPS en Asia/Europa.

## Probar
```bash
pip install -r requirements-richy.txt
python -m pytest tests -q
python -m richy.cli backtest --strategy trend      # o meanrev / regime
python -m richy.cli walkforward
python -m richy.cli grid ; python -m richy.cli funding
python -m richy.cli backtest --csv mis_velas.csv   # datos reales: columnas open,high,low,close,volume
```
**Los resultados con datos sintéticos no demuestran nada sobre dinero real.** Antes de meter capital:
baja velas reales (`richy/data.py`), corre `walkforward`, y si el rendimiento fuera de muestra no se sostiene,
no sale a producción. Luego paper trading semanas, y solo después `--real` con poco capital.

## Firebase (lo haces tú; yo no tengo tu cuenta)
1. Consola de Firebase: crea proyecto, activa **Firestore** y **Authentication > Google**.
2. Configuración > Cuentas de servicio > *Generar clave privada* -> guárdala en `secrets/serviceAccountKey.json` (ignorada por git).
3. Configuración > Tus apps > Web: copia el `firebaseConfig` en `web/index.html` (`FIREBASE_CONFIG`).
4. En `firestore.rules` cambia `TU_CORREO@gmail.com` por tu correo. Copia `.firebaserc.example` a `.firebaserc` con tu proyecto.
5. `npm i -g firebase-tools && firebase login && firebase deploy`
6. El bot: `export GOOGLE_APPLICATION_CREDENTIALS=secrets/serviceAccountKey.json`.
   (La `apiKey` web no es secreta; la clave de servicio **sí**.)

## Producción
VPS cerca del exchange (Tokio para Binance) con `docker compose up -d`. API keys **sin permiso de retiro** y
restringidas a la IP del servidor. Alertas: Grafana sobre TimescaleDB y/o el notificador de Telegram existente.

## Funding: resultado con datos reales (BTC, 2025-12 → 2026-11)
Funding medio **+3.5% anual** sobre el nocional; solo 9% de los pagos llegó a 0.01% (el tope). Entrar al inicio y no salir
nunca rindió **+1.46% sobre el capital** (la mitad del capital es margen del corto). El diseño anterior entraba y salía 11 veces
y pagaba 242 en costos por 118 cobrados (-1.24%). Por eso el arbitraje queda **apagado por defecto**: el panel solo
monitorea el funding y avisa cuando el rendimiento esperado sobre el capital supere ~5% anual (umbral orientativo).
`python -m richy.cli funding-sweep` repite el diagnóstico con tus datos.

## Correr gratis en GitHub Actions (sin PC ni VPS)
`.github/workflows/bot.yml` ejecuta un ciclo cada 4 h con `python -m richy.cli live --once`. El estado de la sesión vive en
Firestore (`bot_state/paper`), así que sobrevive entre corridas. Requisitos: (1) el workflow debe estar en la rama por defecto,
porque GitHub solo ejecuta los cron desde ahí; (2) crear el secreto `FIREBASE_SERVICE_ACCOUNT` con el contenido del JSON de la
cuenta de servicio; (3) NO correr a la vez el bot en tu PC con la misma base de datos (se pisarían). Limitaciones: no es 24/7, los
cron pueden retrasarse y GitHub los desactiva tras 60 días sin actividad en repos públicos. El funding (fapi) está bloqueado
desde EE. UU.; el panel mostrará "Sin datos de funding", que no afecta a la tendencia.
