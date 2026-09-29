# Sistema de Afiliados Automatizado — GangasMX

Bot de marketing de afiliados que scrapea ofertas de Mercado Libre, genera links de afiliado y publica automáticamente en Facebook, Pinterest, Telegram y una landing page.

---

## Arquitectura general

```
Windows (8 AM diario)                Linux VPS (24/7)
──────────────────────               ────────────────────────────
run_scraper_windows.py               amazon_deal_bot.py --schedule
  ├─ ml_offers_scraper.py              ├─ telegram_bot.py  (escucha comandos)
  ├─ image_cache/ (descarga imgs)      └─ scheduler.py     (8 slots diarios)
  └─ affiliate_linker.py                    └─ orchestrator.py (publica)
         │
         └──► Syncthing sincroniza products_list.json + image_cache/ → Linux
```

**Puntos clave de diseño:**
- Windows tiene sesión de ML (para affiliate linker). Linux NO toca ML para no invalidar esas cookies.
- Los archivos de sesión son separados: `storage_state.json` (Windows) y `storage_state_linux.json` (Linux).
- ML API: **NO viable** (search bloqueado desde abril 2025, items solo devuelve productos propios).
- Facebook Graph API: **NO disponible** para publicar en grupos en apps nuevas (desde Cambridge Analytica). Todo es Playwright.

---

## Archivos del proyecto

### Raíz
| Archivo | Descripción |
|---|---|
| `amazon_deal_bot.py` | **Entry point principal.** CLI con flags: `--schedule`, `--login`, `--dry-run`, `--visible`, o URL directa |
| `run_scraper_windows.py` | Rutina diaria de Windows (8 AM). Scraper → imágenes → affiliate links → notifica a Telegram |
| `ml_offers_scraper.py` | Scraper **anónimo** (sin sesión) de la página de ofertas de ML. Filtra por categoría y 50%+ descuento |
| `affiliate_linker.py` | Convierte URLs raw de ML a links `meli.la` usando el linkbuilder web con sesión activa |
| `manual_login.py` | Abre un navegador para hacer login manual y guardar la sesión |
| `build_site.py` | Genera el HTML de gangasmx.com desde `website_db.json` |
| `tiktok_generator.py` | Genera videos de TikTok/Reels desde datos del producto |
| `amazon_offers_scraper.py` | Scraper standalone de ofertas Amazon (no integrado en el flujo automático) |

### `core/`
| Archivo | Descripción |
|---|---|
| `orchestrator.py` | **Lógica central de publicación.** Método `run_publication()`. Scrape → imagen → Gemini → Pinterest → Facebook → Telegram → TikTok → Web |
| `telegram_bot.py` | Bot de control (2099 líneas). Panel de botones, IA Gemini, admin browser, modo cola, modo edición |
| `scheduler.py` | Vigilante de 8 slots diarios (8,10,12,14,16,18,20,22 hrs). Publica un producto por slot |
| `message_builder.py` | Genera textos variados anti-spam con `random.choice()`. Detecta categoría por keywords y asigna emoji |
| `config.py` | Configuración global. `FB_GROUPS` recarga el `.env` en caliente en cada acceso |
| `session_manager.py` | Carga y guarda `storage_state.json` / `storage_state_linux.json` según OS |
| `utils.py` | `with_retry` (decorador async), `filter_blacklist_product`, `check_title_similarity`, `escape_markdown` |

### `publishers/`
| Archivo | Descripción |
|---|---|
| `facebook_publisher.py` | Publica en grupos de FB via Playwright. Maneja rate limits, sube imagen, restaura saltos de línea |
| `pinterest_publisher.py` | Publica en Pinterest via Playwright. Usa `@with_retry` |
| `telegram_publisher.py` | Publica en el **canal** de Telegram via HTTP API (no Playwright) |
| `web_publisher.py` | Actualiza gangasmx.com: inserta en `website_db.json` → build HTML → push a GitHub via REST API |

### `scrapers/`
| Archivo | Descripción |
|---|---|
| `ml_scraper.py` | Scrape de una página individual de ML. Soporta páginas `/p/MLM` (catálogo) y `/MLM` (listado). Maneja redirección `/social/` |
| `amazon_scraper.py` | Scrape de páginas de Amazon. Captura bounding box img+precio |

---

## Variables de entorno (`.env`)

```env
TELEGRAM_BOT_TOKEN=          # Token del bot de control
TELEGRAM_CHAT_ID=            # Chat ID del admin
TELEGRAM_CHANNEL_ID=         # Canal donde se publican las ofertas
FACEBOOK_EMAIL=              # Solo para --login
FACEBOOK_PASSWORD=           # Solo para --login
FB_GROUP_URLS=url1,url2,...  # Grupos de Facebook (se recargan en caliente)
GEMINI_API_KEY=              # Para limpieza de títulos con IA
GITHUB_TOKEN=                # Para push a GitHub (gangasmx.com)
BLACKLIST_WORDS=funda,mica,case,protector,cable
MIN_PRICE=100.0
```

---

## Archivos de datos

| Archivo | Descripción |
|---|---|
| `products_list.json` | Cola de productos con `meli.la` links listos para publicar |
| `products_draft.json` | Borrador de productos para curación manual desde Telegram |
| `published_history.json` | Set de IDs/URLs ya publicados (escritura atómica con `.tmp`) |
| `website_db.json` | Base de datos de la landing page (máx 100 productos) |
| `last_published.json` | Último producto publicado (contexto para el IA de Telegram) |
| `storage_state.json` | Sesión del navegador en Windows (ML + Facebook + Pinterest) |
| `storage_state_linux.json` | Sesión del navegador en Linux (Facebook + Pinterest únicamente) |
| `image_cache/` | Imágenes descargadas por `run_scraper_windows.py` |
| `captures/` | Captures de pantalla de productos tomadas por el orchestrator |
| `tiktok_videos/` | Videos generados por `tiktok_generator.py` |
| `logs/` | Screenshots de evidencia de publicaciones FB y errores |
| `public/` | HTML generado de gangasmx.com |

---

## Flujo completo de publicación (`orchestrator.run_publication`)

1. **Verificar sesión FB** — va a `facebook.com` con `domcontentloaded`, busca `input[email]`
2. **Scrape / datos cacheados** — si viene de la cola, usa datos del JSON; si es URL manual, scrape en vivo con contexto anónimo (Googlebot UA)
3. **Validaciones:**
   - Redirección a lista general → cancela, registra en historial
   - Mismatch de título vs. cola → cancela, registra en historial
4. **Rescate de link de afiliado** — si no hay `meli.la`, abre el linkbuilder en tiempo real con la sesión activa
5. **Limpieza de título con Gemini** — via `asyncio.to_thread` para no bloquear
6. **Auto-captura de imagen:**
   - Prioridad 1: descarga directa de la URL OG tag del scraper
   - Prioridad 2: screenshot de Playwright con CSS cleanup
   - Reutiliza si ya existe el archivo en `captures/`
7. **Publicación en plataformas** (secuencial, mismo browser context):
   - Pinterest → Facebook (en bloques rotativos 1/3 de grupos por slot) → Telegram canal
   - Entre grupos FB: delay aleatorio 3-6 minutos (anti-detección)
   - Pre-test de rate limit antes de cada cola de grupos
8. **Post-publicación:**
   - Registrar en `published_history.json` (escritura atómica)
   - Actualizar `last_published.json`
   - Actualizar `website_db.json` → rebuild HTML → push GitHub
   - Generar video TikTok (en thread separado)

---

## Cómo correr el sistema

### Setup inicial (una sola vez)
```bash
pip install -r requirements.txt
playwright install chromium
python manual_login.py       # Windows: guarda storage_state.json
```

En Linux, copiar `storage_state_linux.json` con solo sesión de FB/Pinterest.

### Windows — Rutina diaria (automática via Task Scheduler a las 8 AM)
```bash
python run_scraper_windows.py
```

### Linux — Producción (como servicio systemd)
```bash
python amazon_deal_bot.py --schedule
# o via servicio:
sudo systemctl start amazon_bot
```

### Publicación manual
```bash
python amazon_deal_bot.py https://www.mercadolibre.com.mx/...
python amazon_deal_bot.py URL --dry-run   # Simula sin publicar
python amazon_deal_bot.py URL --visible   # Con navegador visible (debug)
```

### Gestión de sesión
```bash
python amazon_deal_bot.py --login    # Abre 4 tabs: Amazon, FB, ML, Pinterest
```

---

## Panel de control Telegram

Botones inline del bot:
- **🚀 Publicar Siguiente Ahora** — publica el primer producto de la cola
- **📥 Modo Cola** — el bot acepta links via mensaje y los pone en cola
- **📘/✈️/📌/🎵/🌐 Solo [plataforma]** — cambia plataforma destino
- **📊 Estado** — muestra estado del bot y cola
- **📋 Ver Cola** — lista los productos pendientes
- **🗑️ Vaciar Cola** — limpia `products_list.json`
- **⏸️ Facebook: ACTIVO/PAUSADO** — pausa/reanuda publicaciones en FB
- **🎬 Forzar Video** — genera video TikTok del último producto
- **🌐 Forzar Web** — fuerza rebuild y push de la landing page
- **📑 Ver Errores** — muestra screenshots de errores en `logs/`
- **🔄 Reiniciar Bot** — reinicia el proceso

Comandos de texto (vía IA Gemini):
- Enviar un URL directamente → publica ese producto
- Enviar foto con URL en caption → establece imagen del producto

---

## Categorías soportadas por el scraper

El `ml_offers_scraper.py` filtra con `is_valid_product()`:
- **Tech:** laptops, celulares, audio, gaming, tablets, smartwatches, cámaras, SSDs, etc.
- **Moda:** Nike, Adidas, Jordan, tenis, pants, playeras, chamarras, joggers, jeans
- **Perfumería:** marcas reconocidas (Carolina Herrera, Hugo Boss, Calvin Klein, Dior, etc.)
- **Herramientas/Hogar:** Dewalt, Milwaukee, Makita, freidoras de aire, aspiradoras Roomba

Blacklist: medicamentos, suplementos, productos de higiene básica.
Mínimo requerido: **50% de descuento**.

---

## Notas técnicas importantes

- **GitHub uploads son secuenciales** — la Contents API crea un commit por archivo; paralelizarlos causaría conflictos de SHA (error 422).
- **`with_retry`** solo aplica en `pinterest_publisher.py`. Facebook maneja sus propios reintentos y `FacebookLimitedException` internamente.
- **`check_title_similarity`** en `core/utils.py` previene publicar productos con mismatch de redirección de ML (cuando un link redirige a otro producto diferente).
- **`Config.FB_GROUPS`** es una `@property` que recarga el `.env` en cada acceso, permitiendo agregar/quitar grupos sin reiniciar el bot.
- El orchestrator usa un `asyncio.Lock` (`_publish_lock`) para evitar publicaciones duplicadas simultáneas.
- `message_builder.py` tiene 8 intros con descuento, 6 sin descuento, 6 CTAs, 6 frases de urgencia, 4 menciones al sitio — todos con `random.choice()`. Telegram excluye el link del canal (ya están en él).
