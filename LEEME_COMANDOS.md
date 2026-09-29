# 🚀 Manual Rápido de Comandos del Sistema (Local y VPS)

Este es tu manual de referencia para administrar el sistema, reiniciar servicios y controlar el bot.

## 🌟 NUEVO: Reiniciar Todo el Ecosistema a la vez

Se ha configurado un servicio maestro (`gangas.target`) que agrupa la API, el Web Panel y el Bot.
Para que funcione, primero debes habilitarlo en tu servidor Linux copiando los archivos:

```bash
# 1. Copia los archivos actualizados a la carpeta de systemd (en tu servidor Linux)
sudo cp /home/laloehm/Desktop/System-Afiliados/*.service /etc/systemd/system/
sudo cp /home/laloehm/Desktop/System-Afiliados/*.target /etc/systemd/system/

# 2. Recarga systemd para que reconozca los cambios
sudo systemctl daemon-reload

# 3. Habilita el target
sudo systemctl enable gangas.target
```

A partir de ahora, **para reiniciar TODOS los componentes con un solo comando**, ejecuta:

```bash
sudo systemctl restart gangas.target
```
*(Esto reiniciará simultáneamente `gangas_api`, `gangas_web` y `amazon_bot`).*

> 💡 **Desde el Panel Web:**
> También puedes hacer esto sin abrir la terminal yendo a `panel.gangasmx.com/settings` → sección **"Mantenimiento del Sistema"** → botón rojo **"REINICIAR SISTEMA COMPLETO"**.

---

## 💰 Priorizar Productos por Mayor Ahorro ($ MXN)

En el Panel Web (`panel.gangasmx.com/queues/[nicho]`):
1. **Filtrar visualmente la vista:** Usa las píldoras de ordenación rápida (*Cola Real*, *Mayor Ahorro ($)*, *Mayor Dto (%)*, *Menor Precio*).
2. **Reordenar físicamente la cola en el servidor:** Haz clic en **"Reordenar Cola por Mayor Ahorro ($)"** para re-anclar el archivo JSON en Linux y que el bot publique primero los chollos con más dinero de ahorro real.

## 🖥️ Reinicios Individuales (Solo si es necesario)

Si necesitas reiniciar solo una parte del ecosistema sin afectar el resto:

*   **Reiniciar solo el Panel Visual (Frontend Next.js):**
    ```bash
    sudo systemctl restart gangas_web
    ```
*   **Reiniciar solo el Motor de Datos (Backend Python):**
    ```bash
    sudo systemctl restart gangas_api
    ```
*   **Reiniciar solo el Bot Publicador:**
    ```bash
    sudo systemctl restart amazon_bot
    ```

## 📊 Ver Estado y Logs de los Servicios

Para ver si están activos (verde) o caídos (rojo):
```bash
sudo systemctl status gangas.target
```

Para ver los logs en vivo (por ejemplo, del bot):
```bash
sudo journalctl -u amazon_bot -f
```

---

## 🛠️ Reparar Entorno Virtual Corrupto (.venv)

Si Playwright o alguna otra librería de repente deja de funcionar, o si ves errores de `Permission denied` o `invalid metadata entry` al instalar paquetes, significa que **Syncthing mezcló los archivos de Windows con los de Linux**.

Para solucionarlo de raíz y en 30 segundos, debes eliminar y reconstruir el entorno en tu servidor Linux. Ejecuta los siguientes comandos uno por uno:

```bash
# 1. Salir del entorno si estás dentro
deactivate

# 2. Asegurarse de tener la herramienta en Ubuntu
sudo apt install python3-venv -y

# 3. Borrar el entorno corrupto por completo
sudo rm -rf .venv

# 4. Crear un entorno virtual fresco usando el Python del sistema
/usr/bin/python3 -m venv .venv

# 5. Instalar todas las dependencias
.venv/bin/pip install -r requirements.txt

# 6. Reinstalar los binarios del navegador (vital para las capturas)
.venv/bin/playwright install chromium
```

> **[IMPORTANTE]** Para evitar que esto vuelva a suceder, asegúrate de que la carpeta `.venv/` esté dentro del archivo `.stignore` de Syncthing en ambos equipos.

---

## 🔑 Renovar Sesión de Mercado Libre (Cuando el bot falla)

Si el bot te empieza a mandar muchos mensajes de "Error de extracción" con links de Mercado Libre o notas que no está scrapeando las ofertas, significa que **tu sesión caducó o Mercado Libre la bloqueó por seguridad**.

Para renovarla, **NUNCA intentes loguearte desde Linux**, porque te pedirá reconocimiento facial. Sigue estos 3 pasos exactos:

**Paso 1: En tu computadora (Windows)**
Abre una terminal en la carpeta del proyecto y corre el script de login manual:
```bash
python manual_login.py
```
Se abrirá el navegador. Inicia sesión en Mercado Libre, revisa que el panel de Afiliados cargue bien, y **cierra la ventana en la "X"**. Esto guardará la sesión fresca en el archivo `storage_state.json`.

**Paso 2: Espera unos segundos a Syncthing**
Dale unos 5 a 10 segundos para que Syncthing suba el archivo `storage_state.json` desde tu Windows hasta el servidor Linux en la nube.

**Paso 3: Aplica la sesión en tu servidor (Linux)**
Abre tu terminal conectada al servidor Linux (VPS), navega a la carpeta del proyecto y ejecuta este comando para heredar la sesión de Windows al bot de Linux:
```bash
cp storage_state.json storage_state_linux.json
```
*(Opcional: Si el bot sigue fallando después de esto, reinícialo con `sudo systemctl restart amazon_bot` para obligarlo a leer el archivo nuevo).*
