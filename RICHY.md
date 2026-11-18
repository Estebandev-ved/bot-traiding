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
| Datos ccxt (REST, WebSocket, funding, open interest) | `richy/data.py` | **Sin probar contra exchanges reales** |
| Firestore + panel con interruptores por estrategia | `richy/cloud.py`, `web/` | Panel probado en modo demo; Firebase real sin probar |
| TimescaleDB, Grafana, Docker | `infra/`, `docker-compose.yml` | Sin probar |

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
