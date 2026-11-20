# Informe de validación de la estrategia (honesto, fuera de muestra)

Generado con `python -m research.run_research` y `python -m research.report`. Datos: velas públicas de Binance,
5 pares (BTC, ETH, BNB, SOL, XRP), 2020-2026. Costos incluidos: comisión 0.075 % + slippage 0.02 % **por lado**.

## Veredicto en una frase

**Todavía no existe evidencia de que este bot gane dinero de forma sostenida.** Encontré una estrategia con edge
real en 2022-nov 2025, pero en los últimos 12 meses (que no usé para decidir nada) **perdió −9.5 %**. Hoy no se
puede presentar a un inversionista como "algoritmo ganador"; sí se puede empezar a construir el historial que
sí lo convencería (ver "Ruta").

## 1. Lo que encontré

| Estrategia (BTC y 5 pares, comisiones incluidas) | Resultado |
|---|---|
| Cruce EMA9/21 de `bot-richy.py`, 1h, BTC, 6.9 años | **−50 %** (comprar y mantener: +780 %) |
| Pullback RSI, 1h y 4h | pierde, con o sin ML |
| Cruce EMA 4h | pierde, con o sin ML |
| **Ruptura Donchian-48 + EMA200, 4h** | la única con edge en el periodo de diseño |

El ML no crea edge donde la señal base no lo tiene (cruce EMA y pullback pierden igual con ML). Donde sí hay señal
(ruptura/tendencia), el filtro ML reduce el drawdown a la mitad o menos.

### Estrategia candidata (declarada antes de mirar el tramo final)
Ruptura del máximo de 48 velas con precio sobre EMA200, 4h, solo largos spot; SL 2×ATR, TP 4×ATR, máx. 24 velas;
filtro ML (gradient boosting) re-entrenado cada trimestre solo con trades ya terminados; máx. 3 posiciones;
riesgo 2 % por trade. Se eligió el **centro** de la meseta de parámetros, no el máximo.

| Segmento (todo fuera de muestra) | Trades | Retorno | Max DD | Sharpe | Win | Profit factor | Prom./trade | Comprar y mantener |
|---|---|---|---|---|---|---|---|---|
| **Diseño** 2022-01 → 2025-11 | 149 | **+80.9 %** (16.5 %/año) | −8.4 % | 1.27 | 51 % | 1.75 | +1.26 % | +98.5 % |
| **Holdout** últimos 12 meses | 75 | **−9.5 %** | −20.5 % | −0.64 | 36 % | 0.80 | −0.36 % | −41.7 % |

Las 3 variantes de parámetros ganan en diseño y **las 3 pierden en el holdout** (−4.5 %, −9.5 %, −1.8 %).
El año de holdout fue un mercado bajista fuerte (−42 %): la estrategia protegió capital (−9.5 % vs −41.7 %) pero no
generó ganancia. La estrategia es *long-only* de tendencia: gana en tendencias alcistas y sangra en rango/bajista.
Con 75 trades el holdout no es estadísticamente distinguible de cero (p≈0.8), así que tampoco prueba que el edge
haya muerto: simplemente **no está confirmado**.

Gráfico: `reports/equity_primaria.png`. Trades: `reports/trades_primaria_*.csv`.

## 2. Advertencias que debo reportar (para no engañarnos)

1. **Múltiples pruebas**: ~23 configuraciones examinadas en el diseño. Una "ganadora" entre tantas puede ser azar.
2. **Concentración**: en el diseño SOL aportó ~40 % del PnL y los 5 mejores trades ~33 %. Pocos trades grandes.
3. **El holdout ya fue visto**. Cualquier ajuste posterior sobre estos mismos datos lo invalida. La única validación
   nueva posible es hacia adelante (paper trading).
4. **Un error mío corregido**: el simulador dejaba abrir una posición en la misma vela en que otra se cerraba
   (información futura). Al corregirlo, el diseño bajó de +107 % a +81 %. Las cifras de este informe son las corregidas.
5. **Prueba de paridad**: el motor de paper trading reproduce 37/37 trades del backtest y el equity al centavo.
6. El backtest no modela rechazos de órdenes, caídas del exchange ni liquidez en momentos extremos.

## 3. Por qué el `bot-richy.py` original no es confiable tal cual
- El "backtest" predice con un modelo **ya entrenado con esos mismos datos** (fuga de información): se ve mejor de lo real.
- No incluye comisiones ni slippage. Con $25 las comisiones decidirían el resultado.
- La etiqueta "¿sube la próxima vela?" es casi ruido (~50 %); no tiene en cuenta stop, objetivo ni costos.
- Su regla de entrada (cruce EMA) pierde dinero tras costos (tabla de arriba).
- `test_size` temporal sin purga y re-entrenamiento cada 10 ciclos sin validar el resultado.

## 4. La matemática de $1–2 al día

Con el mejor caso medido (16.5 %/año, que el holdout **no** confirma):

| Capital | Ganancia/año a 16.5 % | Por día |
|---|---|---|
| $25 | $4.1 | **$0.011** |
| $2,200 | $365 | $1.00 |
| $4,400 | $730 | $2.00 |

Si el edge real fuera 5-10 %/año, hacen falta $3,650–$14,600. Con $25, el mínimo de Binance ($5 por orden) obliga
además a limitar a ~3 posiciones de ~$8. **No hay forma honesta de obtener $1–2/día con $25**; apalancarlo para
lograrlo liquida la cuenta (con ~2 %–3 % de trade perdedor a 20×).

## 5. Ruta recomendada (lo que sí convence a un inversionista)

1. **Paper trading en vivo ya**, sin dinero: `python3 paper_trader.py run` cada 4 h (cron). Genera un registro real,
   con precios reales, que nadie puede acusar de sobreajustado.
2. **Paciencia estadística**: la estrategia hace ~3-7 trades/mes. Hacen falta ~100 trades para distinguir habilidad de
   suerte → entre **14 y 30 meses**. Para acortarlo: añadir más pares (esto sí se puede probar en el laboratorio).
   60 días (≈10 trades) no demuestran nada.
3. **Solo después** de resultados positivos en paper (y drawdown tolerable), pasar a dinero real con el capital que
   puedas perder, y llevar un registro con extractos del exchange.
4. **Para inversionistas**: lo que piden es historial verificado (≥6-12 meses, extractos), drawdown máximo y por qué
   funciona la estrategia — no un backtest. Gestionar dinero de terceros puede requerir registro/licencia según tu
   país: consúltalo con un abogado antes de captar fondos.
5. **Mejoras de investigación** (en el laboratorio, no sobre el holdout ya visto): más pares/temporalidades,
   detección de régimen (no operar en mercado bajista), cortos vía futuros con apalancamiento bajo.
