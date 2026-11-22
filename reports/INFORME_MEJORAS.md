# Informe de mejoras (laboratorio honesto, fuera de muestra)

Reproducir: `python -m research.run_enhancements` · `python -m research.run_portfolio_mix` · `python -m research.parity_check`
Datos reales de Binance (espejo `data-api.binance.vision`), costos incluidos (comisión 0.075 % + slippage 0.02 % por lado).
Misma señal, mismos parámetros y mismo walk-forward ML que `INFORME_VALIDACION.md`: **no se re-ajustó nada**.
DISEÑO = 2022-01 → 2025-11-22 · HOLDOUT = últimos 365 días (**ya visto** en el informe anterior).

## Veredicto en tres líneas

1. **Ninguna mejora crea edge.** El Sharpe deflactado (DSR) del diseño es 87 % (< 95 %) y en el holdout el PSR es 23 %:
   sigue sin haber evidencia estadística de que Breakout 4h gane dinero de forma sostenida.
2. **Lo único que el laboratorio respalda es el filtro de régimen** (no abrir si BTC está bajo su EMA200 diaria): baja la caída
   del holdout de −20.5 % a −8.8 % y sube un poco el Sharpe del diseño (1.26 → 1.30), a cambio de retorno (+80.9 % → +67.1 %).
   Es un **reductor de riesgo**, no una fuente de ganancia. Está encendido en producción.
3. **Más pares empeoró todo** (5 → 10 pares: +80.9 % → +28.3 %, caída −8.4 % → −26.0 %, Sharpe 1.26 → 0.43). **No se amplió el universo.**

## 1. Overlays sobre Breakout 4h (5 pares = producción)

| Configuración | Diseño: ret / caída / Sharpe / trades | Holdout: ret / caída / trades | MC caída p95 (diseño) |
|---|---|---|---|
| base (sin overlays) | +80.9 % / −8.4 % / 1.26 / 149 | −9.5 % / −20.5 % / 75 | −16.3 % |
| **régimen BTC EMA200d (PRODUCCIÓN)** | +67.1 % / −8.4 % / **1.30** / 118 | **−5.1 % / −8.8 %** / 25 | **−13.8 %** |
| régimen por amplitud | +47.4 % / −13.2 % / 1.05 / 114 | +4.9 % / −10.3 % / 46 | −16.2 % |
| solo tamaño por volatilidad | +62.4 % / −7.6 % / 1.24 / 149 | −11.1 % / −18.0 % / 75 | −14.0 % |
| solo tamaño por correlación | +74.8 % / −8.0 % / 1.28 / 149 | −10.5 % / −17.7 % / 75 | −15.9 % |
| todo junto | +49.9 % / −7.1 % / 1.30 / 118 | −5.5 % / −7.1 % / 25 | −11.1 % |

Lectura honesta:
- Los tamaños por **volatilidad** y **correlación** cuestan retorno y **empeoran el holdout** (−11.1 % y −10.5 % vs −9.5 %).
  Están implementados y probados (`research/overlays.py`) pero **apagados por defecto**.
- La **amplitud** parece mejor en el holdout (+4.9 %) pero es claramente peor en el diseño (+47 %, caída −13 %): no se eligió.
- Con el filtro de régimen el holdout baja de 75 a 25 trades: menos exposición y menos pérdidas, pero **PSR 23 %**: tampoco aquí hay evidencia de edge.
- Costo real del filtro: ~14 puntos de retorno en el diseño (bloqueó 42 señales por BTC bajo su EMA200; los trades bajan de 149 a 118).

## 2. Más pares (10 en vez de 5: +ADA, LINK, AVAX, DOGE, LTC)

| Universo | Diseño: ret / caída / Sharpe / trades | Holdout: ret / caída |
|---|---|---|
| 5 pares, base | +80.9 % / −8.4 % / 1.26 / 149 | −9.5 % / −20.5 % |
| 10 pares, base | +28.3 % / −26.0 % / 0.43 / 314 | −3.0 % / −21.6 % |
| 10 pares + régimen BTC | +30.4 % / −21.2 % / 0.49 / 250 | +8.8 % / −7.4 % |

Más trades no ayudó: las altcoins añadidas diluyen el edge y quintuplican la caída. El resultado de 5 pares probablemente
contiene **selección de los majors** (ver advertencia 2). `BREAKOUT_SYMS` permite cambiar el universo a propósito, pero no es el valor por defecto.

## 3. Combinar Richy + Breakout (50/50)

| | Diseño: ret / caída / Sharpe | Holdout: ret / caída / Sharpe |
|---|---|---|
| 100 % Richy | +18.8 % / −14.8 % / 0.52 | +4.2 % / −7.7 % / 0.44 |
| 100 % Breakout (régimen) | +67.1 % / −8.0 % / 1.30 | −5.1 % / −8.7 % / −0.57 |
| **50/50** | +41.8 % / **−6.9 %** / 1.14 | −0.5 % / **−6.2 %** / −0.01 |
| pesos por inverso de volatilidad | +41.1 % / −6.9 % / 1.13 | −0.7 % / −6.4 % / −0.05 |

Correlación diaria Richy–Breakout: **+0.33** (diseño) y **+0.52** (holdout). Combinar baja la caída por debajo de la de cada uno,
pero **no mejora el retorno ajustado por riesgo** del mejor de los dos en el diseño. Pesos por inverso de volatilidad ≈ 50/50: se dejó 50/50.
Por eso el gestor de portafolio es un **límite de riesgo común**, no un generador de retorno.

## 4. Robustez estadística (nuevo)

`research/robust.py`: PSR, DSR, Monte Carlo de trades, IC del Sharpe y trades mínimos. Se muestra en el semáforo de Richy (check «PSR»).
Sharpe deflactado con **18 pruebas** (12 de esta corrida + 6 de la primera pasada, ver defecto 1).

## 5. Qué se agregó a producción y qué no

| Mejora | Estado | Por qué |
|---|---|---|
| Filtro de régimen BTC EMA200d | **ON** (interruptor `overlays` en el panel / `BREAKOUT_OVERLAYS=off`) | Única que mejora el riesgo sin empeorar el Sharpe |
| Tamaño por volatilidad / correlación | implementado, **OFF** | Costó retorno y no mejoró el holdout |
| Más pares | **no** (`BREAKOUT_SYMS` opcional) | Empeoró el resultado |
| Gestor de portafolio (pérdida diaria −3 %, caída −15 %) | **ON** (interruptor `portfolio_enforce`) | Límite común; falla abierto; frena entradas, no cierra posiciones |
| Tope de concentración por activo | solo avisa | Bloquearlo alteraría el historial de cada bot |
| Deriva paper-vs-backtest | **ON** (alertas) | Línea base = `reports/baseline_breakout.json` (118 trades, misma configuración que corre) |
| Salud de ciclos (latido 6 h, velas 8 h) | **ON** | Más rápido que el vigilante de 12 h de noticias |
| PSR / DSR / Monte Carlo | **ON** en el semáforo | Distingue habilidad de suerte |

## 6. Defectos propios encontrados (y corregidos)

1. **Los multiplicadores de tamaño se aplicaban antes del tope de 1/3 por posición.** Ese tope casi siempre manda
   (riesgo 2 % / stop ≈ 2.4 % ≈ 83 % > 33 %), así que «solo vol» y «solo corr» no cambiaban nada. Lo vi al escribir el test de correlación.
   Corregido (el multiplicador va **después** del tope) y la primera pasada cuenta como 6 pruebas más en el DSR.
2. El test de paridad (`research/parity_check.py`) confirma que laboratorio y paper trader **abren y cierran exactamente los mismos
   trades y con los mismos tamaños** (211 / 145 / 145 trades idénticos en 3 configuraciones, error de tamaño ~1e-15 desde 2025-01).

## 7. Advertencias (para no engañarnos)

1. **El holdout ya estaba visto.** El filtro de régimen se recomendó en el informe anterior *antes* de esta prueba, pero igual
   cualquier cifra del holdout aquí es ilustrativa. La única validación limpia es **paper trading hacia adelante**.
2. **Múltiples pruebas**: 18 en total; ni siquiera el diseño supera DSR 95 %.
3. **El historial en vivo cambia de régimen de riesgo**: cada cambio de configuración queda en `state["overlay_history"]`; no mezcles estadísticas de tramos con configuraciones distintas.
4. Monte Carlo asume trades independientes; no captura rachas de mercado.
5. El backtest no modela rechazos de órdenes, caídas del exchange ni liquidez extrema.
6. Nada de esto justifica dinero real todavía. La regla del informe anterior sigue vigente: ~100 trades en vivo, 14-30 meses a esta frecuencia.
