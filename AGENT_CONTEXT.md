# AGENT_CONTEXT.md — Sistema de Afiliados Automatizado (Gangas MX)
> **Versión:** 2.1 — Actualizado: 02 Julio 2026
> **PARA CUALQUIER AGENTE DE IA:** Lee este archivo COMPLETO antes de hacer cualquier cosa. Es la fuente de verdad del sistema.

---

## 0. REGLAS ABSOLUTAS PARA AGENTES

1. **NUNCA modifiques código directamente con el Edit tool en `core/telegram_bot.py`** — usa siempre un script Python externo con `$env:PYTHONIOENCODING="utf-8"; python patch_script.py`. El archivo tiene emojis y caracteres Braille que rompen el editor.
2. **Verifica sintaxis SIEMPRE** después de editar cualquier archivo Python: `python -X utf8 -m py_compile <archivo.py>`
3. **Para aplicar parches con strings multi-línea**, usa este patrón de reemplazo seguro (maneja CRLF/LF):
   ```python
   with open(path, "r", encoding="utf-8") as f: content = f.read()
   if "\r\n" in content: target = target.replace("\n", "\r\n")
   content = content.replace(target, replacement)
   with open(path, "w", encoding="utf-8", newline="") as f: f.write(content)
   ```
4. **NO hay scripts del sistema corriendo en Windows**. El bot corre solo en Linux.
5. **NO duplicar métodos** — buscar primero con grep antes de agregar algo nuevo.
6. **Los cambios se sincronizan Linux↔Windows via Syncthing automáticamente**, pero requieren reiniciar el bot en Linux para cargar el nuevo código.
7. **NUNCA ASUMAS LA EXISTENCIA DE UN MÉTODO O SU FIRMA.** Antes de invocar un método (ej. `post_to_facebook`), VERIFICA en el archivo de origen (ej. `facebook_publisher.py`) que el método existe, los parámetros que requiere (ej. si necesita un objeto `page` de Playwright) y su contexto de ejecución (`async`/`sync`, dependencias de estado).

---

## 0.1 CHECKLIST OBLIGATORIO ANTES DE CONFIRMAR IMPLEMENTACIONES (PRE-FLIGHT CHECK)

**Por orden estricta del usuario, ANTES de dar por terminada CUALQUIER implementación, debes auditar tu propio trabajo respondiendo internamente a estas preguntas:**
1. **¿Verificaste TODAS las dependencias de los métodos que llamaste?** (Ej: Si llamas a una función de publicación, ¿le estás pasando los objetos de navegador correctos? ¿Revisaste el código original de esa función para confirmarlo?).
2. **¿Manejaste los errores de forma visible?** (Ej: Si usas `asyncio.create_task`, ¿aseguraste que los errores no se traguen silenciosamente? ¿Los estás notificando a Telegram?).
3. **¿La lógica afecta otras partes del sistema?** (Ej: Si regresas un producto a una cola global como `products_draft.json`, ¿eres consciente de que se publicará en TODAS las redes y no solo en la que falló?).
4. **¿Hiciste pruebas de regresión sintáctica o lógica?** (Ej: Al usar expresiones regulares o replaces masivos, ¿verificaste que no rompiste cadenas adyacentes o variables con el mismo nombre?).
5. **¿El usuario tiene forma de revertir o ver lo que hiciste en la interfaz?**

**Si la respuesta a alguna de estas es NO o "asumí que funcionaba", DETENTE, revisa el código fuente de los conectores y corrige tu implementación ANTES de avisarle al usuario.**

---

## 0.2 LISTA ESTRICTA DE PROHIBICIONES Y OBLIGACIONES (POR ORDEN DEL USUARIO)

### ❌ LO QUE NUNCA DEBES HACER (PROHIBIDO)
1. **NO CREES ARCHIVOS DE "PLAN DE IMPLEMENTACIÓN" (`implementation_plan.md`) NI ARTIFACTS SIMILARES.** El usuario los detesta. No interrumpas el flujo pidiendo aprobaciones formales en artifacts, ejecuta los cambios directamente o pregunta en el chat si tienes dudas puntuales.
2. **NO ASUMAS QUE TERMINASTE SI NO REVISASTE TODO EL CÓDIGO.** No apliques parches rápidos a la interfaz y digas "listo". Busca activamente dónde más impacta (conteos, logs, categorización de IA, base de datos).
3. **NO MODIFIQUES `telegram_bot.py` DIRECTAMENTE.** Siempre usa scripts de Python.

### ✅ LO QUE SIEMPRE DEBES HACER (OBLIGATORIO)
1. **ANALIZA A FONDO ANTES DE ACTUAR.** Haz un mapeo mental (o en tu bloque de pensamiento) de TODO el flujo del sistema antes de escribir código.
2. **APLICA LOS CAMBIOS SIN ESPERAR PERMISO.** Si ya identificaste el error completo y sabes cómo arreglarlo en el ecosistema, escribe los scripts y arréglalo de una vez.
3. **SÉ HONESTO.** Si fallaste en ver una dependencia, admítelo, parchéalo y explica qué hiciste.

---

## 1. DESCRIPCIÓN GENERAL

Sistema automatizado de marketing de afiliados. Scrapea ofertas de Mercado Libre y Amazon, genera links de afiliado y publica en múltiples plataformas usando un bot de Telegram como panel de control central.

- **Canal público:** @cazando_promociones (Telegram)
- **Landing page:** gangasmx.com (Cloudflare Pages / GitHub Pages)
- **Repositorio:** github.com/laloehm/gangas-mx

---

## 2. ENTORNO DUAL (CRÍTICO)

| | Windows (Desarrollo) | Linux VPS (Producción) |
|---|---|---|
| **Ruta** | `C:\Users\eduardo.hernandez\OneDrive - Valtech\Documents\System\` | `/home/laloehm/Desktop/System-Afiliados/` |
| **Rol** | Edición de código, scraping con sesión ML activa | Bot de Telegram corriendo 24/7 como servicio systemd |
| **Sesión** | `storage_state.json` (ML + FB + Pinterest) | `storage_state_linux.json` (FB + Pinterest únicamente) |
| **Procesos activos** | NINGUNO (solo editor de código) | `amazon_bot.service` via systemd |

**Sincronización:** Syncthing sincroniza automáticamente. Los archivos `.env` requieren actualización manual en Linux.

**Reinicio del bot:** Desde Telegram → Panel Principal → MANTENIMIENTO → REINICIAR BOT (usa `os._exit(0)`, systemd lo reinicia).

---

## 3. ESTRUCTURA DE ARCHIVOS

```
System/
│
├── amazon_deal_bot.py          ← Entry point. Flags: --schedule, --login, --dry-run, --visible, URL directa
├── tiktok_generator.py         ← Generador de video básico (fallback, 8s en loop)
├── build_site.py               ← Genera landing page estática desde website_db.json
├── run_scraper_windows.py      ← Rutina de scraping para Windows (Task Scheduler)
├── affiliate_linker.py         ← Convierte URLs raw ML → links meli.la con sesión activa
├── ml_offers_scraper.py        ← Scraper anónimo de la página de ofertas de ML
│
├── core/
│   ├── orchestrator.py         ← Lógica central de publicación (run_publication)
│   ├── telegram_bot.py         ← Panel de control UI (~230KB, ~4500 líneas) ⚠️ editar con script externo
│   ├── scheduler.py            ← Slots horarios de publicación
│   ├── config.py               ← Config global (ConfigMeta hot-reload .env)
│   ├── voice_generator.py      ← TTS con ElevenLabs + normalización de precios en español
│   ├── advanced_video_maker.py ← Renderizado de video premium (moviepy, 6 escenas)
│   ├── message_builder.py      ← Generación de copy para cada plataforma
│   ├── cleanup.py              ← Limpieza automática 3 AM (captures/ y tiktok_videos/ > 7 días)
│   ├── session_manager.py      ← Manejo de storage_state.json
│   ├── manufacturer_scraper.py ← Scraping de imágenes del sitio del fabricante
│   └── utils.py                ← with_retry, filter_blacklist, check_title_similarity
│
├── scrapers/
│   ├── ml_scraper.py           ← scrape_ml_product_headless() + get_gallery_images_headless()
│   └── amazon_scraper.py       ← Scraping headless de Amazon
│
├── publishers/
│   ├── facebook_publisher.py   ← Grupos FB via Playwright
│   ├── facebook_api_publisher.py ← Facebook Page via Graph API
│   ├── telegram_publisher.py   ← Canal Telegram via HTTP API
│   ├── pinterest_publisher.py  ← Pinterest via Playwright
│   ├── tiktok_publisher.py     ← TikTok fantasma via Playwright (tiktok_state.json)
│   └── youtube_publisher.py    ← YouTube Shorts via Playwright (youtube_state.json)
│
├── products_list.json          ← Cola activa (199 productos al 02-Jul-2026)
├── products_draft.json         ← Drafts pendientes de aprobación
├── published_history.json      ← Historial de IDs publicados (evita duplicados)
├── scheduler_config.json       ← Slots activos: {"slots": [9, 12, 15, 18, 21]}
├── user_state.json             ← Estado de redes y modo del bot
├── storage_state.json          ← Sesión Playwright (Windows: ML+FB+Pinterest)
├── storage_state_linux.json    ← Sesión Playwright (Linux: FB+Pinterest)
├── tiktok_state.json           ← Sesión Playwright TikTok
├── youtube_state.json          ← Sesión Playwright YouTube
├── guion.json                  ← Script del video premium activo (6 escenas como JSON)
├── last_published.json         ← Último producto publicado (contexto para IA)
├── website_db.json             ← Base de datos de la landing page (máx 100 productos)
├── CLAUDE.md                   ← Contexto anterior (desactualizado, usar este archivo)
└── AGENT_CONTEXT.md            ← ESTE ARCHIVO (fuente de verdad actualizada)
```

---

## 4. ESTADO ACTUAL DEL SISTEMA (02-Jul-2026)

| Campo | Valor |
|---|---|
| **Productos en cola** | 199 en products_list.json |
| **Slots activos** | Horarios independientes por red (Configurables) usando Arquitectura de Cursores |
| **Facebook Grupos** | ON |
| **Facebook Page** | ON |
| **Telegram Canal** | ON |
| **Pinterest** | OFF |
| **TikTok** | OFF |
| **YouTube** | ON |
| **Web** | ON |
| **Modo video** | normal (fallback básico, se activa premium si hay script) |

---

## 5. FLUJO COMPLETO DE PUBLICACIÓN (`orchestrator.run_publication`)

```
run_publication(url, target_platform, pre_scraped_details, affiliate_override)
│
├── 1. Verificar sesión FB (si es necesario)
├── 2. Datos del producto:
│   ├── Si pre_scraped_details → usar esos datos
│   └── Si no → scrape en vivo (scrape_ml_product_headless o AmazonScraper)
│
├── 3. FUSIÓN DE METADATOS (⭐ añadido Jul-2026):
│   └── Copiar de pre_scraped_details → details:
│       script, gallery_images, bullets, criterios, skip_scrape, force_publish
│
├── 4. Validaciones:
│   ├── Redirección a lista → cancelar, registrar en historial
│   └── Mismatch de título → cancelar, registrar en historial
│
├── 5. Limpieza de título con Gemini (asyncio.to_thread)
├── 6. Auto-captura de imagen (captures/{id}.png)
│
├── 7. Publicación secuencial:
│   ├── Pinterest (hasta 3 reintentos)
│   ├── Facebook Grupos (bloques rotativos 1/3 del total)
│   ├── GENERACIÓN DE VIDEO:
│   │   ├── Logs [ORQUESTADOR VIDEO] → muestra estado de script/galería
│   │   ├── Si details["script"] tiene 6 elementos → FLUJO PREMIUM:
│   │   │   ├── Descarga gallery_images → captures/{id}_gal_{idx}.jpg
│   │   │   ├── Escribe guion.json
│   │   │   ├── voice_generator.py → ElevenLabs → audio_{1-6}.mp3
│   │   │   └── advanced_video_maker.py → tiktok_videos/{id}.mp4
│   │   └── Si falla o no hay script de 6 → FALLBACK BÁSICO:
│   │       └── tiktok_generator.create_tiktok_video() (8s en loop)
│   ├── Facebook Page API (Graph API)
│   ├── Telegram Canal
│   ├── TikTok (tiktok_publisher.py, sesión tiktok_state.json)
│   └── YouTube Shorts (youtube_publisher.py, sesión youtube_state.json)
│
└── 8. Post-publicación:
    ├── Registrar en published_history.json (escritura atómica)
    ├── Eliminar de products_list.json (escritura atómica)
    ├── Actualizar last_published.json
    └── Actualizar website_db.json → rebuild HTML → push GitHub
```

---

## 6. FLUJO DE ENCOLAMIENTO (`telegram_bot._process_queue_command`)

Cuando el usuario manda un URL al bot en modo cola:

```
_process_queue_command(url)
│
├── Scrape del producto (scrape_ml_product_headless o AmazonScraper)
├── Generar ID del producto
├── Auto-captura de screenshot → captures/{id}.png
├── details["screenshot"] = cap_path
│
├── ⭐ NUEVO (Jul-2026): Generar script de 6 escenas:
│   ├── _call_gemini_for_6_lines(details) → lista de 6 strings
│   ├── Si Gemini falla → fallback genérico de 6 líneas
│   └── details["script"] = lines
│
├── ⭐ NUEVO (Jul-2026): Scrapear galería de imágenes:
│   ├── get_gallery_images_headless(page, url) → lista de URLs
│   └── details["gallery_images"] = gallery
│
├── Verificar duplicados contra published_history.json
└── Insertar en products_list.json (al inicio de la lista)
```

---

## 7. PIPELINE DE VIDEO PREMIUM

### Activación automática
- `details["script"]` = lista de exactamente **6 strings** (generados por Gemini al encolar)
- `details["gallery_images"]` = lista de URLs de imágenes del producto

### Métodos involucrados
| Método | Archivo | Línea aprox |
|---|---|---|
| `_call_gemini_for_6_lines(product)` | telegram_bot.py | 1998 |
| `get_gallery_images_headless(page, url)` | scrapers/ml_scraper.py | 275+ |
| `_ensure_top_10_queue_assets()` | telegram_bot.py | 2047 |
| `process_script(script_path, work_dir)` | core/voice_generator.py | — |
| `create_final_video(images, audio_data, out)` | core/advanced_video_maker.py | — |

### Flujo de renderizado
1. Descarga `gallery_images` → `captures/{id}_gal_{idx}.jpg`
2. Escribe `guion.json` con las 6 escenas numeradas
3. `voice_generator.process_script()` → ElevenLabs TTS → `captures/premium_temp/audio_{1-6}.mp3`
4. `advanced_video_maker.create_final_video()` → moviepy → `tiktok_videos/{id}.mp4`
5. Si cualquier paso falla → fallback a `tiktok_generator.create_tiktok_video()`

### Dependencias críticas
- `ELEVENLABS_API_KEY` en `.env`
- `moviepy` instalado en el entorno
- `edge-tts` instalado como fallback de voz (`pip install --break-system-packages edge-tts`)

---

## 8. MENÚ DEL BOT (ESTRUCTURA ACTUAL)

```
PANEL PRINCIPAL
├── PUBLICACION (nav_publicacion)
│   ├── PUBLICAR SIGUIENTE  |  VIDEO PREMIUM
│   ├── FORZAR TIKTOK       |  FORZAR YOUTUBE
│   ├── FORZAR GRUPOS FB    |  FORZAR PAGINA FB
│   ├── FORZAR TELEGRAM     |  FORZAR PINTEREST
│   ├── NORMAL [ON/OFF]     |  BENEFICIOS [ON/OFF]
│   ├── COMPARATIVA [ON/OFF]|  FORZAR WEB
│   └── VOLVER
├── CONTENIDO (nav_contenido)
│   ├── PENDIENTES DE APROBACION
│   ├── PROCESAR DRAFTS (WINDOWS)
│   └── VOLVER
├── REDES (nav_redes)
│   ├── [ON/OFF] FB GRUPOS / FB PAGE / TELEGRAM / PINTEREST / TIKTOK / YOUTUBE / WORDPRESS
│   ├── AÑADIR GRUPO FB
│   └── VOLVER
├── PROGRAMACION (nav_programacion)
│   ├── HORARIO GENERAL (Aplica a redes sin custom)
│   ├── HORARIO [RED] (Submenús para Telegram, FB, TikTok, etc.)
│   │   ├── USAR HORARIO PERSONALIZADO [ON/OFF]
│   │   └── Toggles de horas 8-22 exclusivos de la red
│   └── VOLVER
├── ESTADO (nav_estado)
│   ├── ESTADO GENERAL
│   ├── VER COLA
│   └── VOLVER
└── MANTENIMIENTO (nav_mantenimiento)
    ├── ADMINISTRAR WEB | VACIAR COLA
    ├── REVISAR LOGS    | LIMPIAR LOGS
    ├── REINICIAR BOT
    └── VOLVER
```

**Reglas de UI (NO cambiar sin consultar):**
- SIN EMOJIS en botones — solo texto en MAYÚSCULAS
- Estados: `[ON]` / `[OFF]` (no emojis)
- Padding de ancho: caracteres Braille invisibles `⠀` repetidos 40 veces al final de mensajes de menú — **NUNCA QUITAR**
- Todas las notificaciones de fin de proceso deben incluir `reply_markup=self.get_master_keyboard()`

---

## 9. MÉTODOS CRÍTICOS QUE YA EXISTEN (NO DUPLICAR)

| Método | Archivo | Descripción |
|---|---|---|
| `_call_gemini_for_6_lines(product)` | telegram_bot.py:1998 | Script 6 escenas via Gemini API |
| `_ensure_top_10_queue_assets()` | telegram_bot.py:2047 | Asegura assets para top 10 en cola |
| `_process_queue_command(url)` | telegram_bot.py:4046 | Encola con screenshot + script + galería |
| `_execute_premium_flow(url)` | telegram_bot.py | VIDEO PREMIUM manual desde fabricante |
| `_execute_premium_render(images, dir)` | telegram_bot.py | Render final de video premium |
| `_get_send_session()` | telegram_bot.py | Sesión aiohttp persistente para envío — NUNCA ELIMINAR |
| `_get_poll_session()` | telegram_bot.py | Sesión aiohttp para polling — NUNCA ELIMINAR |
| `run_publication(url, ...)` | orchestrator.py | Publicación completa multi-plataforma |
| `_register_in_history(url, details)` | orchestrator.py | Registra en published_history.json |
| `get_gallery_images_headless(page, url)` | scrapers/ml_scraper.py:275 | Extrae galería de imágenes ML |
| `scrape_ml_product_headless(page, url)` | scrapers/ml_scraper.py:6 | Scrape completo de producto ML |

---

## 10. VARIABLES DE ENTORNO (`.env`)

```bash
# Telegram
TELEGRAM_BOT_TOKEN=          # Token del bot de control
TELEGRAM_CHAT_ID=            # Chat ID del admin (recibe notificaciones)
TELEGRAM_CHANNEL_ID=         # Canal donde se publican las ofertas

# IA
GEMINI_API_KEY=              # Para guiones de 6 escenas y limpieza de títulos
ELEVENLABS_API_KEY=          # Para síntesis de voz en video premium

# Facebook
FB_ACCESS_TOKEN=             # Graph API para Facebook Page
FB_PAGE_ID=                  # ID de la página de Facebook
FB_GROUP_URLS=url1,url2,...  # Grupos (se recargan en caliente via ConfigMeta)

# Web / Git
GITHUB_TOKEN=                # Push automático a gangasmx.com

# Amazon
AMAZON_AFFILIATE_TAG=        # Tag de afiliado Amazon
AMAZON_ACCESS_KEY=
AMAZON_SECRET_KEY=
AMAZON_PARTNER_TAG=

# Mercado Libre
ML_AFFILIATE_ID=             # ID de afiliado ML

# Misc
BLACKLIST_WORDS=funda,mica,case,protector,cable
```

---

## 11. COMANDOS DIAGNÓSTICO

```powershell
# Windows — verificar que no hay procesos del sistema corriendo
Get-CimInstance Win32_Process -Filter "name = 'python.exe'" | Select-Object ProcessId, CommandLine

# Contar productos en cola
python -c "import json; q=json.load(open('products_list.json','r',encoding='utf-8')); print(len(q))"

# Verificar sintaxis de archivos modificados
python -X utf8 -m py_compile core/telegram_bot.py
python -X utf8 -m py_compile core/orchestrator.py
python -X utf8 -m py_compile scrapers/ml_scraper.py

# Ver qué cambió (git diff)
git diff --stat
```

```bash
# Linux — ver logs del bot en tiempo real
journalctl -u amazon_bot -f

# Estado del servicio
systemctl status amazon_bot

# Reiniciar manualmente (o usar el botón en Telegram)
systemctl restart amazon_bot
```

---

## 12. PROBLEMAS CONOCIDOS Y SOLUCIONES

| Problema | Causa | Solución |
|---|---|---|
| Video premium no se genera | `script` o `gallery_images` se pierden en live-scrape | Ya resuelto en orchestrator.py con fusión de metadatos |
| UnicodeEncodeError en PowerShell | Encoding cp1252 | Usar `$env:PYTHONIOENCODING="utf-8"` antes del comando |
| Conflictos `.sync-conflict-*` | Escritura simultánea Syncthing | Eliminar archivos `.sync-conflict-*`, quedarse con el más reciente |
| YouTube sesión expirada | Cookie caduca | Correr `refresh_youtube_session.py` o `import_youtube_cookies.py` |
| ML redirige a otra página | Producto sin stock | Orchestrator detecta mismatch y salta al siguiente |
| GitHub push falla (422) | Conflicto de SHA | Los uploads de archivos son secuenciales — no paralelizar |

---

## 13. HISTORIAL DE CAMBIOS (Septiembre 2026)

### 30-Sep-2026 — Eliminación de Pantalla y Endpoints Legacy de Apify Staging ✅
- **`web-panel/src/app/apify/`**: Eliminada la ruta completa de la pantalla de curación manual obsoleta.
- **`web-panel/src/components/Sidebar.tsx`**: Removido el enlace a `/apify` del menú de navegación.
- **`api/main.py`**: Eliminados los endpoints legacy `/api/apify/products`, `/api/apify/products/{sku}/approve` y `/api/apify/products/{sku}/discard`.
- **Archivos Locales**: Eliminados `apify_products.json`, `apify_discarded.json` y `monitor_apify.sh`.

### 30-Sep-2026 — Ciclos Rotativos Secuenciales de Scraping por Nicho (Round-Robin) ✅
- **`core/apify_refiller.py`**:
  - `get_scraping_keyword(niche, default, advance=False)`: Implementa rotación Round-Robin secuencial basada en términos separados por coma (e.g. `laptops gamer, monitores, herramientas`).
  - Persistencia de cursores en `scraping_cursors.json` mediante escritura atómica (`json_save_atomic`), asegurando persistencia entre reinicios.
  - `is_scraper_enabled(niche, scraper_status)`: Valida el estado del auto-scraper antes de disparar el refill o rotar el cursor. Si un scraper está en pausa, no consume búsquedas ni adelanta el turno.
- **`scrapers/amazon_deals_linux.py`**: Acepta `keyword_override` para scraping en Linux y toma el término activo del ciclo general.
- **`api/main.py`**: Inyecta `_cursors` en `GET /api/config/scraping` y lo filtra en `PUT /api/config/scraping` para no ensuciar la configuración estática.
- **`web-panel/src/app/settings/page.tsx`**: Interfaz visual con píldoras dinámicas por término, flechas de flujo `→`, indicador animado pulsante del término en turno y badge de alerta `⏸️ Auto-Scraper Pausado` si el scraper del nicho no está activo.

### 27-Sep-2026 — Sistema de Expiración de Historial y Re-aprobación a las 3 Semanas (TTL 21 Días) ✅
- **`core/history_manager.py` (NUEVO)**: Módulo centralizado para gestión de historial con marcas de tiempo ISO. Migró `published_history.json` de lista plana a `{identificador: iso_timestamp}`. Rescató timestamps reales de los últimos 200 productos desde `website_db.json` y `last_published.json`, liberando los productos antiguos (>45 días) como elegibles para re-publicación.
- **Filtro de Historial Reciente (`load_recent_history`)**: Integrado en `core/orchestrator.py`, `core/scheduler.py`, `core/apify_refiller.py`, `scrapers/amazon_deals_linux.py`, `api/main.py` y `core/telegram_bot.py`. Los productos solo se consideran duplicados durante su ventana de TTL (por defecto 21 días / 3 semanas).
- **`scraping_config.json` & `web-panel/src/app/settings/page.tsx`**: Añadido parámetro dinámico `"history_ttl_days": 21` con control numérico en el Panel Web.
- **`core/orchestrator.py` & `core/scheduler.py`**: Publicaciones atómicas mediante `register_in_history()` con fecha actual. Eliminado guardado redundante en scheduler que sobreescribía el mapa con listas simples.

### 26-Sep-2026 — Gobierno 100% por Ahorro en Pesos (Eliminación Completa de Filtros de Porcentaje) ✅
- **`core/apify_refiller.py`**: Aprobación automática basada 100% en `ahorro_pesos >= min_ahorro_estricto` (leído dinámicamente de `scraping_config.json`). Eliminado el requisito residual de porcentaje (`disc_val_pct >= min_discount_pct`) y la constante fija `MIN_DISCOUNT_PCT`.
- **`scrapers/amazon_deals_linux.py`**: Aprobación automática basada 100% en `ahorro_pesos >= min_ahorro_estricto`. Eliminada la condición `discount_pct >= min_discount_pct`.
- **`core/utils.py` (`filter_blacklist_product`)**: Adaptado para evaluar exclusivamente el ahorro estricto en pesos y la existencia de descuento real (precio tachado), eliminando cualquier rechazo por porcentaje.
- **Unificación Total**: Toda la arquitectura (Web Panel, Orquestador, Scrapers, Bot) ahora obedece únicamente al Ahorro Mínimo en Pesos (`min_strict_savings`) configurado en el Panel Web.

### 26-Sep-2026 — Unificación de Conteo de Colas y Purga Automática de Productos Publicados ✅
- **`core/orchestrator.py` (`_finalize_publication`)**: Integrado `self._remove_from_queue(enriched.id, enriched.url)` para desalojar físicamente el producto publicado de todas las colas de disco (`products_list.json`, etc.) al terminar la publicación, evitando que se queden como registros zombis acumulados.
- **`core/scheduler.py`**: El bucle de slots ahora purga activamente de los archivos de cola cualquier producto que ya figure en `published_history.json` (además de los descartados), manteniendo los archivos de colas 100% limpios de productos antiguos.
- **`products_list.json`**: Se purgó en disco removiendo 60 productos antiguos que ya estaban en `published_history.json`. La cola en disco se unificó de 66 a los 6 productos reales pendientes, coincidiendo exactamente con la vista del Web Panel.

### 24-Sep-2026 — Corrección Integral de Títulos, Detección de Género, Purga de Zombies y Optimización del Web Panel ✅
- **`core/product_types.py` (`EnrichedProductDetails.to_dict`)**: Se incluyeron `clean_title`, `category`, `description` y `affiliate_link` en la serialización. Previamente los publicadores recibían diccionarios sin `clean_title` y caían de vuelta al título crudo de 150 caracteres.
- **`core/message_builder.py`**:
  - Eliminado el regex destructivo de swap de palabras que convertía "Mesa de estudio para Laptop..." en "Laptop Escritorio...".
  - Priorización directa de `clean_title` de Gemini.
  - Reescrita `_clean_title(raw)` para cortar hasta 75 caracteres preservando el orden gramatical sin preposiciones colgadas.
  - Reescrita `_detect_article(title)` para evaluar el sustantivo rector inicial (head noun), resolviendo el género gramatical ("este" vs "esta").
- **`core/orchestrator.py` & `publishers/twitter_publisher.py`**: Prompt de Gemini reforzado para preservar categoría de producto y fallback suave a `_clean_title` en error 429; sincronizado en Twitter publisher.
- **`core/scheduler.py`**: Auto-purga física de disco (`products_list.json`) para productos descartados (`is_already_discarded`), eliminando productos zombis congelados en cola.
- **`web-panel/src/app/loading.tsx` & `NavigationProgressBar.tsx`**: Añadido skeleton de Suspense y barra de progreso superior animada con fallback anti-bloqueo (2.5s) para navegación instantánea sin sensación de congelamiento.
- **`web-panel/src/components/Sidebar.tsx` & `BottomNav.tsx`**: `prefetch={false}` para evitar saturación de compilación concurrente en modo dev de Next.js.
- **`web-panel/src/app/queues/...` & `next.config.ts`**: Eliminados fallbacks al puerto 8000 (ahorro de 1s de timeout) y agregado `127.0.0.1` a `allowedDevOrigins`.
- **`affiliate_linker.py`**: Manejo limpio de saltos de línea `\n` al parsear enlaces de Mercado Libre.
- **`scrapers/ml_scraper.py`**: Aislamiento estricto de selectores a la tarjeta objetivo (`targetCard`) en páginas sociales `/social/`, erradicando la fuga de selectores que fusionaba el precio actual de un producto con el precio tachado y descuento de otra tarjeta del feed. Validación forzosa `offer < list` en JavaScript.
- **`core/orchestrator.py` & `message_builder.py`**: Rechazo categórico en `_validate_product_for_publication` si `not details.original_price` (oferta expirada) o si `details.original_price <= details.price` (precios invertidos o incoherentes). Salvaguarda en `message_builder.py` que anula `list_price` si alguna vez llegara un precio de oferta mayor al original.

### 23-Sep-2026 — Optimización Integral Anti-Bloqueos, Variabilidad y Priorización por Pesos ✅
- **`scraping_config.json` & `core/orchestrator.py`**: Añadidos `"pasta blanda"` y `"pasta dura"` a `excluded_keywords`. El orquestador unifica la lectura de palabras excluidas desde el JSON con `BLACKLIST_WORDS` del `.env` y especifica el término exacto en la alerta de descarte de Telegram.
- **`core/orchestrator.py` & `tiktok_generator.py`**: Filtro de video estricto (`ahorro >= $250` y `precio >= $300`) protegiendo ElevenLabs y Gemini de consumo innecesario en baratijas.
- **`core/scheduler.py`**: Jitter aleatorio (+30s a +180s) en cada slot programado para eliminar patrones mecánicos.
- **`core/message_builder.py`**: Matrices de copys/ganchos y llamados a la acción variados con seed determinista por ID de producto (cero tokens de Gemini, anti-spam en Facebook/Telegram).
- **`api/main.py` & `web-panel/src/app/queues/...`**: Endpoint `POST /api/queues/{niche}/sort-by-savings` y barra de herramientas visual en el Panel Web con píldoras de ordenación y botón para reordenar la cola físicamente por mayor ahorro en pesos.
- **`core/orchestrator.py` & `core/scheduler.py`**: Barredora automática de bloqueos huérfanos (`_lock_acquired_time > 600s`) con auto-recuperación y alertas a Telegram.
- **`core/telegram_bot.py`**: Corrección estructural del árbol sintáctico de callbacks tras anidamiento roto en `_send_system_status`, re-anclando los 62 botones y comandos de mantenimiento.
- **`api/main.py` & `web-panel/src/app/settings/page.tsx`**: Endpoint `/api/system/restart-all` y botón "REINICIAR SISTEMA COMPLETO" para reciclar API, Bot y Web simultáneamente.

### 12-Ago-2026 — Refuerzo Validación Estricta en Orquestador y Scrapers ✅
- **`core/orchestrator.py`**: Se reparó el bloque de validación anti-N/A. Ahora evalúa forzosamente `live_discount < min_discount` si la promoción de origen (ej. list_price en ML) ha caducado, evitando publicaciones de productos sin ofertas reales.
- **`core/apify_refiller.py` y `scrapers/amazon_deals_linux.py`**: Se corrigió la regla matemática de filtrado inicial. Ahora los productos deben cumplir `discount_pct >= min_discount` O BIEN `ahorro_pesos >= min_strict` de manera exclusiva, evitando productos con 8% de descuento que se colaban por cumplir únicamente el mínimo estricto de ahorro en pesos. Ambos scrapers ahora leen el archivo `scraping_config.json` en tiempo real.

---

## 14. PENDIENTE (próximos pasos)

- [ ] **Reiniciar servicios en Linux** para cargar en memoria el nuevo código (`sudo systemctl restart gangas.target` o botón en `/settings`).
- [ ] **Monitorear próximas publicaciones** para confirmar la coherencia de títulos limpios y la correcta auto-purga de la cola.


4. **PROTOCOLO DE AUDITORIA GLOBAL OBLIGATORIA:** Bajo ninguna circunstancia puedes declarar un trabajo como terminado basandote en un solo archivo. Si el usuario te pide agregar o modificar una entidad, ESTAS OBLIGADO a usar grep_search para auditar: core/config.py, core/telegram_bot.py, core/orchestrator.py, y core/scheduler.py. Si no garantizas el flujo completo desde la UI hasta el motor, has fallado.
---

## 12. REGLAS CRÍTICAS DE ARQUITECTURA (NUEVAS - Ago 2026)

**12.1 NEXT.JS Y LA TRAMPA DE SYNCTHING:**
- NUNCA asumas que un cambio visual o lógico en el frontend de React (web-panel/src/app/...) se verá reflejado automáticamente en Linux solo porque Syncthing sincronizó el archivo .tsx.
- Next.js en el servidor del usuario corre en producción. Debes indicarle al usuario que corra 
pm run build dentro de la carpeta web-panel y luego reinicie los servicios, de lo contrario la UI nunca se actualizará.

**12.2 MANEJO MULTI-COLA Y BORRADO (PRODUCTOS FANTASMA):**
- Existen múltiples archivos de colas (products_list.json, queue_tenis.json, queue_moda.json, etc.). 
- Si modificas métodos de API para borrar, actualizar o mover productos, **ASEGÚRATE DE ITERAR POR QUEUE_FILES**. No asumas que borrar un producto de la cola general lo borra del universo. Si omites esto, crearás productos "fantasma" que rompen los ciclos de los nichos.

**12.3 RESILIENCIA DEL SCHEDULER:**
- El bot no puede detenerse si la IA falla. Nunca insertes llamadas a Gemini (ej. generate_content) dentro del bucle de scheduler.py sin un fuerte 	ry...except que capture la excepción, asigne slot_results[niche] = "❌ Falló publicación", e inmediatamente haga un continue para saltar al siguiente producto válido.
