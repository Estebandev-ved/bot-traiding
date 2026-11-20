#!/usr/bin/env bash
# Instala los bots como servicios de usuario (systemd --user) en Kali/Debian/Ubuntu. No necesita root.
#   bash deploy/kali/instalar.sh
# Antes: deja el JSON de la cuenta de servicio en ~/.config/richy/serviceAccountKey.json (ver deploy/kali/LEEME.md).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CFG="$HOME/.config/richy"; ENV_FILE="$CFG/richy.env"; KEY="$CFG/serviceAccountKey.json"
UNITS="$HOME/.config/systemd/user"
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

say "1/5 Comprobando requisitos"
command -v python3 >/dev/null || { echo "Falta python3: sudo apt install -y python3 python3-venv python3-pip"; exit 1; }
python3 -m venv --help >/dev/null 2>&1 || { echo "Falta venv: sudo apt install -y python3-venv"; exit 1; }
command -v flock >/dev/null || { echo "Falta flock: sudo apt install -y util-linux"; exit 1; }
command -v curl >/dev/null || { echo "Falta curl: sudo apt install -y curl"; exit 1; }
[ "$(id -u)" -ne 0 ] || { echo "No lo ejecutes como root: usa tu usuario normal."; exit 1; }
mkdir -p "$CFG"; chmod 700 "$CFG"
if [ ! -f "$KEY" ]; then
  echo "Falta la clave de Firebase en $KEY"
  echo "Cópiala desde tu PC (ver deploy/kali/LEEME.md, paso 3) y vuelve a ejecutar este script."; exit 1
fi
chmod 600 "$KEY"

say "2/5 Entorno de Python (.venv) y dependencias"
[ -d "$REPO/.venv" ] || python3 -m venv "$REPO/.venv"
"$REPO/.venv/bin/pip" install -q --upgrade pip
"$REPO/.venv/bin/pip" install -q -r "$REPO/requirements-server.txt"

say "3/5 Archivo de credenciales ($ENV_FILE)"
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<ENVEOF
# Credenciales de los bots. Permisos 600. NO subir a git.
GOOGLE_APPLICATION_CREDENTIALS=$KEY
# Telegram (opcional): descomenta y rellena
#TELEGRAM_BOT_TOKEN=
#TELEGRAM_CHAT_ID=
ENVEOF
  echo "Creado. Para activar Telegram edítalo: nano $ENV_FILE"
fi
chmod 600 "$ENV_FILE"

say "4/5 Servicios systemd de usuario"
mkdir -p "$UNITS" "$REPO/logs"
for u in richy-trading.service richy-trading.timer richy-news.service richy-news.timer; do
  sed "s#@REPO@#$REPO#g" "$REPO/deploy/kali/$u" > "$UNITS/$u"
done
systemctl --user daemon-reload
systemctl --user enable --now richy-trading.timer richy-news.timer
loginctl enable-linger "$USER" 2>/dev/null || sudo loginctl enable-linger "$USER" || \
  echo "AVISO: no pude activar «linger»; sin él los timers se detienen al cerrar sesión. Ejecuta: sudo loginctl enable-linger $USER"

say "5/5 Listo. Próximas ejecuciones:"
systemctl --user list-timers --no-pager | grep -E "NEXT|richy" || true
echo
echo "Prueba ahora:  bash $REPO/deploy/kali/run_cycle.sh news && tail -n 20 $REPO/logs/news.log"
