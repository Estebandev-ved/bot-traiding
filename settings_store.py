"""
Configuración compartida entre el dashboard y el bot.
El dashboard escribe `bot_settings.json`; el bot lo relee en cada ciclo.
"""
import json
import os
import tempfile

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot_settings.json')

DEFAULTS = {
    # --- Control ---
    'bot_enabled': True,            # False = el bot no abre operaciones nuevas
    # --- Estrategia / riesgo (los nombres coinciden con las variables de bot-richy.py) ---
    'SYMBOL': 'BTCUSDT',
    'INTERVAL': '1h',
    'RISK_PER_TRADE': 0.02,
    'STOP_LOSS_PCT': 0.03,
    'TAKE_PROFIT_PCT': 0.06,
    'MIN_CONFIDENCE': 0.60,
    'MIN_VOLUME_RATIO': 0.8,
    'MAX_ATR_PCT': 5.0,
    'SLEEP_SECONDS': 1800,
    'TRAILING_STOP_ENABLED': True,
    'TRAILING_STOP_PCT': 0.02,
    'TRAILING_STOP_ACTIVATION': 0.01,
    # --- Dashboard ---
    'initial_balance': 1000.0,
    'refresh_seconds': 5,
    'theme': 'Cyan',                # Cyan | Violeta | Verde | Ámbar
    'sound_enabled': True,
    'sound_volume': 0.5,
    'sound_win': 'Campana',         # Campana | Moneda | Arpegio
    'sound_loss': 'Grave',          # Grave | Alerta | Silencio
    'sound_on_open': True,          # sonido al abrir posición
    'notify_min_profit': 0.0,       # solo suena si |P&L| >= este valor (USDT)
    'daily_loss_limit': 0.0,        # 0 = desactivado; alerta si pérdida del día supera
    'daily_profit_target': 0.0,     # 0 = desactivado; alerta al alcanzar meta
    'max_trades_shown': 50,
}

BOT_KEYS = [k for k in DEFAULTS if k.isupper()]


def load_settings() -> dict:
    data = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            saved = json.load(f)
        for k, v in saved.items():
            if k in DEFAULTS:
                data[k] = v
    except (FileNotFoundError, ValueError, OSError):
        pass
    return data


def save_settings(settings: dict) -> None:
    clean = {k: settings.get(k, v) for k, v in DEFAULTS.items()}
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(SETTINGS_FILE), suffix='.tmp')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)
    os.replace(tmp, SETTINGS_FILE)  # escritura atómica


def apply_to_module(module_globals: dict) -> dict:
    """Aplica al módulo del bot los valores guardados. Devuelve los settings."""
    s = load_settings()
    for k in BOT_KEYS:
        if k in module_globals:
            default = module_globals[k]
            try:
                module_globals[k] = type(default)(s[k]) if not isinstance(default, bool) else bool(s[k])
            except (TypeError, ValueError):
                pass
    return s
