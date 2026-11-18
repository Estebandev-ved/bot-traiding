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

## Paper trading en vivo (sin dinero)
```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="secrets\serviceAccountKey.json"
python -m richy.cli live --symbol BTC/USDT            # si Binance da 451: añade --mirror data-api.binance.vision
```
Cada vela cerrada simula las decisiones del bot con comisiones, slippage y límites de riesgo, y sube a Firestore el
capital, las operaciones y el estado. La sesión arranca con 10,000 USDT simulados y sin posición, y se guarda en
`paper_state.json` (bórralo para empezar de cero). Las señales ya tomadas quedan congeladas: apagar una estrategia
desde el panel solo afecta a las velas nuevas. `--real` está bloqueado a propósito hasta validar la estrategia.

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
