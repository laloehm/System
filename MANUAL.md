# 📖 Manual de Restauración, Respaldos y Uso del Sistema
> **Sistema de Afiliados Automatizado (Gangas MX)**  
> Este manual explica paso a paso cómo restaurar el sistema completo en una computadora nueva en caso de pérdida o migración, cómo generar nuevos respaldos para Google Drive y cómo sincronizar cambios con GitHub.

---

## 📑 Tabla de Contenido
1. [Arquitectura de Respaldos (GitHub + Drive)](#1-arquitectura-de-respaldos)
2. [Guía de Restauración en una PC Nueva (Paso a Paso)](#2-guía-de-restauración-en-una-pc-nueva)
3. [Cómo Generar un Nuevo Respaldo para Google Drive](#3-cómo-generar-un-nuevo-respaldo-para-google-drive)
4. [Cómo Guardar y Subir Cambios a GitHub](#4-cómo-guardar-y-subir-cambios-a-github)
5. [Cómo Arrancar el Sistema en Desarrollo (Windows)](#5-cómo-arrancar-el-sistema-en-desarrollo-windows)
6. [Ecosistema de Producción (Laptop Linux)](#6-ecosistema-de-producción-laptop-linux)
7. [Preguntas Frecuentes y Solución de Problemas](#7-preguntas-frecuentes-y-solución-de-problemas)

---

## 1. Arquitectura de Respaldos

El sistema utiliza una estrategia de respaldo dividida en dos componentes para garantizar **100% de seguridad y cero fugas de contraseñas**:

| Componente | ¿Dónde vive? | ¿Qué contiene? | Visibilidad |
|---|---|---|---|
| **Código Fuente** | **GitHub** (`laloehm/System`) | Código Python, scrapers, APIs, Panel Web (Next.js), scripts y plantillas. | Privado |
| **Secretos y Sesiones** | **Google Drive** (`Respaldo_Privado_*.zip`) | Archivo `.env` (tokens reales), cookies/sesiones de redes sociales (`*_state.json`) y colas de productos. | Privado (Personal) |

---

## 2. Guía de Restauración en una PC Nueva

Si formateaste tu equipo o necesitas trabajar en una computadora completamente nueva, sigue estos **3 pasos**:

### Requisitos previos en la nueva PC:
* **Git:** [git-scm.com/download/win](https://git-scm.com/download/win)
* **Python 3.10 o superior:** [python.org/downloads](https://www.python.org/downloads/) *(marcar la casilla "Add python.exe to PATH")*
* **Node.js (v18 o superior):** [nodejs.org](https://nodejs.org/) *(para el Panel Web Next.js)*

---

### Paso 1: Clonar el repositorio desde GitHub
Abre PowerShell en la carpeta donde deseas guardar el proyecto (ej. `Documents`) y ejecuta:

```powershell
git clone https://github.com/laloehm/System.git
cd System
```

---

### Paso 2: Descomprimir tu Respaldo de Google Drive
1. Ve a tu Google Drive y descarga el archivo más reciente: `Respaldo_Privado_System_*.zip`.
2. Descomprime **todo su contenido directamente dentro de la carpeta `System`** que acabas de clonar.
3. Esto restaurará en segundos:
   - Tu archivo `.env` con todas tus API keys y tokens.
   - Las sesiones activas de navegador (`storage_state.json`, `tiktok_state.json`, `youtube_state.json`, etc.).
   - Las colas actuales de productos y configuraciones de scraping.

---

### Paso 3: Ejecutar el Instalador Automático
En la misma terminal de PowerShell dentro de la carpeta `System`, ejecuta:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

**¿Qué hace este script automáticamente?**
* Crea el entorno virtual de Python (`venv`).
* Instala todas las dependencias requeridas (`requirements.txt`).
* Descarga el navegador Chromium para Playwright.
* Instala los paquetes de Node.js en `web-panel/` (`npm install`).
* Verifica que tu archivo `.env` esté en su lugar.

¡Y listo! Tu entorno estará 100% configurado y listo para operar.

---

## 3. Cómo Generar un Nuevo Respaldo para Google Drive

Siempre que actualices tokens en el `.env`, inicies sesión en nuevas cuentas de redes sociales o quieras tener un punto de restauración fresco:

1. Abre tu terminal en la carpeta `System`.
2. Ejecuta el script generador:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\crear_backup_para_drive.ps1
   ```
3. El script creará automáticamente un archivo `.zip` en tu **Escritorio** con fecha y hora (ej. `Respaldo_Privado_System_20260929_144525.zip`).
4. **Sube ese archivo ZIP a tu Google Drive** y reemplaza o conserva los anteriores.

---

## 4. Cómo Guardar y Subir Cambios a GitHub

Cuando agregues nuevas funcionalidades, corrijas errores o mejores el diseño del Panel Web:

```powershell
# 1. Ver qué archivos cambiaron
git status

# 2. Agregar los cambios (el .gitignore protege automáticamente tus secretos)
git add .

# 3. Crear el commit explicando qué hiciste
git commit -m "Descripción clara de las mejoras realizadas"

# 4. Subir a GitHub
git push
```

---

## 5. Cómo Arrancar el Sistema en Desarrollo (Windows)

Si deseas probar localmente en Windows:

### Para el Panel Web (Next.js):
```powershell
cd web-panel
npm run dev
# Abre en tu navegador: http://localhost:3000
```

### Para la API de FastAPI:
```powershell
.\venv\Scripts\Activate.ps1
uvicorn api.main:app --host 127.0.0.1 --port 8001 --reload
```

---

## 6. Ecosistema de Producción (Laptop Linux)

Recuerda las reglas fundamentales de arquitectura de este proyecto:

* **Windows es para desarrollo:** Se edita el código, se prueban componentes y se hace debug.
* **Linux es producción:** La laptop dedicada ejecuta el orquestador 24/7 (`amazon_bot.service`), la API (`gangas_api.service`) y el panel expuesto con Cloudflare Tunnel.
* **Sincronización:** Los archivos se replican en tiempo real mediante **Syncthing**. Si modificas código en Windows, Syncthing lo copia al instante a Linux.
* **Reinicio de servicios en Linux:** Para que Linux adopte cambios de código Python o variables de entorno:
  ```bash
  sudo systemctl restart gangas.target
  ```
  *(O usando el botón de reinicio dentro de `/settings` en el Panel Web).*

---

## 7. Preguntas Frecuentes y Solución de Problemas

#### P: PowerShell dice que la ejecución de scripts está deshabilitada (`ExecutionPolicy`)
**R:** Ejecuta el script anteponiendo la bandera de bypass:
```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

#### P: `git push` me pide autenticación
**R:** Git for Windows abrirá una pequeña ventana en tu navegador para iniciar sesión en GitHub con un clic. Una vez autorizado, queda recordado permanentemente.

#### P: ¿Por qué no veo mis archivos `.env` o `storage_state.json` en GitHub?
**R:** Están intencionalmente excluidos en [.gitignore](.gitignore) para evitar que tus contraseñas o cuentas de redes sociales queden expuestas. Esos archivos viven exclusivamente en tus computadoras y en tu ZIP privado de Google Drive.
