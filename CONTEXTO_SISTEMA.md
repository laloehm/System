# CONTEXTO COMPLETO DEL SISTEMA — Sistema-Afiliados (Gangas MX)
**Generado:** 2 Julio 2026 | **Actualizado:** 22 Julio 2026 | **Versión:** 3.1 (Web Panel Next.js + Arquitectura SEO Artículos)

> **INSTRUCCIÓN PARA LA IA:** Este archivo contiene todo el contexto del proyecto. Léelo completo antes de realizar cualquier acción. La regla más importante es que **NO SE MODIFICA CÓDIGO SIN LEER ESTE ARCHIVO PRIMERO.**

---

## 1. DESCRIPCIÓN DEL PROYECTO

Sistema automatizado de marketing de afiliados que publica ofertas de Mercado Libre y Amazon en múltiples plataformas (Telegram, Facebook Grupos, Facebook Page, TikTok, YouTube Shorts, Pinterest, Web) usando un bot de Telegram como panel de control.

**Nombre del canal:** @cazando_promociones  
**Página web:** gangas-mx (Cloudflare Pages, GitHub: laloehm/gangas-mx)

---

## 2. ENTORNO DUAL Y ARQUITECTURA (CRÍTICO — LEER SIEMPRE)

El sistema opera mediante una sincronización en tiempo real usando **Syncthing** entre dos máquinas físicas, lo que permite desarrollar en una y ejecutar en otra sin fricciones.

| Entorno | Ruta | Propósito |
|---|---|---|
| **Windows** (Laptop de desarrollo) | `C:\Users\eduardo.hernandez\OneDrive - Valtech\Documents\System\` | Edición de código (VSCode), debugging, y scraping inicial que requiere sesión gráfica (ML). |
| **Linux** (Laptop de producción) | `/home/laloehm/Desktop/System-Afiliados/` | Es una laptop dedicada exclusivamente a correr el sistema (NO ES UN VPS). Aquí se ejecutan los servicios finales. |

### 2.1 Flujo de Ejecución en Linux (Laptop Producción)
El usuario no usa gestores de procesos como PM2. El ecosistema en Linux se mantiene vivo mediante la siguiente estructura:

1. **El Bot Principal (Orquestador):** Corre de forma invisible como un servicio nativo de Linux (Systemd) bajo el nombre `amazon_bot.service`.
2. **Las 3 Consolas Manuales:** El usuario mantiene 3 ventanas de terminal abiertas permanentemente en la laptop Linux para:
   - **Consola 1 (API):** `uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload`
   - **Consola 2 (Panel Web):** `npm run dev` (dentro de `web-panel/`)
   - **Consola 3 (Túnel):** El servicio de Cloudflare Tunnel (`cloudflared`) que expone el panel al mundo.

### 2.2 Gestión de Logs (El puente Windows-Linux)
- El bot (al correr en Systemd) escribe sus logs en el diario del sistema (`journalctl -u amazon_bot.service`).
- Para asegurar la compatibilidad multiplataforma y evitar que los logs se pierdan si se ejecuta manualmente, `amazon_deal_bot.py` usa una clase `DualLogger` que intercepta `sys.stdout` y crea una copia en un archivo llamado **`bot.log`**.
- El endpoint del panel web `/api/bot/logs` es inteligente: intenta leer de `journalctl` (si detecta Linux) o de `bot.log`/`nohup.out` como respaldo, permitiendo que el visor de logs del Frontend funcione perfecto sin importar cómo se ejecutó el bot.

**REGLA DE ORO Windows:** No hay scripts corriendo en background en Windows. El bot corre solo en Linux. Las ediciones hechas en Windows se sincronizan a Linux, donde impactan de inmediato a la API/Panel (por el hot-reload), pero requieren reiniciar `amazon_bot.service` para que el bot adopte el nuevo código de Python.

---

## 3. ARQUITECTURA DE ARCHIVOS CLAVE

```
System/
├── amazon_deal_bot.py          ← Punto de entrada (--schedule)
├── core/
│   ├── orchestrator.py         ← Lógica de publicación multi-plataforma
│   ├── scheduler.py            ← Slots horarios de publicación
│   ├── telegram_bot.py         ← Panel de control UI (~230KB, ~4500 líneas)
│   ├── config.py               ← Config global (ConfigMeta hot-reload .env)
│   ├── voice_generator.py      ← TTS ElevenLabs + normalización precios en español
│   ├── advanced_video_maker.py ← Renderizado video premium (moviepy)
│   ├── message_builder.py      ← Copy para cada plataforma
│   ├── cleanup.py              ← Limpieza automática 3 AM
│   ├── session_manager.py      ← storage_state.json para Playwright
│   └── manufacturer_scraper.py ← Scraping imágenes del fabricante
├── scrapers/
│   ├── ml_scraper.py           ← Scraping headless Mercado Libre
│   └── amazon_scraper.py       ← Scraping headless Amazon
├── publishers/
│   ├── facebook_publisher.py   ← FB Grupos (Playwright)
│   ├── facebook_api_publisher.py ← FB Page (Graph API)
│   ├── telegram_publisher.py   ← Canal Telegram
│   ├── pinterest_publisher.py  ← Pinterest
│   ├── tiktok_publisher.py     ← TikTok fantasma (tiktok_state.json)
│   └── youtube_publisher.py    ← YouTube Shorts (youtube_state.json)
├── tiktok_generator.py         ← Video básico fallback (8s loop)
├── build_site.py               ← Landing page estática + Generador Artículos SEO
├── web-panel/                  ← Aplicación Next.js para Panel de Administración Web
├── products_list.json          ← Cola (199 productos al 02-Jul-2026)
├── products_draft.json         ← Drafts pendientes
├── published_history.json      ← Historial IDs publicados
├── scheduler_config.json       ← Slots: [9, 12, 15, 18, 21]
├── user_state.json             ← Estado redes/modo bot
├── storage_state.json          ← Sesión Playwright Facebook/Pinterest
├── tiktok_state.json           ← Sesión TikTok
├── youtube_state.json          ← Sesión YouTube
└── guion.json                  ← Script video premium activo (6 escenas)
```

---

## 4. ESTADO ACTUAL DEL SISTEMA (02-Jul-2026)

### Cola: 199 productos listos en products_list.json
### Redes activas:
- facebook: ON, fb_page: ON, telegram: ON, pinterest: OFF, tiktok: OFF, youtube: ON, web: ON
### Slots: 9h, 12h, 15h, 18h, 21h (hora México UTC-6)

---

## 5. FLUJO DE VIDEO PREMIUM (ESTABILIZADO — Jul 2026)

### Activación
- `details["script"]` = lista de exactamente **6 strings** (generados por Gemini)
- `details["gallery_images"]` = lista de URLs de imágenes

### Problema resuelto
El live-scraping descartaba `script` y `gallery_images` de la cola. Solución: fusión de metadatos en `orchestrator.py` después del scrape:
```python
if pre_scraped_details:
    if pre_scraped_details.get("script") and not details.get("script"):
        details["script"] = pre_scraped_details["script"]
    if pre_scraped_details.get("gallery_images"):
        details["gallery_images"] = pre_scraped_details["gallery_images"]
```

### Al encolar (telegram_bot.py _process_queue_command)
Ahora genera automáticamente:
1. Script de 6 escenas via `_call_gemini_for_6_lines()` (línea 1998)
2. Galería de imágenes via `get_gallery_images_headless()`

### Pipeline de renderizado
1. Descarga gallery_images → captures/{id}_gal_{idx}.jpg
2. Escribe guion.json
3. voice_generator.py → ElevenLabs → captures/premium_temp/audio_{1-6}.mp3
4. advanced_video_maker.py → moviepy → tiktok_videos/{id}.mp4
5. Si falla → fallback a tiktok_generator.create_tiktok_video()

---

## 6. REGLAS DE CODIFICACIÓN (MANDATORIAS)

### Para editar telegram_bot.py
```bash
# SIEMPRE usar script .py externo
$env:PYTHONIOENCODING="utf-8"; python patch_script.py
# Verificar sintaxis después
python -X utf8 -m py_compile core/telegram_bot.py
```
El archivo tiene emojis y caracteres Braille que rompen el Edit tool directo.

### Para aplicar parches (manejar CRLF)
```python
with open(path, "r", encoding="utf-8") as f:
    content = f.read()
if "\r\n" in content:
    target = target.replace("\n", "\r\n")
content = content.replace(target, replacement)
with open(path, "w", encoding="utf-8", newline="") as f:
    f.write(content)
```

### UI del bot
- SIN EMOJIS en botones — solo texto MAYÚSCULAS
- Estados: [ON] / [OFF]
- Padding: caracteres Braille invisibles (40x) — NO QUITAR
- Notificaciones largas terminan con `reply_markup=self.get_master_keyboard()`

---

## 7. MÉTODOS EXISTENTES (NO DUPLICAR)

| Método | Línea aprox | Descripción |
|---|---|---|
| `_call_gemini_for_6_lines(product)` | 1998 | Script 6 escenas via Gemini |
| `_ensure_top_10_queue_assets()` | 2047 | Asegura assets para top 10 en cola |
| `_process_queue_command(url)` | 4046 | Encola producto con script y galería |
| `_execute_premium_flow(url)` | — | VIDEO PREMIUM manual desde fabricante |
| `_execute_premium_render(images, dir)` | — | Render final video premium |
| `_get_send_session()` | — | Sesión aiohttp persistente (NUNCA ELIMINAR) |
| `_get_poll_session()` | — | Sesión aiohttp polling (NUNCA ELIMINAR) |
| `run_publication(url, ...)` | orchestrator.py | Publicación completa multi-plataforma |

---

## 8. SISTEMA DE CINCO COLAS Y NICHOS

El sistema maneja cinco nichos independientes, cada uno con su propia cola, grupos de Facebook y canal de Telegram.

### Colas y archivos

| Nicho | Tag interno | Archivo de cola | Fuente de productos |
|---|---|---|---|
| General | `[CAT:GENERAL]` | `products_list.json` | Apify "tecnologia" + Amazon scraper |
| Bebés | `[CAT:BEBES]` / `"baby"` | `products_list_baby.json` | Apify "bebes" |
| Mascotas | `[CAT:MASCOTAS]` / `"pets"` | `products_list_pets.json` | Apify "perros" |
| Tenis | `[CAT:TENIS]` / `"tenis"` | `queue_tenis.json` | Manual / importación |
| Moda | `[CAT:MODA]` / `"moda"` | `queue_moda.json` | Manual / importación |

> **Nota:** Tenis y Moda no tienen refill automático de Apify — se llenan manualmente con `import_apify.py` o importando datasets.

### Redes activas por nicho

```json
// user_state.json → active_networks
{
  "facebook": true,           // Grupos generales de FB
  "facebook_bebes": true,     // Grupos de bebés en FB
  "facebook_pets": true,      // Grupos de mascotas en FB
  "facebook_tenis": true,     // Grupos de tenis en FB
  "facebook_moda": true,      // Grupos de moda en FB
  "fb_page": true,            // Página de FB (Graph API)
  "telegram": true,           // Canales Telegram (routing automático por nicho)
  "pinterest": true,
  "web": true
}
```

El scheduler lee esto antes de cada slot y arma `networks_scheduled`. El orchestrator filtra los grupos de FB según el nicho del producto — un producto de bebés nunca toca los grupos de mascotas ni generales.

### Routing de Telegram por nicho

| Nicho | Variable .env | Canal destino |
|---|---|---|
| General / Amazon | `TELEGRAM_CHANNEL_ID` | Canal general |
| Bebés | `TELEGRAM_CHANNEL_BABY_ID` | Canal bebés |
| Mascotas | `TELEGRAM_CHANNEL_PETS_ID` | Canal mascotas |
| Tenis | `TELEGRAM_CHANNEL_ID` (general) | Canal general (sin canal propio) |
| Moda | `TELEGRAM_CHANNEL_ID` (general) | Canal general (sin canal propio) |

### Bloques de FB por nicho

Cada nicho tiene su propio contador de bloque rotativo guardado en `user_state.json`:

| Nicho | Variable de split | Variable de índice |
|---|---|---|
| General | `fb_split_blocks` | `fb_gen_block_index` |
| Bebés | `fb_bebes_split_blocks` | `fb_bebes_block_index` |
| Mascotas | `fb_pets_split_blocks` | `fb_pets_block_index` |
| Tenis | `fb_tenis_split_blocks` | `fb_tenis_block_index` |
| Moda | `fb_moda_split_blocks` | `fb_moda_block_index` |

Ejemplo: 9 grupos + `fb_split_blocks: 3` → publica en 3 grupos por slot, rota al siguiente bloque en el siguiente slot.

### Videos — nichos excluidos

Los productos de bebés y mascotas **no generan video**. La condición en `telegram_bot.py`:
```python
is_no_video_niche = niche in ("[CAT:BEBES]", "baby", "[CAT:MASCOTAS]", "pets")
```

---

## 9. FLUJO DE LLENADO DE COLAS (AUTOMÁTICO)

**Todo el llenado de colas ocurre en Linux sin intervención en Windows.**

### 9.1 MercadoLibre — vía Apify

**Archivo:** `core/apify_refiller.py`  
**Actor Apify:** `karamelo~mercadolibre-scraper-espanol-castellano`

#### Cuándo se activa
El `scheduler.py` llama `check_and_refill(orchestrator)` en cada slot horario como tarea en segundo plano (`asyncio.create_task`). Se activa si:
- La cola del nicho tiene **menos de 10 productos listos** (con `meli.la`)
- Han pasado al menos **24 horas** desde el último refill de ese nicho

#### Qué hace
1. Lanza el actor de Apify con la keyword del nicho y 2 páginas de resultados
2. Espera hasta 15 minutos a que el actor termine
3. Descarga los items del dataset
4. Filtra: valida contra `scraping_config.json` (ahorro mínimo en pesos `$400 MXN`, min 15% de descuento, o >=$1,000 de ahorro con >=10%)
5. Deduplica contra la cola actual e historial de publicados
6. Guarda los productos en la cola con `review_status: "pending_affiliate"`
7. Manda notificación a Telegram con el resumen + **un mensaje por cada producto** con la URL de ML

#### Estado de los productos importados
Los productos de Apify llegan con la URL directa de ML (ej. `https://articulo.mercadolibre.com.mx/MLM-XXXXX`). El campo `affiliate_url` contiene esa URL cruda. El scheduler los **ignora** hasta que tengan un link `meli.la`.

#### Flujo para activar el link de afiliado
```
Bot Telegram manda:
  🔗 Pendiente de afiliado [general]
  📦 "Laptop HP 15 pulgadas..."
  https://articulo.mercadolibre.com.mx/MLM-XXXXX
  Responde con el link meli.la

Usuario:
  1. Abre el link de ML
  2. Genera el link meli.la en el sitio de ML
  3. Manda el link meli.la al bot

Bot detecta el meli.la:
  → Busca el primer producto pending_affiliate en cola (general → bebés → mascotas)
  → Actualiza affiliate_url con el meli.la
  → Elimina review_status
  → Confirma: "✅ Link asignado [general] — Producto listo para publicarse"
```

El handler en `telegram_bot.py` detecta links `meli.la` recibidos en modo normal (sin modo cola) y ejecuta `_update_pending_affiliate()`, que actualiza el primer pendiente en orden FIFO.

#### Variables .env para keywords de Apify
```
APIFY_API_TOKEN=...
APIFY_KEYWORD_GENERAL=tecnologia   # default: "tecnologia"
APIFY_KEYWORD_BABY=bebes           # default: "bebes"
APIFY_KEYWORD_PETS=perros          # default: "perros"
```

---

### 9.2 Amazon — scraper propio en Linux

**Archivo:** `scrapers/amazon_deals_linux.py`  
**Activación:** Automática desde `apify_refiller.py` cuando la cola **general** baja de 10 productos

#### Qué hace
1. Abre `amazon.com.mx/deals` con Playwright headless
2. Hace scroll para cargar todos los productos
3. Extrae los ASINs de los links de la página
4. Visita hasta 10 productos en detalle
5. Filtra: valida contra `scraping_config.json` (ahorro mínimo en pesos `$400 MXN` y porcentaje configurado)
6. Por cada producto aprobado:
   - Extrae título, precio oferta, precio original, descuento, imagen
   - Genera el link de afiliado:
     - **Con sesión:** usa SiteStripe (link de Associates)
     - **Sin sesión (fallback):** `?tag=AMAZON_PARTNER_TAG`
   - Toma screenshot de imagen + precio (bounding box)
7. Guarda directo en `products_list.json` (cola general) — **ya listos para publicar, sin pasar por pending_affiliate**

#### Detección de sesión (orden de prioridad)
```
storage_state_amazon.json  ← sesión dedicada Amazon (si existe)
storage_state_linux.json   ← sesión Linux (FB + Pinterest)
storage_state.json         ← sesión Windows sincronizada vía Syncthing
```

La sesión es la que se inició con Chrome en Amazon Associates. El scraper usa la que encuentre primero.

#### Variable .env requerida
```
AMAZON_PARTNER_TAG=tuTag-20   # tag de afiliado para los links ?tag=
```

#### Diferencia clave con ML
Los productos de Amazon **no requieren paso manual de afiliado** — el link ya viene con el tag embedido. Se publican directamente en el siguiente slot.

---

## 10. FLUJO COMPLETO DE PUBLICACIÓN POR SLOT

```
Scheduler (cada hora en slots configurados)
  │
  ├─► [background] apify_refiller.check_and_refill()
  │     ├─ Si cola general < 10 → Amazon scraper
  │     ├─ Si cola general < 10 y pasaron 24h → Apify actor (keyword general)
  │     ├─ Si cola baby < 10 y pasaron 24h → Apify actor (keyword bebes)
  │     └─ Si cola pets < 10 y pasaron 24h → Apify actor (keyword perros)
  │     (Tenis y Moda no tienen refill automático)
  │
  └─► Para cada cola: general → baby → pets → tenis → moda
        │
        ├─ Busca primer producto listo (meli.la o Amazon, no en historial)
        ├─ Valida que no tenga valores N/A
        │
        └─► orchestrator.run_publication()
              ├─ Descarga imagen desde image_url (aiohttp, sin sesión)
              ├─ Si ML: valida meli.la, limpia título con Gemini
              ├─ Filtra targets_active por nicho:
              │   General → facebook, fb_page, telegram (general), pinterest, web
              │   Baby    → facebook_bebes, telegram (canal baby)
              │   Pets    → facebook_pets, telegram (canal pets)
              │   Tenis   → facebook_tenis, telegram (canal general)
              │   Moda    → facebook_moda, telegram (canal general)
              ├─ Publica: Pinterest → Facebook (bloque rotativo) → Telegram canal
              ├─ Registra en published_history.json
              └─ Actualiza website_db.json → push GitHub
```

---

## 11. VARIABLES DE ENTORNO (.env en raíz del proyecto)

```
# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=           # Chat ID del admin (recibe alertas y controla el bot)
TELEGRAM_CHANNEL_ID=        # Canal general de ofertas
TELEGRAM_CHANNEL_BABY_ID=   # Canal de bebés
TELEGRAM_CHANNEL_PETS_ID=   # Canal de mascotas

# Facebook
FB_GROUP_URLS=url1,url2     # Grupos generales (recarga en caliente)
FB_GROUPS_BABY_URLS=        # Grupos de bebés
FB_GROUPS_PETS_URLS=        # Grupos de mascotas
FB_PAGE_ID=                 # Página de Facebook
FB_PAGE_TOKEN=              # Token Graph API para la página

# IA
GEMINI_API_KEY=             # Para limpieza de títulos y copy
ELEVENLABS_API_KEY=         # Para TTS de videos premium

# Afiliados
AMAZON_PARTNER_TAG=         # Tag de afiliado Amazon (ej: gangas-20)

# Apify (llenado automático de colas ML)
APIFY_API_TOKEN=
APIFY_KEYWORD_GENERAL=tecnologia
APIFY_KEYWORD_BABY=bebes
APIFY_KEYWORD_PETS=perros

# Infraestructura
GITHUB_TOKEN=               # Para push de landing page gangasmx.com
BLACKLIST_WORDS=funda,mica,case,protector,cable
MIN_PRICE=100.0
```

---

## 12. PROBLEMAS CONOCIDOS Y SOLUCIONES

| Problema | Solución |
|---|---|
| Video premium no se genera | Verificar que details["script"] tenga 6 líneas al llegar al bloque de video |
| Conflictos .sync-conflict | Eliminar los archivos .sync-conflict-* y quedarse con el más reciente |
| Error Unicode en PowerShell | Usar `$env:PYTHONIOENCODING="utf-8"` antes de correr scripts |
| YouTube sesión expirada | Correr `refresh_youtube_session.py` o `import_youtube_cookies.py` |
| Amazon detecta bot (CAPTCHA) | Reintentar más tarde; el scraper lo omite y sigue con el siguiente producto |
| Cola no avanza (mismo producto) | Revisar que el producto publicado se registre en published_history.json; si falla la publicación el scheduler no lo marca |
| Producto ML no publica (no tiene meli.la) | El bot manda la URL de ML por Telegram — el usuario genera el meli.la y lo responde al bot |
| Apify refill no se dispara | Verificar APIFY_API_TOKEN en .env del VPS y que la cola tenga efectivamente menos de 10 con meli.la |

---

## 13. COMANDOS DIAGNÓSTICO

```bash
# En Linux — logs del bot en tiempo real
journalctl -u amazon_bot -f
systemctl status amazon_bot
sudo systemctl restart amazon_bot

# Contar productos listos en cada cola
python3 -c "
import json, os
colas = [
    ('products_list.json','General'),
    ('products_list_baby.json','Baby'),
    ('products_list_pets.json','Pets'),
    ('queue_tenis.json','Tenis'),
    ('queue_moda.json','Moda'),
]
for f, label in colas:
    if not os.path.exists(f): print(f'{label}: archivo no encontrado'); continue
    q = json.load(open(f))
    listos = [p for p in q if 'meli.la' in p.get('affiliate_url','') or p.get('source')=='amazon']
    pendientes = [p for p in q if p.get('review_status')=='pending_affiliate']
    print(f'{label}: {len(listos)} listos, {len(pendientes)} pendientes de afiliado, {len(q)} total')
"

# Probar Amazon scraper manualmente
python3 -c "import asyncio; from scrapers.amazon_deals_linux import run; print(asyncio.run(run()))"
```

```powershell
# En Windows — Ver procesos Python activos
Get-CimInstance Win32_Process -Filter "name = 'python.exe'" | Select-Object ProcessId, CommandLine

# Verificar sintaxis telegram_bot.py
python -X utf8 -m py_compile core/telegram_bot.py
```

---

## 14. HISTORIAL DE CAMBIOS

### 11-Jul-2026 — Sistema de tres nichos + Apify automatico + Amazon scraper

**orchestrator.py:**
- Resultados dict completo con claves `facebook_bebes` y `facebook_pets`
- `targets_active` se filtra por nicho antes de publicar (baby → solo facebook_bebes, pets → solo facebook_pets)
- Descarga directa de imagen desde `image_url` con aiohttp antes de Playwright auto-capture

**telegram_bot.py:**
- Corregido `is_baby` → `is_no_video_niche` (causaba crash al ver productos en cola)
- Excluidos nichos baby y pets de generacion de video
- Nuevo metodo `_update_pending_affiliate(meli_url)` — detecta links meli.la recibidos y actualiza el primer producto pendiente en cualquier cola
- Nicho pets agregado a todas las condiciones donde solo estaba baby

**user_state.json:**
- Agregado `"facebook_pets": true` a `active_networks`

**.env (VPS Linux):**
- Agregado `TELEGRAM_CHANNEL_PETS_ID` para canal de mascotas
- Agregado `APIFY_API_TOKEN`

**core/apify_refiller.py — NUEVO ARCHIVO:**
- Rellena automaticamente las 3 colas desde Apify cuando bajan de 10 productos listos
- Cooldown de 24 horas por nicho para no quemar creditos
- Filtra productos con menos de 30% de descuento
- Manda notificacion Telegram con resumen + un mensaje por producto con la URL de ML
- Tambien dispara el Amazon scraper para la cola general

**scrapers/amazon_deals_linux.py — NUEVO ARCHIVO:**
- Scraper de amazon.com.mx/deals para Linux (headless, sin sesion requerida)
- Filtra menos de 30% de descuento
- Link de afiliado: SiteStripe si hay sesion, `?tag=AMAZON_PARTNER_TAG` como fallback
- Screenshot automatico de imagen + precio
- Guarda directo en products_list.json (ya listo para publicar)

**core/scheduler.py:**
- Llama `check_and_refill(orchestrator)` en cada slot como tarea en segundo plano

### 02-Jul-2026 — Estabilizacion Pipeline Premium
- *### Cómo funciona (`build_site.py`)
1. Busca archivos `.md` en la carpeta `content/articles/`.
2. Lee el bloque Frontmatter de cada artículo (título, descripción, fecha, etc.) y genera páginas estáticas.
3. Estas URLs se inyectan automáticamente en el sidebar del blog bajo "📝 Reseñas y Artículos" y en el `sitemap.xml`.

> **Nota:** La automatización de estos textos se rige mediante un pipeline de SEO Médico/E-commerce paralelo, pero la ingesta final en la web es exclusivamente mediante estos archivos Markdown + Frontmatter.

---

## 16. RESOLUCIÓN DE BUGS CRÍTICOS Y REGLAS DE ARQUITECTURA

### 16.1 Sincronización del Web Panel (Next.js) vs Syncthing
- **El Problema:** Syncthing copia el código fuente (.tsx, .ts, etc.) de manera instantánea de Windows a Linux. Sin embargo, en Linux el Panel Web se ejecuta en modo producción (usualmente a través de una compilación previa) o bajo dev server.
- **La Regla:** Cualquier modificación que implique cambios en la interfaz gráfica, componentes React o la lógica del frontend (ej. `web-panel/src/app/...`) requiere que el proceso de Next.js se reinicie (`sudo systemctl restart gangas_web`) para liberar memoria y aplicar cambios.

### 16.2 Arquitectura de Colas y Productos Fantasma (Bug de Borrado)
- **El Problema:** El sistema maneja múltiples colas de forma independiente (`products_list.json` para general, `queue_tenis.json` para tenis, `queue_moda.json` para moda, etc.). Un mismo producto puede existir simultáneamente en la general y en una o más colas de nicho.
- **La Regla:** El endpoint de borrado de la API (`/api/queues/{niche}/{product_id}`) **DEBE** iterar obligatoriamente sobre el diccionario global `QUEUE_FILES` y eliminar el producto de absolutamente todos los archivos donde exista.

### 16.3 Resiliencia del Scheduler frente a fallos de IA
- **El Problema:** El bucle principal de publicación en `core/scheduler.py` utiliza Gemini para limpiar títulos o generar guiones. Si Gemini devolvía un error de API (ej. Quota Exceeded), el bot entero se bloqueaba o descartaba el slot completo.
- **La Regla:** El código de `run_publication` y el bucle interno del `scheduler.py` deben aislar las excepciones. Si la publicación de un producto falla por culpa de la IA (o cualquier otro motivo crítico), el código debe marcar `slot_results[niche] = "❌ Falló publicación"`, sumar 1 al contador de `failed_attempts` del producto, e inmediatamente ejecutar un `continue` para intentar publicar **el siguiente producto válido de la cola** sin detener la ejecución del slot para ese nicho.

---

## 17. ESTADO DEL SISTEMA Y HOJA DE RUTA CONSOLIDADA (Septiembre 2026)

### 17.1 Depuraciones Permanentes Realizadas (22 Septiembre 2026)
Quedaron completamente eliminadas del código, API, frontend y documentación:
1. **Tracking de Clics (`click_tracking.json`):** Endpoints `/api/clicks` y `/api/track_click` eliminados, vista `/clicks` en Next.js removida.
2. **Diagnóstico Matutino (7:50 AM) y Reporte Nocturno (23:00):** Tareas eliminadas de `core/scheduler.py` y `core/orchestrator.py` para evitar spam de reportes periódicos en Telegram.
3. **Súper Ofertas VIP (`super_oferta_{nicho}.json`):** Bypass y cola prioritaria eliminados de `core/scheduler.py` y callback eliminado de `core/telegram_bot.py`.

### 17.2 Mejoras en API y Resiliencia
- **Recursos del Sistema sin psutil:** `/api/system/resources` ahora lee nativamente `/proc/meminfo` y `shutil.disk_usage('/')` con fallback automático.
- **Reinicio Seguro:** `/api/bot/restart` maneja fallbacks con `pkill` nativo en Linux, y se creó `/api/system/restart-web` para reciclar Next.js vía API.

### 17.3 Política de Respaldos
- Los respaldos locales completos del sistema se archivan en `backups/`.
- Último respaldo completo previo a optimizaciones: `backups/backup_sistema_20260922_175811.zip` (907 archivos, 60.89 MB).

### 17.4 Implementaciones de Optimización Ejecutadas (23 Septiembre 2026) ✅

Todas las fases de la hoja de ruta fueron implementadas, testeadas con pruebas en vivo y sincronizadas:

1. **Métrica Reina — Priorización por Ahorro Real en Pesos ($ MXN):**
   - **Endpoint API (`POST /api/queues/{niche}/sort-by-savings`):** Reordena físicamente el archivo JSON de la cola (`products_list.json`, etc.) organizando los productos de mayor a menor ahorro en pesos.
   - **Controles en Panel Web (`web-panel/src/app/queues/[niche]/components/QueueClient.tsx`):**
     - Píldoras de ordenación inmediata: *Cola Real (FIFO)*, *Mayor Ahorro ($)*, *Mayor Dto (%)*, *Menor Precio*.
     - Botón de acción: *"Reordenar Cola por Mayor Ahorro ($)"* que re-ancla físicamente la cola en el servidor para que el bot publique primero las mejores ofertas en dinero real.

2. **Fase 1 — Seguridad, Anti-Bloqueos y Tiempos:**
   - **Filtro de Libros ("Pasta blanda" y "Pasta dura"):** Agregados a `excluded_keywords` en `scraping_config.json` y unificados en `_validate_product_for_publication` de `core/orchestrator.py` con reporte detallado del término causante del descarte.
   - **Filtro Estricto de Video Premium:** Bloquea la generación de guiones y la síntesis con ElevenLabs en `core/orchestrator.py` y `tiktok_generator.py` para productos con `ahorro < $250` o `precio < $300` (salvo que el usuario fuerce el video manualmente).
   - **Jitter de Horarios (`core/scheduler.py`):** Retraso aleatorio controlado de **+30s a +180s** en cada slot programado para eliminar patrones mecánicos detectables por algoritmos de redes sociales.

3. **Fase 2 — Variabilidad de Mensajes Determinista sin IA:**
   - **Matrices de Copys (`core/message_builder.py`):**
     - 10 ganchos conversacionales para productos con descuento y 7 para productos sin descuento.
     - Variaciones dinámicas de llamadas a la acción (CTAs) de compra para Facebook.
     - Formatos rotativos de ahorro en pesos y menciones variables a `gangasmx.com` y Telegram.
     - Rotación de sets de hashtags.
   - **Seed Determinista (`_get_product_rng`):** Sembrado por el ID/URL del producto mediante hash MD5. Cada producto recibe un copy único y natural, pero completamente reproducible si se re-evalúa. Costo de tokens de Gemini: **$0**.

4. **Fase 3 — Auto-Recuperación y Barredora de Bloqueos:**
5. **Detección de Bloqueos Huérfanos (`_lock_acquired_time > 600s`):** Tanto `core/orchestrator.py` como `core/scheduler.py` monitorean la duración de `_publish_lock`. Si una sesión de Playwright se cuelga por más de 10 minutos, el candado se libera automáticamente, se notifica a Telegram (`🛡️ Auto-Recuperación`) y el sistema continúa operando sin intervención manual.
   - **Botón y Endpoint de Reinicio Total:** `/api/system/restart-all` y botón en `/settings` del Panel Web para reiniciar simultáneamente API, Web y Bot sin requerir comandos de terminal.
   - **Restauración de Callbacks del Bot (`core/telegram_bot.py`):** Corregido el árbol de indentación que dejaba inactivos los 62 botones de callback query.

### 17.5 Pipeline de Títulos Limpios y Eliminación de Keyword Scrambling (24 Septiembre 2026) ✅

Se corrigió de raíz el error que causaba que productos como escritorios o mochilas se publicaran con títulos incoherentes (ejemplo: *"esta Laptop Escritorio Para Computadora..."* cuando el producto real era un escritorio de madera para computadora):

1. **Serialización Completa en `EnrichedProductDetails.to_dict()` (`core/product_types.py`):**
   - **Causa Raíz:** El método `to_dict()` no exportaba las propiedades `clean_title`, `category`, `description` ni `affiliate_link`. Por ende, cuando el orquestador enriquecía el producto con Gemini y lo serializaba hacia los publicadores, estos recibían un diccionario sin `clean_title` y caían de vuelta en el título crudo de 150 caracteres de Mercado Libre.
   - **Solución:** Se incluyeron explícitamente todos los campos en la serialización hacia diccionario.

2. **Eliminación del Regex Destructivo de Swap en `core/message_builder.py`:**
   - **Causa Raíz:** La función de limpieza manual `_clean_title()` contenía una expresión regular (`re.sub(r'^([A-Z0-9][a-zA-Z0-9\s\-\.\"\’]+?)\s+(Barra de Sonido|...|Laptop|...)\b', r'\2 \1', clean)`) diseñada para reordenar marcas y tipos de producto. Sin embargo, al toparse con títulos como *"Mesa de estudio para Laptop PC..."*, la regex capturaba todo el texto previo y la palabra *"Laptop"*, anteponiendo *"Laptop"* al inicio del título (*"Laptop Mesa de estudio..."*).
   - **Solución:** Se erradicó por completo el intercambio forzado de palabras por regex. Se prioriza el `clean_title` generado por Gemini; y en caso de fallback manual, `_clean_title(raw)` preserva el orden gramatical del producto original cortando limpiamente hasta 75 caracteres sin dejar preposiciones colgadas al final.

3. **Detección de Género por Sustantivo Rector (`_detect_article`):**
   - **Causa Raíz:** El detector de artículos gramaticales buscaba palabras clave en cualquier parte del título (`f" {k}" in clean_lower`). Si un escritorio mencionaba la palabra *"laptop"*, detectaba femenino y asignaba *"esta"*.
   - **Solución:** `_detect_article(title)` ahora analiza estrictamente el sustantivo inicial (las primeras palabras del título). Si el producto inicia con "Escritorio", "Soporte", "Cable", asigna "este"; si inicia con "Mesa", "Bolsa", "Silla", asigna "esta".

4. **Refuerzo de Prompt en `core/orchestrator.py` y Sincronización en `publishers/twitter_publisher.py`:**
   - El prompt enviado a Gemini instruye categóricamente preservar la identidad del objeto principal (ej. si es accesorio o mueble para laptop, jamás nombrarlo laptop).
   - Si Gemini agota cuota (HTTP 429), el orquestador cae suavemente al nuevo `_clean_title()` garantizando títulos concisos y lógicos.

---

### 17.6 Optimización de Navegación del Panel Web Next.js (24 Septiembre 2026) ✅

Se eliminó la sensación de congelamiento o lentitud que obligaba al usuario a refrescar manualmente la página (F5) al navegar entre vistas:

1. **Causa Raíz:**
   - En Linux, `gangas_web.service` corre Next.js en modo desarrollo (`npm run dev`). Next.js compila las rutas bajo demanda (*on-demand compilation*), tomando de 1.5 a 4 segundos por página no cargada previamente.
   - En Next.js App Router, si no existe un archivo `loading.tsx`, el navegador no da **ninguna retroalimentación visual (0ms)** mientras la página compila en el servidor, dando la impresión de que el clic no funcionó o la app se trabó.
   - Además, la barra lateral (`Sidebar.tsx`) tenía 9 enlaces con `prefetch={true}`, lo que provocaba que al cargar el panel se dispararan múltiples compilaciones simultáneas en Node.js, saturando el CPU de la laptop.
   - Por último, `queues/page.tsx` y `queues/[niche]/page.tsx` incluían un fallback innecesario al puerto muerto 8000 con timeout de 1000ms en caso de error.

2. **Soluciones Implementadas:**
   - **Skeleton de Carga Inmediata (`web-panel/src/app/loading.tsx`):** Proporciona un esqueleto de React Suspense animado instantáneo en cuanto el usuario hace clic en cualquier ruta.
   - **Barra de Progreso Reactiva (`web-panel/src/components/NavigationProgressBar.tsx`):** Barra superior de brillo cian (`#06b6d4`) montada en `AppShell.tsx` que arranca a 30% en 100ms, avanza dinámicamente y posee un seguro anti-congelamiento que fuerza `window.location.href` a los 2.5s si el router de React se atora.
   - **Desactivación de Prefetch Masivo:** Se configuró `prefetch={false}` en `Sidebar.tsx` y `BottomNav.tsx` para que Next.js solo compile la página que el usuario realmente solicita.
   - **Limpieza de Puerto 8000:** Se eliminaron los fallbacks al puerto 8000 en componentes de servidor, reduciendo la latencia de red.
   - **Configuración `next.config.ts`:** Añadido `127.0.0.1` a `allowedDevOrigins` para llamadas locales.

---

### 17.7 Auto-Purga de Productos Zombi en Colas y Aclaración de Métricas (24 Septiembre 2026) ✅

1. **Resolución de Productos Atascados en Cola (Soundcore Q20i y Shure SM-57):**
   - **Causa Raíz:** Productos con ahorro inferior a `$400 MXN` (ej. $300 y $346) eran rechazados por la validación estricta y anotados en `discarded_products.json`. Sin embargo, `core/scheduler.py` únicamente hacía `if is_already_discarded: continue` saltando el producto, pero **dejándolo físicamente dentro del archivo `products_list.json`**. Esto causaba que los productos permanecieran visibles en el Panel Web y en la cabeza de la cola indefinidamente como zombis.
   - **Solución:** `core/scheduler.py` ahora purga automáticamente de disco cualquier producto registrado en `discarded_products.json`, reescribiendo la cola limpia de inmediato.

2. **Aclaración de Métrica Reina (Ahorro en Pesos vs Porcentaje):**
   - Toda la arquitectura (orquestador, scheduler, scraping_config.json y Panel Web) opera gobernada por el **Ahorro Mínimo en Pesos ($ MXN)** (`min_strict_savings = $400`). El porcentaje no es la condición determinante de publicación cuando el ahorro en dinero real es inferior al umbral configurado.

3. **Corrección en `affiliate_linker.py`:**
   - Corregido el manejo de cadenas con saltos de línea `\n` al interactuar con enlaces de Mercado Libre y robustecido el flujo de generación masiva de afiliados.

---

### 17.8 Resolución del Bug de Precios Invertidos y Fuga de Selectores en Páginas Sociales (24 Septiembre 2026) ✅

Se investigó y solucionó la publicación anómala de productos con precio de oferta mayor al precio original (ejemplo: *"Precio original: $699 / Precio oferta: $1104 con 41% de descuento"* en el Mouse Gamer Razer Cobra):

1. **Causa Raíz Principal — Fuga de Selectores en la Página Social (`scrapers/ml_scraper.py`):**
   - Cuando un enlace `meli.la` redirige a la página de perfil/feed social del afiliado (`/social/laloehm?...`), Mercado Libre renderiza una cuadrícula con decenas de tarjetas de productos (`.poly-card`).
   - El scraper ejecutaba `document.querySelector` a nivel global en todo el documento HTML:
     - `offerEl` buscaba `.poly-price__current` y coincidía con la tarjeta #0 (el Mouse Razer Cobra), cuyo precio actual en Mercado Libre era de **$1,104** a precio regular (su oferta había expirado y ya no tenía descuento).
     - Al no haber precio tachado (`<s>`) en la tarjeta #0, `document.querySelector('s .andes-money-amount__fraction')` continuaba buscando por todo el DOM y capturaba el precio tachado de la tarjeta #1 (un producto distinto, Ratón Razer DeathAdder): **$699**.
     - Lo mismo ocurría con `document.querySelector('.poly-price__disc')`, capturando el badge de descuento de la tarjeta #1: **41% OFF**.
   - **Resultado:** El scraper fusionó el precio actual del producto #0 ($1,104) con el precio original ($699) y el descuento (41%) del producto #1.

2. **Causa Secundaria — Omisión de Validación en `core/orchestrator.py`:**
   - En `_validate_product_for_publication()`, la condición `if details.original_price and details.original_price > details.price:` solo se activaba si el precio original era estrictamente mayor al de oferta. Al ser $699 <= $1104, la condición se saltaba silenciosamente y el producto pasaba como "válido".
   - Tampoco existía rechazo obligatorio para productos que hubieran perdido el precio de descuento (`original_price is None`).

3. **Solución Implementada y Verificada:**
   - **Aislamiento Estricto por Tarjeta (`scrapers/ml_scraper.py`):** Los selectores de precio de oferta, precio de lista y descuento ahora se ejecutan exclusivamente dentro de la tarjeta objetivo del producto (`targetCard.querySelector(...)`). Además, si `Number(offer) >= Number(list)`, el JavaScript descarta inmediatamente `list` y `discount`.
   - **Triple Validación en Orquestador (`core/orchestrator.py`):**
     1. Si `not details.original_price`: Se rechaza como `⚠️ PRODUCTO SIN DESCUENTO ACTIVO` (oferta expirada).
     2. Si `details.original_price <= details.price`: Se rechaza como `⚠️ PRECIOS INCOHERENTES (OFERTA >= ORIGINAL)`.
     3. Si `savings_pesos < min_savings`: Se rechaza como `⚠️ DESCUENTO INSUFICIENTE`.
   - **Salvaguarda Final en Generador de Mensajes (`core/message_builder.py`):** Si por cualquier anomalía llegara un producto con precio de oferta mayor o igual al original, se anula `list_price` impidiendo que jamás se imprima un precio tachado menor a la oferta.
---

### 17.9 Unificación de Conteo de Colas y Purga Automática de Publicados (26 Septiembre 2026) ✅

1. **Discrepancia Entre Conteo Raw y Panel Web (48 vs 6 productos):**
   - **Diagnóstico:** En una inspección cruda del archivo `products_list.json` existían 66 productos almacenados, de los cuales 48 tenían enlaces de afiliados (`meli.la` o `amazon`). Sin embargo, **60 de esos 66 productos ya habían sido publicados en días y semanas anteriores** y estaban registrados en `published_history.json`.
   - **Por qué el Panel Web mostraba solo 6:** El endpoint de la API (`api/main.py: get_queue()`) cuenta con un filtro estricto que descarta cualquier producto cuyo ID o URL de afiliado figure en `published_history.json`. Por ende, el Panel Web mostraba con total precisión los **6 productos realmente pendientes**:
     1. `MLM79498490` - Cargador USB C 118W Para Laptop (Listo con `meli.la/1QU4chB`)
     2. `MLM6162587152` - Dell Latitude 5320 2 En 1 (Pendiente link)
     3. `MLM2927481167` - Dell Optiplex 7040 Sff Pc (Pendiente link)
     4. `MLM4668802798` - Lenovo Thinkpad X1 Carbon G9 (Pendiente link)
     5. `MLM2721739733` - Laptop Dell Latitude 5420 (Pendiente link)
     6. `MLM44433125` - Monitor Gamer 27" Xtreme Pc (Listo con `meli.la/19FNLNt`)
   - **Causa Raíz de la Acumulación:** Al finalizar una publicación exitosa, `_finalize_publication()` en `core/orchestrator.py` agregaba el producto a `published_history.json`, pero no ejecutaba `_remove_from_queue()` para desalojarlo físicamente del archivo JSON de la cola.

2. **Soluciones Implementadas:**
   - **Desalojo Automático al Publicar (`core/orchestrator.py`):** Se integró `self._remove_from_queue(enriched.id, enriched.url)` dentro de `_finalize_publication()`. Cada producto publicado se remueve físicamente de todas las colas de inmediato.
   - **Purga Defensiva en el Scheduler (`core/scheduler.py`):** Al iniciar la revisión de colas de cada slot, el scheduler ahora elimina de los archivos de cola tanto los productos descartados (`is_already_discarded`) como los que ya existen en `published_history.json` (salvo que tengan `force_publish=True`).
   - **Limpieza de Archivo en Disco:** Se purgó `products_list.json`, pasando de 66 a exactamente los 6 productos pendientes reales, unificando al 100% las lecturas de terminal, scripts y el Panel Web.

---

### 17.10 Gobierno 100% por Ahorro en Pesos ($ MXN) en Toda la Arquitectura (26 Septiembre 2026) ✅

1. **Eliminación Definitiva de Filtros de Porcentaje:**
   - Previamente, aunque el Orquestador y el Panel Web operaban gobernados por el Ahorro en Pesos (`min_strict_savings`), los scrapers automáticos (`core/apify_refiller.py`, `scrapers/amazon_deals_linux.py` y `core/utils.py`) conservaban internamente una condición residual que exigía al menos 15% de descuento (`and disc_val_pct >= min_discount_pct`).
   - Esto provocaba que productos con excelente ahorro en dinero (ej. Laptops que ahorraban $962 y $858 MXN pero con 11% o 12% OFF) fueran descartados innecesariamente.

2. **Unificación al 100% en Pesos:**
   - **`core/apify_refiller.py`:** Aprobación automática cuando `ahorro_pesos >= min_ahorro_estricto` (leído dinámicamente de `scraping_config.json`, configurado desde el Panel Web). Eliminada la constante fija `MIN_DISCOUNT_PCT`.
   - **`scrapers/amazon_deals_linux.py`:** Aprobación automática cuando `ahorro_pesos >= min_ahorro_estricto`. Eliminada la condición `discount_pct >= min_discount_pct`.
   - **`core/utils.py` (`filter_blacklist_product`):** Evalúa el ahorro estricto en pesos contra `min_strict` y la presencia de descuento activo, sin bloquear por porcentaje.
   - **`core/orchestrator.py`:** Se mantiene gobernando las publicaciones por `savings_pesos >= min_savings`.

---

### 17.11 Sistema de Expiración de Historial y Re-aprobación a las 3 Semanas (TTL de 21 Días) (27 Septiembre 2026) ✅

1. **Problema del Bloqueo Perpetuo:**
   - Históricamente, `published_history.json` era una lista plana de strings sin marcas de tiempo. Todo producto publicado quedaba bloqueado "de por vida", impidiendo que los scrapers o el orquestador volvieran a publicar ofertas de productos cíclicos excelentes (laptops, consolas, pantallas) cuando meses después volvían a tener promociones destacadas.

2. **Solución Implementada (`core/history_manager.py`):**
   - **Evolución a Formato con Marcas de Tiempo:** `published_history.json` se migró a un mapa clave-valor `{identificador: iso_timestamp}`. Se rescataron los timestamps reales de los últimos 200 productos desde `website_db.json` y `last_published.json`, y los productos antiguos (>45 días) se marcaron como ya expirados.
   - **Ventana de Expiración (TTL de 21 días / 3 semanas):** Configurable en `scraping_config.json` mediante `"history_ttl_days": 21` y expuesto visualmente en el Panel Web (`/settings`).
   - **Filtro Dinámico `load_recent_history()`:** Todos los componentes (`core/orchestrator.py`, `core/scheduler.py`, `core/apify_refiller.py`, `scrapers/amazon_deals_linux.py`, `api/main.py` y `core/telegram_bot.py`) ahora evalúan duplicados únicamente contra publicaciones recientes (< 21 días).
   - **Elegibilidad de Re-aprobación:** Si un producto fue publicado hace más de 21 días, expira del filtro activo y queda 100% elegible para volver a entrar a la cola y ser publicado si vuelve a detectarse con oferta válida.
   - **Registro Atómico:** Cada nueva publicación actualiza el timestamp en `published_history.json` con la fecha y hora de la nueva publicación, reiniciando su ventana de 21 días.

---

### 17.12 Ciclos Rotativos Secuenciales de Términos de Scraping (30 Septiembre 2026) ✅

1. **Objetivo y Necesidad:**
   - Previamente, cada nicho tenía un único término fijo de búsqueda en `scraping_config.json` (ej. "tecnologia", "bebes", "perros"). Para diversificar las ofertas y no saturar las colas con el mismo tipo de producto, se implementó un sistema de rotación secuencial cíclica (Round-Robin) entre múltiples términos configurables.

2. **Solución Implementada:**
   - **Formato Simple Separado por Comas:** En el Panel Web (`/settings`), el usuario puede ingresar múltiples términos separados por comas para cualquier nicho (ej. `laptops gamer, monitores, herramientas dewalt, smart tv`).
   - **Rotación Round-Robin Persistente (`core/apify_refiller.py`):**
     - La función `get_scraping_keyword(niche, default, advance=False)` extrae la lista de términos limpios, obtiene el cursor actual guardado en `scraping_cursors.json` y calcula el índice mediante módulo (`cursor % len(terms)`).
     - Si `advance=True`, incrementa el cursor secuencialmente (`(idx + 1) % len(terms)`) y lo guarda de forma atómica con `json_save_atomic`.
     - Sobrevive a reinicios del bot y de los servicios sin perder el turno.
   - **Respeto Estricto de Estado de Pausa:**
     - La función `is_scraper_enabled(niche, scraper_status)` valida si el scraper de ese nicho está activo en `scraper_status.json`.
     - Si un scraper está en pausa/desactivado, el scheduler lo omite y **el cursor NO rota ni se consume**, preservando el turno exacto para cuando se reactive.
   - **Integración con Amazon Scraper (`scrapers/amazon_deals_linux.py`):**
     - Acepta el parámetro `keyword_override` pasado desde `_check_amazon_refill` para buscar en Amazon Deals las ofertas del término rotativo que corresponde en el nicho general.
   - **Visualización en el Web Panel (`web-panel/src/app/settings/page.tsx`):**
     - Muestra píldoras interactivas con cada término del ciclo y flechas de secuencia (`Término 1 → Término 2 → Término 3`).
     - Indicador visual animado pulsante en el término que se encuentra actualmente en turno.
     - Badge informativo `⏸️ Auto-Scraper Pausado` si el auto-scraper del nicho se encuentra desactivado.

---

### 17.13 Depuración y Eliminación de la Pantalla Legacy de Apify Staging (30 Septiembre 2026) ✅

1. **Contexto:**
   - La pantalla `/apify` y sus endpoints asociados (`/api/apify/products`, `approve`, `discard`) correspondían a un flujo histórico manual anterior al auto-refill en segundo plano.
   - Con la consolidación del motor autónomo (`core/apify_refiller.py` y `scrapers/amazon_deals_linux.py`) que inyecta ofertas directamente a las colas activas y resuelve afiliados en Telegram, dicha vista quedó completamente obsoleta y en desuso con 0 productos.

2. **Acciones de Limpieza Ejecutadas:**
   - **Frontend:** Eliminada la ruta `web-panel/src/app/apify/` y removido el enlace del menú en `web-panel/src/components/Sidebar.tsx`.
   - **Backend API (`api/main.py`):** Eliminados endpoints `/api/apify/products`, `/api/apify/products/{sku}/approve` y `/api/apify/products/{sku}/discard`.
   - **Archivos de Disco:** Eliminados `apify_products.json`, `apify_discarded.json` y el script de prueba `monitor_apify.sh`.


