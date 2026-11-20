# 🚀 Suite de Trading Algorítmico Avanzado con Machine Learning

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Binance](https://img.shields.io/badge/Exchange-Binance-yellow.svg)](https://www.binance.com/)
[![ML](https://img.shields.io/badge/Technology-RandomForest-green.svg)](https://scikit-learn.org/)

## 🎯 Visión y Propósito del Proyecto
Este proyecto es un ecosistema de trading automatizado avanzado diseñado para transformar datos en rendimiento constante en el mercado. La filosofía central de este bot es la **Toma de Decisiones Híbrida**: combinando patrones probados de análisis técnico con una sofisticada capa de Machine Learning para eliminar las emociones humanas y maximizar el crecimiento del capital.

El objetivo final es construir un "Motor de Riqueza" escalable que trate el trading como un problema de ingeniería riguroso, centrándose en la preservación del capital mediante una gestión de riesgos estricta, mientras se capturan oportunidades de alta probabilidad en el mercado de criptomonedas.

## ✨ Características Principales
- **🤖 Capa de Inteligencia Artificial**: Utiliza un clasificador `Random Forest` para analizar más de 25 indicadores técnicos y predecir la probabilidad de que la próxima vela sea alcista.
- **📈 Sinergia de Señales**: Ejecuta operaciones solo cuando los Indicadores Técnicos (Cruce de EMA, RSI, MACD) se alinean con predicciones de ML de alta confianza.
- **🛡️ Gestión de Riesgos de Nivel Institucional**:
    - Cálculo automático del tamaño de la posición basado en el balance disponible y el riesgo por operación.
    - Órdenes OCO (One-Cancels-the-Other) para Take-Profit y Stop-Loss simultáneos.
    - **Trailing Stop** dinámico para asegurar ganancias durante movimientos de tendencia.
- **💾 Persistencia de Estado**: Sistema tolerante a fallos que rastrea posiciones abiertas y órdenes pendientes en tiempo real, sobreviviendo a reinicios del sistema.
- **📢 Notificaciones en Tiempo Real**: Bot de Telegram integrado para alertas instantáneas sobre operaciones, métricas de rendimiento y errores del sistema.
- **📊 Analítica de Rendimiento**: Cálculo integrado de Sharpe Ratio, Max Drawdown y Win Rate.

## 🛠️ Stack Tecnológico
- **Binance API**: Python-binance para la interacción con el exchange.
- **Análisis Técnico**: TA-Lib para cálculos de indicadores de alto rendimiento.
- **Machine Learning**: Scikit-Learn (Random Forest) y Joblib para la gestión del modelo.
- **Data Science**: Pandas y NumPy para el procesamiento eficiente de series temporales.
- **Infraestructura**: Python Dotenv para la gestión segura de configuraciones.

## 🚀 Inicio Rápido

### 1. Requisitos Previos
- Python 3.8 o superior.
- [TA-Lib](https://ta-lib.org/) instalado en el sistema.
- Claves de API de Binance (Testnet o Live).

### 2. Instalación
```bash
# Clonar el repositorio
git clone https://github.com/tu-usuario/trading-bot.git
cd trading-bot

# Instalar dependencias
pip install -r requirements.txt
```

### 3. Configuración
Renombra `config.env` y completa tus credenciales:
```env
BINANCE_API_KEY=tu_clave
BINANCE_API_SECRET=tu_secreto
TRADING_MODE=testnet  # ¡Usa 'testnet' primero por seguridad!
SYMBOL=BTCUSDT
RISK_PER_TRADE=0.02
```

### 4. Ejecución del Bot
```bash
# Para ejecutar el bucle principal del bot
python bot-richy.py

# Dashboard futurista (auto-actualización, sonidos, configuración)
streamlit run dashboard.py
```

## 🔬 Validación honesta y Paper Trading (nuevo)

> **📘 Guía completa (activar GitHub Actions, verificar que corre, leer el panel): [`GUIA_DE_USO.md`](GUIA_DE_USO.md).**
> Incluye el **panel renovado** (Resumen, gráficos interactivos, Noticias, Operaciones con CSV, modo claro/oscuro),
> **alertas por Telegram** (`alerts/`, `telegram_probar.py`) y el **bot de noticias** (`news_bot.py`, workflow `news-bot`).
> El bot *Breakout 4h* también se publica en el panel de Firebase (pestañas **Breakout 4h** y **Guía**) y corre solo
> cada 4 h con el workflow `.github/workflows/breakout.yml`. Comprobar que está vivo: `python verificar_nube.py`.

> **Estado real**: tras validar con walk-forward, comisiones y un tramo final sin tocar, **no hay evidencia aún de
> rentabilidad sostenida** (la estrategia candidata ganó +81 % en 2022-nov 2025 pero perdió −9.5 % en el último año).
> Lee `reports/INFORME_VALIDACION.md` antes de arriesgar dinero real o hablar con inversionistas.

```bash
pip install -r requirements-research.txt

python -m research.data                # descarga/actualiza historial público (sin API key)
python -m research.run_research        # experimento completo: diseño + holdout, con costos
python -m research.report              # gráfico y tablas -> reports/

python3 paper_trader.py train          # entrena el modelo con todo el histórico
python3 paper_trader.py run            # procesa velas 4h nuevas (cron: 2 */4 * * *)
python3 paper_trader.py status         # historial en vivo (sin dinero)

streamlit run dashboard.py             # pestaña «Paper Trading»: historial en vivo, validación y calculadora de capital
```

Módulos: `research/features.py` (indicadores sin TA-Lib), `engine.py` (simulador con SL/TP, comisiones, slippage),
`walkforward.py` (meta-labeling ML fuera de muestra), `portfolio.py` (capital compartido, mínimo de orden de Binance),
`paper.py` (motor en vivo; reproduce el backtest trade por trade).

## 📈 Hoja de Ruta (Roadmap)
- [ ] Trading simultáneo de múltiples pares.
- [ ] Integración de Análisis de Sentimiento de noticias y redes sociales.
- [ ] Implementación de Deep Learning (LSTM) para pronósticos de tendencia a largo plazo.
- [ ] Ajuste automático de hiperparámetros para el modelo de ML.

## ⚠️ Descargo de Responsabilidad (Disclaimer)
El trading de criptomonedas implica un riesgo significativo. Este software es para fines educativos y de investigación. El rendimiento pasado no garantiza resultados futuros. Usa un entorno de Testnet antes de comprometer capital real.

---
*Desarrollado con ❤️ como parte de una iniciativa de gestión de patrimonio de alto rendimiento.*
