#!/usr/bin/env bash
# Un ciclo de un bot en el servidor.   Uso: run_cycle.sh richy|breakout|news
#  - Carga las credenciales de ~/.config/richy/richy.env (chmod 600; fuera del repositorio).
#  - No se solapa consigo mismo (flock) y se corta a los 10 min (timeout).
#  - Registra en logs/<bot>.log (rota a los 5 MB) y, si falla, avisa por Telegram (máx. 1 aviso cada 6 h por bot).
#  - DRY_RUN=1 muestra qué ejecutaría sin ejecutar nada.
set -uo pipefail
JOB="${1:?uso: run_cycle.sh richy|breakout|news}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${RICHY_ENV_FILE:-$HOME/.config/richy/richy.env}"
LOG_DIR="$REPO/logs"; mkdir -p "$LOG_DIR"; LOG="$LOG_DIR/$JOB.log"
if [ -f "$LOG" ] && [ "$(stat -c%s "$LOG")" -gt 5242880 ]; then mv -f "$LOG" "$LOG.1"; fi
exec >>"$LOG" 2>&1
echo "=== $(date -u +%FT%TZ) $JOB ==="

set -a; [ -f "$ENV_FILE" ] && . "$ENV_FILE"; set +a
cd "$REPO"
exec 9>"/tmp/richy-$JOB-$(id -u).lock"
flock -n 9 || { echo "ya hay un ciclo de $JOB en curso; salgo"; exit 0; }

PY="$REPO/.venv/bin/python"
case "$JOB" in
  richy)    CMD=("$PY" -m richy.cli live --symbol BTC/USDT --timeframe 4h --mirror data-api.binance.vision --once) ;;
  breakout) CMD=("$PY" paper_trader.py run --cloud) ;;
  news)     CMD=("$PY" news_bot.py run --cloud) ;;
  *) echo "trabajo desconocido: $JOB"; exit 2 ;;
esac
if [ "${DRY_RUN:-0}" = 1 ]; then echo "DRY_RUN: ${CMD[*]}"; exit 0; fi
if [ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] || [ ! -f "${GOOGLE_APPLICATION_CREDENTIALS}" ]; then
  echo "ERROR: falta GOOGLE_APPLICATION_CREDENTIALS o el archivo no existe (revisa $ENV_FILE)"; exit 3
fi

timeout 600 "${CMD[@]}"; RC=$?
if [ $RC -ne 0 ]; then
  echo "FALLÓ con código $RC"
  STAMP="/tmp/richy-$JOB-$(id -u).alert"
  if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ] && { [ ! -f "$STAMP" ] || [ $(( $(date +%s) - $(stat -c %Y "$STAMP") )) -gt 21600 ]; }; then
    curl -sS -m 20 -o /dev/null "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
      --data-urlencode "text=⚠️ El bot ${JOB} falló en el servidor (código ${RC}). Mira logs/${JOB}.log" >/dev/null 2>&1 && touch "$STAMP"
  fi
fi
exit $RC
