# Correr los bots en tu servidor Kali (puntual y gratis)

**Por qué:** GitHub Actions no garantiza los horarios y en este repositorio se saltó horas de ejecuciones. Tu servidor
sí es puntual: lanza Richy y Breakout 4h cada hora, y el bot de noticias cada 20 minutos, aunque el servidor haya estado
apagado un rato (al arrancar recupera lo pendiente).

**Tiempo:** ~10 minutos. **Requisitos:** el servidor Kali con internet y encendido 24/7, y tu usuario normal (no root).

> Todo es **paper trading** (sin dinero real). Estos scripts solo leen datos públicos de Binance y escriben en tu
> Firebase, igual que GitHub Actions.

---

## Paso 1. Preparar Kali (en el servidor)

```bash
sudo apt update && sudo apt install -y git python3-venv python3-pip curl util-linux
```

```bash
sudo timedatectl set-ntp true
```

(El reloj sincronizado evita errores de hora con Binance.)

## Paso 2. Bajar el proyecto (en el servidor)

El repositorio es público, no pide contraseña:

```bash
git clone https://github.com/Estebandev-ved/bot-traiding.git ~/bot-traiding
```

## Paso 3. Pasar la clave de Firebase desde tu PC a Kali

La clave `serviceAccountKey.json` **no está en el repositorio** (es secreta): hay que copiarla tú.

1. En el servidor, averigua su IP y activa SSH:

```bash
hostname -I
```

```bash
sudo systemctl enable --now ssh
```

2. En el servidor, crea la carpeta destino:

```bash
mkdir -p ~/.config/richy && chmod 700 ~/.config/richy
```

3. En tu **PC con Windows** (PowerShell). Cambia `kali` por tu usuario de Kali y `IP_DEL_SERVIDOR` por la IP del paso 1:

```powershell
scp C:\Users\Lenovo\Documents\bot-traiding\secrets\serviceAccountKey.json kali@IP_DEL_SERVIDOR:~/.config/richy/serviceAccountKey.json
```

   (Si prefieres no usar `scp`: en el servidor ejecuta `nano ~/.config/richy/serviceAccountKey.json`, pega el contenido
   del JSON y guarda con `Ctrl+O`, `Enter`, `Ctrl+X`.)

4. En el servidor, protege el archivo:

```bash
chmod 600 ~/.config/richy/serviceAccountKey.json
```

## Paso 4. Instalar (en el servidor)

```bash
bash ~/bot-traiding/deploy/kali/instalar.sh
```

Crea el entorno de Python, instala las dependencias, guarda las credenciales en `~/.config/richy/richy.env` (permisos
600) y activa **dos temporizadores** de systemd (de usuario, sin root):

| Temporizador | Qué lanza | Cuándo |
|---|---|---|
| `richy-trading.timer` | Richy y Breakout 4h | cada hora (minuto :05) |
| `richy-news.timer` | Noticias, Fear & Greed y alertas | cada 20 min |

## Paso 5. Probar que funciona (en el servidor)

```bash
bash ~/bot-traiding/deploy/kali/run_cycle.sh news && tail -n 15 ~/bot-traiding/logs/news.log
```

Debes ver una lista de fuentes con ✔ y una línea final con el número de noticias. Luego prueba los otros dos:

```bash
bash ~/bot-traiding/deploy/kali/run_cycle.sh breakout && tail -n 8 ~/bot-traiding/logs/breakout.log
```

```bash
bash ~/bot-traiding/deploy/kali/run_cycle.sh richy && tail -n 8 ~/bot-traiding/logs/richy.log
```

Y comprueba que los temporizadores están armados:

```bash
systemctl --user list-timers
```

## Paso 6. Apagar los horarios de GitHub (importante)

Para que **no corran en dos sitios a la vez** (podrían pisarse el estado). En GitHub → pestaña **Actions** → en la
barra izquierda abre cada workflow (`richy-bot`, `breakout-bot`, `news-bot`) → botón **⋯** (arriba a la derecha) →
**Disable workflow**. Los dejas desactivados; si algún día el servidor falla, los vuelves a activar con **Enable workflow**.

## Paso 7. Verificar desde tu PC

En PowerShell (define la variable en esa ventana):

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\Users\Lenovo\Documents\bot-traiding\secrets\serviceAccountKey.json"
```

```powershell
python verificar_nube.py
```

Los tres deben salir `OK` con «hace unos minutos». En el panel, las píldoras de arriba en verde.

---

## Telegram (opcional)

```bash
nano ~/.config/richy/richy.env
```

Quita el `#` de las dos líneas de Telegram, pega tu token y tu chat_id (ver `GUIA_DE_USO.md`, sección 3), guarda con
`Ctrl+O`, `Enter`, `Ctrl+X`. No hace falta reiniciar nada: se lee en cada ciclo. Si un bot falla, recibirás un aviso
(máximo uno cada 6 h por bot).

## Mantenimiento

| Qué | Comando (en el servidor) |
|---|---|
| Ver el último ciclo de un bot | `tail -n 30 ~/bot-traiding/logs/news.log` (o `breakout.log`, `richy.log`) |
| Ver cuándo corre lo siguiente | `systemctl --user list-timers` |
| Lanzar un ciclo ahora | `systemctl --user start richy-trading.service` o `bash ~/bot-traiding/deploy/kali/run_cycle.sh news` |
| Actualizar a una versión nueva | `cd ~/bot-traiding && git pull && .venv/bin/pip install -q -r requirements-server.txt` |
| Pausar todo | `systemctl --user disable --now richy-trading.timer richy-news.timer` |
| Desinstalar | lo anterior y `rm ~/.config/systemd/user/richy-*` |

Los logs rotan solos a los 5 MB (se conserva el anterior en `.log.1`).

## Si algo falla

| Síntoma | Causa probable | Solución |
|---|---|---|
| `instalar.sh`: «Falta la clave de Firebase» | No copiaste el JSON | Paso 3 |
| `Failed to connect to bus: No medium found` | SSH sin sesión de usuario de systemd | `export XDG_RUNTIME_DIR=/run/user/$(id -u)` y repite |
| El log dice `falta GOOGLE_APPLICATION_CREDENTIALS` | `richy.env` vacío o ruta mala | Revisa `~/.config/richy/richy.env` |
| Los temporizadores no corren tras reiniciar | Falta «linger» | `sudo loginctl enable-linger $USER` |
| Un bot sale `FALLÓ con código 1` | Mira la causa en su `.log` | Pega las últimas 20 líneas del log (sin claves) para revisarlas |
| Una fuente de noticias «no responde» | Ese sitio cambió su RSS | No afecta al resto |

## Seguridad (Kali no viene endurecido para producción)

- Usa tu **usuario normal**, nunca root. El instalador se niega a correr como root.
- La clave de Firebase y `richy.env` quedan en `~/.config/richy/` con permisos 600, fuera del repositorio.
- Cambia las contraseñas por defecto y activa el firewall:

```bash
sudo apt install -y ufw && sudo ufw default deny incoming && sudo ufw allow ssh && sudo ufw enable
```

- Si algún día pasas a dinero real, usa API keys de Binance **sin permiso de retiro** y restringidas a la IP del servidor.
